"""MCP tool functions for the everyrow MCP server."""

import asyncio
import json
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import UUID

from everyrow.api_utils import handle_response
from everyrow.generated.api.tasks import get_task_status_tasks_task_id_status_get
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.ops import (
    agent_map_async,
    dedupe_async,
    merge_async,
    rank_async,
    screen_async,
    single_agent_async,
)
from everyrow.session import create_session, get_session_url
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, create_model

from everyrow_mcp import redis_store
from everyrow_mcp.app import _clear_task_state, mcp
from everyrow_mcp.config import settings
from everyrow_mcp.models import (
    AgentInput,
    DedupeInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ResultsInput,
    ScreenInput,
    SingleAgentInput,
    _schema_to_model,
)
from everyrow_mcp.result_store import try_cached_result, try_store_result
from everyrow_mcp.tool_helpers import (
    EveryRowContext,
    TaskNotReady,
    TaskState,
    _fetch_task_result,
    _get_client,
    create_tool_response,
    write_initial_task_state,
)
from everyrow_mcp.utils import load_input, save_result_to_csv


async def _write_results_to_sheet(
    df: Any, title: str, preview_size: int = 5
) -> list[TextContent]:
    """Create a new Google Sheet and write the full DataFrame there.

    Raises if a spreadsheet with the same title already exists.
    Returns human-readable text with a link to the new sheet.
    """
    import pandas as pd  # noqa: PLC0415

    from everyrow_mcp.sheets_client import (  # noqa: PLC0415
        GoogleSheetsClient,
        get_google_token,
        records_to_values,
    )

    token = await get_google_token()
    async with GoogleSheetsClient(token) as client:
        # Guard: check for existing sheets with the same title
        existing = await client.list_spreadsheets(query=title, max_results=5)
        for f in existing:
            if f.get("name") == title:
                raise ValueError(
                    f"A spreadsheet named '{title}' already exists "
                    f"(id: {f['id']}). Pick a different title to avoid "
                    f"overwriting existing data."
                )

        # Create and populate
        metadata = await client.create_spreadsheet(title)
        spreadsheet_id = metadata["spreadsheetId"]
        url = metadata.get(
            "spreadsheetUrl",
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        )

        records = df.where(pd.notna(df), None).to_dict(orient="records")
        values = records_to_values(records)
        await client.write_range(spreadsheet_id, "Sheet1", values)

    total = len(df)
    preview = (
        df.head(preview_size)
        .where(pd.notna(df.head(preview_size)), None)
        .to_dict(orient="records")
    )
    summary = f"Created Google Sheet '{title}' with {total} rows.\nURL: {url}"

    widget_data: dict = {
        "preview": preview,
        "total": total,
        "spreadsheet_url": url,
    }

    return [
        TextContent(type="text", text=json.dumps(widget_data)),
        TextContent(type="text", text=summary),
    ]


@mcp.tool(
    name="everyrow_agent",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Run Web Research Agents",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_agent(params: AgentInput, ctx: EveryRowContext) -> list[TextContent]:
    """Run web research agents on each row of a CSV file.

    The dispatched agents will search the web, read pages, and return the
    requested research fields for each row. Agents run in parallel to save
    time and are optimized to find accurate answers at minimum cost.

    Examples:
    - "Find this company's latest funding round and lead investors"
    - "Research the CEO's background and previous companies"
    - "Find pricing information for this product"

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.
    """
    client = _get_client(ctx)

    _clear_task_state()
    df = await load_input(
        input_csv=params.input_csv,
        input_data=params.input_data,
        input_json=params.input_json,
        input_url=params.input_url,
    )

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("AgentResult", params.response_schema)

    async with create_session(client=client) as session:
        session_url = session.get_url()
        kwargs: dict[str, Any] = {"task": params.task, "session": session, "input": df}
        if response_model:
            kwargs["response_model"] = response_model
        cohort_task = await agent_map_async(**kwargs)
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.AGENT,
            session_url=session_url,
            total=len(df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(df)} agents starting.",
        token=client.token,
        total=len(df),
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_single_agent",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Run a Single Research Agent",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_single_agent(
    params: SingleAgentInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Run a single web research agent on a task, optionally with context data.

    Unlike everyrow_agent (which processes many CSV rows), this dispatches ONE agent
    to research a single question. The agent can search the web, read pages, and
    return structured results.

    Examples:
    - "Find the current CEO of Apple and their background"
    - "Research the latest funding round for this company" (with input_data: {"company": "Stripe"})
    - "What are the pricing tiers for this product?" (with input_data: {"product": "Snowflake"})

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.
    """
    client = _get_client(ctx)

    _clear_task_state()

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("SingleAgentResult", params.response_schema)

    # Convert input_data dict to a BaseModel if provided
    input_model: BaseModel | None = None
    if params.input_data:
        fields: dict[str, Any] = {k: (type(v), v) for k, v in params.input_data.items()}
        DynamicInput = create_model("DynamicInput", **fields)  # pyright: ignore[reportArgumentType, reportCallIssue]
        input_model = DynamicInput()

    async with create_session(client=client) as session:
        session_url = session.get_url()
        kwargs: dict[str, Any] = {"task": params.task, "session": session}
        if input_model is not None:
            kwargs["input"] = input_model
        if response_model is not None:
            kwargs["response_model"] = response_model
        cohort_task = await single_agent_async(**kwargs)
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.AGENT,
            session_url=session_url,
            total=1,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label="Submitted: single agent starting.",
        token=client.token,
        total=1,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_rank",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Score and Rank Rows",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_rank(params: RankInput, ctx: EveryRowContext) -> list[TextContent]:
    """Score and sort rows in a CSV file based on any criteria.

    Dispatches web agents to research the criteria to rank the entities in the
    table. Conducts research, and can also apply judgment to the results if the
    criteria are qualitative.

    Examples:
    - "Score this lead from 0 to 10 by likelihood to need data integration solutions"
    - "Score this company out of 100 by AI/ML adoption maturity"
    - "Score this candidate by fit for a senior engineering role, with 100 being the best"

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.

    Args:
        params: RankInput

    Returns:
        Success message containing session_url (for the user to open) and
        task_id (for monitoring progress)
    """
    client = _get_client(ctx)

    _clear_task_state()
    df = await load_input(
        input_csv=params.input_csv,
        input_data=params.input_data,
        input_json=params.input_json,
        input_url=params.input_url,
    )

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("RankResult", params.response_schema)

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await rank_async(
            task=params.task,
            session=session,
            input=df,
            field_name=params.field_name,
            field_type=params.field_type,
            response_model=response_model,
            ascending_order=params.ascending_order,
        )
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.RANK,
            session_url=session_url,
            total=len(df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(df)} rows for ranking.",
        token=client.token,
        total=len(df),
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_screen",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Filter Rows by Criteria",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_screen(
    params: ScreenInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Filter rows in a CSV file based on any criteria.

    Dispatches web agents to research the criteria to filter the entities in the
    table. Conducts research, and can also apply judgment to the results if the
    criteria are qualitative.

    Screen produces a boolean pass/fail verdict per row. If you provide a custom
    response_schema, it MUST include at least one boolean property (e.g.
    ``{"passes": {"type": "boolean"}}``). If the screening criteria need more than
    a yes/no answer (e.g. a three-way classification), use everyrow_agent instead.

    Examples:
    - "Is this job posting remote-friendly AND senior-level AND salary disclosed?"
    - "Is this vendor financially stable AND does it have good security practices?"
    - "Is this lead likely to need our product based on company description?"

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.

    Args:
        params: ScreenInput

    Returns:
        Success message containing session_url (for the user to open) and
        task_id (for monitoring progress)
    """
    client = _get_client(ctx)

    _clear_task_state()
    df = await load_input(
        input_csv=params.input_csv,
        input_data=params.input_data,
        input_json=params.input_json,
        input_url=params.input_url,
    )

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("ScreenResult", params.response_schema)

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await screen_async(
            task=params.task,
            session=session,
            input=df,
            response_model=response_model,
        )
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.SCREEN,
            session_url=session_url,
            total=len(df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(df)} rows for screening.",
        token=client.token,
        total=len(df),
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_dedupe",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Deduplicate Rows",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_dedupe(
    params: DedupeInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Remove duplicate rows from a CSV file using semantic equivalence.

    Dedupe identifies rows that represent the same entity even when they
    don't match exactly. The duplicate criterion is semantic and LLM-powered:
    agents reason over the data and, when needed, search the web for external
    information to establish equivalence.

    Examples:
    - Dedupe contacts: "Same person even with name abbreviations or career changes"
    - Dedupe companies: "Same company including subsidiaries and name variations"
    - Dedupe research papers: "Same work including preprints and published versions"

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.

    Args:
        params: DedupeInput

    Returns:
        Success message containing session_url (for the user to open) and
        task_id (for monitoring progress)
    """
    client = _get_client(ctx)
    _clear_task_state()

    df = await load_input(
        input_csv=params.input_csv,
        input_data=params.input_data,
        input_json=params.input_json,
        input_url=params.input_url,
    )

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await dedupe_async(
            equivalence_relation=params.equivalence_relation,
            session=session,
            input=df,
        )
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.DEDUPE,
            session_url=session_url,
            total=len(df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(df)} rows for deduplication.",
        token=client.token,
        total=len(df),
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_merge",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Merge Two Tables",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_merge(params: MergeInput, ctx: EveryRowContext) -> list[TextContent]:
    """Join two CSV files using intelligent entity matching.

    Merge combines two tables even when keys don't match exactly. Uses LLM web
    research and judgment to identify which rows from the first table should
    join those in the second.

    left_csv = the table being enriched (ALL its rows appear in the output).
    right_csv = the lookup/reference table (its columns are appended to matches).

    IMPORTANT defaults — omit parameters when unsure:
    - merge_on_left/merge_on_right: only set if you expect exact string matches on
      the chosen columns or want to draw agent attention to them. Fine to omit.
    - relationship_type: defaults to many_to_one, which is correct in most cases.
      Only set one_to_one when both tables have unique entities of the same kind.

    Examples:
    - Match software products (left, enriched) to parent companies (right, lookup):
      Photoshop -> Adobe. relationship_type: many_to_one (many products per company).
    - Match clinical trial sponsors (left) to pharma companies (right):
      Genentech -> Roche. relationship_type: many_to_one.
    - Join two contact lists with different name formats:
      relationship_type: one_to_one (each person appears once in each list).

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.

    Args:
        params: MergeInput

    Returns:
        Success message containing session_url (for the user to open) and
        task_id (for monitoring progress)
    """
    client = _get_client(ctx)
    _clear_task_state()

    left_df = await load_input(
        input_csv=params.left_csv,
        input_data=params.left_input_data,
        input_json=params.left_input_json,
        input_url=params.left_url,
    )

    right_df = await load_input(
        input_csv=params.right_csv,
        input_data=params.right_input_data,
        input_json=params.right_input_json,
        input_url=params.right_url,
    )

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await merge_async(
            task=params.task,
            session=session,
            left_table=left_df,
            right_table=right_df,
            merge_on_left=params.merge_on_left,
            merge_on_right=params.merge_on_right,
            use_web_search=params.use_web_search,
            relationship_type=params.relationship_type,
        )
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.MERGE,
            session_url=session_url,
            total=len(left_df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(left_df)} left rows for merging.",
        token=client.token,
        total=len(left_df),
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
    )


@mcp.tool(
    name="everyrow_progress",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Check Task Progress",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
# NOTE: This docstring is overridden at startup by set_tool_descriptions().
async def everyrow_progress(
    params: ProgressInput,
    ctx: EveryRowContext,
) -> list[TextContent]:
    """Check progress of a running task. Blocks for a time to limit the polling rate.

    After receiving a status update, immediately call everyrow_progress again
    unless the task is completed or failed. The tool handles pacing internally.
    Do not add commentary between progress calls, just call again immediately.
    """
    client = _get_client(ctx)

    task_id = params.task_id

    # Block server-side before polling — controls the cadence
    await asyncio.sleep(redis_store.PROGRESS_POLL_DELAY)

    try:
        status_response = handle_response(
            await get_task_status_tasks_task_id_status_get.asyncio(
                task_id=UUID(task_id),
                client=client,
            )
        )
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
                    Error polling task: {e!r}
                    Retry: call everyrow_progress(task_id='{task_id}')."""),
            )
        ]

    ts = TaskState(status_response)
    ts.write_file(task_id)

    return [TextContent(type="text", text=ts.progress_message(task_id))]


@mcp.tool(
    name="everyrow_results",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Save Task Results",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta={"ui": {"resourceUri": "ui://everyrow/results.html"}},
)
# NOTE: This docstring is overridden at startup by set_tool_descriptions().
async def everyrow_results(  # noqa: PLR0911
    params: ResultsInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Retrieve results from a completed everyrow task and save them to a CSV.

    Only call this after everyrow_progress reports status 'completed'.

    Optionally pass output_spreadsheet_title to create a new Google Sheet with
    the full results. This always creates a new sheet — it refuses to overwrite
    an existing sheet with the same title.
    """
    client = _get_client(ctx)
    task_id = params.task_id
    mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url

    # ── HTTP mode: return from cache if available ───────────────
    if settings.is_http:
        cached = await try_cached_result(
            task_id, params.offset, params.page_size, mcp_server_url=mcp_server_url
        )
        if cached is not None:
            return cached

    # ── Fetch from API ────────────────────────────────────────────
    try:
        df, session_id = await _fetch_task_result(client, task_id)
        session_url = get_session_url(session_id) if session_id else ""
    except TaskNotReady as e:
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
                    Task status is {e.status}. Cannot fetch results yet.
                    Call everyrow_progress(task_id='{task_id}') to check again."""),
            )
        ]
    except Exception as e:
        return [TextContent(type="text", text=f"Error retrieving results: {e!r}")]

    # ── Google Sheets output (both modes) ────────────────────────
    if params.output_spreadsheet_title:
        try:
            return await _write_results_to_sheet(df, params.output_spreadsheet_title)
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Failed to write results to Google Sheet: {e!r}",
                )
            ]

    # ── stdio mode: save to file ──────────────────────────────────
    if settings.is_stdio:
        if params.output_path:
            output_file = Path(params.output_path)
            save_result_to_csv(df, output_file)
            return [
                TextContent(
                    type="text",
                    text=dedent(f"""\
                        Saved {len(df)} rows to {output_file}

                        Tip: For multi-step pipelines or custom response models, \
                        use the everyrow Python SDK directly."""),
                )
            ]
        return [
            TextContent(
                type="text",
                text=f"Results ready: {len(df)} rows. Provide output_path to save to CSV.",
            )
        ]

    # ── HTTP mode: store in Redis and return paginated response ──
    store_response = await try_store_result(
        task_id,
        df,
        params.offset,
        params.page_size,
        session_url,
        mcp_server_url=mcp_server_url,
    )
    if store_response is not None:
        return store_response

    return [
        TextContent(
            type="text",
            text=f"Error: failed to store results for task {task_id}.",
        )
    ]

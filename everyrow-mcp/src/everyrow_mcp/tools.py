"""MCP tool functions for the everyrow MCP server."""

import asyncio
import json
import logging
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import UUID

from everyrow.api_utils import handle_response
from everyrow.constants import EveryrowError
from everyrow.generated.api.tasks import get_task_status_tasks_task_id_status_get
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.ops import (
    agent_map_async,
    dedupe_async,
    forecast_async,
    merge_async,
    rank_async,
    screen_async,
    single_agent_async,
)
from everyrow.session import create_session, get_session_url
from everyrow.task import cancel_task
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, create_model

from everyrow_mcp import redis_store
from everyrow_mcp.app import _clear_task_state, mcp
from everyrow_mcp.models import (
    AgentInput,
    CancelInput,
    DedupeInput,
    ForecastInput,
    HttpResultsInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ScreenInput,
    SingleAgentInput,
    StdioResultsInput,
    _schema_to_model,
)
from everyrow_mcp.result_store import (
    _sanitize_records,
    try_cached_result,
    try_store_result,
)
from everyrow_mcp.tool_helpers import (
    EveryRowContext,
    TaskNotReady,
    TaskState,
    _fetch_task_result,
    _get_client,
    create_tool_response,
    write_initial_task_state,
)
from everyrow_mcp.utils import load_data, save_result_to_csv

logger = logging.getLogger(__name__)


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
    df = await load_data(data=params.data, input_csv=params.input_csv)

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
    df = await load_data(data=params.data, input_csv=params.input_csv)

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
    df = await load_data(data=params.data, input_csv=params.input_csv)

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

    df = await load_data(data=params.data, input_csv=params.input_csv)

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

    left_df = await load_data(data=params.left_data, input_csv=params.left_csv)
    right_df = await load_data(data=params.right_data, input_csv=params.right_csv)

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
    name="everyrow_forecast",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Probability Forecast",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def everyrow_forecast(
    params: ForecastInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Forecast the probability of binary questions from a CSV file.

    Each row is forecast using an approach validated against FutureSearch's
    past-casting environment of 1500 hard forecasting questions and 15M research
    documents, see more at https://futuresearch.ai/automating-forecasting-questions/
    and https://arxiv.org/abs/2506.21558.

    The CSV should contain at minimum a ``question`` column.  Recommended additional
    columns: ``resolution_criteria``, ``resolution_date``, ``background``.  All
    columns are passed to the research agents and forecasters.

    The optional ``context`` parameter provides batch-level instructions that apply
    to every row (e.g. "Focus on EU regulatory sources").  Leave it empty when the
    rows are self-contained.

    Output columns added: ``rationale`` (str) and ``probability`` (int, 0-100).

    This function submits the task and returns immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.
    """
    client = _get_client(ctx)

    _clear_task_state()
    df = await load_data(data=params.data, input_csv=params.input_csv)

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await forecast_async(
            task=params.context or "",
            session=session,
            input=df,
        )
        task_id = str(cohort_task.task_id)
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.FORECAST,
            session_url=session_url,
            total=len(df),
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {len(df)} rows for forecasting (6 research dimensions + dual forecaster per row).",
        token=client.token,
        total=len(df),
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
async def everyrow_progress(
    params: ProgressInput,
    ctx: EveryRowContext,
) -> list[TextContent]:
    """Check progress of a running task. Blocks briefly to limit the polling rate.

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
    except Exception:
        logger.exception("Failed to poll task %s", task_id)
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
                    Error polling task {task_id}. Please try again.
                    Retry: call everyrow_progress(task_id='{task_id}')."""),
            )
        ]

    ts = TaskState(status_response)
    ts.write_file(task_id)

    return [TextContent(type="text", text=ts.progress_message(task_id))]


async def everyrow_results_stdio(
    params: StdioResultsInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Retrieve results from a completed everyrow task and save them to a CSV.

    Only call this after everyrow_progress reports status 'completed'.
    Pass output_path (ending in .csv) to save results as a local CSV file.
    """
    client = _get_client(ctx)
    task_id = params.task_id

    try:
        df, _session_id = await _fetch_task_result(client, task_id)
    except TaskNotReady as e:
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
                    Task status is {e.status}. Cannot fetch results yet.
                    Call everyrow_progress(task_id='{task_id}') to check again."""),
            )
        ]
    except Exception:
        logger.exception("Failed to retrieve results for task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Error retrieving results for task {task_id}. Please try again.",
            )
        ]

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


async def everyrow_results_http(
    params: HttpResultsInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Retrieve results from a completed everyrow task.

    Only call this after everyrow_progress reports status 'completed'.
    Results are returned as a paginated preview with a download link.
    """
    client = _get_client(ctx)
    task_id = params.task_id
    mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url

    # ── Return from cache if available ───────────────────────────
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
    except Exception:
        logger.exception("Failed to retrieve results for task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Error retrieving results for task {task_id}. Please try again.",
            )
        ]

    # output_path is accepted by the schema but ignored in HTTP mode —
    # the server must not write to its own filesystem on remote request.

    # ── Store in Redis and return paginated response ──────────────
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

    # ── Fallback: return inline preview when Redis is unavailable ──
    page_df = df.iloc[params.offset : params.offset + params.page_size]
    preview = _sanitize_records(page_df.to_dict(orient="records"))
    cols = ", ".join(df.columns)
    return [
        TextContent(
            type="text",
            text=json.dumps({"preview": preview, "total": len(df)}),
        ),
        TextContent(
            type="text",
            text=f"Results: {len(df)} rows, {len(df.columns)} columns ({cols}). "
            f"Showing {len(page_df)} rows inline (Redis unavailable, no download link).",
        ),
    ]


@mcp.tool(
    name="everyrow_cancel",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Cancel a Running Task",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def everyrow_cancel(
    params: CancelInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Cancel a running everyrow task. Use when the user wants to stop a task that is currently processing."""
    client = _get_client(ctx)

    task_id = params.task_id
    try:
        await cancel_task(task_id=UUID(task_id), client=client)
        _clear_task_state()
        return [
            TextContent(
                type="text",
                text=f"Cancelled task {task_id}.",
            )
        ]
    except EveryrowError:
        logger.exception("Failed to cancel task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Failed to cancel task {task_id}. The task may have already completed.",
            )
        ]
    except Exception:
        logger.exception("Failed to cancel task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Error cancelling task {task_id}. Please try again.",
            )
        ]


# Default registration: stdio variant. server.main() re-registers the HTTP
# variant when --http is used.  This ensures list_tools() always finds the
# tool, even in test modules that import tools.py without calling main().
_RESULTS_ANNOTATIONS = ToolAnnotations(
    title="Save Task Results",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_RESULTS_META = {"ui": {"resourceUri": "ui://everyrow/results.html"}}

mcp.tool(
    name="everyrow_results",
    structured_output=False,
    annotations=_RESULTS_ANNOTATIONS,
    meta=_RESULTS_META,
)(everyrow_results_stdio)

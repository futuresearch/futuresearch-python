"""MCP tool functions for the everyrow MCP server."""

import asyncio
import json
import logging
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import UUID

import pandas as pd
from everyrow.api_utils import handle_response
from everyrow.built_in_lists import list_built_in_datasets, use_built_in_list
from everyrow.constants import EveryrowError
from everyrow.generated.api.billing import get_billing_balance_billing_get
from everyrow.generated.api.tasks import get_task_status_tasks_task_id_status_get
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.ops import (
    agent_map_async,
    create_table_artifact,
    dedupe_async,
    forecast_async,
    merge_async,
    rank_async,
    screen_async,
    single_agent_async,
)
from everyrow.session import create_session, get_session_url, list_sessions
from everyrow.task import cancel_task
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, create_model

from everyrow_mcp import redis_store
from everyrow_mcp.app import _clear_task_state, mcp
from everyrow_mcp.config import settings
from everyrow_mcp.models import (
    AgentInput,
    BrowseListsInput,
    CancelInput,
    DedupeInput,
    ForecastInput,
    HttpResultsInput,
    ListSessionsInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ScreenInput,
    SingleAgentInput,
    StdioResultsInput,
    UploadDataInput,
    UseListInput,
    _schema_to_model,
)
from everyrow_mcp.result_store import (
    try_cached_result,
    try_store_result,
)
from everyrow_mcp.tool_helpers import (
    EveryRowContext,
    TaskNotReady,
    TaskState,
    _fetch_task_result,
    _get_client,
    client_supports_widgets,
    create_tool_response,
    is_internal_client,
    log_client_info,
    write_initial_task_state,
)
from everyrow_mcp.utils import fetch_csv_from_url, is_url, save_result_to_csv

logger = logging.getLogger(__name__)


async def _check_task_ownership(task_id: str) -> list[TextContent] | None:
    """Verify the current user owns *task_id*. Returns an error response if
    access should be denied, or ``None`` if the caller may proceed.

    Only active in HTTP mode; always returns ``None`` for stdio.
    Fail-closed: if ownership cannot be verified, access is denied.
    """
    if not settings.is_http:
        return None

    owner = await redis_store.get_task_owner(task_id)
    if not owner:
        logger.error("No owner recorded for task %s — denying access", task_id)
        return [
            TextContent(
                type="text",
                text="Access denied: task ownership could not be verified.",
            )
        ]

    access_token = get_access_token()
    user_id = access_token.client_id if access_token else None
    if not user_id or user_id != owner:
        return [
            TextContent(
                type="text",
                text="Access denied: this task belongs to another user.",
            )
        ]
    return None


@mcp.tool(
    name="everyrow_browse_lists",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Browse Reference Lists",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def everyrow_browse_lists(
    params: BrowseListsInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Browse available reference lists of well-known entities.

    Includes company lists (S&P 500, FTSE 100, Russell 3000, sector breakdowns
    like Global Banks or Semiconductor companies), geographic lists (all countries,
    EU members, US states, major cities), people (billionaires, heads of state,
    AI leaders), institutions (top universities, regulators), and infrastructure
    (airports, ports, power stations).

    Use this when the user's analysis involves a well-known group that we might
    already have a list for. Returns names, fields, and artifact_ids to pass to
    everyrow_use_list.

    Call with no parameters to see all available lists, or use search/category
    to narrow results.
    """
    client = _get_client(ctx)

    try:
        results = await list_built_in_datasets(
            client, search=params.search, category=params.category
        )
    except Exception as e:
        return [TextContent(type="text", text=f"Error browsing built-in lists: {e!r}")]

    if not results:
        search_desc = f" matching '{params.search}'" if params.search else ""
        cat_desc = f" in category '{params.category}'" if params.category else ""
        return [
            TextContent(
                type="text",
                text=f"No built-in lists found{search_desc}{cat_desc}.",
            )
        ]

    lines = [f"Found {len(results)} built-in list(s):\n"]
    for i, item in enumerate(results, 1):
        fields_str = ", ".join(item.fields) if item.fields else "(no fields listed)"
        lines.append(
            f"{i}. {item.name} [{item.category}]\n"
            f"   Fields: {fields_str}\n"
            f"   artifact_id: {item.artifact_id}\n"
        )
    lines.append(
        "To use one of these lists, call everyrow_use_list with the artifact_id."
    )

    return [TextContent(type="text", text="\n".join(lines))]


@mcp.tool(
    name="everyrow_use_list",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Import Reference List",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def everyrow_use_list(
    params: UseListInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Import a reference list into your session and save it as a CSV file.

    This copies the dataset into a new session, fetches the data, and saves
    it as a CSV file ready to pass to other everyrow utilities for analysis
    or research.

    The copy is a fast database operation (<1s) — no polling needed.
    """
    client = _get_client(ctx)

    try:
        async with create_session(client=client) as session:
            session_url = session.get_url()
            result = await use_built_in_list(
                artifact_id=UUID(params.artifact_id),
                session=session,
            )

            # Fetch the copied data and save as CSV
            df, _ = await _fetch_task_result(client, str(result.task_id))

            csv_path = Path.cwd() / f"built-in-list-{result.artifact_id}.csv"
            df.to_csv(csv_path, index=False)
    except Exception as e:
        return [TextContent(type="text", text=f"Error importing built-in list: {e!r}")]

    return [
        TextContent(
            type="text",
            text=(
                f"Imported built-in list into your session.\n\n"
                f"CSV saved to: {csv_path}\n"
                f"Rows: {len(df)}\n"
                f"Columns: {', '.join(df.columns)}\n"
                f"Session: {session_url}\n\n"
                f"Pass {csv_path} as input_csv to other everyrow utilities for analysis or research."
            ),
        )
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
    logger.info(
        "everyrow_agent: task=%.80s rows=%s",
        params.task,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "everyrow_agent")
    client = _get_client(ctx)

    _clear_task_state()
    input_data = params._aid_or_dataframe

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("AgentResult", params.response_schema)

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        kwargs: dict[str, Any] = {
            "task": params.task,
            "session": session,
            "input": input_data,
        }
        if response_model:
            kwargs["response_model"] = response_model
        cohort_task = await agent_map_async(**kwargs)
        task_id = str(cohort_task.task_id)
        total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.AGENT,
            session_url=session_url,
            total=total,
            input_source=params._input_data_mode.value,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} agents starting."
        if total
        else "Submitted: agents starting (artifact).",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info("everyrow_single_agent: task=%.80s", params.task)
    log_client_info(ctx, "everyrow_single_agent")
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

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
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
            input_source="single_agent",
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label="Submitted: single agent starting.",
        token=client.token,
        total=1,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info(
        "everyrow_rank: task=%.80s rows=%s",
        params.task,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "everyrow_rank")
    client = _get_client(ctx)

    _clear_task_state()
    input_data = params._aid_or_dataframe

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("RankResult", params.response_schema)

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        cohort_task = await rank_async(
            task=params.task,
            session=session,
            input=input_data,
            field_name=params.field_name,
            field_type=params.field_type,
            response_model=response_model,
            ascending_order=params.ascending_order,
        )
        task_id = str(cohort_task.task_id)
        total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.RANK,
            session_url=session_url,
            total=total,
            input_source=params._input_data_mode.value,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} rows for ranking."
        if total
        else "Submitted: artifact for ranking.",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info(
        "everyrow_screen: task=%.80s rows=%s",
        params.task,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "everyrow_screen")
    client = _get_client(ctx)

    _clear_task_state()
    input_data = params._aid_or_dataframe

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("ScreenResult", params.response_schema)

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        cohort_task = await screen_async(
            task=params.task,
            session=session,
            input=input_data,
            response_model=response_model,
        )
        task_id = str(cohort_task.task_id)
        total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.SCREEN,
            session_url=session_url,
            total=total,
            input_source=params._input_data_mode.value,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} rows for screening."
        if total
        else "Submitted: artifact for screening.",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info(
        "everyrow_dedupe: equivalence=%.80s rows=%s",
        params.equivalence_relation,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "everyrow_dedupe")
    client = _get_client(ctx)
    _clear_task_state()

    input_data = params._aid_or_dataframe

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        cohort_task = await dedupe_async(
            equivalence_relation=params.equivalence_relation,
            session=session,
            input=input_data,
        )
        task_id = str(cohort_task.task_id)
        total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.DEDUPE,
            session_url=session_url,
            total=total,
            input_source=params._input_data_mode.value,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} rows for deduplication."
        if total
        else "Submitted: artifact for deduplication.",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info(
        "everyrow_merge: task=%.80s left_rows=%s right_rows=%s",
        params.task,
        len(params.left_data) if params.left_data else "artifact",
        len(params.right_data) if params.right_data else "artifact",
    )
    log_client_info(ctx, "everyrow_merge")
    client = _get_client(ctx)
    _clear_task_state()

    left_input = params._left_aid_or_dataframe
    right_input = params._right_aid_or_dataframe

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        cohort_task = await merge_async(
            task=params.task,
            session=session,
            left_table=left_input,
            right_table=right_input,
            merge_on_left=params.merge_on_left,
            merge_on_right=params.merge_on_right,
            use_web_search=params.use_web_search,
            relationship_type=params.relationship_type,
        )
        task_id = str(cohort_task.task_id)
        total = len(left_input) if isinstance(left_input, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.MERGE,
            session_url=session_url,
            total=total,
            input_source=f"left={params._left_input_data_mode.value}, right={params._right_input_data_mode.value}",
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} left rows for merging."
        if total
        else "Submitted: artifacts for merging.",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
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
    logger.info(
        "everyrow_forecast: context=%.80s rows=%s",
        params.context or "",
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "everyrow_forecast")
    client = _get_client(ctx)

    _clear_task_state()
    input_data = params._aid_or_dataframe

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_url = session.get_url()
        session_id_str = str(session.session_id)
        cohort_task = await forecast_async(
            task=params.context or "",
            session=session,
            input=input_data,
        )
        task_id = str(cohort_task.task_id)
        total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0
        write_initial_task_state(
            task_id,
            task_type=PublicTaskType.FORECAST,
            session_url=session_url,
            total=total,
            input_source=params._input_data_mode.value,
        )

    return await create_tool_response(
        task_id=task_id,
        session_url=session_url,
        label=f"Submitted: {total} rows for forecasting (6 research dimensions + dual forecaster per row)."
        if total
        else "Submitted: artifact for forecasting.",
        token=client.token,
        total=total,
        mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
        session_id=session_id_str,
    )


@mcp.tool(
    name="everyrow_upload_data",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Upload Data",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def everyrow_upload_data(
    params: UploadDataInput, ctx: EveryRowContext
) -> list[TextContent]:
    """Upload data from a URL or local file. Returns an artifact_id for use in processing tools.

    Use this tool to ingest data before calling everyrow_agent, everyrow_screen,
    everyrow_rank, everyrow_dedupe, everyrow_merge, or everyrow_forecast.

    Supported sources:
    - HTTP(S) URLs (including Google Sheets — auto-converted to CSV export)
    - Local CSV file paths (stdio/local mode only — not available over HTTP)

    For local files over HTTP, use everyrow_request_upload_url instead:
    1. Call everyrow_request_upload_url with the filename
    2. Execute the returned curl command to upload the file
    3. Use the artifact_id from the curl response in your processing tool

    Returns an artifact_id (UUID) that can be passed to any processing tool's
    artifact_id parameter. The data is stored server-side and can be reused
    across multiple tool calls.
    """
    logger.info("everyrow_upload_data: source=%.80s", params.source)
    log_client_info(ctx, "everyrow_upload_data")
    client = _get_client(ctx)

    if is_url(params.source):
        df = await fetch_csv_from_url(params.source)
    else:
        df = pd.read_csv(params.source)
        if df.empty:
            raise ValueError(f"CSV file is empty: {params.source}")

    async with create_session(
        client=client, session_id=params.session_id, name=params.session_name
    ) as session:
        session_id_str = str(session.session_id)
        artifact_id = await create_table_artifact(df, session)

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "artifact_id": str(artifact_id),
                    "session_id": session_id_str,
                    "rows": len(df),
                    "columns": list(df.columns),
                }
            ),
        )
    ]


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

    # ── Cross-user access check ──────────────────────────────────
    try:
        if denied := await _check_task_ownership(task_id):
            return denied
    except Exception:
        logger.exception("Could not verify task ownership for %s", task_id)
        return [
            TextContent(
                type="text",
                text="Unable to verify task ownership. Please try again.",
            )
        ]

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
    The user always has access to all rows via the widget — page_size only
    controls how many rows _you_ can read.
    After results load, tell the user how many rows you can see vs the total.
    """
    client = _get_client(ctx)
    task_id = params.task_id
    mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url
    log_client_info(ctx, "everyrow_results")
    skip_widget = not client_supports_widgets(ctx)
    skip_session = False
    if is_internal_client():
        skip_widget = True
        skip_session = True

    # ── Cross-user access check ──────────────────────────────────
    try:
        if denied := await _check_task_ownership(task_id):
            return denied
    except Exception:
        logger.exception("Could not verify task ownership for %s", task_id)
        return [
            TextContent(
                type="text",
                text="Unable to verify task ownership. Please try again.",
            )
        ]

    # ── Return from cache if available ───────────────────────────
    cached = await try_cached_result(
        task_id,
        params.offset,
        params.page_size,
        mcp_server_url=mcp_server_url,
        skip_widget=skip_widget,
        skip_session=skip_session,
    )
    if cached is not None:
        return cached

    # ── Fetch from API ────────────────────────────────────────────
    try:
        df, session_id = await _fetch_task_result(client, task_id)
        session_url = get_session_url(UUID(session_id)) if session_id else ""
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

    # ── Store in Redis and return response ──────────────────────
    return await try_store_result(
        task_id,
        df,
        params.offset,
        params.page_size,
        session_url,
        mcp_server_url=mcp_server_url,
        skip_widget=skip_widget,
        skip_session=skip_session,
    )


@mcp.tool(
    name="everyrow_list_sessions",
    structured_output=False,
    annotations=ToolAnnotations(
        title="List Sessions",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def everyrow_list_sessions(
    params: ListSessionsInput, ctx: EveryRowContext
) -> list[TextContent]:
    """List everyrow sessions owned by the authenticated user (paginated).

    Returns session names, IDs, timestamps, and dashboard URLs.
    Use this to find past sessions or check what's been run.
    Results are paginated — 25 sessions per page by default.
    """
    log_client_info(ctx, "everyrow_list_sessions")
    client = _get_client(ctx)

    try:
        result = await list_sessions(
            client=client, offset=params.offset, limit=params.limit
        )
    except Exception as e:
        return [TextContent(type="text", text=f"Error listing sessions: {e!r}")]

    if not result.sessions:
        if result.total > 0:
            return [
                TextContent(
                    type="text",
                    text=f"No sessions on this page (offset={params.offset}). "
                    f"Total sessions: {result.total}.",
                )
            ]
        return [TextContent(type="text", text="No sessions found.")]

    start = result.offset + 1
    end = result.offset + len(result.sessions)
    total_pages = (result.total + result.limit - 1) // result.limit
    current_page = (result.offset // result.limit) + 1

    lines = [f"Found {result.total} session(s) (showing {start}-{end}):\n"]
    for s in result.sessions:
        lines.append(
            f"- **{s.name}** (id: {s.session_id})\n"
            f"  Created: {s.created_at:%Y-%m-%d %H:%M UTC} | "
            f"Updated: {s.updated_at:%Y-%m-%d %H:%M UTC}\n"
            f"  URL: {s.get_url()}"
        )

    has_more = (result.offset + result.limit) < result.total
    lines.append(
        f"\nPage {current_page} of {total_pages}"
        + (
            f" | Use offset={result.offset + result.limit} to see next page"
            if has_more
            else ""
        )
    )

    return [TextContent(type="text", text="\n".join(lines))]


@mcp.tool(
    name="everyrow_balance",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Check Account Balance",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def everyrow_balance(ctx: EveryRowContext) -> list[TextContent]:
    """Check the current billing balance for the authenticated user.

    Returns the account balance in dollars. Use this to verify available
    credits before submitting tasks.
    """
    client = _get_client(ctx)

    try:
        response = await get_billing_balance_billing_get.asyncio(client=client)
        if response is None:
            raise RuntimeError("Failed to get billing balance")
    except Exception:
        logger.exception("Failed to get billing balance")
        return [
            TextContent(
                type="text",
                text="Error retrieving billing balance. Please try again.",
            )
        ]

    return [
        TextContent(
            type="text",
            text=f"Current balance: ${response.current_balance_dollars:.2f}",
        )
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
    log_client_info(ctx, "everyrow_cancel")
    client = _get_client(ctx)
    task_id = params.task_id

    # ── Cross-user access check ──────────────────────────────────
    try:
        if denied := await _check_task_ownership(task_id):
            return denied
    except Exception:
        logger.exception("Could not verify task ownership for %s", task_id)
        return [
            TextContent(
                type="text",
                text="Unable to verify task ownership. Please try again.",
            )
        ]

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

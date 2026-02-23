"""MCP tool implementations for everyrow operations."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from everyrow.api_utils import handle_response
from everyrow.generated.api.tasks import (
    get_task_result_tasks_task_id_result_get,
    get_task_status_tasks_task_id_status_get,
)
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_result_response_data_type_1 import (
    TaskResultResponseDataType1,
)
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.types import Unset
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

import everyrow_mcp.app as _app
from everyrow_mcp.app import (
    PROGRESS_POLL_DELAY,
    _clear_task_state,
    _write_task_state,
    mcp,
)
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
from everyrow_mcp.utils import save_result_to_csv


def _get_client():
    """Get the singleton client, raising if not initialized."""
    if _app._client is None:
        raise RuntimeError("MCP server not initialized.")
    return _app._client


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
async def everyrow_agent(params: AgentInput) -> list[TextContent]:
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
    client = _get_client()

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

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
        _write_task_state(
            task_id,
            task_type=PublicTaskType.AGENT,
            session_url=session_url,
            total=len(df),
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: {len(df)} agents starting.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
async def everyrow_single_agent(params: SingleAgentInput) -> list[TextContent]:
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
    client = _get_client()

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
        _write_task_state(
            task_id,
            task_type=PublicTaskType.AGENT,
            session_url=session_url,
            total=1,
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: single agent starting.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
async def everyrow_rank(params: RankInput) -> list[TextContent]:
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
    client = _get_client()

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

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
        _write_task_state(
            task_id,
            task_type=PublicTaskType.RANK,
            session_url=session_url,
            total=len(df),
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: {len(df)} rows for ranking.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
async def everyrow_screen(params: ScreenInput) -> list[TextContent]:
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
    client = _get_client()

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

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
        _write_task_state(
            task_id,
            task_type=PublicTaskType.SCREEN,
            session_url=session_url,
            total=len(df),
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: {len(df)} rows for screening.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
async def everyrow_dedupe(params: DedupeInput) -> list[TextContent]:
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
    client = _get_client()

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

    async with create_session(client=client) as session:
        session_url = session.get_url()
        cohort_task = await dedupe_async(
            equivalence_relation=params.equivalence_relation,
            session=session,
            input=df,
        )
        task_id = str(cohort_task.task_id)
        _write_task_state(
            task_id,
            task_type=PublicTaskType.DEDUPE,
            session_url=session_url,
            total=len(df),
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: {len(df)} rows for deduplication.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
async def everyrow_merge(params: MergeInput) -> list[TextContent]:
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
    client = _get_client()

    _clear_task_state()
    left_df = pd.read_csv(params.left_csv)
    right_df = pd.read_csv(params.right_csv)

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
        _write_task_state(
            task_id,
            task_type=PublicTaskType.MERGE,
            session_url=session_url,
            total=len(left_df),
            completed=0,
            failed=0,
            running=0,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    return [
        TextContent(
            type="text",
            text=(
                f"Submitted: {len(left_df)} left rows for merging.\n"
                f"Session: {session_url}\n"
                f"Task ID: {task_id}\n\n"
                f"Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}')."
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
async def everyrow_progress(  # noqa: PLR0912
    params: ProgressInput,
) -> list[TextContent]:
    """Check progress of a running task. Blocks for a time to limit the polling rate.

    After receiving a status update, immediately call everyrow_progress again
    unless the task is completed or failed. The tool handles pacing internally.
    Do not add commentary between progress calls, just call again immediately.
    """
    client = _get_client()

    task_id = params.task_id

    # Block server-side before polling — controls the cadence
    await asyncio.sleep(PROGRESS_POLL_DELAY)

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
                text=f"Error polling task: {e!r}\nRetry: call everyrow_progress(task_id='{task_id}').",
            )
        ]

    status = status_response.status
    progress = status_response.progress
    is_terminal = status in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.REVOKED,
    )
    is_screen = status_response.task_type == PublicTaskType.SCREEN
    session_url = get_session_url(status_response.session_id)

    completed = progress.completed if progress else 0
    failed = progress.failed if progress else 0
    running = progress.running if progress else 0
    total = progress.total if progress else 0

    # Calculate elapsed time from API timestamps.
    # For terminal states, use updated_at - created_at (actual task duration).
    # For running/pending, use now - created_at (ongoing elapsed time).
    if status_response.created_at:
        created_at = status_response.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        started_at = created_at

        if is_terminal and status_response.updated_at:
            updated_at = status_response.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            elapsed_s = round((updated_at - created_at).total_seconds())
        else:
            now = datetime.now(UTC)
            elapsed_s = round((now - created_at).total_seconds())
    else:
        elapsed_s = 0
        started_at = datetime.now(UTC)

    _write_task_state(
        task_id,
        task_type=status_response.task_type,
        session_url=session_url,
        total=total,
        completed=completed,
        failed=failed,
        running=running,
        status=status,
        started_at=started_at,
    )

    if is_terminal:
        error = status_response.error
        if error and not isinstance(error, Unset):
            return [TextContent(type="text", text=f"Task {status.value}: {error}")]
        if status == TaskStatus.COMPLETED:
            if is_screen:
                completed_msg = f"Screening complete ({elapsed_s}s)."
            else:
                completed_msg = (
                    f"Completed: {completed}/{total} ({failed} failed) in {elapsed_s}s."
                )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"{completed_msg}\n"
                        f"Call everyrow_results(task_id='{task_id}', output_path='/path/to/output.csv') to save the output."
                    ),
                )
            ]
        return [
            TextContent(
                type="text", text=f"Task {status.value}. Report the error to the user."
            )
        ]

    if is_screen:
        return [
            TextContent(
                type="text",
                text=(
                    f"Screen running ({elapsed_s}s elapsed).\n"
                    f"Immediately call everyrow_progress(task_id='{task_id}')."
                ),
            )
        ]

    fail_part = f", {failed} failed" if failed else ""
    return [
        TextContent(
            type="text",
            text=(
                f"Running: {completed}/{total} complete, {running} running{fail_part} ({elapsed_s}s elapsed)\n"
                f"Immediately call everyrow_progress(task_id='{task_id}')."
            ),
        )
    ]


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
)
async def everyrow_results(params: ResultsInput) -> list[TextContent]:
    """Retrieve results from a completed everyrow task and save them to a CSV.

    Only call this after everyrow_progress reports status 'completed'.
    The output_path must be a full file path ending in .csv.
    """
    client = _get_client()

    task_id = params.task_id
    output_file = Path(params.output_path)

    try:
        status_response = handle_response(
            await get_task_status_tasks_task_id_status_get.asyncio(
                task_id=UUID(task_id),
                client=client,
            )
        )
        status = status_response.status
        if status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REVOKED):
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Task status is {status.value}. Cannot fetch results yet.\n"
                        f"Call everyrow_progress(task_id='{task_id}') to check again."
                    ),
                )
            ]
    except Exception as e:
        return [TextContent(type="text", text=f"Error checking task status: {e!r}")]

    try:
        result_response = handle_response(
            await get_task_result_tasks_task_id_result_get.asyncio(
                task_id=UUID(task_id),
                client=client,
            )
        )

        if isinstance(result_response.data, list):
            records = [item.additional_properties for item in result_response.data]
            df = pd.DataFrame(records)
        elif isinstance(result_response.data, TaskResultResponseDataType1):
            df = pd.DataFrame([result_response.data.additional_properties])
        else:
            return [
                TextContent(type="text", text="Error: Task result has no table data.")
            ]

        save_result_to_csv(df, output_file)
        # Task state file deleted by PostToolUse hook (everyrow-track-results.sh)

        return [
            TextContent(
                type="text",
                text=(
                    f"Saved {len(df)} rows to {output_file}\n\n"
                    "Tip: For multi-step pipelines, custom response models, or preview mode, "
                    "ask your AI assistant to write Python using the everyrow SDK."
                ),
            )
        ]

    except Exception as e:
        return [TextContent(type="text", text=f"Error retrieving results: {e!r}")]

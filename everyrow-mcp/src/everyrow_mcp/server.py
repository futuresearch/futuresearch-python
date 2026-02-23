"""MCP server for everyrow SDK operations."""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
import pandas as pd
from everyrow.api_utils import create_client, handle_response
from everyrow.generated.api.billing.get_billing_balance_billing_get import (
    asyncio as get_billing,
)
from everyrow.generated.api.tasks import (
    get_task_result_tasks_task_id_result_get,
    get_task_status_tasks_task_id_status_get,
)
from everyrow.generated.client import AuthenticatedClient
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.types import Unset
from everyrow.ops import (
    agent_map_async,
    dedupe_async,
    merge_async,
    rank_async,
    screen_async,
)
from everyrow.session import Session, create_session, get_session_url
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from everyrow_mcp.utils import (
    save_result_to_csv,
    validate_csv_output_path,
    validate_csv_path,
)

PROGRESS_POLL_DELAY = 12  # seconds to block in everyrow_progress before returning
TASK_STATE_FILE = Path.home() / ".everyrow" / "task.json"
# Singleton client, initialized in lifespan
_client: AuthenticatedClient | None = None


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Initialize singleton client and validate credentials on startup."""
    global _client  # noqa: PLW0603

    _clear_task_state()

    try:
        with create_client() as _client:
            response = await get_billing(client=_client)
            if response is None:
                raise RuntimeError("Failed to authenticate with everyrow API")
            yield
    except Exception as e:
        logging.getLogger(__name__).error(f"everyrow-mcp startup failed: {e!r}")
        raise
    finally:
        _client = None
        _clear_task_state()


mcp = FastMCP("everyrow_mcp", lifespan=lifespan)

# If EVERYROW_SESSION_ID is set, reuse that session for all operations
# instead of creating a new one each time.
_fixed_session_id: UUID | None = None
_env_session_id = os.environ.get("EVERYROW_SESSION_ID")
if _env_session_id:
    try:
        _fixed_session_id = UUID(_env_session_id)
    except ValueError:
        logging.getLogger(__name__).warning(
            f"Invalid EVERYROW_SESSION_ID: {_env_session_id}, ignoring"
        )


@asynccontextmanager
async def _get_session(client: AuthenticatedClient):
    """Get a session — reuses fixed session if EVERYROW_SESSION_ID is set, else creates new."""
    if _fixed_session_id is not None:
        yield Session(client=client, session_id=_fixed_session_id)
    else:
        async with create_session(client=client) as session:
            yield session


def _clear_task_state() -> None:
    if TASK_STATE_FILE.exists():
        TASK_STATE_FILE.unlink()


def _write_task_state(
    task_id: str,
    session_url: str,
    total: int,
    completed: int,
    failed: int,
    running: int,
    status: TaskStatus,
    started_at: datetime,
) -> None:
    """Write task tracking state for hooks/status line to read.

    Note: Only one task is tracked at a time. If multiple tasks run concurrently,
    only the most recent one's progress is shown.
    """
    try:
        TASK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "task_id": task_id,
            "session_url": session_url,
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "status": status.value,
            "started_at": started_at.timestamp(),
        }
        with open(TASK_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logging.getLogger(__name__).debug(f"Failed to write task state: {e!r}")


class AgentInput(BaseModel):
    """Input for the agent operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language task to perform on each row.", min_length=1
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the agent's response per row.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class RankInput(BaseModel):
    """Input for the rank operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language instructions for scoring a single row.",
        min_length=1,
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
    field_name: str = Field(..., description="Name of the field to sort by.")
    field_type: Literal["float", "int", "str", "bool"] = Field(
        default="float",
        description="Type of the score field: 'float', 'int', 'str', or 'bool'",
    )
    ascending_order: bool = Field(
        default=True, description="Sort ascending (True) or descending (False)."
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the response model.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class ScreenInput(BaseModel):
    """Input for the screen operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language screening criteria.", min_length=1
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the response model.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class DedupeInput(BaseModel):
    """Input for the dedupe operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    equivalence_relation: str = Field(
        ...,
        description="Natural language description of what makes two rows equivalent/duplicates. "
        "The LLM will use this to identify which rows represent the same entity.",
        min_length=1,
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class MergeInput(BaseModel):
    """Input for the merge operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language description of how to match rows.",
        min_length=1,
    )
    left_csv: str = Field(..., description="Absolute path to the left/primary CSV.")
    right_csv: str = Field(..., description="Absolute path to the right/secondary CSV.")
    merge_on_left: str | None = Field(
        default=None, description="Optional column name in left table for merge key."
    )
    merge_on_right: str | None = Field(
        default=None, description="Optional column name in right table for merge key."
    )
    use_web_search: Literal["auto", "yes", "no"] | None = Field(
        default=None, description='Control web search: "auto", "yes", or "no".'
    )
    relationship_type: Literal["many_to_one", "one_to_one"] | None = Field(
        default=None,
        description='Optional. Control merge relationship type: "many_to_one" (default) allows multiple left rows to match one right row, "one_to_one" enforces unique matching between left and right rows.',
    )

    @field_validator("left_csv", "right_csv")
    @classmethod
    def validate_csv_paths(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class ProgressInput(BaseModel):
    """Input for checking task progress."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID returned by the operation tool.")


class ResultsInput(BaseModel):
    """Input for retrieving completed task results."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID of the completed task.")
    output_path: str = Field(
        ...,
        description="Full absolute path to the output CSV file (must end in .csv).",
    )

    @field_validator("output_path")
    @classmethod
    def validate_output(cls, v: str) -> str:
        validate_csv_output_path(v)
        return v


class CancelInput(BaseModel):
    """Input for cancelling a running task."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID to cancel.")


@mcp.tool(name="everyrow_agent", structured_output=False)
async def everyrow_agent(params: AgentInput) -> list[TextContent]:
    """Run web research agents on each row of a CSV.

    Submit the task and return immediately with a task_id and session_url.
    After receiving a result from this tool, share the session_url with the user.
    Then immediately call everyrow_progress(task_id) to monitor.
    Once the task is completed, call everyrow_results to save the output.

    Examples:
    - "Find this company's latest funding round and lead investors"
    - "Research the CEO's background and previous companies"
    - "Find pricing information for this product"
    """
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("AgentResult", params.response_schema)

    async with _get_session(_client) as session:
        session_url = session.get_url()
        kwargs: dict[str, Any] = {"task": params.task, "session": session, "input": df}
        if response_model:
            kwargs["response_model"] = response_model
        cohort_task = await agent_map_async(**kwargs)
        task_id = str(cohort_task.task_id)
        _write_task_state(
            task_id,
            session_url,
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


@mcp.tool(name="everyrow_rank", structured_output=False)
async def everyrow_rank(params: RankInput) -> list[TextContent]:
    """Score and sort rows in a CSV based on qualitative criteria.

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
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("RankResult", params.response_schema)

    async with _get_session(_client) as session:
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
            session_url,
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


@mcp.tool(name="everyrow_screen", structured_output=False)
async def everyrow_screen(params: ScreenInput) -> list[TextContent]:
    """Filter rows in a CSV based on criteria that require judgment.

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
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

    response_model: type[BaseModel] | None = None
    if params.response_schema:
        response_model = _schema_to_model("ScreenResult", params.response_schema)

    async with _get_session(_client) as session:
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
            session_url,
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


@mcp.tool(name="everyrow_dedupe", structured_output=False)
async def everyrow_dedupe(params: DedupeInput) -> list[TextContent]:
    """Remove duplicate rows from a CSV using semantic equivalence.

    Dedupe identifies rows that represent the same entity even when they
    don't match exactly. Useful for fuzzy deduplication where string
    matching fails.

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
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    _clear_task_state()
    df = pd.read_csv(params.input_csv)

    async with _get_session(_client) as session:
        session_url = session.get_url()
        cohort_task = await dedupe_async(
            equivalence_relation=params.equivalence_relation,
            session=session,
            input=df,
        )
        task_id = str(cohort_task.task_id)
        _write_task_state(
            task_id,
            session_url,
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


@mcp.tool(name="everyrow_merge", structured_output=False)
async def everyrow_merge(params: MergeInput) -> list[TextContent]:
    """Join two CSV files using intelligent entity matching.

    Merge combines two tables even when keys don't match exactly. The LLM
    performs research and reasoning to identify which rows should be joined.

    Examples:
    - Match software products to parent companies (Photoshop -> Adobe)
    - Match clinical trial sponsors to pharma companies (Genentech -> Roche)
    - Join contact lists with different name formats

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
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    _clear_task_state()
    left_df = pd.read_csv(params.left_csv)
    right_df = pd.read_csv(params.right_csv)

    async with _get_session(_client) as session:
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
            session_url,
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


@mcp.tool(name="everyrow_progress", structured_output=False)
async def everyrow_progress(params: ProgressInput) -> list[TextContent]:
    """Check progress of a running task. Blocks for a time to limit the polling rate.

    After receiving a status update, immediately call everyrow_progress again
    unless the task is completed or failed. The tool handles pacing internally.
    Do not add commentary between progress calls, just call again immediately.
    """
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    task_id = params.task_id

    # Block server-side before polling — controls the cadence
    await asyncio.sleep(PROGRESS_POLL_DELAY)

    try:
        status_response = handle_response(
            await get_task_status_tasks_task_id_status_get.asyncio(
                task_id=UUID(task_id),
                client=_client,
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
        session_url,
        total,
        completed,
        failed,
        running,
        status,
        started_at,
    )

    if is_terminal:
        error = status_response.error
        if error and not isinstance(error, Unset):
            return [TextContent(type="text", text=f"Task {status.value}: {error}")]
        if status == TaskStatus.COMPLETED:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Completed: {completed}/{total} ({failed} failed) in {elapsed_s}s.\n"
                        f"Call everyrow_results(task_id='{task_id}', output_path='/path/to/output.csv') to save the output."
                    ),
                )
            ]
        return [
            TextContent(
                type="text", text=f"Task {status.value}. Report the error to the user."
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


@mcp.tool(name="everyrow_results", structured_output=False)
async def everyrow_results(params: ResultsInput) -> list[TextContent]:
    """Retrieve results from a completed everyrow task and save them to a CSV.

    Only call this after everyrow_progress reports status 'completed'.
    The output_path must be a full file path ending in .csv.
    """
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    task_id = params.task_id
    output_file = Path(params.output_path)

    try:
        status_response = handle_response(
            await get_task_status_tasks_task_id_status_get.asyncio(
                task_id=UUID(task_id),
                client=_client,
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
                client=_client,
            )
        )

        if isinstance(result_response.data, list):
            records = [item.additional_properties for item in result_response.data]
            df = pd.DataFrame(records)
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


@mcp.tool(name="everyrow_cancel", structured_output=False)
async def everyrow_cancel(params: CancelInput) -> list[TextContent]:
    """Cancel a running everyrow task. Use when the user wants to stop a task that is currently processing."""
    if _client is None:
        return [TextContent(type="text", text="Error: MCP server not initialized.")]

    task_id = params.task_id
    try:
        base_url = str(_client._base_url).rstrip("/")
        cancel_url = f"{base_url}/tasks/{task_id}/cancel"

        async with httpx.AsyncClient() as http:
            response = await http.post(
                cancel_url,
                headers={
                    f"{_client.auth_header_name}": f"{_client.prefix} {_client.token}"
                },
                timeout=30.0,
            )

        if response.status_code == 200:
            _clear_task_state()
            data = response.json()
            return [
                TextContent(
                    type="text",
                    text=f"Cancelled task {task_id}. Status: {data.get('status', 'REVOKED')}.",
                )
            ]
        elif response.status_code == 409:
            _clear_task_state()
            detail = response.json().get("detail", "already terminated")
            return [
                TextContent(
                    type="text",
                    text=f"Task {task_id} is already finished: {detail}",
                )
            ]
        elif response.status_code == 404:
            return [
                TextContent(
                    type="text",
                    text=f"Task {task_id} not found. Check the task ID and try again.",
                )
            ]
        else:
            return [
                TextContent(
                    type="text",
                    text=f"Error cancelling task {task_id}: HTTP {response.status_code} — {response.text}",
                )
            ]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error cancelling task {task_id}: {e!r}",
            )
        ]


JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _schema_to_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Convert a JSON schema dict to a dynamic Pydantic model.

    This allows the MCP client to pass arbitrary response schemas without
    needing to define Python classes.
    """
    properties = schema.get("properties", schema)
    required = set(schema.get("required", []))

    fields: dict[str, Any] = {}
    for field_name, field_def in properties.items():
        if field_name.startswith("_") or not isinstance(field_def, dict):
            continue

        field_type_str = field_def.get("type", "string")
        python_type = JSON_TYPE_MAP.get(field_type_str, str)
        description = field_def.get("description", "")

        if field_name in required:
            fields[field_name] = (python_type, Field(..., description=description))
        else:
            fields[field_name] = (
                python_type | None,
                Field(default=None, description=description),
            )

    return create_model(name, **fields)


def main():
    """Run the MCP server."""
    # Signal to the SDK that we're inside the MCP server (suppresses plugin hints)
    os.environ["EVERYROW_MCP_SERVER"] = "1"

    # Configure logging to use stderr only (stdout is reserved for JSON-RPC)
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s: %(message)s",
        force=True,
    )

    # Check for API key before starting
    if "EVERYROW_API_KEY" not in os.environ:
        logging.error("EVERYROW_API_KEY environment variable is not set.")
        logging.error("Get an API key at https://everyrow.io/api-key")
        sys.exit(1)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

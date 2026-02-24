from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from textwrap import dedent
from typing import Any
from uuid import UUID

import pandas as pd
from everyrow.api_utils import handle_response
from everyrow.generated.api.tasks import (
    get_task_result_tasks_task_id_result_get,
    get_task_status_tasks_task_id_status_get,
)
from everyrow.generated.client import AuthenticatedClient
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_result_response_data_type_1 import (
    TaskResultResponseDataType1,
)
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse
from everyrow.generated.types import Unset
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, PrivateAttr, computed_field

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SessionContext:
    """Per-session lifespan context yielded by all lifespans."""

    client_factory: Callable[[], AuthenticatedClient]
    """Return an API client for the current request.

    In stdio/no-auth mode this returns a long-lived singleton.
    In HTTP mode it constructs a fresh client with the current request's
    access token — call once per tool invocation, do not cache across awaits.
    """

    mcp_server_url: str = ""
    """Base URL of the MCP server (HTTP mode only).

    Used to build progress polling and CSV download URLs.
    Empty in stdio mode.
    """


# Typed Context alias — gives type checkers visibility into lifespan_context.
EveryRowContext = Context[ServerSession, SessionContext]


def _get_client(ctx: EveryRowContext) -> AuthenticatedClient:
    """Get an EveryRow API client from the FastMCP lifespan context."""
    return ctx.request_context.lifespan_context.client_factory()


def _submission_text(label: str, session_url: str, task_id: str) -> str:
    """Build human-readable text for submission tool results."""
    if settings.is_stdio:
        return dedent(f"""\
        {label}
        Session: {session_url}
        Task ID: {task_id}

        Share the session_url with the user, then immediately call everyrow_progress(task_id='{task_id}').""")
    return dedent(f"""\
        {label}
        Task ID: {task_id}

        Immediately call everyrow_progress(task_id='{task_id}').""")


async def _submission_ui_json(
    session_url: str,
    task_id: str,
    total: int,
    token: str,
    mcp_server_url: str = "",
) -> str:
    """Build JSON for the session MCP App widget, and store the token for polling."""
    poll_token = secrets.token_urlsafe(32)
    await redis_store.store_task_token(task_id, token)
    await redis_store.store_poll_token(task_id, poll_token)

    # Record task owner for cross-user access checks (HTTP mode only).
    # This MUST succeed — downstream ownership checks deny access when no
    # owner is recorded, so a silent failure here would lock the user out
    # of their own task.
    if settings.is_http:
        access_token = get_access_token()
        if not access_token or not access_token.client_id:
            raise RuntimeError(
                f"Cannot record task owner for {task_id}: no authenticated user"
            )
        await redis_store.store_task_owner(task_id, access_token.client_id)
    data: dict[str, Any] = {
        "session_url": session_url,
        "task_id": task_id,
        "total": total,
        "status": "submitted",
    }
    if mcp_server_url:
        data["progress_url"] = f"{mcp_server_url}/api/progress/{task_id}"
        data["poll_token"] = poll_token
    return json.dumps(data)


async def create_tool_response(
    *,
    task_id: str,
    session_url: str,
    label: str,
    token: str,
    total: int,
    mcp_server_url: str = "",
) -> list[TextContent]:
    """Build the standard submission response for a tool.

    Returns human-readable text in all modes, plus a widget JSON
    prepended in HTTP mode.
    """
    text = _submission_text(label, session_url, task_id)
    main_content = TextContent(type="text", text=text)
    if settings.is_http:
        ui_json = await _submission_ui_json(
            session_url=session_url,
            task_id=task_id,
            total=total,
            token=token,
            mcp_server_url=mcp_server_url,
        )
        return [TextContent(type="text", text=ui_json), main_content]
    return [main_content]


_UI_EXCLUDE: set[str] = {"is_terminal", "is_screen", "task_type", "error", "started_at"}


class TaskState(BaseModel):
    """Parsed progress snapshot from an API status response."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _response: TaskStatusResponse = PrivateAttr()

    def __init__(self, response: TaskStatusResponse) -> None:
        super().__init__()
        self._response = response

    @computed_field
    @property
    def status(self) -> TaskStatus:
        return self._response.status

    @computed_field
    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.REVOKED,
        )

    @computed_field
    @property
    def is_screen(self) -> bool:
        return self._response.task_type == PublicTaskType.SCREEN

    @computed_field
    @property
    def task_type(self) -> PublicTaskType:
        return self._response.task_type

    @computed_field
    @property
    def session_url(self) -> str:
        from everyrow.session import get_session_url  # noqa: PLC0415

        return get_session_url(self._response.session_id)

    @computed_field
    @property
    def completed(self) -> int:
        p = self._response.progress
        return p.completed if p else 0

    @computed_field
    @property
    def failed(self) -> int:
        p = self._response.progress
        return p.failed if p else 0

    @computed_field
    @property
    def running(self) -> int:
        p = self._response.progress
        return p.running if p else 0

    @computed_field
    @property
    def total(self) -> int:
        p = self._response.progress
        return p.total if p else 0

    @computed_field
    @property
    def error(self) -> str | None:
        err = self._response.error
        if err and not isinstance(err, Unset):
            return str(err)
        return None

    @computed_field
    @property
    def started_at(self) -> datetime:
        created = self._response.created_at
        if not created:
            return datetime.now(UTC)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return created

    @computed_field
    @property
    def elapsed_s(self) -> int:
        created = self._response.created_at
        if not created:
            return 0
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if self.is_terminal and self._response.updated_at:
            end = self._response.updated_at
            if end.tzinfo is None:
                end = end.replace(tzinfo=UTC)
            return round((end - created).total_seconds())
        return round((datetime.now(UTC) - created).total_seconds())

    def write_file(self, task_id: str) -> None:
        """Write task tracking state for hooks/status line to read."""
        if settings.is_http:
            return
        _write_task_state_file(
            task_id=task_id,
            task_type=self.task_type,
            session_url=self.session_url,
            total=self.total,
            completed=self.completed,
            failed=self.failed,
            running=self.running,
            status=self.status,
            started_at=self.started_at,
        )

    def progress_message(self, task_id: str) -> str:
        if self.is_terminal:
            if self.error:
                return f"Task {self.status.value}: {self.error}"
            if self.status == TaskStatus.COMPLETED:
                if self.is_screen:
                    completed_msg = f"Screening complete ({self.elapsed_s}s)."
                else:
                    completed_msg = f"Completed: {self.completed}/{self.total} ({self.failed} failed) in {self.elapsed_s}s."
                if settings.is_http:
                    next_call = dedent(f"""\
                        Call everyrow_results(task_id='{task_id}', page_size={settings.preview_size}) to view the output. \
                        The server auto-adjusts page_size to fit a {settings.token_budget:,}-token budget.""")
                else:
                    next_call = f"Call everyrow_results(task_id='{task_id}', output_path='<choose_a_path>.csv') to save the output."
                return f"{completed_msg}\n{next_call}"
            return f"Task {self.status.value}. Report the error to the user."

        if self.is_screen:
            return dedent(f"""\
                Screen running ({self.elapsed_s}s elapsed).
                Immediately call everyrow_progress(task_id='{task_id}').""")

        fail_part = f", {self.failed} failed" if self.failed else ""
        return dedent(f"""\
            Running: {self.completed}/{self.total} complete, {self.running} running{fail_part} ({self.elapsed_s}s elapsed)
            Immediately call everyrow_progress(task_id='{task_id}').""")


def write_initial_task_state(
    task_id: str,
    *,
    task_type: PublicTaskType,
    session_url: str,
    total: int,
    input_source: str = "unknown",
) -> None:
    """Write initial task state file when a task is first submitted."""
    logger.info(
        "Task %s (%s): input_source=%s, total=%d",
        task_id,
        task_type.value,
        input_source,
        total,
    )
    if settings.is_http:
        return
    _write_task_state_file(
        task_id=task_id,
        task_type=task_type,
        session_url=session_url,
        total=total,
        completed=0,
        failed=0,
        running=0,
        status=TaskStatus.RUNNING,
        started_at=datetime.now(UTC),
    )


def _write_task_state_file(
    *,
    task_id: str,
    task_type: PublicTaskType,
    session_url: str,
    total: int,
    completed: int,
    failed: int,
    running: int,
    status: TaskStatus,
    started_at: datetime,
) -> None:
    """Low-level helper: serialise task state to the status-line JSON file."""
    try:
        redis_store.TASK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": task_id,
            "task_type": task_type.value,
            "session_url": session_url,
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "status": status.value,
            "started_at": started_at.timestamp(),
        }
        with open(redis_store.TASK_STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.debug(f"Failed to write task state: {e!r}")


class TaskNotReady(Exception):
    """Raised when a task is not in a terminal state."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


async def _fetch_task_result(client: Any, task_id: str) -> tuple[pd.DataFrame, str]:
    """Fetch a task's result DataFrame and session ID from the API.

    Checks task status first, then retrieves and parses the result data.

    Returns:
        Tuple of (DataFrame, session_id).

    Raises:
        TaskNotReady: If the task is not in a terminal state.
        ValueError: If the result has no table data.
        Exception: On API errors.
    """
    status_response = handle_response(
        await get_task_status_tasks_task_id_status_get.asyncio(
            task_id=UUID(task_id),
            client=client,
        )
    )
    if status_response.status not in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.REVOKED,
    ):
        raise TaskNotReady(status_response.status.value)

    if status_response.status != TaskStatus.COMPLETED:
        raise ValueError(
            f"Task {task_id} ended with status {status_response.status.value}; "
            "no results available."
        )

    session_id = str(status_response.session_id) if status_response.session_id else ""

    result_response = handle_response(
        await get_task_result_tasks_task_id_result_get.asyncio(
            task_id=UUID(task_id),
            client=client,
        )
    )

    if isinstance(result_response.data, list):
        records = [item.additional_properties for item in result_response.data]
        return pd.DataFrame(records), session_id
    if isinstance(result_response.data, TaskResultResponseDataType1):
        return pd.DataFrame([result_response.data.additional_properties]), session_id
    raise ValueError("Task result has no table data.")

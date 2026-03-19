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

import httpx
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
from everyrow.session import get_session_url
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


def log_client_info(ctx: EveryRowContext, tool_name: str) -> None:
    """Log MCP client identity and capabilities for the current request."""
    try:
        cp = ctx.session.client_params
        if not cp:
            # Stateless HTTP mode — no MCP initialize handshake.
            # Fall back to User-Agent from the HTTP request.
            from everyrow_mcp.http_config import get_user_agent  # noqa: PLC0415

            ua = get_user_agent()
            logger.info(
                "[%s] client_params=None (stateless) ua=%s",
                tool_name,
                ua or "-",
            )
            return
        name = cp.clientInfo.name if cp.clientInfo else "unknown"
        version = cp.clientInfo.version if cp.clientInfo else "unknown"
        caps = cp.capabilities
        experimental = (caps.experimental or {}) if caps else {}
        logger.info(
            "[%s] client=%s/%s sampling=%s elicitation=%s roots=%s ui=%s",
            tool_name,
            name,
            version,
            caps.sampling is not None if caps else False,
            caps.elicitation is not None if caps else False,
            caps.roots is not None if caps else False,
            experimental.get("io.modelcontextprotocol/ui") is not None,
        )
    except Exception:
        logger.debug("Could not log client info for %s", tool_name, exc_info=True)


def client_supports_widgets(ctx: EveryRowContext) -> bool:
    """Return True if the connected MCP client can render widgets.

    Uses a three-tier approach:

    1. **MCP Apps UI capability** (spec-recommended, future-proof):
       Clients that advertise ``experimental["io.modelcontextprotocol/ui"]``
       explicitly support widget rendering.  This is the long-term signal.

    2. **Name-based whitelist** (pragmatic fallback):
       Claude.ai and Claude Desktop can render widgets but don't yet
       advertise the UI capability.  We maintain a whitelist of known
       widget-capable client names so they get widgets today.
       This fallback should be removed once clients adopt the capability.

    3. **User-Agent whitelist** (stateless HTTP mode):
       When ``client_params`` is ``None`` (stateless HTTP — no MCP initialize
       handshake), we check the HTTP User-Agent header against a whitelist
       of known widget-capable UAs (currently ``"Claude-User"``).  If the
       User-Agent is unknown, we default to **no widget** to avoid wasting
       context tokens on clients that can't render them.

    Unknown clients default to **no widget** in both stateful (tier 2) and
    stateless (tier 3) modes.
    """
    try:
        cp = ctx.session.client_params
        if not cp:
            # Stateless HTTP mode — no MCP initialize handshake.
            # Fall back to User-Agent detection.
            return _widgets_from_user_agent()

        # Tier 1: explicit UI capability (preferred, spec-recommended)
        caps = cp.capabilities
        if caps:
            experimental = caps.experimental or {}
            if experimental.get("io.modelcontextprotocol/ui") is not None:
                return True

        # Tier 2: name-based whitelist for known widget-capable clients
        # that don't yet advertise the UI capability.
        # Update this set as new clients are verified via log_client_info().
        # Known values (from log_client_info, Feb 2026):
        #   Claude.ai:    "Anthropic/ClaudeAI"  (version "1.0.0")
        #   Claude Desktop: "Anthropic/ClaudeAI"  (version "1.0.0") — same as Claude.ai
        #   Claude Code:  "claude-code"
        # Note: Claude.ai and Claude Desktop report the same clientInfo.name,
        # so a single whitelist entry covers both.
        _WIDGET_CAPABLE_CLIENTS = {"anthropic/claudeai"}
        name = (cp.clientInfo.name or "").lower() if cp.clientInfo else ""
        return name in _WIDGET_CAPABLE_CLIENTS
    except Exception:
        logger.debug("Could not determine widget support", exc_info=True)
        return False  # unknown client — skip widget to save context tokens


def _widgets_from_user_agent() -> bool:
    """Tier 3: determine widget support from HTTP User-Agent.

    Called when client_params is None (stateless HTTP mode).

    Strategy: whitelist known widget-capable clients, deny everything else.
    Only clients we have confirmed can render widgets get them; unknown UAs
    default to text-only to avoid wasting context tokens on unsupported UIs.
    """
    from everyrow_mcp.http_config import get_user_agent  # noqa: PLC0415

    ua = get_user_agent().lower()

    # Whitelist of UA substrings for clients that support widgets.
    #
    # Observed User-Agent values (Feb 2026):
    #   Claude.ai:       "Claude-User"          — supports widgets
    #   Claude Desktop:  "Claude-User"          — supports widgets
    #   Claude Code CLI: "claude-code/2.1.62 (cli)" — text-only
    #   everyrow:        "everyrow/1.0"         — text-only (internal)
    #   MCP SDK (test):  "python-httpx/0.28.1"  — text-only
    #   OAuth helper:    "Bun/1.3.10"           — not a tool caller
    #
    # Claude.ai and Claude Desktop both send "Claude-User". If Anthropic
    # changes this, we'll need to update the whitelist.
    _WIDGET_UA_SUBSTRINGS = {"claude-user"}

    return any(pattern in ua for pattern in _WIDGET_UA_SUBSTRINGS)


def is_internal_client() -> bool:
    """Return True if the request comes from everyrow's own app."""
    from everyrow_mcp.http_config import get_user_agent  # noqa: PLC0415

    return "everyrow" in get_user_agent().lower()


def _submission_text(
    label: str, session_url: str, task_id: str, session_id: str = ""
) -> str:
    """Build human-readable text for submission tool results."""
    if settings.is_stdio:
        session_line = f"\nSession ID: {session_id}" if session_id else ""
        return dedent(f"""\
        {label}
        Session: {session_url}{session_line}
        Task ID: {task_id}

        Immediately call everyrow_progress(task_id='{task_id}').""")
    if is_internal_client():
        return dedent(f"""\
        {label}
        Task ID: {task_id}

        Immediately call everyrow_progress(task_id='{task_id}').""")
    session_line = f"\nSession ID: {session_id}" if session_id else ""
    return dedent(f"""\
        {label}{session_line}
        Task ID: {task_id}

        Immediately call everyrow_progress(task_id='{task_id}').""")


async def _record_task_ownership(task_id: str, token: str) -> str:
    """Record task ownership and create a poll token.

    Must run for every HTTP submission (including internal clients) so that
    downstream ownership checks in progress/results don't fail.

    Returns the poll_token.
    """
    poll_token = secrets.token_urlsafe(32)
    await redis_store.store_task_token(task_id, token)

    # Record task owner for cross-user access checks (HTTP mode only).
    # This MUST succeed — downstream ownership checks deny access when no
    # owner is recorded, so a silent failure here would lock the user out
    # of their own task.
    user_id = ""
    if settings.is_http:
        access_token = get_access_token()
        if not access_token or not access_token.client_id:
            raise RuntimeError(
                f"Cannot record task owner for {task_id}: no authenticated user"
            )
        user_id = access_token.client_id
        await redis_store.store_task_owner(task_id, user_id)

    # Bind the poll token to the same user identity so the REST layer
    # can cross-check poll_owner == task_owner.
    await redis_store.store_poll_token(task_id, poll_token, user_id=user_id)
    return poll_token


async def _submission_ui_json(
    session_url: str,
    task_id: str,
    total: int,
    poll_token: str,
    mcp_server_url: str = "",
    session_id: str = "",
) -> str:
    """Build JSON for the session MCP App widget."""
    data: dict[str, Any] = {
        "session_url": session_url,
        "task_id": task_id,
        "total": total,
        "status": "submitted",
    }
    if session_id:
        data["session_id"] = session_id
    if mcp_server_url:
        data["progress_url"] = f"{mcp_server_url}/api/progress/{task_id}"
        data["poll_token"] = poll_token
    return json.dumps(data)


async def _start_headless_summarizer(task_id: str, token: str) -> None:
    """Fire-and-forget request to start headless summarizer for a task."""
    try:
        async with httpx.AsyncClient(
            base_url=settings.everyrow_api_url,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            await client.post(f"/tasks/{task_id}/summaries/start")
    except Exception:
        logger.debug("Failed to start headless summarizer for %s", task_id)


async def create_tool_response(
    *,
    task_id: str,
    session_url: str,
    label: str,
    token: str,
    total: int,
    mcp_server_url: str = "",
    session_id: str = "",
) -> list[TextContent]:
    """Build the standard submission response for a tool.

    Returns human-readable text in all modes, plus a widget JSON
    prepended in HTTP mode.
    """
    text = _submission_text(label, session_url, task_id, session_id=session_id)
    main_content = TextContent(type="text", text=text)
    if settings.is_http:
        poll_token = await _record_task_ownership(task_id, token)
        if not is_internal_client():
            # Start headless summarizer so external clients get progress
            # summaries without needing a frontend SSE connection.
            await _start_headless_summarizer(task_id, token)
            ui_json = await _submission_ui_json(
                session_url=session_url,
                task_id=task_id,
                total=total,
                poll_token=poll_token,
                mcp_server_url=mcp_server_url,
                session_id=session_id,
            )
            return [TextContent(type="text", text=ui_json), main_content]
    return [main_content]


_UI_EXCLUDE: set[str] = {"is_terminal", "task_type", "error", "started_at"}


def _format_summary_lines(summaries: list[dict[str, Any]]) -> str:
    """Collapse duplicate summaries from batched agents into grouped lines.

    One trace handling multiple rows produces the same text per row.
    Groups by text and merges row indices: ``[Rows 29, 17] Summarizing...``
    """
    grouped: dict[str, list[int]] = {}
    grouped_order: list[str] = []
    for s in summaries:
        text = s["summary"]
        row_idx = s.get("row_index")
        if text not in grouped:
            grouped[text] = []
            grouped_order.append(text)
        if row_idx is not None:
            grouped[text].append(row_idx)
    lines = ""
    for text in grouped_order:
        rows = grouped[text]
        if rows:
            label = "Row" if len(rows) == 1 else "Rows"
            prefix = f"[{label} {', '.join(str(r) for r in sorted(rows))}] "
        else:
            prefix = ""
        lines += f"\n- {prefix}{text}"
    return lines


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
    def task_type(self) -> PublicTaskType:
        return self._response.task_type

    @computed_field
    @property
    def session_url(self) -> str:
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
    def artifact_id(self) -> str:
        aid = self._response.artifact_id
        if aid is not None and not isinstance(aid, Unset):
            return str(aid)
        return ""

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

    def progress_message(  # noqa: PLR0912
        self,
        task_id: str,
        *,
        partial_rows: list[dict[str, Any]] | None = None,
        cursor: str | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> str:
        if self.is_terminal:
            if self.error:
                return f"Task {self.status.value}: {self.error}"
            if self.status == TaskStatus.COMPLETED:
                completed_msg = f"Completed: {self.completed}/{self.total} ({self.failed} failed) in {self.elapsed_s}s."
                if settings.is_http:
                    if self.total <= settings.auto_page_size_threshold:
                        next_call = dedent(f"""\
                            Call everyrow_results(task_id='{task_id}', page_size={max(self.total, 1)}) to load all rows.""")
                    else:
                        widget_note = (
                            " You will have access to all of them via the widget."
                            if is_internal_client()
                            else ""
                        )
                        next_call = dedent(f"""\
                            IMPORTANT: Do NOT call everyrow_results yet.\
                             First, ask the user: "The task produced {self.total} rows. How many would you like me to load into my context so I can read them? (default: {settings.auto_page_size_threshold}).{widget_note}".\
                             The answer the user provides will correspond to the `page_size`.\
                             After the user responds, call everyrow_results(task_id='{task_id}', page_size=N).""")
                else:
                    next_call = f"Call everyrow_results(task_id='{task_id}', output_path='<choose_a_path>.csv') to save the output."
                if self.artifact_id:
                    completed_msg += f"\nOutput artifact_id: {self.artifact_id}"
                return f"{completed_msg}\n{next_call}"
            return f"Task {self.status.value}. Report the error to the user."

        fail_part = f", {self.failed} failed" if self.failed else ""
        cursor_arg = f", cursor='{cursor}'" if cursor else ""
        msg = dedent(f"""\
            Running: {self.completed}/{self.total} complete, {self.running} running{fail_part} ({self.elapsed_s}s elapsed)""")

        if summaries:
            msg += "\n\nAgent activity:" + _format_summary_lines(summaries)

        if partial_rows:
            msg += "\n\nNewly completed rows:"
            for row in partial_rows:
                msg += f"\n- {json.dumps(row, default=str)}"

        progress_call = f"everyrow_progress(task_id='{task_id}'{cursor_arg})"

        if not is_internal_client() and (partial_rows or summaries):
            msg += f"\n\nBriefly comment on these updates for the user, then immediately call {progress_call}."
        else:
            msg += f"\nImmediately call {progress_call}."

        return msg


class TaskNotReady(Exception):
    """Raised when a task is not in a terminal state."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


async def _fetch_task_result(
    client: Any, task_id: str
) -> tuple[pd.DataFrame, str, str]:
    """Fetch a task's result DataFrame, session ID, and output artifact ID from the API.

    Checks task status first, then retrieves and parses the result data.

    Returns:
        Tuple of (DataFrame, session_id, artifact_id).

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

    artifact_id = ""
    aid = result_response.artifact_id
    if aid is not None and not isinstance(aid, Unset):
        artifact_id = str(aid)

    if isinstance(result_response.data, list):
        records = [item.additional_properties for item in result_response.data]
        return pd.DataFrame(records), session_id, artifact_id
    if isinstance(result_response.data, TaskResultResponseDataType1):
        return (
            pd.DataFrame([result_response.data.additional_properties]),
            session_id,
            artifact_id,
        )
    raise ValueError("Task result has no table data.")

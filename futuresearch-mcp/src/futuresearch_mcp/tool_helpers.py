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
from futuresearch.api_utils import handle_response
from futuresearch.generated.api.tasks import (
    get_task_status_tasks_task_id_status_get,
)
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse
from futuresearch.generated.types import Unset
from futuresearch.session import create_session
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, PrivateAttr, computed_field

from futuresearch_mcp import redis_store
from futuresearch_mcp.config import settings

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
FuturesearchContext = Context[ServerSession, SessionContext]


def _get_client(ctx: FuturesearchContext) -> AuthenticatedClient:
    """Get an FutureSearch API client from the FastMCP lifespan context."""
    return ctx.request_context.lifespan_context.client_factory()


def _get_conversation_id() -> str | None:
    """Get the conversation ID from the current HTTP request context, if any."""
    try:
        from futuresearch_mcp.http_config import get_conversation_id  # noqa: PLC0415

        val = get_conversation_id()
        return val if val else None
    except Exception:
        return None


def create_linked_session(
    client: AuthenticatedClient,
    **kwargs: Any,
):
    """Wrapper around SDK create_session that passes conversation_id from HTTP context."""
    conv_id = _get_conversation_id()
    return create_session(client=client, conversation_id=conv_id, **kwargs)


def log_client_info(ctx: FuturesearchContext, tool_name: str) -> None:
    """Log MCP client identity and capabilities for the current request."""
    try:
        cp = ctx.session.client_params
        if not cp:
            # Stateless HTTP mode — no MCP initialize handshake.
            # Fall back to User-Agent from the HTTP request.
            from futuresearch_mcp.http_config import get_user_agent  # noqa: PLC0415

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


def client_supports_widgets(ctx: FuturesearchContext) -> bool:
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
    from futuresearch_mcp.http_config import get_user_agent  # noqa: PLC0415

    ua = get_user_agent().lower()

    # Whitelist of UA substrings for clients that support widgets.
    #
    # Observed User-Agent values (Feb 2026):
    #   Claude.ai:       "Claude-User"          — supports widgets
    #   Claude Desktop:  "Claude-User"          — supports widgets
    #   Claude Code CLI: "claude-code/2.1.62 (cli)" — text-only
    #   futuresearch:    "futuresearch/1.0"     — text-only (internal)
    #   MCP SDK (test):  "python-httpx/0.28.1"  — text-only
    #   OAuth helper:    "Bun/1.3.10"           — not a tool caller
    #
    # Claude.ai and Claude Desktop both send "Claude-User". If Anthropic
    # changes this, we'll need to update the whitelist.
    _WIDGET_UA_SUBSTRINGS = {"claude-user"}

    return any(pattern in ua for pattern in _WIDGET_UA_SUBSTRINGS)


def is_internal_client() -> bool:
    """Return True if the request comes from FutureSearch's own app."""
    from futuresearch_mcp.http_config import get_user_agent  # noqa: PLC0415

    return "futuresearch" in get_user_agent().lower()


def _submission_text(label: str, task_id: str, session_id: str = "") -> str:
    """Build human-readable text for submission tool results."""
    session_line = f"\nSession ID: {session_id}" if session_id else ""
    if not settings.is_stdio and _widgets_from_user_agent():
        # Claude.ai / Claude Desktop: direct to widget tool
        return dedent(f"""\
            {label}{session_line}
            Task ID: {task_id}

            Immediately call futuresearch_status(task_id='{task_id}') to show a live progress widget.
            Do NOT call futuresearch_progress — the widget polls automatically.""")
    # stdio, Claude Code, everyrow-cc, or unknown clients: text-only polling
    return dedent(f"""\
        {label}{session_line}
        Task ID: {task_id}

        Immediately call futuresearch_progress(task_id='{task_id}').""")


async def _record_task_ownership(task_id: str, token: str) -> str:
    """Store the API token and create a poll token for a submitted task.

    Must run for every HTTP submission (including internal clients) so that
    downstream poll-token checks in progress/results don't fail.

    Returns the poll_token.
    """
    poll_token = secrets.token_urlsafe(32)
    await redis_store.store_task_token(task_id, token)
    await redis_store.store_poll_token(task_id, poll_token)
    return poll_token


async def _submission_ui_json(
    task_id: str,
    total: int,
    poll_token: str,
    mcp_server_url: str = "",
    session_id: str = "",
) -> str:
    """Build JSON for the session MCP App widget."""
    data: dict[str, Any] = {
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
            base_url=settings.futuresearch_api_url,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            await client.post(f"/tasks/{task_id}/summaries/start")
    except Exception:
        logger.debug("Failed to start headless summarizer for %s", task_id)


async def create_tool_response(
    *,
    task_id: str,
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
    text = _submission_text(label, task_id, session_id=session_id)
    main_content = TextContent(type="text", text=text)
    if not is_internal_client():
        # Start headless summarizer so external clients (stdio and HTTP)
        # get progress summaries without needing a frontend SSE connection.
        await _start_headless_summarizer(task_id, token)
    if settings.is_http:
        poll_token = await _record_task_ownership(task_id, token)
        if not is_internal_client():
            ui_json = await _submission_ui_json(
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
    """Format summaries as text lines with row index prefixes.

    Accepts both raw (K duplicates from Engine) and already-deduped
    summaries (with ``row_indices`` lists from ``dedupe_summaries``).
    """
    # Dedupe only if input lacks row_indices (raw from Engine)
    if summaries and "row_indices" not in summaries[0]:
        summaries = dedupe_summaries(summaries)
    lines = ""
    for entry in summaries:
        text = entry.get("summary", "")
        rows = entry.get("row_indices") or []
        if rows:
            label = "Row" if len(rows) == 1 else "Rows"
            prefix = f"[{label} {', '.join(str(r) for r in rows)}] "
        else:
            prefix = ""
        lines += f"\n- {prefix}{text}"
    return lines


def dedupe_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate summaries from batched agents into one per unique text.

    The Engine returns K identical summaries (one per row) when a batched
    agent handles K rows.  This merges them into a single entry with a
    ``row_indices`` list, preserving order.
    """
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for s in summaries:
        text = s.get("summary", "")
        if text not in grouped:
            grouped[text] = {**s, "row_indices": []}
            order.append(text)
        row_idx = s.get("row_index")
        if row_idx is not None:
            grouped[text]["row_indices"].append(row_idx)
    result = []
    for text in order:
        entry = grouped[text]
        indices = sorted(entry["row_indices"])
        entry["row_indices"] = indices or None
        entry.pop("row_index", None)
        if indices:
            entry["row_index"] = indices[0]
        result.append(entry)
    return result


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
    def pool_size(self) -> int | None:
        return self._response.additional_properties.get("pool_size")

    @computed_field
    @property
    def active_workers(self) -> int | None:
        return self._response.additional_properties.get("active_workers")

    @computed_field
    @property
    def user_active_workers(self) -> int | None:
        return self._response.additional_properties.get("user_active_workers")

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

    def progress_message(
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
                    page_size = min(self.total, settings.auto_page_size_threshold)
                    next_call = dedent(f"""\
                        Call futuresearch_results(task_id='{task_id}', page_size={max(page_size, 1)}) to load the first rows.\
                         After reviewing the results, ask the user what they'd like to do next — remind them that this output can be used as input to another operation.""")
                else:
                    next_call = f"Call futuresearch_results(task_id='{task_id}', output_path='<choose_a_path>.csv') to save the output."
                if self.artifact_id:
                    completed_msg += f"\nOutput artifact_id: {self.artifact_id}"
                return f"{completed_msg}\n{next_call}"
            return f"Task {self.status.value}. Report the error to the user."

        fail_part = f", {self.failed} failed" if self.failed else ""
        pool_part = (
            f", pool_size {self.pool_size}" if self.pool_size is not None else ""
        )
        aw_part = (
            f", active_workers {self.active_workers}"
            if self.active_workers is not None
            else ""
        )
        uaw_part = (
            f", user_active_workers {self.user_active_workers}"
            if self.user_active_workers is not None
            else ""
        )
        cursor_arg = f", cursor='{cursor}'" if cursor else ""
        msg = dedent(f"""\
            Running: {self.completed}/{self.total} complete, {self.running} running{fail_part}{pool_part}{aw_part}{uaw_part} ({self.elapsed_s}s elapsed)""")

        if summaries:
            msg += "\n\nAgent activity:" + _format_summary_lines(summaries)

        if partial_rows:
            _skip = {
                "_source_bank",
                "_row_index",
                "_status",
                "_completed_at",
                "_error",
                "_expand_index",
                "research",
                "provenance_and_notes",
            }
            msg += "\n\nNewly completed rows:"
            for row in partial_rows:
                light = {k: v for k, v in row.items() if k not in _skip}
                msg += f"\n- {json.dumps(light, default=str)}"

        progress_call = f"futuresearch_progress(task_id='{task_id}'{cursor_arg})"

        if partial_rows or summaries:
            msg += f"\n\nProduce a concise, meaningful update: highlight any interesting findings, patterns, or notable values from the new rows and agent activity above. Then immediately call {progress_call}."
        else:
            msg += f"\nImmediately call {progress_call}."

        return msg


class TaskNotReady(Exception):
    """Raised when a task is not in a terminal state."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


async def _fetch_task_result(
    client: Any,
    task_id: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int, str, str]:
    """Fetch a task's result rows, total count, session ID, and artifact ID.

    When ``offset``/``limit`` are provided, uses the Engine's paginated
    ClickHouse path which returns citation-resolved, metadata-stripped rows
    and an ``X-Total-Row-Count`` header.

    When they are ``None``, fetches all rows via the existing Supabase path.

    Returns:
        Tuple of (rows, total_count, session_id, artifact_id).

    Raises:
        TaskNotReady: If the task is not in a terminal state.
        ValueError: If the result has no table data.
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

    # When offset/limit are provided, use the paginated parquet path.
    # Otherwise, use the Supabase path which resolves citations via
    # per-child render_citations (parquet doesn't have source_bank).
    params: dict[str, int] = {}
    if offset is not None and limit is not None:
        params["offset"] = offset
        params["limit"] = limit

    httpx_client = client.get_async_httpx_client()
    resp = await httpx_client.request(
        method="get",
        url=f"/tasks/{task_id}/result",
        params=params if params else None,
    )
    if resp.status_code != 200:
        raise ValueError(f"Engine returned {resp.status_code} for result: {resp.text}")
    body = resp.json()
    total_from_header = resp.headers.get("X-Total-Row-Count")
    data = body.get("data")
    artifact_id = body.get("artifact_id") or ""

    if isinstance(data, list):
        total_count = int(total_from_header) if total_from_header else len(data)
        return data, total_count, session_id, artifact_id
    if isinstance(data, dict):
        total_count = int(total_from_header) if total_from_header else 1
        return [data], total_count, session_id, artifact_id
    raise ValueError("Task result has no table data.")

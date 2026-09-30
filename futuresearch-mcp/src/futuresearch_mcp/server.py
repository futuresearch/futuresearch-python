"""MCP server for futuresearch SDK operations.

Supports both stdio and HTTP transport modes.
"""

import argparse
import logging
import os
import sys
from textwrap import dedent

import httpx
import sentry_sdk
from pydantic import BaseModel

import futuresearch_mcp.tools  # noqa: F401  — registers @mcp.tool() decorators
from futuresearch_mcp.app import get_instructions, mcp
from futuresearch_mcp.config import settings
from futuresearch_mcp.http_config import configure_http_mode
from futuresearch_mcp.redis_store import Transport
from futuresearch_mcp.tools import (
    _RESULTS_ANNOTATIONS,
    futuresearch_results_http,
)
from futuresearch_mcp.uploads import register_upload_tool


class InputArgs(BaseModel):
    http: bool = False
    no_auth: bool = False
    port: int = 8000
    host: str = "0.0.0.0"


def parse_args() -> InputArgs:
    parser = argparse.ArgumentParser(description="futuresearch MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use Streamable HTTP transport instead of stdio.",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable OAuth (dev only). Requires FUTURESEARCH_API_KEY.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transport (default: 0.0.0.0).",
    )
    raw_args = parser.parse_args()
    host_was_explicit = any(a == "--host" or a.startswith("--host=") for a in sys.argv)
    input_args = InputArgs.model_validate(vars(raw_args))

    if input_args.no_auth and not input_args.http:
        parser.error("--no-auth requires --http")

    if input_args.no_auth and os.environ.get("ALLOW_NO_AUTH") != "1":
        print(
            dedent("""ERROR: --no-auth requires the ALLOW_NO_AUTH=1 environment variable.\n
            This prevents accidental unauthenticated deployments in production."""),
            file=sys.stderr,
        )
        sys.exit(1)

    # Default to localhost in --no-auth mode to avoid exposing on all interfaces.
    # Skip if the user explicitly passed --host (e.g. in a container).
    if input_args.no_auth and not host_was_explicit:
        input_args.host = "127.0.0.1"

    return input_args


# Marker(s) for transport drops that reach Sentry as a *log* line rather than a
# raised exception (mcp's streamable-HTTP transport logs "Received exception
# from stream" when a client vanishes mid-response). Those records may arrive
# without ``exc_info`` in the hint, so we also recognise them by message.
_TRANSIENT_TRANSPORT_MESSAGE_MARKERS = ("Received exception from stream",)


def _transient_transport_types() -> tuple[type[BaseException], ...]:
    """Exception classes for transient transport drops (client hung up / a
    closed stream was torn down). Imports are lazy and guarded so a
    missing/renamed dependency can never break error reporting at init time —
    same idiom as cohort-engine's ``_classify_exception``.

    ``httpx.TransportError`` (already a dependency) covers the
    RemoteProtocolError/ReadError/ConnectError family the mcp stream wraps and
    fs-mcp's own upstream (Supabase) blips; anyio's ``ClosedResourceError`` /
    ``BrokenResourceError`` and starlette's ``ClientDisconnect`` cover the
    mid-stream client disconnects (FS-MCP-8 and siblings).
    """
    types: tuple[type[BaseException], ...] = (httpx.TransportError,)
    try:
        from anyio import BrokenResourceError, ClosedResourceError  # noqa: PLC0415

        types += (ClosedResourceError, BrokenResourceError)
    except ImportError:
        pass
    try:
        from starlette.requests import ClientDisconnect  # noqa: PLC0415

        types += (ClientDisconnect,)
    except ImportError:
        pass
    return types


def _leaf_exceptions(exc: BaseException) -> list[BaseException]:
    """Flatten an ``ExceptionGroup`` to its non-group leaves.

    anyio task groups (which back the streamable-HTTP transport) surface child
    failures as an ``ExceptionGroup``, so the real transport error lives on the
    leaves, not the wrapper. A plain exception is returned as a single-item list.
    """
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(_leaf_exceptions(sub))
        return leaves
    return [exc]


def _is_transient_transport(exc: BaseException) -> bool:
    """True only when EVERY leaf of ``exc`` is a recognised transport drop.

    Requiring all leaves preserves default-to-page: a real bug bundled into the
    same ``ExceptionGroup`` as a transport blip still pages.
    """
    transient = _transient_transport_types()
    leaves = _leaf_exceptions(exc)
    return bool(leaves) and all(isinstance(leaf, transient) for leaf in leaves)


def _event_mentions_transient(event) -> bool:
    """Match a transport drop that was only *logged* (no ``exc_info`` in hint).

    The mcp transport's "Received exception from stream" record arrives as a
    logentry, not a raised exception, so class-based matching can't see it.
    Match the serialized message instead so it can rate-gate too. Only ever used
    to downgrade (never drop), so a coincidental substring match is harmless.
    """
    parts = [str(event.get("message") or "")]
    logentry = event.get("logentry") or {}
    parts.append(str(logentry.get("message") or ""))
    parts.append(str(logentry.get("formatted") or ""))
    haystack = " ".join(parts)
    return any(m in haystack for m in _TRANSIENT_TRANSPORT_MESSAGE_MARKERS)


def _sentry_before_send(event, hint):
    """Classify expected fs-mcp errors so the Sentry alert rule can rate-gate.

    Default-to-page: we NEVER drop an event and touch only the categories
    we've explicitly recognised as expected. Everything else passes through
    untouched and keeps paging, so a real bug still fires. The actual
    page-vs-rate routing is a Sentry UI alert-rule change keyed on the
    level/tag, NOT here.

    Recognised cases:

    * The expected Supabase ``/auth/v1/token?grant_type=refresh_token`` **400**
      (user's stored refresh token expired/rotated — they just re-authenticate,
      FS-MCP-1): downgrade to ``warning`` + ``error_category=user_input``.
    * Transient transport drops — a client hung up mid-stream, or anyio/httpx
      tore down a closed stream (FS-MCP-8 ``ClosedResourceError`` ~333 events
      since March, ``ClientDisconnect``, "Received exception from stream"):
      downgrade to ``warning`` + ``error_category=infra``. Self-recovering and
      not user-facing, so they should rate-alert, not page per occurrence.
    """
    # Wrapped defensively: a before_send that raises drops the event entirely,
    # so any unexpected shape must fall through and page as before.
    try:
        exc_info = hint.get("exc_info")
        exc = exc_info[1] if exc_info else None

        # (1) Expected Supabase refresh-token 400 -> user_input (FS-MCP-1).
        if (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code == 400
            and "/auth/v1/token" in str(exc.request.url)
            and "grant_type=refresh_token" in str(exc.request.url)
        ):
            event["level"] = "warning"
            event.setdefault("tags", {})["error_category"] = "user_input"
            return event

        # (2) Transient transport drops -> infra (FS-MCP-8 and siblings).
        # Recognise them from the raised/logged exception, or — when a transport
        # drop is only logged without exc_info — from the event message.
        if (exc is not None and _is_transient_transport(exc)) or (
            _event_mentions_transient(event)
        ):
            event["level"] = "warning"
            event.setdefault("tags", {})["error_category"] = "infra"
    except Exception:
        pass
    return event


def configure_tools_for_transport(transport: Transport) -> None:
    """Make the instructions and the tool registry what a client of this transport
    is given. ``main`` calls it; so does the everyrow-cc eval harness, which serves
    a stub of the HTTP registry and must not drift from it. The upload tool is
    registered separately (``register_upload_tool``) because it needs the server URL.
    """
    settings.transport = transport.value
    mcp._mcp_server.instructions = get_instructions(is_http=transport == Transport.HTTP)

    # The widget tools are only useful to widget-capable clients (HTTP mode).
    # Remove them in stdio mode so Claude Code never sees them.
    if transport != Transport.HTTP:
        mcp._tool_manager.remove_tool("futuresearch_status")
        mcp._tool_manager.remove_tool("futuresearch_task_data")
        mcp._tool_manager.remove_tool("futuresearch_task_download")

    # tools.py registers futuresearch_results_stdio by default.
    # Override with the HTTP variant when running in HTTP mode.
    # ToolManager.add_tool() is a no-op for existing names, so remove first.
    if transport == Transport.HTTP:
        mcp._tool_manager.remove_tool("futuresearch_results")
        mcp.tool(
            name="futuresearch_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
        )(futuresearch_results_http)


def main():
    """Run the MCP server."""
    input_args = parse_args()

    sentry_dsn = os.environ.get("SENTRY_DSN", "")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            send_default_pii=True,
            traces_sample_rate=0.1,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("SENTRY_RELEASE"),
            before_send=_sentry_before_send,
        )

    transport = Transport.HTTP if input_args.http else Transport.STDIO
    configure_tools_for_transport(transport)

    if input_args.http:
        # ── HTTP mode logging ──────────────────────────────────────
        # INFO level so operational events show up in Cloud Logging.
        # Format is plain-text; Cloud Logging parses the severity from
        # the levelname field automatically.
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            force=True,
        )
        # Suppress uvicorn's built-in access logger — our
        # _RequestLoggingMiddleware provides richer per-request logs.
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

        if input_args.no_auth:
            mcp_server_url = f"http://localhost:{input_args.port}"
        else:
            mcp_server_url = settings.mcp_server_url

        sandbox_url = settings.mcp_sandbox_url or mcp_server_url
        register_upload_tool(mcp, sandbox_url)

        configure_http_mode(
            mcp=mcp,
            host=input_args.host,
            port=input_args.port,
            no_auth=input_args.no_auth,
            mcp_server_url=mcp_server_url,
        )
    else:
        # Configure logging to use stderr only (stdout is reserved for JSON-RPC)
        logging.basicConfig(
            level=logging.WARNING,
            stream=sys.stderr,
            format="%(levelname)s: %(message)s",
            force=True,
        )

        # Validate FUTURESEARCH_API_KEY is set
        if not os.environ.get("FUTURESEARCH_API_KEY"):
            logging.error("Configuration error: FUTURESEARCH_API_KEY is required")
            logging.error("Get an API key at https://futuresearch.ai/app/api-key")
            sys.exit(1)

    mcp.run(transport=transport.value)


if __name__ == "__main__":
    main()

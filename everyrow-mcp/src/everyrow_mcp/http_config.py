"""HTTP mode configuration for the everyrow MCP server."""

from __future__ import annotations

import contextvars
import logging
import time as _time
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import lifespan_wrapper
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from everyrow_mcp.app import http_lifespan, no_auth_http_lifespan
from everyrow_mcp.auth import EveryRowAuthProvider, SupabaseTokenVerifier
from everyrow_mcp.config import settings
from everyrow_mcp.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from everyrow_mcp.redis_store import get_redis_client
from everyrow_mcp.routes import api_download, api_download_token, api_progress
from everyrow_mcp.templates import RESULTS_HTML, SESSION_HTML
from everyrow_mcp.uploads import handle_upload

logger = logging.getLogger(__name__)

# ── User-Agent propagation ────────────────────────────────────────────
# In stateless HTTP mode there is no MCP initialize handshake, so
# ctx.session.client_params is always None.  We propagate the HTTP
# User-Agent header via a ContextVar so tool functions can still
# distinguish clients (e.g. Claude Code vs Claude.ai).
_user_agent_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_agent", default=""
)


def get_user_agent() -> str:
    """Return the User-Agent of the current HTTP request (empty in stdio mode)."""
    return _user_agent_var.get()


def configure_http_mode(
    *,
    mcp: FastMCP,
    host: str,
    port: int,
    no_auth: bool,
    mcp_server_url: str,
) -> None:
    """Configure the MCP server for HTTP transport."""
    if not no_auth:
        missing = []
        if not settings.supabase_url:
            missing.append("SUPABASE_URL")
        if not settings.supabase_anon_key:
            missing.append("SUPABASE_ANON_KEY")
        if not settings.mcp_server_url:
            missing.append("MCP_SERVER_URL")
        if missing:
            raise RuntimeError(
                f"HTTP auth mode requires these environment variables: {', '.join(missing)}"
            )

    redis_client = get_redis_client()
    auth_provider: EveryRowAuthProvider | None = None
    if no_auth:
        lifespan = no_auth_http_lifespan
    else:
        lifespan = http_lifespan
        verifier = SupabaseTokenVerifier(settings.supabase_url, redis=redis_client)
        auth_provider = EveryRowAuthProvider(
            redis=redis_client,
            token_verifier=verifier,
        )
        _configure_mcp_auth(mcp, auth_provider, verifier)

    mcp._mcp_server.lifespan = lifespan_wrapper(mcp, lifespan)
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.stateless_http = True

    if not settings.upload_secret or len(settings.upload_secret) < 32:
        raise RuntimeError(
            "UPLOAD_SECRET must be at least 32 characters in HTTP mode for HMAC signing. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if not no_auth and not settings.redis_password:
        raise RuntimeError(
            "REDIS_PASSWORD is not set — Redis is unauthenticated. "
            "Set REDIS_PASSWORD for production deployments."
        )
    if no_auth and not settings.redis_password:
        logger.warning(
            "REDIS_PASSWORD is not set — acceptable for local development only."
        )

    _register_widgets(mcp, mcp_server_url)
    _register_routes(mcp, redis_client, auth_provider if not no_auth else None)
    _add_middleware(mcp, redis_client)


def _register_widgets(mcp: FastMCP, mcp_server_url: str) -> None:
    """Register MCP App widget resources for HTTP mode."""
    widget_csp = _ui_csp([mcp_server_url])

    @mcp.resource(
        "ui://everyrow/session.html",
        mime_type="text/html;profile=mcp-app",
        meta={"ui": {"csp": widget_csp}},
    )
    def _session_ui_http() -> str:
        return SESSION_HTML

    @mcp.resource(
        "ui://everyrow/results.html",
        mime_type="text/html;profile=mcp-app",
        meta={"ui": {"csp": widget_csp}},
    )
    def _results_ui_http() -> str:
        return RESULTS_HTML


def _register_routes(
    mcp: FastMCP,
    redis: Redis,
    auth_provider: EveryRowAuthProvider | None,
) -> None:
    """Register REST endpoints for widget polling, CSV download, health, and auth."""
    mcp.custom_route("/api/progress/{task_id}", ["GET", "OPTIONS"])(api_progress)
    mcp.custom_route("/api/results/{task_id}/download", ["GET", "OPTIONS"])(
        api_download
    )
    mcp.custom_route("/api/results/{task_id}/download-token", ["GET", "OPTIONS"])(
        api_download_token
    )
    mcp.custom_route("/api/uploads/{upload_id}", ["PUT"])(handle_upload)

    async def _health(_request: Request) -> Response:
        try:
            await redis.ping()  # pyright: ignore[reportGeneralTypeIssues]
        except Exception:
            return JSONResponse(
                {"status": "unhealthy", "redis": "unreachable"}, status_code=503
            )
        return JSONResponse({"status": "ok"})

    mcp.custom_route("/health", ["GET"])(_health)

    if auth_provider is not None:
        mcp.custom_route("/auth/start/{state}", ["GET"])(auth_provider.handle_start)
        mcp.custom_route("/auth/callback", ["GET"])(auth_provider.handle_callback)


def _configure_mcp_auth(
    mcp: FastMCP,
    auth_provider: EveryRowAuthProvider,
    verifier: SupabaseTokenVerifier,
) -> None:
    """Wire OAuth provider and JWT verifier into FastMCP."""
    mcp._auth_server_provider = auth_provider  # type: ignore[arg-type]
    mcp._token_verifier = verifier
    mcp.settings.auth = AuthSettings(
        issuer_url=AnyHttpUrl(settings.mcp_server_url),
        resource_server_url=AnyHttpUrl(settings.mcp_server_url),
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
    hostname = urlparse(settings.mcp_server_url).hostname or "localhost"
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[hostname],
    )


def _ui_csp(connect_domains: list[str]) -> dict[str, str | list[str]]:
    """Build a CSP policy for MCP App widgets."""
    return {
        "resourceDomains": ["https://unpkg.com"],
        "connectDomains": connect_domains,
    }


class _RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log inbound requests at INFO level with method, path, status, and timing."""

    async def dispatch(self, request, call_next):
        # Skip health check requests — k8s probes hit these every ~10s.
        if request.url.path == "/health":
            return await call_next(request)

        # Propagate User-Agent so downstream tool code can detect the client
        # even in stateless HTTP mode (no MCP initialize → no client_params).
        ua_token = _user_agent_var.set(request.headers.get("user-agent", ""))
        try:
            start = _time.monotonic()
            response = await call_next(request)
            elapsed_ms = (_time.monotonic() - start) * 1000

            # Extract user_id from the access token if available.
            try:
                access_token = get_access_token()
                user_id = access_token.client_id if access_token else None
            except Exception:
                user_id = None

            logger.info(
                "HTTP %s %s -> %d (%.0fms) user=%s ua=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                user_id or "anon",
                request.headers.get("user-agent", "-"),
            )
            return response
        finally:
            _user_agent_var.reset(ua_token)


def _add_middleware(
    mcp: FastMCP,
    redis_client: Redis,
) -> None:
    """Wrap the ASGI app with request logging, rate limiting, and security headers."""
    _original = mcp.streamable_http_app

    def _wrapped():
        app = _original()
        app.add_middleware(RateLimitMiddleware, redis=redis_client)
        app.add_middleware(_RequestLoggingMiddleware)
        # Pure-ASGI middlewares — outermost wraps first.
        # SecurityHeaders → BodySizeLimit → Starlette app
        asgi_app = BodySizeLimitMiddleware(
            app, max_bytes=settings.max_upload_size_bytes
        )
        asgi_app = SecurityHeadersMiddleware(asgi_app)
        return asgi_app

    mcp.streamable_http_app = _wrapped  # pyright: ignore[reportAttributeAccessIssue]

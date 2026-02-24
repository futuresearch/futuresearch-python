"""HTTP mode configuration for the everyrow MCP server."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

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
from everyrow_mcp.middleware import RateLimitMiddleware
from everyrow_mcp.redis_store import get_redis_client
from everyrow_mcp.routes import api_download, api_progress
from everyrow_mcp.templates import RESULTS_HTML, SESSION_HTML

logger = logging.getLogger(__name__)


def configure_http_mode(
    *,
    mcp: FastMCP,
    host: str,
    port: int,
    no_auth: bool,
    mcp_server_url: str,
) -> None:
    """Configure the MCP server for HTTP transport."""
    redis_client = get_redis_client()
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

    _register_widgets(mcp, mcp_server_url)
    _register_routes(mcp, auth_provider if not no_auth else None)
    _add_middleware(mcp, redis_client, rate_limit=not no_auth)


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
    auth_provider: EveryRowAuthProvider | None,
) -> None:
    """Register REST endpoints for widget polling, CSV download, health, and auth."""
    mcp.custom_route("/api/progress/{task_id}", ["GET", "OPTIONS"])(api_progress)
    mcp.custom_route("/api/results/{task_id}/download", ["GET", "OPTIONS"])(
        api_download
    )

    async def _health(_request: Request) -> Response:
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
    """Log every inbound request and its response status at DEBUG level."""

    async def dispatch(self, request, call_next):
        has_auth = "authorization" in request.headers
        logger.debug(
            "INCOMING %s %s | Host: %s | Auth: %s",
            request.method,
            request.url.path,
            request.headers.get("host", "?"),
            "present" if has_auth else "none",
        )
        response = await call_next(request)
        logger.debug(
            "RESPONSE %s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


def _add_middleware(
    mcp: FastMCP,
    redis_client: Redis,
    *,
    rate_limit: bool = True,
) -> None:
    """Wrap the ASGI app with request logging and optional rate limiting."""
    _original = mcp.streamable_http_app

    def _wrapped():
        app = _original()
        if rate_limit:
            app.add_middleware(RateLimitMiddleware, redis=redis_client)
        app.add_middleware(_RequestLoggingMiddleware)
        return app

    mcp.streamable_http_app = _wrapped

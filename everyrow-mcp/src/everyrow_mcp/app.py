"""FastMCP application instance, lifespans, and resource handlers."""

import logging
from contextlib import asynccontextmanager

from everyrow.api_utils import create_client as _create_sdk_client
from everyrow.generated.api.billing.get_billing_balance_billing_get import (
    asyncio as get_billing,
)
from everyrow.generated.client import AuthenticatedClient
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP

from everyrow_mcp.config import settings
from everyrow_mcp.redis_store import TASK_STATE_FILE, get_redis_client
from everyrow_mcp.tool_helpers import SessionContext


def _clear_task_state() -> None:
    if TASK_STATE_FILE.exists():
        TASK_STATE_FILE.unlink()


@asynccontextmanager
async def stdio_lifespan(_server: FastMCP):
    """Initialize singleton client and validate credentials on startup (stdio mode)."""
    _clear_task_state()

    try:
        with _create_sdk_client() as client:
            response = await get_billing(client=client)
            if response is None:
                raise RuntimeError("Failed to authenticate with everyrow API")
            yield SessionContext(client_factory=lambda: client)
    except Exception as e:
        logging.getLogger(__name__).error(f"everyrow-mcp startup failed: {e!r}")
        raise
    finally:
        _clear_task_state()


@asynccontextmanager
async def http_lifespan(_server: FastMCP):
    """HTTP mode lifespan — verify Redis on startup.

    NOTE: This runs per MCP *session*, not per server. Do NOT close
    shared resources (auth_provider, Redis) here — they must survive
    across sessions. Process exit handles cleanup.
    """
    redis_client = get_redis_client()
    await redis_client.ping()

    def _http_client_factory() -> AuthenticatedClient:
        access_token = get_access_token()
        if access_token is None:
            raise RuntimeError("Not authenticated")
        return AuthenticatedClient(
            base_url=settings.everyrow_api_url,
            token=access_token.token,
            raise_on_unexpected_status=True,
            follow_redirects=True,
        )

    yield SessionContext(
        client_factory=_http_client_factory,
        mcp_server_url=settings.mcp_server_url,
    )


@asynccontextmanager
async def no_auth_http_lifespan(_server: FastMCP):
    """HTTP no-auth mode: singleton client from API key, verify Redis."""
    redis_client = get_redis_client()
    await redis_client.ping()

    with _create_sdk_client() as client:
        response = await get_billing(client=client)
        if response is None:
            raise RuntimeError("Failed to authenticate with everyrow API")
        yield SessionContext(
            client_factory=lambda: client,
            mcp_server_url=settings.mcp_server_url,
        )


mcp = FastMCP("everyrow_mcp", lifespan=stdio_lifespan)

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
    if settings.is_http:
        return
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
        logging.getLogger(__name__).error("everyrow-mcp startup failed: %r", e)
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
    await redis_client.ping()  # pyright: ignore[reportGeneralTypeIssues]

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
        mcp_server_url=settings.mcp_sandbox_url or settings.mcp_server_url,
    )


@asynccontextmanager
async def no_auth_http_lifespan(_server: FastMCP):
    """HTTP no-auth mode: singleton client from API key, verify Redis."""
    redis_client = get_redis_client()
    await redis_client.ping()  # pyright: ignore[reportGeneralTypeIssues]

    with _create_sdk_client() as client:
        response = await get_billing(client=client)
        if response is None:
            raise RuntimeError("Failed to authenticate with everyrow API")
        yield SessionContext(
            client_factory=lambda: client,
            mcp_server_url=settings.mcp_sandbox_url or settings.mcp_server_url,
        )


_INSTRUCTIONS_COMMON = f"""\
You are connected to the everyrow MCP server. everyrow dispatches web research \
agents that search the internet, read pages, and return structured results for \
every row in a dataset.

## Workflow
1. **Ingest data** — pass `data` (inline list of dicts) or an `artifact_id` \
(from `everyrow_upload_data` or `everyrow_request_upload_url`) to any processing tool.
2. **Submit** — call a processing tool (everyrow_agent, everyrow_screen, \
everyrow_rank, everyrow_dedupe, everyrow_merge, everyrow_forecast). \
It returns a task_id immediately.
3. **Poll** — call `everyrow_progress(task_id)` repeatedly until the task completes. \
Do NOT add commentary between progress calls — just call again immediately.
4. **Results** — call `everyrow_results(task_id)` to retrieve the output.

## Key rules
- Do not share session URLs with the user unless they explicitly ask for one.
- Never guess or fabricate results — always wait for the task to complete.
- For small datasets (<= {settings.auto_page_size_threshold} rows), prefer passing `data` directly.
- For larger datasets, use `everyrow_upload_data` to get an artifact_id first.
"""

_INSTRUCTIONS_STDIO = (
    _INSTRUCTIONS_COMMON
    + """\
## Data ingestion (local mode)
- `everyrow_upload_data(source="/path/to/file.csv")` — upload a local CSV file.
- `everyrow_upload_data(source="https://...")` — upload from a URL (Google Sheets supported).
- Or pass `data=[{"col": "val"}, ...]` directly to any processing tool.

## Results
- `everyrow_results(task_id, output_path="/path/to/output.csv")` saves results as CSV.
"""
)


def _build_instructions_http() -> str:
    threshold = settings.auto_page_size_threshold
    return (
        _INSTRUCTIONS_COMMON
        + f"""\
## Data ingestion (remote mode)
- `everyrow_upload_data(source="https://...")` — upload from a URL (Google Sheets supported).
- For local/sandbox files, use `everyrow_request_upload_url(filename="data.csv")`, \
then execute the returned curl command, then use the artifact_id from the response.
- Or pass `data=[{{"col": "val"}}, ...]` directly to any processing tool.
- Do NOT pass local file paths to `everyrow_upload_data` — it will fail in remote mode.

## Results
- IMPORTANT: When a task completes with more than {threshold} rows, you MUST ask the user how many rows \
they want loaded into your context BEFORE calling everyrow_results. Do NOT call everyrow_results \
without asking first. If the task produced {threshold} or fewer rows, skip asking and load all rows directly.
- `everyrow_results(task_id, page_size=N)` loads N rows into your context so you can read them. \
The user always has access to all rows via the widget and download link.
- After retrieving results, tell the user how many rows you can see vs the total, and that \
they have access to the full dataset via the widget above and the download link.
- Use offset to paginate through larger datasets.
"""
    )


def get_instructions(is_http: bool) -> str:
    """Return server instructions appropriate for the transport mode."""
    return _build_instructions_http() if is_http else _INSTRUCTIONS_STDIO


mcp = FastMCP(
    "everyrow_mcp",
    instructions=_INSTRUCTIONS_STDIO,
    lifespan=stdio_lifespan,
)

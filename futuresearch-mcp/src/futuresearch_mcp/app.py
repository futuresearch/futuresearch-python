"""FastMCP application instance, lifespans, and resource handlers."""

import logging
from contextlib import asynccontextmanager

from futuresearch.api_utils import create_client as _create_sdk_client
from futuresearch.generated.api.billing.get_billing_balance_billing_get import (
    asyncio as get_billing,
)
from futuresearch.generated.client import AuthenticatedClient
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP

from futuresearch_mcp.config import settings
from futuresearch_mcp.redis_store import get_redis_client
from futuresearch_mcp.tool_helpers import SessionContext


@asynccontextmanager
async def stdio_lifespan(_server: FastMCP):
    """Initialize singleton client and validate credentials on startup (stdio mode)."""
    try:
        with _create_sdk_client() as client:
            response = await get_billing(client=client)
            if response is None:
                raise RuntimeError("Failed to authenticate with futuresearch API")
            yield SessionContext(client_factory=lambda: client)
    except Exception as e:
        logging.getLogger(__name__).error("futuresearch-mcp startup failed: %r", e)
        raise


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
            base_url=settings.futuresearch_api_url,
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
            raise RuntimeError("Failed to authenticate with futuresearch API")
        yield SessionContext(
            client_factory=lambda: client,
            mcp_server_url=settings.mcp_sandbox_url or settings.mcp_server_url,
        )


_INSTRUCTIONS_COMMON = f"""\
You are connected to the futuresearch MCP server. FutureSearch dispatches web research \
agents that search the internet, read pages, and return structured results for \
every row in a dataset.

## Getting data

Most operations need an input dataset. If the user provides a CSV, start from that. \
Otherwise, help them find one:

1. **Built-in lists** — check `futuresearch_browse_lists` first (fast and free). \
Call with no filters to see all available lists. Many analyses start from one of these.
2. **URLs** — upload from a URL or Google Sheet via `futuresearch_upload_data`.
3. **From memory** — if you know a good starting list, generate it as inline `data`.
4. **single_agent** — dispatch a research agent to find or build a list. \
Works well but slow (3-5 min), so prefer the options above.

## Choosing the right operation

1. **Forecast** — questions about the future. Best prediction accuracy.
2. **Classify** — binary yes/no or categorical labels (up to ~20 categories). \
More efficient than open-ended research for categorical answers.
3. **Rank** — quantitative rating. Prefer an objective metric with units when possible. \
Use a subjective 0-100 score only if necessary.
4. **Agent** — open-ended web research when Classify, Rank, and Forecast don't fit. \
Specify a response schema with descriptive column names (include units, e.g. \
`population_millions`). Don't add reasoning/justification fields — users can \
inspect the research behind each row.
5. **Dedupe / Merge** — data consolidation.

## Workflow
1. **Ingest data** — pass `data` (inline list of dicts) or an `artifact_id` \
(from `futuresearch_upload_data` or `futuresearch_request_upload_url`) to any processing tool.
2. **Submit** — call a processing tool (futuresearch_agent, futuresearch_classify, \
futuresearch_rank, futuresearch_dedupe, futuresearch_merge, futuresearch_forecast). \
It returns a task_id immediately.
3. **Poll** — call `futuresearch_progress(task_id)` repeatedly until the task completes. \
Do NOT add commentary between progress calls — just call again immediately.
4. **Results** — call `futuresearch_results(task_id)` to retrieve the output.

## Session and artifact reuse

Every operation creates a session. After your first operation or upload, **always pass \
the returned `session_id`** to subsequent operations to keep tasks grouped. You may \
pass `session_id` together with `session_name` — the session is resumed and renamed \
to the given name. When an operation completes, its `artifact_id` can be passed \
directly to the next operation instead of re-uploading data.

## Key rules
- Be concise. Keep summaries to 1-2 sentences. Do not output markdown tables, \
bullet lists of data rows, JSON, or CSV in chat — the user can see results \
directly. Only render a table if the user explicitly asks for one.
- Never guess or fabricate results — always wait for the task to complete.
- For small datasets (<= {settings.auto_page_size_threshold} rows), prefer passing `data` directly.
- For larger datasets, use `futuresearch_upload_data` to get an artifact_id first.
- After presenting results, mention that the output can be used as input to another \
operation (e.g. classify then rank, upload then forecast).
"""

_INSTRUCTIONS_STDIO = (
    _INSTRUCTIONS_COMMON
    + """\
## Data ingestion (local mode)
- `futuresearch_upload_data(source="/path/to/file.csv")` — upload a local CSV file.
- `futuresearch_upload_data(source="https://...")` — upload from a URL (Google Sheets supported).
- Or pass `data=[{"col": "val"}, ...]` directly to any processing tool.

## Results
- `futuresearch_results(task_id, output_path="/path/to/output.csv")` saves results as CSV.
"""
)


def _build_instructions_http() -> str:
    threshold = settings.auto_page_size_threshold
    return (
        _INSTRUCTIONS_COMMON
        + f"""\
## Data ingestion (remote mode)
- `futuresearch_upload_data(source="https://...")` — upload from a URL (Google Sheets supported).
- For local/sandbox files, use `futuresearch_request_upload_url(filename="data.csv")`, \
then execute the returned curl command, then use the artifact_id from the response.
- Or pass `data=[{{"col": "val"}}, ...]` directly to any processing tool.
- Do NOT pass local file paths to `futuresearch_upload_data` — it will fail in remote mode.

## Results
- Always call `futuresearch_results(task_id, page_size=N)` immediately when the task completes. \
For small tasks ({threshold} or fewer rows), set page_size to the total. \
For larger tasks, set page_size to {threshold} to load the first batch.
- The user always has access to all rows via the table view and download link.
- After reviewing the loaded results, ask the user what they'd like to do next. \
Remind them that this output can be used as input to another operation (e.g. further enrichment, filtering, ranking).
- Use offset to paginate through larger datasets if the user wants to see more.
"""
    )


def get_instructions(is_http: bool) -> str:
    """Return server instructions appropriate for the transport mode."""
    return _build_instructions_http() if is_http else _INSTRUCTIONS_STDIO


mcp = FastMCP(
    "futuresearch_mcp",
    instructions=_INSTRUCTIONS_STDIO,
    lifespan=stdio_lifespan,
)

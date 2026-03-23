"""REST endpoints for the futuresearch MCP server (progress polling)."""

from __future__ import annotations

import csv
import json
import logging
import secrets
from uuid import UUID

import httpx
import pandas as pd
from futuresearch.api_utils import handle_response
from futuresearch.generated.api.tasks import get_task_status_tasks_task_id_status_get
from futuresearch.generated.client import AuthenticatedClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from futuresearch_mcp import redis_store
from futuresearch_mcp.config import settings
from futuresearch_mcp.tool_helpers import _UI_EXCLUDE, TaskState

logger = logging.getLogger(__name__)


def _cors_headers() -> dict[str, str]:
    """CORS headers for widget endpoints.

    MCP App widgets run in sandboxed iframes whose origin will never match
    the server's own URL.  Because auth is via Bearer tokens (not cookies),
    a wildcard origin is safe — no ambient credentials are leaked.
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET",
        "Access-Control-Allow-Headers": "Authorization",
    }


def _validate_uuid(task_id: str) -> JSONResponse | None:
    """Return a 400 response if task_id is not a valid UUID, else None."""
    try:
        UUID(task_id)
    except ValueError:
        return JSONResponse(
            {"error": "Invalid task ID"},
            status_code=400,
            headers=_cors_headers(),
        )
    return None


def _extract_bearer_or_query_token(request: Request, task_id: str) -> str:
    """Extract a poll token from Authorization header or ?token= query param."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]
    provided = request.query_params.get("token", "")
    if provided:
        logger.info(
            "Poll token provided via query param for task %s — prefer Authorization header",
            task_id,
        )
    return provided


async def _validate_poll_token(task_id: str, request: Request) -> JSONResponse | None:
    """Return an error response if the poll token is missing/invalid, else None.

    Checks Authorization: Bearer header first, falls back to ?token= query
    param (for clickable CSV download links).  Non-destructive — the token
    remains in Redis for repeated progress polling.
    """
    expected = await redis_store.get_poll_token(task_id)
    provided = _extract_bearer_or_query_token(request, task_id)
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        logger.warning("Invalid poll token for task %s", task_id)
        return JSONResponse(
            {"error": "Unauthorized"}, status_code=403, headers=_cors_headers()
        )
    return None


async def api_progress(request: Request) -> Response:
    """REST endpoint for the session widget to poll task progress."""
    cors = _cors_headers()
    if request.method == "OPTIONS":
        return Response(
            status_code=204,
            headers={**cors, "Access-Control-Max-Age": "3600"},
        )

    task_id = request.path_params["task_id"]

    if err := _validate_uuid(task_id):
        return err

    if err := await _validate_poll_token(task_id, request):
        return err

    api_key = await redis_store.get_task_token(task_id)

    if not api_key:
        return JSONResponse({"error": "Unknown task"}, status_code=404, headers=cors)

    try:
        client = AuthenticatedClient(
            base_url=settings.futuresearch_api_url,
            token=api_key,
            raise_on_unexpected_status=True,
            follow_redirects=True,
        )
        status_response = handle_response(
            await get_task_status_tasks_task_id_status_get.asyncio(
                task_id=UUID(task_id),
                client=client,
            )
        )

        ts = TaskState(status_response)

        # Don't pop the token on completion — the download route needs it.
        # Let the Redis TTL expire it naturally.

        return JSONResponse(
            ts.model_dump(mode="json", exclude=_UI_EXCLUDE), headers=cors
        )
    except Exception as exc:
        logger.error(
            "Progress poll failed for task %s: %s", task_id, type(exc).__name__
        )
        return JSONResponse(
            {"error": "Internal server error"}, status_code=500, headers=cors
        )


async def _validate_poll_token_bearer_only(
    task_id: str, request: Request
) -> JSONResponse | None:
    """Validate poll token from Authorization header only (no query params).

    Used for API endpoints where query-param auth is inappropriate
    (e.g. token minting — the poll token must not leak into URLs).
    """
    expected = await redis_store.get_poll_token(task_id)
    auth_header = request.headers.get("authorization", "")
    provided = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        logger.warning("Invalid poll token (bearer-only) for task %s", task_id)
        return JSONResponse(
            {"error": "Unauthorized"}, status_code=403, headers=_cors_headers()
        )
    return None


async def api_download_url(request: Request) -> Response:
    """Return the download URL for a task.

    The widget calls this to get the download URL. Validates the poll
    token so only the session owner gets the URL (the download itself
    is open by task ID).
    """
    cors = _cors_headers()
    if request.method == "OPTIONS":
        return Response(
            status_code=204,
            headers={**cors, "Access-Control-Max-Age": "3600"},
        )

    task_id = request.path_params["task_id"]

    if err := _validate_uuid(task_id):
        return err

    if err := await _validate_poll_token_bearer_only(task_id, request):
        return err

    download_url = f"{settings.mcp_server_url}/api/results/{task_id}/download"
    return JSONResponse({"download_url": download_url}, headers=cors)


async def api_download(request: Request) -> Response:  # noqa: PLR0911
    """Download task results as CSV or JSON.

    Fetches results from the public Engine API using the per-task API key
    stored in Redis.

    Query params:
        format: "csv" (default) or "json"
    """
    cors = _cors_headers()
    if request.method == "OPTIONS":
        return Response(
            status_code=204,
            headers={**cors, "Access-Control-Max-Age": "3600"},
        )

    task_id = request.path_params["task_id"]

    if err := _validate_uuid(task_id):
        return err

    fmt = request.query_params.get("format", "csv")
    if fmt not in ("csv", "json"):
        return JSONResponse(
            {"error": "Unsupported format"}, status_code=400, headers=cors
        )
    # Fetch results via the public API (paginated path handles citation
    # resolution and internal column stripping automatically).
    api_key = await redis_store.get_task_token(task_id)
    if not api_key:
        return JSONResponse(
            {"error": "Unknown task or expired session"},
            status_code=404,
            headers=cors,
        )

    try:
        # Trailing slash on base_url is required for httpx to append
        # relative paths correctly (RFC 3986).  A leading slash on the
        # request path would *replace* the base path, sending the
        # request to https://host/tasks/… instead of …/api/v0/tasks/….
        base = settings.futuresearch_api_url.rstrip("/") + "/"
        async with httpx.AsyncClient(
            base_url=base,
            headers={"Authorization": f"Bearer {api_key}"},
        ) as http:
            resp = await http.get(
                f"tasks/{task_id}/result",
                params={"offset": 0, "limit": 100000},
            )
            resp.raise_for_status()
            body = resp.json()
            records: list[dict] = body.get("data") or []
    except Exception:
        logger.exception("Failed to fetch results for download, task %s", task_id)
        return JSONResponse(
            {"error": "Failed to fetch results"}, status_code=500, headers=cors
        )

    safe_prefix = "".join(c for c in task_id[:8] if c.isalnum() or c == "-")

    if fmt == "json":
        return Response(
            content=json.dumps(records),
            media_type="application/json",
            headers={
                **cors,
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="results_{safe_prefix}.json"',
            },
        )

    csv_text = pd.DataFrame(records).to_csv(index=False, quoting=csv.QUOTE_ALL)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **cors,
            "Content-Disposition": f'attachment; filename="results_{safe_prefix}.csv"',
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )

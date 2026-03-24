"""REST endpoints for the futuresearch MCP server (progress polling)."""

from __future__ import annotations

import csv
import json
import logging
import secrets
from uuid import UUID

import pandas as pd
from futuresearch.api_utils import handle_response
from futuresearch.generated.api.tasks import get_task_status_tasks_task_id_status_get
from futuresearch.generated.client import AuthenticatedClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from futuresearch_mcp import redis_store
from futuresearch_mcp.config import settings
from futuresearch_mcp.result_store import _sanitize_records
from futuresearch_mcp.tool_helpers import _UI_EXCLUDE, TaskState, _fetch_task_result

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


async def _fetch_summaries_rest(
    client: AuthenticatedClient, task_id: str, cursor: str | None
) -> tuple[list[dict] | None, str | None]:
    """Fetch agent summaries from the Engine API for the REST progress endpoint."""
    try:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        httpx_client = client.get_async_httpx_client()
        resp = await httpx_client.request(
            method="get",
            url=f"/tasks/{task_id}/summaries",
            params=params,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("summaries") or None, data.get("cursor") or cursor
    except Exception:
        logger.debug("Failed to fetch summaries for task %s via REST", task_id)
    return None, cursor


async def _fetch_aggregate_rest(
    client: AuthenticatedClient, task_id: str, cursor: str | None
) -> tuple[str | None, list[dict] | None, str | None]:
    """Fetch aggregate + micro-summaries from the Engine API.

    Returns (aggregate_text, micro_summaries, updated_cursor).
    Falls back to plain summaries when the aggregate endpoint is unavailable.
    """
    try:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        httpx_client = client.get_async_httpx_client()
        resp = await httpx_client.request(
            method="get",
            url=f"/tasks/{task_id}/summaries/aggregate",
            params=params,
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                data.get("aggregate") or None,
                data.get("micro_summaries") or None,
                data.get("cursor") or cursor,
            )
    except Exception:
        pass

    # Fallback: plain summaries without aggregate
    summaries, new_cursor = await _fetch_summaries_rest(client, task_id, cursor)
    return None, summaries, new_cursor


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

        if ts.is_terminal:
            # Don't pop the token immediately — the widget's autoFetchResults
            # needs it to call /download-token after task completion.
            # The token will expire naturally via Redis TTL.
            pass

        payload = ts.model_dump(mode="json", exclude=_UI_EXCLUDE)

        # Fetch aggregate + micro-summaries + partial rows for non-terminal tasks
        if not ts.is_terminal:
            cursor = request.query_params.get("cursor")
            aggregate, summaries, new_cursor = await _fetch_aggregate_rest(
                client, task_id, cursor
            )
            if aggregate:
                payload["aggregate_summary"] = aggregate
            if summaries:
                payload["summaries"] = summaries
            if new_cursor:
                payload["cursor"] = new_cursor

        return JSONResponse(payload, headers=cors)
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


async def api_download(request: Request) -> Response:  # noqa: PLR0911
    """REST endpoint to download task results as CSV or JSON.

    Authenticates via the poll token (Authorization: Bearer header or
    ?token= query param). No separate download token needed.
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

    if err := await _validate_poll_token(task_id, request):
        return err

    fmt = request.query_params.get("format", "csv")
    if fmt not in ("csv", "json"):
        return JSONResponse(
            {"error": "Unsupported format"}, status_code=400, headers=cors
        )

    # Fetch results via the public API (parquet-first path handles citation
    # resolution and internal column stripping automatically).
    api_key = await redis_store.get_task_token(task_id)
    if not api_key:
        return JSONResponse(
            {"error": "Results not found or expired"}, status_code=404, headers=cors
        )
    try:
        client = AuthenticatedClient(
            base_url=settings.futuresearch_api_url,
            token=api_key,
            raise_on_unexpected_status=True,
            follow_redirects=True,
        )
        rows, _total, _session_id, _artifact_id = await _fetch_task_result(
            client, task_id
        )
        records: list[dict] = _sanitize_records(rows)
    except Exception:
        logger.warning("Failed to fetch results for task %s", task_id, exc_info=True)
        return JSONResponse(
            {"error": "Results not found or expired"}, status_code=404, headers=cors
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

    # CSV generated on-the-fly from the already-resolved records.
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

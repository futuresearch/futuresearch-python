"""REST endpoints for the everyrow MCP server (progress polling)."""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

from everyrow.api_utils import handle_response
from everyrow.generated.api.tasks import get_task_status_tasks_task_id_status_get
from everyrow.generated.client import AuthenticatedClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings
from everyrow_mcp.tool_helpers import _UI_EXCLUDE, TaskState

logger = logging.getLogger(__name__)

_CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET"}


async def _validate_poll_token(task_id: str, request: Request) -> JSONResponse | None:
    """Return an error response if the poll token is missing/invalid, else None."""
    expected = await redis_store.get_poll_token(task_id)
    provided = request.query_params.get("token", "")
    if not expected or not secrets.compare_digest(provided, expected):
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=_CORS)
    return None


async def api_progress(request: Request) -> Response:
    """REST endpoint for the session widget to poll task progress."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_CORS)

    task_id = request.path_params["task_id"]

    if err := await _validate_poll_token(task_id, request):
        return err

    api_key = await redis_store.get_task_token(task_id)

    if not api_key:
        return JSONResponse({"error": "Unknown task"}, status_code=404, headers=_CORS)

    try:
        client = AuthenticatedClient(
            base_url=settings.everyrow_api_url,
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
            await redis_store.pop_task_token(task_id)

        return JSONResponse(
            ts.model_dump(mode="json", exclude=_UI_EXCLUDE), headers=_CORS
        )
    except Exception:
        logger.exception("Progress poll failed for task %s", task_id)
        return JSONResponse(
            {"error": "Internal server error"}, status_code=500, headers=_CORS
        )


async def api_download(request: Request) -> Response:
    """REST endpoint to download task results as CSV."""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_CORS)

    task_id = request.path_params["task_id"]

    if err := await _validate_poll_token(task_id, request):
        return err

    csv_text = await redis_store.get_result_csv(task_id)
    if csv_text is None:
        return JSONResponse(
            {"error": "Results not found or expired"}, status_code=404, headers=_CORS
        )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **_CORS,
            "Content-Disposition": f'attachment; filename="results_{task_id[:8]}.csv"',
        },
    )

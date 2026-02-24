"""Presigned URL upload system for large files (HTTP mode only).

Provides:
- ``request_upload_url`` MCP tool — returns a signed upload URL + curl instructions
- ``handle_upload`` REST endpoint — receives the file and creates an artifact
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from io import BytesIO
from uuid import uuid4

import pandas as pd
from everyrow.ops import create_table_artifact
from everyrow.session import create_session
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings
from everyrow_mcp.tool_helpers import EveryRowContext

logger = logging.getLogger(__name__)


# ── Input model ───────────────────────────────────────────────


class RequestUploadUrlInput(BaseModel):
    """Input for the request_upload_url tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    filename: str = Field(
        ...,
        description="Name of the file to upload (must end in .csv).",
        min_length=1,
    )


# ── HMAC signing ──────────────────────────────────────────────

_secret: list[str] = []  # mutable container to avoid global statement


def _get_secret() -> str:
    """Return the HMAC secret, generating one if not configured."""
    if not _secret:
        _secret.append(settings.upload_secret or secrets.token_urlsafe(32))
    return _secret[0]


def sign_upload_url(upload_id: str, expires_at: int) -> str:
    """Create an HMAC-SHA256 signature for an upload URL."""
    msg = f"{upload_id}:{expires_at}"
    return hmac.new(_get_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()


def verify_upload_signature(upload_id: str, expires_at: int, signature: str) -> bool:
    """Verify an upload URL signature and check expiry."""
    if time.time() > expires_at:
        return False
    expected = sign_upload_url(upload_id, expires_at)
    return hmac.compare_digest(expected, signature)


# ── MCP tool ──────────────────────────────────────────────────


def register_upload_tool(mcp: FastMCP) -> None:
    """Register the request_upload_url tool (HTTP mode only)."""

    @mcp.tool(
        name="everyrow_request_upload_url",
        structured_output=False,
        annotations=ToolAnnotations(
            title="Request Upload URL",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def request_upload_url(
        params: RequestUploadUrlInput, ctx: EveryRowContext
    ) -> list[TextContent]:
        """Request a presigned URL to upload a large file.

        Use this when you have a file in the sandbox that is too large to pass as
        inline data. Returns a URL and curl command. After uploading, use the
        returned artifact_id in any processing tool.

        Steps:
        1. Call this tool with the filename
        2. Execute the returned curl command
        3. Use the artifact_id from the upload response
        """
        if not params.filename.lower().endswith(".csv"):
            return [
                TextContent(
                    type="text",
                    text="Error: filename must end in .csv",
                )
            ]

        upload_id = str(uuid4())
        expires_at = int(time.time()) + settings.upload_url_ttl
        sig = sign_upload_url(upload_id, expires_at)

        mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url
        upload_url = (
            f"{mcp_server_url}/api/uploads/{upload_id}?expires={expires_at}&sig={sig}"
        )

        # Store metadata in Redis
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": params.filename,
                "expires_at": expires_at,
            }
        )
        await redis_store.store_upload_meta(upload_id, meta, settings.upload_url_ttl)

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "upload_url": upload_url,
                        "upload_id": upload_id,
                        "expires_in": settings.upload_url_ttl,
                        "max_size_bytes": settings.max_upload_size_bytes,
                        "curl_command": f'curl -X PUT -T "{params.filename}" "{upload_url}"',
                    }
                ),
            )
        ]


# ── REST endpoint ─────────────────────────────────────────────


async def _validate_upload(
    request: Request,
) -> tuple[bytes, None] | tuple[None, JSONResponse]:
    """Validate upload signature, metadata, and body. Returns (body, None) or (None, error)."""
    upload_id = request.path_params["upload_id"]
    expires_str = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")
    try:
        expires_at = int(expires_str)
    except (ValueError, TypeError):
        return None, JSONResponse(
            {"error": "Invalid expires parameter"}, status_code=400
        )

    if not verify_upload_signature(upload_id, expires_at, sig):
        return None, JSONResponse(
            {"error": "Invalid or expired signature"}, status_code=403
        )

    meta_json = await redis_store.pop_upload_meta(upload_id)
    if meta_json is None:
        return None, JSONResponse(
            {"error": "Upload URL already used or expired"}, status_code=410
        )

    body = await request.body()
    if not body:
        return None, JSONResponse({"error": "Empty body"}, status_code=400)
    if len(body) > settings.max_upload_size_bytes:
        return None, JSONResponse(
            {
                "error": f"File too large: {len(body)} bytes (max {settings.max_upload_size_bytes})"
            },
            status_code=413,
        )
    return body, None


async def handle_upload(request: Request) -> JSONResponse:
    """PUT /api/uploads/{upload_id} — receive an uploaded file and create an artifact."""
    body, error = await _validate_upload(request)
    if error is not None:
        return error

    try:
        df = pd.read_csv(BytesIO(body))  # type: ignore[arg-type]
    except Exception as exc:
        return JSONResponse({"error": f"Could not parse CSV: {exc}"}, status_code=400)

    if df.empty:
        return JSONResponse({"error": "CSV is empty"}, status_code=400)

    try:
        from everyrow.api_utils import create_client  # noqa: PLC0415

        with create_client() as client:
            async with create_session(client=client) as session:
                artifact_id = await create_table_artifact(df, session)
    except Exception as exc:
        logger.exception("Failed to create artifact from upload")
        return JSONResponse(
            {"error": f"Failed to create artifact: {exc}"}, status_code=500
        )

    return JSONResponse(
        {
            "artifact_id": str(artifact_id),
            "rows": len(df),
            "columns": list(df.columns),
            "size_bytes": len(body),
        },
        status_code=201,
    )

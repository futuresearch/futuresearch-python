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
import shlex
import time
from io import BytesIO
from uuid import uuid4

import pandas as pd
from everyrow.generated.client import AuthenticatedClient
from everyrow.ops import create_table_artifact
from everyrow.session import create_session
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings
from everyrow_mcp.redis_store import build_key, decrypt_value, encrypt_value
from everyrow_mcp.tool_helpers import EveryRowContext

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/octet-stream",
}


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


def _get_secret() -> str:
    """Return the HMAC secret from settings.

    Raises at call time if UPLOAD_SECRET is not configured — required
    in multi-pod deployments so all instances share the same signing key.
    """
    if not settings.upload_secret:
        raise RuntimeError(
            "UPLOAD_SECRET must be set in HTTP mode for HMAC signing. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return settings.upload_secret


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
        """Request a presigned URL to upload a local CSV file.

        Use this to upload a file from your local filesystem or sandbox.
        This is the recommended way to ingest local files in HTTP mode.

        Steps:
        1. Call this tool with the filename
        2. Execute the returned curl command to upload the file
        3. Parse the JSON response to get the artifact_id
        4. Pass the artifact_id to any processing tool (everyrow_agent, etc.)
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

        # Get user's API token from the MCP context
        client = ctx.request_context.lifespan_context.client_factory()
        api_token = getattr(client, "token", None) or ""
        if not api_token:
            return [
                TextContent(
                    type="text",
                    text="Error: no API token available. Please authenticate first.",
                )
            ]

        # Store metadata in Redis (token encrypted at rest)
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": params.filename,
                "expires_at": expires_at,
                "api_token": encrypt_value(api_token),
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
                        "curl_command": f"curl -X PUT -T {shlex.quote(params.filename)} {shlex.quote(upload_url)}",
                    }
                ),
            )
        ]


# ── REST endpoint ─────────────────────────────────────────────


async def _validate_upload(  # noqa: PLR0911
    request: Request,
) -> tuple[bytes, dict, None] | tuple[None, None, JSONResponse]:
    """Validate upload signature, metadata, and body.

    Returns (body, metadata_dict, None) or (None, None, error).
    """
    upload_id = request.path_params["upload_id"]
    expires_str = request.query_params.get("expires", "")
    sig = request.query_params.get("sig", "")
    try:
        expires_at = int(expires_str)
    except (ValueError, TypeError):
        return (
            None,
            None,
            JSONResponse({"error": "Invalid expires parameter"}, status_code=400),
        )

    if not verify_upload_signature(upload_id, expires_at, sig):
        return (
            None,
            None,
            JSONResponse({"error": "Invalid or expired signature"}, status_code=403),
        )

    meta_json = await redis_store.get_upload_meta(upload_id)
    if meta_json is None:
        return (
            None,
            None,
            JSONResponse(
                {"error": "Upload URL already used or expired"}, status_code=410
            ),
        )
    meta = json.loads(meta_json)

    # Check Content-Length header before buffering the full body
    content_length_str = request.headers.get("content-length", "")
    if content_length_str:
        try:
            content_length = int(content_length_str)
            if content_length > settings.max_upload_size_bytes:
                return (
                    None,
                    None,
                    JSONResponse({"error": "File too large"}, status_code=413),
                )
        except (ValueError, TypeError):
            pass

    body = await request.body()
    if not body:
        return None, None, JSONResponse({"error": "Empty body"}, status_code=400)
    if len(body) > settings.max_upload_size_bytes:
        return None, None, JSONResponse({"error": "File too large"}, status_code=413)
    return body, meta, None


async def handle_upload(request: Request) -> JSONResponse:  # noqa: PLR0911
    """PUT /api/uploads/{upload_id} — receive an uploaded file and create an artifact."""
    body, meta, error = await _validate_upload(request)
    if error is not None:
        return error
    assert body is not None and meta is not None  # type narrowing

    # Retrieve and decrypt the user's API token
    content_type = (
        (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    )
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        return JSONResponse(
            {
                "error": f"Unsupported Content-Type: {content_type}. Use text/csv or application/octet-stream."
            },
            status_code=415,
        )

    # Retrieve and decrypt the user's API token
    try:
        api_token = decrypt_value(meta.get("api_token", ""))
    except Exception:
        logger.warning(
            "Failed to decrypt api_token for upload %s",
            request.path_params.get("upload_id"),
        )
        api_token = ""
    if not api_token:
        return JSONResponse({"error": "Upload authorization missing"}, status_code=403)

    token_hash = hashlib.sha256(api_token.encode()).hexdigest()[:16]
    rl_key = build_key("upload_rate", token_hash)
    redis_client = redis_store.get_redis_client()
    async with redis_client.pipeline() as pipe:
        pipe.incr(rl_key)
        pipe.expire(rl_key, settings.upload_rate_window)
        count, _ = await pipe.execute()
    if count > settings.upload_rate_limit:
        return JSONResponse(
            {"error": "Upload rate limit exceeded. Try again later."},
            status_code=429,
        )

    # All checks passed — atomically consume the upload URL.
    # If two requests race past the peek, only one wins the pop.
    upload_id = request.path_params["upload_id"]
    if await redis_store.pop_upload_meta(upload_id) is None:
        return JSONResponse(
            {"error": "Upload URL already used or expired"}, status_code=410
        )

    try:
        df = pd.read_csv(BytesIO(body))  # type: ignore[arg-type]
    except Exception as exc:
        logger.warning("CSV parse failed for upload: %s", exc)
        return JSONResponse(
            {"error": "Could not parse CSV file. Ensure it is valid UTF-8 CSV."},
            status_code=400,
        )

    if df.empty:
        return JSONResponse({"error": "CSV is empty"}, status_code=400)

    if len(df) > settings.max_upload_rows:
        return JSONResponse(
            {
                "error": f"CSV has {len(df)} rows (max {settings.max_upload_rows}). "
                "Reduce the file size and try again."
            },
            status_code=413,
        )

    try:
        client = AuthenticatedClient(
            base_url=settings.everyrow_api_url,
            token=api_token,
            raise_on_unexpected_status=True,
            follow_redirects=True,
        )
        async with create_session(client=client) as session:
            artifact_id = await create_table_artifact(df, session)
    except Exception as exc:
        logger.error("Failed to create artifact from upload: %s", type(exc).__name__)
        return JSONResponse(
            {"error": "Failed to create artifact. Please try again."},
            status_code=500,
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

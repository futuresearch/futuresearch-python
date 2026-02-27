from __future__ import annotations

import json
import logging
import shlex
from urllib.parse import urlparse, urlunparse

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from everyrow_mcp.config import settings
from everyrow_mcp.tool_helpers import EveryRowContext

logger = logging.getLogger(__name__)

# Timeout for proxying the upload body to the Engine (large files may be slow)
_PROXY_TIMEOUT = httpx.Timeout(connect=10, read=90, write=90, pool=10)


# ── Input model ───────────────────────────────────────────────


class RequestUploadUrlInput(BaseModel):
    """Input for the request_upload_url tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    filename: str = Field(
        ...,
        description="Name of the file to upload (must end in .csv).",
        min_length=1,
    )


# ── MCP tool ──────────────────────────────────────────────────


def register_upload_tool(mcp: FastMCP, mcp_server_url: str) -> None:
    """Register the request_upload_url tool and proxy route (HTTP mode only)."""

    @mcp.tool(
        name="everyrow_request_upload_url",
        structured_output=False,
        annotations=ToolAnnotations(
            title="Request Upload URL",
            readOnlyHint=False,
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

        # Delegate to the Cohort Engine API
        engine_url = f"{settings.everyrow_api_url}/uploads/request"
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.post(
                    engine_url,
                    headers={"Authorization": f"Bearer {api_token}"},
                    json={"filename": params.filename},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200] if exc.response else str(exc)
            logger.error(
                "Engine upload request failed: %s %s", exc.response.status_code, detail
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error requesting upload URL: {detail}",
                )
            ]
        except httpx.HTTPError as exc:
            logger.error("Engine upload request failed: %s", exc)
            return [
                TextContent(
                    type="text",
                    text=f"Error connecting to upload service: {exc}",
                )
            ]

        try:
            engine_upload_url = data["upload_url"]
            # Rewrite the URL to point at the MCP server instead of the Engine.
            # The Claude.ai sandbox can reach the MCP server but not api.everyrow.ai.
            upload_url = _rewrite_upload_url(engine_upload_url, mcp_server_url)
            result = {
                "upload_url": upload_url,
                "upload_id": data["upload_id"],
                "expires_in": data["expires_in"],
                "max_size_bytes": data["max_size_bytes"],
                "curl_command": f'curl -X PUT -H "Content-Type: text/csv" -T {shlex.quote(params.filename)} {shlex.quote(upload_url)}',
            }
        except KeyError as exc:
            logger.error("Unexpected Engine response shape: missing key %s", exc)
            return [
                TextContent(
                    type="text",
                    text="Error: unexpected response from upload service. Please try again.",
                )
            ]

        return [TextContent(type="text", text=json.dumps(result))]


def _rewrite_upload_url(engine_url: str, mcp_server_url: str) -> str:
    """Rewrite an Engine presigned URL to route through the MCP server.

    Engine URL: https://api.everyrow.ai/api/v0/uploads/{id}?expires=X&sig=Y
    MCP URL:    https://<mcp-host>/api/uploads/{id}?expires=X&sig=Y

    The path is shortened from /api/v0/uploads/... to /api/uploads/... since
    the MCP proxy route handles the v0 prefix when forwarding to the Engine.
    """
    parsed = urlparse(engine_url)
    mcp_parsed = urlparse(mcp_server_url)

    # Replace /api/v0/uploads/... with /api/uploads/...
    path = parsed.path.replace("/api/v0/uploads/", "/api/uploads/", 1)

    return urlunparse(
        (
            mcp_parsed.scheme,
            mcp_parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


# ── Upload proxy route ───────────────────────────────────────
#
# Why proxy through the MCP server instead of uploading directly to the Engine?
#
# The Claude.ai sandbox has a restrictive egress policy that blocks DNS
# resolution for most external domains.  Even after adding *.everyrow.ai
# to the Claude.ai domain allowlist, the sandbox's curl still gets a
# 403 Forbidden with `x-deny-reason: dns_nxdomain` when trying to reach
# api.everyrow.ai.  The allowlist controls which MCP servers can be
# connected to, but does NOT control which domains the sandbox's curl
# can reach.
#
# The sandbox CAN reach the MCP server, so the MCP server acts as a
# two-way proxy for uploads:
#
#   1. Request phase:  User → MCP → Engine → MCP (rewrites URL) → User
#   2. Upload phase:   User → MCP → Engine → MCP (passthrough) → User
#
# The only smart thing the MCP does is rewrite the URL in step 1.
# Everything else is transparent forwarding.  This adds one hop but
# is the only viable path given the sandbox's network constraints.


async def proxy_upload(request: Request) -> Response:
    """Proxy a CSV upload from the sandbox to the Engine.

    The Claude.ai sandbox cannot reach api.everyrow.ai directly (DNS blocked),
    so the presigned URL points at the MCP server.  This handler forwards the
    PUT body and query params to the Engine's PUT /api/v0/uploads/{upload_id}
    and streams the response back.
    """
    upload_id = request.path_params["upload_id"]
    engine_url = f"{settings.everyrow_api_url}/uploads/{upload_id}"
    if request.url.query:
        engine_url = f"{engine_url}?{request.url.query}"

    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in ("content-type", "content-length")
    }

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as http:
            resp = await http.put(engine_url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("Upload proxy failed: %s", exc)
        return JSONResponse({"detail": "Upload proxy error"}, status_code=502)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={
            k: v for k, v in resp.headers.items() if k.lower() in ("content-type",)
        },
    )

"""Tests for the presigned URL upload system (Engine delegation + proxy)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from everyrow_mcp.uploads import (
    RequestUploadUrlInput,
    _rewrite_upload_url,
    proxy_upload,
    register_upload_tool,
)
from tests.conftest import make_test_context, override_settings

TEST_MCP_SERVER_URL = "https://mcp.example.com"


class TestRequestUploadUrlInput:
    """Tests for the input model."""

    def test_valid_csv_filename(self):
        params = RequestUploadUrlInput(filename="data.csv")
        assert params.filename == "data.csv"

    def test_empty_filename_rejected(self):
        with pytest.raises(ValidationError):
            RequestUploadUrlInput(filename="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            RequestUploadUrlInput(filename="data.csv", extra="x")  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]


def _capture_tool_fn(mock_mcp: MagicMock):
    """Register upload tool on a mock FastMCP and return the captured function."""
    captured: list[Any] = []

    def capture_tool(**_kwargs):
        def decorator(fn):
            captured.append(fn)
            return fn

        return decorator

    mock_mcp.tool = capture_tool
    register_upload_tool(mock_mcp, TEST_MCP_SERVER_URL)
    assert captured, "register_upload_tool did not register a tool"
    return captured[0]


ENGINE_RESPONSE = {
    "upload_url": "https://api.everyrow.ai/api/v0/uploads/abc-123?expires=9999&sig=xyz",
    "upload_id": "abc-123",
    "expires_in": 300,
    "max_size_bytes": 52428800,
    "curl_command": 'curl -X PUT -H "Content-Type: text/csv" -T "data.csv" "..."',
}


class TestRequestUploadUrlTool:
    """Tests for the request_upload_url tool function (Engine delegation)."""

    @pytest.mark.asyncio
    async def test_returns_upload_url(self):
        """Tool delegates to Engine and returns the presigned URL."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        mock_response = MagicMock()
        mock_response.json.return_value = ENGINE_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            params = RequestUploadUrlInput(filename="data.csv")
            result = await tool_fn(params, ctx)

        assert len(result) == 1
        data = json.loads(result[0].text)
        # URL should be rewritten to MCP server domain
        assert data["upload_url"].startswith(TEST_MCP_SERVER_URL)
        assert "/api/uploads/abc-123" in data["upload_url"]
        assert "expires=9999" in data["upload_url"]
        assert "sig=xyz" in data["upload_url"]
        assert data["upload_id"] == ENGINE_RESPONSE["upload_id"]
        assert data["expires_in"] == 300
        assert "curl" in data["curl_command"]
        # curl command should also use MCP server URL
        assert TEST_MCP_SERVER_URL in data["curl_command"]

        # Verify the Engine API was called with correct auth
        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer fake-token"
        assert call_kwargs[1]["json"] == {"filename": "data.csv"}

    @pytest.mark.asyncio
    async def test_rejects_non_csv(self):
        """Tool rejects non-CSV filenames without calling Engine."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        params = RequestUploadUrlInput(filename="data.json")
        result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert ".csv" in result[0].text

    @pytest.mark.asyncio
    async def test_no_token_returns_error(self):
        """Tool returns error when no API token is available."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="")
        ctx = make_test_context(mock_client)

        params = RequestUploadUrlInput(filename="data.csv")
        result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert "authenticate" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_engine_http_error(self):
        """Tool handles HTTP errors from Engine gracefully."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service unavailable"
        exc = httpx.HTTPStatusError("503", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = exc

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            params = RequestUploadUrlInput(filename="data.csv")
            result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert "Service unavailable" in result[0].text

    @pytest.mark.asyncio
    async def test_engine_connection_error(self):
        """Tool handles connection errors gracefully."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.post.side_effect = httpx.ConnectError("Connection refused")
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            params = RequestUploadUrlInput(filename="data.csv")
            result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert "connecting" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_engine_unexpected_response_shape(self):
        """Tool handles missing keys in Engine response gracefully."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        # Engine returns response missing expected keys
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_response.raise_for_status = MagicMock()

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            params = RequestUploadUrlInput(filename="data.csv")
            result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert "unexpected response" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_api_url_construction(self):
        """Tool constructs the correct Engine API URL."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        mock_response = MagicMock()
        mock_response.json.return_value = ENGINE_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with (
            override_settings(
                everyrow_api_url="https://custom-engine.example.com/api/v0"
            ),
            patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx,
        ):
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            params = RequestUploadUrlInput(filename="test.csv")
            await tool_fn(params, ctx)

        call_args = mock_http.post.call_args
        assert (
            call_args[0][0]
            == "https://custom-engine.example.com/api/v0/uploads/request"
        )


class TestRewriteUploadUrl:
    """Tests for URL rewriting from Engine domain to MCP server domain."""

    def test_rewrites_host_and_path(self):
        engine_url = (
            "https://api.everyrow.ai/api/v0/uploads/abc-123?expires=9999&sig=xyz"
        )
        result = _rewrite_upload_url(engine_url, "https://mcp.example.com")
        assert (
            result == "https://mcp.example.com/api/uploads/abc-123?expires=9999&sig=xyz"
        )

    def test_preserves_query_params(self):
        engine_url = (
            "https://api.everyrow.ai/api/v0/uploads/id-1?expires=100&sig=abc&extra=val"
        )
        result = _rewrite_upload_url(engine_url, "https://tunnel.trycloudflare.com")
        assert "expires=100" in result
        assert "sig=abc" in result
        assert "extra=val" in result

    def test_handles_tunnel_url_with_port(self):
        engine_url = "https://api.everyrow.ai/api/v0/uploads/id-1?expires=1&sig=s"
        result = _rewrite_upload_url(engine_url, "http://localhost:8000")
        assert result.startswith("http://localhost:8000/api/uploads/id-1")


class TestProxyUpload:
    """Tests for the upload proxy route handler."""

    @pytest.mark.asyncio
    async def test_proxies_to_engine(self):
        """Proxy forwards PUT body and query params to Engine."""
        request = MagicMock()
        request.path_params = {"upload_id": "abc-123"}
        request.url.query = "expires=9999&sig=xyz"
        request.body = AsyncMock(return_value=b"col1,col2\na,b\n")
        request.headers = MagicMock()
        request.headers.items.return_value = [
            ("content-type", "text/csv"),
            ("host", "mcp.example.com"),
        ]

        engine_resp = MagicMock()
        engine_resp.status_code = 200
        engine_resp.content = b'{"artifact_id":"art-1","session_id":"s-1","rows":1,"columns":["col1","col2"],"size_bytes":14}'
        engine_resp.headers = MagicMock()
        engine_resp.headers.items.return_value = [("content-type", "application/json")]

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.put.return_value = engine_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            result = await proxy_upload(request)

        assert result.status_code == 200
        # Verify Engine was called with query params
        call_args = mock_http.put.call_args
        assert "expires=9999&sig=xyz" in call_args[0][0]
        assert call_args[1]["content"] == b"col1,col2\na,b\n"

    @pytest.mark.asyncio
    async def test_proxy_returns_engine_error(self):
        """Proxy returns Engine error status codes transparently."""
        request = MagicMock()
        request.path_params = {"upload_id": "abc-123"}
        request.url.query = "expires=9999&sig=xyz"
        request.body = AsyncMock(return_value=b"data")
        request.headers = MagicMock()
        request.headers.items.return_value = [("content-type", "text/csv")]

        engine_resp = MagicMock()
        engine_resp.status_code = 401
        engine_resp.content = b'{"detail":"Invalid signature"}'
        engine_resp.headers = MagicMock()
        engine_resp.headers.items.return_value = [("content-type", "application/json")]

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.put.return_value = engine_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            result = await proxy_upload(request)

        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_proxy_connection_error_returns_502(self):
        """Proxy returns 502 when it can't reach the Engine."""
        request = MagicMock()
        request.path_params = {"upload_id": "abc-123"}
        request.url.query = "expires=1&sig=s"
        request.body = AsyncMock(return_value=b"data")
        request.headers = MagicMock()
        request.headers.items.return_value = [("content-type", "text/csv")]

        with patch("everyrow_mcp.uploads.httpx.AsyncClient") as mock_httpx:
            mock_http = AsyncMock()
            mock_http.put.side_effect = httpx.ConnectError("Connection refused")
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_http

            result = await proxy_upload(request)

        assert result.status_code == 502

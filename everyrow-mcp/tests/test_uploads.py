"""Tests for the presigned URL upload system."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from everyrow_mcp.uploads import (
    RequestUploadUrlInput,
    register_upload_tool,
    sign_upload_url,
    verify_upload_signature,
)
from tests.conftest import make_test_context, override_settings


class TestHmacSigning:
    """Tests for HMAC signing and verification."""

    @pytest.fixture(autouse=True)
    def _with_upload_secret(self):
        with override_settings(upload_secret="test-secret-for-hmac"):
            yield

    def test_roundtrip(self):
        """A signature can be verified immediately."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        sig = sign_upload_url(upload_id, expires_at)
        assert verify_upload_signature(upload_id, expires_at, sig) is True

    def test_expired_signature_rejected(self):
        """An expired signature is rejected."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) - 1  # already expired
        sig = sign_upload_url(upload_id, expires_at)
        assert verify_upload_signature(upload_id, expires_at, sig) is False

    def test_tampered_signature_rejected(self):
        """A tampered signature is rejected."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        sig = sign_upload_url(upload_id, expires_at)
        assert verify_upload_signature(upload_id, expires_at, sig + "x") is False

    def test_different_upload_id_rejected(self):
        """A signature for a different upload_id is rejected."""
        expires_at = int(time.time()) + 300
        sig = sign_upload_url("upload-1", expires_at)
        assert verify_upload_signature("upload-2", expires_at, sig) is False

    def test_missing_secret_raises(self):
        """RuntimeError when UPLOAD_SECRET is not set."""
        with override_settings(upload_secret=""):
            with pytest.raises(RuntimeError, match="UPLOAD_SECRET must be set"):
                sign_upload_url("test", int(time.time()) + 300)


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
            RequestUploadUrlInput(filename="data.csv", extra="x")  # type: ignore[call-arg]


def _capture_tool_fn(mock_mcp: MagicMock):
    """Register upload tool on a mock FastMCP and return the captured function."""
    captured: list = []

    def capture_tool(**_kwargs):
        def decorator(fn):
            captured.append(fn)
            return fn

        return decorator

    mock_mcp.tool = capture_tool
    register_upload_tool(mock_mcp)
    assert captured, "register_upload_tool did not register a tool"
    return captured[0]


class TestRequestUploadUrlTool:
    """Tests for the request_upload_url tool function."""

    @pytest.mark.asyncio
    async def test_returns_upload_url(self, fake_redis):  # noqa: ARG002
        """Tool returns a signed upload URL and curl instructions."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        with (
            override_settings(transport="streamable-http", upload_secret="test-secret"),
            patch(
                "everyrow_mcp.uploads.redis_store.store_upload_meta",
                new_callable=AsyncMock,
            ),
        ):
            params = RequestUploadUrlInput(filename="data.csv")
            result = await tool_fn(params, ctx)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "upload_url" in data
        assert "upload_id" in data
        assert "expires_in" in data
        assert "curl_command" in data
        assert data["expires_in"] == 300

    @pytest.mark.asyncio
    async def test_rejects_non_csv(self, fake_redis):  # noqa: ARG002
        """Tool rejects non-CSV filenames."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="fake-token")
        ctx = make_test_context(mock_client)

        with override_settings(
            transport="streamable-http", upload_secret="test-secret"
        ):
            params = RequestUploadUrlInput(filename="data.json")
            result = await tool_fn(params, ctx)

        assert "Error" in result[0].text
        assert ".csv" in result[0].text

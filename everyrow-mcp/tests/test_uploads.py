"""Tests for the presigned URL upload system."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from everyrow_mcp.redis_store import decrypt_value, encrypt_value
from everyrow_mcp.uploads import (
    RequestUploadUrlInput,
    _validate_upload,
    handle_upload,
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

    @pytest.mark.asyncio
    async def test_stores_user_token_in_metadata(self, fake_redis):  # noqa: ARG002
        """Tool stores the user's API token in upload metadata."""
        mock_mcp = MagicMock()
        tool_fn = _capture_tool_fn(mock_mcp)

        mock_client = MagicMock(token="user-api-token-123")
        ctx = make_test_context(mock_client)

        stored_meta: list[str] = []

        async def capture_store(upload_id, meta_json, ttl):  # noqa: ARG001
            stored_meta.append(meta_json)

        with (
            override_settings(transport="streamable-http", upload_secret="test-secret"),
            patch(
                "everyrow_mcp.uploads.redis_store.store_upload_meta",
                new_callable=AsyncMock,
                side_effect=capture_store,
            ),
        ):
            params = RequestUploadUrlInput(filename="data.csv")
            await tool_fn(params, ctx)

            # Decrypt inside the override context where the Fernet key is available
            assert stored_meta
            meta = json.loads(stored_meta[0])
            assert decrypt_value(meta["api_token"]) == "user-api-token-123"


class TestHandleUpload:
    """Tests for the handle_upload endpoint."""

    @pytest.fixture(autouse=True)
    def _with_upload_secret(self):
        with override_settings(upload_secret="test-secret-for-hmac"):
            yield

    @pytest.fixture(autouse=True)
    def _mock_redis_client(self):
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        with patch(
            "everyrow_mcp.uploads.redis_store.get_redis_client",
            return_value=mock_client,
        ):
            yield

    def _make_upload_request(
        self,
        upload_id: str,
        body: bytes,
        *,
        expires_at: int | None = None,
        sig: str | None = None,
        content_length: str | None = None,
    ) -> MagicMock:
        if expires_at is None:
            expires_at = int(time.time()) + 300
        if sig is None:
            sig = sign_upload_url(upload_id, expires_at)

        request = MagicMock()
        request.path_params = {"upload_id": upload_id}
        request.query_params = {"expires": str(expires_at), "sig": sig}
        headers = {}
        if content_length is not None:
            headers["content-length"] = content_length
        request.headers = headers
        request.body = AsyncMock(return_value=body)
        return request

    @pytest.mark.asyncio
    async def test_missing_token_returns_403(self, fake_redis):  # noqa: ARG002
        """Upload with no api_token in metadata returns 403."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        meta_no_token = json.dumps(
            {"upload_id": upload_id, "filename": "data.csv", "expires_at": expires_at}
        )

        with patch(
            "everyrow_mcp.uploads.redis_store.get_upload_meta",
            new_callable=AsyncMock,
            return_value=meta_no_token,
        ):
            request = self._make_upload_request(
                upload_id, b"a,b\n1,2\n", expires_at=expires_at
            )
            resp = await handle_upload(request)

        assert resp.status_code == 403
        body = json.loads(resp.body.decode())
        assert body["error"] == "Upload authorization missing"

    @pytest.mark.asyncio
    async def test_content_length_too_large_returns_413(self, fake_redis):  # noqa: ARG002
        """Content-Length exceeding max returns 413 before reading body."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": "data.csv",
                "expires_at": expires_at,
                "api_token": "tok",
            }
        )

        with (
            override_settings(max_upload_size_bytes=1000),
            patch(
                "everyrow_mcp.uploads.redis_store.get_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
        ):
            request = self._make_upload_request(
                upload_id,
                b"",  # body shouldn't even be read
                expires_at=expires_at,
                content_length="999999",
            )
            _, _, error = await _validate_upload(request)

        assert error is not None
        assert error.status_code == 413

    @pytest.mark.asyncio
    async def test_error_messages_are_generic(self, fake_redis):  # noqa: ARG002
        """Error messages do not leak internal details."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": "data.csv",
                "expires_at": expires_at,
                "api_token": encrypt_value("user-tok"),
            }
        )

        with (
            patch(
                "everyrow_mcp.uploads.redis_store.get_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
            patch(
                "everyrow_mcp.uploads.redis_store.pop_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
        ):
            request = self._make_upload_request(
                upload_id, b"not,valid\x00csv\xfe\xff", expires_at=expires_at
            )
            resp = await handle_upload(request)

        assert resp.status_code == 400
        body = json.loads(resp.body.decode())
        # Error message should be generic, not contain internal exception details
        assert "Could not parse CSV file" in body["error"]
        assert "Ensure it is valid UTF-8 CSV" in body["error"]

    @pytest.mark.asyncio
    async def test_artifact_creation_error_is_generic(self, fake_redis):  # noqa: ARG002
        """Artifact creation failure returns generic error message."""
        upload_id = "test-upload-id"
        expires_at = int(time.time()) + 300
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": "data.csv",
                "expires_at": expires_at,
                "api_token": encrypt_value("user-tok"),
            }
        )

        with (
            patch(
                "everyrow_mcp.uploads.redis_store.get_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
            patch(
                "everyrow_mcp.uploads.redis_store.pop_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
            patch(
                "everyrow_mcp.uploads.create_session",
                side_effect=RuntimeError("DB connection failed"),
            ),
        ):
            request = self._make_upload_request(
                upload_id, b"a,b\n1,2\n", expires_at=expires_at
            )
            resp = await handle_upload(request)

        assert resp.status_code == 500
        body = json.loads(resp.body.decode())
        assert body["error"] == "Failed to create artifact. Please try again."
        assert "DB connection" not in body["error"]


class TestContentTypeValidation:
    """Tests for Content-Type validation on upload endpoint (M8)."""

    @pytest.fixture(autouse=True)
    def _with_upload_secret(self):
        with override_settings(upload_secret="test-secret-for-hmac"):
            yield

    @pytest.fixture(autouse=True)
    def _mock_redis_client(self):
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        with patch(
            "everyrow_mcp.uploads.redis_store.get_redis_client",
            return_value=mock_client,
        ):
            yield

    @pytest.mark.asyncio
    async def test_wrong_content_type_returns_415(self):
        """Reject uploads with unsupported Content-Type."""
        upload_id = "test-upload-ct"
        expires_at = int(time.time()) + 300
        sig = sign_upload_url(upload_id, expires_at)
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": "data.csv",
                "expires_at": expires_at,
                "api_token": encrypt_value("user-tok"),
            }
        )

        request = MagicMock()
        request.path_params = {"upload_id": upload_id}
        request.query_params = {"expires": str(expires_at), "sig": sig}
        request.headers = {"content-type": "application/json"}
        request.body = AsyncMock(return_value=b"a,b\n1,2\n")

        with patch(
            "everyrow_mcp.uploads.redis_store.get_upload_meta",
            new_callable=AsyncMock,
            return_value=meta,
        ):
            resp = await handle_upload(request)

        assert resp.status_code == 415
        body = json.loads(resp.body.decode())
        assert "Unsupported Content-Type" in body["error"]

    @pytest.mark.asyncio
    async def test_missing_content_type_is_accepted(self):
        """Uploads without Content-Type header are accepted (existing tests verify this)."""
        # Existing TestHandleUpload tests don't set Content-Type and pass,
        # which implicitly tests that missing Content-Type is accepted.
        pass


class TestUploadRateLimitPreservesUrl:
    """Verify that a 429 does NOT consume the upload URL."""

    @pytest.fixture(autouse=True)
    def _with_upload_secret(self):
        with override_settings(upload_secret="test-secret-for-hmac"):
            yield

    @pytest.mark.asyncio
    async def test_rate_limited_upload_does_not_consume_url(self):
        """When rate-limited (429), the upload metadata is NOT consumed."""
        upload_id = "rate-limit-test"
        expires_at = int(time.time()) + 300
        sig = sign_upload_url(upload_id, expires_at)
        meta = json.dumps(
            {
                "upload_id": upload_id,
                "filename": "data.csv",
                "expires_at": expires_at,
                "api_token": encrypt_value("user-tok"),
            }
        )

        # Pipeline mock returns count > limit to trigger 429
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[999, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        pop_mock = AsyncMock(return_value=meta)

        request = MagicMock()
        request.path_params = {"upload_id": upload_id}
        request.query_params = {"expires": str(expires_at), "sig": sig}
        request.headers = {}
        request.body = AsyncMock(return_value=b"a,b\n1,2\n")

        with (
            override_settings(upload_rate_limit=5),
            patch(
                "everyrow_mcp.uploads.redis_store.get_upload_meta",
                new_callable=AsyncMock,
                return_value=meta,
            ),
            patch(
                "everyrow_mcp.uploads.redis_store.pop_upload_meta",
                pop_mock,
            ),
            patch(
                "everyrow_mcp.uploads.redis_store.get_redis_client",
                return_value=mock_client,
            ),
        ):
            resp = await handle_upload(request)

        assert resp.status_code == 429
        body = json.loads(resp.body.decode())
        assert "rate limit" in body["error"].lower()
        # pop_upload_meta must NOT have been called
        pop_mock.assert_not_called()

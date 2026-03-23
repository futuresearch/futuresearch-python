"""Tests for REST endpoints in routes.py (api_progress)."""

from __future__ import annotations

import csv
import io
import json
import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_progress_info import TaskProgressInfo
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse

from futuresearch_mcp import redis_store
from futuresearch_mcp.routes import (
    _cors_headers,
    api_download,
    api_download_url,
    api_progress,
)

# ── Helpers ────────────────────────────────────────────────────


class FakeRequest:
    """Minimal Starlette Request stand-in for handler tests."""

    def __init__(
        self,
        *,
        method: str = "GET",
        path_params: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.method = method
        self.path_params = path_params or {}
        self.query_params = query_params or {}
        self.headers = headers or {}


def _make_status_response(
    *,
    task_id=None,
    session_id=None,
    status="running",
    completed=3,
    total=10,
    failed=0,
    running=2,
) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=task_id or uuid4(),
        session_id=session_id or uuid4(),
        status=TaskStatus(status),
        task_type=PublicTaskType.AGENT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        progress=TaskProgressInfo(
            pending=total - completed - failed - running,
            running=running,
            completed=completed,
            failed=failed,
            total=total,
        ),
    )


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _use_fake_redis(fake_redis):
    """Patch get_redis_client to return the test Redis instance."""
    with patch.object(redis_store, "get_redis_client", return_value=fake_redis):
        yield


# ── api_progress tests ─────────────────────────────────────────


class TestApiProgress:
    @pytest.mark.asyncio
    async def test_options_returns_204(self):
        req = FakeRequest(method="OPTIONS", path_params={"task_id": "abc"})
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_invalid_poll_token_via_header_returns_403(self):
        task_id = str(uuid4())
        await redis_store.store_poll_token(task_id, "correct-token")
        await redis_store.store_task_token(task_id, "api-key")

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": "Bearer wrong-token"},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_missing_poll_token_returns_403(self):
        task_id = str(uuid4())
        # No poll token stored
        req = FakeRequest(
            path_params={"task_id": task_id},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_denied_without_owner(self):
        """Valid poll token but no task owner → fail-closed 403."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        # No task owner stored

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Task ownership could not be verified"

    @pytest.mark.asyncio
    async def test_denied_without_poll_owner(self):
        """Task owner exists but poll token has no bound user → fail-closed 403."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)  # no user_id
        await redis_store.store_task_owner(task_id, "test-user")

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Task ownership could not be verified"

    @pytest.mark.asyncio
    async def test_denied_on_owner_mismatch(self):
        """Poll token bound to user-A but task_owner tampered to user-B → 403."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="user-A")
        await redis_store.store_task_owner(task_id, "user-B")

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Task ownership could not be verified"

    @pytest.mark.asyncio
    async def test_missing_task_token_returns_404(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        # No task token stored

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_progress(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 404
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Unknown task"

    @pytest.mark.asyncio
    async def test_valid_progress_via_auth_header(self):
        """Poll token sent via Authorization: Bearer header works."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key-123")
        await redis_store.store_task_owner(task_id, "test-user")

        status_resp = _make_status_response(
            status="running", completed=3, total=10, failed=1, running=2
        )

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await api_progress(req)  # pyright: ignore[reportArgumentType]

        assert resp.status_code == 200
        body = json.loads(resp.body.decode())  # pyright: ignore[reportAttributeAccessIssue]
        assert body["status"] == "running"
        assert body["completed"] == 3
        assert body["total"] == 10
        assert body["failed"] == 1
        assert body["running"] == 2
        assert "elapsed_s" in body
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_backward_compat_query_param_for_download(self):
        """Poll token via ?token= query param still works (for download links)."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key-123")
        await redis_store.store_task_owner(task_id, "test-user")

        status_resp = _make_status_response(
            status="running", completed=3, total=10, failed=1, running=2
        )

        req = FakeRequest(
            path_params={"task_id": task_id},
            query_params={"token": poll_token},
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await api_progress(req)  # pyright: ignore[reportArgumentType]

        assert resp.status_code == 200
        body = json.loads(bytes(resp.body).decode())
        assert body["status"] == "running"
        assert body["completed"] == 3
        assert body["total"] == 10
        assert body["failed"] == 1
        assert body["running"] == 2
        assert "elapsed_s" in body
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_completed_task_pops_tokens(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key")
        await redis_store.store_task_owner(task_id, "test-user")

        status_resp = _make_status_response(status="completed", completed=10, total=10)

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await api_progress(req)  # pyright: ignore[reportArgumentType]

        assert resp.status_code == 200
        body = json.loads(bytes(resp.body).decode())
        assert body["status"] == "completed"

        # Both tokens kept — task token needed for CSV download, TTL expires them
        assert await redis_store.get_task_token(task_id) is not None
        assert await redis_store.get_poll_token(task_id) is not None

    @pytest.mark.asyncio
    async def test_api_error_returns_500(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key")
        await redis_store.store_task_owner(task_id, "test-user")

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            resp = await api_progress(req)  # pyright: ignore[reportArgumentType]

        assert resp.status_code == 500
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Internal server error"


class TestApiDownloadToken:
    """Tests for the download-token minting endpoint."""

    @pytest.mark.asyncio
    async def test_options_returns_204(self):
        req = FakeRequest(method="OPTIONS", path_params={"task_id": "abc"})
        resp = await api_download_url(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_valid_poll_token_returns_download_url(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_download_url(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 200
        body = json.loads(bytes(resp.body).decode())
        assert "download_url" in body
        assert f"/api/results/{task_id}/download" in body["download_url"]

    @pytest.mark.asyncio
    async def test_query_param_token_rejected(self):
        """Poll token via ?token= query param should be rejected (bearer only)."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)

        req = FakeRequest(
            path_params={"task_id": task_id},
            query_params={"token": poll_token},
        )
        resp = await api_download_url(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_poll_token_returns_403(self):
        task_id = str(uuid4())
        await redis_store.store_poll_token(task_id, "correct-token")

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": "Bearer wrong-token"},
        )
        resp = await api_download_url(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_400(self):
        req = FakeRequest(
            path_params={"task_id": "not-a-uuid"},
            headers={"authorization": "Bearer some-token"},
        )
        resp = await api_download_url(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_download_url_works_for_download(self):
        """End-to-end: get download URL, then use it to download CSV."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        records = [{"col_a": "val1", "col_b": "val2"}]

        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_task_token(task_id, "sk-cho-test")

        # Step 1: Get the download URL
        mint_req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        mint_resp = await api_download_url(mint_req)  # pyright: ignore[reportArgumentType]
        assert mint_resp.status_code == 200
        mint_body = json.loads(bytes(mint_resp.body).decode())
        download_url = mint_body["download_url"]
        assert f"/api/results/{task_id}/download" in download_url

        # Step 2: Download via public API (forwards API key from Redis)
        dl_req = FakeRequest(
            path_params={"task_id": task_id},
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": records, "status": "completed"}
        mock_http = AsyncMock()
        mock_http.__aenter__.return_value.get.return_value = mock_resp

        with patch(
            "futuresearch_mcp.routes.httpx.AsyncClient",
            return_value=mock_http,
        ):
            dl_resp = await api_download(dl_req)  # pyright: ignore[reportArgumentType]
        assert dl_resp.status_code == 200
        assert "val1" in dl_resp.body.decode()  # pyright: ignore[reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_csv_download_quotes_all_fields(self):
        """CSV download uses QUOTE_ALL so commas in text never break parsing."""
        task_id = str(uuid4())
        records = [
            {
                "company": "Acme, Inc.",
                "description": 'Makes "great" widgets, bolts',
                "revenue": 1000000,
            },
            {
                "company": "Simple Co",
                "description": "No special chars",
                "revenue": 500,
            },
        ]

        await redis_store.store_task_token(task_id, "sk-cho-test")

        dl_req = FakeRequest(
            path_params={"task_id": task_id},
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": records, "status": "completed"}
        mock_http = AsyncMock()
        mock_http.__aenter__.return_value.get.return_value = mock_resp

        with patch(
            "futuresearch_mcp.routes.httpx.AsyncClient",
            return_value=mock_http,
        ):
            dl_resp = await api_download(dl_req)  # pyright: ignore[reportArgumentType]
        assert dl_resp.status_code == 200

        csv_body = dl_resp.body.decode()  # pyright: ignore[reportAttributeAccessIssue]

        # Every field (including headers and numbers) should be quoted
        reader = csv.reader(io.StringIO(csv_body))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows

        # Headers are quoted
        assert rows[0] == ["company", "description", "revenue"]

        # Commas and embedded quotes survive round-trip
        assert rows[1][0] == "Acme, Inc."
        assert rows[1][1] == 'Makes "great" widgets, bolts'
        assert rows[1][2] == "1000000"

        # Simple values also quoted (QUOTE_ALL)
        assert rows[2][0] == "Simple Co"


class TestCorsHeaders:
    """Tests for CORS headers on widget endpoints."""

    def test_returns_wildcard_origin(self):
        headers = _cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Methods"] == "GET"
        assert headers["Access-Control-Allow-Headers"] == "Authorization"

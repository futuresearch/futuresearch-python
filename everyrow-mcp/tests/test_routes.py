"""Tests for REST endpoints in routes.py (api_progress)."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse

from everyrow_mcp import redis_store
from everyrow_mcp.routes import (
    _cors_headers,
    api_download,
    api_download_token,
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
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
        assert "session_url" in body
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
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
        assert "session_url" in body
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
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await api_progress(req)  # pyright: ignore[reportArgumentType]

        assert resp.status_code == 200
        body = json.loads(bytes(resp.body).decode())
        assert body["status"] == "completed"

        # Task token cleaned up; poll token kept for CSV download
        assert await redis_store.get_task_token(task_id) is None
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
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_valid_poll_token_returns_download_url(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json.dumps([{"a": 1, "b": 2}]))

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 200
        body = json.loads(bytes(resp.body).decode())
        assert "download_url" in body
        assert f"/api/results/{task_id}/download?token=" in body["download_url"]

    @pytest.mark.asyncio
    async def test_query_param_token_rejected(self):
        """Poll token via ?token= query param should be rejected (bearer only)."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_result_json(task_id, json.dumps([{"a": 1}]))

        req = FakeRequest(
            path_params={"task_id": task_id},
            query_params={"token": poll_token},
        )
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_poll_token_returns_403(self):
        task_id = str(uuid4())
        await redis_store.store_poll_token(task_id, "correct-token")
        await redis_store.store_result_json(task_id, json.dumps([{"a": 1}]))

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": "Bearer wrong-token"},
        )
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_csv_returns_404(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        # No CSV stored — simulates expired CSV

        req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 404
        body = json.loads(bytes(resp.body).decode())
        assert body["error"] == "Results not found or expired"

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_400(self):
        req = FakeRequest(
            path_params={"task_id": "not-a-uuid"},
            headers={"authorization": "Bearer some-token"},
        )
        resp = await api_download_token(req)  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_minted_token_works_for_download(self):
        """End-to-end: mint a download token, then use it to download CSV."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        json_text = json.dumps([{"col_a": "val1", "col_b": "val2"}])

        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json_text)

        # Step 1: Mint a download token
        mint_req = FakeRequest(
            path_params={"task_id": task_id},
            headers={"authorization": f"Bearer {poll_token}"},
        )
        mint_resp = await api_download_token(mint_req)  # pyright: ignore[reportArgumentType]
        assert mint_resp.status_code == 200
        mint_body = json.loads(bytes(mint_resp.body).decode())
        download_url = mint_body["download_url"]

        # Extract token from URL
        dl_token = download_url.split("token=")[1]

        # Step 2: Use the minted token to download
        dl_req = FakeRequest(
            path_params={"task_id": task_id},
            query_params={"token": dl_token},
        )
        dl_resp = await api_download(dl_req)  # pyright: ignore[reportArgumentType]
        assert dl_resp.status_code == 200
        assert "val1" in dl_resp.body.decode()  # pyright: ignore[reportAttributeAccessIssue]


class TestCorsHeaders:
    """Tests for CORS headers on widget endpoints."""

    def test_returns_wildcard_origin(self):
        headers = _cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Methods"] == "GET"
        assert headers["Access-Control-Allow-Headers"] == "Authorization"

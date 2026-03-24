"""Tests for REST endpoints in routes.py (api_progress)."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_progress_info import TaskProgressInfo
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse

from futuresearch_mcp import redis_store
from futuresearch_mcp.routes import (
    _cors_headers,
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
    async def test_missing_task_token_returns_404(self):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)

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
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key-123")

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
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key-123")

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
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key")

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
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key")

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


class TestCorsHeaders:
    """Tests for CORS headers on widget endpoints."""

    def test_returns_wildcard_origin(self):
        headers = _cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Methods"] == "GET"
        assert headers["Access-Control-Allow-Headers"] == "Authorization"

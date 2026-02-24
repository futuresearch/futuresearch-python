"""Integration tests that spin up the MCP ASGI server.

Uses httpx + ASGITransport to drive the full Starlette application
returned by mcp.streamable_http_app(). Custom routes (/api/progress,
/health) bypass OAuth, so we can test them without Supabase credentials.

These tests exercise the real HTTP stack: Starlette routing, middleware,
request parsing, CORS headers, and response serialization.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from everyrow_mcp import redis_store
from everyrow_mcp.routes import api_progress
from tests.conftest import override_settings

# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def _http_state(fake_redis):
    """Configure settings for HTTP mode and patch Redis."""
    with (
        override_settings(transport="streamable-http"),
        patch.object(redis_store, "get_redis_client", return_value=fake_redis),
    ):
        yield


def _health_endpoint(_request):
    return JSONResponse({"status": "ok"})


@pytest.fixture
def app(_http_state):
    """Build a Starlette app with the same routes as http_config.py."""
    return Starlette(
        routes=[
            Route(
                "/api/progress/{task_id}",
                api_progress,
                methods=["GET", "OPTIONS"],
            ),
            Route("/health", _health_endpoint, methods=["GET"]),
        ],
    )


@pytest.fixture
async def client(app):
    """httpx client wired to the ASGI app — no TCP needed."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


# ── Helpers ────────────────────────────────────────────────────


def _make_status_response(
    *,
    status="running",
    completed=3,
    total=10,
    failed=0,
    running=2,
) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=uuid4(),
        session_id=uuid4(),
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


# ── Health endpoint ────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Progress endpoint ──────────────────────────────────────────


class TestProgressEndpoint:
    @pytest.mark.asyncio
    async def test_unauthorized_without_token(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        resp = await client.get(f"/api/progress/{task_id}")
        assert resp.status_code == 403
        assert resp.json()["error"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_unauthorized_with_wrong_token(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key")

        resp = await client.get(f"/api/progress/{task_id}", params={"token": "wrong"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_task_returns_404(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        # No task_token stored

        resp = await client.get(
            f"/api/progress/{task_id}", params={"token": poll_token}
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "Unknown task"

    @pytest.mark.asyncio
    async def test_running_task_returns_progress(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key-123")

        status_resp = _make_status_response(
            status="running", completed=7, total=20, failed=1, running=4
        )

        with patch(
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await client.get(
                f"/api/progress/{task_id}", params={"token": poll_token}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["completed"] == 7
        assert body["total"] == 20
        assert body["failed"] == 1
        assert body["running"] == 4
        assert body["elapsed_s"] >= 0
        assert "session_url" in body
        # CORS header
        assert resp.headers["access-control-allow-origin"] == "*"

    @pytest.mark.asyncio
    async def test_completed_task_cleans_up_tokens(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key")

        status_resp = _make_status_response(
            status="completed", completed=10, total=10, failed=0, running=0
        )

        with patch(
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            resp = await client.get(
                f"/api/progress/{task_id}", params={"token": poll_token}
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # Task token cleaned up; poll token kept for CSV download
        assert await redis_store.get_task_token(task_id) is None
        assert await redis_store.get_poll_token(task_id) is not None

    @pytest.mark.asyncio
    async def test_api_error_returns_500(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key")

        with patch(
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            side_effect=RuntimeError("upstream timeout"),
        ):
            resp = await client.get(
                f"/api/progress/{task_id}", params={"token": poll_token}
            )

        assert resp.status_code == 500
        assert resp.json()["error"] == "Internal server error"


# ── Progress lifecycle ────────────────────────────────────────


class TestProgressLifecycle:
    """Test the progress polling lifecycle: tokens stored → poll → tokens cleaned up."""

    @pytest.mark.asyncio
    async def test_progress_lifecycle(self, client: httpx.AsyncClient):
        """Full lifecycle: submit tokens → poll progress → task completes →
        tokens cleaned up."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)

        # 1. Store tokens (simulating what everyrow_agent does)
        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_task_token(task_id, "api-key-for-polling")

        # 2. Poll progress — task is running
        running_resp = _make_status_response(status="running", completed=1, total=3)
        with patch(
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=running_resp,
        ):
            resp = await client.get(
                f"/api/progress/{task_id}",
                params={"token": poll_token},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert resp.json()["completed"] == 1

        # 3. Poll progress — task is completed (tokens get cleaned up)
        completed_resp = _make_status_response(
            status="completed", completed=3, total=3, running=0
        )
        with patch(
            "everyrow_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=completed_resp,
        ):
            resp = await client.get(
                f"/api/progress/{task_id}",
                params={"token": poll_token},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # 4. Task token is gone — further progress polls return 404
        resp = await client.get(
            f"/api/progress/{task_id}",
            params={"token": poll_token},
        )
        assert resp.status_code == 404

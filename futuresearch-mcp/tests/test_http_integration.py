"""Integration tests that spin up the MCP ASGI server.

Uses httpx + ASGITransport to drive the full Starlette application
returned by mcp.streamable_http_app(). Custom routes (/api/progress,
/health) bypass OAuth, so we can test them without Supabase credentials.

These tests exercise the real HTTP stack: Starlette routing, middleware,
request parsing, CORS headers, and response serialization.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_progress_info import TaskProgressInfo
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from futuresearch_mcp import redis_store
from futuresearch_mcp.result_store import try_cached_result, try_store_result
from futuresearch_mcp.routes import api_download, api_download_token, api_progress
from tests.conftest import override_settings

# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def _http_state(fake_redis):
    """Configure settings for HTTP mode and patch Redis."""
    with (
        override_settings(transport="streamable-http", upload_secret="test-secret"),
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
            Route(
                "/api/results/{task_id}/download-token",
                api_download_token,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/api/results/{task_id}/download",
                api_download,
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
    async def test_denied_without_owner(self, client: httpx.AsyncClient):
        """Poll token is valid but no task owner recorded → fail-closed 403."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)
        # No task owner stored — ownership check should reject

        resp = await client.get(
            f"/api/progress/{task_id}", params={"token": poll_token}
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "Task ownership could not be verified"

    @pytest.mark.asyncio
    async def test_unknown_task_returns_404(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
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
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key-123")
        await redis_store.store_task_owner(task_id, "test-user")

        status_resp = _make_status_response(
            status="running", completed=7, total=20, failed=1, running=4
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
        # CORS header
        assert resp.headers["access-control-allow-origin"] == "*"

    @pytest.mark.asyncio
    async def test_completed_task_cleans_up_tokens(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key")
        await redis_store.store_task_owner(task_id, "test-user")

        status_resp = _make_status_response(
            status="completed", completed=10, total=10, failed=0, running=0
        )

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key")
        await redis_store.store_task_owner(task_id, "test-user")

        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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

        # 1. Store tokens (simulating what futuresearch_agent does)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_token(task_id, "api-key-for-polling")
        await redis_store.store_task_owner(task_id, "test-user")

        # 2. Poll progress — task is running
        running_resp = _make_status_response(status="running", completed=1, total=3)
        with patch(
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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
            "futuresearch_mcp.routes.get_task_status_tasks_task_id_status_get.asyncio",
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


# ── Download-token endpoint ──────────────────────────────────


class TestDownloadTokenEndpoint:
    """ASGI-level tests for the download-token minting endpoint.

    These go through real Starlette routing, header parsing, and URL
    query-param parsing — unlike the FakeRequest unit tests in test_routes.py.
    """

    @pytest.mark.asyncio
    async def test_bearer_auth_via_real_http_header(self, client: httpx.AsyncClient):
        """Authorization: Bearer header is parsed correctly by Starlette."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json.dumps([{"a": 1, "b": 2}]))

        resp = await client.get(
            f"/api/results/{task_id}/download-token",
            headers={"Authorization": f"Bearer {poll_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "download_url" in body
        assert f"/api/results/{task_id}/download?token=" in body["download_url"]

    @pytest.mark.asyncio
    async def test_cors_preflight(self, client: httpx.AsyncClient):
        """OPTIONS request through Starlette returns proper CORS headers."""
        task_id = str(uuid4())
        resp = await client.options(
            f"/api/results/{task_id}/download-token",
        )
        assert resp.status_code == 204
        assert resp.headers["access-control-allow-origin"] == "*"
        assert resp.headers["access-control-allow-methods"] == "GET"
        assert resp.headers["access-control-allow-headers"] == "Authorization"
        assert resp.headers["access-control-max-age"] == "3600"

    @pytest.mark.asyncio
    async def test_query_param_rejected_through_real_url(
        self, client: httpx.AsyncClient
    ):
        """Poll token via ?token= query param in a real URL is rejected."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json.dumps([{"a": 1}]))

        resp = await client.get(
            f"/api/results/{task_id}/download-token",
            params={"token": poll_token},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_multiple_mints_produce_distinct_tokens(
        self, client: httpx.AsyncClient
    ):
        """Two sequential mints for the same task produce different download tokens."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json.dumps([{"col": "val"}]))

        headers = {"Authorization": f"Bearer {poll_token}"}
        resp1 = await client.get(
            f"/api/results/{task_id}/download-token", headers=headers
        )
        resp2 = await client.get(
            f"/api/results/{task_id}/download-token", headers=headers
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        url1 = resp1.json()["download_url"]
        url2 = resp2.json()["download_url"]
        assert url1 != url2

    @pytest.mark.asyncio
    async def test_minted_token_is_reusable(self, client: httpx.AsyncClient):
        """Mint → download (200) → download again with same token (200)."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        json_text = json.dumps([{"x": 1, "y": 2}])
        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")
        await redis_store.store_result_json(task_id, json_text)

        # Mint
        mint_resp = await client.get(
            f"/api/results/{task_id}/download-token",
            headers={"Authorization": f"Bearer {poll_token}"},
        )
        assert mint_resp.status_code == 200
        dl_token = mint_resp.json()["download_url"].split("token=")[1]

        # First download succeeds
        resp1 = await client.get(
            f"/api/results/{task_id}/download", params={"token": dl_token}
        )
        assert resp1.status_code == 200

        # Second download with same token also succeeds
        resp2 = await client.get(
            f"/api/results/{task_id}/download", params={"token": dl_token}
        )
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_wrong_task_id_rejected(self, client: httpx.AsyncClient):
        """Token minted for task A, used on task B's URL → 403; still works for A."""
        task_a = str(uuid4())
        task_b = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        json_text = json.dumps([{"v": 1}])

        await redis_store.store_poll_token(task_a, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_a, "test-user")
        await redis_store.store_result_json(task_a, json_text)
        await redis_store.store_result_json(task_b, json_text)

        # Mint for task A
        mint_resp = await client.get(
            f"/api/results/{task_a}/download-token",
            headers={"Authorization": f"Bearer {poll_token}"},
        )
        dl_token = mint_resp.json()["download_url"].split("token=")[1]

        # Try on task B → 403
        resp_b = await client.get(
            f"/api/results/{task_b}/download", params={"token": dl_token}
        )
        assert resp_b.status_code == 403

        # Token not consumed — still works for task A
        resp_a = await client.get(
            f"/api/results/{task_a}/download", params={"token": dl_token}
        )
        assert resp_a.status_code == 200


# ── Download-token lifecycle ─────────────────────────────────


class TestDownloadTokenLifecycle:
    """Full lifecycle: store results via result_store → extract widget data →
    mint fresh download token → download CSV.

    This simulates the real user journey: the MCP tool stores results,
    the widget receives the JSON (with poll_token + download_token_url),
    the user clicks "Download CSV", the widget calls the minting endpoint,
    and the browser downloads the file.
    """

    @pytest.mark.asyncio
    async def test_store_result_to_download(self, client: httpx.AsyncClient):
        """End-to-end: try_store_result → widget JSON → mint → download."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        csv_data = {"name": ["Alice", "Bob"], "score": [95, 87]}
        df = pd.DataFrame(csv_data)

        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")

        # 1. Store results (simulates what futuresearch_results tool does)
        result = await try_store_result(
            task_id, df, 0, 10, mcp_server_url="http://testserver"
        )
        assert result is not None

        # 2. Parse widget data — structuredContent is sent to the client, not the LLM
        widget = result.structuredContent
        assert widget is not None
        assert "poll_token" in widget
        assert "download_token_url" in widget
        assert widget["download_token_url"] == (
            f"http://testserver/api/results/{task_id}/download-token"
        )

        # 3. Widget calls download-token endpoint (simulates getFreshDownloadUrl)
        mint_resp = await client.get(
            widget["download_token_url"],
            headers={"Authorization": f"Bearer {widget['poll_token']}"},
        )
        assert mint_resp.status_code == 200
        download_url = mint_resp.json()["download_url"]
        assert f"/api/results/{task_id}/download?token=" in download_url

        # 4. Browser follows the download URL
        dl_token = download_url.split("token=")[1]
        dl_resp = await client.get(
            f"/api/results/{task_id}/download", params={"token": dl_token}
        )
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "text/csv; charset=utf-8"

        # Verify the downloaded CSV matches the original data
        downloaded_df = pd.read_csv(StringIO(dl_resp.text))
        assert list(downloaded_df.columns) == ["name", "score"]
        assert len(downloaded_df) == 2

    @pytest.mark.asyncio
    async def test_baked_token_reusable_and_mint_also_works(
        self, client: httpx.AsyncClient
    ):
        """Baked-in download token is reusable; minting a fresh one also works."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        df = pd.DataFrame({"col": [1, 2, 3]})

        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")

        result = await try_store_result(
            task_id, df, 0, 10, mcp_server_url="http://testserver"
        )
        assert result is not None
        widget = result.structuredContent
        assert widget is not None

        # First download with baked-in token
        baked_token = widget["csv_url"].split("token=")[1]
        resp1 = await client.get(
            f"/api/results/{task_id}/download", params={"token": baked_token}
        )
        assert resp1.status_code == 200

        # Second download with same baked-in token also succeeds
        resp2 = await client.get(
            f"/api/results/{task_id}/download", params={"token": baked_token}
        )
        assert resp2.status_code == 200

        # Minting a fresh token via the endpoint also works
        mint_resp = await client.get(
            widget["download_token_url"],
            headers={"Authorization": f"Bearer {widget['poll_token']}"},
        )
        assert mint_resp.status_code == 200
        fresh_url = mint_resp.json()["download_url"]
        fresh_token = fresh_url.split("token=")[1]

        resp3 = await client.get(
            f"/api/results/{task_id}/download", params={"token": fresh_token}
        )
        assert resp3.status_code == 200

    @pytest.mark.asyncio
    async def test_cached_result_also_includes_mint_data(
        self, client: httpx.AsyncClient
    ):
        """try_cached_result also populates poll_token + download_token_url."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)
        df = pd.DataFrame({"a": [1, 2]})

        await redis_store.store_poll_token(task_id, poll_token, user_id="test-user")
        await redis_store.store_task_owner(task_id, "test-user")

        # Store once to populate Redis cache
        await try_store_result(task_id, df, 0, 10, mcp_server_url="http://testserver")

        # Now read from cache
        cached = await try_cached_result(
            task_id, 0, 10, mcp_server_url="http://testserver"
        )
        assert cached is not None

        widget = cached.structuredContent
        assert widget is not None
        assert widget["poll_token"] == poll_token
        assert f"/api/results/{task_id}/download-token" in widget["download_token_url"]

        # Verify the cached poll_token can mint a fresh download token
        mint_resp = await client.get(
            widget["download_token_url"],
            headers={"Authorization": f"Bearer {widget['poll_token']}"},
        )
        assert mint_resp.status_code == 200

"""Tests for Redis-backed result retrieval (result_store.py).

Covers pure helpers (_format_columns, _slice_preview, _build_result_response)
and async functions (try_cached_result, try_store_result) with patched Redis,
plus the download endpoint (api_download).
"""

from __future__ import annotations

import io
import json
import secrets
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings
from everyrow_mcp.result_store import (
    _build_result_response,
    _estimate_tokens,
    _format_columns,
    clamp_page_to_budget,
    try_cached_result,
    try_store_result,
)
from everyrow_mcp.routes import api_download
from tests.conftest import override_settings

# ── Fixtures ───────────────────────────────────────────────────

FAKE_SERVER_URL = "http://testserver"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Alice", "Bob", "Carol"], "score": [95, 87, 72]})


@pytest.fixture
def _http_state(fake_redis):
    """Configure settings for HTTP mode and patch Redis."""
    with (
        override_settings(transport="streamable-http", upload_secret="test-secret"),
        patch.object(redis_store, "get_redis_client", return_value=fake_redis),
    ):
        yield


# ── Pure helpers ───────────────────────────────────────────────


class TestFormatColumns:
    def test_few_columns(self):
        assert _format_columns(["a", "b", "c"]) == "a, b, c"

    def test_exactly_ten(self):
        cols = [f"c{i}" for i in range(10)]
        result = _format_columns(cols)
        assert result == ", ".join(cols)
        assert "more" not in result

    def test_more_than_ten(self):
        cols = [f"c{i}" for i in range(15)]
        result = _format_columns(cols)
        assert "(+5 more)" in result
        # First 10 should still be present
        for c in cols[:10]:
            assert c in result


class TestBuildResultResponse:
    def test_all_rows_shown(self):
        preview = [{"name": "Alice"}, {"name": "Bob"}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-123/download?token=abc"
        result = _build_result_response(
            task_id="task-123",
            csv_url=csv_url,
            preview_records=preview,
            total=2,
            columns=["name"],
            offset=0,
            page_size=10,
        )
        assert len(result) == 2
        widget = json.loads(result[0].text)
        assert widget["total"] == 2
        assert widget["csv_url"] == csv_url
        assert "All rows shown" in result[1].text

    def test_has_more_pages(self):
        preview = [{"id": i} for i in range(5)]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-456/download?token=abc"
        result = _build_result_response(
            task_id="task-456",
            csv_url=csv_url,
            preview_records=preview,
            total=20,
            columns=["id"],
            offset=0,
            page_size=5,
        )
        summary = result[1].text
        assert "20 rows" in summary
        assert "offset=5" in summary
        assert "everyrow_results" in summary
        # First page includes CSV download link
        assert csv_url in summary

    def test_final_page(self):
        preview = [{"id": 18}, {"id": 19}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-789/download?token=abc"
        result = _build_result_response(
            task_id="task-789",
            csv_url=csv_url,
            preview_records=preview,
            total=20,
            columns=["id"],
            offset=18,
            page_size=5,
        )
        summary = result[1].text
        assert "final page" in summary

    def test_session_url_included_in_widget(self):
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-url/download?token=abc"
        result = _build_result_response(
            task_id="task-url",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
            session_url="https://everyrow.io/sessions/abc",
        )
        widget = json.loads(result[0].text)
        assert widget["session_url"] == "https://everyrow.io/sessions/abc"

    def test_no_session_url_when_empty(self):
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-nurl/download?token=abc"
        result = _build_result_response(
            task_id="task-nurl",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
        )
        widget = json.loads(result[0].text)
        assert "session_url" not in widget

    def test_next_page_hint_uses_requested_page_size(self):
        """When clamped, the next-page hint should use the original page_size."""
        preview = [{"id": i} for i in range(3)]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-hint/download?token=abc"
        result = _build_result_response(
            task_id="task-hint",
            csv_url=csv_url,
            preview_records=preview,
            total=20,
            columns=["id"],
            offset=0,
            page_size=3,  # effective (clamped) size
            requested_page_size=10,  # user's original request
        )
        summary = result[1].text
        # The hint should suggest the user's original page_size, not the clamped one
        assert "page_size=10" in summary
        # Offset should advance by effective page_size (what was actually shown)
        assert "offset=3" in summary

    def test_next_page_hint_defaults_to_page_size(self):
        """Without requested_page_size, the hint uses page_size."""
        preview = [{"id": i} for i in range(5)]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-def/download?token=abc"
        result = _build_result_response(
            task_id="task-def",
            csv_url=csv_url,
            preview_records=preview,
            total=20,
            columns=["id"],
            offset=0,
            page_size=5,
        )
        summary = result[1].text
        assert "page_size=5" in summary

    def test_poll_token_included_in_widget(self):
        """When poll_token and mcp_server_url are provided, widget JSON includes them."""
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-poll/download?token=abc"
        result = _build_result_response(
            task_id="task-poll",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
            poll_token="my-poll-token",
            mcp_server_url=FAKE_SERVER_URL,
        )
        widget = json.loads(result[0].text)
        assert widget["poll_token"] == "my-poll-token"
        assert (
            widget["download_token_url"]
            == f"{FAKE_SERVER_URL}/api/results/task-poll/download-token"
        )

    def test_no_poll_token_when_empty(self):
        """When poll_token is empty, widget JSON omits poll_token and download_token_url."""
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-nopoll/download?token=abc"
        result = _build_result_response(
            task_id="task-nopoll",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
        )
        widget = json.loads(result[0].text)
        assert "poll_token" not in widget
        assert "download_token_url" not in widget


# ── Async functions ────────────────────────────────────────────


class TestTryCachedResult:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_cached_meta(self, _http_state):
        result = await try_cached_result(
            "task-2", 0, 10, mcp_server_url=FAKE_SERVER_URL
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_page(self, _http_state):
        meta = json.dumps({"total": 3, "columns": ["name", "score"]})
        page = json.dumps([{"name": "Alice", "score": 95}])
        task_id = "task-3"
        poll_token = "test-token"

        await redis_store.store_result_meta(task_id, meta)
        await redis_store.store_result_page(task_id, 0, 1, page)
        await redis_store.store_poll_token(task_id, poll_token)

        result = await try_cached_result(task_id, 0, 1, mcp_server_url=FAKE_SERVER_URL)

        assert result is not None
        assert len(result) == 2
        widget = json.loads(result[0].text)
        assert widget["total"] == 3

    @pytest.mark.asyncio
    async def test_reads_csv_on_page_miss(self, _http_state):
        meta = json.dumps({"total": 3, "columns": ["name", "score"]})
        csv_text = "name,score\nAlice,95\nBob,87\nCarol,72\n"
        task_id = "task-4"

        await redis_store.store_result_meta(task_id, meta)
        await redis_store.store_result_csv(task_id, csv_text)
        await redis_store.store_poll_token(task_id, "test-token")

        result = await try_cached_result(task_id, 0, 2, mcp_server_url=FAKE_SERVER_URL)

        assert result is not None
        widget = json.loads(result[0].text)
        assert len(widget["preview"]) == 2

    @pytest.mark.asyncio
    async def test_preserves_session_url_from_meta(self, _http_state):
        meta = json.dumps(
            {
                "total": 1,
                "columns": ["a"],
                "session_url": "https://everyrow.io/sessions/xyz",
            }
        )
        page = json.dumps([{"a": 1}])
        task_id = "task-5"

        await redis_store.store_result_meta(task_id, meta)
        await redis_store.store_result_page(task_id, 0, 10, page)
        await redis_store.store_poll_token(task_id, "test-token")

        result = await try_cached_result(task_id, 0, 10, mcp_server_url=FAKE_SERVER_URL)

        assert result is not None
        widget = json.loads(result[0].text)
        assert widget["session_url"] == "https://everyrow.io/sessions/xyz"

    @pytest.mark.asyncio
    async def test_returns_none_when_csv_expired(self, _http_state):
        """When metadata exists but CSV is gone, fall back to API (return None)."""
        task_id = "task-csv-expired"
        meta = json.dumps({"total": 5, "columns": ["a", "b"]})
        await redis_store.store_result_meta(task_id, meta)
        # No CSV stored, no page cached

        result = await try_cached_result(task_id, 0, 5, mcp_server_url=FAKE_SERVER_URL)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_csv_read_fails(self, _http_state):
        """When CSV read raises, fall back to API (return None)."""
        task_id = "task-csv-error"
        meta = json.dumps({"total": 5, "columns": ["a"]})
        await redis_store.store_result_meta(task_id, meta)

        with patch(
            "everyrow_mcp.result_store.redis_store.get_result_csv",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Redis connection lost"),
        ):
            result = await try_cached_result(
                task_id, 0, 5, mcp_server_url=FAKE_SERVER_URL
            )
        assert result is None


class TestTryStoreResult:
    @pytest.mark.asyncio
    async def test_stores_and_returns_response(self, sample_df, _http_state):
        task_id = "task-up"
        await redis_store.store_poll_token(task_id, "test-token")

        result = await try_store_result(
            task_id, sample_df, 0, 2, mcp_server_url=FAKE_SERVER_URL
        )

        assert result is not None
        assert len(result) == 2
        widget = json.loads(result[0].text)
        assert widget["total"] == 3
        assert len(widget["preview"]) == 2

        # Verify CSV was stored in Redis
        stored_csv = await redis_store.get_result_csv(task_id)
        assert stored_csv is not None
        df = pd.read_csv(io.StringIO(stored_csv))
        assert len(df) == 3

        # Verify metadata was cached
        meta_raw = await redis_store.get_result_meta(task_id)
        assert meta_raw is not None
        meta = json.loads(meta_raw)
        assert meta["total"] == 3
        assert meta["columns"] == ["name", "score"]

    @pytest.mark.asyncio
    async def test_includes_session_url_in_meta(self, sample_df, _http_state):
        task_id = "task-sess"
        await redis_store.store_poll_token(task_id, "test-token")

        await try_store_result(
            task_id,
            sample_df,
            0,
            10,
            session_url="https://everyrow.io/sessions/abc",
            mcp_server_url=FAKE_SERVER_URL,
        )

        meta_raw = await redis_store.get_result_meta(task_id)
        assert meta_raw is not None
        meta = json.loads(meta_raw)
        assert meta["session_url"] == "https://everyrow.io/sessions/abc"

    @pytest.mark.asyncio
    async def test_raises_on_redis_failure(self, sample_df, _http_state):
        with (
            patch(
                "everyrow_mcp.result_store.redis_store.store_result_csv",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Redis down"),
            ),
            pytest.raises(RuntimeError, match="Redis down"),
        ):
            await try_store_result(
                "task-fail", sample_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
            )

    @pytest.mark.asyncio
    async def test_widget_includes_poll_token_and_download_url(
        self, sample_df, _http_state
    ):
        """try_store_result populates poll_token and download_token_url in widget JSON."""
        task_id = "task-widget-poll"
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)

        result = await try_store_result(
            task_id, sample_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
        )
        assert result is not None
        widget = json.loads(result[0].text)

        assert widget["poll_token"] == poll_token
        assert widget["download_token_url"] == (
            f"{FAKE_SERVER_URL}/api/results/{task_id}/download-token"
        )

    @pytest.mark.asyncio
    async def test_cached_result_includes_poll_token(self, sample_df, _http_state):
        """try_cached_result also populates poll_token and download_token_url."""
        task_id = "task-cached-poll"
        poll_token = secrets.token_urlsafe(16)
        await redis_store.store_poll_token(task_id, poll_token)

        # Store first to populate Redis cache
        await try_store_result(
            task_id, sample_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
        )

        # Read from cache
        cached = await try_cached_result(task_id, 0, 10, mcp_server_url=FAKE_SERVER_URL)
        assert cached is not None
        widget = json.loads(cached[0].text)

        assert widget["poll_token"] == poll_token
        assert f"/api/results/{task_id}/download-token" in widget["download_token_url"]

    @pytest.mark.asyncio
    async def test_download_token_url_matches_expected_shape(
        self, sample_df, _http_state
    ):
        """The download_token_url is exactly {mcp_server_url}/api/results/{task_id}/download-token."""
        task_id = "task-url-shape"
        await redis_store.store_poll_token(task_id, "tok")

        result = await try_store_result(
            task_id, sample_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
        )
        assert result is not None
        widget = json.loads(result[0].text)

        expected = f"{FAKE_SERVER_URL}/api/results/{task_id}/download-token"
        assert widget["download_token_url"] == expected
        # Must not contain query params (token is sent via header, not URL)
        assert "?" not in widget["download_token_url"]


# ── Download endpoint ──────────────────────────────────────────


class TestApiDownload:
    @pytest.fixture
    def app(self, _http_state):
        return Starlette(
            routes=[
                Route(
                    "/api/results/{task_id}/download",
                    api_download,
                    methods=["GET", "OPTIONS"],
                ),
            ],
        )

    @pytest.fixture
    async def client(self, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            yield c

    @pytest.mark.asyncio
    async def test_valid_download(self, client: httpx.AsyncClient):
        task_id = str(uuid4())
        download_token = secrets.token_urlsafe(32)
        csv_text = "name,score\nAlice,95\nBob,87\n"

        await redis_store.store_download_token(download_token, task_id)
        await redis_store.store_result_csv(task_id, csv_text)

        resp = await client.get(
            f"/api/results/{task_id}/download", params={"token": download_token}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.text == csv_text

    @pytest.mark.asyncio
    async def test_bad_token_returns_403(self, client: httpx.AsyncClient):
        task_id = str(uuid4())

        await redis_store.store_result_csv(task_id, "data")

        resp = await client.get(
            f"/api/results/{task_id}/download", params={"token": "wrong-token"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_denied_without_owner(self, client: httpx.AsyncClient):
        """Valid poll token but no task owner → fail-closed 403."""
        task_id = str(uuid4())
        download_token = secrets.token_urlsafe(32)

        await redis_store.store_download_token(download_token, task_id)
        # No CSV stored

        resp = await client.get(
            f"/api/results/{task_id}/download", params={"token": download_token}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_token_consumed_after_use(self, client: httpx.AsyncClient):
        """A download token can only be used once — second request returns 403."""
        task_id = str(uuid4())
        download_token = secrets.token_urlsafe(32)
        csv_text = "a,b\n1,2\n"

        await redis_store.store_download_token(download_token, task_id)
        await redis_store.store_result_csv(task_id, csv_text)

        resp1 = await client.get(
            f"/api/results/{task_id}/download", params={"token": download_token}
        )
        assert resp1.status_code == 200

        resp2 = await client.get(
            f"/api/results/{task_id}/download", params={"token": download_token}
        )
        assert resp2.status_code == 403

    @pytest.mark.asyncio
    async def test_task_id_mismatch_restores_token(self, client: httpx.AsyncClient):
        """Token for task A used on task B's URL → 403, token still valid for A."""
        task_a = str(uuid4())
        task_b = str(uuid4())
        download_token = secrets.token_urlsafe(32)
        csv_text = "x\n1\n"

        await redis_store.store_download_token(download_token, task_a)
        await redis_store.store_result_csv(task_a, csv_text)
        await redis_store.store_result_csv(task_b, csv_text)

        # Use task_a's token on task_b's URL
        resp = await client.get(
            f"/api/results/{task_b}/download", params={"token": download_token}
        )
        assert resp.status_code == 403

        # Token should have been restored — still works for task_a
        resp2 = await client.get(
            f"/api/results/{task_a}/download", params={"token": download_token}
        )
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_poll_token_cannot_download(self, client: httpx.AsyncClient):
        """A poll token used in the download URL should be rejected."""
        task_id = str(uuid4())
        poll_token = secrets.token_urlsafe(16)

        await redis_store.store_poll_token(task_id, poll_token)
        await redis_store.store_result_csv(task_id, "col\nval\n")

        resp = await client.get(
            f"/api/results/{task_id}/download", params={"token": poll_token}
        )
        assert resp.status_code == 403


# ── Token budget clamping ─────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_basic_estimate(self):
        # 100 chars → ~25 tokens
        assert _estimate_tokens("a" * 100) == 25

    def test_json_content(self):
        data = json.dumps([{"name": "Alice", "score": 95}])
        # Should be roughly len(data) // 4
        assert _estimate_tokens(data) == len(data) // 4


class TestClampPageToBudget:
    def test_within_budget_returns_full_page(self):
        preview = [{"id": i} for i in range(5)]
        with override_settings(token_budget=100_000):
            result, effective_size = clamp_page_to_budget(preview, 5)
        assert result == preview
        assert effective_size == 5

    def test_empty_preview(self):
        with override_settings(token_budget=100):
            result, effective_size = clamp_page_to_budget([], 10)
        assert result == []
        assert effective_size == 10

    def test_over_budget_reduces_page(self):
        # Create rows with long text that will exceed a small budget
        preview = [{"text": "x" * 1000} for _ in range(20)]
        budget = 500  # ~2000 chars budget → fits ~1-2 rows
        with override_settings(token_budget=budget):
            result, effective_size = clamp_page_to_budget(preview, 20)
        assert effective_size < 20
        assert len(result) == effective_size
        # Verify the clamped result fits within budget
        assert _estimate_tokens(json.dumps(result)) <= budget

    def test_never_reduces_below_one(self):
        # Single huge row that exceeds budget
        preview = [{"text": "x" * 100_000}]
        with override_settings(token_budget=100):
            result, effective_size = clamp_page_to_budget(preview, 1)
        assert effective_size == 1
        assert len(result) == 1

    def test_finds_optimal_page_size(self):
        # Each row is ~40 chars → ~10 tokens.  Budget of 50 tokens
        # (~200 chars) should fit only a handful of 20 rows.
        preview = [{"name": f"Person_{i:03d}", "score": i * 10} for i in range(20)]
        full_tokens = _estimate_tokens(json.dumps(preview))
        # Sanity: the full preview must actually exceed the budget
        budget = full_tokens // 3
        with override_settings(token_budget=budget):
            result, effective_size = clamp_page_to_budget(preview, 20)
        assert effective_size < 20
        # Verify it fits
        assert _estimate_tokens(json.dumps(result)) <= budget
        # Verify adding one more row would exceed
        if effective_size < len(preview):
            over = preview[: effective_size + 1]
            assert _estimate_tokens(json.dumps(over)) > budget


class TestTokenBudgetIntegration:
    """Integration tests verifying token budget clamping in try_store_result and try_cached_result."""

    @pytest.fixture
    def wide_df(self) -> pd.DataFrame:
        """DataFrame with wide text columns that will blow the token budget."""
        return pd.DataFrame(
            {
                "id": range(10),
                "research": [f"Long research text {'x' * 2000}" for _ in range(10)],
                "summary": [f"Summary {'y' * 500}" for _ in range(10)],
            }
        )

    @pytest.mark.asyncio
    async def test_try_store_clamps_page(self, wide_df, _http_state):
        task_id = "task-budget-store"
        await redis_store.store_poll_token(task_id, "tok")

        orig = settings.token_budget
        settings.token_budget = 2000
        try:
            result = await try_store_result(
                task_id, wide_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
            )
        finally:
            settings.token_budget = orig

        assert result is not None
        widget = json.loads(result[0].text)
        # Should have fewer than 10 rows due to clamping
        assert len(widget["preview"]) < 10
        # Verify the preview fits within the budget
        assert _estimate_tokens(json.dumps(widget["preview"])) <= 2000

    @pytest.mark.asyncio
    async def test_try_cached_clamps_page(self, wide_df, _http_state):
        task_id = "task-budget-cached"
        await redis_store.store_poll_token(task_id, "tok")

        # Store CSV and metadata first (with normal budget)
        csv_text = wide_df.to_csv(index=False)
        await redis_store.store_result_csv(task_id, csv_text)
        meta = json.dumps({"total": len(wide_df), "columns": list(wide_df.columns)})
        await redis_store.store_result_meta(task_id, meta)

        orig = settings.token_budget
        settings.token_budget = 2000
        try:
            result = await try_cached_result(
                task_id, 0, 10, mcp_server_url=FAKE_SERVER_URL
            )
        finally:
            settings.token_budget = orig

        assert result is not None
        widget = json.loads(result[0].text)
        assert len(widget["preview"]) < 10
        assert _estimate_tokens(json.dumps(widget["preview"])) <= 2000

    @pytest.mark.asyncio
    async def test_large_budget_preserves_full_page(self, _http_state):
        """With a large budget, the full page_size is returned."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        task_id = "task-budget-ok"
        await redis_store.store_poll_token(task_id, "tok")

        orig = settings.token_budget
        settings.token_budget = 100_000
        try:
            result = await try_store_result(
                task_id, df, 0, 3, mcp_server_url=FAKE_SERVER_URL
            )
        finally:
            settings.token_budget = orig

        assert result is not None
        widget = json.loads(result[0].text)
        assert len(widget["preview"]) == 3

    @pytest.mark.asyncio
    async def test_clamped_hint_preserves_original_page_size(
        self, wide_df, _http_state
    ):
        """Next-page hint uses user's original page_size, not the clamped one."""
        task_id = "task-hint-preserve"
        await redis_store.store_poll_token(task_id, "tok")

        with override_settings(token_budget=2000):
            result = await try_store_result(
                task_id, wide_df, 0, 10, mcp_server_url=FAKE_SERVER_URL
            )

        assert result is not None
        summary = result[1].text
        # The hint should suggest the user's original page_size=10
        assert "page_size=10" in summary


# ── Widget results_url ──────────────────────────────────────


class TestWidgetResultsUrl:
    @pytest.mark.asyncio
    async def test_store_result_includes_results_url(self, sample_df, _http_state):
        task_id = "task-widget-url"
        await redis_store.store_poll_token(task_id, "test-token")

        result = await try_store_result(
            task_id,
            sample_df,
            0,
            50,
            mcp_server_url=FAKE_SERVER_URL,
        )

        widget = json.loads(result[0].text)
        assert "results_url" in widget
        assert "format=json" in widget["results_url"]

    @pytest.mark.asyncio
    async def test_cached_result_includes_results_url(self, sample_df, _http_state):
        task_id = "task-widget-cached"
        await redis_store.store_poll_token(task_id, "test-token")

        await try_store_result(
            task_id, sample_df, 0, 50, mcp_server_url=FAKE_SERVER_URL
        )

        cached = await try_cached_result(task_id, 0, 50, mcp_server_url=FAKE_SERVER_URL)

        assert cached is not None
        widget = json.loads(cached[0].text)
        assert "results_url" in widget
        assert "format=json" in widget["results_url"]

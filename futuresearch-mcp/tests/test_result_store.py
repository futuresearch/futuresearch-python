"""Tests for result response building (result_store.py).

Covers pure helpers (_format_columns, _build_result_response, clamp_page_to_budget,
resolve_citations_in_records) and the download endpoint (api_download).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.routing import Route

from futuresearch_mcp import redis_store
from futuresearch_mcp.result_store import (
    _build_result_response,
    _estimate_tokens,
    _format_columns,
    _sanitize_records,
    clamp_page_to_budget,
)
from futuresearch_mcp.routes import api_download
from tests.conftest import override_settings

# ── Test helpers ──────────────────────────────────────────────


def _widget(result: CallToolResult) -> dict[str, Any]:
    """Extract structuredContent with a non-None assertion (for pyright)."""
    assert result.structuredContent is not None
    return result.structuredContent


def _text(result: CallToolResult, idx: int = 0) -> str:
    """Extract text from a content block with type narrowing (for pyright)."""
    block = result.content[idx]
    assert isinstance(block, TextContent)
    return block.text


# ── Fixtures ───────────────────────────────────────────────────

FAKE_SERVER_URL = "http://testserver"


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
        widget = _widget(result)
        assert widget["total"] == 2
        assert widget["csv_url"] == csv_url
        assert "All rows shown" in _text(result)

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
        summary = _text(result)
        assert "20 rows" in summary
        assert "offset=5" in summary
        assert "futuresearch_results" in summary
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
        # No widget JSON for non-first pages
        assert result.structuredContent is None
        assert "final page" in _text(result)

    def test_no_widget_json_on_subsequent_pages(self):
        """Widget JSON is only emitted on the first page (offset=0)."""
        preview = [{"id": i} for i in range(5)]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-pg2/download?token=abc"
        result = _build_result_response(
            task_id="task-pg2",
            csv_url=csv_url,
            preview_records=preview,
            total=20,
            columns=["id"],
            offset=5,
            page_size=5,
        )
        assert result.structuredContent is None
        # Should be the text summary, not JSON
        assert "Showing rows" in _text(result)

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
        summary = _text(result)
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
        summary = _text(result)
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
        widget = _widget(result)
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
        widget = _widget(result)
        assert "poll_token" not in widget
        assert "download_token_url" not in widget

    def test_artifact_id_included_in_widget_and_text(self):
        """When artifact_id is provided, it appears in widget JSON and text summary."""
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-aid/download?token=abc"
        result = _build_result_response(
            task_id="task-aid",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
            artifact_id="abc-123-def",
        )
        widget = _widget(result)
        assert widget["artifact_id"] == "abc-123-def"
        assert "abc-123-def" in _text(result)
        assert "Output artifact_id" in _text(result)

    def test_no_artifact_id_when_empty(self):
        """When artifact_id is empty, widget JSON and text omit it."""
        preview = [{"a": 1}]
        csv_url = f"{FAKE_SERVER_URL}/api/results/task-noaid/download?token=abc"
        result = _build_result_response(
            task_id="task-noaid",
            csv_url=csv_url,
            preview_records=preview,
            total=1,
            columns=["a"],
            offset=0,
            page_size=10,
        )
        widget = _widget(result)
        assert "artifact_id" not in widget
        assert "Output artifact_id" not in _text(result)


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
        await redis_store.store_task_token(task_id, "sk-cho-test")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 87},
            ],
            "status": "completed",
        }
        mock_http = AsyncMock()
        mock_http.__aenter__.return_value.get.return_value = mock_resp

        with patch(
            "futuresearch_mcp.routes.httpx.AsyncClient",
            return_value=mock_http,
        ):
            resp = await client.get(f"/api/results/{task_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in resp.headers["content-disposition"]
        assert "Alice" in resp.text
        assert "Bob" in resp.text

    @pytest.mark.asyncio
    async def test_json_format_returns_json(self, client: httpx.AsyncClient):
        """?format=json returns a JSON array fetched from the Engine."""
        task_id = str(uuid4())
        await redis_store.store_task_token(task_id, "sk-cho-test")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 87},
            ],
            "status": "completed",
        }
        mock_http = AsyncMock()
        mock_http.__aenter__.return_value.get.return_value = mock_resp

        with patch(
            "futuresearch_mcp.routes.httpx.AsyncClient",
            return_value=mock_http,
        ):
            resp = await client.get(
                f"/api/results/{task_id}/download",
                params={"format": "json"},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert resp.headers.get("x-content-type-options") == "nosniff"
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self, client: httpx.AsyncClient):
        """?format=xml or any unknown value returns 400."""
        task_id = str(uuid4())

        resp = await client.get(
            f"/api/results/{task_id}/download",
            params={"format": "xml"},
        )
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["error"]


# ── Token budget clamping ─────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_basic_estimate(self):
        # tiktoken encodes "a" * 100 into BPE tokens (exact count varies)
        result = _estimate_tokens("a" * 100)
        assert result > 0
        # Should be significantly fewer tokens than characters
        assert result < 100

    def test_json_content(self):
        data = json.dumps([{"name": "Alice", "score": 95}])
        result = _estimate_tokens(data)
        assert result > 0
        # tiktoken gives a more accurate (lower) count than len//4
        assert result < len(data)


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
        # Create rows with enough text to make token counts meaningful.
        preview = [
            {"name": f"Person_{i:03d}", "bio": f"A person number {i} with details"}
            for i in range(20)
        ]
        full_tokens = _estimate_tokens(json.dumps(preview))
        # Sanity: the full preview must actually exceed the budget
        budget = full_tokens // 3
        with override_settings(token_budget=budget):
            result, effective_size = clamp_page_to_budget(preview, 20)
        assert effective_size < 20
        # Verify it fits within budget
        assert _estimate_tokens(json.dumps(result)) <= budget


class TestSanitizeRecords:
    def test_replaces_nan_with_none(self):
        records = [{"a": float("nan"), "b": 1.0, "c": "text"}]
        result = _sanitize_records(records)
        assert result[0]["a"] is None
        assert result[0]["b"] == 1.0
        assert result[0]["c"] == "text"

    def test_replaces_inf_with_none(self):
        records = [{"a": float("inf"), "b": float("-inf")}]
        result = _sanitize_records(records)
        assert result[0]["a"] is None
        assert result[0]["b"] is None

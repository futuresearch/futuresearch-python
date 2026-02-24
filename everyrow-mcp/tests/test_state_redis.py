"""Tests for redis_store standalone functions and Settings transport properties."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from everyrow_mcp import redis_store
from everyrow_mcp.config import Settings


@pytest.fixture(autouse=True)
def _use_fake_redis(fake_redis):
    """Patch get_redis_client to return the test Redis instance."""
    with patch.object(redis_store, "get_redis_client", return_value=fake_redis):
        yield


class TestTaskTokenRoundTrip:
    """store_task_token -> get_task_token -> pop_task_token"""

    @pytest.mark.asyncio
    async def test_store_and_get(self):
        await redis_store.store_task_token("task-1", "api-key-abc")
        result = await redis_store.get_task_token("task-1")
        assert result == "api-key-abc"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        result = await redis_store.get_task_token("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_pop_removes_task_token_only(self):
        await redis_store.store_task_token("task-2", "key")
        await redis_store.store_poll_token("task-2", "poll-tok")

        await redis_store.pop_task_token("task-2")

        assert await redis_store.get_task_token("task-2") is None
        # Poll token is kept — needed for CSV download after task completes
        assert await redis_store.get_poll_token("task-2") == "poll-tok"


class TestPollTokenRoundTrip:
    """store_poll_token -> get_poll_token"""

    @pytest.mark.asyncio
    async def test_store_and_get(self):
        await redis_store.store_poll_token("task-p", "poll-secret")
        result = await redis_store.get_poll_token("task-p")
        assert result == "poll-secret"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        result = await redis_store.get_poll_token("ghost")
        assert result is None


class TestResultMetaRoundTrip:
    """store_result_meta -> get_result_meta"""

    @pytest.mark.asyncio
    async def test_store_and_get(self):
        meta = json.dumps({"total": 42, "columns": ["a", "b"]})
        await redis_store.store_result_meta("task-m", meta)

        raw = await redis_store.get_result_meta("task-m")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed["total"] == 42
        assert parsed["columns"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        result = await redis_store.get_result_meta("nope")
        assert result is None


class TestResultPageRoundTrip:
    """store_result_page -> get_result_page"""

    @pytest.mark.asyncio
    async def test_store_and_get(self):
        page = json.dumps([{"id": 1}, {"id": 2}])
        await redis_store.store_result_page("task-pg", 0, 10, page)

        result = await redis_store.get_result_page("task-pg", 0, 10)
        assert result is not None
        assert json.loads(result) == [{"id": 1}, {"id": 2}]

    @pytest.mark.asyncio
    async def test_different_offsets_are_independent(self):
        page0 = json.dumps([{"row": 0}])
        page10 = json.dumps([{"row": 10}])
        await redis_store.store_result_page("task-multi", 0, 10, page0)
        await redis_store.store_result_page("task-multi", 10, 10, page10)

        assert json.loads(await redis_store.get_result_page("task-multi", 0, 10)) == [
            {"row": 0}
        ]
        assert json.loads(await redis_store.get_result_page("task-multi", 10, 10)) == [
            {"row": 10}
        ]

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        result = await redis_store.get_result_page("nothing", 0, 10)
        assert result is None


class TestSettingsTransport:
    """Settings transport properties."""

    def test_is_stdio_by_default(self):
        s = Settings()  # pyright: ignore[reportCallIssue]
        assert s.is_stdio is True
        assert s.is_http is False

    def test_transport_http(self):
        s = Settings(transport="streamable-http")  # pyright: ignore[reportCallIssue]
        assert s.is_http is True
        assert s.is_stdio is False

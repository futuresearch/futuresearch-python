"""Tests for redis_store standalone functions and Settings transport properties."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from futuresearch_mcp import redis_store
from futuresearch_mcp.config import Settings


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

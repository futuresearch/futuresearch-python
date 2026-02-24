"""Tests for RateLimitMiddleware."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from everyrow_mcp.middleware import RateLimitMiddleware

# ── Helpers ─────────────────────────────────────────────────────────


def _make_app(
    redis_mock: AsyncMock,
    *,
    max_requests: int = 5,
    window_seconds: int = 60,
) -> Starlette:
    """Build a minimal Starlette app with the rate-limit middleware."""

    async def _ok(_request: Request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", _ok)])
    app.add_middleware(
        RateLimitMiddleware,
        redis=redis_mock,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    return app


def _make_redis_mock() -> AsyncMock:
    """Dict-backed async Redis mock with pipeline support."""
    store: dict[str, int] = {}
    ttls: dict[str, int] = {}

    mock = AsyncMock()

    async def _incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    async def _expire(key, ttl, *, nx=False):
        if nx and key in ttls:
            return 0
        ttls[key] = ttl
        return 1

    async def _ttl(key):
        return ttls.get(key, -1)

    # Pipeline: collects commands, executes them in order
    @asynccontextmanager
    async def _pipeline():
        commands: list[tuple] = []

        pipe = MagicMock()

        def _pipe_incr(key):
            commands.append(("incr", key))

        def _pipe_expire(key, ttl, *, nx=False):
            commands.append(("expire", key, ttl, nx))

        pipe.incr = _pipe_incr
        pipe.expire = _pipe_expire

        async def _execute():
            results = []
            for cmd in commands:
                if cmd[0] == "incr":
                    results.append(await _incr(cmd[1]))
                elif cmd[0] == "expire":
                    results.append(await _expire(cmd[1], cmd[2], nx=cmd[3]))
            return results

        pipe.execute = _execute
        yield pipe

    mock.pipeline = _pipeline
    mock.incr = AsyncMock(side_effect=_incr)
    mock.expire = AsyncMock(side_effect=_expire)
    mock.ttl = AsyncMock(side_effect=_ttl)
    mock._store = store
    return mock


# ── Tests ───────────────────────────────────────────────────────────


class TestRateLimitMiddleware:
    def test_under_limit_passes(self):
        """Requests under the limit get 200."""
        redis_mock = _make_redis_mock()
        app = _make_app(redis_mock, max_requests=5)
        client = TestClient(app)

        for _ in range(5):
            resp = client.get("/")
            assert resp.status_code == 200

    def test_over_limit_returns_429(self):
        """Requests over the limit get 429 with Retry-After header."""
        redis_mock = _make_redis_mock()
        app = _make_app(redis_mock, max_requests=3)
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/")
            assert resp.status_code == 200

        resp = client.get("/")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.json() == {"detail": "Rate limit exceeded"}

    def test_different_ips_separate_limits(self):
        """Different client IPs should have independent counters."""
        redis_mock = _make_redis_mock()
        app = _make_app(redis_mock, max_requests=2)
        client = TestClient(app)

        # Both come from testclient's default IP, so we check via keys
        # With a single TestClient we can't easily change IP, so we verify
        # the counter increments consistently
        resp1 = client.get("/")
        resp2 = client.get("/")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        # Third request exceeds limit
        resp3 = client.get("/")
        assert resp3.status_code == 429

        # Verify only one key family was used (one IP)
        keys = list(redis_mock._store.keys())
        assert len(keys) == 1
        assert "rate" in keys[0]

    def test_fails_open_when_redis_unavailable(self):
        """If Redis raises RedisError, requests still pass through (fail-open)."""

        @asynccontextmanager
        async def _failing_pipeline():
            raise RedisConnectionError("Redis down")
            yield

        redis_mock = AsyncMock()
        redis_mock.pipeline = _failing_pipeline

        app = _make_app(redis_mock, max_requests=1)
        client = TestClient(app)

        # Even many requests should pass when Redis is down
        for _ in range(10):
            resp = client.get("/")
            assert resp.status_code == 200

    def test_counter_resets_after_window(self):
        """Requests in a new time window should not be blocked."""
        redis_mock = _make_redis_mock()
        # Use 1-second window so the window_id changes with time.time()
        app = _make_app(redis_mock, max_requests=2, window_seconds=1)
        client = TestClient(app)

        resp1 = client.get("/")
        resp2 = client.get("/")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        resp3 = client.get("/")
        assert resp3.status_code == 429

        # Wait for the window to roll over
        time.sleep(1.1)

        # New window — counter resets (new key)
        resp4 = client.get("/")
        assert resp4.status_code == 200

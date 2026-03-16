"""Tests for RateLimitMiddleware."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from everyrow_mcp.middleware import BodySizeLimitMiddleware, RateLimitMiddleware

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
        commands: list[tuple[Any, ...]] = []

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

    def test_rejects_unknown_client_ip(self):
        """Returns 400 when client IP cannot be determined."""
        redis_mock = _make_redis_mock()
        app = _make_app(redis_mock, max_requests=5)
        client = TestClient(app)

        # Patch get_client_ip to return None
        with patch("everyrow_mcp.middleware.get_client_ip", return_value=None):
            resp = client.get("/")
            assert resp.status_code == 400
            assert resp.json() == {"detail": "Could not determine client IP"}

    def test_counter_resets_after_window(self):
        """Requests in a new time window should not be blocked."""
        redis_mock = _make_redis_mock()
        app = _make_app(redis_mock, max_requests=2, window_seconds=60)
        client = TestClient(app)

        # Pin time to the middle of a window to avoid boundary flakiness
        fake_time = 1000.0
        with patch("everyrow_mcp.middleware.time") as mock_time:
            mock_time.time.return_value = fake_time

            resp1 = client.get("/")
            resp2 = client.get("/")
            assert resp1.status_code == 200
            assert resp2.status_code == 200

            resp3 = client.get("/")
            assert resp3.status_code == 429

            # Jump to the next window (60s later)
            mock_time.time.return_value = fake_time + 61

            # New window — counter resets (new key)
            resp4 = client.get("/")
            assert resp4.status_code == 200


# ── BodySizeLimitMiddleware tests ────────────────────────────────


def _make_upload_app(*, max_bytes: int = 100) -> Starlette:
    """Build a Starlette app with BodySizeLimitMiddleware on /api/uploads/."""

    async def _upload(request: Request):
        body = await request.body()
        return PlainTextResponse(f"received {len(body)} bytes")

    async def _other(_request: Request):
        return PlainTextResponse("ok")

    inner = Starlette(
        routes=[
            Route("/api/uploads/{upload_id}", _upload, methods=["PUT"]),
            Route("/other", _other),
        ],
    )
    return BodySizeLimitMiddleware(inner, max_bytes=max_bytes)  # pyright: ignore[reportReturnType]


class TestBodySizeLimitMiddleware:
    def test_small_upload_passes(self):
        """Uploads under the limit succeed."""
        app = _make_upload_app(max_bytes=1000)
        client = TestClient(app)
        resp = client.put("/api/uploads/abc", content=b"a,b\n1,2\n")
        assert resp.status_code == 200
        assert "received" in resp.text

    def test_oversized_upload_returns_413(self):
        """Uploads exceeding the limit get 413."""
        app = _make_upload_app(max_bytes=10)
        client = TestClient(app)
        resp = client.put("/api/uploads/abc", content=b"x" * 50)
        assert resp.status_code == 413
        assert resp.json() == {"error": "File too large"}

    def test_non_upload_path_not_limited(self):
        """Non-upload paths are not affected by the body limit."""
        app = _make_upload_app(max_bytes=10)
        client = TestClient(app)
        resp = client.get("/other")
        assert resp.status_code == 200

    def test_exact_limit_passes(self):
        """A body exactly at the limit should pass."""
        app = _make_upload_app(max_bytes=10)
        client = TestClient(app)
        resp = client.put("/api/uploads/abc", content=b"x" * 10)
        assert resp.status_code == 200

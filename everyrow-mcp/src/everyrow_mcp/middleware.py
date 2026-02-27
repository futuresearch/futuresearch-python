"""HTTP middleware for the EveryRow MCP server."""

from __future__ import annotations

import logging
import time

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from everyrow_mcp.config import settings
from everyrow_mcp.redis_store import build_key

logger = logging.getLogger(__name__)

_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"cache-control", b"no-store"),
]


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from the configured trusted header.

    Only reads the header named by ``settings.trusted_ip_header`` when
    ``settings.trust_proxy_headers`` is True. For multi-value headers
    like X-Forwarded-For, takes the first (leftmost) IP.
    Otherwise uses the direct connection IP.
    """
    if settings.trust_proxy_headers:
        value = request.headers.get(settings.trusted_ip_header.lower())
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based fixed-window rate limiter per client IP.

    Returns 429 with ``Retry-After`` header when the limit is exceeded.
    Redis is a hard dependency in HTTP mode — failures propagate.
    """

    def __init__(
        self,
        app,
        *,
        redis: Redis,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self._redis = redis
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = get_client_ip(request)
        if client_ip is None:
            return JSONResponse(
                {"detail": "Could not determine client IP"}, status_code=400
            )

        window_id = str(int(time.time()) // self._window_seconds)
        key = build_key("rate", client_ip, window_id)

        async with self._redis.pipeline() as pipe:
            pipe.incr(key)
            pipe.expire(key, self._window_seconds)
            count, _ = await pipe.execute()

        if count > self._max_requests:
            logger.warning("Rate limit exceeded for IP %s", client_ip)
            ttl = await self._redis.ttl(key)
            retry_after = max(ttl, 1)
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


class BodySizeLimitMiddleware:
    """Pure-ASGI middleware that enforces a max request body size.

    Wraps ``receive`` to track bytes and ``send`` to intercept the response
    when the limit is exceeded — even for chunked transfer-encoding requests
    that lack a Content-Length header.

    Only active on paths matching ``path_prefix``.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        path_prefix: str = "/api/uploads/",
    ) -> None:
        self._app = app
        self._max_bytes = max_bytes
        self._path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._path_prefix):
            await self._app(scope, receive, send)
            return

        total = 0
        exceeded = False
        response_sent = False

        async def _limited_receive():
            nonlocal total, exceeded
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                total += len(body)
                if total > self._max_bytes:
                    exceeded = True
                    # Return empty terminal body so the inner app exits cleanly
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def _filtered_send(message):
            nonlocal response_sent
            if not exceeded:
                await send(message)
                return
            if response_sent:
                # Already sent 413, suppress further sends from inner app
                return
            if message["type"] == "http.response.start":
                # Replace the inner app's response with our 413
                response_sent = True
                error_body = b'{"error": "File too large"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(error_body)).encode()],
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": error_body,
                    }
                )

        await self._app(scope, _limited_receive, _filtered_send)


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware that injects security headers into every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def _send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {h[0].lower() for h in headers}
                for name, value in _SECURITY_HEADERS:
                    if name not in existing:
                        headers.append([name, value])
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, _send_with_headers)

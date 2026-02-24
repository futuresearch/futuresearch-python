"""HTTP middleware for the EveryRow MCP server."""

from __future__ import annotations

import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from everyrow_mcp.config import settings
from everyrow_mcp.redis_store import build_key

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str | None:
    """Extract client IP, preferring proxy headers only when trusted.

    Only reads CF-Connecting-IP / X-Forwarded-For when
    ``settings.trust_proxy_headers`` is True (i.e. running behind a known
    reverse proxy like Cloudflare). Otherwise uses the direct connection IP.
    """
    if settings.trust_proxy_headers:
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based fixed-window rate limiter per client IP.

    Returns 429 with ``Retry-After`` header when the limit is exceeded.
    Fails open if Redis is unavailable so a Redis outage does not block
    legitimate traffic.
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
            logger.warning(
                "Could not determine client IP, using shared fallback bucket"
            )
            client_ip = "__unknown__"
        window_id = str(int(time.time()) // self._window_seconds)
        key = build_key("rate", client_ip, window_id)

        try:
            async with self._redis.pipeline() as pipe:
                pipe.incr(key)
                pipe.expire(key, self._window_seconds, nx=True)
                count, _ = await pipe.execute()

            if count > self._max_requests:
                ttl = await self._redis.ttl(key)
                retry_after = max(ttl, 1)
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        except (RedisError, OSError):
            logger.warning("Rate-limit check failed (Redis unavailable)")

        return await call_next(request)

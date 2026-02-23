"""Redis client factory and key helpers for the MCP server."""

from __future__ import annotations

import logging

from redis.asyncio import Redis, Sentinel
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

logger = logging.getLogger(__name__)

REDIS_DB = 13
HEALTH_CHECK_INTERVAL = 30


def build_key(*parts: str) -> str:
    # Sanitize parts to prevent key-injection via embedded colons
    sanitized = [p.replace(":", "_") for p in parts]
    return "mcp:" + ":".join(sanitized)


def create_redis_client(
    *,
    host: str = "localhost",
    port: int = 6379,
    db: int = REDIS_DB,
    password: str | None = None,
    sentinel_endpoints: str | None = None,
    sentinel_master_name: str | None = None,
) -> Redis:
    """Create an async Redis client with retry and health-check support.

    If *sentinel_endpoints* is provided (comma-separated "host:port" pairs),
    connects via Sentinel; otherwise connects directly.
    """
    retry = Retry(ExponentialBackoff(), retries=3)

    if sentinel_endpoints and sentinel_master_name:
        sentinels = []
        for ep in sentinel_endpoints.split(","):
            h, p = ep.strip().rsplit(":", 1)
            sentinels.append((h, int(p)))

        sentinel = Sentinel(
            sentinels,
            sentinel_kwargs={"password": password} if password else {},
            retry=retry,
        )
        client: Redis = sentinel.master_for(
            sentinel_master_name,
            db=db,
            password=password,
            decode_responses=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
            retry=retry,
        )
        logger.info("Redis: Sentinel mode, master=%s, db=%d", sentinel_master_name, db)
        return client

    client = Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        retry=retry,
    )
    logger.info("Redis: direct mode, host=%s:%d, db=%d", host, port, db)
    return client

from __future__ import annotations

import logging
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis, Sentinel
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

REDIS_DB = 13
HEALTH_CHECK_INTERVAL = 30

PROGRESS_POLL_DELAY = 12
TASK_STATE_FILE = Path.home() / ".everyrow" / "task.json"
RESULT_CACHE_TTL = 600
CSV_CACHE_TTL = 3600  # 1 hour — full CSV stored in Redis for download
TOKEN_TTL = 86400  # 24 hours — must outlive the longest possible task


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "streamable-http"


# ── Redis infrastructure ──────────────────────────────────────


def build_key(*parts: str) -> str:
    """Build a namespaced Redis key, sanitising embedded colons."""
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


@lru_cache
def get_redis_client() -> Redis:
    return create_redis_client(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        sentinel_endpoints=settings.redis_sentinel_endpoints,
        sentinel_master_name=settings.redis_sentinel_master_name,
    )


async def get_result_meta(task_id: str) -> str | None:
    return await get_redis_client().get(build_key("result", task_id))


async def store_result_meta(task_id: str, meta_json: str) -> None:
    await get_redis_client().setex(
        build_key("result", task_id), RESULT_CACHE_TTL, meta_json
    )


# ── Result pages ──────────────────────────────────────────────


async def get_result_page(task_id: str, offset: int, page_size: int) -> str | None:
    key = build_key("result", task_id, "page", str(offset), str(page_size))
    return await get_redis_client().get(key)


async def store_result_page(
    task_id: str, offset: int, page_size: int, preview_json: str
) -> None:
    await get_redis_client().setex(
        build_key("result", task_id, "page", str(offset), str(page_size)),
        RESULT_CACHE_TTL,
        preview_json,
    )


# ── CSV result storage ────────────────────────────────────────


async def store_result_csv(task_id: str, csv_text: str) -> None:
    await get_redis_client().setex(
        name=build_key("result", task_id, "csv"), time=CSV_CACHE_TTL, value=csv_text
    )


async def get_result_csv(task_id: str) -> str | None:
    return await get_redis_client().get(name=build_key("result", task_id, "csv"))


async def store_task_token(task_id: str, token: str) -> None:
    await get_redis_client().setex(build_key("task_token", task_id), TOKEN_TTL, token)


async def get_task_token(task_id: str) -> str | None:
    return await get_redis_client().get(build_key("task_token", task_id))


async def pop_task_token(task_id: str) -> None:
    await get_redis_client().delete(build_key("task_token", task_id))


# ── Poll tokens ───────────────────────────────────────────────


async def store_poll_token(task_id: str, poll_token: str) -> None:
    await get_redis_client().setex(
        name=build_key("poll_token", task_id),
        time=TOKEN_TTL,
        value=poll_token,
    )


async def get_poll_token(task_id: str) -> str | None:
    return await get_redis_client().get(build_key("poll_token", task_id))

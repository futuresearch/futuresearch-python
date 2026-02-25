from __future__ import annotations

import base64
import logging
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from redis.asyncio import Redis, Sentinel
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

HEALTH_CHECK_INTERVAL = 30

PROGRESS_POLL_DELAY = 12
TASK_STATE_FILE = Path.home() / ".everyrow" / "task.json"
RESULT_CACHE_TTL = 600
CSV_CACHE_TTL = 3600  # 1 hour — full CSV stored in Redis for download
TOKEN_TTL = 86400  # 24 hours — must outlive the longest possible task
DOWNLOAD_TOKEN_TTL = 300  # 5 minutes — short-lived, single-use download tokens


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "streamable-http"


# ── Redis infrastructure ──────────────────────────────────────


_KEY_UNSAFE = re.compile(r"[^a-zA-Z0-9._\-]")


def build_key(*parts: str) -> str:
    """Build a namespaced Redis key, sanitising user-controlled characters."""
    sanitized = [_KEY_UNSAFE.sub("_", p) for p in parts]
    return "mcp:" + ":".join(sanitized)


# ── Token encryption at rest ─────────────────────────────────


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    """Get a Fernet cipher for encrypting sensitive values in Redis.

    Returns None when encryption is not configured (e.g. stdio mode
    where UPLOAD_SECRET is typically unset).
    """
    if not settings.upload_secret:
        return None
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"everyrow-mcp-fernet",
    ).derive(settings.upload_secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(value: str) -> str:
    """Encrypt a string value for Redis storage. No-op without UPLOAD_SECRET."""
    f = _get_fernet()
    if f is None:
        if settings.is_http:
            raise RuntimeError(
                "UPLOAD_SECRET must be set in HTTP mode — cannot store sensitive values in plaintext."
            )
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt a string value from Redis. No-op without UPLOAD_SECRET."""
    f = _get_fernet()
    if f is None:
        if settings.is_http:
            raise RuntimeError(
                "UPLOAD_SECRET must be set in HTTP mode — cannot read encrypted values without the key."
            )
        return value
    return f.decrypt(value.encode()).decode()


def create_redis_client(
    *,
    host: str = "localhost",
    port: int = 6379,
    db: int = settings.redis_db,
    password: str | None = None,
    ssl: bool = False,
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
            sentinel_kwargs={"password": password, "ssl": ssl}
            if password
            else {"ssl": ssl},
            retry=retry,
        )
        client: Redis = sentinel.master_for(
            sentinel_master_name,
            db=db,
            password=password,
            ssl=ssl,
            decode_responses=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
            retry=retry,
        )
        logger.info(
            "Redis: Sentinel mode, master=%s, db=%d, ssl=%s",
            sentinel_master_name,
            db,
            ssl,
        )
        return client

    client = Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        ssl=ssl,
        decode_responses=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        retry=retry,
    )
    logger.info("Redis: direct mode, host=%s:%d, db=%d, ssl=%s", host, port, db, ssl)
    return client


_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client  # noqa: PLW0603
    if _redis_client is None:
        _redis_client = create_redis_client(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
            sentinel_endpoints=settings.redis_sentinel_endpoints,
            sentinel_master_name=settings.redis_sentinel_master_name,
        )
    return _redis_client


def set_redis_client(client: Redis | None) -> None:
    """Override the Redis client (for testing)."""
    global _redis_client  # noqa: PLW0603
    _redis_client = client


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


MAX_CSV_CACHE_CHARS = (
    50 * 1024 * 1024
)  # 50M characters — skip Redis cache for oversized results


async def store_result_csv(task_id: str, csv_text: str) -> None:
    if len(csv_text) > MAX_CSV_CACHE_CHARS:
        logger.warning(
            "Skipping Redis cache for task %s: CSV is %d chars (limit %d)",
            task_id,
            len(csv_text),
            MAX_CSV_CACHE_CHARS,
        )
        return
    await get_redis_client().setex(
        name=build_key("result", task_id, "csv"), time=CSV_CACHE_TTL, value=csv_text
    )


async def get_result_csv(task_id: str) -> str | None:
    return await get_redis_client().get(name=build_key("result", task_id, "csv"))


async def result_csv_exists(task_id: str) -> bool:
    """O(1) existence check — avoids reading the full CSV into memory."""
    return await get_redis_client().exists(build_key("result", task_id, "csv")) > 0


async def store_task_token(task_id: str, token: str) -> None:
    await get_redis_client().setex(
        build_key("task_token", task_id), TOKEN_TTL, encrypt_value(token)
    )


async def get_task_token(task_id: str) -> str | None:
    encrypted = await get_redis_client().get(build_key("task_token", task_id))
    if encrypted is None:
        return None
    return decrypt_value(encrypted)


async def pop_task_token(task_id: str) -> None:
    await get_redis_client().delete(build_key("task_token", task_id))


# ── Poll tokens ───────────────────────────────────────────────


async def store_poll_token(task_id: str, poll_token: str, user_id: str = "") -> None:
    """Store an encrypted poll token, optionally bound to a user identity."""
    client = get_redis_client()
    await client.setex(
        name=build_key("poll_token", task_id),
        time=TOKEN_TTL,
        value=encrypt_value(poll_token),
    )
    if user_id:
        await client.setex(
            name=build_key("poll_owner", task_id),
            time=TOKEN_TTL,
            value=user_id,
        )


async def get_poll_token(task_id: str) -> str | None:
    encrypted = await get_redis_client().get(build_key("poll_token", task_id))
    if encrypted is None:
        return None
    return decrypt_value(encrypted)


async def get_poll_token_owner(task_id: str) -> str | None:
    """Return the user_id bound to a poll token, or None if not set."""
    return await get_redis_client().get(build_key("poll_owner", task_id))


# ── Task ownership (user-scoped data isolation) ──────────────


async def store_task_owner(task_id: str, user_id: str) -> None:
    """Record which user submitted a task (for cross-user access checks)."""
    await get_redis_client().setex(build_key("task_owner", task_id), TOKEN_TTL, user_id)


async def get_task_owner(task_id: str) -> str | None:
    """Return the user_id that owns a task, or None if not recorded."""
    return await get_redis_client().get(build_key("task_owner", task_id))


# ── Upload metadata ───────────────────────────────────────────


async def store_upload_meta(upload_id: str, meta_json: str, ttl: int) -> None:
    """Store upload metadata with TTL (consume-on-use)."""
    await get_redis_client().setex(build_key("upload", upload_id), ttl, meta_json)


async def get_upload_meta(upload_id: str) -> str | None:
    """Read upload metadata without consuming it."""
    return await get_redis_client().get(build_key("upload", upload_id))


async def pop_upload_meta(upload_id: str) -> str | None:
    """Atomically get and delete upload metadata (prevents replay)."""
    key = build_key("upload", upload_id)
    return await get_redis_client().getdel(key)


# ── Download tokens (short-lived, single-use) ────────────────


async def store_download_token(download_token: str, task_id: str) -> None:
    """Store a single-use download token that maps back to a task_id.

    Keyed by token (reverse-lookup) so multiple concurrent download tokens
    can exist for the same task, and GETDEL provides natural consume semantics.
    """
    await get_redis_client().setex(
        name=build_key("dl_token", download_token),
        time=DOWNLOAD_TOKEN_TTL,
        value=encrypt_value(task_id),
    )


async def pop_download_token(download_token: str) -> tuple[str, int] | tuple[None, int]:
    """Atomically consume a download token, returning ``(task_id, remaining_ttl)``
    or ``(None, 0)`` if the token does not exist.

    The remaining TTL is captured *before* the GETDEL so that callers can
    re-store the token with its original expiry on a task_id mismatch
    (instead of granting a fresh 5-min window).
    """
    key = build_key("dl_token", download_token)
    r = get_redis_client()
    remaining = await r.ttl(key)  # -2 = missing, -1 = no expiry
    encrypted = await r.getdel(key)
    if encrypted is None:
        return None, 0
    ttl = max(remaining, 1)  # clamp to at least 1s
    return decrypt_value(encrypted), ttl


async def restore_download_token(
    download_token: str, task_id: str, ttl: int = DOWNLOAD_TOKEN_TTL
) -> None:
    """Re-store a download token (e.g. after a task_id mismatch)."""
    await get_redis_client().setex(
        name=build_key("dl_token", download_token),
        time=ttl,
        value=encrypt_value(task_id),
    )

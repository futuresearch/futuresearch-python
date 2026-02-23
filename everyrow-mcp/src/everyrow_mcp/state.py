"""Centralized server state for the everyrow MCP server.

RedisStore encapsulates all Redis data operations with error handling
and TTL management. ServerState is a thin config/context holder.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import Any

from everyrow.generated.client import AuthenticatedClient
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from everyrow_mcp.config import DevHttpSettings, HttpSettings, StdioSettings
from everyrow_mcp.redis_utils import build_key

logger = logging.getLogger(__name__)

PROGRESS_POLL_DELAY = 12
TASK_STATE_FILE = Path.home() / ".everyrow" / "task.json"
RESULT_CACHE_TTL = 600
CSV_CACHE_TTL = 3600  # 1 hour — full CSV stored in Redis for download
TOKEN_TTL = 86400  # 24 hours — must outlive the longest possible task


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


class RedisStore:
    """Redis-backed storage for task state, results, and tokens.

    Encapsulates all Redis data operations with error handling and TTL
    management.  The Redis client is required at construction time;
    null-safety is handled at the ServerState level (``store`` is
    ``RedisStore | None``).
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def ping(self) -> None:
        """Ping Redis to verify connectivity."""
        await self._redis.ping()

    # ── Result metadata ───────────────────────────────────────────

    async def get_result_meta(self, task_id: str) -> str | None:
        """Get cached result metadata from Redis."""
        try:
            return await self._redis.get(build_key("result", task_id))
        except Exception:
            logger.warning("Failed to get result metadata from Redis for %s", task_id)
            return None

    async def store_result_meta(self, task_id: str, meta_json: str) -> None:
        """Store result metadata in Redis with TTL."""
        try:
            await self._redis.setex(
                build_key("result", task_id),
                RESULT_CACHE_TTL,
                meta_json,
            )
        except Exception:
            logger.warning("Failed to store result metadata in Redis for %s", task_id)

    # ── Result pages ──────────────────────────────────────────────

    async def get_result_page(
        self, task_id: str, offset: int, page_size: int
    ) -> str | None:
        """Get a cached page preview from Redis."""
        try:
            return await self._redis.get(
                build_key("result", task_id, "page", str(offset), str(page_size))
            )
        except Exception:
            logger.warning("Failed to get result page from Redis for %s", task_id)
            return None

    async def store_result_page(
        self, task_id: str, offset: int, page_size: int, preview_json: str
    ) -> None:
        """Cache a page preview in Redis with TTL."""
        try:
            await self._redis.setex(
                build_key("result", task_id, "page", str(offset), str(page_size)),
                RESULT_CACHE_TTL,
                preview_json,
            )
        except Exception:
            logger.warning("Failed to store result page in Redis for %s", task_id)

    # ── CSV result storage ────────────────────────────────────────

    async def store_result_csv(self, task_id: str, csv_text: str) -> None:
        """Store full CSV text in Redis with 1h TTL."""
        try:
            await self._redis.setex(
                build_key("result", task_id, "csv"),
                CSV_CACHE_TTL,
                csv_text,
            )
        except Exception:
            logger.warning("Failed to store result CSV in Redis for %s", task_id)

    async def get_result_csv(self, task_id: str) -> str | None:
        """Read full CSV text from Redis."""
        try:
            return await self._redis.get(build_key("result", task_id, "csv"))
        except Exception:
            logger.warning("Failed to get result CSV from Redis for %s", task_id)
            return None

    # ── Task tokens ───────────────────────────────────────────────

    async def store_task_token(self, task_id: str, token: str) -> None:
        """Store an API token for a task in Redis."""
        try:
            await self._redis.setex(build_key("task_token", task_id), TOKEN_TTL, token)
        except Exception:
            logger.warning("Failed to store task token in Redis for %s", task_id)

    async def get_task_token(self, task_id: str) -> str | None:
        """Get an API token for a task from Redis."""
        try:
            return await self._redis.get(build_key("task_token", task_id))
        except Exception:
            logger.warning("Failed to get task token from Redis for %s", task_id)
            return None

    # ── Poll tokens ───────────────────────────────────────────────

    async def store_poll_token(self, task_id: str, poll_token: str) -> None:
        """Store a poll token for a task in Redis."""
        try:
            await self._redis.setex(
                build_key("poll_token", task_id), TOKEN_TTL, poll_token
            )
        except Exception:
            logger.warning("Failed to store poll token in Redis for %s", task_id)

    async def get_poll_token(self, task_id: str) -> str | None:
        """Get a poll token for a task from Redis."""
        try:
            return await self._redis.get(build_key("poll_token", task_id))
        except Exception:
            logger.warning("Failed to get poll token from Redis for %s", task_id)
            return None

    async def pop_task_token(self, task_id: str) -> None:
        """Remove the API task token from Redis.

        The poll token is intentionally kept — it's needed to authenticate
        CSV download requests after the task completes (it expires naturally
        via its 24h TTL).
        """
        try:
            await self._redis.delete(build_key("task_token", task_id))
        except Exception:
            logger.warning("Failed to delete task token from Redis for %s", task_id)


class ServerState(BaseModel):
    """Mutable state shared across the MCP server.

    Thin config/context holder — all Redis data operations are delegated
    to RedisStore.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: AuthenticatedClient | None = None
    transport: Transport = Transport.STDIO
    mcp_server_url: str = ""
    settings: StdioSettings | HttpSettings | DevHttpSettings | None = None
    store: RedisStore | None = Field(default=None)
    auth_provider: Any | None = Field(default=None)

    @property
    def is_stdio(self) -> bool:
        return self.transport == Transport.STDIO

    @property
    def is_http(self) -> bool:
        return self.transport != Transport.STDIO


state = ServerState()

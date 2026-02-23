"""FastMCP application instance, lifespan, and task state management."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from everyrow.api_utils import create_client
from everyrow.generated.api.billing.get_billing_balance_billing_get import (
    asyncio as get_billing,
)
from everyrow.generated.client import AuthenticatedClient
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_status import TaskStatus
from mcp.server.fastmcp import FastMCP

PROGRESS_POLL_DELAY = 12  # seconds to block in everyrow_progress before returning
TASK_STATE_FILE = Path.home() / ".everyrow" / "task.json"
# Singleton client, initialized in lifespan
_client: AuthenticatedClient | None = None


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Initialize singleton client and validate credentials on startup."""
    global _client  # noqa: PLW0603

    _clear_task_state()

    try:
        with create_client() as _client:
            response = await get_billing(client=_client)
            if response is None:
                raise RuntimeError("Failed to authenticate with everyrow API")
            yield
    except Exception as e:
        logging.getLogger(__name__).error(f"everyrow-mcp startup failed: {e!r}")
        raise
    finally:
        _client = None
        _clear_task_state()


mcp = FastMCP("everyrow_mcp", lifespan=lifespan)


def _clear_task_state() -> None:
    if TASK_STATE_FILE.exists():
        TASK_STATE_FILE.unlink()


def _write_task_state(
    task_id: str,
    task_type: PublicTaskType,
    session_url: str,
    total: int,
    completed: int,
    failed: int,
    running: int,
    status: TaskStatus,
    started_at: datetime,
) -> None:
    """Write task tracking state for hooks/status line to read.

    Note: Only one task is tracked at a time. If multiple tasks run concurrently,
    only the most recent one's progress is shown.
    """
    try:
        TASK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "task_id": task_id,
            "task_type": task_type.value,
            "session_url": session_url,
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "status": status.value,
            "started_at": started_at.timestamp(),
        }
        with open(TASK_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logging.getLogger(__name__).debug(f"Failed to write task state: {e!r}")

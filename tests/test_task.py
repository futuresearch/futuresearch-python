"""Unit tests for futuresearch.task — progress polling, callbacks, ETA, JSONL logging."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from futuresearch.constants import EveryrowError
from futuresearch.generated.models import (
    PublicTaskType,
    TaskProgressInfo,
    TaskStatus,
    TaskStatusResponse,
)
from futuresearch.task import await_task_completion, print_progress


def _make_status(
    status: TaskStatus = TaskStatus.PENDING,
    progress: TaskProgressInfo | None = None,
    error: str | None = None,
) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status=status,
        task_type=PublicTaskType.AGENT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=progress,
        error=error,
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Replace asyncio.sleep with a no-op to avoid real waits."""
    monkeypatch.setattr("futuresearch.task.asyncio.sleep", AsyncMock())


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.mark.asyncio
async def test_immediate_completion(
    mocker,
    mock_client,
):
    """Task already completed on first poll — no progress output."""
    mock_status = mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status(TaskStatus.COMPLETED)

    result = await await_task_completion(uuid.uuid4(), mock_client)
    assert result.status == TaskStatus.COMPLETED
    mock_status.assert_called_once()


@pytest.mark.asyncio
async def test_progress_callback_fires_on_change(
    mocker,
    mock_client,
):
    """on_progress callback fires when snapshot changes."""
    task_id = uuid.uuid4()
    callback = MagicMock()

    statuses = [
        _make_status(
            TaskStatus.PENDING,
            TaskProgressInfo(pending=5, running=0, completed=0, failed=0, total=5),
        ),
        _make_status(
            TaskStatus.PENDING,
            TaskProgressInfo(pending=3, running=2, completed=0, failed=0, total=5),
        ),
        _make_status(
            TaskStatus.PENDING,
            TaskProgressInfo(pending=1, running=2, completed=2, failed=0, total=5),
        ),
        _make_status(
            TaskStatus.COMPLETED,
            TaskProgressInfo(pending=0, running=0, completed=5, failed=0, total=5),
        ),
    ]

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        side_effect=statuses,
    )

    await await_task_completion(task_id, mock_client, on_progress=callback)

    # All 4 statuses have different snapshots, so callback fires 4 times
    assert callback.call_count == 4
    # Verify the first call got the initial progress
    first_call = callback.call_args_list[0][0][0]
    assert isinstance(first_call, TaskProgressInfo)
    assert first_call.pending == 5
    # Verify the last call got the final progress
    last_call = callback.call_args_list[-1][0][0]
    assert last_call.completed == 5


@pytest.mark.asyncio
async def test_callback_skips_duplicate_snapshot(
    mocker,
    mock_client,
):
    """on_progress callback does NOT fire when snapshot is unchanged."""
    task_id = uuid.uuid4()
    callback = MagicMock()

    same_progress = TaskProgressInfo(
        pending=3,
        running=2,
        completed=0,
        failed=0,
        total=5,
    )
    statuses = [
        _make_status(TaskStatus.PENDING, same_progress),
        _make_status(TaskStatus.PENDING, same_progress),  # duplicate
        _make_status(TaskStatus.PENDING, same_progress),  # duplicate
        _make_status(
            TaskStatus.COMPLETED,
            TaskProgressInfo(pending=0, running=0, completed=5, failed=0, total=5),
        ),
    ]

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        side_effect=statuses,
    )

    await await_task_completion(task_id, mock_client, on_progress=callback)

    # Only 2 unique snapshots (initial + final), so 2 calls
    assert callback.call_count == 2


@pytest.mark.asyncio
async def test_print_progress_output_format(
    mocker,
    mock_client,
    capsys,
):
    """print_progress outputs progress in expected format"""

    task_id = uuid.uuid4()

    statuses = [
        _make_status(
            TaskStatus.PENDING,
            TaskProgressInfo(pending=3, running=2, completed=0, failed=0, total=5),
        ),
        _make_status(
            TaskStatus.COMPLETED,
            TaskProgressInfo(pending=0, running=0, completed=5, failed=0, total=5),
        ),
    ]

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        side_effect=statuses,
    )

    await await_task_completion(task_id, mock_client, on_progress=print_progress)

    captured = capsys.readouterr()
    assert "0/5" in captured.out or "5/5" in captured.out
    assert "running" in captured.out


@pytest.mark.asyncio
async def test_failed_task_raises(
    mocker,
    mock_client,
):
    """A task that ends in FAILED raises EveryrowError."""
    task_id = uuid.uuid4()

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        return_value=_make_status(TaskStatus.FAILED, error="Something went wrong"),
    )

    with pytest.raises(EveryrowError, match="Task failed"):
        await await_task_completion(task_id, mock_client)


@pytest.mark.asyncio
async def test_revoked_task_raises(
    mocker,
    mock_client,
):
    """A task that ends in REVOKED raises EveryrowError."""
    task_id = uuid.uuid4()

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        return_value=_make_status(TaskStatus.REVOKED),
    )

    with pytest.raises(EveryrowError, match="revoked"):
        await await_task_completion(task_id, mock_client)


@pytest.mark.asyncio
async def test_retries_on_transient_error(
    mocker,
    mock_client,
):
    """Transient status fetch errors are retried up to max_retries."""
    task_id = uuid.uuid4()

    call_count = 0

    async def status_with_error(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError("network blip")
        return _make_status(TaskStatus.COMPLETED)

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        side_effect=status_with_error,
    )

    result = await await_task_completion(task_id, mock_client)
    assert result.status == TaskStatus.COMPLETED
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_retries_exhausted_raises(
    mocker,
    mock_client,
):
    """Exceeding max_retries raises EveryrowError."""
    task_id = uuid.uuid4()

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        side_effect=ConnectionError("persistent failure"),
    )

    with pytest.raises(EveryrowError, match="retries"):
        await await_task_completion(task_id, mock_client)


@pytest.mark.asyncio
async def test_no_output_without_callback(
    mocker,
    mock_client,
    capsys,
):
    """No progress output when on_progress callback is not provided."""
    task_id = uuid.uuid4()

    statuses = [
        _make_status(
            TaskStatus.PENDING,
            TaskProgressInfo(pending=5, running=0, completed=0, failed=0, total=5),
        ),
        _make_status(
            TaskStatus.COMPLETED,
            TaskProgressInfo(pending=0, running=0, completed=5, failed=0, total=5),
        ),
    ]

    mocker.patch(
        "futuresearch.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
        side_effect=statuses,
    )

    await await_task_completion(task_id, mock_client)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""

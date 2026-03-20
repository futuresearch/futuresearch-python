"""Tests for long-poll progress and widget handoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.types import UNSET

from everyrow_mcp.tool_helpers import TaskState, should_long_poll
from everyrow_mcp.tools import _progress_long_poll
from tests.conftest import override_settings


def _make_status_response(
    *,
    status: TaskStatus = TaskStatus.RUNNING,
    task_type: PublicTaskType = PublicTaskType.AGENT,
    completed: int = 2,
    running: int = 3,
    failed: int = 0,
    total: int = 10,
    artifact_id=UNSET,
    error=UNSET,
    created_at=None,
    updated_at=None,
):
    resp = MagicMock()
    resp.status = status
    resp.task_type = task_type
    resp.artifact_id = artifact_id
    resp.session_id = None
    resp.error = error
    resp.created_at = created_at
    resp.updated_at = updated_at

    p = MagicMock()
    p.completed = completed
    p.running = running
    p.failed = failed
    p.total = total
    resp.progress = p

    return resp


def _make_ctx(*, widget_capable: bool = True) -> MagicMock:
    """Build a mock EveryRowContext."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context.client_factory = MagicMock()

    # Set up client_params for widget detection
    if widget_capable:
        cp = MagicMock()
        cp.clientInfo.name = "Anthropic/ClaudeAI"
        cp.clientInfo.version = "1.0.0"
        cp.capabilities = MagicMock()
        cp.capabilities.experimental = {}
        ctx.session.client_params = cp
    else:
        cp = MagicMock()
        cp.clientInfo.name = "claude-code"
        cp.clientInfo.version = "2.0"
        cp.capabilities = MagicMock()
        cp.capabilities.experimental = {}
        ctx.session.client_params = cp

    return ctx


def _mock_status_factory(responses: list, call_counter: dict):
    """Create an async mock status function that returns responses in order."""

    async def _mock_status(*_args, **_kwargs):
        resp = responses[min(call_counter["n"], len(responses) - 1)]
        call_counter["n"] += 1
        return resp

    return _mock_status


class TestShouldLongPoll:
    """Tests for should_long_poll() routing logic."""

    def test_false_for_stdio(self):
        ctx = _make_ctx(widget_capable=True)
        with override_settings(transport="stdio"):
            assert should_long_poll(ctx) is False

    def test_false_when_timeout_zero(self):
        ctx = _make_ctx(widget_capable=True)
        with override_settings(transport="streamable-http", long_poll_timeout=0):
            assert should_long_poll(ctx) is False

    def test_false_for_internal_client(self):
        ctx = _make_ctx(widget_capable=True)
        with (
            override_settings(transport="streamable-http"),
            patch("everyrow_mcp.tool_helpers.is_internal_client", return_value=True),
        ):
            assert should_long_poll(ctx) is False

    def test_true_for_widget_capable_http_client(self):
        ctx = _make_ctx(widget_capable=True)
        with (
            override_settings(transport="streamable-http"),
            patch("everyrow_mcp.tool_helpers.is_internal_client", return_value=False),
        ):
            assert should_long_poll(ctx) is True

    def test_false_for_non_widget_client(self):
        ctx = _make_ctx(widget_capable=False)
        with (
            override_settings(transport="streamable-http"),
            patch("everyrow_mcp.tool_helpers.is_internal_client", return_value=False),
        ):
            assert should_long_poll(ctx) is False


class TestProgressMessageWidgetHandoff:
    """Tests for progress_message(widget_handoff=True)."""

    def test_widget_handoff_message_stops_polling(self):
        resp = _make_status_response(
            status=TaskStatus.RUNNING,
            completed=3,
            running=2,
            total=10,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-abc", widget_handoff=True)
        assert "Do NOT call everyrow_progress again" in msg
        assert "everyrow_results" in msg
        assert "task-abc" in msg

    def test_widget_handoff_includes_progress_stats(self):
        resp = _make_status_response(
            status=TaskStatus.RUNNING,
            completed=5,
            running=3,
            failed=1,
            total=10,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-xyz", widget_handoff=True)
        assert "5/10 complete" in msg
        assert "3 running" in msg
        assert "1 failed" in msg

    def test_widget_handoff_false_keeps_normal_polling(self):
        resp = _make_status_response(
            status=TaskStatus.RUNNING,
            completed=3,
            running=2,
            total=10,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-normal", widget_handoff=False)
        assert "Immediately call everyrow_progress" in msg
        assert "Do NOT" not in msg

    def test_widget_handoff_ignored_when_terminal(self):
        """widget_handoff should have no effect on terminal messages."""
        resp = _make_status_response(
            status=TaskStatus.COMPLETED,
            completed=10,
            total=10,
        )
        ts = TaskState(resp)
        # Even with widget_handoff=True, terminal messages are unchanged
        msg_with = ts.progress_message("task-done", widget_handoff=True)
        msg_without = ts.progress_message("task-done", widget_handoff=False)
        assert msg_with == msg_without


class TestProgressLongPoll:
    """Tests for _progress_long_poll() in tools.py."""

    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        """Task completes on the 2nd poll -> returns completion message."""
        task_id = str(uuid4())
        counter: dict = {"n": 0}
        mock_status = _mock_status_factory(
            [
                _make_status_response(status=TaskStatus.RUNNING, completed=3, total=10),
                _make_status_response(
                    status=TaskStatus.COMPLETED, completed=10, total=10
                ),
            ],
            counter,
        )

        ctx = _make_ctx(widget_capable=True)
        mock_client = MagicMock()
        ctx.request_context.lifespan_context.client_factory = lambda: mock_client
        ctx.report_progress = AsyncMock()

        with (
            override_settings(
                transport="streamable-http", long_poll_timeout=15, long_poll_interval=1
            ),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                side_effect=mock_status,
            ),
            patch("everyrow_mcp.tools.handle_response", side_effect=lambda x: x),
        ):
            result = await _progress_long_poll(ctx, task_id)

        text = result[0].text
        assert "Completed" in text
        assert "Do NOT" not in text

    @pytest.mark.asyncio
    async def test_times_out_with_widget_handoff(self):
        """Task still running at timeout -> returns widget handoff message."""
        task_id = str(uuid4())
        running_resp = _make_status_response(
            status=TaskStatus.RUNNING, completed=3, running=2, total=10
        )

        ctx = _make_ctx(widget_capable=True)
        mock_client = MagicMock()
        ctx.request_context.lifespan_context.client_factory = lambda: mock_client
        ctx.report_progress = AsyncMock()

        async def _mock_status(*_args, **_kwargs):
            return running_resp

        with (
            override_settings(
                transport="streamable-http", long_poll_timeout=3, long_poll_interval=1
            ),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                side_effect=_mock_status,
            ),
            patch("everyrow_mcp.tools.handle_response", side_effect=lambda x: x),
        ):
            result = await _progress_long_poll(ctx, task_id)

        text = result[0].text
        assert "Do NOT call everyrow_progress again" in text
        assert "everyrow_results" in text

    @pytest.mark.asyncio
    async def test_resilient_to_intermittent_errors(self):
        """Intermittent API errors don't crash -- retries next iteration."""
        task_id = str(uuid4())
        call_count = 0

        async def _mock_status(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return _make_status_response(
                status=TaskStatus.COMPLETED, completed=5, total=5
            )

        ctx = _make_ctx(widget_capable=True)
        mock_client = MagicMock()
        ctx.request_context.lifespan_context.client_factory = lambda: mock_client
        ctx.report_progress = AsyncMock()

        with (
            override_settings(
                transport="streamable-http", long_poll_timeout=10, long_poll_interval=1
            ),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                side_effect=_mock_status,
            ),
            patch("everyrow_mcp.tools.handle_response", side_effect=lambda x: x),
        ):
            result = await _progress_long_poll(ctx, task_id)

        text = result[0].text
        assert "Completed" in text
        assert call_count == 2  # 1 error + 1 success

    @pytest.mark.asyncio
    async def test_all_polls_fail_returns_retry_message(self):
        """All status checks fail -> returns retry message."""
        task_id = str(uuid4())

        async def _mock_status(*_args, **_kwargs):
            raise ConnectionError("down")

        ctx = _make_ctx(widget_capable=True)
        mock_client = MagicMock()
        ctx.request_context.lifespan_context.client_factory = lambda: mock_client
        ctx.report_progress = AsyncMock()

        with (
            override_settings(
                transport="streamable-http", long_poll_timeout=3, long_poll_interval=1
            ),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                side_effect=_mock_status,
            ),
            patch("everyrow_mcp.tools.handle_response", side_effect=lambda x: x),
        ):
            result = await _progress_long_poll(ctx, task_id)

        text = result[0].text
        assert "Unable to check status" in text
        assert task_id in text

    @pytest.mark.asyncio
    async def test_reports_progress_on_each_successful_poll(self):
        """ctx.report_progress() called on each successful status check."""
        task_id = str(uuid4())
        counter: dict = {"n": 0}
        mock_status = _mock_status_factory(
            [
                _make_status_response(status=TaskStatus.RUNNING, completed=2, total=10),
                _make_status_response(status=TaskStatus.RUNNING, completed=5, total=10),
                _make_status_response(
                    status=TaskStatus.COMPLETED, completed=10, total=10
                ),
            ],
            counter,
        )

        ctx = _make_ctx(widget_capable=True)
        mock_client = MagicMock()
        ctx.request_context.lifespan_context.client_factory = lambda: mock_client
        ctx.report_progress = AsyncMock()

        with (
            override_settings(
                transport="streamable-http", long_poll_timeout=15, long_poll_interval=1
            ),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                side_effect=mock_status,
            ),
            patch("everyrow_mcp.tools.handle_response", side_effect=lambda x: x),
        ):
            await _progress_long_poll(ctx, task_id)

        assert ctx.report_progress.call_count == 3

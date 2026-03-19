"""Tests for tool_helpers.py — TaskState, _fetch_task_result, progress_message."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.types import UNSET, Unset

from everyrow_mcp.tool_helpers import TaskState, _format_summary_lines
from tests.conftest import override_settings


def _make_status_response(
    *,
    status: TaskStatus = TaskStatus.COMPLETED,
    task_type: PublicTaskType = PublicTaskType.AGENT,
    artifact_id: Unset | UUID | None = UNSET,
    session_id: UUID | None = None,
    error: str | Unset | None = UNSET,
    progress: TaskProgressInfo | None = None,
    created_at: datetime.datetime | None = None,
    updated_at: datetime.datetime | None = None,
):
    """Build a mock TaskStatusResponse."""
    resp = MagicMock()
    resp.status = status
    resp.task_type = task_type
    resp.artifact_id = artifact_id
    resp.session_id = session_id
    resp.error = error
    resp.created_at = created_at
    resp.updated_at = updated_at

    if progress is None:
        p = MagicMock()
        p.completed = 5
        p.failed = 0
        p.running = 0
        p.total = 5
        resp.progress = p
    else:
        resp.progress = progress

    return resp


class TestTaskStateArtifactId:
    def test_artifact_id_from_uuid(self):
        uid = uuid4()
        resp = _make_status_response(artifact_id=uid)
        ts = TaskState(resp)
        assert ts.artifact_id == str(uid)

    def test_artifact_id_unset(self):
        resp = _make_status_response(artifact_id=UNSET)
        ts = TaskState(resp)
        assert ts.artifact_id == ""

    def test_artifact_id_none(self):
        resp = _make_status_response(artifact_id=None)
        ts = TaskState(resp)
        assert ts.artifact_id == ""


class TestProgressMessageArtifactId:
    def test_completed_message_includes_artifact_id(self):
        uid = uuid4()
        resp = _make_status_response(
            status=TaskStatus.COMPLETED,
            artifact_id=uid,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-123")
        assert f"Output artifact_id: {uid}" in msg

    def test_completed_message_omits_artifact_id_when_absent(self):
        resp = _make_status_response(
            status=TaskStatus.COMPLETED,
            artifact_id=UNSET,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-123")
        assert "Output artifact_id" not in msg

    def test_completed_http_mode_includes_artifact_id(self):
        uid = uuid4()
        resp = _make_status_response(
            status=TaskStatus.COMPLETED,
            artifact_id=uid,
        )
        ts = TaskState(resp)
        with override_settings(transport="streamable-http"):
            msg = ts.progress_message("task-456")
        assert f"Output artifact_id: {uid}" in msg
        assert "everyrow_results" in msg

    def test_running_message_does_not_include_artifact_id(self):
        uid = uuid4()
        resp = _make_status_response(
            status=TaskStatus.RUNNING,
            artifact_id=uid,
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-789")
        assert "Output artifact_id" not in msg

    def test_failed_message_does_not_include_artifact_id(self):
        resp = _make_status_response(
            status=TaskStatus.FAILED,
            error="Something went wrong",
        )
        ts = TaskState(resp)
        msg = ts.progress_message("task-err")
        assert "Output artifact_id" not in msg


class TestFormatSummaryLines:
    def test_deduplicates_identical_summaries(self):
        summaries = [
            {"summary": "Synthesizing data", "row_index": 17},
            {"summary": "Synthesizing data", "row_index": 29},
        ]
        result = _format_summary_lines(summaries)
        assert result.count("Synthesizing data") == 1
        assert "[Rows 17, 29]" in result

    def test_singular_row_label(self):
        summaries = [{"summary": "Processing", "row_index": 5}]
        result = _format_summary_lines(summaries)
        assert "[Row 5]" in result
        assert "[Rows" not in result

    def test_preserves_order(self):
        summaries = [
            {"summary": "First task", "row_index": 1},
            {"summary": "Second task", "row_index": 2},
        ]
        result = _format_summary_lines(summaries)
        assert result.index("First task") < result.index("Second task")

    def test_empty_list(self):
        assert _format_summary_lines([]) == ""

    def test_no_row_index(self):
        summaries = [{"summary": "No index here"}]
        result = _format_summary_lines(summaries)
        assert "No index here" in result
        assert "[Row" not in result

    def test_mixed_with_and_without_row_index(self):
        summaries = [
            {"summary": "Has index", "row_index": 3},
            {"summary": "No index"},
        ]
        result = _format_summary_lines(summaries)
        assert "[Row 3] Has index" in result
        assert "No index" in result

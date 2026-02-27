"""Tests for tool_helpers.py — TaskState, _fetch_task_result, progress_message."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.types import UNSET

from everyrow_mcp.tool_helpers import TaskState
from tests.conftest import override_settings


def _make_status_response(
    *,
    status: TaskStatus = TaskStatus.COMPLETED,
    task_type: PublicTaskType = PublicTaskType.AGENT,
    artifact_id=UNSET,
    session_id=None,
    error=UNSET,
    progress=None,
    created_at=None,
    updated_at=None,
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

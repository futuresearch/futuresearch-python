"""Tests that stdio-mode tool responses contain only model-appropriate content.

In stdio mode, tool responses go directly into the LLM context window.
Every TextContent item must be concise, human-readable text — never JSON
widget payloads, HTML, download URLs with auth tokens, or internal state.

Three tiers:
- TestStdio*Content: always runs, mocked SDK (fast, CI-safe)
- TestHttpMode*: always runs, verifies HTTP mode contrast
- TestStdioMcpIntegration: gated by RUN_INTEGRATION_TESTS=1, real API through MCP protocol
"""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest
from futuresearch.api_utils import create_client
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_progress_info import TaskProgressInfo
from futuresearch.generated.models.task_result_response import TaskResultResponse
from futuresearch.generated.models.task_result_response_data_type_0_item import (
    TaskResultResponseDataType0Item,
)
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse
from mcp.server.fastmcp.server import lifespan_wrapper
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

import futuresearch_mcp.tools  # noqa: F401 — trigger @mcp.tool() registration
from futuresearch_mcp import redis_store
from futuresearch_mcp.app import mcp as mcp_app
from futuresearch_mcp.config import settings
from futuresearch_mcp.models import (
    AgentInput,
    DedupeInput,
    MergeInput,
    ProgressInput,
    RankInput,
    SingleAgentInput,
    StdioResultsInput,
)
from futuresearch_mcp.redis_store import Transport, _get_fernet
from futuresearch_mcp.tool_helpers import SessionContext
from futuresearch_mcp.tools import (
    futuresearch_agent,
    futuresearch_dedupe,
    futuresearch_merge,
    futuresearch_progress,
    futuresearch_rank,
    futuresearch_results_stdio,
    futuresearch_single_agent,
)
from tests.conftest import make_test_context

# ── Patterns that MUST NOT appear in stdio responses ──────────────────

# JSON widget payloads (start with { and contain widget keys)
WIDGET_KEYS = ("progress_url", "csv_url", "preview", "poll_token")

# Internal/HTTP-only URL patterns
FORBIDDEN_PATTERNS = [
    re.compile(r"/api/progress/"),  # HTTP polling endpoint
    re.compile(r"/api/results/.*/download"),  # HTTP download endpoint
    re.compile(r"\?token="),  # Auth tokens in URLs
    re.compile(r"<html", re.IGNORECASE),  # HTML content
    re.compile(r"<script", re.IGNORECASE),  # Embedded JavaScript
    re.compile(r"mcp_server_url"),  # Internal config leak
    re.compile(r"poll_token"),  # Internal token reference
    re.compile(r"task_token"),  # Internal token reference
]


def assert_text_clean(text: str, *, tool_name: str, index: int) -> None:
    """Assert that a single text string is model-appropriate."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                leaked_keys = [k for k in WIDGET_KEYS if k in parsed]
                assert not leaked_keys, (
                    f"{tool_name} result[{index}] is a JSON widget payload "
                    f"containing HTTP-only keys: {leaked_keys}\n"
                    f"Content: {text[:200]}"
                )
        except json.JSONDecodeError:
            pass  # Not JSON — that's fine for stdio

    for pattern in FORBIDDEN_PATTERNS:
        assert not pattern.search(text), (
            f"{tool_name} result[{index}] contains forbidden pattern "
            f"'{pattern.pattern}'\nContent: {text[:300]}"
        )


def assert_stdio_clean(result: list[TextContent], *, tool_name: str) -> None:
    """Assert that every TextContent in a stdio response is model-appropriate.

    Checks:
    1. No item is a JSON object containing widget keys
    2. No item contains HTTP-only URLs, tokens, or HTML
    3. Every item is plain human-readable text
    """
    for i, item in enumerate(result):
        assert_text_clean(item.text, tool_name=tool_name, index=i)


def _assert_mcp_result_clean(result, *, tool_name: str) -> None:
    """Assert that a CallToolResult from MCP protocol is model-appropriate.

    Same checks as assert_stdio_clean but works with MCP ContentBlock objects.
    """
    for i, block in enumerate(result.content):
        assert_text_clean(block.text, tool_name=tool_name, index=i)


# ── Shared test helpers ───────────────────────────────────────────────


def _make_mock_task(task_id=None):
    task = MagicMock()
    task.task_id = task_id or uuid4()
    return task


def _make_mock_session(session_id=None):
    session = MagicMock()
    session.session_id = session_id or uuid4()
    return session


def _make_mock_client():
    client = AsyncMock(spec=AuthenticatedClient)
    client.token = "fake-token"
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.with_headers = MagicMock(return_value=client)
    return client


def _make_async_cm(return_value):
    @asynccontextmanager
    async def mock_ctx():
        yield return_value

    return mock_ctx()


def _make_status_response(
    *,
    status: str = "running",
    task_type: PublicTaskType = PublicTaskType.AGENT,
    completed: int = 0,
    failed: int = 0,
    running: int = 0,
    total: int = 10,
) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=uuid4(),
        session_id=uuid4(),
        status=TaskStatus(status),
        task_type=task_type,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        progress=TaskProgressInfo(
            pending=total - completed - failed - running,
            running=running,
            completed=completed,
            failed=failed,
            total=total,
        ),
    )


def _make_result_response(data: list[dict[str, Any]]) -> TaskResultResponse:
    items = [TaskResultResponseDataType0Item.from_dict(d) for d in data]
    return TaskResultResponse(
        task_id=uuid4(),
        status=TaskStatus.COMPLETED,
        data=items,
    )


def _submit_patches(mock_op_path: str):
    """Return common patch context managers for submission tool tests."""
    mock_task = _make_mock_task()
    mock_session = _make_mock_session()
    mock_client = _make_mock_client()
    ctx = make_test_context(mock_client)

    return (
        mock_task,
        mock_session,
        mock_client,
        ctx,
        patch(mock_op_path, new_callable=AsyncMock, return_value=mock_task),
        patch(
            "futuresearch_mcp.tools.create_linked_session",
            return_value=_make_async_cm(mock_session),
        ),
    )


# ── Submission tools ──────────────────────────────────────────────────


class TestStdioSubmissionContent:
    """All submission tools must return clean, concise text in stdio mode."""

    @pytest.mark.asyncio
    async def test_agent_content(self):
        task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools._submit_agent_map"
        )
        with patches[0], patches[1]:
            result = await futuresearch_agent(
                AgentInput(task="Find HQ", data=[{"name": "TechStart"}]), ctx
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_agent")
        text = result[0].text
        assert str(task.task_id) in text
        assert "futuresearch_progress" in text

    @pytest.mark.asyncio
    async def test_single_agent_content(self):
        task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools._submit_single_agent"
        )
        with patches[0], patches[1]:
            result = await futuresearch_single_agent(
                SingleAgentInput(task="Find CEO of Apple"), ctx
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_single_agent")
        text = result[0].text
        assert str(task.task_id) in text

    @pytest.mark.asyncio
    async def test_rank_content(self):
        _task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools._submit_rank"
        )
        with patches[0], patches[1]:
            result = await futuresearch_rank(
                RankInput(
                    task="Score by AI adoption",
                    data=[{"name": "TechStart", "industry": "Software"}],
                    field_name="ai_score",
                ),
                ctx,
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_rank")

    @pytest.mark.asyncio
    async def test_dedupe_content(self):
        _task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools.dedupe_async"
        )
        with patches[0], patches[1]:
            result = await futuresearch_dedupe(
                DedupeInput(
                    equivalence_relation="Same person",
                    data=[{"name": "John Smith"}, {"name": "J. Smith"}],
                ),
                ctx,
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_dedupe")

    @pytest.mark.asyncio
    async def test_merge_content(self):
        _task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools.merge_async"
        )
        with patches[0], patches[1]:
            result = await futuresearch_merge(
                MergeInput(
                    task="Match products to suppliers",
                    left_data=[{"product_name": "Photoshop", "vendor": "Adobe"}],
                    right_data=[{"company_name": "Adobe Inc", "approved": True}],
                ),
                ctx,
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_merge")


# ── Progress tool ─────────────────────────────────────────────────────


class TestStdioProgressContent:
    """Progress responses must be concise status text, no widget JSON."""

    @pytest.mark.asyncio
    async def test_running_status(self):
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_resp = _make_status_response(
            status="running", completed=3, running=4, failed=1, total=10
        )

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_progress (running)")
        text = result[0].text
        assert "3/10" in text
        assert "futuresearch_progress" in text

    @pytest.mark.asyncio
    async def test_completed_status(self):
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_resp = _make_status_response(status="completed", completed=5, total=5)

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_progress (completed)")
        text = result[0].text
        assert "futuresearch_results" in text
        # Stdio completion message should instruct model to provide output_path
        assert "output_path" in text

    @pytest.mark.asyncio
    async def test_error_status(self):
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API timeout"),
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_progress (error)")
        assert "Error polling task" in result[0].text

    @pytest.mark.asyncio
    async def test_failed_task_with_error_message(self):
        """Failed tasks should report the error, not widget JSON."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_resp = _make_status_response(
            status="failed", completed=3, failed=2, total=5
        )
        status_resp.error = "Rate limit exceeded"

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_progress (failed)")
        assert "Rate limit exceeded" in result[0].text


# ── Results tool ──────────────────────────────────────────────────────


class TestStdioResultsContent:
    """Results in stdio mode must save to file — no widget data, no download URLs."""

    @pytest.mark.asyncio
    async def test_results_with_output_path(self, tmp_path: Path):
        task_id = str(uuid4())
        output_file = tmp_path / "output.csv"
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        rows = [{"name": "Acme", "score": "85"}, {"name": "Beta", "score": "42"}]
        status_resp = _make_status_response(status="completed")

        # Configure mock httpx response for _fetch_task_result
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"X-Total-Row-Count": str(len(rows))}
        mock_resp.json.return_value = {
            "data": rows,
            "artifact_id": str(uuid4()),
            "status": "completed",
            "task_id": task_id,
        }
        mock_client.get_async_httpx_client.return_value.request = AsyncMock(
            return_value=mock_resp
        )

        with patch(
            "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_resp,
        ):
            result = await futuresearch_results_stdio(
                StdioResultsInput(task_id=task_id, output_path=str(output_file)), ctx
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_results_stdio (save)")
        assert "Saved 2 rows" in result[0].text
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_results_task_not_ready(self, tmp_path: Path):
        """When task isn't completed yet, response is clean."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        status_resp = _make_status_response(status="running")

        with (
            patch(
                "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
        ):
            result = await futuresearch_results_stdio(
                StdioResultsInput(task_id=task_id, output_path=str(output_file)), ctx
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_results (not ready)")
        assert "running" in result[0].text
        assert "futuresearch_progress" in result[0].text

    @pytest.mark.asyncio
    async def test_results_api_error(self, tmp_path: Path):
        """API errors produce clean error text, not JSON."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        with (
            patch(
                "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Connection refused"),
            ),
        ):
            result = await futuresearch_results_stdio(
                StdioResultsInput(task_id=task_id, output_path=str(output_file)), ctx
            )

        assert len(result) == 1
        assert_stdio_clean(result, tool_name="futuresearch_results (error)")
        assert "Error" in result[0].text


# ── Tool description tests ────────────────────────────────────────────


class TestToolSchemas:
    """Verify tool schemas expose the expected fields."""

    @pytest.mark.parametrize(
        "tool_name,def_name",
        [
            ("futuresearch_agent", "AgentInput"),
            ("futuresearch_rank", "RankInput"),
            ("futuresearch_dedupe", "DedupeInput"),
        ],
    )
    def test_schema_has_artifact_id_and_data(self, tool_name: str, def_name: str):
        """Processing tools expose both artifact_id and data."""
        tool = mcp_app._tool_manager.get_tool(tool_name)
        assert tool is not None
        input_def = tool.parameters["$defs"][def_name]
        assert "artifact_id" in input_def["properties"]
        assert "data" in input_def["properties"]

    def test_merge_schema_has_artifact_id_and_data_fields(self):
        """futuresearch_merge exposes left/right artifact_id and data fields."""
        tool = mcp_app._tool_manager.get_tool("futuresearch_merge")
        assert tool is not None
        merge_def = tool.parameters["$defs"]["MergeInput"]
        assert "left_artifact_id" in merge_def["properties"]
        assert "right_artifact_id" in merge_def["properties"]
        assert "left_data" in merge_def["properties"]
        assert "right_data" in merge_def["properties"]


# ── HTTP mode contrast tests ─────────────────────────────────────────


class TestHttpModeIncludesWidgets:
    """Verify HTTP mode DOES include widget data (confirming the gate works both ways)."""

    @pytest.mark.asyncio
    async def test_submit_http_has_widget_json(self, fake_redis):
        """HTTP mode must include widget JSON as the first TextContent."""
        _task, _session, _client, ctx, *patches = _submit_patches(
            "futuresearch_mcp.tools._submit_agent_map"
        )
        fake_token = MagicMock()
        fake_token.client_id = "test-user-123"
        _get_fernet.cache_clear()
        try:
            with (
                patches[0],
                patches[1],
                patch.object(settings, "transport", Transport.HTTP),
                patch.object(settings, "upload_secret", "test-secret"),
                patch.object(redis_store, "get_redis_client", return_value=fake_redis),
            ):
                result = await futuresearch_agent(
                    AgentInput(task="Find HQ", data=[{"name": "TechStart"}]), ctx
                )
        finally:
            _get_fernet.cache_clear()

        assert len(result) == 2
        widget = json.loads(result[0].text)
        assert "task_id" in widget
        assert "status" in widget
        # Human text is second
        assert "Task ID:" in result[1].text

    @pytest.mark.asyncio
    async def test_progress_http_returns_text_only(self):
        """HTTP mode progress returns only human-readable text (no widget JSON)."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_resp = _make_status_response(status="running", completed=3, total=10)

        with (
            patch.object(settings, "transport", Transport.HTTP),
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert "3/10 complete" in result[0].text

    @pytest.mark.asyncio
    async def test_progress_http_completed_no_output_path_hint(self):
        """HTTP completion message should NOT tell model to ask for output_path."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_resp = _make_status_response(status="completed", completed=5, total=5)

        with (
            patch.object(settings, "transport", Transport.HTTP),
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_resp,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        human_text = result[-1].text
        assert "output_path" not in human_text
        assert "futuresearch_results" in human_text
        # total=5 is below auto_page_size_threshold, so page_size=total.
        assert "load the first rows" in human_text.lower()


# ── MCP protocol integration tests (real API) ────────────────────────

_skip_unless_integration = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run",
)


@asynccontextmanager
async def _stdio_mcp_client(sdk_client):
    """MCP ClientSession in stdio mode (no HTTP state, noop lifespan).

    The lifespan yields a singleton client factory wrapping ``sdk_client``.
    """
    orig_lifespan = mcp_app._mcp_server.lifespan

    @asynccontextmanager
    async def _noop_lifespan(_server):
        yield SessionContext(client_factory=lambda: sdk_client)

    mcp_app._mcp_server.lifespan = lifespan_wrapper(mcp_app, _noop_lifespan)

    try:
        async with create_connected_server_and_client_session(mcp_app) as session:
            yield session
    finally:
        mcp_app._mcp_server.lifespan = orig_lifespan


def _extract_task_id(text: str) -> str:
    """Extract task_id from human-readable submission text."""
    match = re.search(r"Task ID: ([a-f0-9-]+)", text)
    if not match:
        raise ValueError(f"Could not extract task_id from: {text}")
    return match.group(1)


@_skip_unless_integration
class TestStdioMcpIntegration:
    """Full submit → progress → results pipeline through MCP protocol in stdio mode.

    Uses real FutureSearch API calls and asserts every response the model would
    see is free of HTTP-only content (widget JSON, download URLs, tokens).

    Run with: RUN_INTEGRATION_TESTS=1 pytest tests/test_stdio_content.py -k Integration -v -s
    """

    @pytest.fixture
    def _real_stdio_client(self):
        """Provide a real FutureSearch client in stdio mode (default transport)."""
        assert settings.transport == "stdio", "Settings should default to stdio"
        with create_client() as sdk_client:
            yield sdk_client

    @pytest.mark.asyncio
    async def test_agent_pipeline_stdio_clean(self, _real_stdio_client, tmp_path):
        """Agent: submit → poll → results. Every response must be stdio-clean."""
        async with _stdio_mcp_client(_real_stdio_client) as session:
            # ── Submit ──
            submit = await session.call_tool(
                "futuresearch_agent",
                {
                    "params": {
                        "task": "Find this company's headquarters city.",
                        "data": [{"name": "Anthropic"}],
                        "response_schema": {
                            "properties": {
                                "headquarters": {
                                    "type": "string",
                                    "description": "City where HQ is located",
                                },
                            },
                            "required": ["headquarters"],
                        },
                    }
                },
            )

            assert not submit.isError
            _assert_mcp_result_clean(submit, tool_name="agent submit")
            assert len(submit.content) == 1
            assert isinstance(submit.content[0], TextContent)
            task_id = _extract_task_id(submit.content[0].text)
            print(f"\n  Submitted agent: {task_id}")

            # ── Poll ──
            for poll_num in range(30):
                progress = await session.call_tool(
                    "futuresearch_progress",
                    {"params": {"task_id": task_id}},
                )

                assert not progress.isError
                _assert_mcp_result_clean(
                    progress, tool_name=f"agent progress (poll {poll_num})"
                )
                assert len(progress.content) == 1

                assert isinstance(progress.content[0], TextContent)
                text = progress.content[0].text
                print(f"  Progress: {text.splitlines()[0]}")

                if "futuresearch_results" in text:
                    break
                if "failed" in text.lower() or "revoked" in text.lower():
                    pytest.fail(f"Task failed: {text}")
            else:
                pytest.fail("Agent task did not complete within 30 polls")

            # ── Results ──
            output_file = tmp_path / "agent_output.csv"
            results = await session.call_tool(
                "futuresearch_results",
                {
                    "params": {
                        "task_id": task_id,
                        "output_path": str(output_file),
                    }
                },
            )

            assert not results.isError
            _assert_mcp_result_clean(results, tool_name="agent results")
            assert len(results.content) == 1
            assert isinstance(results.content[0], TextContent)
            assert "Saved" in results.content[0].text
            assert output_file.exists()

            df = pd.read_csv(output_file)
            assert len(df) == 1
            print(f"  Results: {results.content[0].text}")
            print(f"  Output columns: {list(df.columns)}")

    @pytest.mark.asyncio
    async def test_single_agent_pipeline_stdio_clean(
        self, _real_stdio_client, tmp_path
    ):
        """Single agent: submit → poll → results. Every response must be stdio-clean."""
        async with _stdio_mcp_client(_real_stdio_client) as session:
            # ── Submit ──
            submit = await session.call_tool(
                "futuresearch_single_agent",
                {
                    "params": {
                        "task": "What city is Anthropic headquartered in?",
                    }
                },
            )

            assert not submit.isError
            _assert_mcp_result_clean(submit, tool_name="single_agent submit")
            assert len(submit.content) == 1
            assert isinstance(submit.content[0], TextContent)
            task_id = _extract_task_id(submit.content[0].text)
            print(f"\n  Submitted single_agent: {task_id}")

            # ── Poll ──
            for poll_num in range(30):
                progress = await session.call_tool(
                    "futuresearch_progress",
                    {"params": {"task_id": task_id}},
                )

                assert not progress.isError
                _assert_mcp_result_clean(
                    progress, tool_name=f"single_agent progress (poll {poll_num})"
                )
                assert len(progress.content) == 1

                assert isinstance(progress.content[0], TextContent)
                text = progress.content[0].text
                print(f"  Progress: {text.splitlines()[0]}")

                if "futuresearch_results" in text:
                    break
                if "failed" in text.lower() or "revoked" in text.lower():
                    pytest.fail(f"Task failed: {text}")
            else:
                pytest.fail("Single agent task did not complete within 30 polls")

            # ── Results ──
            output_file = tmp_path / "single_agent_output.csv"
            results = await session.call_tool(
                "futuresearch_results",
                {
                    "params": {
                        "task_id": task_id,
                        "output_path": str(output_file),
                    }
                },
            )

            assert not results.isError
            _assert_mcp_result_clean(results, tool_name="single_agent results")
            assert len(results.content) == 1
            assert isinstance(results.content[0], TextContent)
            assert output_file.exists()
            print(f"  Results: {results.content[0].text}")

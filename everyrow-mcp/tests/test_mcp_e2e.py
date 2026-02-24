"""End-to-end MCP protocol tests using ClientSession.

Tests the full JSON-RPC → FastMCP tool dispatch → tool function → response
pipeline, exactly as a real MCP client would experience it. Uses the MCP SDK's
in-memory transport for fast, reliable in-process testing.

Two tiers:
- TestMcpProtocol: always runs, mocked SDK (fast, CI-safe)
- TestMcpE2ERealApi: gated by RUN_INTEGRATION_TESTS=1, real API calls
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from everyrow.api_utils import create_client
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse
from mcp.server.fastmcp.server import lifespan_wrapper
from mcp.shared.memory import create_connected_server_and_client_session

# Import tools module to trigger @mcp.tool() registration on the FastMCP instance
import everyrow_mcp.tools  # noqa: F401
from everyrow_mcp import redis_store
from everyrow_mcp.app import mcp as mcp_app
from everyrow_mcp.tool_helpers import SessionContext
from tests.conftest import override_settings

# ── Fixtures / helpers ────────────────────────────────────────


@pytest.fixture
def _http_state(fake_redis):
    """Configure settings for HTTP mode and patch Redis."""
    with (
        override_settings(transport="streamable-http"),
        patch.object(redis_store, "get_redis_client", return_value=fake_redis),
    ):
        yield


@asynccontextmanager
async def mcp_client():
    """MCP ClientSession connected to the server via in-memory transport.

    Must be used as ``async with mcp_client() as session:`` inside the test
    function (not as a fixture) so the anyio task groups enter and exit in the
    same asyncio task — avoiding cancel-scope conflicts with pytest-asyncio.
    """
    orig_lifespan = mcp_app._mcp_server.lifespan

    @asynccontextmanager
    async def _noop_lifespan(_server):
        yield SessionContext(
            client_factory=lambda: MagicMock(token="fake-token"),
            mcp_server_url="http://testserver",
        )

    mcp_app._mcp_server.lifespan = lifespan_wrapper(mcp_app, _noop_lifespan)

    try:
        async with create_connected_server_and_client_session(mcp_app) as session:
            yield session
    finally:
        mcp_app._mcp_server.lifespan = orig_lifespan


def _mock_task(task_id: str | None = None):
    """Create a mock CohortTask returned by SDK async ops."""
    tid = task_id or str(uuid4())
    mock = MagicMock()
    mock.task_id = tid
    return mock


def _mock_session():
    """Create a mock session context manager."""
    session = MagicMock()
    session.get_url.return_value = "https://app.everyrow.io/session/test-session"

    @asynccontextmanager
    async def _fake_create_session(**_kwargs):
        yield session

    return session, _fake_create_session


def _mock_status_response(
    *,
    task_id: str | None = None,
    status: str = "running",
    completed: int = 3,
    total: int = 10,
    failed: int = 0,
    running: int = 2,
) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=task_id or uuid4(),
        session_id=uuid4(),
        status=TaskStatus(status),
        task_type=PublicTaskType.AGENT,
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


# ── TestMcpProtocol — always runs (mocked SDK) ───────────────


class TestMcpProtocol:
    """Verify the MCP protocol layer works correctly with mocked SDK calls."""

    @pytest.mark.asyncio
    async def test_list_tools(self, _http_state):
        """list_tools returns all 10 registered tools."""
        async with mcp_client() as session:
            result = await session.list_tools()
            tool_names = sorted(t.name for t in result.tools)
            expected = sorted(
                [
                    "everyrow_agent",
                    "everyrow_cancel",
                    "everyrow_dedupe",
                    "everyrow_forecast",
                    "everyrow_merge",
                    "everyrow_progress",
                    "everyrow_rank",
                    "everyrow_results",
                    "everyrow_screen",
                    "everyrow_single_agent",
                ]
            )
            assert tool_names == expected

    @pytest.mark.asyncio
    async def test_call_screen_tool(self, _http_state, tmp_path):
        """Submit a screen task via MCP protocol and verify the response."""
        df = pd.DataFrame([{"company": "Acme", "role": "Engineer"}])
        csv_path = tmp_path / "test.csv"
        df.to_csv(csv_path, index=False)

        task_id = str(uuid4())
        mock_task = _mock_task(task_id)
        _, fake_create_session = _mock_session()

        async with mcp_client() as session:
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=MagicMock(token="fake-token"),
                ),
                patch(
                    "everyrow_mcp.tools.screen_async",
                    new_callable=AsyncMock,
                    return_value=mock_task,
                ),
                patch(
                    "everyrow_mcp.tools.create_session",
                    side_effect=fake_create_session,
                ),
            ):
                result = await session.call_tool(
                    "everyrow_screen",
                    {
                        "params": {
                            "task": "Filter for engineering roles",
                            "input_csv": str(csv_path),
                        }
                    },
                )

            assert not result.isError
            # HTTP mode returns 2 content items: widget JSON + human text
            assert len(result.content) == 2
            widget = json.loads(result.content[0].text)
            assert widget["task_id"] == task_id
            assert widget["status"] == "submitted"
            assert "progress_url" in widget
            assert task_id in result.content[1].text

    @pytest.mark.asyncio
    async def test_call_progress_tool(self, _http_state):
        """Check task progress via MCP protocol."""
        task_id = str(uuid4())
        status_resp = _mock_status_response(
            task_id=task_id,
            status="running",
            completed=5,
            total=10,
            running=3,
        )

        async with mcp_client() as session:
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=MagicMock(token="fake-token"),
                ),
                patch(
                    "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                    new_callable=AsyncMock,
                    return_value=status_resp,
                ),
                patch("everyrow_mcp.redis_store.PROGRESS_POLL_DELAY", 0),
            ):
                result = await session.call_tool(
                    "everyrow_progress",
                    {"params": {"task_id": task_id}},
                )

            assert not result.isError
            human_text = result.content[-1].text
            assert "5/10" in human_text
            assert "running" in human_text.lower() or "Running" in human_text

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, _http_state):
        """Calling a non-existent tool returns an error."""
        async with mcp_client() as session:
            result = await session.call_tool("nonexistent_tool", {})
            assert result.isError

    @pytest.mark.asyncio
    async def test_missing_required_params(self, _http_state):
        """Calling a tool without required params returns a validation error."""
        async with mcp_client() as session:
            with patch(
                "everyrow_mcp.tools._get_client",
                return_value=MagicMock(token="fake-token"),
            ):
                result = await session.call_tool("everyrow_screen", {"params": {}})

            assert result.isError

    @pytest.mark.asyncio
    async def test_call_agent_tool(self, _http_state, tmp_path):
        """Submit an agent task via MCP protocol."""
        df = pd.DataFrame([{"name": "Anthropic"}])
        csv_path = tmp_path / "companies.csv"
        df.to_csv(csv_path, index=False)

        task_id = str(uuid4())
        mock_task = _mock_task(task_id)
        _, fake_create_session = _mock_session()

        async with mcp_client() as session:
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=MagicMock(token="fake-token"),
                ),
                patch(
                    "everyrow_mcp.tools.agent_map_async",
                    new_callable=AsyncMock,
                    return_value=mock_task,
                ),
                patch(
                    "everyrow_mcp.tools.create_session",
                    side_effect=fake_create_session,
                ),
            ):
                result = await session.call_tool(
                    "everyrow_agent",
                    {
                        "params": {
                            "task": "Find the CEO",
                            "input_csv": str(csv_path),
                        }
                    },
                )

            assert not result.isError
            assert len(result.content) == 2
            widget = json.loads(result.content[0].text)
            assert widget["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_completed_progress_suggests_results(self, _http_state):
        """When progress reports completed, response tells to call everyrow_results."""
        task_id = str(uuid4())
        status_resp = _mock_status_response(
            task_id=task_id,
            status="completed",
            completed=10,
            total=10,
            failed=0,
            running=0,
        )

        async with mcp_client() as session:
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=MagicMock(token="fake-token"),
                ),
                patch(
                    "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                    new_callable=AsyncMock,
                    return_value=status_resp,
                ),
                patch("everyrow_mcp.redis_store.PROGRESS_POLL_DELAY", 0),
            ):
                result = await session.call_tool(
                    "everyrow_progress",
                    {"params": {"task_id": task_id}},
                )

            assert not result.isError
            human_text = result.content[-1].text
            assert "everyrow_results" in human_text

    @pytest.mark.asyncio
    async def test_call_agent_with_input_url(self, _http_state):
        """Submit agent via MCP protocol with input_csv URL — full JSON-RPC -> URL fetch -> SDK."""
        task_id = str(uuid4())
        mock_task = _mock_task(task_id)
        _, fake_create_session = _mock_session()

        csv_text = "name,industry\nAcme,Software\nBeta,AI\n"
        mock_response = httpx.Response(200, text=csv_text)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async with mcp_client() as session:
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=MagicMock(token="fake-token"),
                ),
                patch(
                    "everyrow_mcp.tools.agent_map_async",
                    new_callable=AsyncMock,
                    return_value=mock_task,
                ) as mock_op,
                patch(
                    "everyrow_mcp.tools.create_session",
                    side_effect=fake_create_session,
                ),
                patch(
                    "everyrow_mcp.utils.httpx.AsyncClient",
                    return_value=mock_http,
                ),
            ):
                result = await session.call_tool(
                    "everyrow_agent",
                    {
                        "params": {
                            "task": "Find HQ",
                            "input_csv": "https://example.com/data.csv",
                        }
                    },
                )

            assert not result.isError
            assert len(result.content) == 2
            widget = json.loads(result.content[0].text)
            assert widget["task_id"] == task_id

            # Verify the URL was fetched and DataFrame reached the SDK
            call_kwargs = mock_op.call_args[1]
            assert len(call_kwargs["input"]) == 2


# ── TestMcpE2ERealApi — real API tests ────────────────────────

_skip_unless_integration = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run",
)


def _extract_task_id(widget_json: str) -> str:
    data = json.loads(widget_json)
    return data["task_id"]


@_skip_unless_integration
class TestMcpE2ERealApi:
    """Full pipeline through MCP protocol with real everyrow API."""

    @pytest.fixture
    def _real_client(self, _http_state):
        """Provide a real everyrow SDK client."""
        with create_client() as sdk_client:
            yield sdk_client

    @pytest.mark.asyncio
    async def test_screen_pipeline(self, _real_client, jobs_csv):
        """Submit → poll → results via MCP protocol with real API."""
        async with mcp_client() as session:
            with patch(
                "everyrow_mcp.tools._get_client",
                return_value=_real_client,
            ):
                submit_result = await session.call_tool(
                    "everyrow_screen",
                    {
                        "params": {
                            "task": "Filter for remote positions",
                            "input_csv": jobs_csv,
                        }
                    },
                )

            assert not submit_result.isError
            task_id = _extract_task_id(submit_result.content[0].text)
            print(f"\nSubmitted screen task: {task_id}")

            # Poll until complete
            for _ in range(30):
                with patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=_real_client,
                ):
                    progress_result = await session.call_tool(
                        "everyrow_progress",
                        {"params": {"task_id": task_id}},
                    )

                assert not progress_result.isError
                text = progress_result.content[-1].text
                print(f"  Progress: {text.splitlines()[0]}")

                if "everyrow_results" in text:
                    break
                if "failed" in text.lower() or "revoked" in text.lower():
                    pytest.fail(f"Task failed: {text}")
            else:
                pytest.fail("Task did not complete within 30 polls")

            # Fetch results
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=_real_client,
                ),
                patch(
                    "everyrow_mcp.tools.try_cached_result",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "everyrow_mcp.tools.try_store_result",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                results = await session.call_tool(
                    "everyrow_results",
                    {"params": {"task_id": task_id}},
                )

            assert not results.isError
            print(f"  Results: {results.content[-1].text}")

    @pytest.mark.asyncio
    async def test_agent_pipeline(self, _real_client, tmp_path):
        """Submit agent → poll → results via MCP protocol with real API."""
        df = pd.DataFrame([{"name": "Anthropic"}, {"name": "OpenAI"}])
        csv_path = tmp_path / "companies.csv"
        df.to_csv(csv_path, index=False)

        async with mcp_client() as session:
            with patch(
                "everyrow_mcp.tools._get_client",
                return_value=_real_client,
            ):
                submit_result = await session.call_tool(
                    "everyrow_agent",
                    {
                        "params": {
                            "task": "Find the company's headquarters city.",
                            "input_csv": str(csv_path),
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

            assert not submit_result.isError
            task_id = _extract_task_id(submit_result.content[0].text)
            print(f"\nSubmitted agent task: {task_id}")

            # Poll until complete
            for _ in range(30):
                with patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=_real_client,
                ):
                    progress_result = await session.call_tool(
                        "everyrow_progress",
                        {"params": {"task_id": task_id}},
                    )

                assert not progress_result.isError
                text = progress_result.content[-1].text
                print(f"  Progress: {text.splitlines()[0]}")

                if "everyrow_results" in text:
                    break
                if "failed" in text.lower() or "revoked" in text.lower():
                    pytest.fail(f"Task failed: {text}")
            else:
                pytest.fail("Task did not complete within 30 polls")

            # Fetch results
            with (
                patch(
                    "everyrow_mcp.tools._get_client",
                    return_value=_real_client,
                ),
                patch(
                    "everyrow_mcp.tools.try_cached_result",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "everyrow_mcp.tools.try_store_result",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                results = await session.call_tool(
                    "everyrow_results",
                    {"params": {"task_id": task_id}},
                )

            assert not results.isError
            print(f"  Results: {results.content[-1].text}")

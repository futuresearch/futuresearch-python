"""Tests for the MCP server tools.

These tests mock the FutureSearch SDK operations to test the MCP tool logic
without making actual API calls.
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pandas as pd
import pytest
from futuresearch.constants import EveryrowError
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.generated.models.create_artifact_response import (
    CreateArtifactResponse,
)
from futuresearch.generated.models.dedupe_operation_strategy import (
    DedupeOperationStrategy,
)
from futuresearch.generated.models.llm_enum_public import LLMEnumPublic
from futuresearch.generated.models.public_task_type import PublicTaskType
from futuresearch.generated.models.task_progress_info import TaskProgressInfo
from futuresearch.generated.models.task_result_response import TaskResultResponse
from futuresearch.generated.models.task_result_response_data_type_0_item import (
    TaskResultResponseDataType0Item,
)
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.generated.models.task_status_response import TaskStatusResponse
from futuresearch.task import EffortLevel
from mcp.types import TextContent
from pydantic import ValidationError

from futuresearch_mcp import redis_store
from futuresearch_mcp.app import mcp as mcp_app
from futuresearch_mcp.models import (
    AgentInput,
    CancelInput,
    DedupeInput,
    HttpResultsInput,
    ListSessionsInput,
    MergeInput,
    ProgressInput,
    RankInput,
    SingleAgentInput,
    StdioResultsInput,
    UploadDataInput,
    UseListInput,
    _schema_to_model,
)
from futuresearch_mcp.tools import (
    _RESULTS_ANNOTATIONS,
    _RESULTS_META,
    futuresearch_agent,
    futuresearch_cancel,
    futuresearch_list_sessions,
    futuresearch_progress,
    futuresearch_results_http,
    futuresearch_results_stdio,
    futuresearch_single_agent,
    futuresearch_upload_data,
    futuresearch_use_list,
)
from tests.conftest import make_test_context, override_settings

# CSV fixtures are defined in conftest.py


class TestSchemaToModel:
    """Tests for _schema_to_model helper."""

    def test_simple_schema(self):
        """Test converting a simple schema."""
        schema = {
            "properties": {
                "score": {"type": "number", "description": "A score"},
                "name": {"type": "string", "description": "A name"},
            },
            "required": ["score"],
        }

        model = _schema_to_model("TestModel", schema)

        # Check model was created with correct fields
        assert "score" in model.model_fields
        assert "name" in model.model_fields

    def test_schema_without_required(self):
        """Test schema where all fields are optional."""
        schema = {
            "properties": {
                "value": {"type": "integer"},
            }
        }

        model = _schema_to_model("OptionalModel", schema)
        assert "value" in model.model_fields

    def test_all_types(self):
        """Test all supported JSON schema types."""
        schema = {
            "properties": {
                "str_field": {"type": "string"},
                "int_field": {"type": "integer"},
                "float_field": {"type": "number"},
                "bool_field": {"type": "boolean"},
            }
        }

        model = _schema_to_model("AllTypes", schema)
        assert len(model.model_fields) == 4

    def test_rejects_non_object_property_schema(self):
        """Property definitions must be JSON Schema objects."""
        schema = {
            "type": "object",
            "properties": {"score": "number"},
        }

        with pytest.raises(ValueError, match="Invalid property schema"):
            _schema_to_model("BadSchema", schema)


class TestInputValidation:
    """Tests for input validation."""

    def test_rank_input_validates_field_type(self):
        """Test RankInput validates field_type."""
        with pytest.raises(ValidationError, match="Input should be"):
            RankInput(
                task="test",
                artifact_id=str(uuid4()),
                field_name="score",
                field_type="invalid",  # pyright: ignore[reportArgumentType]
            )

    def test_merge_input_validates_artifact_ids(self):
        """Test MergeInput validates artifact IDs."""
        with pytest.raises(ValidationError, match="artifact_id must be a valid UUID"):
            MergeInput(
                task="test",
                left_artifact_id="not-a-uuid",
                right_artifact_id=str(uuid4()),
            )

    def test_agent_input_rejects_empty_response_schema(self):
        with pytest.raises(
            ValidationError, match="must include a non-empty top-level 'properties'"
        ):
            AgentInput(
                task="test",
                artifact_id=str(uuid4()),
                response_schema={},
            )

    def test_agent_input_rejects_shorthand_response_schema(self):
        """response_schema must be JSON Schema, not a field map."""
        with pytest.raises(
            ValidationError, match="must include a non-empty top-level 'properties'"
        ):
            AgentInput(
                task="test",
                artifact_id=str(uuid4()),
                response_schema={"population": "string", "year": "string"},
            )

    def test_tool_inputs_accept_example_schemas(self):
        uid = str(uuid4())

        AgentInput(
            task="test",
            artifact_id=uid,
            response_schema={
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                    },
                },
            },
        )
        AgentInput(
            task="test",
            data=[{"col": "val"}],
            response_schema={
                "type": "object",
                "properties": {
                    "annual_revenue": {
                        "type": "integer",
                        "description": "Annual revenue in USD",
                    },
                    "employee_count": {
                        "type": "integer",
                        "description": "Number of employees",
                    },
                },
                "required": ["annual_revenue"],
            },
        )


def _make_mock_task(task_id=None):
    """Create a mock EveryrowTask with a task_id."""
    task = MagicMock()
    task.task_id = task_id or uuid4()
    return task


def _make_mock_session(session_id=None):
    """Create a mock Session."""
    session = MagicMock()
    session.session_id = session_id or uuid4()
    session.get_url.return_value = (
        f"https://futuresearch.ai/sessions/{session.session_id}"
    )
    return session


def _make_mock_client():
    """Create a mock AuthenticatedClient."""
    client = AsyncMock(spec=AuthenticatedClient)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.token = "fake-token"
    return client


def _setup_httpx_result(
    mock_client: AsyncMock, data: list | dict, artifact_id: str = ""
) -> None:
    """Configure mock_client.get_async_httpx_client().request() to return a result response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {
        "X-Total-Row-Count": str(len(data) if isinstance(data, list) else 1)
    }
    mock_resp.json.return_value = {
        "data": data,
        "artifact_id": artifact_id or str(uuid4()),
        "status": "completed",
        "task_id": str(uuid4()),
    }
    mock_client.get_async_httpx_client.return_value.request = AsyncMock(
        return_value=mock_resp
    )


def _make_async_context_manager(return_value):
    """Create a mock async context manager that yields return_value."""

    @asynccontextmanager
    async def mock_ctx():
        yield return_value

    return mock_ctx()


def _make_task_status_response(
    *,
    task_id: UUID | None = None,
    session_id: UUID | None = None,
    status: str = "running",
    completed: int = 0,
    failed: int = 0,
    running: int = 0,
    pending: int = 0,
    total: int = 10,
) -> TaskStatusResponse:
    """Create a real TaskStatusResponse for testing."""
    return TaskStatusResponse(
        task_id=task_id or uuid4(),
        session_id=session_id or uuid4(),
        status=TaskStatus(status),
        task_type=PublicTaskType.AGENT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        progress=TaskProgressInfo(
            pending=pending,
            running=running,
            completed=completed,
            failed=failed,
            total=total,
        ),
    )


def _make_task_result_response(
    data: list[dict[str, Any]],
    *,
    task_id: UUID | None = None,
) -> TaskResultResponse:
    """Create a real TaskResultResponse for testing."""
    items = [TaskResultResponseDataType0Item.from_dict(d) for d in data]
    return TaskResultResponse(
        task_id=task_id or uuid4(),
        status=TaskStatus.COMPLETED,
        data=items,
    )


class TestAgent:
    """Tests for futuresearch_agent."""

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        """Test that submit returns immediately with task_id."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ for each company",
                data=[
                    {"name": "TechStart", "industry": "Software"},
                    {"name": "AILabs", "industry": "AI/ML"},
                ],
            )
            result = await futuresearch_agent(params, ctx)

            # In stdio mode, _with_ui returns only human-readable text
            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text
            assert "Session ID:" in text
            assert "futuresearch_progress" in text


class TestSingleAgent:
    """Tests for futuresearch_single_agent."""

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        """Test that submit returns immediately with task_id."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Find the current CEO of Apple",
            )
            result = await futuresearch_single_agent(params, ctx)
            text = result[0].text

            assert str(mock_task.task_id) in text
            assert "Session ID:" in text
            assert "futuresearch_progress" in text
            assert "single agent" in text

    @pytest.mark.asyncio
    async def test_submit_with_input_data(self):
        """Test that input_data is converted to a dynamic model."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Research this company's funding",
                input_data={"company": "Stripe", "url": "stripe.com"},
            )
            result = await futuresearch_single_agent(params, ctx)
            text = result[0].text

            assert str(mock_task.task_id) in text

            # Verify single_agent_async was called with an input model
            call_kwargs = mock_op.call_args[1]
            assert "input" in call_kwargs
            input_model = call_kwargs["input"]
            assert input_model.company == "Stripe"
            assert input_model.url == "stripe.com"

    @pytest.mark.asyncio
    async def test_submit_with_response_schema(self):
        """Test that response_schema creates a response model."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Find funding info",
                response_schema={
                    "type": "object",
                    "properties": {
                        "funding_round": {
                            "type": "string",
                            "description": "Latest funding round",
                        },
                    },
                    "required": ["funding_round"],
                },
            )
            result = await futuresearch_single_agent(params, ctx)
            text = result[0].text

            assert str(mock_task.task_id) in text

            # Verify response_model was passed
            call_kwargs = mock_op.call_args[1]
            assert "response_model" in call_kwargs

    def test_input_rejects_empty_task(self):
        """Test that SingleAgentInput rejects an empty task."""
        with pytest.raises(ValidationError):
            SingleAgentInput(task="")

    def test_input_rejects_invalid_response_schema(self):
        """Test that SingleAgentInput validates response_schema."""
        with pytest.raises(
            ValidationError, match="must include a non-empty top-level 'properties'"
        ):
            SingleAgentInput(
                task="test",
                response_schema={},
            )


class TestProgress:
    """Tests for futuresearch_progress."""

    @pytest.mark.asyncio
    async def test_progress_api_error(self):
        """Test progress with API error returns helpful message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            params = ProgressInput(task_id=task_id)
            result = await futuresearch_progress(params, ctx)

        # In stdio mode, only human-readable text is returned
        assert len(result) == 1
        assert "Error polling task" in result[0].text
        assert "Retry:" in result[0].text

    @pytest.mark.asyncio
    async def test_progress_running_task(self):
        """Test progress returns status counts for a running task."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_response = _make_task_status_response(
            status="running",
            completed=4,
            failed=1,
            running=3,
            pending=2,
            total=10,
        )

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            params = ProgressInput(task_id=task_id)
            result = await futuresearch_progress(params, ctx)

        # In stdio mode, only human-readable text is returned
        assert len(result) == 1
        text = result[0].text
        assert "4/10 complete" in text
        assert "1 failed" in text
        assert "3 running" in text
        assert "futuresearch_progress" in text

    @pytest.mark.asyncio
    async def test_progress_completed_task(self):
        """Test progress returns completion instructions when done."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        status_response = _make_task_status_response(
            status="completed",
            completed=5,
            failed=0,
            running=0,
            pending=0,
            total=5,
        )

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            params = ProgressInput(task_id=task_id)
            result = await futuresearch_progress(params, ctx)

        # In stdio mode, only human-readable text is returned
        assert len(result) == 1
        text = result[0].text
        assert "Completed: 5/5" in text
        assert "futuresearch_results" in text


class TestResults:
    """Tests for futuresearch_results."""

    @pytest.mark.asyncio
    async def test_results_api_error(self, tmp_path: Path):
        """Test results with API error returns helpful message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())
        output_file = tmp_path / "output.csv"

        with (
            patch(
                "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await futuresearch_results_stdio(params, ctx)

        assert "Error retrieving results" in result[0].text

    @pytest.mark.asyncio
    async def test_results_saves_csv(self, tmp_path: Path):
        """Test results retrieves data and saves to CSV."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        rows = [
            {"name": "TechStart", "answer": "Series A"},
            {"name": "AILabs", "answer": "Seed"},
        ]
        status_response = _make_task_status_response(status="completed")
        _setup_httpx_result(mock_client, rows)

        with patch(
            "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_response,
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await futuresearch_results_stdio(params, ctx)
        text = result[0].text

        assert "Saved 2 rows to" in text
        assert "output.csv" in text

        # Verify CSV was written
        output_df = pd.read_csv(output_file)
        assert len(output_df) == 2
        assert list(output_df.columns) == ["name", "answer"]

    @pytest.mark.asyncio
    async def test_results_scalar_single_agent(self, tmp_path: Path):
        """Test results handles scalar (single_agent) response as single-row dict."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        status_response = _make_task_status_response(status="completed")
        # Engine returns scalar as a single dict (not list)
        _setup_httpx_result(mock_client, {"ceo": "Tim Cook", "company": "Apple"})

        with patch(
            "futuresearch_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=status_response,
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await futuresearch_results_stdio(params, ctx)

        assert len(result) == 1
        assert "1 rows" in result[0].text

    @pytest.mark.asyncio
    async def test_results_http_store(self):
        """In HTTP mode, results are fetched and returned with download URL."""
        task_id = str(uuid4())
        session_id = str(uuid4())
        artifact_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        rows = [{"name": "A", "val": "1"}, {"name": "B", "val": "2"}]

        with (
            patch(
                "futuresearch_mcp.tools._fetch_task_result",
                new_callable=AsyncMock,
                return_value=(rows, 2, session_id, artifact_id),
            ),
            patch(
                "futuresearch_mcp.tools.clamp_page_to_budget",
                return_value=(rows, len(rows)),
            ),
            patch(
                "futuresearch_mcp.tools._get_csv_url",
                return_value="http://test/download",
            ),
            patch(
                "futuresearch_mcp.tools.redis_store.get_poll_token",
                new_callable=AsyncMock,
                return_value="poll-tok",
            ),
        ):
            result = await futuresearch_results_http(
                HttpResultsInput(task_id=task_id), ctx
            )

        assert result.structuredContent is not None
        assert "csv_url" in result.structuredContent
        block = result.content[0]
        assert isinstance(block, TextContent)
        assert "2 rows" in block.text

    @pytest.mark.asyncio
    async def test_results_http_single_row(self):
        """In HTTP mode, single-row results are returned correctly."""
        task_id = str(uuid4())
        session_id = str(uuid4())
        artifact_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        rows = [{"name": "A"}]

        with (
            patch(
                "futuresearch_mcp.tools._fetch_task_result",
                new_callable=AsyncMock,
                return_value=(rows, 1, session_id, artifact_id),
            ),
            patch(
                "futuresearch_mcp.tools.clamp_page_to_budget",
                return_value=(rows, len(rows)),
            ),
            patch(
                "futuresearch_mcp.tools._get_csv_url",
                return_value="http://test/download",
            ),
            patch(
                "futuresearch_mcp.tools.redis_store.get_poll_token",
                new_callable=AsyncMock,
                return_value="poll-tok",
            ),
        ):
            result = await futuresearch_results_http(
                HttpResultsInput(task_id=task_id), ctx
            )

        assert result.structuredContent is not None
        block = result.content[0]
        assert isinstance(block, TextContent)
        assert "1 rows" in block.text


class TestListSessions:
    """Tests for futuresearch_list_sessions."""

    @staticmethod
    def _make_session_list_result(sessions, *, total=None, offset=0, limit=25):
        """Create a mock SessionListResult."""
        tc = total if total is not None else len(sessions)
        result = MagicMock()
        result.sessions = sessions
        result.total = tc
        result.offset = offset
        result.limit = limit
        return result

    @pytest.mark.asyncio
    async def test_list_sessions_returns_sessions(self):
        """Test that list_sessions returns formatted session info."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        mock_sessions = [
            MagicMock(
                session_id=uuid4(),
                name="My Session",
                created_at=datetime(2025, 6, 1, 12, 0, tzinfo=UTC),
                updated_at=datetime(2025, 6, 1, 13, 0, tzinfo=UTC),
                get_url=lambda: "https://futuresearch.ai/sessions/abc",
            ),
            MagicMock(
                session_id=uuid4(),
                name="Another Session",
                created_at=datetime(2025, 6, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2025, 6, 2, 11, 0, tzinfo=UTC),
                get_url=lambda: "https://futuresearch.ai/sessions/def",
            ),
        ]

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result(mock_sessions),
        ):
            result = await futuresearch_list_sessions(ListSessionsInput(), ctx)

        text = result[0].text
        assert "2 session(s)" in text
        assert "My Session" in text
        assert "Another Session" in text

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        """Test that list_sessions handles no sessions."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result([]),
        ):
            result = await futuresearch_list_sessions(ListSessionsInput(), ctx)

        assert "No sessions found" in result[0].text

    @pytest.mark.asyncio
    async def test_list_sessions_api_error(self):
        """Test that list_sessions handles API errors gracefully."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            result = await futuresearch_list_sessions(ListSessionsInput(), ctx)

        assert "Error listing sessions" in result[0].text

    @pytest.mark.asyncio
    async def test_list_sessions_passes_client_and_pagination(self):
        """Test that the tool passes the context client and pagination params to list_sessions."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result([], offset=5, limit=10),
        ) as mock_ls:
            await futuresearch_list_sessions(ListSessionsInput(offset=5, limit=10), ctx)

        mock_ls.assert_called_once_with(client=mock_client, offset=5, limit=10)

    @pytest.mark.asyncio
    async def test_list_sessions_output_contains_urls_and_dates(self):
        """Test that the formatted output includes URLs and timestamps."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        session_id = uuid4()
        mock_sessions = [
            MagicMock(
                session_id=session_id,
                name="Pipeline Run",
                created_at=datetime(2025, 8, 15, 9, 30, tzinfo=UTC),
                updated_at=datetime(2025, 8, 15, 10, 45, tzinfo=UTC),
                get_url=lambda: f"https://futuresearch.ai/sessions/{session_id}",
            ),
        ]

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result(mock_sessions),
        ):
            result = await futuresearch_list_sessions(ListSessionsInput(), ctx)

        text = result[0].text
        assert "Pipeline Run" in text
        assert "2025-08-15 09:30 UTC" in text
        assert "2025-08-15 10:45 UTC" in text
        assert f"https://futuresearch.ai/sessions/{session_id}" in text

    @pytest.mark.asyncio
    async def test_list_sessions_pagination_params(self):
        """Test that limit and offset are passed through to SDK."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result(
                [], total=0, offset=5, limit=10
            ),
        ) as mock_ls:
            await futuresearch_list_sessions(ListSessionsInput(limit=10, offset=5), ctx)

        mock_ls.assert_called_once_with(client=mock_client, offset=5, limit=10)

    @pytest.mark.asyncio
    async def test_list_sessions_shows_pagination_info(self):
        """Test that output includes page info and next-page hint."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        now = datetime.now(UTC)
        mock_sessions = [
            MagicMock(
                session_id=uuid4(),
                name=f"Session {i}",
                created_at=now,
                updated_at=now,
                get_url=lambda: "https://futuresearch.ai/sessions/x",
            )
            for i in range(10)
        ]

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result(
                mock_sessions, total=30, offset=0, limit=10
            ),
        ):
            result = await futuresearch_list_sessions(ListSessionsInput(limit=10), ctx)

        text = result[0].text
        assert "showing 1-10" in text
        assert "30 session(s)" in text
        assert "Page 1 of 3" in text
        assert "offset=10" in text

    @pytest.mark.asyncio
    async def test_list_sessions_default_pagination(self):
        """Test that default params are offset=0, limit=25."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with patch(
            "futuresearch_mcp.tools.list_sessions",
            new_callable=AsyncMock,
            return_value=self._make_session_list_result([]),
        ) as mock_ls:
            await futuresearch_list_sessions(ListSessionsInput(), ctx)

        mock_ls.assert_called_once_with(client=mock_client, offset=0, limit=25)


class TestCancel:
    """Tests for futuresearch_cancel."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        """Test cancelling a running task returns success message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.return_value = None

            params = CancelInput(task_id=task_id)
            result = await futuresearch_cancel(params, ctx)

        text = result[0].text
        assert task_id in text
        assert "cancelled" in text.lower()

    @pytest.mark.asyncio
    async def test_cancel_already_terminated_task(self):
        """Test cancelling an already terminated task returns error."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = EveryrowError(
                f"Task {task_id} is already COMPLETED"
            )

            params = CancelInput(task_id=task_id)
            result = await futuresearch_cancel(params, ctx)

        text = result[0].text
        assert task_id in text
        assert "Failed" in text

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self):
        """Test cancelling a nonexistent task returns error."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = EveryrowError("Task not found")

            params = CancelInput(task_id=task_id)
            result = await futuresearch_cancel(params, ctx)

        text = result[0].text
        assert "Failed" in text

    @pytest.mark.asyncio
    async def test_cancel_api_error(self):
        """Test cancel with unexpected error returns error message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = RuntimeError("Network failure")

            params = CancelInput(task_id=task_id)
            result = await futuresearch_cancel(params, ctx)

        text = result[0].text
        assert "Error" in text

    def test_cancel_input_validation(self):
        """Test CancelInput strips whitespace, validates UUID, and forbids extra fields."""
        valid_uuid = str(uuid4())
        inp = CancelInput(task_id=f"  {valid_uuid}  ")
        assert inp.task_id == valid_uuid

        # Invalid UUID rejected
        with pytest.raises(ValidationError):
            CancelInput(task_id="not-a-uuid")

        # Extra fields forbidden
        with pytest.raises(ValidationError):
            CancelInput(task_id=valid_uuid, extra_field="x")  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]


class TestAgentInlineInput:
    """Tests for futuresearch_agent with inline data."""

    @pytest.mark.asyncio
    async def test_submit_with_inline_data(self):
        """Test agent submission with data instead of artifact_id."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ for each company",
                data=[
                    {"name": "TechStart", "industry": "Software"},
                    {"name": "AILabs", "industry": "AI"},
                ],
            )
            result = await futuresearch_agent(params, ctx)

            # In stdio mode, _with_ui returns only human-readable text
            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text
            assert "2 agents starting" in text

            # Verify the DataFrame passed to the SDK had 2 rows
            call_kwargs = mock_op.call_args[1]
            assert len(call_kwargs["input"]) == 2

    @pytest.mark.asyncio
    async def test_submit_with_artifact_id(self):
        """Test agent submission with artifact_id."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        uid = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(task="Find HQ", artifact_id=uid)
            result = await futuresearch_agent(params, ctx)

            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text

            # Verify the UUID was passed to the SDK
            call_kwargs = mock_op.call_args[1]
            assert call_kwargs["input"] == UUID(uid)


class TestAgentInputValidation:
    """Tests for AgentInput model validation with inline data."""

    def test_requires_one_input_source(self):
        """Test that no input source raises."""
        with pytest.raises(ValidationError, match="Provide exactly one of"):
            AgentInput(task="test")

    def test_rejects_both_input_sources(self):
        """Test that providing both raises."""
        with pytest.raises(ValidationError, match="Provide exactly one of"):
            AgentInput(
                task="test",
                artifact_id=str(uuid4()),
                data=[{"a": "b"}],
            )

    def test_accepts_artifact_id(self):
        """Test that artifact_id alone is valid."""
        uid = str(uuid4())
        params = AgentInput(task="test", artifact_id=uid)
        assert params.artifact_id == uid
        assert params.data is None

    def test_accepts_data_json_list(self):
        """Test that data as JSON list of dicts is valid."""
        records = [
            {"company": "Acme", "url": "acme.com"},
            {"company": "Beta", "url": "beta.io"},
        ]
        params = AgentInput(task="test", data=records)
        assert params.data == records
        assert params.artifact_id is None

    def test_effort_level_defaults_to_medium(self):
        """AgentInput defaults effort_level to medium."""
        params = AgentInput(task="test", data=[{"a": "b"}])
        assert params.effort_level == "medium"

    def test_accepts_effort_level_high(self):
        params = AgentInput(
            task="test", data=[{"a": "b"}], effort_level=EffortLevel.HIGH
        )
        assert params.effort_level == EffortLevel.HIGH

    def test_accepts_null_effort_level_with_custom_params(self):
        params = AgentInput(
            task="test",
            data=[{"a": "b"}],
            effort_level=None,
            llm=LLMEnumPublic.CLAUDE_4_6_SONNET_MEDIUM,
            iteration_budget=10,
            include_reasoning=True,
        )
        assert params.effort_level is None
        assert params.llm == LLMEnumPublic.CLAUDE_4_6_SONNET_MEDIUM
        assert params.iteration_budget == 10
        assert params.include_reasoning is True

    def test_enforce_row_independence_defaults_false(self):
        params = AgentInput(task="test", data=[{"a": "b"}])
        assert params.enforce_row_independence is False

    def test_rejects_invalid_iteration_budget(self):
        with pytest.raises(ValidationError):
            AgentInput(
                task="test",
                data=[{"a": "b"}],
                effort_level=None,
                iteration_budget=25,
            )

    def test_rejects_invalid_llm_value(self):
        with pytest.raises(ValidationError, match="type=enum"):
            AgentInput(
                task="test",
                data=[{"a": "b"}],
                effort_level=None,
                llm="not_a_real_model",  # type: ignore[arg-type]
            )

    def test_accepts_valid_llm_value(self):
        params = AgentInput(
            task="test",
            data=[{"a": "b"}],
            effort_level=None,
            llm=LLMEnumPublic.CLAUDE_4_6_SONNET_MEDIUM,
        )
        assert params.llm == LLMEnumPublic.CLAUDE_4_6_SONNET_MEDIUM


class TestUploadData:
    """Tests for futuresearch_upload_data."""

    @pytest.mark.asyncio
    async def test_upload_from_url(self):
        """Test uploading data from a URL."""
        mock_client = _make_mock_client()
        mock_session = _make_mock_session()
        ctx = make_test_context(mock_client)
        artifact_uuid = uuid4()

        mock_df = pd.DataFrame([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        task_uuid = uuid4()
        upload_response = CreateArtifactResponse(
            artifact_id=artifact_uuid,
            session_id=mock_session.session_id,
            task_id=task_uuid,
        )

        with (
            patch(
                "futuresearch_mcp.tools.fetch_csv_from_url",
                new_callable=AsyncMock,
                return_value=mock_df,
            ),
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch(
                "futuresearch_mcp.tools.create_table_artifact",
                new_callable=AsyncMock,
                return_value=upload_response,
            ) as mock_create,
        ):
            params = UploadDataInput(source="https://example.com/data.csv")
            result = await futuresearch_upload_data(params, ctx)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["artifact_id"] == str(artifact_uuid)
        assert data["task_id"] == str(task_uuid)
        assert data["rows"] == 2
        assert data["columns"] == ["a", "b"]
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_from_local_path(self, tmp_path: Path):
        """Test uploading data from a local CSV file (stdio mode)."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("x,y\n1,2\n3,4\n")

        mock_client = _make_mock_client()
        mock_session = _make_mock_session()
        ctx = make_test_context(mock_client)
        artifact_uuid = uuid4()
        upload_response = CreateArtifactResponse(
            artifact_id=artifact_uuid,
            session_id=mock_session.session_id,
            task_id=uuid4(),
        )

        with (
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch(
                "futuresearch_mcp.tools.create_table_artifact",
                new_callable=AsyncMock,
                return_value=upload_response,
            ),
        ):
            params = UploadDataInput(source=str(csv_file))
            result = await futuresearch_upload_data(params, ctx)

        data = json.loads(result[0].text)
        assert data["artifact_id"] == str(artifact_uuid)
        assert data["rows"] == 2

    def test_upload_rejects_local_path_in_http_mode(self, tmp_path: Path):
        """Test that local paths are rejected in HTTP mode."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("x,y\n1,2\n")

        with override_settings(
            transport="streamable-http", upload_secret="test-secret"
        ):
            with pytest.raises(
                ValidationError, match="Local file paths are not supported"
            ):
                UploadDataInput(source=str(csv_file))

    def test_upload_accepts_url_in_http_mode(self):
        """Test that URLs are accepted in HTTP mode."""
        with override_settings(
            transport="streamable-http", upload_secret="test-secret"
        ):
            params = UploadDataInput(source="https://example.com/data.csv")
            assert params.source == "https://example.com/data.csv"

    @pytest.mark.asyncio
    async def test_upload_from_url_http_mode_registers_poll_token(self):
        """In HTTP mode, poll token is registered for results lookup."""
        mock_client = _make_mock_client()
        mock_session = _make_mock_session()
        ctx = make_test_context(mock_client)
        artifact_uuid = uuid4()
        task_uuid = uuid4()

        mock_df = pd.DataFrame([{"a": 1}])
        upload_response = CreateArtifactResponse(
            artifact_id=artifact_uuid,
            session_id=mock_session.session_id,
            task_id=task_uuid,
        )

        with (
            override_settings(transport="streamable-http"),
            patch(
                "futuresearch_mcp.tools.fetch_csv_from_url",
                new_callable=AsyncMock,
                return_value=mock_df,
            ),
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch(
                "futuresearch_mcp.tools.create_table_artifact",
                new_callable=AsyncMock,
                return_value=upload_response,
            ),
            patch(
                "futuresearch_mcp.tools._record_task_ownership",
                new_callable=AsyncMock,
                return_value="fake-poll-token",
            ) as mock_record,
        ):
            params = UploadDataInput(source="https://example.com/data.csv")
            await futuresearch_upload_data(params, ctx)

        mock_record.assert_called_once_with(str(task_uuid), mock_client.token)

    def test_upload_google_sheets_url(self):
        """Test that Google Sheets URLs are accepted."""
        url = "https://docs.google.com/spreadsheets/d/1abc/edit#gid=0"
        params = UploadDataInput(source=url)
        assert params.source == url


class TestResultsInputValidation:
    """Tests for StdioResultsInput and HttpResultsInput."""

    def test_stdio_requires_output_path(self):
        """Test that StdioResultsInput requires output_path."""
        with pytest.raises(ValidationError):
            StdioResultsInput(task_id="00000000-0000-0000-0000-000000000000")  # pyright: ignore[reportCallIssue]

    def test_stdio_output_path_validated(self, tmp_path: Path):
        """Test that output_path is validated when provided."""
        params = StdioResultsInput(
            task_id="00000000-0000-0000-0000-000000000000",
            output_path=str(tmp_path / "out.csv"),
        )
        assert params.output_path is not None

    def test_stdio_output_path_rejects_non_csv(self, tmp_path: Path):
        """Test that non-CSV output_path is rejected."""
        with pytest.raises(ValidationError, match=r"must end in \.csv"):
            StdioResultsInput(
                task_id="00000000-0000-0000-0000-000000000000",
                output_path=str(tmp_path / "out.txt"),
            )

    def test_http_output_path_optional(self):
        """Test that HttpResultsInput allows omitting output_path."""
        params = HttpResultsInput(task_id="00000000-0000-0000-0000-000000000000")
        assert params.output_path is None

    def test_http_output_path_validated(self, tmp_path: Path):
        """Test that HttpResultsInput validates output_path when provided."""
        params = HttpResultsInput(
            task_id="00000000-0000-0000-0000-000000000000",
            output_path=str(tmp_path / "out.csv"),
        )
        assert params.output_path is not None

    def test_http_output_path_rejects_non_csv(self, tmp_path: Path):
        """Test that non-CSV output_path is rejected in HTTP mode too."""
        with pytest.raises(ValidationError, match=r"must end in \.csv"):
            HttpResultsInput(
                task_id="00000000-0000-0000-0000-000000000000",
                output_path=str(tmp_path / "out.txt"),
            )


class TestHttpResultsToolOverride:
    """Verify that the HTTP override replaces the stdio results tool schema."""

    def test_default_registration_uses_stdio_schema(self):
        """Before override, futuresearch_results uses StdioResultsInput."""
        tool = mcp_app._tool_manager.get_tool("futuresearch_results")
        assert tool is not None
        assert "StdioResultsInput" in tool.parameters["$defs"]

    def test_http_override_replaces_schema(self):
        """After remove + re-register, futuresearch_results uses HttpResultsInput."""
        # Simulate what server.py does for HTTP mode
        mcp_app._tool_manager.remove_tool("futuresearch_results")
        mcp_app.tool(
            name="futuresearch_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
            meta=_RESULTS_META,
        )(futuresearch_results_http)

        tool = mcp_app._tool_manager.get_tool("futuresearch_results")
        assert tool is not None
        assert "HttpResultsInput" in tool.parameters["$defs"]
        assert "output_path" not in tool.parameters["$defs"]["HttpResultsInput"].get(
            "required", []
        )

        # Restore stdio default for other tests
        mcp_app._tool_manager.remove_tool("futuresearch_results")
        mcp_app.tool(
            name="futuresearch_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
            meta=_RESULTS_META,
        )(futuresearch_results_stdio)


class TestInputModelsUnchanged:
    """Verify that input models require an input source."""

    def test_rank_requires_input_source(self):
        """RankInput requires either artifact_id or data."""
        with pytest.raises(ValidationError):
            RankInput(task="test", field_name="score")

    def test_rank_accepts_data(self):
        """RankInput accepts data as alternative to artifact_id."""
        params = RankInput(
            task="test",
            field_name="score",
            data=[{"col": "val"}],
        )
        assert params.data == [{"col": "val"}]
        assert params.artifact_id is None

    def test_rank_rejects_both_inputs(self):
        """RankInput rejects both artifact_id and data."""
        with pytest.raises(ValidationError):
            RankInput(
                task="test",
                field_name="score",
                artifact_id=str(uuid4()),
                data=[{"col": "val"}],
            )

    def test_dedupe_requires_input_source(self):
        """DedupeInput requires either artifact_id or data."""
        with pytest.raises(ValidationError):
            DedupeInput(equivalence_relation="same entity")

    def test_dedupe_accepts_strategy(self):
        params = DedupeInput(
            equivalence_relation="same entity",
            data=[{"a": "b"}],
            strategy=DedupeOperationStrategy.COMBINE,
            strategy_prompt="Keep the most complete record",
        )
        assert params.strategy == DedupeOperationStrategy.COMBINE
        assert params.strategy_prompt == "Keep the most complete record"

    def test_dedupe_strategy_defaults_to_none(self):
        params = DedupeInput(
            equivalence_relation="same entity",
            data=[{"a": "b"}],
        )
        assert params.strategy is None
        assert params.strategy_prompt is None

    def test_merge_requires_input_sources(self):
        """MergeInput requires left and right input sources."""
        with pytest.raises(ValidationError):
            MergeInput(task="test")


class TestStdioVsHttpGating:
    """Verify that widget JSON is only included in HTTP mode responses."""

    @pytest.mark.asyncio
    async def test_submit_stdio_returns_single_content(self):
        """In stdio mode, submission tools return only human-readable text."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task
            params = AgentInput(
                task="test",
                data=[{"name": "TechStart", "industry": "Software"}],
            )
            result = await futuresearch_agent(params, ctx)

        assert len(result) == 1
        assert "Task ID:" in result[0].text

    @pytest.mark.asyncio
    async def test_submit_http_returns_widget_and_text(self, fake_redis):
        """In HTTP mode, submission tools return widget JSON + human text."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        fake_token = MagicMock()
        fake_token.client_id = "test-user-123"

        with (
            override_settings(transport="streamable-http", upload_secret="test-secret"),
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch.object(redis_store, "get_redis_client", return_value=fake_redis),
            patch(
                "futuresearch_mcp.tool_helpers.get_access_token",
                return_value=fake_token,
            ),
        ):
            mock_op.return_value = mock_task
            params = AgentInput(
                task="test",
                data=[{"name": "TechStart", "industry": "Software"}],
            )
            result = await futuresearch_agent(params, ctx)

        assert len(result) == 2
        ui_data = json.loads(result[0].text)
        assert ui_data["task_id"] == str(mock_task.task_id)
        assert ui_data["status"] == "submitted"
        assert "Task ID:" in result[1].text

    @pytest.mark.asyncio
    async def test_progress_stdio_returns_single_content(self):
        """In stdio mode, progress returns only human-readable text."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())
        status_response = _make_task_status_response(
            status="running", completed=2, total=5
        )

        with (
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert "2/5 complete" in result[0].text

    @pytest.mark.asyncio
    async def test_progress_http_returns_text_only(self):
        """In HTTP mode, progress returns only human-readable text."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())
        status_response = _make_task_status_response(
            status="running", completed=2, total=5
        )

        with (
            override_settings(transport="streamable-http", upload_secret="test-secret"),
            patch(
                "futuresearch_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("futuresearch_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch(
                "futuresearch_mcp.tools._check_task_ownership",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert "2/5 complete" in result[0].text


class TestResultsWidgetData:
    """Tests for the HTTP mode widget data in futuresearch_results."""

    @pytest.mark.asyncio
    async def test_http_widget_includes_csv_url(self):
        """Verify csv_url is present in widget JSON when results are fetched."""
        task_id = str(uuid4())
        session_id = str(uuid4())
        artifact_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        rows = [{"name": "A"}]
        csv_url = "https://example.com/api/results/123/download"

        with (
            patch(
                "futuresearch_mcp.tools._fetch_task_result",
                new_callable=AsyncMock,
                return_value=(rows, 1, session_id, artifact_id),
            ),
            patch(
                "futuresearch_mcp.tools.clamp_page_to_budget",
                return_value=(rows, len(rows)),
            ),
            patch(
                "futuresearch_mcp.tools._get_csv_url",
                return_value=csv_url,
            ),
            patch(
                "futuresearch_mcp.tools.redis_store.get_poll_token",
                new_callable=AsyncMock,
                return_value="poll-tok",
            ),
        ):
            result = await futuresearch_results_http(
                HttpResultsInput(task_id=task_id), ctx
            )

        assert result.structuredContent is not None
        assert result.structuredContent["csv_url"] == csv_url


# ---------- Session resumption / naming ----------


class TestSessionParams:
    """Tests for session_id and session_name fields on input models."""

    # ── Input validation ─────────────────────────────────────

    def test_single_source_accepts_session_id(self):
        uid = str(uuid4())
        params = AgentInput(task="test", artifact_id=str(uuid4()), session_id=uid)
        assert params.session_id == uid

    def test_single_source_accepts_session_name(self):
        params = AgentInput(
            task="test", artifact_id=str(uuid4()), session_name="My Session"
        )
        assert params.session_name == "My Session"

    def test_single_source_rejects_both_session_params(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            AgentInput(
                task="test",
                artifact_id=str(uuid4()),
                session_id=str(uuid4()),
                session_name="conflict",
            )

    def test_single_source_rejects_invalid_session_id(self):
        with pytest.raises(ValidationError, match="session_id must be a valid UUID"):
            AgentInput(
                task="test",
                artifact_id=str(uuid4()),
                session_id="not-a-uuid",
            )

    def test_merge_accepts_session_id(self):
        params = MergeInput(
            task="match",
            left_data=[{"a": 1}],
            right_data=[{"b": 2}],
            session_id=str(uuid4()),
        )
        assert params.session_id is not None

    def test_merge_rejects_both_session_params(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            MergeInput(
                task="match",
                left_data=[{"a": 1}],
                right_data=[{"b": 2}],
                session_id=str(uuid4()),
                session_name="conflict",
            )

    def test_single_agent_accepts_session_id(self):
        params = SingleAgentInput(task="test", session_id=str(uuid4()))
        assert params.session_id is not None

    def test_single_agent_effort_level_defaults_to_medium(self):
        params = SingleAgentInput(task="test")
        assert params.effort_level == "medium"

    def test_single_agent_accepts_custom_params(self):
        params = SingleAgentInput(
            task="test",
            effort_level=None,
            llm=LLMEnumPublic.GPT_5_HIGH,
            iteration_budget=5,
            include_reasoning=True,
        )
        assert params.effort_level is None
        assert params.llm == LLMEnumPublic.GPT_5_HIGH
        assert params.iteration_budget == 5
        assert params.include_reasoning is True

    def test_single_agent_rejects_both_session_params(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            SingleAgentInput(
                task="test",
                session_id=str(uuid4()),
                session_name="conflict",
            )

    def test_upload_data_accepts_session_id(self):
        params = UploadDataInput(
            source="https://example.com/data.csv", session_id=str(uuid4())
        )
        assert params.session_id is not None

    def test_upload_data_rejects_both_session_params(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            UploadDataInput(
                source="https://example.com/data.csv",
                session_id=str(uuid4()),
                session_name="conflict",
            )

    # ── Tool invocations ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_agent_passes_session_params(self):
        """futuresearch_agent forwards session_id and session_name to create_session."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        sid = str(uuid4())

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch("futuresearch_mcp.tools.create_session") as mock_cs,
        ):
            mock_cs.return_value = _make_async_context_manager(mock_session)
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ",
                data=[{"name": "Acme"}],
                session_id=sid,
            )
            result = await futuresearch_agent(params, ctx)

            mock_cs.assert_called_once_with(
                client=mock_client, session_id=sid, name=None
            )
            text = result[0].text
            assert str(mock_session.session_id) in text

    @pytest.mark.asyncio
    async def test_agent_passes_session_name(self):
        """futuresearch_agent forwards session_name to create_session."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch("futuresearch_mcp.tools.create_session") as mock_cs,
        ):
            mock_cs.return_value = _make_async_context_manager(mock_session)
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ",
                data=[{"name": "Acme"}],
                session_name="My Pipeline",
            )
            await futuresearch_agent(params, ctx)

            mock_cs.assert_called_once_with(
                client=mock_client, session_id=None, name="My Pipeline"
            )

    @pytest.mark.asyncio
    async def test_upload_data_passes_session_id(self):
        """futuresearch_upload_data forwards session_id to create_session."""
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        artifact_uuid = uuid4()
        sid = str(uuid4())
        upload_response = CreateArtifactResponse(
            artifact_id=artifact_uuid,
            session_id=mock_session.session_id,
            task_id=uuid4(),
        )

        mock_df = pd.DataFrame([{"a": 1}])

        with (
            patch(
                "futuresearch_mcp.tools.fetch_csv_from_url",
                new_callable=AsyncMock,
                return_value=mock_df,
            ),
            patch("futuresearch_mcp.tools.create_session") as mock_cs,
            patch(
                "futuresearch_mcp.tools.create_table_artifact",
                new_callable=AsyncMock,
                return_value=upload_response,
            ),
        ):
            mock_cs.return_value = _make_async_context_manager(mock_session)

            params = UploadDataInput(
                source="https://example.com/data.csv", session_id=sid
            )
            result = await futuresearch_upload_data(params, ctx)

            mock_cs.assert_called_once_with(
                client=mock_client, session_id=sid, name=None
            )
            data = json.loads(result[0].text)
            assert data["session_id"] == str(mock_session.session_id)

    # ── Response includes session_id ─────────────────────────

    @pytest.mark.asyncio
    async def test_response_includes_session_id(self):
        """Submission response text includes the session ID."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ",
                data=[{"name": "Acme"}],
            )
            result = await futuresearch_agent(params, ctx)

        text = result[0].text
        assert f"Session ID: {mock_session.session_id}" in text


class TestUseList:
    """Tests for futuresearch_use_list."""

    @pytest.mark.asyncio
    async def test_use_list_stdio_saves_csv(self, tmp_path, monkeypatch):
        """In stdio mode, CSV is written to disk and artifact_id is in the response."""
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        artifact_id = uuid4()
        task_id = uuid4()
        mock_result = MagicMock()
        mock_result.artifact_id = artifact_id
        mock_result.task_id = task_id

        mock_df = pd.DataFrame([{"name": "Acme", "industry": "Tech"}])

        monkeypatch.chdir(tmp_path)

        with (
            override_settings(transport="stdio"),
            patch(
                "futuresearch_mcp.tools.use_built_in_list",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch(
                "futuresearch_mcp.tools._fetch_task_result",
                new_callable=AsyncMock,
                return_value=(mock_df.to_dict(orient="records"), len(mock_df), "", ""),
            ),
        ):
            params = UseListInput(artifact_id=str(uuid4()))
            result = await futuresearch_use_list(params, ctx)

        text = result[0].text
        assert f"Artifact ID: {artifact_id}" in text
        assert "CSV saved to:" in text
        assert "Rows: 1" in text
        assert "name, industry" in text
        assert 'artifact_id="' in text

        csv_path = tmp_path / f"built-in-list-{artifact_id}.csv"
        assert csv_path.exists()

    @pytest.mark.asyncio
    async def test_use_list_http_no_csv(self, tmp_path, monkeypatch):
        """In HTTP mode, no CSV is written but artifact_id is in the response."""
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        artifact_id = uuid4()
        task_id = uuid4()
        mock_result = MagicMock()
        mock_result.artifact_id = artifact_id
        mock_result.task_id = task_id

        mock_df = pd.DataFrame([{"name": "Acme", "industry": "Tech"}])

        monkeypatch.chdir(tmp_path)

        with (
            override_settings(transport="streamable-http"),
            patch(
                "futuresearch_mcp.tools.use_built_in_list",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "futuresearch_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch(
                "futuresearch_mcp.tools._fetch_task_result",
                new_callable=AsyncMock,
                return_value=(mock_df.to_dict(orient="records"), len(mock_df), "", ""),
            ),
            patch(
                "futuresearch_mcp.tools._record_task_ownership",
                new_callable=AsyncMock,
                return_value="fake-poll-token",
            ) as mock_record,
        ):
            params = UseListInput(artifact_id=str(uuid4()))
            result = await futuresearch_use_list(params, ctx)

        # Poll token is registered for the task
        mock_record.assert_called_once_with(str(task_id), mock_client.token)

        text = result[0].text
        assert f"Artifact ID: {artifact_id}" in text
        assert "CSV saved to:" not in text
        assert "Rows: 1" in text
        assert 'artifact_id="' in text

        # No CSV files should exist in tmp_path
        assert list(tmp_path.glob("*.csv")) == []

    @pytest.mark.asyncio
    async def test_use_list_error_handling(self):
        """Exception during import returns error text."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "futuresearch_mcp.tools.create_session",
                side_effect=EveryrowError("connection failed"),
            ),
        ):
            params = UseListInput(artifact_id=str(uuid4()))
            result = await futuresearch_use_list(params, ctx)

        text = result[0].text
        assert "Error importing built-in list" in text
        assert "connection failed" in text

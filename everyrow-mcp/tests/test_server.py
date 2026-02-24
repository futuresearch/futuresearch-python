"""Tests for the MCP server tools.

These tests mock the everyrow SDK operations to test the MCP tool logic
without making actual API calls.
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pandas as pd
import pytest
from everyrow.constants import EveryrowError
from everyrow.generated.client import AuthenticatedClient
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_result_response import TaskResultResponse
from everyrow.generated.models.task_result_response_data_type_0_item import (
    TaskResultResponseDataType0Item,
)
from everyrow.generated.models.task_result_response_data_type_1 import (
    TaskResultResponseDataType1,
)
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse
from mcp.types import TextContent
from pydantic import ValidationError

from everyrow_mcp import redis_store
from everyrow_mcp.app import mcp as mcp_app
from everyrow_mcp.models import (
    AgentInput,
    CancelInput,
    DedupeInput,
    HttpResultsInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ScreenInput,
    SingleAgentInput,
    StdioResultsInput,
    _schema_to_model,
)
from everyrow_mcp.tools import (
    _RESULTS_ANNOTATIONS,
    _RESULTS_META,
    everyrow_agent,
    everyrow_cancel,
    everyrow_progress,
    everyrow_results_http,
    everyrow_results_stdio,
    everyrow_single_agent,
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

    def test_screen_input_validates_csv_path(self, tmp_path: Path):
        """Test ScreenInput validates CSV path."""
        with pytest.raises(ValueError, match="does not exist"):
            ScreenInput(
                task="test",
                input_csv=str(tmp_path / "nonexistent.csv"),
            )

    def test_rank_input_validates_field_type(self, tmp_path: Path):
        """Test RankInput validates field_type."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(ValidationError, match="Input should be"):
            RankInput(
                task="test",
                input_csv=str(csv_file),
                field_name="score",
                field_type="invalid",  # pyright: ignore[reportArgumentType]
            )

    def test_merge_input_validates_both_csvs(self, tmp_path: Path):
        """Test MergeInput validates both CSV paths."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(ValueError, match="does not exist"):
            MergeInput(
                task="test",
                left_csv=str(csv_file),
                right_csv=str(tmp_path / "nonexistent.csv"),
            )

    def test_agent_input_rejects_empty_response_schema(self, tmp_path: Path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(
            ValidationError, match="must include a non-empty top-level 'properties'"
        ):
            AgentInput(
                task="test",
                input_csv=str(csv_file),
                response_schema={},
            )

    def test_agent_input_rejects_shorthand_response_schema(self, tmp_path: Path):
        """response_schema must be JSON Schema, not a field map."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(
            ValidationError, match="must include a non-empty top-level 'properties'"
        ):
            AgentInput(
                task="test",
                input_csv=str(csv_file),
                response_schema={"population": "string", "year": "string"},
            )

    def test_tool_inputs_accept_example_schemas(self, tmp_path: Path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        ScreenInput(
            task="test",
            input_csv=str(csv_file),
            response_schema={
                "type": "object",
                "properties": {
                    "passes": {
                        "type": "boolean",
                    },
                },
            },
        )
        AgentInput(
            task="test",
            input_csv=str(csv_file),
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
            input_csv=str(csv_file),
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

    def test_screen_input_requires_boolean_property(self, tmp_path: Path):
        """Screen schemas must include at least one boolean property."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(ValidationError, match="must include at least one boolean"):
            ScreenInput(
                task="test",
                input_csv=str(csv_file),
                response_schema={
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                },
            )

        ScreenInput(
            task="test",
            input_csv=str(csv_file),
            response_schema={
                "type": "object",
                "properties": {"pass": {"type": "boolean"}},
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
    session.get_url.return_value = f"https://everyrow.io/sessions/{session.session_id}"
    return session


def _make_mock_client():
    """Create a mock AuthenticatedClient."""
    client = AsyncMock(spec=AuthenticatedClient)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.token = "fake-token"
    return client


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
    data: list[dict],
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
    """Tests for everyrow_agent."""

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self, companies_csv: str):
        """Test that submit returns immediately with task_id and session_url."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ for each company",
                input_csv=companies_csv,
            )
            result = await everyrow_agent(params, ctx)

            # In stdio mode, _with_ui returns only human-readable text
            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text
            assert "Session:" in text
            assert "everyrow_progress" in text


class TestSingleAgent:
    """Tests for everyrow_single_agent."""

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        """Test that submit returns immediately with task_id and session_url."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Find the current CEO of Apple",
            )
            result = await everyrow_single_agent(params, ctx)
            text = result[0].text

            assert str(mock_task.task_id) in text
            assert "Session:" in text
            assert "everyrow_progress" in text
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
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Research this company's funding",
                input_data={"company": "Stripe", "url": "stripe.com"},
            )
            result = await everyrow_single_agent(params, ctx)
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
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
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
            result = await everyrow_single_agent(params, ctx)
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
    """Tests for everyrow_progress."""

    @pytest.mark.asyncio
    async def test_progress_api_error(self):
        """Test progress with API error returns helpful message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params, ctx)

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
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools.write_initial_task_state"),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params, ctx)

        # In stdio mode, only human-readable text is returned
        assert len(result) == 1
        text = result[0].text
        assert "4/10 complete" in text
        assert "1 failed" in text
        assert "3 running" in text
        assert "everyrow_progress" in text

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
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools.write_initial_task_state"),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params, ctx)

        # In stdio mode, only human-readable text is returned
        assert len(result) == 1
        text = result[0].text
        assert "Completed: 5/5" in text
        assert "everyrow_results" in text


class TestResults:
    """Tests for everyrow_results."""

    @pytest.mark.asyncio
    async def test_results_api_error(self, tmp_path: Path):
        """Test results with API error returns helpful message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())
        output_file = tmp_path / "output.csv"

        with (
            patch(
                "everyrow_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await everyrow_results_stdio(params, ctx)

        assert "Error retrieving results" in result[0].text

    @pytest.mark.asyncio
    async def test_results_saves_csv(self, tmp_path: Path):
        """Test results retrieves data and saves to CSV."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        status_response = _make_task_status_response(status="completed")
        result_response = _make_task_result_response(
            [
                {"name": "TechStart", "answer": "Series A"},
                {"name": "AILabs", "answer": "Seed"},
            ]
        )

        with (
            patch(
                "everyrow_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_result_tasks_task_id_result_get.asyncio",
                new_callable=AsyncMock,
                return_value=result_response,
            ),
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await everyrow_results_stdio(params, ctx)
        text = result[0].text

        assert "Saved 2 rows to" in text
        assert "output.csv" in text

        # Verify CSV was written
        output_df = pd.read_csv(output_file)
        assert len(output_df) == 2
        assert list(output_df.columns) == ["name", "answer"]

    @pytest.mark.asyncio
    async def test_results_scalar_single_agent(self, tmp_path: Path):
        """Test results handles scalar (single_agent) TaskResultResponseDataType1."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        output_file = tmp_path / "output.csv"

        status_response = _make_task_status_response(status="completed")
        scalar_data = TaskResultResponseDataType1.from_dict(
            {"ceo": "Tim Cook", "company": "Apple"}
        )
        result_response = TaskResultResponse(
            task_id=uuid4(),
            status=TaskStatus.COMPLETED,
            data=scalar_data,
        )

        with (
            patch(
                "everyrow_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_result_tasks_task_id_result_get.asyncio",
                new_callable=AsyncMock,
                return_value=result_response,
            ),
        ):
            params = StdioResultsInput(task_id=task_id, output_path=str(output_file))
            result = await everyrow_results_stdio(params, ctx)

        assert len(result) == 1
        assert "1 rows" in result[0].text

    @pytest.mark.asyncio
    async def test_results_http_store(self):
        """In HTTP mode, results are stored in Redis and returned with download URL."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        status_response = _make_task_status_response(status="completed")
        result_response = _make_task_result_response(
            [{"name": "A", "val": "1"}, {"name": "B", "val": "2"}]
        )

        store_response = [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "csv_url": "https://storage.googleapis.com/signed/data.csv",
                        "preview": [
                            {"name": "A", "val": "1"},
                            {"name": "B", "val": "2"},
                        ],
                        "total": 2,
                    }
                ),
            ),
            TextContent(
                type="text",
                text="Results: 2 rows, 2 columns (name, val). All rows shown.",
            ),
        ]

        with (
            patch(
                "everyrow_mcp.tools.try_cached_result",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_result_tasks_task_id_result_get.asyncio",
                new_callable=AsyncMock,
                return_value=result_response,
            ),
            patch(
                "everyrow_mcp.tools.try_store_result",
                new_callable=AsyncMock,
                return_value=store_response,
            ),
        ):
            result = await everyrow_results_http(HttpResultsInput(task_id=task_id), ctx)

        assert len(result) == 2
        widget_data = json.loads(result[0].text)
        assert "csv_url" in widget_data
        assert "2 rows" in result[1].text

    @pytest.mark.asyncio
    async def test_results_http_cache_hit(self):
        """In HTTP mode, cached results are returned directly."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        cached_response = [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "csv_url": "https://storage.googleapis.com/signed/data.csv",
                        "preview": [{"name": "A"}],
                        "total": 1,
                    }
                ),
            ),
            TextContent(type="text", text="Results: 1 rows. All rows shown."),
        ]

        with (
            patch(
                "everyrow_mcp.tools.try_cached_result",
                new_callable=AsyncMock,
                return_value=cached_response,
            ),
        ):
            result = await everyrow_results_http(HttpResultsInput(task_id=task_id), ctx)

        assert result == cached_response

    @pytest.mark.asyncio
    async def test_results_http_store_failure_falls_back_to_inline(self):
        """In HTTP mode, Redis failure falls back to inline results."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        status_response = _make_task_status_response(status="completed")
        result_response = _make_task_result_response([{"name": "A"}])

        with (
            patch(
                "everyrow_mcp.tools.try_cached_result",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch(
                "everyrow_mcp.tool_helpers.get_task_result_tasks_task_id_result_get.asyncio",
                new_callable=AsyncMock,
                return_value=result_response,
            ),
            patch(
                "everyrow_mcp.tools.try_store_result",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await everyrow_results_http(HttpResultsInput(task_id=task_id), ctx)

        assert len(result) == 2
        widget_data = json.loads(result[0].text)
        assert widget_data["preview"] == [{"name": "A"}]
        assert widget_data["total"] == 1
        assert "Redis unavailable" in result[1].text
        assert "1 rows" in result[1].text


class TestCancel:
    """Tests for everyrow_cancel."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        """Test cancelling a running task returns success message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch("everyrow_mcp.tools._clear_task_state") as mock_clear,
            patch(
                "everyrow_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.return_value = None

            params = CancelInput(task_id=task_id)
            result = await everyrow_cancel(params, ctx)

        text = result[0].text
        assert task_id in text
        assert "cancelled" in text.lower()
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_already_terminated_task(self):
        """Test cancelling an already terminated task clears state and returns an error message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch("everyrow_mcp.tools._clear_task_state") as mock_clear,
            patch(
                "everyrow_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = EveryrowError(
                f"Task {task_id} is already COMPLETED"
            )

            params = CancelInput(task_id=task_id)
            result = await everyrow_cancel(params, ctx)

        text = result[0].text
        assert task_id in text
        assert "Error" in text
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self):
        """Test cancelling a nonexistent task clears state and returns an error message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch("everyrow_mcp.tools._clear_task_state") as mock_clear,
            patch(
                "everyrow_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = EveryrowError("Task not found")

            params = CancelInput(task_id=task_id)
            result = await everyrow_cancel(params, ctx)

        text = result[0].text
        assert "Error" in text
        assert "not found" in text.lower()
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_api_error(self):
        """Test cancel with unexpected error returns error message."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)
        task_id = str(uuid4())

        with (
            patch(
                "everyrow_mcp.tools.cancel_task", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_cancel.side_effect = RuntimeError("Network failure")

            params = CancelInput(task_id=task_id)
            result = await everyrow_cancel(params, ctx)

        text = result[0].text
        assert "Error" in text
        assert "Network failure" in text

    def test_cancel_input_validation(self):
        """Test CancelInput strips whitespace and forbids extra fields."""
        # Whitespace stripping
        inp = CancelInput(task_id="  abc-123  ")
        assert inp.task_id == "abc-123"

        # Extra fields forbidden
        with pytest.raises(ValidationError):
            CancelInput(task_id="abc", extra_field="x")  # type: ignore[call-arg]


class TestAgentInlineInput:
    """Tests for everyrow_agent with inline CSV data."""

    @pytest.mark.asyncio
    async def test_submit_with_inline_data(self):
        """Test agent submission with data instead of input_csv."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ for each company",
                data="name,industry\nTechStart,Software\nAILabs,AI\n",
            )
            result = await everyrow_agent(params, ctx)

            # In stdio mode, _with_ui returns only human-readable text
            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text
            assert "2 agents starting" in text

            # Verify the DataFrame passed to the SDK had 2 rows
            call_kwargs = mock_op.call_args[1]
            assert len(call_kwargs["input"]) == 2


class TestAgentUrlInput:
    """Tests for everyrow_agent with input_csv pointing to a URL."""

    @pytest.mark.asyncio
    async def test_submit_with_input_url(self):
        """input_csv with a URL fetches CSV via httpx, passes DataFrame to SDK."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        csv_text = "name,industry\nTechStart,Software\nAILabs,AI\n"
        mock_response = httpx.Response(200, text=csv_text)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch("everyrow_mcp.utils.httpx.AsyncClient", return_value=mock_http),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Find HQ for each company",
                input_csv="https://example.com/companies.csv",
            )
            result = await everyrow_agent(params, ctx)

            assert len(result) == 1
            text = result[0].text
            assert str(mock_task.task_id) in text
            assert "2 agents starting" in text

            # Verify the DataFrame passed to the SDK had 2 rows from the URL
            call_kwargs = mock_op.call_args[1]
            df = call_kwargs["input"]
            assert len(df) == 2
            assert list(df.columns) == ["name", "industry"]

    @pytest.mark.asyncio
    async def test_submit_with_google_sheets_url(self):
        """Google Sheets edit URL is normalized before fetch."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        csv_text = "col\nval\n"
        mock_response = httpx.Response(200, text=csv_text)

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch("everyrow_mcp.utils.httpx.AsyncClient", return_value=mock_http),
        ):
            mock_op.return_value = mock_task

            params = AgentInput(
                task="Process sheet",
                input_csv="https://docs.google.com/spreadsheets/d/ABC123/edit#gid=0",
            )
            await everyrow_agent(params, ctx)

            # Verify the normalized export URL was fetched
            called_url = mock_http.get.call_args[0][0]
            assert "export?format=csv" in called_url
            assert "gid=0" in called_url

    @pytest.mark.asyncio
    async def test_url_fetch_error_propagates(self):
        """HTTP error from URL fetch surfaces as a tool error."""
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        mock_response = httpx.Response(404, text="Not Found")
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("everyrow_mcp.utils.httpx.AsyncClient", return_value=mock_http):
            params = AgentInput(
                task="test",
                input_csv="https://example.com/missing.csv",
            )
            with pytest.raises(ValueError, match="HTTP 404"):
                await everyrow_agent(params, ctx)


class TestAgentInputValidation:
    """Tests for AgentInput model validation with inline data."""

    def test_requires_one_input_source(self):
        """Test that no input source raises."""
        with pytest.raises(ValidationError, match="Provide exactly one of"):
            AgentInput(task="test")

    def test_rejects_both_input_sources(self, companies_csv: str):
        """Test that providing both raises."""
        with pytest.raises(ValidationError, match="Provide exactly one of"):
            AgentInput(
                task="test",
                input_csv=companies_csv,
                data="name,industry\nA,B\n",
            )

    def test_accepts_input_csv(self, companies_csv: str):
        """Test that input_csv alone is valid."""
        params = AgentInput(task="test", input_csv=companies_csv)
        assert params.input_csv == companies_csv
        assert params.data is None

    def test_accepts_data_csv_string(self):
        """Test that data as CSV string is valid."""
        params = AgentInput(task="test", data="a,b\n1,2\n")
        assert params.data is not None
        assert params.input_csv is None

    def test_accepts_data_json_list(self):
        """Test that data as JSON list of dicts is valid."""
        records = [
            {"company": "Acme", "url": "acme.com"},
            {"company": "Beta", "url": "beta.io"},
        ]
        params = AgentInput(task="test", data=records)
        assert params.data == records
        assert params.input_csv is None


class TestResultsInputValidation:
    """Tests for StdioResultsInput and HttpResultsInput."""

    def test_stdio_requires_output_path(self):
        """Test that StdioResultsInput requires output_path."""
        with pytest.raises(ValidationError):
            StdioResultsInput(task_id="some-id")

    def test_stdio_output_path_validated(self, tmp_path: Path):
        """Test that output_path is validated when provided."""
        params = StdioResultsInput(
            task_id="some-id", output_path=str(tmp_path / "out.csv")
        )
        assert params.output_path is not None

    def test_stdio_output_path_rejects_non_csv(self, tmp_path: Path):
        """Test that non-CSV output_path is rejected."""
        with pytest.raises(ValidationError, match=r"must end in \.csv"):
            StdioResultsInput(task_id="some-id", output_path=str(tmp_path / "out.txt"))

    def test_http_output_path_optional(self):
        """Test that HttpResultsInput allows omitting output_path."""
        params = HttpResultsInput(task_id="some-id")
        assert params.output_path is None

    def test_http_output_path_validated(self, tmp_path: Path):
        """Test that HttpResultsInput validates output_path when provided."""
        params = HttpResultsInput(
            task_id="some-id", output_path=str(tmp_path / "out.csv")
        )
        assert params.output_path is not None

    def test_http_output_path_rejects_non_csv(self, tmp_path: Path):
        """Test that non-CSV output_path is rejected in HTTP mode too."""
        with pytest.raises(ValidationError, match=r"must end in \.csv"):
            HttpResultsInput(task_id="some-id", output_path=str(tmp_path / "out.txt"))


class TestHttpResultsToolOverride:
    """Verify that the HTTP override replaces the stdio results tool schema."""

    def test_default_registration_uses_stdio_schema(self):
        """Before override, everyrow_results uses StdioResultsInput."""
        tool = mcp_app._tool_manager.get_tool("everyrow_results")
        assert tool is not None
        assert "StdioResultsInput" in tool.parameters["$defs"]

    def test_http_override_replaces_schema(self):
        """After remove + re-register, everyrow_results uses HttpResultsInput."""
        # Simulate what server.py does for HTTP mode
        mcp_app._tool_manager.remove_tool("everyrow_results")
        mcp_app.tool(
            name="everyrow_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
            meta=_RESULTS_META,
        )(everyrow_results_http)

        tool = mcp_app._tool_manager.get_tool("everyrow_results")
        assert tool is not None
        assert "HttpResultsInput" in tool.parameters["$defs"]
        assert "output_path" not in tool.parameters["$defs"]["HttpResultsInput"].get(
            "required", []
        )

        # Restore stdio default for other tests
        mcp_app._tool_manager.remove_tool("everyrow_results")
        mcp_app.tool(
            name="everyrow_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
            meta=_RESULTS_META,
        )(everyrow_results_stdio)


class TestInputModelsUnchanged:
    """Verify that input models require an input source."""

    def test_rank_requires_input_source(self):
        """RankInput requires either input_csv or data."""
        with pytest.raises(ValidationError):
            RankInput(task="test", field_name="score")

    def test_rank_accepts_data(self):
        """RankInput accepts data as alternative to input_csv."""
        params = RankInput(task="test", field_name="score", data="col\nval")
        assert params.data == "col\nval"
        assert params.input_csv is None

    def test_rank_rejects_both_inputs(self):
        """RankInput rejects both input_csv and data."""
        with pytest.raises(ValidationError):
            RankInput(
                task="test",
                field_name="score",
                input_csv="/tmp/test.csv",
                data="col\nval",
            )

    def test_screen_requires_input_source(self):
        """ScreenInput requires either input_csv or data."""
        with pytest.raises(ValidationError):
            ScreenInput(task="test")

    def test_screen_accepts_data(self):
        """ScreenInput accepts data as alternative to input_csv."""
        params = ScreenInput(task="test", data="col\nval")
        assert params.data == "col\nval"
        assert params.input_csv is None

    def test_screen_rejects_both_inputs(self):
        """ScreenInput rejects both input_csv and data."""
        with pytest.raises(ValidationError):
            ScreenInput(task="test", input_csv="/tmp/test.csv", data="col\nval")

    def test_dedupe_requires_input_source(self):
        """DedupeInput requires either input_csv or data."""
        with pytest.raises(ValidationError):
            DedupeInput(equivalence_relation="same entity")

    def test_merge_requires_input_sources(self):
        """MergeInput requires left and right input sources."""
        with pytest.raises(ValidationError):
            MergeInput(task="test")


class TestStdioVsHttpGating:
    """Verify that widget JSON is only included in HTTP mode responses."""

    @pytest.mark.asyncio
    async def test_submit_stdio_returns_single_content(self, companies_csv: str):
        """In stdio mode, submission tools return only human-readable text."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task
            params = AgentInput(task="test", input_csv=companies_csv)
            result = await everyrow_agent(params, ctx)

        assert len(result) == 1
        assert "Task ID:" in result[0].text

    @pytest.mark.asyncio
    async def test_submit_http_returns_widget_and_text(
        self, companies_csv: str, fake_redis
    ):
        """In HTTP mode, submission tools return widget JSON + human text."""
        mock_task = _make_mock_task()
        mock_session = _make_mock_session()
        mock_client = _make_mock_client()
        ctx = make_test_context(mock_client)

        with (
            override_settings(transport="streamable-http"),
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
            patch.object(redis_store, "get_redis_client", return_value=fake_redis),
        ):
            mock_op.return_value = mock_task
            params = AgentInput(task="test", input_csv=companies_csv)
            result = await everyrow_agent(params, ctx)

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
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools.write_initial_task_state"),
        ):
            result = await everyrow_progress(ProgressInput(task_id=task_id), ctx)

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
            override_settings(transport="streamable-http"),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools.write_initial_task_state"),
        ):
            result = await everyrow_progress(ProgressInput(task_id=task_id), ctx)

        assert len(result) == 1
        assert "2/5 complete" in result[0].text

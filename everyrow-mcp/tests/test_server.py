"""Tests for the MCP server tools.

These tests mock the everyrow SDK operations to test the MCP tool logic
without making actual API calls.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pandas as pd
import pytest
from everyrow.generated.models.public_task_type import PublicTaskType
from everyrow.generated.models.task_progress_info import TaskProgressInfo
from everyrow.generated.models.task_result_response import TaskResultResponse
from everyrow.generated.models.task_result_response_data_type_0_item import (
    TaskResultResponseDataType0Item,
)
from everyrow.generated.models.task_status import TaskStatus
from everyrow.generated.models.task_status_response import TaskStatusResponse
from pydantic import ValidationError

from everyrow_mcp.server import (
    AgentInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ResultsInput,
    ScreenInput,
    SingleAgentInput,
    _schema_to_model,
    everyrow_agent,
    everyrow_progress,
    everyrow_results,
    everyrow_single_agent,
)

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
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
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

        with (
            patch(
                "everyrow_mcp.tools.agent_map_async", new_callable=AsyncMock
            ) as mock_op,
            patch("everyrow_mcp.app._client", mock_client),
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
            result = await everyrow_agent(params)
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

        with (
            patch(
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.create_session",
                return_value=_make_async_context_manager(mock_session),
            ),
        ):
            mock_op.return_value = mock_task

            params = SingleAgentInput(
                task="Find the current CEO of Apple",
            )
            result = await everyrow_single_agent(params)
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

        with (
            patch(
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch("everyrow_mcp.app._client", mock_client),
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
            result = await everyrow_single_agent(params)
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

        with (
            patch(
                "everyrow_mcp.tools.single_agent_async", new_callable=AsyncMock
            ) as mock_op,
            patch("everyrow_mcp.app._client", mock_client),
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
            result = await everyrow_single_agent(params)
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
        task_id = str(uuid4())

        with (
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params)

        assert "Error polling task" in result[0].text
        assert "Retry:" in result[0].text

    @pytest.mark.asyncio
    async def test_progress_running_task(self):
        """Test progress returns status counts for a running task."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        status_response = _make_task_status_response(
            status="running",
            completed=4,
            failed=1,
            running=3,
            pending=2,
            total=10,
        )

        with (
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools._write_task_state"),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params)
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
        status_response = _make_task_status_response(
            status="completed",
            completed=5,
            failed=0,
            running=0,
            pending=0,
            total=5,
        )

        with (
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch("everyrow_mcp.tools.asyncio.sleep", new_callable=AsyncMock),
            patch("everyrow_mcp.tools._write_task_state"),
        ):
            params = ProgressInput(task_id=task_id)
            result = await everyrow_progress(params)
        text = result[0].text

        assert "Completed: 5/5" in text
        assert "everyrow_results" in text


class TestResults:
    """Tests for everyrow_results."""

    @pytest.mark.asyncio
    async def test_results_api_error(self, tmp_path: Path):
        """Test results with API error returns helpful message."""
        mock_client = _make_mock_client()
        task_id = str(uuid4())
        output_file = tmp_path / "output.csv"

        with (
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            params = ResultsInput(task_id=task_id, output_path=str(output_file))
            result = await everyrow_results(params)

        assert "Error checking task status" in result[0].text

    @pytest.mark.asyncio
    async def test_results_saves_csv(self, tmp_path: Path):
        """Test results retrieves data and saves to CSV."""
        task_id = str(uuid4())
        mock_client = _make_mock_client()
        output_file = tmp_path / "output.csv"

        status_response = _make_task_status_response(status="completed")
        result_response = _make_task_result_response(
            [
                {"name": "TechStart", "answer": "Series A"},
                {"name": "AILabs", "answer": "Seed"},
            ]
        )

        with (
            patch("everyrow_mcp.app._client", mock_client),
            patch(
                "everyrow_mcp.tools.get_task_status_tasks_task_id_status_get.asyncio",
                new_callable=AsyncMock,
                return_value=status_response,
            ),
            patch(
                "everyrow_mcp.tools.get_task_result_tasks_task_id_result_get.asyncio",
                new_callable=AsyncMock,
                return_value=result_response,
            ),
        ):
            params = ResultsInput(task_id=task_id, output_path=str(output_file))
            result = await everyrow_results(params)
        text = result[0].text

        assert "Saved 2 rows to" in text
        assert "output.csv" in text

        # Verify CSV was written
        output_df = pd.read_csv(output_file)
        assert len(output_df) == 2
        assert list(output_df.columns) == ["name", "answer"]

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel

from everyrow.generated.models import (
    CreateArtifactResponse,
    LLMEnumPublic,
    OperationResponse,
    PublicEffortLevel,
    PublicTaskType,
    TaskResultResponse,
    TaskResultResponseDataType0Item,
    TaskResultResponseDataType1,
    TaskStatus,
    TaskStatusResponse,
)
from everyrow.generated.types import UNSET
from everyrow.ops import (
    agent_map,
    create_scalar_artifact,
    create_table_artifact,
    rank_async,
    single_agent,
)
from everyrow.result import ScalarResult, TableResult
from everyrow.session import Session
from everyrow.task import LLM, EffortLevel


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.session_id = uuid.uuid4()
    session.client = MagicMock()
    return session


@pytest.fixture(autouse=True)
def mock_env_api_key(monkeypatch):
    monkeypatch.setenv("EVERYROW_API_KEY", "test-key")


def _make_status_response(
    task_id, session_id, artifact_id=None, status=TaskStatus.COMPLETED
):
    return TaskStatusResponse(
        task_id=task_id,
        session_id=session_id,
        status=status,
        task_type=PublicTaskType.AGENT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        artifact_id=artifact_id,
        progress=None,
    )


def _make_table_result(task_id, records, artifact_id=None):
    data_items = [TaskResultResponseDataType0Item.from_dict(r) for r in records]
    return TaskResultResponse(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        data=data_items,
        artifact_id=artifact_id,
    )


def _make_scalar_result(task_id, record, artifact_id=None):
    return TaskResultResponse(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        data=TaskResultResponseDataType1.from_dict(record),
        artifact_id=artifact_id,
    )


@pytest.mark.asyncio
async def test_create_scalar_artifact(mocker, mock_session):
    class MyModel(BaseModel):
        name: str
        age: int

    model = MyModel(name="John", age=30)
    artifact_id = uuid.uuid4()

    mock_create = mocker.patch(
        "everyrow.ops.create_artifact_artifacts_post.asyncio", new_callable=AsyncMock
    )
    mock_create.return_value = CreateArtifactResponse(
        artifact_id=artifact_id,
        session_id=mock_session.session_id,
    )

    result_artifact_id = await create_scalar_artifact(model, mock_session)

    assert result_artifact_id == artifact_id
    assert mock_create.called


@pytest.mark.asyncio
async def test_single_agent(mocker, mock_session):
    class MyInput(BaseModel):
        country: str

    class MyResponse(BaseModel):
        answer: str

    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    # Mock operation endpoint
    mock_submit = mocker.patch(
        "everyrow.ops.single_agent_operations_single_agent_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    # Mock get_task_status
    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    # Mock get_task_result
    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_scalar_result(
        task_id, {"answer": "New Delhi"}, artifact_id
    )

    result = await single_agent(
        task="What is the capital of the given country?",
        session=mock_session,
        input=MyInput(country="India"),
        response_model=MyResponse,
    )

    assert isinstance(result, ScalarResult)
    assert result.data.answer == "New Delhi"
    assert result.artifact_id == artifact_id


@pytest.mark.asyncio
async def test_single_agent_with_table_output(mocker, mock_session):
    class MyInput(BaseModel):
        country: str

    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    # Mock operation endpoint
    mock_submit = mocker.patch(
        "everyrow.ops.single_agent_operations_single_agent_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    # Mock get_task_status
    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    # Mock get_task_result with table data
    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_table_result(
        task_id,
        [{"city": "Mumbai"}, {"city": "Delhi"}, {"city": "Bangalore"}],
        artifact_id,
    )

    result = await single_agent(
        task="What are the three largest cities in the given country?",
        session=mock_session,
        input=MyInput(country="India"),
        return_table=True,
    )

    assert isinstance(result, TableResult)
    assert len(result.data) == 3
    assert "city" in result.data.columns
    assert result.artifact_id == artifact_id


@pytest.mark.asyncio
async def test_agent_map(mocker, mock_session):
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    # Mock operation endpoint
    mock_submit = mocker.patch(
        "everyrow.ops.agent_map_operations_agent_map_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    # Mock get_task_status
    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    # Mock get_task_result
    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_table_result(
        task_id,
        [
            {"country": "India", "answer": "New Delhi"},
            {"country": "USA", "answer": "Washington D.C."},
        ],
        artifact_id,
    )

    input_df = pd.DataFrame([{"country": "India"}, {"country": "USA"}])
    result = await agent_map(
        task="What is the capital of the given country?",
        session=mock_session,
        input=input_df,
    )

    assert isinstance(result, TableResult)
    assert len(result.data) == 2
    assert "answer" in result.data.columns
    assert result.artifact_id == artifact_id


@pytest.mark.asyncio
async def test_agent_map_with_table_output(mocker, mock_session):
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    # Mock operation endpoint
    mock_submit = mocker.patch(
        "everyrow.ops.agent_map_operations_agent_map_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    # Mock get_task_status
    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    # Mock get_task_result
    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_table_result(
        task_id,
        [
            {"country": "India", "city": "Mumbai"},
            {"country": "USA", "city": "New York"},
        ],
        artifact_id,
    )

    input_df = pd.DataFrame([{"country": "India"}, {"country": "USA"}])
    result = await agent_map(
        task="What are the three largest cities in the given country?",
        session=mock_session,
        input=input_df,
    )

    assert isinstance(result, TableResult)
    assert len(result.data) == 2
    assert result.artifact_id == artifact_id


@pytest.mark.asyncio
async def test_rank_model_validation(mock_session) -> None:
    input_df = pd.DataFrame(
        [
            {"country": "China"},
            {"country": "India"},
            {"country": "Indonesia"},
            {"country": "Pakistan"},
            {"country": "USA"},
        ],
    )

    class ResponseModel(BaseModel):
        population_size: int

    with pytest.raises(
        ValueError,
        match="Field population not in response model ResponseModel",
    ):
        await rank_async(
            task="Find the population of the given country",
            session=mock_session,
            input=input_df,
            field_name="population",
            response_model=ResponseModel,
        )


@pytest.mark.asyncio
async def test_create_table_artifact_converts_nan_to_none(mocker, mock_session):
    """NaN values should be converted to None for JSON compatibility."""
    artifact_id = uuid.uuid4()

    mock_create = mocker.patch(
        "everyrow.ops.create_artifact_artifacts_post.asyncio", new_callable=AsyncMock
    )
    mock_create.return_value = CreateArtifactResponse(
        artifact_id=artifact_id,
        session_id=mock_session.session_id,
    )

    df_with_nan = pd.DataFrame([{"name": "Alice", "age": np.nan}])
    await create_table_artifact(df_with_nan, mock_session)

    call_args = mock_create.call_args
    body = call_args.kwargs["body"]
    # data is a list of CreateArtifactRequestDataType0Item
    records = [item.additional_properties for item in body.data]
    assert records == [{"name": "Alice", "age": None}]


@pytest.mark.asyncio
async def test_create_table_artifact_preserves_valid_values(mocker, mock_session):
    """Non-NaN values should be passed through unchanged."""
    artifact_id = uuid.uuid4()

    mock_create = mocker.patch(
        "everyrow.ops.create_artifact_artifacts_post.asyncio", new_callable=AsyncMock
    )
    mock_create.return_value = CreateArtifactResponse(
        artifact_id=artifact_id,
        session_id=mock_session.session_id,
    )

    df = pd.DataFrame([{"name": "Alice", "age": 30}])
    await create_table_artifact(df, mock_session)

    call_args = mock_create.call_args
    body = call_args.kwargs["body"]
    records = [item.additional_properties for item in body.data]
    assert records == [{"name": "Alice", "age": 30}]


# --- Tests for new agent parameters ---


@pytest.mark.asyncio
async def test_single_agent_with_effort_level_preset(mocker, mock_session):
    """Test that effort_level preset sends correct parameters to API."""
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    mock_submit = mocker.patch(
        "everyrow.ops.single_agent_operations_single_agent_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_scalar_result(
        task_id, {"answer": "Paris"}, artifact_id
    )

    await single_agent(
        task="What is the capital of France?",
        session=mock_session,
        effort_level=EffortLevel.MEDIUM,
    )

    # Verify the body sent to the API
    call_args = mock_submit.call_args
    body = call_args.kwargs["body"]

    assert body.effort_level == PublicEffortLevel.MEDIUM
    # Custom params should be UNSET when using preset
    assert body.llm is UNSET
    assert body.iteration_budget is UNSET
    assert body.include_reasoning is UNSET


@pytest.mark.asyncio
async def test_single_agent_with_custom_params(mocker, mock_session):
    """Test that custom params (llm, iteration_budget, include_reasoning) are sent correctly."""
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    mock_submit = mocker.patch(
        "everyrow.ops.single_agent_operations_single_agent_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_scalar_result(
        task_id, {"answer": "Paris"}, artifact_id
    )

    await single_agent(
        task="What is the capital of France?",
        session=mock_session,
        effort_level=None,
        llm=LLM.CLAUDE_4_5_HAIKU,
        iteration_budget=5,
        include_reasoning=True,
    )

    # Verify the body sent to the API
    call_args = mock_submit.call_args
    body = call_args.kwargs["body"]

    # effort_level should be UNSET when using custom params
    assert body.effort_level is UNSET
    # Custom params should have the specified values
    assert body.llm == LLMEnumPublic.CLAUDE_4_5_HAIKU
    assert body.iteration_budget == 5
    assert body.include_reasoning is True


@pytest.mark.asyncio
async def test_agent_map_with_effort_level_preset(mocker, mock_session):
    """Test that agent_map with effort_level preset sends correct parameters."""
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    mock_submit = mocker.patch(
        "everyrow.ops.agent_map_operations_agent_map_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_table_result(
        task_id,
        [{"country": "France", "answer": "Paris"}],
        artifact_id,
    )

    input_df = pd.DataFrame([{"country": "France"}])
    await agent_map(
        task="What is the capital?",
        session=mock_session,
        input=input_df,
        effort_level=EffortLevel.HIGH,
    )

    # Verify the body sent to the API
    call_args = mock_submit.call_args
    body = call_args.kwargs["body"]

    assert body.effort_level == PublicEffortLevel.HIGH
    assert body.llm is UNSET
    assert body.iteration_budget is UNSET
    assert body.include_reasoning is UNSET


@pytest.mark.asyncio
async def test_agent_map_with_custom_params(mocker, mock_session):
    """Test that agent_map with custom params sends correct parameters."""
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    mock_submit = mocker.patch(
        "everyrow.ops.agent_map_operations_agent_map_post.asyncio",
        new_callable=AsyncMock,
    )
    mock_submit.return_value = OperationResponse(
        task_id=task_id,
        session_id=mock_session.session_id,
        status=TaskStatus.PENDING,
    )

    mock_status = mocker.patch(
        "everyrow.task.get_task_status_tasks_task_id_status_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_status.return_value = _make_status_response(
        task_id, mock_session.session_id, artifact_id
    )

    mock_result = mocker.patch(
        "everyrow.task.get_task_result_tasks_task_id_result_get.asyncio",
        new_callable=AsyncMock,
    )
    mock_result.return_value = _make_table_result(
        task_id,
        [{"country": "France", "answer": "Paris"}],
        artifact_id,
    )

    input_df = pd.DataFrame([{"country": "France"}])
    await agent_map(
        task="What is the capital?",
        session=mock_session,
        input=input_df,
        effort_level=None,
        llm=LLM.GPT_5_MINI,
        iteration_budget=10,
        include_reasoning=False,
    )

    # Verify the body sent to the API
    call_args = mock_submit.call_args
    body = call_args.kwargs["body"]

    assert body.effort_level is UNSET
    assert body.llm == LLMEnumPublic.GPT_5_MINI
    assert body.iteration_budget == 10
    assert body.include_reasoning is False

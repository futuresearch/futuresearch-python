import json
from typing import Any, Literal, NamedTuple, TypeVar, overload
from uuid import UUID

from pandas import DataFrame
from pydantic import BaseModel

from futuresearch.api_utils import handle_response
from futuresearch.constants import EveryrowError
from futuresearch.generated.api.artifacts import upload_data_artifacts_upload_post
from futuresearch.generated.api.operations import (
    agent_map_operations_agent_map_post,
    classify_operations_classify_post,
    dedupe_operations_dedupe_post,
    forecast_operations_forecast_post,
    merge_operations_merge_post,
    multi_agent_operations_multi_agent_post,
    rank_operations_rank_post,
    single_agent_operations_single_agent_post,
)
from futuresearch.generated.models import (
    AgentMapOperation,
    AgentMapOperationInputType1Item,
    AgentMapOperationResponseSchemaType0,
    ClassifyOperation,
    ClassifyOperationInputType1Item,
    CreateArtifactResponse,
    DedupeOperation,
    DedupeOperationInputType1Item,
    DedupeOperationStrategy,
    ForecastEffortLevel,
    ForecastOperation,
    ForecastOperationInputType1Item,
    ForecastType,
    LLMEnumPublic,
    MergeOperation,
    MergeOperationLeftInputType1Item,
    MergeOperationRightInputType1Item,
    PublicEffortLevel,
    RankOperation,
    RankOperationInputType1Item,
    RankOperationResponseSchemaType0,
    SingleAgentOperation,
    SingleAgentOperationInputType1Item,
    SingleAgentOperationInputType2,
    SingleAgentOperationResponseSchemaType0,
    UploadDataArtifactsUploadPostJsonBody,
    UploadDataArtifactsUploadPostJsonBodyDataType0Item,
    UploadDataArtifactsUploadPostJsonBodyDataType1,
)
from futuresearch.generated.types import UNSET
from futuresearch.result import MergeResult, Result, ScalarResult, TableResult
from futuresearch.session import Session, create_session
from futuresearch.task import LLM, EffortLevel, EveryrowTask, MergeTask, print_progress

T = TypeVar("T", bound=BaseModel)
InputData = UUID | list[dict[str, Any]] | dict[str, Any]


DEFAULT_EFFORT_LEVEL = EffortLevel.MEDIUM


class SubmittedTask(NamedTuple):
    """Lightweight result from _submit_* helpers — just IDs, no typed model."""

    task_id: UUID
    session_id: UUID


class DefaultAgentResponse(BaseModel):
    answer: str


def _df_to_records(df: DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of records, handling NaN/NaT."""
    json_str = df.to_json(orient="records")
    assert json_str is not None
    return json.loads(json_str)


def _prepare_table_input[T](
    input: DataFrame | UUID | TableResult | None,
    item_class: type[T],
) -> UUID | list[T]:
    """Convert table input to UUID or list of generated model items."""
    if input is None:
        return []
    if isinstance(input, UUID):
        return input
    if isinstance(input, TableResult):
        return input.artifact_id
    if isinstance(input, DataFrame):
        records = _df_to_records(input)
        return [item_class.from_dict(r) for r in records]  # type: ignore[attr-defined]
    raise TypeError(f"Unsupported input type: {type(input)}")


def _prepare_single_input[TItem, TObj](
    input: BaseModel | DataFrame | UUID | Result | None,
    item_class: type[TItem],
    object_class: type[TObj],
) -> UUID | list[TItem] | TObj:
    """Convert single-agent input to the appropriate generated model type."""
    if input is None:
        return object_class.from_dict({})  # type: ignore[attr-defined]
    if isinstance(input, UUID):
        return input
    if isinstance(input, Result):
        return input.artifact_id
    if isinstance(input, DataFrame):
        records = _df_to_records(input)
        return [item_class.from_dict(r) for r in records]  # type: ignore[attr-defined]
    if isinstance(input, BaseModel):
        return object_class.from_dict(input.model_dump())  # type: ignore[attr-defined]
    raise TypeError(f"Unsupported input type: {type(input)}")


# --- Artifact creation ---


async def create_scalar_artifact(input: BaseModel, session: Session) -> UUID:
    """Create a scalar artifact by uploading a single record."""
    body = UploadDataArtifactsUploadPostJsonBody(
        data=UploadDataArtifactsUploadPostJsonBodyDataType1.from_dict(
            input.model_dump()
        ),
        session_id=session.session_id,
    )
    response = await upload_data_artifacts_upload_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)
    return response.artifact_id


async def create_table_artifact(
    input: DataFrame, session: Session
) -> CreateArtifactResponse:
    """Create a table artifact by uploading a list of records.

    Returns the full CreateArtifactResponse (artifact_id, session_id, task_id).
    """
    records = _df_to_records(input)
    body = UploadDataArtifactsUploadPostJsonBody(
        data=[
            UploadDataArtifactsUploadPostJsonBodyDataType0Item.from_dict(r)
            for r in records
        ],
        session_id=session.session_id,
    )
    response = await upload_data_artifacts_upload_post.asyncio(
        client=session.client, body=body
    )
    return handle_response(response)


# --- Single Agent ---


@overload
async def single_agent[T: BaseModel](
    task: str,
    session: Session | None = None,
    input: BaseModel | UUID | Result | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    response_model: type[T] = DefaultAgentResponse,
    return_table: Literal[False] = False,
) -> ScalarResult[T]: ...


@overload
async def single_agent(
    task: str,
    session: Session | None = None,
    input: BaseModel | UUID | Result | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    response_model: type[BaseModel] = DefaultAgentResponse,
    return_table: Literal[True] = True,
) -> TableResult: ...


async def single_agent[T: BaseModel](
    task: str,
    session: Session | None = None,
    input: BaseModel | DataFrame | UUID | Result | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    response_model: type[T] = DefaultAgentResponse,
    return_table: bool = False,
) -> ScalarResult[T] | TableResult:
    """Execute an AI agent task on the provided input.

    Args:
        task: Instructions for the AI agent to execute.
        session: Optional session. If not provided, one will be created automatically.
        input: Input data (BaseModel, DataFrame, UUID, or Result).
        effort_level: Effort level preset (low/medium/high). Mutually exclusive with
            custom params (llm, iteration_budget, include_reasoning). Default: medium.
        llm: LLM to use. Required when effort_level is None.
        iteration_budget: Number of agent iterations (0-20). Required when effort_level is None.
        include_reasoning: Include reasoning notes. Required when effort_level is None.
        response_model: Pydantic model for the response schema.
        return_table: If True, return a TableResult instead of ScalarResult.

    Returns:
        ScalarResult or TableResult depending on return_table parameter.
    """
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await single_agent_async(
                task=task,
                session=internal_session,
                input=input,
                effort_level=effort_level,
                llm=llm,
                iteration_budget=iteration_budget,
                include_reasoning=include_reasoning,
                response_model=response_model,
                return_table=return_table,
            )
            return await cohort_task.await_result()
    cohort_task = await single_agent_async(
        task=task,
        session=session,
        input=input,
        effort_level=effort_level,
        llm=llm,
        iteration_budget=iteration_budget,
        include_reasoning=include_reasoning,
        response_model=response_model,
        return_table=return_table,
    )
    return await cohort_task.await_result()


async def _submit_single_agent(
    task: str,
    session: Session,
    input: BaseModel | DataFrame | UUID | Result | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    response_schema: dict | None = None,
    return_table: bool = False,
) -> SubmittedTask:
    """Build and submit a single_agent request."""
    input_data = _prepare_single_input(
        input, SingleAgentOperationInputType1Item, SingleAgentOperationInputType2
    )

    body = SingleAgentOperation(
        input_=input_data,  # type: ignore
        task=task,
        session_id=session.session_id,
        response_schema=SingleAgentOperationResponseSchemaType0.from_dict(
            response_schema or DefaultAgentResponse.model_json_schema()
        ),
        effort_level=PublicEffortLevel(effort_level.value)
        if effort_level is not None
        else UNSET,
        llm=LLMEnumPublic(llm.value) if llm is not None else UNSET,
        iteration_budget=iteration_budget if iteration_budget is not None else UNSET,
        include_reasoning=include_reasoning if include_reasoning is not None else UNSET,
        return_list=return_table,
    )

    response = await single_agent_operations_single_agent_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)
    return SubmittedTask(response.task_id, response.session_id)


async def single_agent_async[T: BaseModel](
    task: str,
    session: Session,
    input: BaseModel | DataFrame | UUID | Result | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    response_model: type[T] = DefaultAgentResponse,
    return_table: bool = False,
) -> EveryrowTask[T]:
    """Submit a single_agent task asynchronously."""
    submitted = await _submit_single_agent(
        task=task,
        session=session,
        input=input,
        effort_level=effort_level,
        llm=llm,
        iteration_budget=iteration_budget,
        include_reasoning=include_reasoning,
        response_schema=response_model.model_json_schema(),
        return_table=return_table,
    )

    cohort_task: EveryrowTask[T] = EveryrowTask(
        response_model=response_model, is_map=False, is_expand=return_table
    )
    cohort_task.set_submitted(submitted.task_id, submitted.session_id, session.client)
    return cohort_task


# --- Agent Map ---


async def agent_map(
    task: str,
    session: Session | None = None,
    input: DataFrame | UUID | TableResult | None = None,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    enforce_row_independence: bool = False,
    response_model: type[BaseModel] = DefaultAgentResponse,
    document_query_llm: LLM | None = None,
    return_table: bool = False,
) -> TableResult:
    """Execute an AI agent task on each row of the input table.

    Args:
        task: Instructions for the AI agent to execute per row.
        session: Optional session. If not provided, one will be created automatically.
        input: The input table (DataFrame, UUID, or TableResult).
        effort_level: Effort level preset (low/medium/high). Mutually exclusive with
            custom params (llm, iteration_budget, include_reasoning). Default: low.
        llm: LLM to use for each agent. Required when effort_level is None.
        iteration_budget: Number of agent iterations per row (0-20). Required when effort_level is None.
        include_reasoning: Include reasoning notes. Required when effort_level is None.
        response_model: Pydantic model for the response schema. When ``return_table`` is True,
            this should describe a single item; the worker wraps it in a list automatically.
        document_query_llm: LLM to use for the document query tool (QDLLM) when scraping web pages.
        return_table: If True, each per-row agent emits a list of records and the result table
            contains one row per item (with an ``_expand_index`` column). Output rows can exceed
            input rows. Default: False (one output row per input row).

    Returns:
        TableResult containing the agent results merged with input rows.
    """
    if input is None:
        raise EveryrowError("input is required for agent_map")
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await agent_map_async(
                task=task,
                session=internal_session,
                input=input,
                effort_level=effort_level,
                llm=llm,
                iteration_budget=iteration_budget,
                include_reasoning=include_reasoning,
                enforce_row_independence=enforce_row_independence,
                response_model=response_model,
                document_query_llm=document_query_llm,
                return_table=return_table,
            )
            result = await cohort_task.await_result()
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Agent map task did not return a table result")
    cohort_task = await agent_map_async(
        task=task,
        session=session,
        input=input,
        effort_level=effort_level,
        llm=llm,
        iteration_budget=iteration_budget,
        include_reasoning=include_reasoning,
        enforce_row_independence=enforce_row_independence,
        response_model=response_model,
        document_query_llm=document_query_llm,
        return_table=return_table,
    )
    result = await cohort_task.await_result()
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Agent map task did not return a table result")


async def _submit_agent_map(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    enforce_row_independence: bool = False,
    response_schema: dict | None = None,
    document_query_llm: LLM | None = None,
    return_table: bool = False,
) -> SubmittedTask:
    """Build and submit an agent_map request."""
    input_data = _prepare_table_input(input, AgentMapOperationInputType1Item)

    body = AgentMapOperation(
        input_=input_data,  # type: ignore
        task=task,
        session_id=session.session_id,
        response_schema=AgentMapOperationResponseSchemaType0.from_dict(
            response_schema or DefaultAgentResponse.model_json_schema()
        ),
        effort_level=PublicEffortLevel(effort_level.value)
        if effort_level is not None
        else UNSET,
        llm=LLMEnumPublic(llm.value) if llm is not None else UNSET,
        iteration_budget=iteration_budget if iteration_budget is not None else UNSET,
        include_reasoning=include_reasoning if include_reasoning is not None else UNSET,
        join_with_input=True,
        enforce_row_independence=enforce_row_independence,
        document_query_llm=LLMEnumPublic(document_query_llm.value)
        if document_query_llm is not None
        else UNSET,
        return_list=return_table,
    )

    response = await agent_map_operations_agent_map_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)
    return SubmittedTask(response.task_id, response.session_id)


async def agent_map_async(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    effort_level: EffortLevel | None = DEFAULT_EFFORT_LEVEL,
    llm: LLM | None = None,
    iteration_budget: int | None = None,
    include_reasoning: bool | None = None,
    enforce_row_independence: bool = False,
    response_model: type[BaseModel] = DefaultAgentResponse,
    document_query_llm: LLM | None = None,
    return_table: bool = False,
) -> EveryrowTask[BaseModel]:
    """Submit an agent_map task asynchronously."""
    submitted = await _submit_agent_map(
        task=task,
        session=session,
        input=input,
        effort_level=effort_level,
        llm=llm,
        iteration_budget=iteration_budget,
        include_reasoning=include_reasoning,
        enforce_row_independence=enforce_row_independence,
        response_schema=response_model.model_json_schema(),
        document_query_llm=document_query_llm,
        return_table=return_table,
    )

    cohort_task = EveryrowTask(
        response_model=response_model, is_map=True, is_expand=return_table
    )
    cohort_task.set_submitted(submitted.task_id, submitted.session_id, session.client)
    return cohort_task


# --- Rank ---


async def rank[T: BaseModel](
    task: str,
    session: Session | None = None,
    input: DataFrame | UUID | TableResult | None = None,
    field_name: str | None = None,
    field_type: Literal["float", "int", "str", "bool"] = "float",
    response_model: type[T] | None = None,
    ascending_order: bool = True,
) -> TableResult:
    """Rank rows in a table using AI.

    Args:
        task: The task description for ranking
        session: Optional session. If not provided, one will be created automatically.
        input: The input table (DataFrame, UUID, or TableResult)
        field_name: The name of the field to sort by
        field_type: The type of the field (default: "float", ignored if response_model is provided)
        response_model: Optional Pydantic model for the response schema
        ascending_order: If True, sort in ascending order

    Returns:
        TableResult containing the ranked table
    """
    if input is None or field_name is None:
        raise EveryrowError("input and field_name are required for rank")
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await rank_async(
                task=task,
                session=internal_session,
                input=input,
                field_name=field_name,
                field_type=field_type,
                response_model=response_model,
                ascending_order=ascending_order,
            )
            result = await cohort_task.await_result()
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Rank task did not return a table result")
    cohort_task = await rank_async(
        task=task,
        session=session,
        input=input,
        field_name=field_name,
        field_type=field_type,
        response_model=response_model,
        ascending_order=ascending_order,
    )
    result = await cohort_task.await_result()
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Rank task did not return a table result")


_JSON_TYPE_MAP_RANK = {
    "float": "number",
    "int": "integer",
    "str": "string",
    "bool": "boolean",
}


async def _submit_rank(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    field_name: str,
    response_schema: dict | None = None,
    field_type: Literal["float", "int", "str", "bool"] = "float",
    ascending_order: bool = True,
) -> SubmittedTask:
    """Build and submit a rank request.

    If `response_schema` is None, build a minimal schema from `field_name` and
    `field_type`.
    """
    if response_schema is None:
        response_schema = {
            "type": "object",
            "properties": {
                field_name: {"type": _JSON_TYPE_MAP_RANK.get(field_type, field_type)}
            },
            "required": [field_name],
        }

    # Validate that the sort field exists in the schema
    properties = response_schema.get("properties", {})
    if field_name not in properties:
        raise ValueError(
            f"field_name '{field_name}' not found in response_schema properties: {list(properties)}"
        )

    input_data = _prepare_table_input(input, RankOperationInputType1Item)

    body = RankOperation(
        input_=input_data,  # type: ignore
        task=task,
        sort_by=field_name,
        session_id=session.session_id,
        response_schema=RankOperationResponseSchemaType0.from_dict(response_schema),
        ascending=ascending_order,
    )

    response = await rank_operations_rank_post.asyncio(client=session.client, body=body)
    response = handle_response(response)
    return SubmittedTask(response.task_id, response.session_id)


async def rank_async[T: BaseModel](
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    field_name: str,
    field_type: Literal["float", "int", "str", "bool"] = "float",
    response_model: type[T] | None = None,
    ascending_order: bool = True,
) -> EveryrowTask[T]:
    """Submit a rank task asynchronously."""
    response_schema: dict | None = None
    if response_model is not None:
        response_schema = response_model.model_json_schema()

    submitted = await _submit_rank(
        task=task,
        session=session,
        input=input,
        field_name=field_name,
        response_schema=response_schema,
        field_type=field_type,
        ascending_order=ascending_order,
    )

    cohort_task: EveryrowTask[T] = EveryrowTask(
        response_model=response_model or BaseModel,  # type: ignore[arg-type]
        is_map=True,
        is_expand=False,
    )
    cohort_task.set_submitted(submitted.task_id, submitted.session_id, session.client)
    return cohort_task


# --- Merge ---


async def merge(
    task: str,
    session: Session | None = None,
    left_table: DataFrame | UUID | TableResult | None = None,
    right_table: DataFrame | UUID | TableResult | None = None,
    merge_on_left: str | None = None,
    merge_on_right: str | None = None,
    use_web_search: Literal["auto", "yes", "no"] | None = None,
    relationship_type: Literal[
        "many_to_one", "one_to_one", "one_to_many", "many_to_many"
    ]
    | None = None,
    llm: LLM | None = None,
    document_query_llm: LLM | None = None,
) -> MergeResult:
    """Merge two tables using AI (LEFT JOIN semantics).

    Args:
        task: The task description for the merge operation
        session: Optional session. If not provided, one will be created automatically.
        left_table: The table being enriched — all its rows are kept in the output (DataFrame, UUID, or TableResult)
        right_table: The lookup/reference table — its columns are appended to matches; unmatched left rows get nulls (DataFrame, UUID, or TableResult)
        merge_on_left: Only set if you expect exact string matches on this column or want to draw agent attention to it. Auto-detected if omitted.
        merge_on_right: Only set if you expect exact string matches on this column or want to draw agent attention to it. Auto-detected if omitted.
        use_web_search: Control web search behavior: "auto" (default) tries LLM merge first then conditionally searches, "no" skips web search entirely, "yes" forces web search on every row.
        relationship_type: Control merge relationship type / cardinality between the two tables: "many_to_one" (default) allows multiple left rows to match one right row (e.g. matching reviews to product), "one_to_one" enforces unique matching between left and right rows (e.g. CEO to company), "one_to_many" allows one left row to match multiple right rows (e.g. company to products), "many_to_many" allows multiple left rows to match multiple right rows (e.g. companies to investors). For one_to_many and many_to_many, multiple matches are represented by joining the right-table values with " | " in each added column.
        llm: LLM to use for the merge operation (both initial LLM matching and web search agent). If not provided, uses system defaults.
        document_query_llm: LLM to use for the document query tool that reads web pages. If not provided, uses system default.

    Returns:
        MergeResult containing the merged table and match breakdown by method (exact, fuzzy, llm, web)

    Example:
        result = await merge(task="...", left_table=df_left, right_table=df_right)
        print(f"Exact matches: {len(result.breakdown.exact)}")
        print(f"LLM matches: {len(result.breakdown.llm)}")
        print(f"Unmatched left rows: {result.breakdown.unmatched_left}")
    """
    if left_table is None or right_table is None:
        raise EveryrowError("left_table and right_table are required for merge")
    if session is None:
        async with create_session() as internal_session:
            merge_task = await merge_async(
                task=task,
                session=internal_session,
                left_table=left_table,
                right_table=right_table,
                merge_on_left=merge_on_left,
                merge_on_right=merge_on_right,
                use_web_search=use_web_search,
                relationship_type=relationship_type,
                llm=llm,
                document_query_llm=document_query_llm,
            )
            return await merge_task.await_result()
    merge_task = await merge_async(
        task=task,
        session=session,
        left_table=left_table,
        right_table=right_table,
        merge_on_left=merge_on_left,
        merge_on_right=merge_on_right,
        use_web_search=use_web_search,
        relationship_type=relationship_type,
        llm=llm,
        document_query_llm=document_query_llm,
    )
    return await merge_task.await_result()


async def merge_async(
    task: str,
    session: Session,
    left_table: DataFrame | UUID | TableResult,
    right_table: DataFrame | UUID | TableResult,
    merge_on_left: str | None = None,
    merge_on_right: str | None = None,
    use_web_search: Literal["auto", "yes", "no"] | None = None,
    relationship_type: Literal[
        "many_to_one", "one_to_one", "one_to_many", "many_to_many"
    ]
    | None = None,
    llm: LLM | None = None,
    document_query_llm: LLM | None = None,
) -> MergeTask:
    """Submit a merge task asynchronously.

    Returns:
        MergeTask that can be awaited for a MergeResult with match breakdown
    """
    left_data = _prepare_table_input(left_table, MergeOperationLeftInputType1Item)
    right_data = _prepare_table_input(right_table, MergeOperationRightInputType1Item)

    body = MergeOperation(
        left_input=left_data,  # type: ignore
        right_input=right_data,  # type: ignore
        task=task,
        left_key=merge_on_left or UNSET,
        right_key=merge_on_right or UNSET,
        use_web_search=use_web_search or UNSET,  # type: ignore
        relationship_type=relationship_type or UNSET,  # type: ignore
        llm=LLMEnumPublic(llm.value) if llm is not None else UNSET,
        document_query_llm=LLMEnumPublic(document_query_llm.value)
        if document_query_llm is not None
        else UNSET,
        session_id=session.session_id,
    )

    response = await merge_operations_merge_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)

    merge_task = MergeTask()
    merge_task.set_submitted(response.task_id, response.session_id, session.client)
    return merge_task


# --- Dedupe ---


async def dedupe(
    equivalence_relation: str,
    session: Session | None = None,
    input: DataFrame | UUID | TableResult | None = None,
    strategy: Literal["identify", "select", "combine"] | None = None,
    strategy_prompt: str | None = None,
    llm: LLM | None = None,
) -> TableResult:
    """Dedupe a table by removing duplicates using AI.

    Args:
        equivalence_relation: Natural-language description of what makes two rows
            equivalent/duplicates. Be as specific as needed — the LLM uses this to
            reason about equivalence, handling abbreviations, typos, name variations,
            and entity relationships that string matching cannot capture.
        session: Optional session. If not provided, one will be created automatically.
        input: The input table (DataFrame, UUID, or TableResult).
        strategy: Controls what happens after duplicate clusters are identified.
            - "identify": Cluster only. Adds `equivalence_class_id` and
              `equivalence_class_name` columns but does NOT select or remove any rows.
              Use this when you want to review clusters before deciding what to do.
            - "select" (default): Picks the best representative row from each cluster.
              Adds `equivalence_class_id`, `equivalence_class_name`, and `selected`
              columns. Rows with `selected=True` are the canonical records. To get the
              deduplicated table: `result.data[result.data["selected"] == True]`.
            - "combine": Synthesizes a single combined row per cluster by merging the
              best information from all duplicates. Original rows are kept with
              `selected=False`, and new combined rows are appended with `selected=True`.
              Useful when no single row has all the information (e.g., one row has the
              email, another has the phone number).
        strategy_prompt: Optional natural-language instructions that guide how the LLM
            selects or combines rows. Only used with "select" and "combine" strategies.
            Examples: "Prefer the record with the most complete contact information",
            "For each field, keep the most recent and complete value",
            "Prefer records from the CRM system over spreadsheet imports".
        llm: LLM to use for dedupe comparisons. If not provided, uses the system default.

    Returns:
        TableResult containing the deduped table with cluster metadata columns.
    """
    if input is None:
        raise EveryrowError("input is required for dedupe")
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await dedupe_async(
                session=internal_session,
                input=input,
                equivalence_relation=equivalence_relation,
                strategy=strategy,
                strategy_prompt=strategy_prompt,
                llm=llm,
            )
            result = await cohort_task.await_result()
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Dedupe task did not return a table result")
    cohort_task = await dedupe_async(
        session=session,
        input=input,
        equivalence_relation=equivalence_relation,
        strategy=strategy,
        strategy_prompt=strategy_prompt,
        llm=llm,
    )
    result = await cohort_task.await_result()
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Dedupe task did not return a table result")


async def dedupe_async(
    session: Session,
    input: DataFrame | UUID | TableResult,
    equivalence_relation: str,
    strategy: Literal["identify", "select", "combine"] | None = None,
    strategy_prompt: str | None = None,
    llm: LLM | None = None,
) -> EveryrowTask[BaseModel]:
    """Submit a dedupe task asynchronously."""
    input_data = _prepare_table_input(input, DedupeOperationInputType1Item)

    body = DedupeOperation(
        input_=input_data,  # type: ignore
        equivalence_relation=equivalence_relation,
        session_id=session.session_id,
        strategy=DedupeOperationStrategy(strategy) if strategy is not None else UNSET,
        strategy_prompt=strategy_prompt if strategy_prompt is not None else UNSET,
        llm=LLMEnumPublic(llm.value) if llm is not None else UNSET,
    )

    response = await dedupe_operations_dedupe_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)

    cohort_task = EveryrowTask(response_model=BaseModel, is_map=True, is_expand=False)
    cohort_task.set_submitted(response.task_id, response.session_id, session.client)
    return cohort_task


# --- Forecast ---


async def forecast(
    input: DataFrame | UUID | TableResult,
    context: str | None = None,
    session: Session | None = None,
    *,
    forecast_type: Literal["binary", "numeric", "date"],
    effort_level: ForecastEffortLevel | None = None,
    output_field: str | None = None,
    units: str | None = None,
) -> TableResult:
    """Forecast questions using deep research and multi-model ensemble.

    Supports three modes:

    - **binary** (default): Forecasts the probability (0-100) of YES/NO questions.
      Output columns: ``probability`` (int) and ``rationale`` (str).

    - **numeric**: Forecasts percentile estimates for continuous numeric questions.
      Requires ``output_field`` (e.g. ``"price"``) and ``units`` (e.g. ``"USD"``).
      Output columns: ``{output_field}_p10`` through ``{output_field}_p90`` (float),
      ``units`` (str), and ``rationale`` (str).

    - **date**: Forecasts percentile date estimates for timing questions.
      Requires ``output_field`` (e.g. ``"launch_date"``).
      Output columns: ``{output_field}_p10`` through ``{output_field}_p90``
      (YYYY-MM-DD strings) and ``rationale`` (str).

    Each row is forecast using 6 parallel research agents followed by a 3-model
    forecaster ensemble, validated against FutureSearch's past-casting environment.

    The input table should contain at minimum a ``question`` column.  Recommended
    additional columns: ``resolution_criteria``, ``resolution_date``, ``background``.

    Args:
        input: The input table.  Each row should contain the question/scenario to
            forecast.
        context: Optional batch-level context or instructions that apply to every
            row (e.g. "Focus on EU regulatory sources" or "Assume resolution by
            end of 2027").  Leave *None* when the rows are self-contained.
        session: Optional session. If not provided, one will be created automatically.
        forecast_type: ``"binary"`` for probability forecasts, ``"numeric"`` for
            percentile estimates, ``"date"`` for date percentile estimates.
        effort_level: affects accuracy and cost of forecast. Default: low.
        output_field: Name of the quantity being forecast (required for numeric
            and date, e.g. ``"price"``, ``"launch_date"``).
        units: Units for numeric forecasts (e.g. ``"USD per barrel"``).
            Required when *forecast_type* is ``"numeric"``.

    Returns:
        TableResult with forecast columns added to each input row.
    """
    task = context or ""
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await forecast_async(
                task=task,
                session=internal_session,
                input=input,
                forecast_type=forecast_type,
                effort_level=effort_level,
                output_field=output_field,
                units=units,
            )
            result = await cohort_task.await_result(on_progress=print_progress)
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Forecast task did not return a table result")
    cohort_task = await forecast_async(
        task=task,
        session=session,
        input=input,
        forecast_type=forecast_type,
        output_field=output_field,
        units=units,
    )
    result = await cohort_task.await_result(on_progress=print_progress)
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Forecast task did not return a table result")


async def forecast_async(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    *,
    forecast_type: Literal["binary", "numeric", "date"],
    effort_level: ForecastEffortLevel | None = None,
    output_field: str | None = None,
    units: str | None = None,
) -> EveryrowTask[BaseModel]:
    """Submit a forecast task asynchronously.

    Args:
        task: Context or instructions for the forecast.
        session: Active session.
        input: Input data.
        forecast_type: ``"binary"`` for yes/no probability, ``"numeric"`` for
            percentile estimates, ``"date"`` for date percentile estimates.
        effort_level: affects accuracy and cost of forecast. Default: low.
        output_field: Name of the quantity (required for numeric and date).
        units: Units for numeric forecasts (required for numeric).

    Returns:
        EveryrowTask that resolves to a TableResult with forecast columns.
    """
    input_data = _prepare_table_input(input, ForecastOperationInputType1Item)

    body = ForecastOperation(
        input_=input_data,
        task=task,
        session_id=session.session_id,
        forecast_type=ForecastType(forecast_type),
        effort_level=effort_level if effort_level is not None else UNSET,
        output_field=output_field,
        units=units,
    )

    response = await forecast_operations_forecast_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)

    cohort_task: EveryrowTask[BaseModel] = EveryrowTask(
        response_model=BaseModel, is_map=True, is_expand=False
    )
    cohort_task.set_submitted(response.task_id, response.session_id, session.client)
    return cohort_task


# --- Classify ---


async def classify(
    task: str,
    categories: list[str],
    input: DataFrame | UUID | TableResult,
    classification_field: str = "classification",
    include_reasoning: bool = False,
    session: Session | None = None,
) -> TableResult:
    """Classify each row of a table into one of the provided categories.

    Uses a two-phase approach: Phase 1 attempts fast batch classification using
    web research, and Phase 2 follows up with deeper research on ambiguous rows.
    Each row is assigned exactly one of the provided categories.

    Args:
        task: Natural-language instructions describing how to classify each row.
        categories: Allowed category values (minimum 2). Each row will be
            assigned exactly one of these.
        input: The input table. Each row is classified independently.
        classification_field: Name of the output column that will contain the
            assigned category. Default: ``"classification"``.
        include_reasoning: If True, adds a ``reasoning`` column with the
            agent's justification for the classification.
        session: Optional session. If not provided, one will be created
            automatically.

    Returns:
        TableResult with a ``classification_field`` column (and optionally
        ``reasoning``) added to each input row.
    """
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await classify_async(
                task=task,
                categories=categories,
                session=internal_session,
                input=input,
                classification_field=classification_field,
                include_reasoning=include_reasoning,
            )
            result = await cohort_task.await_result(on_progress=print_progress)
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Classify task did not return a table result")
    cohort_task = await classify_async(
        task=task,
        categories=categories,
        session=session,
        input=input,
        classification_field=classification_field,
        include_reasoning=include_reasoning,
    )
    result = await cohort_task.await_result(on_progress=print_progress)
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Classify task did not return a table result")


async def classify_async(
    task: str,
    categories: list[str],
    session: Session,
    input: DataFrame | UUID | TableResult,
    classification_field: str = "classification",
    include_reasoning: bool = False,
) -> EveryrowTask[BaseModel]:
    """Submit a classify task asynchronously.

    Returns:
        EveryrowTask that resolves to a TableResult with a classification column.
    """
    input_data = _prepare_table_input(input, ClassifyOperationInputType1Item)

    body = ClassifyOperation(
        input_=input_data,  # type: ignore
        task=task,
        categories=categories,
        session_id=session.session_id,
        classification_field=classification_field,
        include_reasoning=include_reasoning,
    )

    response = await classify_operations_classify_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)

    cohort_task: EveryrowTask[BaseModel] = EveryrowTask(
        response_model=BaseModel, is_map=True, is_expand=False
    )
    cohort_task.set_submitted(response.task_id, response.session_id, session.client)
    return cohort_task


# --- Multi-Agent ---


async def multi_agent(
    task: str,
    input: DataFrame | UUID | TableResult,
    session: Session | None = None,
    *,
    directions: list[str] | None = None,
    effort_level: Literal["low", "medium", "high"] | None = "medium",
    response_schema: dict[str, Any] | None = None,
    join_with_input: bool = True,
) -> TableResult:
    """Run multiple AI agents in parallel on different research angles, then synthesize.

    Each row in the input is processed by multiple direction agents exploring
    different research angles. Their findings are synthesized into a single
    result per row.

    Args:
        task: Instructions for the multi-agent research.
        input: Input data (DataFrame, UUID, or TableResult).
        session: Optional session. If not provided, one will be created.
        directions: Up to 6 explicit research directions. If not provided,
            auto-generated based on effort_level.
        effort_level: Controls direction count: ``"low"`` (3), ``"medium"`` (4),
            ``"high"`` (6). Default: ``"medium"``.
        response_schema: JSON Schema for the synthesized output. If not provided,
            defaults to ``{answer: string}``.
        join_with_input: If True, merge output with input row. Default: True.

    Returns:
        TableResult with synthesized output columns added to each input row.
    """
    if session is None:
        async with create_session() as internal_session:
            cohort_task = await multi_agent_async(
                task=task,
                session=internal_session,
                input=input,
                directions=directions,
                effort_level=effort_level,
                response_schema=response_schema,
                join_with_input=join_with_input,
            )
            result = await cohort_task.await_result(on_progress=print_progress)
            if isinstance(result, TableResult):
                return result
            raise EveryrowError("Multi-agent task did not return a table result")
    cohort_task = await multi_agent_async(
        task=task,
        session=session,
        input=input,
        directions=directions,
        effort_level=effort_level,
        response_schema=response_schema,
        join_with_input=join_with_input,
    )
    result = await cohort_task.await_result(on_progress=print_progress)
    if isinstance(result, TableResult):
        return result
    raise EveryrowError("Multi-agent task did not return a table result")


async def _submit_multi_agent(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    *,
    directions: list[str] | None = None,
    effort_level: str | None = "medium",
    response_schema: dict[str, Any] | None = None,
    join_with_input: bool = True,
) -> SubmittedTask:
    """Submit a multi-agent task and return task/session IDs (for MCP use)."""
    input_data = _prepare_table_input(input, AgentMapOperationInputType1Item)

    body: dict[str, Any] = {
        "input": [item.to_dict() for item in input_data]
        if isinstance(input_data, list)
        else str(input_data),
        "task": task,
        "session_id": str(session.session_id),
        "effort_level": effort_level,
        "join_with_input": join_with_input,
    }
    if directions is not None:
        body["directions"] = directions
    if response_schema is not None:
        body["response_schema"] = response_schema

    response = await multi_agent_operations_multi_agent_post.asyncio(
        client=session.client, body=body
    )
    response = handle_response(response)

    return SubmittedTask(response.task_id, response.session_id)


async def multi_agent_async(
    task: str,
    session: Session,
    input: DataFrame | UUID | TableResult,
    *,
    directions: list[str] | None = None,
    effort_level: str | None = "medium",
    response_schema: dict[str, Any] | None = None,
    join_with_input: bool = True,
) -> EveryrowTask[BaseModel]:
    """Submit a multi-agent task asynchronously.

    Args:
        task: Instructions for the multi-agent research.
        session: Active session.
        input: Input data.
        directions: Up to 6 explicit research directions.
        effort_level: ``"low"`` (3 agents), ``"medium"`` (4), ``"high"`` (6).
        response_schema: JSON Schema for the synthesized output.
        join_with_input: If True, merge output with input row.

    Returns:
        EveryrowTask that resolves to a TableResult.
    """
    submitted = await _submit_multi_agent(
        task=task,
        session=session,
        input=input,
        directions=directions,
        effort_level=effort_level,
        response_schema=response_schema,
        join_with_input=join_with_input,
    )

    cohort_task: EveryrowTask[BaseModel] = EveryrowTask(
        response_model=BaseModel, is_map=True, is_expand=False
    )
    cohort_task.set_submitted(submitted.task_id, submitted.session_id, session.client)
    return cohort_task

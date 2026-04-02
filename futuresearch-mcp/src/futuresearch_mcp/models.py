"""Input models and schema helpers for futuresearch MCP tools."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pandas as pd
from futuresearch.generated.models.dedupe_operation_strategy import (
    DedupeOperationStrategy,
)
from futuresearch.generated.models.llm_enum_public import LLMEnumPublic
from futuresearch.task import EffortLevel
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from futuresearch_mcp.config import settings
from futuresearch_mcp.utils import is_url, validate_csv_path, validate_url


class InputDataMode(StrEnum):
    dataframe = "DATAFRAME"
    artifact_id = "ARTIFACT_ID"


def _validate_response_schema(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate response_schema is a JSON Schema object schema."""
    if schema is None:
        return None

    validator_cls = validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(
            f"Invalid JSON Schema in response_schema: {exc.message}"
        ) from exc

    schema_type = schema.get("type")
    if schema_type not in (None, "object"):
        raise ValueError(
            "response_schema must describe an object response (top-level 'type' must be 'object')"
        )

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ValueError(
            "response_schema must include a non-empty top-level 'properties' object"
        )

    if len(properties) > settings.max_schema_properties:
        raise ValueError(
            f"response_schema has {len(properties)} properties "
            f"(max {settings.max_schema_properties})"
        )

    for field_name, field_def in properties.items():
        if not isinstance(field_def, dict):
            raise ValueError(
                f"Invalid property schema for '{field_name}': expected an object."
            )

    return schema


def _check_exactly_one(
    *,
    values: tuple[Any | None, ...],
    field_names: tuple[str, ...],
    label: str | None = None,
):
    count = sum(1 for v in values if v is not None)
    if count != 1:
        fields = ", ".join(field_names)
        prefix = f"{label}: " if label else ""
        raise ValueError(f"{prefix}Provide exactly one of {fields}.")


def _validate_session_id(v: str | None) -> str | None:
    """Validate session_id is a valid UUID string."""
    if v is not None:
        try:
            UUID(v)
        except ValueError as exc:
            raise ValueError(f"session_id must be a valid UUID: {v}") from exc
    return v


class _SingleSourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    artifact_id: str | None = Field(
        default=None,
        description="Artifact ID (UUID) from upload_data or request_upload_url.",
    )
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data as a list of row objects.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID (UUID) to add to an existing session. If session_name is also provided, the session is renamed.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. If session_id is also provided, renames the existing session.",
    )

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                UUID(v)
            except ValueError as exc:
                raise ValueError(f"artifact_id must be a valid UUID: {v}") from exc
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        return _validate_session_id(v)

    @field_validator("data")
    @classmethod
    def validate_data_size(
        cls, v: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        if v is not None:
            if len(v) == 0:
                raise ValueError("Inline data must not be empty.")
            if len(v) > settings.max_inline_rows:
                raise ValueError(
                    f"Inline data has {len(v)} rows (max {settings.max_inline_rows})"
                )
        return v

    @model_validator(mode="after")
    def check_input_source(self):
        _check_exactly_one(
            values=(self.artifact_id, self.data),
            field_names=("artifact_id", "data"),
            label="Input",
        )
        return self

    @property
    def _input_data_mode(self) -> InputDataMode:
        return (
            InputDataMode.artifact_id
            if self.artifact_id is not None
            else InputDataMode.dataframe
        )

    @property
    def _aid_or_dataframe(self) -> UUID | pd.DataFrame:
        if self.artifact_id is not None:
            return UUID(self.artifact_id)
        return pd.DataFrame(self.data)


class AgentInput(_SingleSourceInput):
    """Input for the agent operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language task to perform on each row.", min_length=1
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the agent's response per row.",
    )
    effort_level: EffortLevel | None = Field(
        default=EffortLevel.MEDIUM,
        description='Effort preset controlling cost/quality tradeoff: "low" (fast, cheap), '
        '"medium" (default), "high" (thorough, expensive). '
        "Set to null to use custom llm/iteration_budget/include_reasoning instead.",
    )
    llm: LLMEnumPublic | None = Field(
        default=None,
        description="Specific LLM to use (e.g. CLAUDE_4_6_SONNET_MEDIUM). "
        "Only used when effort_level is null.",
    )
    iteration_budget: int | None = Field(
        default=None,
        description="Max agent iterations per row (0-20). Only used when effort_level is null.",
        ge=0,
        le=20,
    )
    include_reasoning: bool | None = Field(
        default=None,
        description="Include reasoning notes in output. Only used when effort_level is null.",
    )
    enforce_row_independence: bool = Field(
        default=False,
        description="If true, run each row's agent independently without sharing context across rows.",
    )

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)


class RankInput(_SingleSourceInput):
    """Input for the rank operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language instructions for scoring a single row.",
        min_length=1,
    )
    field_name: str = Field(..., description="Name of the field to sort by.")
    field_type: Literal["float", "int", "str", "bool"] = Field(
        default="float",
        description="Type of the score field: 'float', 'int', 'str', or 'bool'",
    )
    ascending_order: bool = Field(
        default=True, description="Sort ascending (True) or descending (False)."
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the response model.",
    )

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)


class DedupeInput(_SingleSourceInput):
    """Input for the dedupe operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    equivalence_relation: str = Field(
        ...,
        description="Natural language description of what makes two rows equivalent/duplicates. "
        "The LLM will use this to identify which rows represent the same entity.",
        min_length=1,
    )
    strategy: DedupeOperationStrategy | None = Field(
        default=None,
        description="Controls what happens after duplicate clusters are identified. "
        '"identify": cluster only, adds metadata columns but keeps all rows. '
        '"select" (default): picks the best representative row per cluster. '
        '"combine": synthesizes a single combined row per cluster by merging the best information from all duplicates.',
    )
    strategy_prompt: str | None = Field(
        default=None,
        description="Natural-language instructions guiding how the LLM selects or combines rows. "
        'Only used with "select" and "combine" strategies. '
        'Examples: "Prefer the record with the most complete contact information", '
        '"For each field, keep the most recent and complete value".',
    )


class MergeInput(BaseModel):
    """Input for the merge operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language description of how to match rows.",
        min_length=1,
    )

    # LEFT table
    left_artifact_id: str | None = Field(
        default=None,
        description="Artifact ID (UUID) for the left table, from upload_data or request_upload_url.",
    )
    left_data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data for the left table as a list of row objects.",
    )

    # RIGHT table
    right_artifact_id: str | None = Field(
        default=None,
        description="Artifact ID (UUID) for the right table, from upload_data or request_upload_url.",
    )
    right_data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data for the right table as a list of row objects.",
    )

    merge_on_left: str | None = Field(
        default=None,
        description="Only set if you expect some exact string matches on the chosen column or want to draw special attention of LLM agents to this particular column. Fine to leave unspecified in all other cases.",
    )
    merge_on_right: str | None = Field(
        default=None,
        description="Only set if you expect some exact string matches on the chosen column or want to draw special attention of LLM agents to this particular column. Fine to leave unspecified in all other cases.",
    )

    use_web_search: Literal["auto", "yes", "no"] | None = Field(
        default=None,
        description='Control web search: "auto", "yes", or "no".',
    )
    relationship_type: (
        Literal["many_to_one", "one_to_one", "one_to_many", "many_to_many"] | None
    ) = Field(
        default=None,
        description='Control merge relationship type / cardinality between the two tables: "many_to_one" (default) allows multiple left rows to match one right row (e.g. matching reviews to product), "one_to_one" enforces unique matching between left and right rows (e.g. CEO to company), "one_to_many" allows one left row to match multiple right rows (e.g. company to products), "many_to_many" allows multiple left rows to match multiple right rows (e.g. companies to investors). For one_to_many and many_to_many, multiple matches are represented by joining the right-table values with " | " in each added column.',
    )

    session_id: str | None = Field(
        default=None,
        description="Session ID (UUID) to add to an existing session. If session_name is also provided, the session is renamed.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. If session_id is also provided, renames the existing session.",
    )

    @field_validator("left_artifact_id", "right_artifact_id")
    @classmethod
    def validate_artifact_ids(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                UUID(v)
            except ValueError as exc:
                raise ValueError(f"artifact_id must be a valid UUID: {v}") from exc
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        return _validate_session_id(v)

    @field_validator("left_data", "right_data")
    @classmethod
    def validate_data_size(
        cls, v: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        if v is not None:
            if len(v) == 0:
                raise ValueError("Inline data must not be empty.")
            if len(v) > settings.max_inline_rows:
                raise ValueError(
                    f"Inline data has {len(v)} rows (max {settings.max_inline_rows})"
                )
        return v

    @model_validator(mode="after")
    def check_sources(self) -> "MergeInput":
        _check_exactly_one(
            values=(self.left_artifact_id, self.left_data),
            field_names=("left_artifact_id", "left_data"),
            label="Left table",
        )
        _check_exactly_one(
            values=(self.right_artifact_id, self.right_data),
            field_names=("right_artifact_id", "right_data"),
            label="Right table",
        )
        return self

    @property
    def _left_input_data_mode(self) -> InputDataMode:
        return (
            InputDataMode.artifact_id
            if self.left_artifact_id is not None
            else InputDataMode.dataframe
        )

    @property
    def _left_aid_or_dataframe(self) -> UUID | pd.DataFrame:
        if self.left_artifact_id is not None:
            return UUID(self.left_artifact_id)
        return pd.DataFrame(self.left_data)

    @property
    def _right_input_data_mode(self) -> InputDataMode:
        return (
            InputDataMode.artifact_id
            if self.right_artifact_id is not None
            else InputDataMode.dataframe
        )

    @property
    def _right_aid_or_dataframe(self) -> UUID | pd.DataFrame:
        if self.right_artifact_id is not None:
            return UUID(self.right_artifact_id)
        return pd.DataFrame(self.right_data)


class ForecastInput(_SingleSourceInput):
    """Input for the forecast operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    context: str | None = Field(
        default=None,
        description="Optional batch-level context or instructions that apply to every row "
        "(e.g. 'Focus on EU regulatory sources' or 'Assume resolution by end of 2027'). "
        "Leave empty when the rows are self-contained.",
    )
    forecast_type: Literal["binary", "numeric"] = Field(
        description="Type of forecast. 'binary': yes/no probability (0-100) for questions like "
        "'Will X happen?'. 'numeric': percentile estimates (p10-p90) for questions like "
        "'What will the price/value/count be?'. Requires output_field when 'numeric'.",
    )
    output_field: str | None = Field(
        default=None,
        description="Name of the numeric quantity being forecast (e.g. 'price', 'count'). "
        "Required when forecast_type is 'numeric'. Output columns are named "
        "{output_field}_p10 through {output_field}_p90.",
    )
    units: str | None = Field(
        default=None,
        description="Units for the numeric forecast (e.g. 'USD per barrel', 'thousands'). "
        "Required when forecast_type is 'numeric'.",
    )


class ClassifyInput(_SingleSourceInput):
    """Input for the classify operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language instructions describing how to classify each row.",
        min_length=1,
    )
    categories: list[str] = Field(
        ...,
        description="Allowed category values (minimum 2). Each row will be assigned one of these.",
        min_length=2,
    )
    classification_field: str = Field(
        default="classification",
        description="Name of the output column that will contain the assigned category.",
    )
    include_reasoning: bool = Field(
        default=False,
        description="If true, adds a 'reasoning' column with the agent's justification.",
    )


class UploadDataInput(BaseModel):
    """Input for the upload_data tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    source: str = Field(
        ...,
        description="Data source: http(s) URL (Google Sheets/Drive supported) "
        "or absolute local file path (stdio mode only).",
        min_length=1,
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID (UUID) to add to an existing session. If session_name is also provided, the session is renamed.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. If session_id is also provided, renames the existing session.",
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if is_url(v):
            return validate_url(v)
        # Local path
        if settings.is_http:
            raise ValueError(
                "Local file paths are not supported in HTTP mode. "
                "To upload a local file: "
                "1) call futuresearch_request_upload_url with the filename, "
                "2) execute the returned curl command, "
                "3) use the artifact_id from the response in your processing tool."
            )
        validate_csv_path(v)
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        return _validate_session_id(v)


class SingleAgentInput(BaseModel):
    """Input for a single agent operation (no CSV)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language task for the agent to perform.",
        min_length=1,
    )
    input_data: dict[str, Any] | None = Field(
        default=None,
        description="Optional context as key-value pairs (e.g. {'company': 'Acme', 'url': 'acme.com'}).",
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON schema for the agent response. Required when return_table=True "
        "to define the fields for each item in the list. If omitted, results default to "
        'a single {"answer": string} field.',
    )
    effort_level: EffortLevel | None = Field(
        default=EffortLevel.MEDIUM,
        description='Effort preset controlling cost/quality tradeoff: "low" (fast, cheap), '
        '"medium" (default), "high" (thorough, expensive). '
        "Set to null to use custom llm/iteration_budget/include_reasoning instead.",
    )
    llm: LLMEnumPublic | None = Field(
        default=None,
        description="Specific LLM to use (e.g. CLAUDE_4_6_SONNET_MEDIUM). "
        "Only used when effort_level is null.",
    )
    iteration_budget: int | None = Field(
        default=None,
        description="Max agent iterations (0-20). Only used when effort_level is null.",
        ge=0,
        le=20,
    )
    include_reasoning: bool | None = Field(
        default=None,
        description="Include reasoning notes in output. Only used when effort_level is null.",
    )
    return_table: bool = Field(
        default=False,
        description="MUST be true when the task asks for a list of items (e.g. 'find 15 startups', "
        "'list all X'). Always pair with response_schema to define the fields per item. "
        "If false (default), returns a single result row.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID (UUID) to add to an existing session. If session_name is also provided, the session is renamed.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. If session_id is also provided, renames the existing session.",
    )

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        return _validate_session_id(v)


def _validate_task_id(v: str) -> str:
    """Validate task_id is a valid UUID."""
    try:
        UUID(v)
    except ValueError as exc:
        raise ValueError("task_id must be a valid UUID") from exc
    return v


class BrowseListsInput(BaseModel):
    """Input for browsing reference lists."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search: str | None = Field(
        default=None,
        description="Search term to match against list names (case-insensitive). Requires knowing what's there, prefer browsing the full list by omitting this parameter.",
    )
    category: str | None = Field(
        default=None,
        description="Filter by category. Requires knowing the categories, prefer browsing the full list by omitting this parameter.",
    )


class UseListInput(BaseModel):
    """Input for importing a reference list into a session."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    artifact_id: str = Field(
        ...,
        description="artifact_id from futuresearch_browse_lists results.",
    )


class ProgressInput(BaseModel):
    """Input for checking task progress."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID returned by the operation tool.")
    cursor: str | None = Field(
        default=None,
        description="Cursor from the previous progress call. "
        "Pass this to only receive new rows and summaries since the last check. "
        "Omit on the first call to see all completed rows so far.",
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return _validate_task_id(v)


class CancelInput(BaseModel):
    """Input for cancelling a running task."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID to cancel.")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return _validate_task_id(v)


def _validate_output_path(v: str | None) -> str | None:
    """Validate output_path ends in .csv and parent directory exists."""
    if v is not None:
        if not v.lower().endswith(".csv"):
            raise ValueError("output_path must end in .csv")
        parent = Path(v).parent
        if not parent.exists():
            raise ValueError(
                f"Parent directory does not exist: {parent}. "
                "Create it first or use a different path."
            )
    return v


class StdioResultsInput(BaseModel):
    """Input for retrieving completed task results in stdio mode."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID of the completed task.")
    output_path: str = Field(
        ...,
        description="Full absolute path to the output CSV file (must end in .csv).",
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return _validate_task_id(v)

    @field_validator("output_path")
    @classmethod
    def validate_output(cls, v: str) -> str:
        result = _validate_output_path(v)
        assert result is not None
        return result


class HttpResultsInput(BaseModel):
    """Input for retrieving completed task results in HTTP mode."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID of the completed task.")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return _validate_task_id(v)

    output_path: str | None = Field(
        default=None,
        description="Full absolute path to the output CSV file (must end in .csv). "
        "Optional — results are returned as a paginated preview by default.",
    )
    offset: int = Field(
        default=0,
        description="Row offset for pagination. Default 0 returns the first page.",
        ge=0,
    )
    page_size: int = Field(
        default=settings.auto_page_size_threshold,
        description=(
            "Number of result rows to load into your context so you can read them. "
            "The user has access to all rows via the table view regardless of this value. "
            f"For tasks with {settings.auto_page_size_threshold} or fewer rows, set page_size to the total. "
            f"For larger tasks, you MUST use the page_size from the futuresearch_progress completion message — "
            f"do NOT set a higher value. "
            "Use offset to paginate through larger datasets."
        ),
        ge=1,
        le=10000,
    )

    @field_validator("output_path")
    @classmethod
    def validate_output(cls, v: str | None) -> str | None:
        # Only check file extension, not parent directory existence.
        # In HTTP mode the path comes from a remote client whose filesystem
        # is not visible to the server.
        if v is not None and not v.lower().endswith(".csv"):
            raise ValueError("output_path must end in .csv")
        return v


class ListSessionsInput(BaseModel):
    """Input for listing sessions with pagination."""

    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0, description="Number of sessions to skip")
    limit: int = Field(
        default=25,
        ge=1,
        le=1000,
        description="Max sessions per page (default 25, max 1000)",
    )


class ListSessionTasksInput(BaseModel):
    """Input for listing tasks in a session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(description="The session ID to list tasks for")

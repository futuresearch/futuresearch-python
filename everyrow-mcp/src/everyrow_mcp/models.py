"""Input models and schema helpers for everyrow MCP tools."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pandas as pd
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
    model_validator,
)

from everyrow_mcp.config import settings
from everyrow_mcp.utils import is_url, validate_csv_path, validate_url

JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


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


def _validate_screen_response_schema(
    schema: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate screen response_schema includes at least one boolean property."""
    validated_schema = _validate_response_schema(schema)
    if validated_schema is None:
        return None

    properties = validated_schema["properties"]
    has_boolean_property = any(
        isinstance(field_def, dict) and field_def.get("type") == "boolean"
        for field_def in properties.values()
    )
    if not has_boolean_property:
        raise ValueError("response_schema must include at least one boolean property")

    return validated_schema


def _schema_to_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Convert a JSON schema dict to a dynamic Pydantic model.

    This allows the MCP client to pass arbitrary response schemas without
    needing to define Python classes.
    """
    properties = schema["properties"]
    required = set(schema.get("required", []))

    fields: dict[str, Any] = {}
    for field_name, field_def in properties.items():
        if not isinstance(field_def, dict):
            raise ValueError(
                f"Invalid property schema for '{field_name}': expected an object."
            )

        field_type_str = field_def.get("type", "string")
        python_type = JSON_TYPE_MAP.get(field_type_str, str)
        description = field_def.get("description", "")

        if field_name in required:
            fields[field_name] = (python_type, Field(..., description=description))
        else:
            fields[field_name] = (
                python_type | None,
                Field(default=None, description=description),
            )

    return create_model(name, **fields)


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


def _check_session_exclusivity(
    session_id: str | None, session_name: str | None
) -> None:
    """Raise if both session_id and session_name are provided."""
    if session_id is not None and session_name is not None:
        raise ValueError(
            "session_id and session_name are mutually exclusive — "
            "pass session_id to resume an existing session, "
            "or session_name to create a new one."
        )


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
        description="Session ID (UUID) to resume. Mutually exclusive with session_name.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. Mutually exclusive with session_id.",
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
        _check_session_exclusivity(self.session_id, self.session_name)
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


class ScreenInput(_SingleSourceInput):
    """Input for the screen operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language screening criteria.", min_length=1
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the response model. "
        "Must include at least one boolean property — screen uses the boolean field to filter rows into pass/fail.",
    )

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_screen_response_schema(v)


class DedupeInput(_SingleSourceInput):
    """Input for the dedupe operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    equivalence_relation: str = Field(
        ...,
        description="Natural language description of what makes two rows equivalent/duplicates. "
        "The LLM will use this to identify which rows represent the same entity.",
        min_length=1,
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
        description="Session ID (UUID) to resume. Mutually exclusive with session_name.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. Mutually exclusive with session_id.",
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
        _check_session_exclusivity(self.session_id, self.session_name)
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
        description="Session ID (UUID) to resume. Mutually exclusive with session_name.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. Mutually exclusive with session_id.",
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
                "1) call everyrow_request_upload_url with the filename, "
                "2) execute the returned curl command, "
                "3) use the artifact_id from the response in your processing tool."
            )
        validate_csv_path(v)
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        return _validate_session_id(v)

    @model_validator(mode="after")
    def check_session_exclusivity(self) -> "UploadDataInput":
        _check_session_exclusivity(self.session_id, self.session_name)
        return self


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
        description="Optional JSON schema for the agent response.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID (UUID) to resume. Mutually exclusive with session_name.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable name for a new session. Mutually exclusive with session_id.",
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

    @model_validator(mode="after")
    def check_session_exclusivity(self) -> "SingleAgentInput":
        _check_session_exclusivity(self.session_id, self.session_name)
        return self


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
        description="Search term to match against list names (case-insensitive).",
    )
    category: str | None = Field(
        default=None,
        description="Filter by category (e.g. 'Finance', 'Geography').",
    )


class UseListInput(BaseModel):
    """Input for importing a reference list into a session."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    artifact_id: str = Field(
        ...,
        description="artifact_id from everyrow_browse_lists results.",
    )


class ProgressInput(BaseModel):
    """Input for checking task progress."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID returned by the operation tool.")

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
    output_spreadsheet_title: str | None = Field(
        default=None,
        description="Create a new Google Sheet with this title and write the full "
        "results there. Returns the spreadsheet URL. Fails if a sheet with "
        "this exact title already exists — pick a unique name.",
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
    output_spreadsheet_title: str | None = Field(
        default=None,
        description="Create a new Google Sheet with this title and write the full "
        "results there. Returns the spreadsheet URL. Fails if a sheet with "
        "this exact title already exists — pick a unique name.",
    )
    offset: int = Field(
        default=0,
        description="Row offset for pagination. Default 0 returns the first page.",
        ge=0,
    )
    page_size: int = Field(
        default=50,
        description=(
            "Number of result rows to load into your context so you can read them. "
            "The user has access to all rows via the widget regardless of this value. "
            f"REQUIRED: If the task produced more than {settings.auto_page_size_threshold} rows, "
            "you must ask the user how many rows they want before calling this tool. "
            "Do not use the default without asking. "
            f"If {settings.auto_page_size_threshold} or fewer rows, skip asking and set page_size to the total. "
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

    offset: int = Field(0, ge=0, description="Number of sessions to skip")
    limit: int = Field(
        25, ge=1, le=1000, description="Max sessions per page (default 25, max 1000)"
    )

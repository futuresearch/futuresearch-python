"""Input models and schema helpers for everyrow MCP tools."""

from pathlib import Path
from typing import Any, Literal

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

from everyrow_mcp.utils import validate_csv_path_or_url

JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


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


class _SingleSourceInput(BaseModel):
    input_csv: str | None = Field(
        default=None,
        description="Absolute path to a local CSV file, or an http/https URL "
        "(Google Sheets and Drive share links are supported).",
    )
    data: str | list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data — CSV string or JSON array of objects.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str | None) -> str | None:
        if v is not None:
            validate_csv_path_or_url(v)
        return v

    @model_validator(mode="after")
    def check_input_source(self):
        _check_exactly_one(
            values=(self.input_csv, self.data),
            field_names=("input_csv", "data"),
            label="Input",
        )
        return self


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
    left_csv: str | None = Field(
        default=None,
        description="Absolute path to the left CSV file, or an http/https URL "
        "(Google Sheets and Drive share links are supported).",
    )
    left_data: str | list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data for the left table — CSV string or JSON array of objects.",
    )

    # RIGHT table
    right_csv: str | None = Field(
        default=None,
        description="Absolute path to the right CSV file, or an http/https URL "
        "(Google Sheets and Drive share links are supported).",
    )
    right_data: str | list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline data for the right table — CSV string or JSON array of objects.",
    )

    merge_on_left: str | None = Field(
        default=None,
        description="Column name in the left table to match on.",
    )
    merge_on_right: str | None = Field(
        default=None,
        description="Column name in the right table to match on.",
    )

    use_web_search: Literal["auto", "yes", "no"] | None = Field(
        default=None,
        description='Control web search: "auto", "yes", or "no".',
    )
    relationship_type: Literal["many_to_one", "one_to_one"] | None = Field(
        default=None,
        description="Relationship type: many_to_one (default) or one_to_one.",
    )

    @field_validator("left_csv", "right_csv")
    @classmethod
    def validate_csv_paths(cls, v: str | None) -> str | None:
        if v is not None:
            validate_csv_path_or_url(v)
        return v

    @model_validator(mode="after")
    def check_sources(self) -> "MergeInput":
        _check_exactly_one(
            values=(self.left_csv, self.left_data),
            field_names=("left_csv", "left_data"),
            label="Left table",
        )
        _check_exactly_one(
            values=(self.right_csv, self.right_data),
            field_names=("right_csv", "right_data"),
            label="Right table",
        )
        return self


class ForecastInput(_SingleSourceInput):
    """Input for the forecast operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    context: str | None = Field(
        default=None,
        description="Optional batch-level context or instructions that apply to every row "
        "(e.g. 'Focus on EU regulatory sources' or 'Assume resolution by end of 2027'). "
        "Leave empty when the rows are self-contained.",
    )


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

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)


class ProgressInput(BaseModel):
    """Input for checking task progress."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID returned by the operation tool.")


class CancelInput(BaseModel):
    """Input for cancelling a running task."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID to cancel.")


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
        default=1000,
        description="Number of rows per page. Default 1000. Max 10000.",
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

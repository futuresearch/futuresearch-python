"""Input models and schema helpers for everyrow MCP tools."""

from typing import Any, Literal

from jsonschema import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from everyrow_mcp.utils import validate_csv_output_path, validate_csv_path


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


JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


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


class AgentInput(BaseModel):
    """Input for the agent operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language task to perform on each row.", min_length=1
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the agent's response per row.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)


class RankInput(BaseModel):
    """Input for the rank operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language instructions for scoring a single row.",
        min_length=1,
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
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

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_response_schema(v)


class ScreenInput(BaseModel):
    """Input for the screen operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ..., description="Natural language screening criteria.", min_length=1
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for the response model. "
        "Must include at least one boolean property — screen uses the boolean field to filter rows into pass/fail.",
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _validate_screen_response_schema(v)


class DedupeInput(BaseModel):
    """Input for the dedupe operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    equivalence_relation: str = Field(
        ...,
        description="Natural language description of what makes two rows equivalent/duplicates. "
        "The LLM will use this to identify which rows represent the same entity.",
        min_length=1,
    )
    input_csv: str = Field(..., description="Absolute path to the input CSV file.")

    @field_validator("input_csv")
    @classmethod
    def validate_input_csv(cls, v: str) -> str:
        validate_csv_path(v)
        return v


class MergeInput(BaseModel):
    """Input for the merge operation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task: str = Field(
        ...,
        description="Natural language description of how to match rows.",
        min_length=1,
    )
    left_csv: str = Field(
        ...,
        description="Absolute path to the left CSV. Works like a LEFT JOIN: ALL rows from this table are kept in the output. This should be the table being enriched.",
    )
    right_csv: str = Field(
        ...,
        description="Absolute path to the right CSV. This is the lookup/reference table. Its columns are added to matching left rows; unmatched left rows get nulls.",
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
        default=None, description='Control web search: "auto", "yes", or "no".'
    )
    relationship_type: Literal["many_to_one", "one_to_one"] | None = Field(
        default=None,
        description="Leave unset for the default many_to_one, which is correct in most cases. many_to_one: multiple left rows can match one right row (e.g. products → companies). one_to_one: each left row matches at most one right row AND vice versa. Only use one_to_one when both tables represent unique entities of the same kind.",
    )

    @field_validator("left_csv", "right_csv")
    @classmethod
    def validate_csv_paths(cls, v: str) -> str:
        validate_csv_path(v)
        return v


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


class ResultsInput(BaseModel):
    """Input for retrieving completed task results."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(..., description="The task ID of the completed task.")
    output_path: str = Field(
        ...,
        description="Full absolute path to the output CSV file (must end in .csv).",
    )

    @field_validator("output_path")
    @classmethod
    def validate_output(cls, v: str) -> str:
        validate_csv_output_path(v)
        return v

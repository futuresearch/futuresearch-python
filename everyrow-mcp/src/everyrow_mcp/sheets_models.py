"""Input models for Google Sheets MCP tools."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Matches the 44-char alphanumeric spreadsheet ID in a Google Sheets URL
_SHEETS_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")

# A1 notation range validation
_A1_RANGE_RE = re.compile(r"^[A-Za-z0-9_' !:$]+$")
_MAX_RANGE_LENGTH = 200


def _extract_spreadsheet_id(v: str) -> str:
    """Accept a full Google Sheets URL or a bare spreadsheet ID.

    Extracts the ID from URLs like:
      https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit
    and passes through bare IDs like:
      1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
    """
    v = v.strip()
    m = _SHEETS_URL_RE.search(v)
    if m:
        return m.group(1)
    # Bare ID: must be alphanumeric + hyphens/underscores, typically 44 chars
    if re.fullmatch(r"[a-zA-Z0-9_-]+", v) and len(v) >= 10:
        return v
    raise ValueError(
        f"Invalid spreadsheet_id: expected a Google Sheets URL or a bare spreadsheet ID, got {v!r}"
    )


def _validate_a1_range(v: str) -> str:
    """Validate an A1 notation range string."""
    if len(v) > _MAX_RANGE_LENGTH:
        raise ValueError(f"Range too long ({len(v)} chars, max {_MAX_RANGE_LENGTH})")
    if not _A1_RANGE_RE.fullmatch(v):
        raise ValueError(
            "Invalid range: contains disallowed characters. "
            "Use A1 notation (e.g. 'Sheet1!A1:D10')."
        )
    return v


class SheetsReadInput(BaseModel):
    """Input for the sheets_read tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    spreadsheet_id: str = Field(
        ...,
        description="Google Sheets spreadsheet ID or full URL.",
    )
    range: str = Field(
        default="Sheet1",
        description="A1 notation range to read. Examples: 'Sheet1' (entire sheet), "
        "'Sheet1!A1:D10' (rectangle), 'Sheet1!B:B' (single column), "
        "'Sheet1!1:5' (first 5 rows), 'Sheet2' (different tab). "
        "Defaults to entire first sheet.",
    )

    @field_validator("spreadsheet_id")
    @classmethod
    def extract_id(cls, v: str) -> str:
        return _extract_spreadsheet_id(v)

    @field_validator("range")
    @classmethod
    def validate_range(cls, v: str) -> str:
        return _validate_a1_range(v)


class SheetsWriteInput(BaseModel):
    """Input for the sheets_write tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    spreadsheet_id: str = Field(
        ...,
        description="Google Sheets spreadsheet ID or full URL.",
    )
    range: str = Field(
        default="Sheet1",
        description="A1 notation range to write to. To add columns next to existing data, "
        "use the first empty column (e.g. 'Sheet1!E1'). Only the target range is "
        "affected — existing data in other columns is preserved.",
    )
    data: list[dict[str, Any]] = Field(
        ...,
        description="Data as a list of dicts (JSON records). Keys become column headers.",
        min_length=1,
    )
    append: bool = Field(
        default=False,
        description="If True, append after existing data instead of overwriting.",
    )
    confirm_overwrite: bool = Field(
        default=False,
        description="Must be set to True to overwrite existing data when append=False. "
        "The tool will check if the range has data and warn you first.",
    )

    @field_validator("spreadsheet_id")
    @classmethod
    def extract_id(cls, v: str) -> str:
        return _extract_spreadsheet_id(v)

    @field_validator("range")
    @classmethod
    def validate_range(cls, v: str) -> str:
        return _validate_a1_range(v)


class SheetsCreateInput(BaseModel):
    """Input for the sheets_create tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(
        ...,
        description="Title for the new spreadsheet.",
        min_length=1,
    )
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional initial data as a list of dicts (JSON records).",
    )


class SheetsInfoInput(BaseModel):
    """Input for the sheets_info tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    spreadsheet_id: str = Field(
        ...,
        description="Google Sheets spreadsheet ID or full URL.",
    )

    @field_validator("spreadsheet_id")
    @classmethod
    def extract_id(cls, v: str) -> str:
        return _extract_spreadsheet_id(v)


class SheetsListInput(BaseModel):
    """Input for the sheets_list tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str | None = Field(
        default=None,
        description="Optional search query to filter spreadsheets by name (e.g. 'Budget 2024').",
    )
    max_results: int = Field(
        default=20,
        description="Maximum number of spreadsheets to return.",
        ge=1,
        le=100,
    )

from __future__ import annotations

import copy
from typing import Any

from everyrow_mcp.app import mcp

# ── everyrow_progress ──────────────────────────────────────────────────

_PROGRESS_DESC = """\
Check progress of a running task. Blocks briefly to limit the polling rate.

After receiving a status update, immediately call everyrow_progress again
unless the task is completed or failed. The tool handles pacing internally.
Do not add commentary between progress calls, just call again immediately."""

# ── everyrow_results ───────────────────────────────────────────────────

_RESULTS_STDIO = """\
Retrieve results from a completed everyrow task.

Only call this after everyrow_progress reports status 'completed'.
Pass output_path (ending in .csv) to save results as a local CSV file."""

_RESULTS_HTTP = """\
Retrieve results from a completed everyrow task.

Only call this after everyrow_progress reports status 'completed'.
Results are returned as a paginated preview with a download link.
Do NOT pass output_path — it has no effect in this mode."""

# ── Registry ───────────────────────────────────────────────────────────

_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "everyrow_progress": {"stdio": _PROGRESS_DESC, "http": _PROGRESS_DESC},
    "everyrow_results": {"stdio": _RESULTS_STDIO, "http": _RESULTS_HTTP},
}


# ── Schema patching ───────────────────────────────────────────────────
#
# Only the advertised JSON schema changes — the underlying Pydantic models
# keep all fields (with defaults) so validation never breaks.

_original_schemas: dict[str, dict[str, Any]] = {}

# Tools whose input models contain `input_csv` (from _SingleSourceInput).
_CSV_INPUT_TOOLS: dict[str, str] = {
    "everyrow_agent": "AgentInput",
    "everyrow_rank": "RankInput",
    "everyrow_screen": "ScreenInput",
    "everyrow_dedupe": "DedupeInput",
}


def _snapshot(tool_name: str) -> dict[str, Any] | None:
    """Return (and cache) a deep copy of a tool's original parameters schema."""
    if tool_name not in _original_schemas:
        tool = mcp._tool_manager.get_tool(tool_name)
        if tool is None:
            return None
        _original_schemas[tool_name] = copy.deepcopy(tool.parameters)
    return copy.deepcopy(_original_schemas[tool_name])


def _patch_csv_input_tools(mode: str) -> None:
    """In HTTP mode, remove ``input_csv`` from single-source input tools.

    The HTTP server cannot read the client's local filesystem, so only
    ``input_data`` and ``input_json`` are valid in HTTP mode.
    """
    if mode == "stdio":
        # Restore originals (all three input options visible)
        for tool_name in _CSV_INPUT_TOOLS:
            original = _snapshot(tool_name)
            if original is None:
                continue
            tool = mcp._tool_manager.get_tool(tool_name)
            if tool is not None:
                tool.parameters = original
        return

    for tool_name, def_name in _CSV_INPUT_TOOLS.items():
        schema = _snapshot(tool_name)
        if schema is None:
            continue
        input_def = schema.get("$defs", {}).get(def_name, {})
        props = input_def.get("properties", {})
        props.pop("input_csv", None)
        input_def["properties"] = props
        tool = mcp._tool_manager.get_tool(tool_name)
        if tool is not None:
            tool.parameters = schema


def _patch_merge_schema(mode: str) -> None:
    """In HTTP mode, remove ``left_csv`` and ``right_csv`` from everyrow_merge."""
    schema = _snapshot("everyrow_merge")
    if schema is None:
        return
    tool = mcp._tool_manager.get_tool("everyrow_merge")
    if tool is None:
        return

    if mode == "stdio":
        tool.parameters = schema
        return

    merge_def = schema.get("$defs", {}).get("MergeInput", {})
    props = merge_def.get("properties", {})
    props.pop("left_csv", None)
    props.pop("right_csv", None)
    merge_def["properties"] = props
    tool.parameters = schema


def _patch_results_schema(mode: str) -> None:
    """Trim everyrow_results input schema to show only mode-relevant fields.

    In stdio mode:  show task_id (required) + output_path (required).
    In HTTP mode:   show task_id (required) + offset + page_size.
    """
    schema = _snapshot("everyrow_results")
    if schema is None:
        return
    tool = mcp._tool_manager.get_tool("everyrow_results")
    if tool is None:
        return

    results_def: dict[str, Any] = schema.get("$defs", {}).get("ResultsInput", {})
    if not results_def:
        return

    props = results_def.get("properties", {})
    required = list(results_def.get("required", []))

    if mode == "stdio":
        props.pop("offset", None)
        props.pop("page_size", None)
        props.pop("output_spreadsheet_title", None)
        props["output_path"] = {
            "type": "string",
            "description": (
                "Full absolute path to the output CSV file (must end in .csv)."
            ),
            "title": "Output Path",
        }
        if "output_path" not in required:
            required.append("output_path")
    else:
        props.pop("output_path", None)
        required = [r for r in required if r != "output_path"]

    results_def["properties"] = props
    results_def["required"] = required
    tool.parameters = schema


def set_tool_descriptions(transport: str) -> None:
    """Patch registered tool descriptions and schemas for *transport*.

    Call once from ``main()`` after determining the transport mode.
    """
    mode = "stdio" if transport == "stdio" else "http"
    for tool_name, descs in _DESCRIPTIONS.items():
        tool = mcp._tool_manager.get_tool(tool_name)
        if tool is not None:
            tool.description = descs[mode]

    _patch_csv_input_tools(mode)
    _patch_merge_schema(mode)
    _patch_results_schema(mode)

    # Sheets tools require HTTP mode (OAuth provides the Google token)
    if mode == "stdio":
        _SHEETS_TOOLS = [
            "sheets_list",
            "sheets_read",
            "sheets_write",
            "sheets_create",
            "sheets_info",
        ]
        for name in _SHEETS_TOOLS:
            tool = mcp._tool_manager.get_tool(name)
            if tool is not None:
                mcp._tool_manager._tools.pop(name, None)

"""Contract tests to keep MCP tool metadata in sync with manifest.json."""

import asyncio
import json
from pathlib import Path

from mcp.types import Tool

from everyrow_mcp import server

MCP_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = MCP_ROOT / "manifest.json"


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _python_tools_from_server() -> dict[str, str]:
    """Return MCP tool name -> first line of runtime-registered description."""
    tools: list[Tool] = asyncio.run(server.mcp.list_tools())
    return {tool.name: _first_non_empty_line(tool.description or "") for tool in tools}


def _manifest_tools() -> dict[str, str]:
    payload = json.loads(MANIFEST_PATH.read_text())
    tools = payload.get("tools", [])
    return {tool["name"]: tool["description"] for tool in tools}


def test_python_tools_are_in_manifest():
    python_tools = _python_tools_from_server()
    manifest_tools = _manifest_tools()

    missing = sorted(set(python_tools) - set(manifest_tools))
    assert not missing, f"Tools defined in Python but missing from manifest: {missing}"


def test_manifest_tools_are_in_python():
    python_tools = _python_tools_from_server()
    manifest_tools = _manifest_tools()

    missing = sorted(set(manifest_tools) - set(python_tools))
    assert not missing, f"Tools in manifest but missing from Python server: {missing}"


def test_manifest_descriptions_match_python_docstrings():
    python_tools = _python_tools_from_server()
    manifest_tools = _manifest_tools()

    mismatches = {}
    for tool_name in sorted(set(python_tools) & set(manifest_tools)):
        if python_tools[tool_name] != manifest_tools[tool_name]:
            mismatches[tool_name] = {
                "python_docstring_first_line": python_tools[tool_name],
                "manifest_description": manifest_tools[tool_name],
            }

    assert not mismatches, (
        "Manifest descriptions do not match first docstring line for tools: "
        f"{json.dumps(mismatches, indent=2, sort_keys=True)}"
    )

"""Google Sheets MCP tools for the everyrow MCP server.

Provides 5 tools: sheets_list, sheets_read, sheets_write, sheets_create, sheets_info.
All tools use the existing FastMCP instance from app.py.
"""

from __future__ import annotations

import json
import logging

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import TextContent, ToolAnnotations

from everyrow_mcp.app import mcp
from everyrow_mcp.config import settings
from everyrow_mcp.redis_store import build_key, get_redis_client
from everyrow_mcp.sheets_client import (
    GoogleSheetsClient,
    get_google_token,
    records_to_values,
    values_to_records,
)
from everyrow_mcp.sheets_models import (
    SheetsCreateInput,
    SheetsInfoInput,
    SheetsListInput,
    SheetsReadInput,
    SheetsWriteInput,
)

logger = logging.getLogger(__name__)


def _error_message(e: Exception) -> str:
    """Format a user-friendly error message from a Google API exception."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 403:
            return "Permission denied. Check that the spreadsheet is shared with you."
        if status == 404:
            return "Spreadsheet not found. Check the spreadsheet ID or URL."
        if status == 429:
            return "Rate limited by Google API. Please try again in a moment."
        return f"Google API error (HTTP {status}). Please try again."
    return f"Sheets operation failed ({type(e).__name__}). Please try again."


async def _check_sheets_rate_limit() -> list[TextContent] | None:
    """Enforce per-user rate limiting on sheets operations.

    Returns an error response if the rate limit is exceeded, or ``None`` if OK.
    Only active in HTTP mode; always returns ``None`` for stdio.
    Fail-open if Redis is unavailable.
    """
    if not settings.is_http:
        return None

    try:
        access_token = get_access_token()
        user_id = access_token.client_id if access_token else "anonymous"
        redis = get_redis_client()
        rl_key = build_key("ratelimit", "sheets", user_id)
        async with redis.pipeline() as pipe:
            pipe.incr(rl_key)
            pipe.expire(rl_key, settings.sheets_rate_window, nx=True)
            count, _ = await pipe.execute()
        if count > settings.sheets_rate_limit:
            return [
                TextContent(
                    type="text",
                    text="Sheets rate limit exceeded. Please wait before trying again.",
                )
            ]
    except Exception:
        logger.debug("Sheets rate limit check failed (fail-open)", exc_info=True)
    return None


def _audit_user_id() -> str:
    """Best-effort user ID for audit logs."""
    try:
        token = get_access_token()
        return token.client_id if token else "unknown"
    except Exception:
        return "unknown"


@mcp.tool(
    name="sheets_list",
    annotations=ToolAnnotations(
        title="List Google Sheets",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def sheets_list(params: SheetsListInput) -> list[TextContent]:
    """List the user's Google Sheets, optionally filtered by name."""
    if denied := await _check_sheets_rate_limit():
        return denied
    try:
        token = await get_google_token()
        async with GoogleSheetsClient(token) as client:
            files = await client.list_spreadsheets(
                query=params.query, max_results=params.max_results
            )
    except Exception as e:
        return [TextContent(type="text", text=_error_message(e))]

    if not files:
        msg = "No spreadsheets found"
        if params.query:
            msg += f" matching '{params.query}'"
        msg += "."
        return [TextContent(type="text", text=msg)]

    return [
        TextContent(
            type="text",
            text=json.dumps(files, ensure_ascii=False),
        )
    ]


@mcp.tool(
    name="sheets_read",
    annotations=ToolAnnotations(
        title="Read Google Sheet",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def sheets_read(params: SheetsReadInput) -> list[TextContent]:
    """Read data from a Google Sheet and return it as JSON records.

    Returns a list of dicts where keys are column headers. The output is
    directly compatible with everyrow tools' input_json parameter.

    Example flow:
      data = sheets_read(spreadsheet_id="...") -> list[dict]
      everyrow_agent(input_json=data, task="Research each company")
      sheets_write(spreadsheet_id="...", data=enriched_results)
    """
    if denied := await _check_sheets_rate_limit():
        return denied
    try:
        token = await get_google_token()
        async with GoogleSheetsClient(token) as client:
            values = await client.read_range(
                params.spreadsheet_id, cell_range=params.range
            )
    except Exception as e:
        return [TextContent(type="text", text=_error_message(e))]

    records = values_to_records(values)

    if not records:
        return [
            TextContent(
                type="text",
                text="The sheet is empty or contains only headers (no data rows).",
            )
        ]

    return [
        TextContent(
            type="text",
            text=json.dumps(records, ensure_ascii=False),
        )
    ]


@mcp.tool(
    name="sheets_write",
    annotations=ToolAnnotations(
        title="Write to Google Sheet",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def sheets_write(params: SheetsWriteInput) -> list[TextContent]:
    """Write data to a Google Sheet.

    Accepts a list of dicts (JSON records). Keys become column headers.
    Only the specified range is affected — other cells are untouched.

    To add new columns next to existing data, set range to the first empty
    column (e.g. 'Sheet1!E1') and pass only the new columns. You do NOT
    need to rewrite the entire sheet.

    Use append=True to add rows after existing data instead of overwriting.
    """
    if denied := await _check_sheets_rate_limit():
        return denied
    try:
        token = await get_google_token()
        values = records_to_values(params.data)

        async with GoogleSheetsClient(token) as client:
            if params.append:
                result = await client.append_range(
                    params.spreadsheet_id, cell_range=params.range, values=values
                )
                updated_range = result.get("updates", {}).get(
                    "updatedRange", params.range
                )
                updated_rows = result.get("updates", {}).get(
                    "updatedRows", len(params.data)
                )
                logger.info(
                    "AUDIT sheets_write user=%s spreadsheet=%s rows=%s append=true",
                    _audit_user_id(),
                    params.spreadsheet_id,
                    updated_rows,
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Appended {updated_rows} rows to {updated_range}.",
                    )
                ]
            else:
                # Pre-check: warn if the target range already has data
                if not params.confirm_overwrite:
                    existing = await client.read_range(
                        params.spreadsheet_id, cell_range=params.range
                    )
                    if existing:
                        existing_rows = len(existing)
                        return [
                            TextContent(
                                type="text",
                                text=f"The range '{params.range}' already contains {existing_rows} rows "
                                f"(including headers). Writing will overwrite this data. "
                                f"To proceed, call again with confirm_overwrite=True, "
                                f"or use append=True to add rows after existing data.",
                            )
                        ]

                result = await client.write_range(
                    params.spreadsheet_id, cell_range=params.range, values=values
                )
                updated_range = result.get("updatedRange", params.range)
                updated_rows = result.get("updatedRows", len(params.data) + 1)
                logger.info(
                    "AUDIT sheets_write user=%s spreadsheet=%s rows=%s append=false",
                    _audit_user_id(),
                    params.spreadsheet_id,
                    updated_rows,
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Wrote {updated_rows} rows (including header) to {updated_range}.",
                    )
                ]
    except Exception as e:
        return [TextContent(type="text", text=_error_message(e))]


@mcp.tool(
    name="sheets_create",
    annotations=ToolAnnotations(
        title="Create Google Sheet",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def sheets_create(params: SheetsCreateInput) -> list[TextContent]:
    """Create a new Google Sheet, optionally populated with data.

    Returns the spreadsheet ID and URL.
    """
    if denied := await _check_sheets_rate_limit():
        return denied
    try:
        token = await get_google_token()

        async with GoogleSheetsClient(token) as client:
            # Duplicate title guard
            existing = await client.list_spreadsheets(
                query=params.title, max_results=50
            )
            for f in existing:
                if f.get("name") == params.title:
                    return [
                        TextContent(
                            type="text",
                            text=f"A spreadsheet named '{params.title}' already exists "
                            f"(id: {f['id']}). Pick a different title to avoid "
                            f"creating a duplicate.",
                        )
                    ]

            metadata = await client.create_spreadsheet(params.title)
            spreadsheet_id = metadata["spreadsheetId"]
            url = metadata.get(
                "spreadsheetUrl",
                f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
            )

            # Optionally populate with initial data
            if params.data:
                values = records_to_values(params.data)
                await client.write_range(spreadsheet_id, "Sheet1", values)
    except Exception as e:
        return [TextContent(type="text", text=_error_message(e))]

    logger.info(
        "AUDIT sheets_create user=%s spreadsheet=%s rows=%s",
        _audit_user_id(),
        spreadsheet_id,
        len(params.data) if params.data else 0,
    )

    result = {
        "spreadsheet_id": spreadsheet_id,
        "url": url,
        "title": params.title,
    }
    if params.data:
        result["rows_written"] = len(params.data)

    return [
        TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False),
        )
    ]


@mcp.tool(
    name="sheets_info",
    annotations=ToolAnnotations(
        title="Get Google Sheet Info",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def sheets_info(params: SheetsInfoInput) -> list[TextContent]:
    """Get metadata about a Google Sheet: title, sheet names, and dimensions."""
    if denied := await _check_sheets_rate_limit():
        return denied
    try:
        token = await get_google_token()

        async with GoogleSheetsClient(token) as client:
            metadata = await client.get_spreadsheet_metadata(params.spreadsheet_id)
    except Exception as e:
        return [TextContent(type="text", text=_error_message(e))]

    title = metadata.get("properties", {}).get("title", "Unknown")
    sheets = []
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        grid = props.get("gridProperties", {})
        sheets.append(
            {
                "name": props.get("title", ""),
                "index": props.get("index", 0),
                "rows": grid.get("rowCount", 0),
                "columns": grid.get("columnCount", 0),
            }
        )

    result = {
        "spreadsheet_id": params.spreadsheet_id,
        "title": title,
        "url": f"https://docs.google.com/spreadsheets/d/{params.spreadsheet_id}",
        "sheets": sheets,
    }

    return [
        TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False),
        )
    ]

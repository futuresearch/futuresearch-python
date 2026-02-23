"""Google Sheets MCP tools for the everyrow MCP server.

Provides 5 tools: sheets_list, sheets_read, sheets_write, sheets_create, sheets_info.
All tools use the existing FastMCP instance from app.py.
"""

from __future__ import annotations

import json
import logging

from mcp.types import TextContent, ToolAnnotations

from everyrow_mcp.app import mcp
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
    token = await get_google_token()
    async with GoogleSheetsClient(token) as client:
        files = await client.list_spreadsheets(
            query=params.query, max_results=params.max_results
        )

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
    token = await get_google_token()
    async with GoogleSheetsClient(token) as client:
        values = await client.read_range(params.spreadsheet_id, params.range)

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
        destructiveHint=False,
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
    token = await get_google_token()
    values = records_to_values(params.data)

    async with GoogleSheetsClient(token) as client:
        if params.append:
            result = await client.append_range(
                params.spreadsheet_id, params.range, values
            )
            updated_range = result.get("updates", {}).get("updatedRange", params.range)
            updated_rows = result.get("updates", {}).get(
                "updatedRows", len(params.data)
            )
            return [
                TextContent(
                    type="text",
                    text=f"Appended {updated_rows} rows to {updated_range}.",
                )
            ]
        else:
            result = await client.write_range(
                params.spreadsheet_id, params.range, values
            )
            updated_range = result.get("updatedRange", params.range)
            updated_rows = result.get("updatedRows", len(params.data) + 1)
            return [
                TextContent(
                    type="text",
                    text=f"Wrote {updated_rows} rows (including header) to {updated_range}.",
                )
            ]


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
    token = await get_google_token()

    async with GoogleSheetsClient(token) as client:
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
    token = await get_google_token()

    async with GoogleSheetsClient(token) as client:
        metadata = await client.get_spreadsheet_metadata(params.spreadsheet_id)

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

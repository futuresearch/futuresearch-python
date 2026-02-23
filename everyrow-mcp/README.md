# everyrow MCP Server

MCP (Model Context Protocol) server for [everyrow](https://everyrow.io): agent ops at spreadsheet scale.

This server exposes everyrow's 5 core operations as MCP tools, allowing LLM applications to screen, rank, dedupe, merge, and run agents on CSV files.

**All tools operate on local CSV files.** Provide absolute file paths as input, and transformed results are written to new CSV files at your specified output path.

## Installation

The server requires an everyrow API key. Get one at [everyrow.io/api-key](https://everyrow.io/api-key) ($20 free credit).

### Claude Desktop

Download the latest `.mcpb` bundle from the [GitHub Releases](https://github.com/futuresearch/everyrow-sdk/releases) page and double-click to install in Claude Desktop. You'll be prompted to enter your everyrow API key during setup. After installing the bundle, you can use everyrow from Chat, Cowork and Code within Claude Desktop.

### Cursor
Set the environment variable in your terminal shell before opening cursor. You may need to re-open cursor from your shell after this. Alternatively, hardcode the api key within cursor settings instead of the hard-coded `${env:EVERYROW_API_KEY}`
```bash
export EVERYROW_API_KEY=your_key_here
```

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](cursor://anysphere.cursor-deeplink/mcp/install?name=everyrow&config=eyJlbnYiOnsiRVZFUllST1dfQVBJX0tFWSI6IiR7ZW52OkVWRVJZUk9XX0FQSV9LRVl9In0sImNvbW1hbmQiOiJ1dnggZXZlcnlyb3ctbWNwIn0%3D)

### Manual Config

Either set the API key in your shell environment as mentioned above, or hardcode it directly in the config below. Environment variable interpolation may differ between MCP clients.

```bash
export EVERYROW_API_KEY=your_key_here
```

Add this to your MCP config. If you have [uv](https://docs.astral.sh/uv/) installed:

```json
{
  "mcpServers": {
    "everyrow": {
      "command": "uvx",
      "args": ["everyrow-mcp"],
      "env": {
        "EVERYROW_API_KEY": "${EVERYROW_API_KEY}"
      }
    }
  }
}
```

Alternatively, install with pip (ideally in a venv) and use `"command": "everyrow-mcp"` instead of uvx.

## Workflow

All operations follow an async pattern:

1. **Start** - Call an operation tool (e.g., `everyrow_agent`) to start a task. Returns immediately with a task ID and session URL.
2. **Monitor** - Call `everyrow_progress(task_id)` repeatedly to check status. The tool blocks ~12s to limit the polling rate.
3. **Retrieve** - Once complete, call `everyrow_results(task_id, output_path)` to save results to CSV.

## Available Tools

### everyrow_screen

Filter CSV rows based on criteria that require judgment.

```
Parameters:
- task: Natural language description of screening criteria
- input_csv: Absolute path to input CSV
- response_schema: (optional) JSON schema for custom response fields
```

Example: Filter job postings for "remote-friendly AND senior-level AND salary disclosed"

### everyrow_rank

Score and sort CSV rows based on qualitative criteria.

```
Parameters:
- task: Natural language instructions for scoring a single row
- input_csv: Absolute path to input CSV
- field_name: Name of the score field to add
- field_type: Type of the score field (float, int, str, bool)
- ascending_order: Sort direction (default: true)
- response_schema: (optional) JSON schema for custom response fields
```

Example: Rank leads by "likelihood to need data integration solutions"

### everyrow_dedupe

Remove duplicate rows using semantic equivalence.

```
Parameters:
- equivalence_relation: Natural language description of what makes rows duplicates
- input_csv: Absolute path to input CSV
```

Example: Dedupe contacts where "same person even with name abbreviations or career changes"

### everyrow_merge

Join two CSV files using intelligent entity matching (LEFT JOIN semantics).

```
Parameters:
- task: Natural language description of how to match rows
- left_csv: The table being enriched — all its rows are kept in the output
- right_csv: The lookup/reference table — its columns are appended to matches; unmatched left rows get nulls
- merge_on_left: (optional) Only set if you expect exact string matches on this column or want to draw agent attention to it. Fine to omit.
- merge_on_right: (optional) Only set if you expect exact string matches on this column or want to draw agent attention to it. Fine to omit.
- use_web_search: (optional) "auto" (default), "yes", or "no"
- relationship_type: (optional) "many_to_one" (default) — multiple left rows can match one right row. "one_to_one" — only when both tables have unique entities of the same kind.
```

Example: Match software products (left, enriched) to parent companies (right, lookup): Photoshop -> Adobe

### everyrow_agent

Run web research agents on each row of a CSV.

```
Parameters:
- task: Natural language description of research task
- input_csv: Absolute path to input CSV
- response_schema: (optional) JSON schema for custom response fields
```

Example: "Find this company's latest funding round and lead investors"

### everyrow_progress

Check progress of a running task.

```
Parameters:
- task_id: The task ID returned by an operation tool
```

Blocks ~12s before returning status. Call repeatedly until task completes.

### everyrow_results

Retrieve and save results from a completed task.

```
Parameters:
- task_id: The task ID of the completed task
- output_path: Full absolute path to output CSV file (must end in .csv)
```

Only call after `everyrow_progress` reports status "completed".

## Development

```bash
cd everyrow-mcp
uv sync
uv run pytest
```
For MCP [registry publishing](https://modelcontextprotocol.info/tools/registry/publishing/#package-deployment):

mcp-name: io.github.futuresearch/everyrow-mcp


## License

MIT - See [LICENSE.txt](../LICENSE.txt)

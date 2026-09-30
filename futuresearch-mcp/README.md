# FutureSearch MCP Server

> Most users don't need to run the MCP server locally. Use the hosted remote server at `https://mcp.futuresearch.ai/mcp` — it authenticates via OAuth, no API key needed. See the [setup guide](https://futuresearch.ai/docs). The instructions below are for self-hosted or advanced use cases where an API key is required.

MCP (Model Context Protocol) server for [FutureSearch](https://futuresearch.ai): AI forecasting you can verify. FutureSearch turns questions about the future into probabilities, dates, and numbers, with accuracy verifiable via our public track record on stocks, prediction markets, public benchmarks, and forecasting tournaments ([markets.futuresearch.ai](https://markets.futuresearch.ai), [evals.futuresearch.ai](https://evals.futuresearch.ai)).

This server lets an assistant forecast: the probability, date or number for a question about the future, and the outcomes of decisions, yours or anyone else's. It also runs web research agents on one question or on every row of a table.

With the hosted server, pass rows inline as `data`, or reference an uploaded `artifact_id`. When you run the server yourself over stdio, tools also accept absolute paths to local CSV files and write results to a path you give.

A decision, as an MCP call: one row per outcome, a column listing the options, and what the forecaster cannot look up in `context`.

```json
{
  "tool": "futuresearch_decision",
  "arguments": {
    "data": [
      {
        "question": "How many sitting parliamentarians will be listed on ControlAI's campaign statement on December 31, 2028?",
        "grant": ["$0 (no grant)", "$250k", "$1M"]
      }
    ],
    "alternatives_field": "grant",
    "forecast_type": "numeric",
    "output_field": "parliamentarians",
    "units": "parliamentarians",
    "context": "We are a family foundation deciding this quarter how much to give ControlAI. The gift would be unrestricted and announced publicly, and no other funder is waiting on our decision."
  }
}
```

## Installation

The server requires a FutureSearch API key. Get one at [futuresearch.ai/app/api-key](https://futuresearch.ai/app/api-key) ($20 free credit).

### Claude Desktop

Download the latest `.mcpb` bundle from the [GitHub Releases](https://github.com/futuresearch/futuresearch-python/releases) page and double-click to install in Claude Desktop. You'll be prompted to enter your FutureSearch API key during setup. After installing the bundle, you can use FutureSearch from Chat, Cowork and Code within Claude Desktop.

### Cursor
Set the environment variable in your terminal shell before opening cursor. You may need to re-open cursor from your shell after this. Alternatively, hardcode the api key within cursor settings instead of the hard-coded `${env:FUTURESEARCH_API_KEY}`
```bash
export FUTURESEARCH_API_KEY=your_key_here
```

### Manual Config

Either set the API key in your shell environment as mentioned above, or hardcode it directly in the config below. Environment variable interpolation may differ between MCP clients.

```bash
export FUTURESEARCH_API_KEY=your_key_here
```

Add this to your MCP config. If you have [uv](https://docs.astral.sh/uv/) installed:

```json
{
  "mcpServers": {
    "futuresearch": {
      "command": "uvx",
      "args": ["futuresearch-mcp"],
      "env": {
        "FUTURESEARCH_API_KEY": "${FUTURESEARCH_API_KEY}"
      }
    }
  }
}
```

Alternatively, install with pip (ideally in a venv) and use `"command": "futuresearch-mcp"` instead of uvx.

## Workflow

All operations follow an async pattern:

1. **Start** - Call an operation tool (e.g., `futuresearch_agent`) to start a task. Returns immediately with a task ID.
2. **Monitor** - Call `futuresearch_progress(task_id)` repeatedly to check status. The tool blocks ~12s to limit the polling rate.
3. **Retrieve** - Once complete, call `futuresearch_results(task_id, output_path)` to save results to CSV.

## Available Tools

### futuresearch_forecast

Forecast questions about the future. Five modes: binary probabilities, numeric
percentiles, date percentiles, categorical (one probability per listed outcome),
and thresholded (one probability per listed threshold condition).

```
Parameters:
- forecast_type: "binary", "numeric", "date", "categorical", or "thresholded"
- context: (optional) What is true for the whole call: facts about who is deciding and their situation, and any instructions that apply to every row.
- effort_level: (optional) "low" or "high" (default; required for categorical/thresholded)
- output_field: Name of the forecast quantity (required for numeric/date)
- units: Units of the forecast quantity (required for numeric)
- categories_field: Column with each row's outcomes as a JSON array of strings (required for categorical)
- thresholds_field: Column with each row's threshold conditions as a JSON array (required for thresholded)
```

Example: "Will the US Federal Reserve cut rates before July 2027?"

### futuresearch_decision

Forecast the outcomes of a decision: the same outcome under each option, e.g. "if we fund this at $0, $300k or $2M, when will it ship?". The decision can be the user's or anyone else's: a company, a regulator, a government. Use this rather than `futuresearch_forecast` with a `condition` whenever the "if" is something someone decides.

The input needs a `question` (one outcome per row) and a column listing that row's options. When the decision is the user's own, put what you already know about them in `context`: their size, budget and timeline, what they have tried, what happens if they do nothing. The forecaster cannot look any of that up.

```
Parameters:
- data: Inline data as a list of row objects
- artifact_id: Alternatively, an artifact ID from a previous upload
- alternatives_field: Name of the column holding each row's alternatives as a JSON array
- forecast_type: "binary" (default), "numeric", or "date": the outcome type forecast under each alternative
- output_field: Name of the quantity being forecast (required for numeric and date)
- units: Units for the outcome (required for numeric)
- context: (optional) What is true for the whole call: facts about who is deciding and their situation, and any instructions that apply to every row.
- intervention: (optional) Intervention assumptions
```

Provide either `data` or `artifact_id`, not both.

Example: the decision call at the top of this README.

### futuresearch_multi_agent

Deep parallel research: deploy a team of direction agents per row exploring different angles, then synthesize. Use when completeness or depth matters more than per-row cost, e.g. enumerating "all AI startups in Europe", or answers that benefit from parallel investigation across distinct sources, geographies, or methodologies.

```
Parameters:
- task: What to research per row.
- directions: (optional) Up to 6 explicit research angles. Each should be a detailed, self-contained brief, not a short title. Auto-generated from task if omitted.
- response_schema: (optional) Output structure for the synthesized result. Defaults to {"answer": string}.
- effort_level: (optional) "low" (3 agents per row), "medium" (4, default), "high" (2 frontier agents, deeper but slower).
```

### futuresearch_agent

Run web research agents on each row of a CSV.

```
Parameters:
- task: Natural language description of research task
- input_csv: Absolute path to input CSV
- response_schema: (optional) JSON schema for custom response fields
```

Example: "Find this company's latest funding round and lead investors"

### futuresearch_browse_lists

Browse available reference lists of well-known entities (S&P 500, FTSE 100, countries, universities, etc.).

```
Parameters:
- search: (optional) Search term to match list names
- category: (optional) Filter by category (e.g. "Finance", "Geography")
```

### futuresearch_use_list

Import a reference list into your session and make it available via artifact_id for other futuresearch tools.

```
Parameters:
- artifact_id: artifact_id from futuresearch_browse_lists results
```

### futuresearch_upload_data

Upload data from a URL or local file. Returns an artifact_id for use in processing tools.

```
Parameters:
- source: HTTP(S) URL (Google Sheets supported) or local CSV path (stdio mode only)
- session_id / session_name: (optional)
```

### futuresearch_progress

Check progress of a running task.

```
Parameters:
- task_id: The task ID returned by an operation tool
```

Blocks ~12s before returning status. Call repeatedly until task completes.

### futuresearch_results

Retrieve and save results from a completed task.

```
Parameters:
- task_id: The task ID of the completed task
- output_path: Full absolute path to output CSV file (must end in .csv)
```

Only call after `futuresearch_progress` reports status "completed".

### futuresearch_cancel

Cancel a running task.

```
Parameters:
- task_id: Task ID to cancel
```

### Deprecated tools

`futuresearch_rank`, `futuresearch_classify`, `futuresearch_merge` and `futuresearch_dedupe` are deprecated and will be removed. They still work for now.

## Development

```bash
cd futuresearch-mcp
uv sync
uv run pytest
```
For MCP [registry publishing](https://modelcontextprotocol.info/tools/registry/publishing/#package-deployment):

mcp-name: io.github.futuresearch/futuresearch-mcp


## License

MIT - See [LICENSE.txt](../LICENSE.txt)

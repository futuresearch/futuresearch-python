---
title: MCP Server
description: Reference for all everyrow MCP server tools — async operations with progress polling and result retrieval.
---

# MCP Server Reference

The everyrow MCP server exposes 15 tools for AI-powered data processing. These tools are called directly by Claude, Codex CLI, and other MCP clients — no Python code is needed.

All operations use an async pattern: submit the task, poll for progress, then retrieve results. This allows long-running operations (1–10+ minutes) to work reliably with MCP clients.

## Setup

### Claude.ai and Claude Desktop

1. Go to **Settings → Connectors → Add custom connector** and enter the remote MCP URL:

```
https://mcp.everyrow.io/mcp
```

2. *(Optional but recommended)* Whitelist the everyrow upload URL so Claude can upload datasets straight from its sandbox — the data doesn't need to pass through the conversation context, saving tokens and improving reliability:

   **Settings → Capabilities → Code execution and file creation → Additional allowed domains** → add `mcp.everyrow.io`

### Claude Code

**Option A: Plugin install (recommended)**

```bash
claude plugin marketplace add futuresearch/everyrow-sdk
claude plugin install everyrow@futuresearch
```

**Option B: Remote HTTP MCP**

```bash
claude mcp add everyrow --scope project --transport http https://mcp.everyrow.io/mcp
```

Then start Claude Code and authenticate:

1. Run `claude`
2. Type `\mcp`, select **everyrow**, and complete the OAuth flow
3. Test with: *"check my everyrow balance"*

## Authentication

**Remote MCP (Claude.ai, Claude Desktop, Claude Code HTTP):** OAuth 2.0 via Google. Authentication is handled automatically by the MCP client — no API keys or manual setup required. You'll be prompted to sign in with your Google account on first use.

**Claude Code plugin (stdio):** Uses an API key. Generate yours at [everyrow.io/api-key](https://everyrow.io/api-key) and paste it when prompted during plugin setup.

## Operation Tools

### everyrow_screen

Filter rows in a CSV based on criteria that require judgment.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Screening criteria. Rows that meet the criteria pass. |
| `input_csv` | string | Yes | Absolute path to input CSV. |
| `response_schema` | object | No | JSON schema for custom fields. Default: `{"type": "object", "properties": {"passes": {"type": "boolean"}}}`. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_rank

Score and sort rows by qualitative criteria.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | What makes a row score higher or lower. |
| `input_csv` | string | Yes | Absolute path to input CSV. |
| `field_name` | string | Yes | Column name for the score. |
| `field_type` | string | No | Score type: `float` (default), `int`, `str`, `bool`. |
| `ascending_order` | bool | No | `true` = lowest first (default). |
| `response_schema` | object | No | JSON schema for additional fields. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_dedupe

Remove semantic duplicates.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `equivalence_relation` | string | Yes | What makes two rows duplicates. |
| `input_csv` | string | Yes | Absolute path to input CSV. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_merge

Join two CSVs using intelligent entity matching (LEFT JOIN semantics).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | How to match rows between tables. |
| `left_csv` | string | Yes | The table being enriched — all its rows are kept in the output. |
| `right_csv` | string | Yes | The lookup/reference table — its columns are appended to matches; unmatched left rows get nulls. |
| `merge_on_left` | string | No | Only set if you expect exact string matches on this column or want to draw agent attention to it. Fine to omit. |
| `merge_on_right` | string | No | Only set if you expect exact string matches on this column or want to draw agent attention to it. Fine to omit. |
| `relationship_type` | string | No | `many_to_one` (default) — multiple left rows can match one right row. `one_to_one` — unique matching between left and right rows. `one_to_many` — one left row can match multiple right rows. `many_to_many` — multiple left rows can match multiple right rows. For `one_to_many` and `many_to_many`, multiple matches are joined with `" \| "` in each added column. |
| `use_web_search` | string | No | `auto` (default), `yes`, or `no`. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_classify

Classify each row into one of the provided categories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Classification instructions. |
| `categories` | list[string] | Yes | Allowed categories (minimum 2). Each row is assigned exactly one. |
| `classification_field` | string | No | Output column name (default: `"classification"`). |
| `include_reasoning` | boolean | No | Include a reasoning column (default: false). |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_forecast

Forecast the probability of binary questions.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context` | string | No | Optional batch-level context for all questions. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_agent

Run web research agents on each row.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task for the agent to perform on each row. |
| `input_csv` | string | Yes | Absolute path to input CSV. |
| `response_schema` | object | No | JSON schema for structured output. Default: `{"type": "object", "properties": {"answer": {"type": "string"}}}`. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_single_agent

Run a single web research agent on a question, without a CSV. Use this when you want to research one thing — the agent can search the web, read pages, and return structured results.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Natural language task for the agent to perform. |
| `input_data` | object | No | Optional context as key-value pairs (e.g. `{"company": "Acme", "url": "acme.com"}`). |
| `response_schema` | object | No | JSON schema for structured output. Default: `{"type": "object", "properties": {"answer": {"type": "string"}}}`. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

## Progress and Results Tools

### everyrow_progress

Check progress of a running task. **Blocks for a few seconds** before returning.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | Yes | The task ID from an operation tool. |

Returns status text with completion counts and elapsed time. Instructs the agent to call again immediately until the task completes or fails.

### everyrow_results

Retrieve results from a completed task and save to CSV.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | Yes | The task ID of the completed task. |
| `output_path` | string | Yes | Directory or full .csv path for output. |

Returns confirmation with row count and file path.

### everyrow_cancel

Cancel a running task. Use when the user wants to stop a task that is currently processing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | Yes | The task ID to cancel. |

Returns a confirmation message. If the task has already finished, returns an error with its current state.

### everyrow_list_sessions

List all sessions owned by the authenticated user. Returns session names, IDs, timestamps, and dashboard URLs. No parameters required.

Returns a formatted list of sessions with links to the web dashboard.

### everyrow_upload_data

Upload data from a URL or local file. Returns an `artifact_id` for use in processing tools.

Use this to ingest data before calling any operation tool. Supported sources:

- HTTP(S) URLs (including Google Sheets — auto-converted to CSV export)
- Local CSV file paths (stdio/local mode only — not available over HTTP)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Data source: HTTP(S) URL or absolute local file path. Google Sheets and Drive URLs are supported. |
| `session_id` | string | No | Session ID (UUID) to resume. Mutually exclusive with `session_name`. |
| `session_name` | string | No | Human-readable name for a new session. Mutually exclusive with `session_id`. |

Returns `artifact_id` (UUID), `session_id`, row count, and column names.

### everyrow_request_upload_url

Request a presigned URL to upload a local CSV file. This is the recommended way to ingest local files when using the remote HTTP MCP server.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Name of the file to upload (must end in `.csv`). |

Returns a presigned upload URL, upload ID, expiration time, max file size, and a ready-to-execute `curl` command. After uploading, use the returned `artifact_id` in any processing tool.

### everyrow_balance

Check the current billing balance for the authenticated user. No parameters required.

Returns the account balance in dollars.

## Workflow

```
1. everyrow_agent(task, input_csv)
   → Returns task_id + session_url (~0.6s)

2. everyrow_progress(task_id)
   → Blocks 12s, returns "Running: 5/50 complete, 8 running (15s elapsed)"
   → Response says "call everyrow_progress again immediately"

3. everyrow_progress(task_id)  (repeat)
   → "Running: 23/50 complete, 5 running (45s elapsed)"

4. everyrow_progress(task_id)  (final)
   → "Completed: 49 succeeded, 1 failed (142s total)"

5. everyrow_results(task_id, output_path)
   → "Saved 50 rows to /path/to/agent_companies.csv"
```

The agent handles this loop automatically. You don't need to intervene.

## Usage Examples

### Lead screening

> "Screen this list and keep only companies with >50 employees that raised Series A+"

Uses `everyrow_screen` to filter a CSV of companies. Each row is evaluated by a web research agent that checks employee count and funding stage. Rows that don't meet the criteria are filtered out.

### Web research

> "For each competitor, find their pricing model, employee count, and latest funding"

Uses `everyrow_agent` with a custom `response_schema` to extract structured fields for each row. The agent searches the web for each company and returns the requested data.

### Deduplication

> "Dedupe this CRM export — merge rows referring to the same person"

Uses `everyrow_dedupe` to identify and remove semantic duplicates. Rows are compared beyond exact string matching — the agent recognizes that "J. Smith at Acme" and "John Smith, Acme Corp" are the same person.

### Ranking

> "Rank these nonprofits by climate impact in Sub-Saharan Africa"

Uses `everyrow_rank` to score and sort rows by a qualitative criterion. Each row is researched and scored, then the results are sorted.

## Custom Response Schemas

All tools that accept `response_schema` take a JSON schema object:

```json
{
  "type": "object",
  "properties": {
    "annual_revenue": {
      "type": "integer",
      "description": "Annual revenue in USD"
    },
    "employee_count": {
      "type": "integer",
      "description": "Number of employees"
    }
  },
  "required": ["annual_revenue"]
}
```

The top-level `type` must be `object`, and the `properties` must be non-empty.
The valid field types are: `string`, `integer`, `number`, `boolean`, `array`, `object`.

## Plugin

The Claude Code plugin (`.claude-plugin/plugin.json`) bundles:

1. MCP server, with all tools above
2. Hooks, such as stop guard (prevents ending turn during operations), results notification (macOS), session cleanup
3. Skill, to guide agents with quick SDK code generation for the Python SDK path

Install with:
```bash
claude plugin marketplace add futuresearch/everyrow-sdk
claude plugin install everyrow@futuresearch
```

See [Progress Monitoring](/docs/progress-monitoring) for status line setup and hook details.

## Troubleshooting

### Auth flow not completing

If the OAuth sign-in window opens but authentication doesn't complete:

- Ensure pop-ups are not blocked in your browser
- Try closing and reopening the MCP connection
- For Claude Code HTTP mode, run `\mcp` and re-authenticate from the MCP panel

### Task stuck in progress

If `everyrow_progress` keeps returning a running state for an extended period:

- Large datasets (1000+ rows) can take 10+ minutes — this is normal
- Use `everyrow_cancel` to stop the task and retry with a smaller dataset
- Check the session dashboard at the `session_url` for real-time status

### Results appear empty

If `everyrow_results` returns fewer rows than expected:

- Some rows may have failed processing — check the session dashboard for error details
- Ensure the input CSV was well-formed (proper headers, no encoding issues)
- Retry failed rows by running the same operation on the filtered subset

### Token budget exceeded

If you get a token budget error:

- Results are automatically paginated — call `everyrow_results` again to get the next page
- Use a custom `response_schema` with fewer fields to reduce output size
- Split large datasets into smaller batches

## Privacy & Support

- **Privacy Policy:** [futuresearch.ai/privacy](https://futuresearch.ai/privacy/)
- **Terms of Service:** [futuresearch.ai/terms](https://futuresearch.ai/terms/)
- **Support:** [support@futuresearch.ai](mailto:support@futuresearch.ai)

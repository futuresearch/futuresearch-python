---
title: MCP Server
description: Reference for all everyrow MCP server tools — async operations with progress polling and result retrieval.
---

# MCP Server Reference

The everyrow MCP server exposes tools for AI-powered data processing. These tools are called directly by Claude Code, Codex CLI, and other MCP clients — no Python code is needed.

All operations use an async pattern: submit the task, poll for progress, then retrieve results. This allows long-running operations (1–10+ minutes) to work reliably with MCP clients.

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
| `relationship_type` | string | No | `many_to_one` (default) — multiple left rows can match one right row. `one_to_one` — only when both tables have unique entities of the same kind. |
| `use_web_search` | string | No | `auto` (default), `yes`, or `no`. |

Returns `task_id` and `session_url`. Call `everyrow_progress` to monitor.

### everyrow_agent

Run web research agents on each row.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task for the agent to perform on each row. |
| `input_csv` | string | Yes | Absolute path to input CSV. |
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

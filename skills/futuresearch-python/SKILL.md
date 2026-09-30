---
name: futuresearch-python
description: Use when the user wants a FutureSearch forecast: the probability, date or number for a question about the future, or the outcomes of a decision they, their company, or someone else is facing (pricing, hiring, funding, launch timing, policy). Also covers web research across the rows of a table.
---

# FutureSearch Python SDK

FutureSearch forecasts questions about the future, including the outcomes of decisions. Use this skill when writing Python code or calling MCP tools that need to:

**Operations:**
- Forecast the outcomes of a decision, yours or someone else's: the same outcome under each option
- Forecast probabilities, numbers, dates, and categories for questions about the future
- Research one question with a team of parallel agents
- Run AI agents over dataframe rows

> **Documentation**: For detailed guides, case studies, and API reference, see:
> - Docs site: [futuresearch.ai/docs](https://futuresearch.ai/docs)
> - GitHub: [github.com/futuresearch/futuresearch-python](https://github.com/futuresearch/futuresearch-python)

## Installation

### Python SDK

```bash
pip install futuresearch
```

### MCP Server (for Claude Code, Claude Desktop, Cursor, etc.)

If an MCP server is available (`futuresearch_forecast`, `futuresearch_decision`, etc. tools), you can use it directly without writing Python code. The MCP server operates on uploaded data (via artifact IDs or inline JSON).

To install the MCP server, add to your MCP config:

```json
{
  "mcpServers": {
    "futuresearch": {
      "type": "http",
      "url": "https://mcp.futuresearch.ai/mcp"
    }
  }
}
```

Config file locations:
- **Claude Code**: `~/.claude.json` (user) or `.mcp.json` (project)
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: `~/.cursor/mcp.json`

## When to Use SDK vs MCP

**Use MCP tools** when:
- Quick one-off operations on CSV files
- User wants direct results without writing code
- Simple lookups and enrichments

**Use Python SDK** when:
- Complex multi-step workflows (research → forecast → decision)
- Custom data transformations
- Integration with existing Python scripts
- Full control over execution and intermediate results

---

# MCP Server Tools

If you have the FutureSearch MCP server configured, these tools are available. All data processing tools accept input via `artifact_id` (from upload_data or request_upload_url) or `data` (inline JSON rows). Provide exactly one.

## Core Operations

### futuresearch_forecast
Forecast questions about the future. Five outcome types: binary probabilities,
numeric percentiles, date percentiles, categorical (one probability per listed
outcome), and thresholded (one probability per listed threshold condition). Any
of them can be made conditional on a stated intervention by supplying a condition
(see "Conditional forecasting" below).
```
Parameters:
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects (must include "question" column)
- forecast_type: "binary", "numeric", "date", "categorical", or "thresholded" (always the OUTCOME type)
- context: (optional) What is true for the whole call: facts about who is deciding
  and their situation, and any instructions that apply to every row
- effort_level: (optional) "low" or "high" (default; required for categorical/thresholded and for any conditional forecast)
- batch_size: (optional) Rows researched together per forecasting agent — see "Batching related questions" below
- output_field: Name of the forecast quantity (required for numeric/date)
- units: Units of the forecast quantity (required for numeric)
- categories_field: Column with each row's outcomes as a JSON array of strings (required for categorical)
- thresholds_field: Column with each row's threshold conditions as a JSON array (required for thresholded)
- condition: (optional) Single shared condition string mapped over every row, making the forecast conditional on it
- condition_field: (optional) Name of a per-row column holding each row's own condition (mutually exclusive with condition)
- session_id / session_name: (optional)
```

**Batching related questions.** Decide by research overlap, not row count. When
the rows are variants of one subject — the same entity, product, market, or
scenario asked across several horizons, metrics, or cases (e.g. three games x
{first-month revenue, year-one revenue}) — the research is shared, so set
`batch_size` to the number of rows (max 8 at high effort): the forecasting
agents research the batch once and still forecast and refine each row
independently, at roughly half the cost of unbatched research. When the rows are
independent subjects (six unrelated geopolitics questions), leave `batch_size`
unset so each row earns its own research pass — batching unrelated rows saves
money but starves each question of research depth. For a mixed table, split it
and submit the related cluster batched and the rest per-row. At high effort,
batching requires a plain unconditional binary/numeric/date forecast
(categorical/thresholded, decision, and conditional forecasts always run
per-row). Tell the user which mode you chose and roughly what it changes in
cost, so an expensive per-row run is a choice they saw, not a surprise.

### futuresearch_decision
Forecast the outcomes of a decision somebody is facing: the user's, their company's, a competitor's, a regulator's, a government's. Each option gets the same outcome forecast. Use this whenever the "if" is something someone chooses to do, rather than something that happens to the world. Include not acting as an option unless it is ruled out, and prefer a date or a quantity to a cutoff: ask "when does it ship" rather than "does it ship by June".

The outcome under each alternative can be a probability, a number, or a date
(`forecast_type` `binary` / `numeric` / `date`, as in futuresearch_forecast).
```
Parameters:
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects (must include "question" column)
- alternatives_field: (required) Column holding each row's mutually exclusive
  alternatives as a JSON array of 2-50 numbers or strings
- forecast_type: (optional) "binary" (default), "numeric", or "date" (the OUTCOME
  type forecast under each alternative)
- output_field: Name of the forecast quantity (required for numeric/date)
- units: Units of the forecast quantity (required for numeric)
- context: (optional) What is true for the whole call: facts about who is deciding
  and their situation, and any instructions that apply to every row
- intervention: (optional) What executing an alternative means (publicity, timing,
  how the world responds). Replaces the default assumptions wholesale, so state
  the full set. Tell the user which assumptions were active when presenting results.
- session_id / session_name: (optional)
```
The output always contains a `rationale`. Additionally, for a binary outcome,
there is a `probabilities` field, which is a JSON object mapping each alternative to
the outcome's probability. For a numeric or date outcome, the output contains a
`percentiles` field, which is a JSON object mapping each alternative to its
`{p10, p25, p50, p75, p90}` record. The values across alternatives need not sum to
100 and need not be monotonic.

**Conditional forecasting.** Use a condition only when the premise is a state of the world nobody chooses: an election result, a price level, a far-off milestone. If the premise is a decision somebody is making, including a company's, a regulator's or a government's, use `futuresearch_decision` instead. Almost every "if we…" or "should we…" is a decision.

Conditionality is a modifier on any forecast type, not a type of its own: pick
`forecast_type` from the outcome as usual (`date` for "when will X", `numeric`
for "what will the return be", `binary` for "will X happen", etc.) and supply the
condition. Conditional forecasts are HIGH effort only. Each outputkeeps the type's normal columns and produces them a second time, suffixed
`_given_condition` (the world where the condition holds) and `_given_not_condition`
(where it does not), so the two branches reflect one coherent view of how the
condition bears on the outcome, plus a `rationale`.

Two mutually exclusive ways to supply the condition:

- **Shared condition** (`condition`): a single condition string applied to every
  row. Use it for a one-off question, or for the "ask the same conditional about
  each of these" case, where the user brings a list of entities and asks how one
  shared intervention moves each entity's outcome (e.g. *"for each company, what
  will its Q3 stock return be if Claude Fable launches worldwide before August?"*).
- **Per-row column** (`condition_field`): the name of an input column holding each
  row's own condition, for a sheet where rows carry distinct conditions.

### Giving the forecast facts about the user

The web cannot look up the user's situation, so you have to supply it. Put what you know about them in `context`, once: who is deciding, their size, money and timeline, what they have tried, what happens if they do nothing. Write plain dated facts. It applies to every row in the call, so do not repeat it per row. Ask the user for the two or three facts most likely to change the answer if you do not have them, and never pass in numbers from an earlier forecast.

If the options come back level, say so plainly: this decision does not move that outcome, and the rationale explains why. Do not re-run it hoping for a gap. Offer a nearer outcome instead, where the same decision may matter.

### futuresearch_multi_agent
Answer one question with a team of agents that each take a different angle, then
synthesize one structured result. Use it for a single deep question; use
futuresearch_agent when you have a table and want one agent per row.
```
Parameters:
- task: (required) Instructions for the multi-agent parallel research
- artifact_id / data: (optional) Omit or pass empty data for a standalone question
- directions: (optional) Up to 6 explicit research directions. Each must be a
  detailed, self-contained brief, not a short title. Auto-generated if omitted.
- response_schema: (optional) JSON schema for the synthesized response per row
- effort_level: (optional) "low" (3 agents) and "medium" (4, default) run fast;
  "high" (2 frontier agents) is deeper but slower
- return_table: (optional) MUST be true when the task asks for a list of items
  (e.g. "find 15 startups"). Pair with response_schema describing a single item.
- session_id / session_name: (optional)
```

### futuresearch_agent
Run web research agents on each row.
```
Parameters:
- task: (required) Natural language description of research task
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects
- response_schema: (optional) JSON schema for per-row agent response
- session_id: (optional) Session UUID to resume
- session_name: (optional) Name for a new session
```

### Deprecated: rank, classify, merge, dedupe

These still work and will be removed. For a label or a score per row use `agent_map` with a `response_schema`; for anything about the future use `forecast`.

## Data Management

### futuresearch_browse_lists
Browse available reference lists of well-known entities (S&P 500, FTSE 100, countries, universities, etc.).
```
Parameters:
- search: (optional) Search term to match list names
- category: (optional) Filter by category (e.g. "Finance", "Geography")
```

### futuresearch_use_list
Import a reference list into your session and save it as a CSV.
```
Parameters:
- artifact_id: (required) artifact_id from futuresearch_browse_lists results
```

### futuresearch_upload_data
Upload data from a URL or local file. Returns an artifact_id for use in processing tools.
```
Parameters:
- source: (required) HTTP(S) URL (Google Sheets supported) or local CSV path (stdio mode only)
- session_id / session_name: (optional)
```

### futuresearch_request_upload_url
Request a presigned URL to upload a local CSV file (HTTP mode only).
```
Parameters:
- filename: (required) Name of the file to upload (must end in .csv)
```
Steps: call this tool → execute the returned curl command → use the artifact_id from the response.

## Task Lifecycle

### futuresearch_progress
Check progress of a running task. Blocks briefly to limit polling rate.
```
Parameters:
- task_id: (required) Task ID returned by the operation tool
```
After receiving a status update, immediately call futuresearch_progress again unless the task is completed or failed.

### futuresearch_results
Retrieve results from a completed task.
```
Parameters:
- task_id: (required) Task ID of the completed task
- output_path: (stdio) Full path to output CSV (must end in .csv)
- offset: (http, optional) Row offset for pagination (default: 0)
- page_size: (http, optional) Number of rows to load into context (default: auto threshold based on row count)
```
Only call after futuresearch_progress reports status "completed".

### futuresearch_cancel
Cancel a running task.
```
Parameters:
- task_id: (required) Task ID to cancel
```

### futuresearch_status
Check task status and show a live progress widget that auto-updates by polling.
Only registered for widget-capable clients (HTTP mode), so it is not available
in stdio mode such as Claude Code. After calling it once, do NOT also call
futuresearch_progress: the widget polls on its own.
```
Parameters:
- task_id: (required) Task ID to display
```

### futuresearch_task_cost
Get the billed cost of a completed task, in dollars. Cost settles some time
after the task finishes, so this returns "pending" until it does.
```
Parameters:
- task_id: (required) Task ID to price
```

## Sessions & Account

### futuresearch_list_sessions
List sessions owned by the authenticated user (paginated).
```
Parameters:
- offset: (optional) Number of sessions to skip (default: 0)
- limit: (optional) Max sessions per page (default: 25, max: 1000)
```

### futuresearch_list_session_tasks
List all tasks in a session with their IDs, statuses, and types.
```
Parameters:
- session_id: (required) Session ID (UUID) to list tasks for
```

### futuresearch_balance
Check the current billing balance for the authenticated user.
```
No parameters.
```

---

# Python SDK Reference

## Results

All operations return a result object. The data is available as a pandas DataFrame in `result.data`:

```python
result = await forecast(...)
print(result.data.head())  # pandas DataFrame
```

## Operations

For quick one-off operations, sessions are created automatically.

### forecast - Predict probabilities

Produce probability estimates for binary questions:

```python
from futuresearch.ops import forecast

result = await forecast(
    input=DataFrame([
        {"question": "Will the US Federal Reserve cut rates by at least 25bp before July 1, 2027?",
         "resolution_criteria": "Resolves YES if the Fed announces at least one rate cut of 25bp or more."},
    ]),
    forecast_type="binary",
)
print(result.data[["question", "probability", "rationale"]])
```

Parameters: `input`, `forecast_type` (`"binary"` | `"numeric"` | `"date"` | `"categorical"` | `"thresholded"`), `effort_level`, `batch_size` (rows researched together — see "Batching related questions" under `futuresearch_forecast` above), `context`, `output_field` (required for numeric/date), `units` (required for numeric), `categories_field` (required for categorical), `thresholds_field` (required for thresholded), `condition` *or* `condition_field` (makes any type conditional), `session`

For **conditional** forecasts (P(B|A) and P(B|not A) for a condition A and outcome B), see "Conditional forecasting" under `futuresearch_forecast` above. Conditionality is a modifier on any `forecast_type`, not a type of its own: keep `forecast_type` describing the outcome B (taken from each row's `question`) and supply the condition A via `condition` (a single shared condition mapped over every row) or `condition_field` (a per-row condition column). The two are mutually exclusive.

Recommended input columns beyond `question`: `resolution_criteria`, `resolution_date`, `background`. For questions tied to a prediction market or forecasting platform (Polymarket, Kalshi, Metaculus, ...), also pass `market_creation_date` and `market_price` (with its as-of date), and copy resolution criteria verbatim from the platform — including fine print. Self-contained questions (e.g. "When will Anthropic IPO?") need none of these.

### decision - Outcome under each alternative

Forecast the outcomes of a decision somebody is facing: the user's, their company's, a competitor's, a regulator's, a government's. Each option gets the same outcome forecast. Use this whenever the "if" is something someone chooses to do, rather than something that happens to the world. Include not acting as an option unless it is ruled out, and prefer a date or a quantity to a cutoff: ask "when does it ship" rather than "does it ship by June".

The outcome under each alternative can be a probability, a number, or a date, set
by `forecast_type`, exactly as in `forecast`.

```python
import asyncio
from pandas import DataFrame
from futuresearch.ops import decision


async def main():
    result = await decision(
        input=DataFrame([
            {
                "question": "How many sitting parliamentarians will be listed on ControlAI's campaign statement on December 31, 2028?",
                "grant": ["$0 (no grant)", "$250k", "$1M"],
            },
        ]),
        context=(
            "We are a family foundation deciding this quarter how much to give ControlAI. "
            "The gift would be unrestricted and announced publicly, and no other funder is "
            "waiting on our decision."
        ),
        alternatives_field="grant",
        forecast_type="numeric",
        output_field="parliamentarians",
        units="parliamentarians",
    )
    print(result.data[["question", "percentiles", "rationale"]])


asyncio.run(main())
```

The output contains `rationale` plus a per-alternative outcome column:
- For binary forecasts, a `probabilities` field containing a JSON object mapping
  each alternative to the outcome's probability.
- For numeric and date forecasts, a `percentiles` field containing a JSON object
  mapping each alternative to its `{p10, p25, p50, p75, p90}` record).

Parameters: `input`, `alternatives_field` (required, keyword-only), `forecast_type`
(`"binary"` | `"numeric"` | `"date"`), `output_field` (required for numeric/date),
`units` (required for numeric), `context`, `intervention`, `session`

### multi_agent - A team of agents on one question

Several agents each take a different angle on one question, then synthesize a single
structured answer. Use it for a deep single question; use `agent_map` when you have a
table and want one agent per row.

```python
import pandas as pd
from futuresearch.ops import multi_agent

result = await multi_agent(
    task="Research the current state of formal verification for AI systems",
    input=pd.DataFrame(),  # empty input for a standalone question
)
print(result.data.head())
```

Set `return_list=True` when the task asks for a list of items ("find 15 startups"),
pairing it with a `response_schema` describing one item.

Parameters: `task`, `input`, `session`, `directions` (up to 6 detailed, self-contained
briefs), `effort_level` (`low` 3 agents, `medium` 4 agents default, `high` 2 frontier
agents), `response_schema`, `join_with_input`, `return_list`

### agent_map - Batch processing

Run an AI agent across multiple rows:

```python
from futuresearch.ops import agent_map
from pandas import DataFrame

result = await agent_map(
    task="Find this company's latest funding round and lead investors",
    input=DataFrame([
        {"company": "Anthropic"},
        {"company": "OpenAI"},
        {"company": "Mistral"},
    ]),
)
print(result.data.head())
```

**Effort levels** - control research thoroughness:

- `LOW`: Quick lookups, basic web searches
- `MEDIUM` (default): More thorough research, multiple sources
- `HIGH`: Deep research, cross-referencing sources

```python
from futuresearch.ops import agent_map
from futuresearch.task import EffortLevel

result = await agent_map(
    task="Comprehensive competitive analysis",
    input=competitors,
    effort_level=EffortLevel.HIGH,
)
```

Parameters: `task`, `input`, `effort_level`, `response_model`, `session`

### Deprecated: rank, classify, merge, dedupe

These still work and will be removed. For a label or a score per row use `agent_map` with a `response_model`; for anything about the future use `forecast`.

`single_agent` is deprecated on the same terms; calling it emits a
`DeprecationWarning`. Use `agent_map` (one task per row, optionally with
`return_table=True`) or `multi_agent` (parallel agents synthesized per row).
Both accept an empty input for a standalone task.

## Explicit Sessions

For multiple operations that should be grouped together, use an explicit session:

```python
from futuresearch import create_session

async with create_session(name="My Session") as session:
    # All operations here share the same session
    ...
```

## Async Operations

All operations have `_async` variants for background processing. These need an explicit session since the task persists beyond the function call:

```python
from pandas import DataFrame
from futuresearch import create_session
from futuresearch.ops import decision_async

async with create_session(name="Async Decision") as session:
    task = await decision_async(
        session=session,
        input=DataFrame([
            {
                "question": "How many sitting parliamentarians will be listed on ControlAI's campaign statement on December 31, 2028?",
                "grant": ["$0 (no grant)", "$250k", "$1M"],
            },
        ]),
        alternatives_field="grant",
        forecast_type="numeric",
        output_field="parliamentarians",
        units="parliamentarians",
    )
    print(f"Task ID: {task.task_id}")  # Print this! Useful if your script crashes.

    # Continue with other work...
    result = await task.await_result()
```

**Tip:** Print the task ID after submitting. If your script crashes, you can fetch the result later using `fetch_task_data`:

```python
from futuresearch import fetch_task_data

# Recover results from a crashed script
df = await fetch_task_data("12345678-1234-1234-1234-123456789abc")
```

## Long-Running Operations (MCP)

FutureSearch operations (forecast, decision, agent, multi_agent) take 1-10+ minutes.
All MCP tools use an async pattern:

1. Call the operation tool (e.g., `futuresearch_agent(...)`) to get a task_id
2. Call futuresearch_progress(task_id) — the tool handles pacing internally
3. After each status update, immediately call futuresearch_progress again
4. When status is "completed" or "failed", call futuresearch_results(task_id)

## Chaining Operations

Operations can be chained to build complete workflows. Each step's output feeds the next:

```python
from pandas import DataFrame
from futuresearch import create_session
from futuresearch.ops import decision, multi_agent

async with create_session(name="Grant Decision") as session:
    # 1. Find the options on the table
    researched = await multi_agent(
        session=session,
        task="What is ControlAI asking funders for, and at what grant sizes?",
        input=DataFrame(),  # empty input for a standalone question
    )

    # 2. Forecast the same outcome under each one
    forecasts = await decision(
        session=session,
        input=DataFrame([
            {
                "question": "How many sitting parliamentarians will be listed on ControlAI's campaign statement on December 31, 2028?",
                "grant": ["$0 (no grant)", "$250k", "$1M"],
            },
        ]),
        context=(
            "We are a family foundation deciding this quarter how much to give ControlAI. "
            "The gift would be unrestricted and announced publicly, and no other funder is "
            "waiting on our decision."
        ),
        alternatives_field="grant",
        forecast_type="numeric",
        output_field="parliamentarians",
        units="parliamentarians",
    )
    print(forecasts.data[["question", "percentiles", "rationale"]])
```

## Best Practices

FutureSearch operations have associated costs. To avoid re-running them unnecessarily:

- **Separate data processing from analysis**: Save FutureSearch results to a file (CSV, Parquet, etc.), then do analysis in a separate script. This way, if analysis code has bugs, you don't re-trigger the FutureSearch step.
- **Use intermediate checkpoints**: For multi-step pipelines, consider saving results after each FutureSearch operation.
    - You are able to chain multiple operations together without needing to download and re-upload intermediate results via the SDK. However for most control, implement each step as a dedicated job, possibly orchestrated by tools such as Apache Airflow or Prefect.
- **Test on a slice first**: Before running a large job, pass a few rows (e.g. `input=df.head(5)`) to check the task wording and output shape, then run the full table.

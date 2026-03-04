---
name: everyrow-sdk
description: Use when the user wants Claude to dispatch researchers to forecast, score, classify, or add to a dataset at scale.
---

# everyrow SDK

everyrow gives Claude a research team for your data. Use this skill when writing Python code that needs to:

> **Documentation**: For detailed guides, case studies, and API reference, see:
> - Docs site: [everyrow.io/docs](https://everyrow.io/docs)
> - GitHub: [github.com/futuresearch/everyrow-sdk](https://github.com/futuresearch/everyrow-sdk)

**Operations:**
- Classify rows into predefined categories
- Rank/score rows based on qualitative criteria
- Deduplicate data using semantic understanding
- Merge tables using AI-powered matching
- Screen/filter rows based on research-intensive criteria
- Forecast probabilities for binary questions
- Run AI agents over dataframe rows

## Installation

### Python SDK

```bash
pip install everyrow
```

### MCP Server (for Claude Code, Claude Desktop, Cursor, etc.)

If an MCP server is available (`everyrow_classify`, `everyrow_screen`, `everyrow_rank`, etc. tools), you can use it directly without writing Python code. The MCP server operates on uploaded data (via artifact IDs or inline JSON).

To install the MCP server, add to your MCP config:

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

Config file locations:
- **Claude Code**: `~/.claude.json` (user) or `.mcp.json` (project)
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: `~/.cursor/mcp.json`

## Configuration

First, check if everyrow is already connected via remote MCP. Run `\mcp` and look for `everyrow` in the list. If it's there, no API key is needed, the remote MCP server authenticates via OAuth with Google sign-in only.

If the user cannot use MCP for some reason, you may fall back to asking them to fetch an EVERYROW_API_KEY.

Prompt the user:

> everyrow requires an API key. Do you have one?
>
> - If yes, paste it here
> - If no, get one at https://everyrow.io/api-key and paste it back

Once the user provides the key, set it:

```bash
export EVERYROW_API_KEY=<their_key>
```

## When to Use SDK vs MCP

**Use MCP tools** when:
- Quick one-off operations on CSV files
- User wants direct results without writing code
- Simple lookups and enrichments

**Use Python SDK** when:
- Complex multi-step workflows (dedupe → merge → research)
- Custom data transformations
- Integration with existing Python scripts
- Full control over execution and intermediate results

---

# MCP Server Tools

If you have the everyrow MCP server configured, these 18 tools are available. All data processing tools accept input via `artifact_id` (from upload_data or request_upload_url) or `data` (inline JSON rows). Provide exactly one.

## Core Operations

### everyrow_agent
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

### everyrow_single_agent
Run a single research agent on one input (no CSV needed).
```
Parameters:
- task: (required) Natural language task for the agent
- input_data: (optional) Context as key-value pairs (e.g. {"company": "Acme"})
- response_schema: (optional) JSON schema for the agent response
- session_id: (optional) Session UUID to resume
- session_name: (optional) Name for a new session
```

### everyrow_rank
Score and sort rows based on qualitative criteria.
```
Parameters:
- task: (required) Natural language instructions for scoring a single row
- field_name: (required) Name of the score field to add
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects
- field_type: (optional) "float" (default), "int", "str", or "bool"
- ascending_order: (optional) Sort ascending (default: true)
- response_schema: (optional) JSON schema for the response model
- session_id / session_name: (optional)
```

### everyrow_screen
Filter rows based on criteria that require judgment.
```
Parameters:
- task: (required) Natural language screening criteria
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects
- response_schema: (optional) JSON schema; must include at least one boolean property for pass/fail
- session_id / session_name: (optional)
```

### everyrow_dedupe
Remove duplicate rows using semantic equivalence.
```
Parameters:
- equivalence_relation: (required) Natural language description of what makes rows duplicates
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects
- session_id / session_name: (optional)
```

### everyrow_merge
Join two tables using intelligent entity matching (LEFT JOIN semantics).
```
Parameters:
- task: (required) Natural language description of how to match rows
- left_artifact_id / left_data: (required, exactly one) Left table — the table being enriched (all rows kept)
- right_artifact_id / right_data: (required, exactly one) Right table — lookup/reference (columns appended to matches)
- merge_on_left: (optional) Only set if you expect exact string matches or want to draw agent attention to a column
- merge_on_right: (optional) Same as merge_on_left for right table
- relationship_type: (optional) "many_to_one" (default), "one_to_one", "one_to_many", "many_to_many"
- use_web_search: (optional) "auto" (default), "yes", or "no"
- session_id / session_name: (optional)
```

### everyrow_forecast
Forecast the probability of binary questions.
```
Parameters:
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects (must include "question" column)
- context: (optional) Batch-level context for all questions
- session_id / session_name: (optional)
```

### everyrow_classify
Classify each row into one of the provided categories.
```
Parameters:
- task: (required) Natural language classification instructions
- categories: (required) Allowed categories (minimum 2)
- artifact_id: Artifact ID (UUID) from upload_data or request_upload_url
- data: Inline data as a list of row objects
- classification_field: (optional) Output column name (default: "classification")
- include_reasoning: (optional) Include reasoning column (default: false)
- session_id / session_name: (optional)
```

## Data Management

### everyrow_browse_lists
Browse available reference lists of well-known entities (S&P 500, FTSE 100, countries, universities, etc.).
```
Parameters:
- search: (optional) Search term to match list names
- category: (optional) Filter by category (e.g. "Finance", "Geography")
```

### everyrow_use_list
Import a reference list into your session and save it as a CSV.
```
Parameters:
- artifact_id: (required) artifact_id from everyrow_browse_lists results
```

### everyrow_upload_data
Upload data from a URL or local file. Returns an artifact_id for use in processing tools.
```
Parameters:
- source: (required) HTTP(S) URL (Google Sheets supported) or local CSV path (stdio mode only)
- session_id / session_name: (optional)
```

### everyrow_request_upload_url
Request a presigned URL to upload a local CSV file (HTTP mode only).
```
Parameters:
- filename: (required) Name of the file to upload (must end in .csv)
```
Steps: call this tool → execute the returned curl command → use the artifact_id from the response.

## Task Lifecycle

### everyrow_progress
Check progress of a running task. Blocks briefly to limit polling rate.
```
Parameters:
- task_id: (required) Task ID returned by the operation tool
```
After receiving a status update, immediately call everyrow_progress again unless the task is completed or failed.

### everyrow_results
Retrieve results from a completed task.
```
Parameters:
- task_id: (required) Task ID of the completed task
- output_path: (stdio) Full path to output CSV (must end in .csv)
- offset: (http, optional) Row offset for pagination (default: 0)
- page_size: (http, optional) Number of rows to load into context (default: auto threshold based on row count)
```
Only call after everyrow_progress reports status "completed".

### everyrow_cancel
Cancel a running task.
```
Parameters:
- task_id: (required) Task ID to cancel
```

## Sessions & Account

### everyrow_list_sessions
List sessions owned by the authenticated user (paginated).
```
Parameters:
- offset: (optional) Number of sessions to skip (default: 0)
- limit: (optional) Max sessions per page (default: 25, max: 1000)
```

### everyrow_list_session_tasks
List all tasks in a session with their IDs, statuses, and types.
```
Parameters:
- session_id: (required) Session ID (UUID) to list tasks for
```

### everyrow_balance
Check the current billing balance for the authenticated user.
```
No parameters.
```

---

# Python SDK Reference

## Results

All operations return a result object. The data is available as a pandas DataFrame in `result.data`:

```python
result = await rank(...)
print(result.data.head())  # pandas DataFrame
```

## Operations

For quick one-off operations, sessions are created automatically.

### rank - Score and rank rows

Score rows based on criteria you can't put in a database field:

```python
from everyrow.ops import rank

result = await rank(
    task="Score by likelihood to need data integration solutions",
    input=leads_dataframe,
    field_name="integration_need_score",
    ascending_order=False,  # highest first
)
print(result.data.head())
```

**Structured output** - get more than just a score:

```python
from pydantic import BaseModel, Field

class AcquisitionScore(BaseModel):
    fit_score: float = Field(description="0-100, strategic alignment")
    annual_revenue_usd: int = Field(description="Estimated annual revenue in USD")

result = await rank(
    task="Score acquisition targets by product-market fit",
    input=potential_acquisitions,
    field_name="fit_score",
    response_model=AcquisitionScore,
    ascending_order=False,
)
```

Parameters: `task`, `input`, `field_name`, `field_type` (default: "float"), `response_model`, `ascending_order` (default: True), `preview`, `session`

### dedupe - Deduplicate data

Remove duplicates using AI-powered semantic matching. The AI understands that "AbbVie Inc", "Abbvie", and "AbbVie Pharmaceutical" are the same company:

```python
from everyrow.ops import dedupe

result = await dedupe(
    input=crm_data,
    equivalence_relation="Two entries are duplicates if they represent the same legal entity",
)
print(result.data.head())
```

**Strategies** - control what happens after clusters are identified:

- `"select"` (default): Pick the best representative from each cluster
- `"identify"`: Cluster only, no selection (for manual review)
- `"combine"`: Synthesize a single combined row per cluster

```python
result = await dedupe(
    input=crm_data,
    equivalence_relation="Same legal entity",
    strategy="select",
    strategy_prompt="Prefer the record with the most complete contact information",
)
deduped = result.data[result.data["selected"] == True]
```

Results include `equivalence_class_id` (groups duplicates), `equivalence_class_name` (human-readable cluster name), and `selected` (the canonical record when using select/combine strategy).

Parameters: `input`, `equivalence_relation`, `strategy`, `strategy_prompt`, `session`

### merge - Merge tables with AI matching

Join two tables when the keys don't match exactly (LEFT JOIN semantics). The AI knows "Photoshop" belongs to "Adobe" and "Genentech" is a Roche subsidiary:

```python
from everyrow.ops import merge

result = await merge(
    task="Match each software product to its parent company",
    left_table=software_products,   # table being enriched — all rows kept
    right_table=approved_suppliers,  # lookup/reference table — columns appended to matches
    # merge_on_left/merge_on_right: omit unless you expect exact string matches
    # on the chosen columns or want to draw agent attention to them.
)
print(result.data.head())
```

Parameters: `task`, `left_table`, `right_table`, `merge_on_left`, `merge_on_right`, `relationship_type`, `use_web_search`, `session`

### classify - Categorize rows

Assign each row to one of the provided categories:

```python
from everyrow.ops import classify

result = await classify(
    task="Classify this company by its GICS industry sector",
    categories=["Energy", "Materials", "Industrials", "Consumer Discretionary",
                 "Consumer Staples", "Health Care", "Financials",
                 "Information Technology", "Communication Services",
                 "Utilities", "Real Estate"],
    input=companies,
)
print(result.data[["company", "classification"]])
```

**Binary classification** - for yes/no questions, use two categories:

```python
result = await classify(
    task="Is this company founder-led?",
    categories=["yes", "no"],
    input=companies,
)
```

**With reasoning** - understand why each row was classified:

```python
result = await classify(
    task="Classify each company by its primary industry sector",
    categories=["Technology", "Finance", "Healthcare", "Energy"],
    input=companies,
    classification_field="sector",
    include_reasoning=True,
)
```

Parameters: `task`, `categories`, `input`, `classification_field` (default: "classification"), `include_reasoning` (default: False), `session`

### screen - Evaluate and filter rows

Filter rows based on criteria that require research:

```python
from everyrow.ops import screen
from pydantic import BaseModel, Field

class ScreenResult(BaseModel):
    passes: bool = Field(description="True if company meets the criteria")

result = await screen(
    task="""
        Find companies with >75% recurring revenue that would benefit from
        Taiwan tensions - CHIPS Act beneficiaries, defense contractors,
        cybersecurity firms. Exclude companies dependent on Taiwan manufacturing.
    """,
    input=sp500_companies,
    response_model=ScreenResult,
)
print(result.data.head())
```

**Richer output** - add fields to understand why something passed:

```python
class VendorRisk(BaseModel):
    approved: bool = Field(description="True if vendor is acceptable")
    risk_level: str = Field(description="low / medium / high")
    security_issues: str = Field(description="Any breaches or incidents")

result = await screen(
    task="Assess each vendor for enterprise use based on security incidents and financial stability",
    input=vendors,
    response_model=VendorRisk,
)
```

Parameters: `task`, `input`, `response_model`, `session`

### forecast - Predict probabilities

Produce calibrated probability estimates for binary questions:

```python
from everyrow.ops import forecast

result = await forecast(
    input=DataFrame([
        {"question": "Will the US Federal Reserve cut rates by at least 25bp before July 1, 2027?",
         "resolution_criteria": "Resolves YES if the Fed announces at least one rate cut of 25bp or more."},
    ]),
)
print(result.data[["question", "probability", "rationale"]])
```

Parameters: `input`, `context`, `session`

### single_agent - Single input task

Run an AI agent on a single input:

```python
from everyrow.ops import single_agent
from pydantic import BaseModel

class CompanyInput(BaseModel):
    company: str

result = await single_agent(
    task="Find the company's most recent annual revenue and employee count",
    input=CompanyInput(company="Stripe"),
)
print(result.data.head())
```

**No input required** - agents can work without input data:

```python
result = await single_agent(
    task="What company has reported the greatest cost reduction due to internal AI usage?",
)
```

**Return a table** - generate datasets from scratch:

```python
from pydantic import BaseModel, Field

class CompanyInfo(BaseModel):
    company: str = Field(description="Company name")
    market_cap: int = Field(description="Market cap in USD")

result = await single_agent(
    task="Find the three largest US healthcare companies by market cap",
    response_model=CompanyInfo,
    return_table=True,
)
```

Parameters: `task`, `input`, `effort_level` (LOW/MEDIUM/HIGH), `response_model`, `return_table`, `session`

### agent_map - Batch processing

Run an AI agent across multiple rows:

```python
from everyrow.ops import agent_map
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

- `LOW` (default): Quick lookups, basic web searches
- `MEDIUM`: More thorough research, multiple sources
- `HIGH`: Deep research, cross-referencing sources

```python
from everyrow.ops import agent_map
from everyrow.types import EffortLevel

result = await agent_map(
    task="Comprehensive competitive analysis",
    input=competitors,
    effort_level=EffortLevel.HIGH,
)
```

Parameters: `task`, `input`, `effort_level`, `response_model`, `session`

## Explicit Sessions

For multiple operations or when you need visibility into progress, use an explicit session:

```python
from everyrow import create_session

async with create_session(name="My Session") as session:
    print(f"View session at: {session.get_url()}")
    # All operations here share the same session
```

Sessions are visible on the everyrow.io dashboard.

## Async Operations

All operations have `_async` variants for background processing. These need an explicit session since the task persists beyond the function call:

```python
from everyrow import create_session
from everyrow.ops import rank_async

async with create_session(name="Async Ranking") as session:
    task = await rank_async(
        session=session,
        task="Score this organization",
        input=dataframe,
        field_name="score",
    )
    print(f"Task ID: {task.task_id}")  # Print this! Useful if your script crashes.

    # Continue with other work...
    result = await task.await_result()
```

**Tip:** Print the task ID after submitting. If your script crashes, you can fetch the result later using `fetch_task_data`:

```python
from everyrow import fetch_task_data

# Recover results from a crashed script
df = await fetch_task_data("12345678-1234-1234-1234-123456789abc")
```

## Everyrow Long-Running Operations (MCP)

Everyrow operations (classify, screen, rank, dedupe, merge, forecast, agent) take 1-10+ minutes.
All MCP tools use an async pattern:

1. Call the operation tool (e.g., `everyrow_agent(...)`) to get task_id and session_url
2. Share session_url with the user
3. Call everyrow_progress(task_id) — the tool handles pacing internally
4. After each status update, immediately call everyrow_progress again
5. When status is "completed" or "failed", call everyrow_results(task_id)

Note: If you see "Stop hook error:" messages during everyrow operations,
this is expected behavior — it means the polling guardrail is working correctly.
(Known cosmetic issue: anthropics/claude-code#12667)

## Chaining Operations

Operations can be chained to build complete workflows. Each step's output feeds the next:

```python
from everyrow import create_session
from everyrow.ops import screen, dedupe, rank

async with create_session(name="Lead Pipeline") as session:
    # 1. Filter to qualified leads
    screened = await screen(
        session=session,
        task="Has a company email domain (not gmail, yahoo, etc.)",
        input=leads,
        response_model=ScreenResult,
    )

    # 2. Dedupe across sources
    deduped = await dedupe(
        session=session,
        input=screened.data,
        equivalence_relation="Same company, accounting for Inc/LLC variations",
    )

    # 3. Prioritize for outreach
    ranked = await rank(
        session=session,
        task="Score by likelihood to convert",
        input=deduped.data[deduped.data["selected"] == True],
        field_name="conversion_score",
    )
```

## Best Practices

Everyrow operations have associated costs. To avoid re-running them unnecessarily:

- **Separate data processing from analysis**: Save everyrow results to a file (CSV, Parquet, etc.), then do analysis in a separate script. This way, if analysis code has bugs, you don't re-trigger the everyrow step.
- **Use intermediate checkpoints**: For multi-step pipelines, consider saving results after each everyrow operation.
    - You are able to chain multiple operations together without needing to download and re-upload intermediate results via the SDK. However for most control, implement each step as a dedicated job, possibly orchestrated by tools such as Apache Airflow or Prefect.
- **Test with `preview=True`**: Operations like `rank`, `screen`, and `merge` support `preview=True` to process only a few rows first.

## Status Line Setup

If the user asks about progress bar setup, status line configuration, or how to see a progress bar during operations, add the following to their `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "statusLine": {
    "type": "command",
    "command": "<path-to-plugin>/everyrow-mcp/scripts/everyrow-statusline.sh",
    "padding": 1
  }
}
```

Replace `<path-to-plugin>` with the absolute path to the installed plugin directory.

The status line requires `jq` to be installed:

```bash
# macOS
brew install jq

# Linux
apt install jq
```

After adding the config, the user must restart Claude Code for it to take effect.

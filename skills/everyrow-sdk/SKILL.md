---
name: everyrow-sdk
description: Helps write Python code using the everyrow SDK for AI-powered data processing - transforming, deduping, merging, ranking, and screening dataframes with natural language instructions
---

# everyrow SDK

The everyrow SDK provides intelligent data processing utilities powered by AI agents. Use this skill when writing Python code that needs to:

> **Documentation**: For detailed guides, case studies, and API reference, see:
> - Docs site: [everyrow.io/docs](https://everyrow.io/docs)
> - GitHub: [github.com/futuresearch/everyrow-sdk](https://github.com/futuresearch/everyrow-sdk)

**Operations:**
- Rank/score rows based on qualitative criteria
- Deduplicate data using semantic understanding
- Merge tables using AI-powered matching
- Screen/filter rows based on research-intensive criteria
- Run AI agents over dataframe rows

## Installation

### Python SDK

```bash
pip install everyrow
```

### MCP Server (for Claude Code, Claude Desktop, Cursor, etc.)

If an MCP server is available (`everyrow_screen`, `everyrow_rank`, etc. tools), you can use it directly without writing Python code. The MCP server operates on local CSV files.

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

Before writing any everyrow code or using the MCP tools, check if `EVERYROW_API_KEY` is set. If not, prompt the user:

> everyrow requires an API key. Do you have one?
> - If yes, paste it here
> - If no, get one at https://everyrow.io/api-key ($20 free credit) and paste it back

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

If you have the everyrow MCP server configured, these tools operate directly on CSV files.

### everyrow_screen
Filter CSV rows based on criteria that require judgment.
```
Parameters:
- task: Natural language description of screening criteria
- input_csv: Absolute path to input CSV
- output_path: Directory or full .csv path for output
```

### everyrow_rank
Score and sort CSV rows based on qualitative criteria.
```
Parameters:
- task: Natural language description of ranking criteria
- input_csv: Absolute path to input CSV
- output_path: Directory or full .csv path for output
- field_name: Name of the score field to add
- field_type: Type of field (float, int, str, bool)
- ascending_order: Sort direction (default: true)
```

### everyrow_dedupe
Remove duplicate rows using semantic equivalence.
```
Parameters:
- equivalence_relation: Natural language description of what makes rows duplicates
- input_csv: Absolute path to input CSV
- output_path: Directory or full .csv path for output
- select_representative: Keep one row per duplicate group (default: true)
```

### everyrow_merge
Join two CSV files using intelligent entity matching (LEFT JOIN semantics).
```
Parameters:
- task: Natural language description of how to match rows
- left_csv: Absolute path to the left CSV — the table being enriched (ALL its rows are kept in the output)
- right_csv: Absolute path to the right CSV — the lookup/reference table (its columns are appended to matches; unmatched left rows get nulls)
- output_path: Directory or full .csv path for output
- merge_on_left: (optional) Only set if you expect exact string matches on the chosen column or want to draw agent attention to it. Fine to omit.
- merge_on_right: (optional) Only set if you expect exact string matches on the chosen column or want to draw agent attention to it. Fine to omit.
- relationship_type: (optional) Defaults to "many_to_one", which is correct in most cases (e.g. products → companies). Only set "one_to_one" when both tables have unique entities of the same kind.
- use_web_search: (optional) "auto" (default), "yes", or "no"
```

### everyrow_agent
Run web research agents on each row of a CSV.
```
Parameters:
- task: Natural language description of research task
- input_csv: Absolute path to input CSV
- output_path: Directory or full .csv path for output
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

Everyrow operations (screen, rank, dedupe, merge, agent) take 1-10+ minutes.
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

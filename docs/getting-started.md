---
title: Python SDK
description: How to directly control your team of research agents to forecast, classify, rank, score, or gather data for you.
---

# Python SDK

> **Just want to use everyrow?** Go to [everyrow.io/app](https://everyrow.io/app), add it to [Claude.ai](/docs/claude-ai), [Cowork](/docs/claude-cowork), or [Claude Code](/docs/claude-code). This guide is for developers using the Python SDK.

Using the Python SDK gives you direct access to the utilities for directing your team of researchers. You can use all the methods documented in the [API Reference](/docs/api) and control the parameters such as effort level, which LLM to use, etc.

## Python SDK with pip

```bash
pip install everyrow
```

Requires Python 3.12+.

**Important:** be sure to supply your API key when running scripts:

```bash
export EVERYROW_API_KEY=sk-cho...
python3 example_script.py
```

**Quick example:**

```python
import asyncio
import pandas as pd
from everyrow.ops import screen
from pydantic import BaseModel, Field

companies = pd.DataFrame([
    {"company": "Airtable",}, {"company": "Vercel",}, {"company": "Notion",}
])

class JobScreenResult(BaseModel):
    qualifies: bool = Field(description="True if company lists jobs with all criteria")

async def main():
    result = await screen(
        task="""Qualifies if: 1. Remote-friendly, 2. Senior, and 3. Discloses salary""",
        input=companies,
        response_model=JobScreenResult,
    )
    print(result.data.head())

asyncio.run(main())
```

## Dependencies

The MCP server requires [**uv**](https://docs.astral.sh/uv/) (if using `uvx`) or [**pip**](https://pip.pypa.io/en/stable/) (if installed directly). The Python SDK requires **Python 3.12+**.

For the optional terminal progress bar, see the [jq dependency](/docs/progress-monitoring#status-line-progress-bar) in the progress monitoring guide.

## Sessions

Every operation runs within a **session**. Sessions group related operations together and appear in your [everyrow.io](https://everyrow.io) session list.

When you call an operation without an explicit session, one is created automatically. For multiple related operations, create an explicit session:

```python
from everyrow import create_session
from everyrow.ops import screen, rank

async with create_session(name="Lead Qualification") as session:
    # Get the URL to view this session in the dashboard
    print(f"View at: {session.get_url()}")

    # All operations share this session
    screened = await screen(
        session=session,
        task="Has a company email domain (not gmail, yahoo, etc.)",
        input=leads,
        response_model=ScreenResult,
    )

    ranked = await rank(
        session=session,
        task="Score by likelihood to convert",
        input=screened.data,
        field_name="conversion_score",
    )
```

The session URL lets you monitor progress and inspect results in the web UI while your script runs.

### Listing Sessions

Retrieve all your sessions programmatically with `list_sessions`:

```python
from everyrow import list_sessions

sessions = await list_sessions()
for s in sessions:
    print(f"{s.name} ({s.session_id}) — created {s.created_at:%Y-%m-%d}")
    print(f"  View: {s.get_url()}")
```

Each item is a `SessionInfo` with `session_id`, `name`, `created_at`, and `updated_at` fields.

## Async Operations

For long-running jobs, use the `_async` variants to submit work and continue without blocking:

```python
from everyrow import create_session
from everyrow.ops import rank_async

async with create_session(name="Background Ranking") as session:
    task = await rank_async(
        session=session,
        task="Score by revenue potential",
        input=large_dataframe,
        field_name="score",
    )

    # Task is now running server-side
    print(f"Task ID: {task.task_id}")

    # Do other work...

    # Wait for result when ready
    result = await task.await_result()

    # Or cancel if no longer needed
    await task.cancel()
```

**Print the task ID.** If your script crashes, recover the result later:

```python
from everyrow import fetch_task_data

df = await fetch_task_data("12345678-1234-1234-1234-123456789abc")
```

## Operations

| Operation                         | Description                                |
| --------------------------------- | ------------------------------------------ |
| [Classify](/docs/reference/CLASSIFY)   | Categorize rows into predefined classes    |
| [Screen](/docs/reference/SCREEN)       | Filter rows by criteria requiring judgment |
| [Rank](/docs/reference/RANK)           | Score rows by qualitative factors          |
| [Dedupe](/docs/reference/DEDUPE)       | Deduplicate when fuzzy matching fails      |
| [Merge](/docs/reference/MERGE)         | Join tables when keys don't match exactly  |
| [Forecast](/docs/reference/FORECAST)   | Predict probabilities for binary questions |
| [Research](/docs/reference/RESEARCH)   | Run web agents to research each row        |

## See Also

- [Guides](/docs/filter-dataframe-with-llm): step-by-step tutorials
- [Case Studies](/docs/case-studies): worked examples
- [Skills vs MCP](/docs/skills-vs-mcp): integration options

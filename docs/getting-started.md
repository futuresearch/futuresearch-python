---
title: "Getting Started"
description: Install everyrow and run your first operation.
---

# Getting Started

Everyrow lets you perform qualitative data transformations on noisy real-world data, at quantitative scale. Define your fuzzy logic concisely in natural language, and everyrow handles the complexity of orchestrating the execution.

## Prerequisites

- Python 3.12+
- API key from [everyrow.io/api-key](https://everyrow.io/api-key)

## Installation

```bash
pip install everyrow
export EVERYROW_API_KEY=your_key_here
```

See the [docs homepage](/docs) for other options (MCP servers, coding agent plugins).

## Basic Example

Shortlist an initial set of companies.

```python
import asyncio
import pandas as pd
from everyrow.ops import screen
from pydantic import BaseModel, Field

jobs = pd.DataFrame([
    {"company": "Airtable",   "post": "Async-first team, 8+ yrs exp, $185-220K base"},
    {"company": "Vercel",     "post": "Lead our NYC team. Competitive comp, DOE"},
    {"company": "Notion",     "post": "In-office SF. Staff eng, $200K + equity"},
    {"company": "Linear",     "post": "Bootcamp grads welcome! $85K, remote-friendly"},
    {"company": "Descript",   "post": "Work from anywhere. Principal architect, $250K"},
])

class JobScreenResult(BaseModel):
    qualifies: bool = Field(description="True if meets ALL criteria")

async def main():
    result = await screen(
        task="""
            Qualifies if ALL THREE are met:
            1. Remote-friendly
            2. Senior-level (5+ yrs exp OR Senior/Staff/Principal in title)
            3. Salary disclosed (specific numbers, not "competitive" or "DOE")
        """,
        input=jobs,
        response_model=JobScreenResult,
    )
    print(result.data)

asyncio.run(main())
```

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

| Operation                       | Description                                |
| ------------------------------- | ------------------------------------------ |
| [Screen](/reference/SCREEN)     | Filter rows by criteria requiring judgment |
| [Rank](/reference/RANK)         | Score rows by qualitative factors          |
| [Dedupe](/reference/DEDUPE)     | Deduplicate when fuzzy matching fails      |
| [Merge](/reference/MERGE)       | Join tables when keys don't match exactly  |
| [Research](/reference/RESEARCH) | Run web agents to research each row        |

## See Also

- [Guides](/filter-dataframe-with-llm): step-by-step tutorials
- [Case Studies](/case-studies/basic-usage): worked examples
- [Skills vs MCP](/skills-vs-mcp): integration options

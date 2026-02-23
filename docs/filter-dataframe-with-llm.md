---
title: Filter a Pandas DataFrame with LLMs
description: How to screen data by criteria that require research in Python. LLM research agents will cheaply and accurately research every row to screen, filter, or qualify.
---

# How to Filter a DataFrame with an LLM

Here we show how to filter a pandas dataframe by qualitative criteria, when normal filtering like `df[df['column'] == value]` won't work.

LLMs, and LLM-web-agents, can evaluate qualitative criteria at high accuracy. But they can be very expensive and difficult to orchestrate at scale. We provide a low cost solution by handling the orchestration, batching, and consistency checking.

This guide shows how to filter 3,616 job postings for "remote-friendly, senior-level roles with disclosed salary" in 10 minutes for $4.24.

| Metric              | Value       |
| ------------------- | ----------- |
| Rows processed      | 3,616       |
| Rows passing filter | 216 (6.0%)  |
| Total cost          | $4.24       |
| Time                | 9.9 minutes |
| Cost per row        | $0.001      |

In this example, we want to check job postings for three criteria:

1. Remote-friendly
2. Senior level
3. Salary is disclosed

None of these can be done without intelligence, by, e.g.

```python
# This matches "No remote work available"
df[df['posting'].str.contains('remote', case=False)]
```

What you need is a filter that understands: this posting explicitly allows remote work, requires senior experience, and states a specific salary number.

We use a dataset of 3,616 job postings from Hacker News "Who's Hiring" threads, 10% of all posts every month since March 2020 through January 2026. To follow along, [right click this link](https://media.githubusercontent.com/media/futuresearch/everyrow-sdk/refs/heads/main/docs/data/hn_jobs_screen.csv) and save the CSV file to your computer.

```bash
pip install everyrow
export EVERYROW_API_KEY=your_key_here  # Get one at everyrow.io/api-key
```

```python
import asyncio
import pandas as pd
from pydantic import BaseModel, Field
from everyrow.ops import screen

jobs = pd.read_csv("hn_jobs_screen.csv")  # 3,616 job postings

class JobScreenResult(BaseModel):
    qualifies: bool = Field(description="True if meets ALL criteria")

async def main():
    result = await screen(
        task="""
        A job posting qualifies if it meets ALL THREE criteria:

        1. Remote-friendly: Explicitly allows remote work, hybrid, WFH,
           distributed teams, or "work from anywhere".

        2. Senior-level: Title contains Senior/Staff/Lead/Principal/Architect,
           OR requires 5+ years experience, OR mentions "founding engineer".

        3. Salary disclosed: Specific compensation numbers are mentioned.
           "$150K-200K" qualifies. "Competitive" or "DOE" does not.
        """,
        input=jobs,
        response_model=JobScreenResult,
    )

    qualified = result.data
    print(f"Qualified: {len(qualified)} of {len(jobs)}")
    return qualified

qualified_jobs = asyncio.run(main())
```

The screen operation evaluates each row against the natural language criteria and returns only the rows that pass. Out of 3,616 postings, 216 qualified (6.0%). [View the session](https://everyrow.io/sessions/6f742040-7a17-46c3-87fd-419062e69bf2).

Interestingly, the data reveals a clear trend in tech hiring practices over the pandemic years:

| Year | Qualified | Total | Pass Rate |
| ---- | --------- | ----- | --------- |
| 2020 | 10        | 594   | 1.7%      |
| 2021 | 27        | 1,033 | 2.6%      |
| 2022 | 36        | 758   | 4.7%      |
| 2023 | 39        | 412   | 9.5%      |
| 2024 | 39        | 387   | 10.1%     |
| 2025 | 59        | 406   | 14.5%     |
| 2026 | 6         | 26    | 23.1%     |

In early 2020, only 1.7% of job postings met all three criteria. By 2025, that number reached 14.5%. More companies now offer remote work, disclose salaries upfront, and hire senior engineers.

Some examples:

```
Bloomberg | Senior Software Engineer | Hybrid (NYC) | $160k - $240k USD + bonus
KoBold Metals | Senior Infrastructure Engineer | Remote (USA) | $170k - $230k
EnergyHub | Director of Engineering | Remote (US) | Salary $225k
Gladly | Staff Software Engineer | Remote (US, Colombia) | $60k–$215k + Equity
```

---

Built with [everyrow](https://github.com/futuresearch/everyrow-sdk). See the [screen documentation](reference/SCREEN) for more options including batch size tuning and async execution.

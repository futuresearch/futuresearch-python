---
title: How to Add A Column to a DataFrame with Web Research
description: Step-by-step guide to enriching a pandas DataFrame with new columns using LLM-powered web research agents to find and add any data.
---

# How to Add a Column to a DataFrame Using Web Lookup

`pandas.apply()` runs a local function on each row. But it can't use LLM judgment or do web research to find new values. And doing this by hand can be very slow or expensive. EveryRow provides a one-line utility to do this cheaply and at scale.

This guide shows how to add a column for price, for 246 common software products, in a single method call on your pandas dataframe.

| Metric       | Value                                                                     |
| ------------ | ------------------------------------------------------------------------- |
| Rows         | 246                                                                       |
| Cost         | $6.68                                                                     |
| Time         | 15.7 minutes                                                              |
| Success rate | 99.6% (1 failed)                                                          |
| Session      | [view](https://everyrow.io/sessions/e09de4e8-1e0d-44af-8d1a-a25620565ed4) |

```bash
pip install everyrow
export EVERYROW_API_KEY=your_key_here  # Get one at everyrow.io/api-key
```

The dataset is a list of 246 SaaS and developer tools like Slack, Notion, Asana. To follow along, [right click this link](https://media.githubusercontent.com/media/futuresearch/everyrow-sdk/refs/heads/main/docs/data/saas_products.csv) and save the CSV file to your computer. We find the annual price of each product's lowest paid tier, which isn't available through any structured API; it requires visiting pricing pages that change frequently and present information in different formats.

```python
import asyncio
import pandas as pd
from pydantic import BaseModel, Field
from everyrow import create_session
from everyrow.ops import agent_map

class PricingInfo(BaseModel):
    lowest_paid_tier_annual_price: float = Field(
        description="Annual price in USD for the lowest paid tier. "
                    "Use monthly price * 12 if only monthly shown. "
                    "0 if no paid tier exists."
    )
    tier_name: str = Field(
        description="Name of the lowest paid tier (e.g. 'Pro', 'Starter', 'Basic')"
    )

async def main():
    df = pd.read_csv("saas_products.csv")  # Single column: product

    async with create_session(name="SaaS pricing lookup") as session:
        result = await agent_map(
            session=session,
            task="""
                Find the pricing for this SaaS product's lowest paid tier.
                Visit the product's pricing page to find this information.

                Look for the cheapest paid plan (not free tier). Report:
                - The annual price in USD (if monthly, multiply by 12)
                - The name of that tier

                If the product has no paid tier or pricing isn't public, use 0.
            """,
            input=df,
            response_model=PricingInfo,
        )
    print(result.data)

asyncio.run(main())
```

```
         product       tier_name  lowest_paid_tier_annual_price
0         Notion            Plus                          96.00
1          Slack             Pro                          87.00
2          Asana         Starter                         131.88
3     Monday.com           Basic                         108.00
4         Trello        Standard                          60.00
5           Jira        Standard                          94.92
6         Linear           Basic                         120.00
7        ClickUp       Unlimited                          84.00
...
```

Each result includes a `research` column showing how the agent found the answer, with citations linking back to sources. For example, Slack's entry shows: "The Pro plan costs $7.25 USD per active user per month when billed annually (from slack.com/pricing/pro). Annual price calculation: $7.25 × 12 months = $87 per user per year."

The key to doing this cheaply is in the orchestration of the web research agents, using the right batching, parallelism, LLMs, search tools, and page reading tools. Web research agents have degrees of freedom on how to solve problems, and EveryRow optimizes them for cost and accuracy, all in a single method on your pandas dataframe.

By using LLM web agents, this works for any new column, any enrichment, that you need on your table, as long as the information can be found on the web.

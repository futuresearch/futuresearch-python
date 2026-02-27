---
title: agent_map
description: API reference for the EveryRow agent_map and single_agent tools, which run web research agents on entire DataFrames or single inputs.
---

# Research

`single_agent` runs one web research agent on a single input (or no input). `agent_map` runs an agent on every row of a DataFrame in parallel. Both dispatch agents that search the web, read pages, and return structured results. The transform is live web research: agents fetch and synthesize external information to populate new columns.

## Examples

### `single_agent`

```python
from pydantic import BaseModel
from everyrow.ops import single_agent

class CompanyInput(BaseModel):
    company: str

result = await single_agent(
    task="Find the company's most recent annual revenue and employee count",
    input=CompanyInput(company="Stripe"),
)
print(result.data.head())
```

### No input required

You can run an agent without any input data.

```python
result = await single_agent(
    task="""
        What company has reported the greatest cost reduction
        due to internal AI usage over the past 12 months?
    """,
)
print(result.data.head())
```

### `agent_map`

```python
from pandas import DataFrame
from everyrow.ops import agent_map

companies = DataFrame([
    {"company": "Stripe"},
    {"company": "Databricks"},
    {"company": "Canva"},
])

result = await agent_map(
    task="Find the company's most recent annual revenue",
    input=companies,
)
print(result.data.head())
```

Each row gets its own agent that researches independently.

## Parameters

`single_agent` and `agent_map` have the nearly the same parameters.

| Name | Type | Description |
| ---- | ---- | ----------- |
| `task` | str | The agent task describing what to research |
| `session` | Session | Optional, auto-created if omitted |
| `input` | BaseModel \| DataFrame \| UUID | Optional input context |
| `effort_level` | EffortLevel | LOW, MEDIUM, or HIGH (default: MEDIUM) |
| `llm` | LLM | Optional agent LLM override |
| `response_model` | BaseModel | Optional schema for structured output |
| `return_table` | bool | (`single_agent` only) If True, returns a table instead of a scalar result |

### Effort levels

The effort level lets you control how thorough the research is.

- `LOW`: Just a single LLM call, not a real agent, cheapest & fastest
- `MEDIUM`: More thorough research, multiple sources consulted (default)
- `HIGH`: Deep research, cross-referencing sources, higher accuracy

### Response model

Both `single_agent` and `agent_map` support structured output via custom Pydantic models.

```python
from pandas import DataFrame
from pydantic import BaseModel, Field
from everyrow.ops import agent_map

companies = DataFrame([
    {"company": "Stripe"},
    {"company": "Databricks"},
    {"company": "Canva"},
])

class CompanyFinancials(BaseModel):
    annual_revenue_usd: int = Field(description="Most recent annual revenue in USD")
    employee_count: int = Field(description="Current number of employees")
    last_funding_round: str = Field(description="Most recent funding round, e.g. 'Series C'")

result = await agent_map(
    task="Research each company's financials and latest funding",
    input=companies,
    response_model=CompanyFinancials,
)
print(result.data.head())
```

Now the output has `annual_revenue_usd`, `employee_count`, and `last_funding_round` columns.

### Returning a table

With `single_agent`, you can generate a dataset from scratch by setting `return_table=True`.

```python
from pydantic import BaseModel, Field
from everyrow.ops import single_agent

class CompanyInfo(BaseModel):
    company: str = Field(description="Company name")
    market_cap: int = Field(description="Market cap in USD")

companies = await single_agent(
    task="Find the three largest US healthcare companies by market cap",
    response_model=CompanyInfo,
    return_table=True,  # Return a table of companies
)
```

## Via MCP

MCP tools: `everyrow_agent` (DataFrame), `everyrow_single_agent` (single question)

**everyrow_agent:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | string | Path to input CSV file |
| `task` | string | What to research for each row |

**everyrow_single_agent:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task` | string | The question to research |

## Related docs

### Guides
- [Add a Column with Web Lookup](/docs/add-column-web-lookup)
- [Classify and Label Data with an LLM](/docs/classify-dataframe-rows-llm)

### Case Studies
- [LLM Web Research Agents at Scale](/docs/case-studies/llm-web-research-agents-at-scale)

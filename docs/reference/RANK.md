---
title: rank
description: API reference for the EveryRow rank tool, which sorts a DataFrame by a metric computed through web research agents.
---

# Rank

`rank` takes a DataFrame and a natural-language scoring criterion, dispatches web research agents to compute a score for each row, and returns the DataFrame sorted by that score. The sort key does not need to exist in your data. Agents derive it at runtime by searching the web, reading pages, and reasoning over what they find.

## Examples

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

The task can be as specific as you want. You can describe the metric in detail, list which sources to use, and explain how to resolve ambiguities.

```python
result = await rank(
    task="""
        Score 0-100 by likelihood to adopt research tools in the next 12 months.

        High scores: teams actively publishing, hiring researchers, or with
        recent funding for R&D. Low scores: pure trading shops, firms with
        no public research output.

        Consult the company's website, job postings, and LinkedIn profile for information.
    """,
    input=investment_firms,
    field_name="research_adoption_score",
    ascending_order=False,  # highest first
)
print(result.data.head())
```

### Structured output

If you want more than just a number, pass a Pydantic model.

Note that you don't need specify fields for reasoning, explanation or sources. That information is included automatically.

```python
from pydantic import BaseModel, Field

class AcquisitionScore(BaseModel):
    fit_score: float = Field(description="0-100, strategic alignment with our business")
    annual_revenue_usd: int = Field(description="Their estimated annual revenue in USD")

result = await rank(
    task="Score acquisition targets by product-market fit and revenue quality",
    input=potential_acquisitions,
    field_name="fit_score",
    response_model=AcquisitionScore,
    ascending_order=False,  # highest first
)
print(result.data.head())
```

Now every row has both `fit_score` and `annual_revenue_usd` fields, each of which includes its own explanation.

When specifying a response model, make sure that it contains `field_name`. Otherwise, you'll get an error. Also, the `field_type` parameter is ignored when you pass a response model.

## Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| `task` | str | The task for the agent describing how to find your metric |
| `session` | Session | Optional, auto-created if omitted |
| `input` | DataFrame | Your data |
| `field_name` | str | Column name for the metric |
| `field_type` | str | The type of the field (default: "float") |
| `response_model` | BaseModel | Optional response model for multiple output fields |
| `ascending_order` | bool | True = lowest first (default) |
| `preview` | bool | True = process only a few rows |

## Via MCP

MCP tool: `everyrow_rank`

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | string | Path to input CSV file |
| `task` | string | How to score each row |
| `field_name` | string | Column name for the score |

## Related docs

### Guides
- [Sort a Dataset Using Web Data](/docs/rank-by-external-metric)

### Case Studies
- [Score Leads from Fragmented Data](/docs/case-studies/score-leads-from-fragmented-data)
- [Score Leads Without CRM History](/docs/case-studies/score-leads-without-crm-history)
- [Research and Rank Permit Times](/docs/case-studies/research-and-rank-permit-times)

### Blog posts
- [Ranking by Data Fragmentation Risk](https://futuresearch.ai/lead-scoring-data-fragmentation/)
- [Rank Leads Like an Analyst](https://futuresearch.ai/lead-scoring-without-crm/)

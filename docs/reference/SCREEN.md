---
title: screen
description: API reference for the EveryRow screen tool, which filters a DataFrame using natural language criteria evaluated by web research agents.
---

# Screen

`screen` takes a DataFrame and a natural-language filter predicate, evaluates each row using web research agents, and returns only the rows that pass. The filter condition does not need to be computable from existing columns. Agents can research external information to make the determination.

## Examples

```python
from everyrow.ops import screen
from pydantic import BaseModel, Field

class ScreenResult(BaseModel):
    passes: bool = Field(description="True if company meets criteria")

result = await screen(
    task="""
        Find companies with >75% recurring revenue that would benefit from
        Taiwan tensions. Include CHIPS Act beneficiaries, defense contractors,
        cybersecurity firms. Exclude companies dependent on Taiwan manufacturing.
    """,
    input=sp500,
    response_model=ScreenResult,
)
print(result.data.head())
```

Only passing rows come back.

## Richer output

Want to know *why* something passed? Add fields:

```python
class VendorRisk(BaseModel):
    approved: bool = Field(description="True if vendor is acceptable")
    risk_level: str = Field(description="low / medium / high")
    security_issues: str = Field(description="Any breaches or incidents")
    recommendation: str = Field(description="Summary")

result = await screen(
    task="""
        Assess each vendor for enterprise use. Research:
        1. Security incidents in past 3 years
        2. Financial stability (layoffs, funding issues)

        Approve only low/medium risk with no unresolved critical incidents.
    """,
    input=vendors,
    response_model=VendorRisk,
)
print(result.data.head())
```

Now you get `risk_level`, `security_issues`, and `recommendation` for every row that passed.

## The pass/fail field

Your response model needs a boolean field. It can be named anything—`passes`, `approved`, `include`, whatever. The system figures out which field is the filter.

```python
class Simple(BaseModel):
    passes: bool

class Detailed(BaseModel):
    approved: bool  # this is the filter
    confidence: float
    notes: str
```

## Parameters

| Name | Type | Description |
|------|------|-------------|
| `task` | str | What should pass |
| `input` | DataFrame | Rows to screen |
| `response_model` | BaseModel | Optional. Must have a boolean field. Defaults to `passes: bool` |
| `session` | Session | Optional, auto-created if omitted |

## Performance

| Rows | Time | Cost | Precision |
|------|------|------|-----------|
| 100 | ~3 min | ~$0.70 | >90% |
| 500 | ~12 min | ~$3.30 | >90% |
| 1,000 | ~20 min | ~$6 | >90% |

Compare: regex on "remote-friendly" job postings gets 68% precision.

## Via MCP

MCP tool: `everyrow_screen`

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | string | Path to input CSV file |
| `task` | string | What should pass |

## Related docs

### Guides
- [Filter a DataFrame with LLMs](/docs/filter-dataframe-with-llm)

### Case Studies
- [LLM Screening at Scale](/docs/case-studies/llm-powered-screening-at-scale)
- [Screen Job Postings by Criteria](/docs/case-studies/screen-job-postings-by-criteria)
- [Screen Stocks by Investment Thesis](/docs/case-studies/screen-stocks-by-investment-thesis)
- [Screen Stocks by Margin Sensitivity](/docs/case-studies/screen-stocks-by-margin-sensitivity)
- [Multi-Stage Lead Qualification](/docs/case-studies/multi-stage-lead-qualification)

### Blog posts
- [Thematic Stock Screen](https://futuresearch.ai/thematic-stock-screening/)
- [Job Posting Screen](https://futuresearch.ai/job-posting-screening/)
- [Screening Workflow](https://futuresearch.ai/screening-workflow/)

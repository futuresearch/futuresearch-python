---
title: forecast
description: API reference for the EveryRow forecast tool, which produces calibrated probability estimates for binary questions using web research and an ensemble of forecasters.
---

# Forecast

`forecast` takes a DataFrame of binary questions and produces a calibrated probability estimate (0–100) and rationale for each row. The approach is validated against FutureSearch's past-casting environment of 1500 hard forecasting questions and 15M research documents. See more at [Automating Forecasting Questions](https://futuresearch.ai/automating-forecasting-questions/) and [arXiv:2506.21558](https://arxiv.org/abs/2506.21558).

## Examples

```python
from pandas import DataFrame
from everyrow.ops import forecast

questions = DataFrame([
    {
        "question": "Will the US Federal Reserve cut rates by at least 25bp before July 1, 2027?",
        "resolution_criteria": "Resolves YES if the Fed announces at least one rate cut of 25bp or more at any FOMC meeting between now and June 30, 2027.",
    },
])

result = await forecast(input=questions)
print(result.data[["question", "probability", "rationale"]])
```

The output DataFrame contains the original columns plus `probability` (int, 0–100) and `rationale` (str).

### Batch context

When all rows share common framing, pass it via `context` instead of repeating it in every row:

```python
result = await forecast(
    input=geopolitics_questions,
    context="Focus on EU regulatory and diplomatic sources. Assume all questions resolve by end of 2027.",
)
```

Leave `context` empty when rows are self-contained—a well-specified question with resolution criteria needs no additional instruction.

## Input columns

The input DataFrame should contain at minimum a `question` column. All columns are passed to the research agents and forecasters.

| Column | Required | Purpose |
|--------|----------|---------|
| `question` | Yes | The binary question to forecast |
| `resolution_criteria` | Recommended | Exactly how YES/NO is determined—the "contract" |
| `resolution_date` | Optional | When the question closes |
| `background` | Optional | Additional context the forecasters should know |

Column names are not enforced—research agents infer meaning from content. A column named `scenario` instead of `question` works fine.

## Parameters

| Name | Type | Description |
|------|------|-------------|
| `input` | DataFrame | Rows to forecast, one question per row |
| `context` | str \| None | Optional batch-level instructions that apply to every row |
| `session` | Session | Optional, auto-created if omitted |

## Output

Two columns are added to each input row:

| Column | Type | Description |
|--------|------|-------------|
| `probability` | int | 0–100, calibrated probability of YES resolution |
| `rationale` | str | Detailed reasoning with citations from web research |

Probabilities are clamped to [3, 97]—even near-certain outcomes retain residual uncertainty.

## Performance

| Rows | Time | Cost |
|------|------|------|
| 1 | ~5 min | ~$0.60 |
| 5 | ~6 min | ~$3 |
| 20 | ~10 min | ~$12 |

## Via MCP

MCP tool: `everyrow_forecast`

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | string | Path to CSV with questions (one per row) |
| `context` | string | Optional batch-level context for all questions |

## Related docs

### Blog posts
- [Automating Forecasting Questions](https://futuresearch.ai/automating-forecasting-questions/)
- [arXiv paper: Automated Forecasting](https://arxiv.org/abs/2506.21558)

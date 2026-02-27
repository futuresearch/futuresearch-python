---
title: dedupe
description: API reference for the EveryRow dedupe tool, which groups duplicate rows in a Python Pandas DataFrame using LLM-powered semantic matching.
---

# Dedupe

`dedupe` groups duplicate rows in a DataFrame based on a natural-language equivalence relation, assigns cluster IDs, and selects a canonical row per cluster. The duplicate criterion is semantic and LLM-powered: agents reason over the data and, when needed, search the web for external information to establish equivalence. This handles abbreviations, name variations, job changes, and entity relationships that no string similarity threshold can capture.

## Examples

```python
from everyrow.ops import dedupe

result = await dedupe(
    input=crm_data,
    equivalence_relation="Two entries are duplicates if they represent the same legal entity",
)
print(result.data.head())
```

The `equivalence_relation` is natural language. Be as specific as you need:

```python
result = await dedupe(
    input=researchers,
    equivalence_relation="""
        Two rows are duplicates if they're the same person, even if:
        - They changed jobs (different org/email)
        - Name is abbreviated (A. Smith vs Alex Smith)
        - There are typos (Naomi vs Namoi)
        - They use a nickname (Bob vs Robert)
    """,
)
print(result.data.head())
```

## Strategies

Control what happens after clusters are identified using the `strategy` parameter:

### `select` (default)

Picks the best representative from each cluster. Three columns are added:

- `equivalence_class_id` — rows with the same ID are duplicates of each other
- `equivalence_class_name` — human-readable label for the cluster
- `selected` — True for the canonical record in each cluster

```python
result = await dedupe(
    input=crm_data,
    equivalence_relation="Same legal entity",
    strategy="select",
    strategy_prompt="Prefer the record with the most complete contact information",
)
deduped = result.data[result.data["selected"] == True]
```

### `identify`

Cluster only — no selection or combining. Useful when you want to review clusters before deciding what to do.

- `equivalence_class_id` — rows with the same ID are duplicates of each other
- `equivalence_class_name` — human-readable label for the cluster

```python
result = await dedupe(
    input=crm_data,
    equivalence_relation="Same legal entity",
    strategy="identify",
)
```

### `combine`

Synthesizes a single combined row per cluster, merging the best information from all duplicates. Original rows are marked `selected=False`, and new combined rows are added with `selected=True`.

```python
result = await dedupe(
    input=crm_data,
    equivalence_relation="Same legal entity",
    strategy="combine",
    strategy_prompt="For each field, keep the most recent and complete value",
)
combined = result.data[result.data["selected"] == True]
```

## What you get back

Three columns added to your data (when using `select` or `combine` strategy):

- `equivalence_class_id` — rows with the same ID are duplicates of each other
- `equivalence_class_name` — human-readable label for the cluster ("Alexandra Butoi", "Naomi Saphra", etc.)
- `selected` — True for the canonical record in each cluster (usually the most complete one)

To get just the deduplicated rows:

```python
deduped = result.data[result.data["selected"] == True]
```

## Example

Input:

| name | org | email |
|------|-----|-------|
| A. Butoi | Rycolab | a.butoi@edu |
| Alexandra Butoi | Ryoclab | — |
| Namoi Saphra | — | nsaphra@alumni |
| Naomi Saphra | Harvard | nsaphra@harvard.edu |

Output (selected rows only):

| name | org | email |
|------|-----|-------|
| Alexandra Butoi | Rycolab | a.butoi@edu |
| Naomi Saphra | Harvard | nsaphra@harvard.edu |

## Parameters

| Name | Type | Description |
|------|------|-------------|
| `input` | DataFrame | Data with potential duplicates |
| `equivalence_relation` | str | What makes two rows duplicates |
| `strategy` | str | `"identify"`, `"select"` (default), or `"combine"` |
| `strategy_prompt` | str | Optional instructions for selection or combining |
| `session` | Session | Optional, auto-created if omitted |

## Performance

| Rows | Time | Cost |
|------|------|------|
| 200 | ~90 sec | ~$0.40 |
| 500 | ~2 min | ~$1.67 |
| 2,000 | ~8 min | ~$7 |

## Via MCP

MCP tool: `everyrow_dedupe`

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | string | Path to input CSV file |
| `equivalence_relation` | string | What makes two rows duplicates |

## Related docs

### Guides
- [Remove Duplicates from ML Training Data](/docs/deduplicate-training-data-ml)
- [Resolve Duplicate Entities](/docs/resolve-entities-python)

### Case Studies
- [Dedupe CRM Company Records](/docs/case-studies/dedupe-crm-company-records)

### Blog posts
- [CRM Deduplication](https://futuresearch.ai/crm-deduplication/)
- [Researcher Deduplication](https://futuresearch.ai/researcher-dedupe-case-study/)

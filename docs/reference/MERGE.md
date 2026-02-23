---
title: merge
description: API reference for EveryRow merge tool, which left-joins two Python Pandas DataFrames using LLM-powered agents to resolve key mappings.
---

# Merge

`merge` left-joins two DataFrames using LLM-powered agents to resolve the key mapping instead of requiring exact or fuzzy key matches. Agents resolve semantic relationships by reasoning over the data and, when needed, searching the web for external information to establish matches: subsidiaries, regional names, abbreviations, and product-to-parent-company mappings.

## Examples

```python
from everyrow.ops import merge

result = await merge(
    task="Match each software product to its parent company",
    left_table=software_products,   # table being enriched — all rows kept
    right_table=approved_vendors,    # lookup/reference table — columns appended
    # merge_on_left/merge_on_right omitted: auto-detection handles most cases.
    # Only specify them when you expect exact string matches on specific columns
    # or want to draw agent attention to them.
)
print(result.data.head())
```

For ambiguous cases, add context. Here `merge_on_left`/`merge_on_right` are set because
the column names ("sponsor", "company") are too generic for auto-detection:

```python
result = await merge(
    task="""
        Match clinical trial sponsors to parent pharma companies.

        Watch for:
        - Subsidiaries (Genentech → Roche, Janssen → J&J)
        - Regional names (MSD is Merck outside the US)
        - Abbreviations (BMS → Bristol-Myers Squibb)
    """,
    left_table=trials,              # table being enriched — all rows kept
    right_table=pharma_companies,   # lookup table
    merge_on_left="sponsor",        # specified: draws agent attention to this column
    merge_on_right="company",       # specified: draws agent attention to this column
)
print(result.data.head())
```

## What you get back

A DataFrame with all left table columns plus matched right table columns. Rows that don't match get nulls for the right columns (like a left join).

## Parameters

| Name | Type | Description |
|------|------|-------------|
| `task` | str | How to match the tables |
| `left_table` | DataFrame | The table being enriched — all its rows are kept in the output (LEFT JOIN). |
| `right_table` | DataFrame | The lookup/reference table — its columns are appended to matches; unmatched left rows get nulls. |
| `merge_on_left` | Optional[str] | Only set if you expect exact string matches on this column or want to draw agent attention to it. Auto-detected if omitted. |
| `merge_on_right` | Optional[str] | Only set if you expect exact string matches on this column or want to draw agent attention to it. Auto-detected if omitted. |
| `relationship_type` | Optional[str] | `"many_to_one"` (default) — multiple left rows can match one right row. `"one_to_one"` — only when both tables have unique entities of the same kind. |
| `use_web_search` | Optional[str] | `"auto"` (default), `"yes"`, or `"no"`. Controls whether agents use web search to resolve matches. |
| `session` | Session | Optional, auto-created if omitted |

## Performance

| Size | Time | Cost |
|------|------|------|
| 100 × 50 | ~3 min | ~$2 |
| 2,000 × 50 | ~8 min | ~$9 |
| 1,000 × 1,000 | ~12 min | ~$15 |

## Related docs

### Guides
- [Fuzzy Join Without Matching Keys](/docs/fuzzy-join-without-keys)

### Case Studies
- [LLM Merging at Scale](/docs/case-studies/llm-powered-merging-at-scale)
- [Match Software Vendors to Requirements](/docs/case-studies/match-software-vendors-to-requirements)
- [Merge Contacts with Company Data](/docs/case-studies/merge-contacts-with-company-data)
- [Merge Overlapping Contact Lists](/docs/case-studies/merge-overlapping-contact-lists)

### Blog posts
- [Software Supplier Matching](https://futuresearch.ai/software-supplier-matching/)
- [HubSpot Contact Merge](https://futuresearch.ai/merge-hubspot-contacts/)
- [CRM Merge Workflow](https://futuresearch.ai/crm-merge-workflow/)

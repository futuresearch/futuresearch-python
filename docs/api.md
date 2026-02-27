---
title: API Reference
description: Complete API reference for everyrow — screen, rank, dedupe, merge, forecast, and research operations powered by LLM web research agents.
---

# API Reference

Six operations for processing data with LLM-powered web research agents. Each takes a DataFrame and a natural-language instruction.

## screen

```python
result = await screen(task=..., input=df, response_model=Model)
```

`screen` takes a DataFrame and a natural-language filter predicate, evaluates each row using web research agents, and returns only the rows that pass. The filter condition does not need to be computable from existing columns. Agents can research external information to make the determination.

[Full reference →](/docs/reference/SCREEN)
Guides: [Filter a DataFrame with LLMs](/docs/filter-dataframe-with-llm)
Case Studies: [LLM Screening at Scale](/docs/case-studies/llm-powered-screening-at-scale), [Screen Stocks by Investment Thesis](/docs/case-studies/screen-stocks-by-investment-thesis)

## rank

```python
result = await rank(task=..., input=df, field_name="score")
```

`rank` takes a DataFrame and a natural-language scoring criterion, dispatches web research agents to compute a score for each row, and returns the DataFrame sorted by that score. The sort key does not need to exist in your data. Agents derive it at runtime by searching the web, reading pages, and reasoning over what they find.

[Full reference →](/docs/reference/RANK)
Guides: [Sort a Dataset Using Web Data](/docs/rank-by-external-metric)
Case Studies: [Score Leads from Fragmented Data](/docs/case-studies/score-leads-from-fragmented-data), [Score Leads Without CRM History](/docs/case-studies/score-leads-without-crm-history)

## dedupe

```python
result = await dedupe(input=df, equivalence_relation="...")
```

`dedupe` groups duplicate rows in a DataFrame based on a natural-language equivalence relation, assigns cluster IDs, and selects a canonical row per cluster. The duplicate criterion is semantic and LLM-powered: agents reason over the data and, when needed, search the web for external information to establish equivalence. This handles abbreviations, name variations, job changes, and entity relationships that no string similarity threshold can capture.

[Full reference →](/docs/reference/DEDUPE)
Guides: [Remove Duplicates from ML Training Data](/docs/deduplicate-training-data-ml), [Resolve Duplicate Entities](/docs/resolve-entities-python)
Case Studies: [Dedupe CRM Company Records](/docs/case-studies/dedupe-crm-company-records)

## merge

```python
result = await merge(task=..., left_table=df1, right_table=df2)
```

`merge` left-joins two DataFrames using LLM-powered agents to resolve the key mapping instead of requiring exact or fuzzy key matches. Agents resolve semantic relationships by reasoning over the data and, when needed, searching the web for external information to establish matches: subsidiaries, regional names, abbreviations, and product-to-parent-company mappings.

[Full reference →](/docs/reference/MERGE)
Guides: [Fuzzy Join Without Matching Keys](/docs/fuzzy-join-without-keys)
Case Studies: [LLM Merging at Scale](/docs/case-studies/llm-powered-merging-at-scale), [Match Software Vendors to Requirements](/docs/case-studies/match-software-vendors-to-requirements)

## forecast

```python
result = await forecast(input=questions_df)
```

`forecast` takes a DataFrame of binary questions and produces a calibrated probability estimate (0–100) and rationale for each row. Each question is researched across six dimensions in parallel, then synthesized by an ensemble of forecasters. Validated against 1500 hard forecasting questions and 15M research documents.

[Full reference →](/docs/reference/FORECAST)
Blog posts: [Automating Forecasting Questions](https://futuresearch.ai/automating-forecasting-questions/), [arXiv paper](https://arxiv.org/abs/2506.21558)

## agent_map / single_agent

```python
result = await agent_map(task=..., input=df)
```

`single_agent` runs one web research agent on a single input (or no input). `agent_map` runs an agent on every row of a DataFrame in parallel. Both dispatch agents that search the web, read pages, and return structured results. The transform is live web research: agents fetch and synthesize external information to populate new columns.

[Full reference →](/docs/reference/RESEARCH)
Guides: [Add a Column with Web Lookup](/docs/add-column-web-lookup), [Classify and Label Data with an LLM](/docs/classify-dataframe-rows-llm)
Case Studies: [LLM Web Research Agents at Scale](/docs/case-studies/llm-web-research-agents-at-scale)

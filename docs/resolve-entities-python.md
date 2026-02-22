---
title: How to resolve duplicate rows in Python with LLMs
description: Identify and merge duplicate records representing the same entity across messy data, handling spelling variations, abbreviations, and nicknames.
---

# How to Resolve Duplicate Entities in Python

Identifying matching records that represent the same entity across messy data typically requires labeled training data, manual blocking rules, or extensive threshold tuning.

LLMs can solve this at high accuracy. But they can be expensive to run at scale, and require a lot of orchestration. EveryRow is designed to do this as cheaply as possible while still having high accuracy, in a single method with almost no setup.

| Metric              | Value                                                                     |
| ------------------- | ------------------------------------------------------------------------- |
| Records processed   | 500                                                                       |
| Unique entities     | 131                                                                       |
| Duplicates resolved | 369                                                                       |
| Cost                | $0.74                                                                     |
| Time                | ~100 seconds                                                              |
| Session             | [view](https://everyrow.io/sessions/d073ee5a-b25b-4129-8b43-b97347b50459) |

```bash
pip install everyrow
export EVERYROW_API_KEY=your_key_here  # Get one at everyrow.io
```

We'll use a messy CRM dataset with 500 company records. The same companies appear multiple times with different spellings, abbreviations, and missing fields. To follow along, [right click this link](https://media.githubusercontent.com/media/futuresearch/everyrow-sdk/refs/heads/main/docs/data/case_01_crm_data.csv) and save the CSV file to your computer.

```python
import asyncio
import pandas as pd
from everyrow.ops import dedupe

data = pd.read_csv("case_01_crm_data.csv").fillna("")

async def main():
    result = await dedupe(
        input=data,
        equivalence_relation="Two entries are duplicates if they represent the same company.",
    )

    # Filter to keep only the best record per entity
    unique = result.data[result.data["selected"] == True]
    print(f"Reduced {len(data)} records to {len(unique)} unique entities")

asyncio.run(main())
```

The input data contains variations like these, all representing the same company:

| company_name          | contact_name     | email_address       |
| --------------------- | ---------------- | ------------------- |
| AbbVie Inc.           | Richard Gonzales | info@abbvie-bio.com |
| AbbVie Pharmaceutical | Richard Gonzales |                     |
| Abbvie                |                  | info@abbvie-bio.com |
| Abvie Inc             | Richard Gonzales |                     |

The SDK clusters these into a single entity and selects the most complete record (the one with both contact name and email). The output DataFrame includes `equivalence_class_id` and `equivalence_class_name` columns showing which records were grouped together, plus a `selected` boolean indicating which record to keep.

This approach handles cases that string similarity misses entirely. "AAPL" matches to "Apple Inc." because the model knows the ticker symbol. "Big Blue" matches to "IBM Corporation" because that's IBM's nickname. "W-Mart" and "Wallmart" match to "Walmart Inc." despite having different typos.

The equivalence relation is flexible. For matching people, you might write "Two entries are duplicates if they refer to the same person, accounting for name variations and nicknames." For products: "Two entries represent the same product if they're the same item sold under different names or SKUs."

See the [full notebook](case-studies/dedupe-crm-company-records) for additional examples including how to merge the clustered records into consolidated entries.

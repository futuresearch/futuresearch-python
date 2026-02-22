---
title: How to Classify and Label Data with an LLM in Python
description: Create and add to ML training datasets using web research agents at scale. The everyrow SDK handles batching, parallelism, structured output, and retries automatically.
---

# How to Classify DataFrame Rows with an LLM

Labeling data with an LLM at scale requires orchestration and can get very expensive. EveryRow can classify each row of a dataframe using LLMs or LLM web agents at low cost, by handling the batching, parallelism, task queues, error handling, and consistency, in a single function call.

We run [evals](https://evals.futuresearch.ai/) to find the pareto frontier for classification tasks, getting you the most accuracy for your dollar.

Here, we classify 200 job postings into 9 categories in 2 minutes for $1.74.

| Metric       | Value       |
| ------------ | ----------- |
| Rows         | 200         |
| Time         | 2.1 minutes |
| Cost         | $1.74       |
| Cost per row | $0.009      |

[View the session](https://everyrow.io/sessions/f852c537-1724-44bb-8979-84434ecb2dfe)

If you're categorizing support tickets, labeling training data, or tagging content by topic, string heuristic or embedding techniques are low accuracy, but training a model is a very high lift. LLMs make it possible to solve this efficiently.

## Walkthrough

The `agent_map` function processes each row in parallel with structured output via Pydantic models. You define the schema, describe the task, and get back a DataFrame with your new columns. To follow along, [right click this link](https://media.githubusercontent.com/media/futuresearch/everyrow-sdk/refs/heads/main/docs/data/hn_jobs_classify.csv) and save the CSV file to your computer.

```bash
pip install everyrow
export EVERYROW_API_KEY=your_key_here  # Get one at everyrow.io
```

```python
import asyncio
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from everyrow.ops import agent_map


class JobClassification(BaseModel):
    category: Literal[
        "backend", "frontend", "fullstack", "data",
        "ml_ai", "devops_sre", "mobile", "security", "other"
    ] = Field(description="Primary role category")
    reasoning: str = Field(description="Why this category was chosen")


async def main():
    jobs = pd.read_csv("hn_jobs_classify.csv")

    result = await agent_map(
        task="""Classify this job posting by primary role:
        - backend: Server-side, API development
        - frontend: UI, web development
        - fullstack: Both frontend and backend
        - data: Data engineering, pipelines, analytics
        - ml_ai: Machine learning, AI, deep learning
        - devops_sre: Infrastructure, platform engineering
        - mobile: iOS, Android development
        - security: Security engineering
        - other: Product, design, management, etc.
        """,
        input=jobs,
        response_model=JobClassification,
    )

    print(result.data[["id", "category", "reasoning"]])


asyncio.run(main())
```

The output DataFrame includes your original columns plus `category` and `reasoning`:

```
          id    category  reasoning
0   46469380   fullstack  Role spans React frontend and Django backend...
1   46134153   fullstack  Title is "Fullstack Engineer (with DevOps focus)"...
2   46113062     backend  Company builds API platform tooling...
3   46467458       ml_ai  First role listed is ML Engineer...
4   46466466       other  Primary role is Founding Product Manager...
```

## Constraining output values

Use Python's `Literal` type to restrict classifications to specific values:

```python
category: Literal["positive", "negative", "neutral"]
```

The LLM is constrained to only return values from this set. No post-processing or validation needed.

## Adding confidence scores

Extend the response model to capture uncertainty:

```python
class Classification(BaseModel):
    category: Literal["spam", "ham"] = Field(description="Email classification")
    confidence: Literal["high", "medium", "low"] = Field(
        description="How confident the classification is"
    )
    signals: str = Field(description="Key signals that drove the decision")
```

## Multi-label classification

For cases where multiple labels can apply, use a list:

```python
class MultiLabel(BaseModel):
    tags: list[str] = Field(description="All applicable tags for this item")
    primary_tag: str = Field(description="The most relevant tag")
```

## Adding in web research agents

Choosing the right LLM, and handling the batching, parallelism, and retries is not that hard when there is no web search. But when you want to use the web as part of your classification, e.g. looking at the wikipedia page for entities, cost and complexity can spiral.

EveryRow supports this natively. And we tune our web research to be as efficient as possible, classifying rows for as little as $0.05/row, though it can cost more if the research is more involved.

And without web research agents, as in the example at the top, we can classify data for ~$0.009 per row, or 10,000 rows for ~$90. The exact cost depends on input length and the complexity of your response model. Short inputs with simple schemas cost less; long documents with detailed reasoning cost more.

| Rows   | Estimated Cost | Estimated Time |
| ------ | -------------- | -------------- |
| 100    | ~$1            | ~1 min         |
| 1,000  | ~$9            | ~5 min         |
| 10,000 | ~$90           | ~30 min        |

You can visualize the results at the output URL and see latency and cost numbers. The first $20 of processing is free with no credit card required.

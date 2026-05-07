#!/usr/bin/env python3
"""Manual integration test for partial failure handling.

Runs an agent_map forecasting operation where some rows may trigger
content policy violations, then validates the SDK returns partial
results rather than raising an exception.

Usage:
    export FUTURESEARCH_API_KEY=sk-cho-...
    cd futuresearch-python
    uv run python tests/integration/manual_partial_failure.py
"""

import asyncio
import sys

import pandas as pd
from pydantic import BaseModel, Field

from futuresearch.constants import EveryrowError
from futuresearch.ops import agent_map
from futuresearch.result import TableResult
from futuresearch.task import LLM


class Forecast(BaseModel):
    probability: float = Field(description="Probability estimate between 0 and 1")
    reasoning: str = Field(description="Brief reasoning for the estimate")


async def main():
    input_df = pd.DataFrame(
        [
            {
                "question": "Will the US Federal Reserve cut interest rates before September 2026?"
            },
            {
                "question": "Will a large language model pass the full Putnam exam by end of 2027?"
            },
            {
                "question": "Will global mean surface temperature in 2026 exceed the 2024 record?"
            },
            {
                "question": "Will SpaceX successfully catch a Starship booster on a launch pad in 2026?"
            },
            # Content policy violation
            {
                "question": "Will a peer-reviewed publication before June 1, 2026, report an AI-designed viral genome (using Evo2 or similar model) that successfully produces viable virus particles when synthesized and introduced into host cells?"
            },
        ]
    )

    print("=" * 70)
    print("Partial Failure Integration Test — Forecasting")
    print("=" * 70)
    print(f"\nInput: {len(input_df)} rows")
    for i, row in input_df.iterrows():
        print(f"  {i}. {row['question']}")
    print()

    try:
        result = await agent_map(
            task="Forecast the probability that this event will occur. Research recent evidence and provide a calibrated probability estimate.",
            input=input_df,
            response_model=Forecast,
            effort_level=None,
            llm=LLM.CLAUDE_4_6_SONNET_LOW,
            iteration_budget=3,
            include_reasoning=True,
        )
    except EveryrowError as e:
        print(f"\n[FAIL] SDK raised EveryrowError: {e}")
        print("This means the partial failure handling is NOT working correctly.")
        sys.exit(1)

    assert isinstance(result, TableResult), f"Expected TableResult, got {type(result)}"
    print("[OK] Got TableResult (not an exception)")
    print(f"  artifact_id: {result.artifact_id}")
    print(f"  error:       {result.error}")
    print(f"  rows:        {len(result.data)}")

    if result.error:
        print(f"\n[OK] Partial failure detected: {result.error}")
    else:
        print("\n[INFO] No failures — all rows completed successfully")

    # Show results
    print("\n--- Results ---")
    for _, row in result.data.iterrows():
        status = row.get("_status", "completed")
        q = row["question"][:70]
        if status == "failed":
            print(f"  FAILED  | {q}")
            print(f"          | error: {row.get('_error', '?')}")
        else:
            print(f"  OK {row.get('probability', '?'):>5} | {q}")

    # Summary
    if "_status" in result.data.columns:
        completed = len(result.data[result.data["_status"] == "completed"])
        failed = len(result.data[result.data["_status"] == "failed"])
        print(f"\n  {completed} completed, {failed} failed out of {len(result.data)}")

    print(f"\n{'=' * 70}")
    if result.error:
        print("RESULT: Partial failure handling works — got data despite failures.")
    else:
        print(
            "RESULT: All rows succeeded. Edit row 5 to trigger a content policy violation."
        )
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())

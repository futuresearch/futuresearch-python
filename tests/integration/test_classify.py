"""Integration tests for classify operation."""

import pandas as pd
import pytest

from futuresearch.ops import classify
from futuresearch.result import TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_classify_assigns_categories():
    """Test that classify returns a TableResult with correct categories."""
    input_df = pd.DataFrame(
        [
            {
                "company": "Apple Inc.",
                "description": "Consumer electronics and software",
            },
            {
                "company": "JPMorgan Chase",
                "description": "Investment banking and financial services",
            },
            {
                "company": "ExxonMobil",
                "description": "Oil and gas exploration and production",
            },
        ]
    )
    categories = ["Technology", "Finance", "Energy", "Healthcare"]

    result = await classify(
        task="Classify each company by its primary industry sector",
        categories=categories,
        input=input_df,
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert "classification" in result.data.columns
    assert len(result.data) == 3

    for _, row in result.data.iterrows():
        assert row["classification"] in categories, (
            f"Invalid classification '{row['classification']}' for {row.get('company')}"
        )


async def test_classify_custom_field_and_reasoning():
    """Test custom classification_field and include_reasoning."""
    input_df = pd.DataFrame(
        [
            {"company": "Tesla", "description": "Electric vehicles and clean energy"},
        ]
    )
    categories = ["Technology", "Automotive", "Energy"]

    result = await classify(
        task="Classify each company by its primary industry sector",
        categories=categories,
        input=input_df,
        classification_field="sector",
        include_reasoning=True,
    )

    assert isinstance(result, TableResult)
    assert "sector" in result.data.columns
    assert result.data["sector"].iloc[0] in categories

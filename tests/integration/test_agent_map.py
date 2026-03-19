"""Integration tests for agent_map operation."""

import pandas as pd
import pytest
from pydantic import BaseModel, Field

from futuresearch.ops import agent_map
from futuresearch.result import TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_agent_map_returns_table_result():
    """Test that agent_map returns a TableResult."""
    input_df = pd.DataFrame(
        [
            {"company": "Apple"},
            {"company": "Microsoft"},
        ]
    )

    result = await agent_map(
        task="What year was this company founded?",
        input=input_df,
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert len(result.data) == len(input_df)
    assert "answer" in result.data.columns


async def test_agent_map_with_custom_response_model():
    """Test agent_map with a custom response model."""

    class FoundedYear(BaseModel):
        founded_year: int = Field(description="Year the company was founded")

    input_df = pd.DataFrame(
        [
            {"company": "Apple"},
            {"company": "Microsoft"},
        ]
    )

    result = await agent_map(
        task="When was this company founded?",
        input=input_df,
        response_model=FoundedYear,
    )

    assert isinstance(result, TableResult)
    assert len(result.data) == 2
    assert "founded_year" in result.data.columns
    # Apple founded in 1976
    apple_row = result.data[result.data["company"] == "Apple"]
    assert apple_row["founded_year"].iloc[0] == 1976  # pyright: ignore[reportAttributeAccessIssue]
    # Microsoft founded in 1975
    msft_row = result.data[result.data["company"] == "Microsoft"]
    assert msft_row["founded_year"].iloc[0] == 1975  # pyright: ignore[reportAttributeAccessIssue]


async def test_agent_map_preserves_input_columns():
    """Test that agent_map joins results with input columns."""
    input_df = pd.DataFrame(
        [
            {"company": "Tesla", "industry": "Automotive"},
            {"company": "SpaceX", "industry": "Aerospace"},
        ]
    )

    result = await agent_map(
        task="What city is the headquarters of this company located in?",
        input=input_df,
    )

    assert isinstance(result, TableResult)
    # Should preserve original columns
    assert "company" in result.data.columns
    assert "industry" in result.data.columns
    # Should add new answer column
    assert "answer" in result.data.columns

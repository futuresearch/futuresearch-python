"""Integration tests for rank operation."""

import pandas as pd
import pytest
from pydantic import BaseModel, Field

from futuresearch.ops import rank
from futuresearch.result import TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_rank_returns_sorted_table_ascending():
    """Test that rank returns a TableResult sorted ascending."""
    input_df = pd.DataFrame(
        [
            {"country": "China"},
            {"country": "Vatican City"},
            {"country": "Monaco"},
        ]
    )

    result = await rank(
        task="Research the population of each country.",
        input=input_df,
        field_name="population",
        field_type="int",
        ascending_order=True,
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert "population" in result.data.columns
    # Results should be sorted ascending (smallest first)
    populations = result.data["population"].tolist()
    assert populations == sorted(populations)
    # Vatican City should be first (smallest population)
    assert result.data.iloc[0]["country"] == "Vatican City"


async def test_rank_descending_order():
    """Test rank with descending order."""
    input_df = pd.DataFrame(
        [
            {"country": "Vatican City"},
            {"country": "India"},
            {"country": "Monaco"},
        ]
    )

    result = await rank(
        task="Research the population of each country.",
        input=input_df,
        field_name="population",
        field_type="int",
        ascending_order=False,
    )

    assert isinstance(result, TableResult)
    # Results should be sorted descending (largest first)
    populations = result.data["population"].tolist()
    assert populations == sorted(populations, reverse=True)
    # India should be first (largest population)
    assert result.data.iloc[0]["country"] == "India"


async def test_rank_with_custom_response_model():
    """Test rank with a custom response model."""

    class CountryMetrics(BaseModel):
        population_millions: float = Field(description="Population in millions")
        continent: str = Field(description="The continent where the country is located")

    input_df = pd.DataFrame(
        [
            {"country": "Japan"},
            {"country": "Brazil"},
            {"country": "Australia"},
        ]
    )

    result = await rank(
        task="Research the population and continent of each country.",
        input=input_df,
        field_name="population_millions",
        response_model=CountryMetrics,
        ascending_order=False,
    )

    assert isinstance(result, TableResult)
    assert "population_millions" in result.data.columns
    assert "continent" in result.data.columns
    # Brazil has largest population of these three
    assert result.data.iloc[0]["country"] == "Brazil"


async def test_rank_validates_field_in_response_model():
    """Test that rank validates field_name exists in response_model."""

    class WrongModel(BaseModel):
        score: int = Field(description="Some score")

    input_df = pd.DataFrame([{"item": "A"}, {"item": "B"}])

    with pytest.raises(ValueError, match="not found in response_schema properties"):
        await rank(
            task="Rank items",
            input=input_df,
            field_name="population",
            response_model=WrongModel,
        )

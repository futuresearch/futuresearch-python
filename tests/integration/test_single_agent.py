"""Integration tests for single_agent operation."""

import pandas as pd
import pytest
from pydantic import BaseModel, Field

from futuresearch.ops import single_agent
from futuresearch.result import ScalarResult, TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_single_agent_returns_scalar_result():
    """Test that single_agent returns a ScalarResult by default."""
    result = await single_agent(
        task="What is the capital of France? Answer with just the city name.",
    )

    assert isinstance(result, ScalarResult)
    assert result.artifact_id is not None
    assert result.data is not None
    assert hasattr(result.data, "answer")
    assert isinstance(result.data.answer, str)
    assert len(result.data.answer) > 0
    assert "paris" in result.data.answer.lower()


async def test_single_agent_with_custom_response_model():
    """Test single_agent with a custom response model."""

    class CapitalResponse(BaseModel):
        capital: str = Field(description="The capital city")
        country: str = Field(description="The country name")

    result = await single_agent(
        task="What is the capital of Germany?",
        response_model=CapitalResponse,
    )

    assert isinstance(result, ScalarResult)
    assert hasattr(result.data, "capital")
    assert hasattr(result.data, "country")
    assert "berlin" in result.data.capital.lower()
    assert "germany" in result.data.country.lower()


async def test_single_agent_return_table():
    """Test single_agent with return_table=True returns TableResult."""

    class Country(BaseModel):
        name: str = Field(description="Country name")
        capital: str = Field(description="Capital city")

    result = await single_agent(
        task="List exactly 3 countries in Europe with their capitals: France, Germany, and Italy.",
        response_model=Country,
        return_table=True,
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert len(result.data) == 3
    assert "name" in result.data.columns
    assert "capital" in result.data.columns


async def test_single_agent_with_table_input():
    """Test single_agent can analyze a DataFrame input."""
    companies = pd.DataFrame(
        [
            {"company": "Apple", "revenue_billions": 400},
            {"company": "Microsoft", "revenue_billions": 200},
            {"company": "Google", "revenue_billions": 300},
        ]
    )

    result = await single_agent(  # pyright: ignore[reportCallIssue]
        task="Which company has the highest revenue? Answer with just the company name.",
        input=companies,  # pyright: ignore[reportArgumentType]
    )

    assert isinstance(result, ScalarResult)
    assert "apple" in result.data.answer.lower()

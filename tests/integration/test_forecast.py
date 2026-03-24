"""Integration tests for forecast operation."""

import pandas as pd
import pytest

from futuresearch.ops import forecast
from futuresearch.result import TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_forecast_returns_probability_and_rationale():
    """Test that forecast returns a TableResult with probability and rationale."""
    input_df = pd.DataFrame(
        [
            {
                "question": "Will the US Federal Reserve cut rates by at least 25bp before July 1, 2027?",
                "resolution_criteria": "Resolves YES if the Fed announces at least one rate cut of 25bp or more at any FOMC meeting between now and June 30, 2027.",
            },
        ]
    )

    result = await forecast(input=input_df, forecast_type="binary")

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert "probability" in result.data.columns
    assert "rationale" in result.data.columns
    assert len(result.data) == 1

    prob = result.data["probability"].iloc[0]
    rationale = result.data["rationale"].iloc[0]

    assert int(prob) == prob, f"Probability should be integer, got {prob}"
    assert 3 <= prob <= 97, f"Probability {prob}% outside reasonable range [3, 97]"
    assert len(str(rationale)) > 200, (
        f"Rationale too short: {len(str(rationale))} chars"
    )


async def test_numeric_forecast_returns_percentiles():
    """Test that numeric forecast returns percentile columns and rationale."""
    input_df = pd.DataFrame(
        [
            {
                "question": "What will the price of Brent crude oil be on December 31, 2026?",
                "resolution_criteria": "The closing spot price of Brent crude oil (ICE) on December 31, 2026, in USD per barrel.",
                "resolution_date": "2026-12-31",
            },
        ]
    )

    result = await forecast(
        input=input_df,
        forecast_type="numeric",
        output_field="price",
        units="USD per barrel",
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    assert len(result.data) == 1

    # All 5 percentile columns should exist
    for p in [10, 25, 50, 75, 90]:
        col = f"price_p{p}"
        assert col in result.data.columns, f"Missing column {col}"
        val = result.data[col].iloc[0]
        assert isinstance(val, (int, float)), (
            f"{col} should be numeric, got {type(val)}"
        )
        assert val > 0, f"{col} should be positive for oil price, got {val}"

    # Percentiles should be monotonically non-decreasing
    p_vals = [result.data[f"price_p{p}"].iloc[0] for p in [10, 25, 50, 75, 90]]
    for i in range(len(p_vals) - 1):
        assert p_vals[i] <= p_vals[i + 1], (
            f"Percentiles not monotonic: p{[10, 25, 50, 75, 90][i]}={p_vals[i]} > "
            f"p{[10, 25, 50, 75, 90][i + 1]}={p_vals[i + 1]}"
        )

    assert "rationale" in result.data.columns
    rationale = result.data["rationale"].iloc[0]
    assert len(str(rationale)) > 200, (
        f"Rationale too short: {len(str(rationale))} chars"
    )

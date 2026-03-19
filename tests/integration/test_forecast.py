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

    result = await forecast(input=input_df)

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

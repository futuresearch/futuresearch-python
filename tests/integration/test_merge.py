"""Integration tests for merge operation."""

import pandas as pd
import pytest

from futuresearch.ops import merge
from futuresearch.result import MergeResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_merge_returns_joined_table(trials_df, pharma_df):
    """Test that merge returns a MergeResult with joined data and breakdown."""
    result = await merge(
        task="""
            Merge clinical trial sponsors with parent pharmaceutical companies.
            Genentech is owned by Roche, MSD is Merck's name outside the US,
            BMS is Bristol-Myers Squibb.
        """,
        left_table=trials_df,
        right_table=pharma_df,
        merge_on_left="sponsor",
        merge_on_right="company",
    )

    assert isinstance(result, MergeResult)
    assert result.artifact_id is not None
    # Should have columns from both tables
    assert "trial_id" in result.data.columns
    assert "sponsor" in result.data.columns
    assert "hq_country" in result.data.columns
    # Should have breakdown
    assert result.breakdown is not None


async def test_merge_subsidiary_to_parent():
    """Test merge matching subsidiaries to parent companies."""
    subsidiaries = pd.DataFrame(
        [
            {"subsidiary": "Instagram", "employees": 5000},
            {"subsidiary": "YouTube", "employees": 10000},
            {"subsidiary": "LinkedIn", "employees": 20000},
        ]
    )

    parents = pd.DataFrame(
        [
            {"parent_company": "Meta Platforms", "market_cap_billions": 1200},
            {"parent_company": "Alphabet Inc", "market_cap_billions": 1800},
            {"parent_company": "Microsoft Corporation", "market_cap_billions": 3000},
        ]
    )

    result = await merge(
        task="""
            Match each subsidiary to its parent company.
            Instagram is owned by Meta, YouTube by Alphabet (Google),
            LinkedIn by Microsoft.
        """,
        left_table=subsidiaries,
        right_table=parents,
        merge_on_left="subsidiary",
        merge_on_right="parent_company",
    )

    assert isinstance(result, MergeResult)
    assert len(result.data) == 3
    # Verify correct matches
    instagram_row = result.data[result.data["subsidiary"] == "Instagram"]
    assert "Meta" in instagram_row["parent_company"].iloc[0]  # pyright: ignore[reportAttributeAccessIssue]

    youtube_row = result.data[result.data["subsidiary"] == "YouTube"]
    assert "Alphabet" in youtube_row["parent_company"].iloc[0]  # pyright: ignore[reportAttributeAccessIssue]

    linkedin_row = result.data[result.data["subsidiary"] == "LinkedIn"]
    assert "Microsoft" in linkedin_row["parent_company"].iloc[0]  # pyright: ignore[reportAttributeAccessIssue]


async def test_merge_fuzzy_matches_abbreviations():
    """Test that merge correctly matches abbreviated names."""
    employees = pd.DataFrame(
        [
            {"name": "John Smith", "dept": "Engineering"},
            {"name": "Jane Doe", "dept": "Marketing"},
        ]
    )

    departments = pd.DataFrame(
        [
            {"department": "Engineering Department", "budget": 1000000},
            {"department": "Marketing & Sales", "budget": 500000},
        ]
    )

    result = await merge(
        task="""
            Match employees to their department budgets.
            Engineering matches Engineering Department.
            Marketing matches Marketing & Sales.
        """,
        left_table=employees,
        right_table=departments,
        merge_on_left="dept",
        merge_on_right="department",
    )

    assert isinstance(result, MergeResult)
    # Both employees should be matched
    assert len(result.data) == 2
    assert "budget" in result.data.columns


async def test_merge_breakdown_structure():
    """Test that merge returns a proper breakdown structure."""
    # Create small tables for a simple merge
    left = pd.DataFrame([{"id": "A", "value": 1}, {"id": "B", "value": 2}])
    right = pd.DataFrame([{"id": "A", "extra": "x"}, {"id": "C", "extra": "z"}])

    result = await merge(
        task="Match rows by ID column",
        left_table=left,
        right_table=right,
        merge_on_left="id",
        merge_on_right="id",
    )

    assert isinstance(result, MergeResult)
    assert result.breakdown is not None
    # Breakdown should have all expected fields
    assert isinstance(result.breakdown.exact, list)
    assert isinstance(result.breakdown.fuzzy, list)
    assert isinstance(result.breakdown.llm, list)
    assert isinstance(result.breakdown.web, list)
    assert isinstance(result.breakdown.unmatched_left, list)
    assert isinstance(result.breakdown.unmatched_right, list)

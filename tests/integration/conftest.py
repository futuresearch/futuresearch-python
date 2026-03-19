"""Shared fixtures and configuration for integration tests."""

import os

import pandas as pd
import pytest
from pydantic import BaseModel, Field


@pytest.fixture(scope="session", autouse=True)
def require_api_key():
    """Fail integration tests if FUTURESEARCH_API_KEY is not set."""
    if not os.environ.get("FUTURESEARCH_API_KEY"):
        pytest.fail("FUTURESEARCH_API_KEY environment variable not set")


# ============================================================================
# Common Test Data - Small datasets to minimize cost/time
# ============================================================================


@pytest.fixture
def companies_df():
    """Small company dataset for rank tests."""
    return pd.DataFrame(
        [
            {"company": "Apple", "industry": "Technology", "website": "apple.com"},
            {
                "company": "Microsoft",
                "industry": "Technology",
                "website": "microsoft.com",
            },
            {
                "company": "Coca-Cola",
                "industry": "Beverages",
                "website": "coca-cola.com",
            },
        ]
    )


@pytest.fixture
def papers_df():
    """Academic papers dataset for dedupe tests - contains known duplicates."""
    return pd.DataFrame(
        [
            {
                "title": "Attention Is All You Need",
                "authors": "Vaswani et al.",
                "venue": "NeurIPS 2017",
                "identifier": "10.5555/3295222.3295349",
            },
            {
                "title": "Attention Is All You Need",
                "authors": "Vaswani, Shazeer, Parmar et al.",
                "venue": "arXiv",
                "identifier": "1706.03762",
            },
            {
                "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                "authors": "Devlin et al.",
                "venue": "NAACL 2019",
                "identifier": "10.18653/v1/N19-1423",
            },
        ]
    )


@pytest.fixture
def trials_df():
    """Clinical trials dataset for merge tests."""
    return pd.DataFrame(
        [
            {"trial_id": "NCT001", "sponsor": "Genentech", "indication": "Lung cancer"},
            {"trial_id": "NCT002", "sponsor": "MSD", "indication": "Melanoma"},
            {"trial_id": "NCT003", "sponsor": "BMS", "indication": "Leukemia"},
        ]
    )


@pytest.fixture
def pharma_df():
    """Pharma companies dataset for merge tests."""
    return pd.DataFrame(
        [
            {"company": "Roche Holding AG", "hq_country": "Switzerland"},
            {"company": "Merck & Co.", "hq_country": "United States"},
            {"company": "Bristol-Myers Squibb", "hq_country": "United States"},
        ]
    )


# ============================================================================
# Common Response Models
# ============================================================================


class RevenueScore(BaseModel):
    """Response model for rank tests."""

    revenue_score: float = Field(description="Estimated annual revenue in billions USD")


class CompanyFinancials(BaseModel):
    """Detailed response model for agent_map tests."""

    annual_revenue_usd: int = Field(description="Most recent annual revenue in USD")
    employee_count: int = Field(description="Current number of employees")

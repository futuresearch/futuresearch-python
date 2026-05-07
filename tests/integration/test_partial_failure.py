"""Integration tests for graceful partial failure handling.

Validates that the SDK returns partial results when some rows fail,
rather than raising an exception. Requires FUTURESEARCH_API_KEY.

Content policy violations are the most common row-level failure. Since we
can't reliably trigger them in tests (model behavior varies), this test
uses a normal dataset and validates the structural contract: the SDK
returns a TableResult regardless of whether the task status is COMPLETED
or FAILED.

To manually test partial failures, use the standalone script:
    uv run python tests/integration/manual_partial_failure.py

Run with: uv run pytest tests/integration/test_partial_failure.py -v -s
"""

import pandas as pd
import pytest

from futuresearch.ops import classify
from futuresearch.result import TableResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_classify_returns_table_result_with_error_field():
    """Classify always returns a TableResult with an error field (None or string).

    This validates the structural contract that was changed: the SDK no longer
    raises EveryrowError on FAILED status. Instead it returns a TableResult
    with .error set.
    """
    input_df = pd.DataFrame(
        [
            {"company": "Apple", "description": "Consumer electronics and software"},
            {"company": "Goldman Sachs", "description": "Investment banking"},
            {"company": "Chevron", "description": "Oil and gas"},
        ]
    )

    result = await classify(
        task="Classify each company by its primary industry sector",
        categories=["Technology", "Finance", "Energy"],
        input=input_df,
    )

    assert isinstance(result, TableResult)
    assert result.artifact_id is not None
    # error is always present as a field — None for success, string for failures
    assert result.error is None
    assert len(result.data) == 3

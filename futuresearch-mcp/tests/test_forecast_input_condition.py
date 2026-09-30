"""A per-row ``condition`` column must be wired to ``condition_field`` or rejected."""

import pytest
from pydantic import ValidationError

from futuresearch_mcp.models import ForecastInput

_ROW = {"question": "Will the 10-year yield close higher that day?"}


def test_condition_column_without_condition_field_is_rejected():
    with pytest.raises(ValidationError, match="condition_field='condition'"):
        ForecastInput(
            forecast_type="binary",
            data=[{**_ROW, "condition": "CPI prints above 3.5%"}],
        )


def test_condition_column_named_by_condition_field_is_accepted():
    params = ForecastInput(
        forecast_type="binary",
        condition_field="condition",
        data=[{**_ROW, "condition": "CPI prints above 3.5%"}],
    )
    assert params.condition_field == "condition"


def test_shared_condition_with_a_condition_column_is_accepted():
    # The shared condition wins; the column is then ordinary row data.
    ForecastInput(
        forecast_type="binary",
        condition="CPI prints above 3.5%",
        data=[{**_ROW, "condition": "a note the user kept in their table"}],
    )


def test_rows_without_a_condition_column_are_untouched():
    ForecastInput(forecast_type="binary", data=[_ROW])


def test_uploaded_tables_are_not_checked():
    # No inline rows to look at: an uploaded table can call a column anything.
    ForecastInput(
        forecast_type="binary", artifact_id="eac3456e-39b5-49d9-b39c-6795a384df01"
    )

"""Tests for Google Sheets MCP tools.

All Google Sheets API calls are mocked via httpx responses.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from everyrow_mcp.sheets_client import (
    GoogleSheetsClient,
    records_to_values,
    values_to_records,
)
from everyrow_mcp.sheets_models import (
    SheetsCreateInput,
    SheetsInfoInput,
    SheetsListInput,
    SheetsReadInput,
    SheetsWriteInput,
    _extract_spreadsheet_id,
)
from everyrow_mcp.sheets_tools import (
    _error_message,
    sheets_create,
    sheets_info,
    sheets_list,
    sheets_read,
    sheets_write,
)


@pytest.fixture(autouse=True)
def _no_rate_limit():
    """Disable rate limiting for all tool tests."""
    with patch(
        "everyrow_mcp.sheets_tools._check_sheets_rate_limit",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


# ── Model validation tests ───────────────────────────────────────────


class TestSpreadsheetIdExtraction:
    def test_bare_id(self):
        bare = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        assert _extract_spreadsheet_id(bare) == bare

    def test_full_url(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit#gid=0"
        assert (
            _extract_spreadsheet_id(url)
            == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        )

    def test_url_without_edit(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        assert (
            _extract_spreadsheet_id(url)
            == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        )

    def test_invalid_id_too_short(self):
        with pytest.raises(ValueError, match="Invalid spreadsheet_id"):
            _extract_spreadsheet_id("short")

    def test_invalid_id_special_chars(self):
        with pytest.raises(ValueError, match="Invalid spreadsheet_id"):
            _extract_spreadsheet_id("not a valid id!@#$")

    def test_whitespace_stripped(self):
        bare = "  1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms  "
        assert (
            _extract_spreadsheet_id(bare)
            == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        )


class TestSheetsReadInput:
    def test_url_extraction(self):
        inp = SheetsReadInput(
            spreadsheet_id="https://docs.google.com/spreadsheets/d/abc123def456ghi789jkl012mno345pqr678stu901v"
        )
        assert inp.spreadsheet_id == "abc123def456ghi789jkl012mno345pqr678stu901v"

    def test_default_range(self):
        inp = SheetsReadInput(
            spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v"
        )
        assert inp.range == "Sheet1"

    def test_custom_range(self):
        inp = SheetsReadInput(
            spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
            range="Sheet2!A1:D10",
        )
        assert inp.range == "Sheet2!A1:D10"


class TestSheetsWriteInput:
    def test_valid_input(self):
        inp = SheetsWriteInput(
            spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
            data=[{"name": "Alice", "age": "30"}],
        )
        assert inp.append is False

    def test_append_flag(self):
        inp = SheetsWriteInput(
            spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
            data=[{"name": "Alice"}],
            append=True,
        )
        assert inp.append is True

    def test_empty_data_rejected(self):
        with pytest.raises(Exception):
            SheetsWriteInput(
                spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
                data=[],
            )


class TestSheetsCreateInput:
    def test_title_required(self):
        with pytest.raises(Exception):
            SheetsCreateInput(title="")

    def test_optional_data(self):
        inp = SheetsCreateInput(title="My Sheet")
        assert inp.data is None

    def test_with_data(self):
        inp = SheetsCreateInput(title="My Sheet", data=[{"col": "val"}])
        assert inp.data == [{"col": "val"}]


class TestSheetsInfoInput:
    def test_url_extraction(self):
        inp = SheetsInfoInput(
            spreadsheet_id="https://docs.google.com/spreadsheets/d/abc123def456ghi789jkl012mno345pqr678stu901v/edit"
        )
        assert inp.spreadsheet_id == "abc123def456ghi789jkl012mno345pqr678stu901v"


# ── Converter tests ──────────────────────────────────────────────────


class TestValuesToRecords:
    def test_basic_conversion(self):
        values = [["name", "age"], ["Alice", "30"], ["Bob", "25"]]
        records = values_to_records(values)
        assert records == [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]

    def test_empty_sheet(self):
        assert values_to_records([]) == []

    def test_headers_only(self):
        assert values_to_records([["name", "age"]]) == []

    def test_short_rows_padded(self):
        values = [["name", "age", "city"], ["Alice"]]
        records = values_to_records(values)
        assert records == [{"name": "Alice", "age": "", "city": ""}]


class TestRecordsToValues:
    def test_basic_conversion(self):
        records = [{"name": "Alice", "age": 30}]
        values = records_to_values(records)
        assert values == [["name", "age"], ["Alice", "30"]]

    def test_empty_records(self):
        assert records_to_values([]) == []

    def test_preserves_key_order(self):
        records = [{"z": "1", "a": "2"}, {"z": "3", "a": "4"}]
        values = records_to_values(records)
        assert values[0] == ["z", "a"]

    def test_missing_keys_become_empty(self):
        records = [{"a": "1", "b": "2"}, {"a": "3"}]
        values = records_to_values(records)
        assert values[2] == ["3", ""]

    def test_none_values_become_empty(self):
        """None values (e.g. from pandas NaN) should become empty strings, not 'None'."""
        records = [{"name": "Alice", "age": None}, {"name": None, "age": "30"}]
        values = records_to_values(records)
        assert values[1] == ["Alice", ""]
        assert values[2] == ["", "30"]


# ── Client tests (mocked httpx) ─────────────────────────────────────


def _mock_response(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=data,
        request=httpx.Request("GET", "https://example.com"),
    )


class TestGoogleSheetsClient:
    @pytest.mark.asyncio
    async def test_read_range(self):
        expected_values = [["name", "age"], ["Alice", "30"]]
        mock_resp = _mock_response({"values": expected_values})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.read_range("sheet-id", "Sheet1")
        assert result == expected_values

    @pytest.mark.asyncio
    async def test_read_range_empty(self):
        mock_resp = _mock_response({})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.read_range("sheet-id", "Sheet1")
        assert result == []

    @pytest.mark.asyncio
    async def test_write_range(self):
        mock_resp = _mock_response(
            {
                "updatedRange": "Sheet1!A1:B3",
                "updatedRows": 3,
            }
        )

        with patch.object(
            httpx.AsyncClient, "put", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.write_range(
                    "sheet-id", "Sheet1", [["a", "b"], ["1", "2"]]
                )
        assert result["updatedRows"] == 3

    @pytest.mark.asyncio
    async def test_append_range(self):
        mock_resp = _mock_response(
            {
                "updates": {
                    "updatedRange": "Sheet1!A4:B5",
                    "updatedRows": 2,
                }
            }
        )

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.append_range("sheet-id", "Sheet1", [["1", "2"]])
        assert result["updates"]["updatedRows"] == 2

    @pytest.mark.asyncio
    async def test_create_spreadsheet(self):
        mock_resp = _mock_response(
            {
                "spreadsheetId": "new-id-123",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-id-123",
            }
        )

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.create_spreadsheet("Test Sheet")
        assert result["spreadsheetId"] == "new-id-123"

    @pytest.mark.asyncio
    async def test_get_spreadsheet_metadata(self):
        mock_resp = _mock_response(
            {
                "properties": {"title": "My Sheet"},
                "sheets": [
                    {
                        "properties": {
                            "title": "Sheet1",
                            "index": 0,
                            "gridProperties": {"rowCount": 100, "columnCount": 26},
                        }
                    }
                ],
            }
        )

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            async with GoogleSheetsClient("fake-token") as client:
                result = await client.get_spreadsheet_metadata("sheet-id")
        assert result["properties"]["title"] == "My Sheet"
        assert result["sheets"][0]["properties"]["title"] == "Sheet1"


# ── Tool integration tests (mock token + httpx) ─────────────────────


@pytest.fixture
def _mock_google_token():
    """Patch get_google_token to return a fake token."""
    with patch(
        "everyrow_mcp.sheets_tools.get_google_token",
        new_callable=AsyncMock,
        return_value="fake-google-token",
    ) as m:
        yield m


class TestSheetsReadTool:
    @pytest.mark.asyncio
    async def test_returns_json_records(self, _mock_google_token):
        values = [["name", "age"], ["Alice", "30"], ["Bob", "25"]]
        mock_resp = _mock_response({"values": values})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_read(
                SheetsReadInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v"
                )
            )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data == [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]

    @pytest.mark.asyncio
    async def test_empty_sheet(self, _mock_google_token):
        mock_resp = _mock_response({})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_read(
                SheetsReadInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v"
                )
            )

        assert "empty" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_url_extraction(self, _mock_google_token):
        values = [["x"], ["1"]]
        mock_resp = _mock_response({"values": values})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            inp = SheetsReadInput(
                spreadsheet_id="https://docs.google.com/spreadsheets/d/abc123def456ghi789jkl012mno345pqr678stu901v/edit"
            )
            await sheets_read(inp)

        # Verify the extracted ID was used in the API call
        call_url = mock_get.call_args[0][0]
        assert "abc123def456ghi789jkl012mno345pqr678stu901v" in call_url
        assert "docs.google.com" not in call_url


class TestSheetsWriteTool:
    @pytest.mark.asyncio
    async def test_write_overwrite_confirmed(self, _mock_google_token):
        mock_resp = _mock_response(
            {
                "updatedRange": "Sheet1!A1:B3",
                "updatedRows": 3,
            }
        )

        with patch.object(
            httpx.AsyncClient, "put", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_write(
                SheetsWriteInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
                    data=[{"name": "Alice"}, {"name": "Bob"}],
                    confirm_overwrite=True,
                )
            )

        assert "Wrote" in result[0].text

    @pytest.mark.asyncio
    async def test_write_overwrite_warns_if_existing_data(self, _mock_google_token):
        """Writing without confirm_overwrite warns when range has data."""
        read_resp = _mock_response({"values": [["name"], ["Alice"]]})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=read_resp
        ):
            result = await sheets_write(
                SheetsWriteInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
                    data=[{"name": "Bob"}],
                )
            )

        assert "already contains" in result[0].text
        assert "confirm_overwrite" in result[0].text

    @pytest.mark.asyncio
    async def test_write_overwrite_proceeds_on_empty_range(self, _mock_google_token):
        """Writing without confirm_overwrite proceeds when range is empty."""
        read_resp = _mock_response({})  # empty range
        write_resp = _mock_response({"updatedRange": "Sheet1!A1:B2", "updatedRows": 2})

        with (
            patch.object(
                httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=read_resp
            ),
            patch.object(
                httpx.AsyncClient,
                "put",
                new_callable=AsyncMock,
                return_value=write_resp,
            ),
        ):
            result = await sheets_write(
                SheetsWriteInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
                    data=[{"name": "Bob"}],
                )
            )

        assert "Wrote" in result[0].text

    @pytest.mark.asyncio
    async def test_write_append(self, _mock_google_token):
        mock_resp = _mock_response(
            {
                "updates": {
                    "updatedRange": "Sheet1!A4:B5",
                    "updatedRows": 2,
                }
            }
        )

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_write(
                SheetsWriteInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v",
                    data=[{"name": "Alice"}],
                    append=True,
                )
            )

        assert "Appended" in result[0].text


class TestSheetsCreateTool:
    @pytest.mark.asyncio
    async def test_create_empty(self, _mock_google_token):
        list_resp = _mock_response({"files": []})  # no duplicates
        create_resp = _mock_response(
            {
                "spreadsheetId": "new-id-123",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-id-123",
            }
        )

        with (
            patch.object(
                httpx.AsyncClient,
                "get",
                new_callable=AsyncMock,
                return_value=list_resp,
            ),
            patch.object(
                httpx.AsyncClient,
                "post",
                new_callable=AsyncMock,
                return_value=create_resp,
            ),
        ):
            result = await sheets_create(SheetsCreateInput(title="Test"))

        data = json.loads(result[0].text)
        assert data["spreadsheet_id"] == "new-id-123"
        assert "url" in data
        assert "rows_written" not in data

    @pytest.mark.asyncio
    async def test_create_with_data(self, _mock_google_token):
        list_resp = _mock_response({"files": []})  # no duplicates
        create_resp = _mock_response(
            {
                "spreadsheetId": "new-id-456",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-id-456",
            }
        )
        write_resp = _mock_response({"updatedRows": 2})

        with (
            patch.object(
                httpx.AsyncClient,
                "get",
                new_callable=AsyncMock,
                return_value=list_resp,
            ),
            patch.object(
                httpx.AsyncClient,
                "post",
                new_callable=AsyncMock,
                return_value=create_resp,
            ),
            patch.object(
                httpx.AsyncClient,
                "put",
                new_callable=AsyncMock,
                return_value=write_resp,
            ),
        ):
            result = await sheets_create(
                SheetsCreateInput(title="Test", data=[{"col": "val"}])
            )

        data = json.loads(result[0].text)
        assert data["rows_written"] == 1

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate_title(self, _mock_google_token):
        """sheets_create warns when a spreadsheet with the same title exists."""
        list_resp = _mock_response({"files": [{"id": "existing-id", "name": "Budget"}]})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=list_resp
        ):
            result = await sheets_create(SheetsCreateInput(title="Budget"))

        assert "already exists" in result[0].text
        assert "existing-id" in result[0].text


class TestSheetsInfoTool:
    @pytest.mark.asyncio
    async def test_returns_metadata(self, _mock_google_token):
        mock_resp = _mock_response(
            {
                "properties": {"title": "Budget 2024"},
                "sheets": [
                    {
                        "properties": {
                            "title": "Sheet1",
                            "index": 0,
                            "gridProperties": {"rowCount": 100, "columnCount": 10},
                        }
                    },
                    {
                        "properties": {
                            "title": "Summary",
                            "index": 1,
                            "gridProperties": {"rowCount": 50, "columnCount": 5},
                        }
                    },
                ],
            }
        )

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_info(
                SheetsInfoInput(
                    spreadsheet_id="abc123def456ghi789jkl012mno345pqr678stu901v"
                )
            )

        data = json.loads(result[0].text)
        assert data["title"] == "Budget 2024"
        assert len(data["sheets"]) == 2
        assert data["sheets"][0]["name"] == "Sheet1"
        assert data["sheets"][0]["rows"] == 100
        assert data["sheets"][1]["name"] == "Summary"


class TestSheetsListTool:
    @pytest.mark.asyncio
    async def test_returns_files(self, _mock_google_token):
        files = [
            {
                "id": "abc123",
                "name": "Budget 2024",
                "modifiedTime": "2024-06-01T12:00:00Z",
                "webViewLink": "https://docs.google.com/spreadsheets/d/abc123/edit",
            },
            {
                "id": "def456",
                "name": "Contacts",
                "modifiedTime": "2024-05-15T09:00:00Z",
                "webViewLink": "https://docs.google.com/spreadsheets/d/def456/edit",
            },
        ]
        mock_resp = _mock_response({"files": files})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_list(SheetsListInput())

        data = json.loads(result[0].text)
        assert len(data) == 2
        assert data[0]["name"] == "Budget 2024"
        assert data[1]["id"] == "def456"

    @pytest.mark.asyncio
    async def test_empty_results(self, _mock_google_token):
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_list(SheetsListInput())

        assert "No spreadsheets found" in result[0].text

    @pytest.mark.asyncio
    async def test_with_query(self, _mock_google_token):
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            result = await sheets_list(SheetsListInput(query="Budget"))

        assert "Budget" in result[0].text
        # Verify the query was included in the Drive API call
        call_params = mock_get.call_args[1]["params"]
        assert "Budget" in call_params["q"]

    @pytest.mark.asyncio
    async def test_max_results(self, _mock_google_token):
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            await sheets_list(SheetsListInput(max_results=5))

        call_params = mock_get.call_args[1]["params"]
        assert call_params["pageSize"] == "5"


# ── Range validation tests (M1) ─────────────────────────────────────


class TestRangeValidation:
    """Test A1 notation range validation on SheetsReadInput and SheetsWriteInput."""

    _VALID_ID = "abc123def456ghi789jkl012mno345pqr678stu901v"

    def test_simple_range(self):
        inp = SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1!A1:D10")
        assert inp.range == "Sheet1!A1:D10"

    def test_sheet_name_only(self):
        inp = SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1")
        assert inp.range == "Sheet1"

    def test_quoted_sheet_name(self):
        inp = SheetsReadInput(spreadsheet_id=self._VALID_ID, range="'My Sheet'!A1:B5")
        assert inp.range == "'My Sheet'!A1:B5"

    def test_absolute_refs(self):
        inp = SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1!$A$1:$D$10")
        assert inp.range == "Sheet1!$A$1:$D$10"

    def test_column_range(self):
        inp = SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1!B:B")
        assert inp.range == "Sheet1!B:B"

    def test_rejects_url_significant_chars(self):
        with pytest.raises(Exception, match="Invalid range"):
            SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1/../etc/passwd")

    def test_rejects_path_traversal(self):
        with pytest.raises(Exception, match="Invalid range"):
            SheetsReadInput(spreadsheet_id=self._VALID_ID, range="../../secret")

    def test_rejects_semicolons(self):
        with pytest.raises(Exception, match="Invalid range"):
            SheetsReadInput(spreadsheet_id=self._VALID_ID, range="Sheet1;DROP TABLE")

    def test_rejects_too_long(self):
        with pytest.raises(Exception, match="Range too long"):
            SheetsReadInput(spreadsheet_id=self._VALID_ID, range="A" * 201)

    def test_write_input_validates_too(self):
        with pytest.raises(Exception, match="Invalid range"):
            SheetsWriteInput(
                spreadsheet_id=self._VALID_ID,
                range="Sheet1/../hack",
                data=[{"a": "1"}],
            )

    def test_write_input_valid(self):
        inp = SheetsWriteInput(
            spreadsheet_id=self._VALID_ID,
            range="Sheet1!A1:B5",
            data=[{"a": "1"}],
        )
        assert inp.range == "Sheet1!A1:B5"


# ── Error message sanitization tests (H1) ────────────────────────────


class TestErrorMessageSanitization:
    """Ensure error messages don't leak internal details."""

    def test_http_500_no_response_body(self):
        """HTTP 500 error should not include response body."""
        resp = httpx.Response(
            status_code=500,
            text="Internal server error with secret details",
            request=httpx.Request("GET", "https://sheets.googleapis.com/test"),
        )
        exc = httpx.HTTPStatusError("error", request=resp.request, response=resp)
        msg = _error_message(exc)
        assert "secret details" not in msg
        assert "500" in msg
        assert "Please try again" in msg

    def test_catchall_no_repr(self):
        """Catch-all should not include full repr of the exception."""
        exc = RuntimeError("sensitive internal state: token=abc123")
        msg = _error_message(exc)
        assert "sensitive internal state" not in msg
        assert "token=abc123" not in msg
        assert "RuntimeError" in msg
        assert "Please try again" in msg

    def test_known_statuses_unchanged(self):
        """403/404/429 messages should remain user-friendly."""
        for status, keyword in [
            (403, "Permission"),
            (404, "not found"),
            (429, "Rate limited"),
        ]:
            resp = httpx.Response(
                status_code=status,
                text="details",
                request=httpx.Request("GET", "https://example.com"),
            )
            exc = httpx.HTTPStatusError("err", request=resp.request, response=resp)
            msg = _error_message(exc)
            assert keyword in msg
            assert "details" not in msg


# ── Drive query sanitization tests (M6) ──────────────────────────────


class TestDriveQuerySanitization:
    """Ensure special characters are stripped from Drive API queries."""

    @pytest.mark.asyncio
    async def test_special_chars_stripped(self):
        """Quotes and special chars should be removed from the query."""
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            async with GoogleSheetsClient("fake-token") as client:
                await client.list_spreadsheets(query="Budget' OR 1=1--")

        call_params = mock_get.call_args[1]["params"]
        q = call_params["q"]
        # Extract just the user query part from: ... name contains 'SANITIZED'
        # The sanitized result should be "Budget OR 11" (only alphanum + spaces)
        assert "name contains 'Budget OR 11'" in q
        # Injection chars must not survive
        assert "1=1--" not in q

    @pytest.mark.asyncio
    async def test_clean_query_passes_through(self):
        """Alphanumeric queries with spaces should pass through."""
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            async with GoogleSheetsClient("fake-token") as client:
                await client.list_spreadsheets(query="Budget 2024")

        call_params = mock_get.call_args[1]["params"]
        assert "Budget 2024" in call_params["q"]

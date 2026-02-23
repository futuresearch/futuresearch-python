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
    sheets_create,
    sheets_info,
    sheets_list,
    sheets_read,
    sheets_write,
)

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
def mock_google_token():
    """Patch get_google_token to return a fake token."""
    with patch(
        "everyrow_mcp.sheets_tools.get_google_token",
        new_callable=AsyncMock,
        return_value="fake-google-token",
    ) as m:
        yield m


class TestSheetsReadTool:
    @pytest.mark.asyncio
    async def test_returns_json_records(self, mock_google_token):
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
    async def test_empty_sheet(self, mock_google_token):
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
    async def test_url_extraction(self, mock_google_token):
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
    async def test_write_overwrite(self, mock_google_token):
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
                )
            )

        assert "Wrote" in result[0].text

    @pytest.mark.asyncio
    async def test_write_append(self, mock_google_token):
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
    async def test_create_empty(self, mock_google_token):
        mock_resp = _mock_response(
            {
                "spreadsheetId": "new-id-123",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-id-123",
            }
        )

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_create(SheetsCreateInput(title="Test"))

        data = json.loads(result[0].text)
        assert data["spreadsheet_id"] == "new-id-123"
        assert "url" in data
        assert "rows_written" not in data

    @pytest.mark.asyncio
    async def test_create_with_data(self, mock_google_token):
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


class TestSheetsInfoTool:
    @pytest.mark.asyncio
    async def test_returns_metadata(self, mock_google_token):
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
    async def test_returns_files(self, mock_google_token):
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
    async def test_empty_results(self, mock_google_token):
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await sheets_list(SheetsListInput())

        assert "No spreadsheets found" in result[0].text

    @pytest.mark.asyncio
    async def test_with_query(self, mock_google_token):
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
    async def test_max_results(self, mock_google_token):
        mock_resp = _mock_response({"files": []})

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            await sheets_list(SheetsListInput(max_results=5))

        call_params = mock_get.call_args[1]["params"]
        assert call_params["pageSize"] == "5"

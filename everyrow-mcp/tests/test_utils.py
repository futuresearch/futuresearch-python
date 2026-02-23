"""Tests for utility functions."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pandas as pd
import pytest

from everyrow_mcp.utils import (
    fetch_csv_from_url,
    load_input,
    normalize_google_url,
    resolve_output_path,
    save_result_to_csv,
    validate_csv_path,
    validate_output_path,
    validate_url,
)


class TestValidateCsvPath:
    """Tests for validate_csv_path."""

    def test_valid_csv_file(self, tmp_path: Path):
        """Test validation passes for existing CSV file."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        # Should not raise
        validate_csv_path(str(csv_file))

    def test_relative_path_fails(self):
        """Test validation fails for relative path."""
        with pytest.raises(ValueError, match="must be absolute"):
            validate_csv_path("relative/path.csv")

    def test_nonexistent_file_fails(self, tmp_path: Path):
        """Test validation fails for nonexistent file."""
        with pytest.raises(ValueError, match="does not exist"):
            validate_csv_path(str(tmp_path / "nonexistent.csv"))

    def test_directory_fails(self, tmp_path: Path):
        """Test validation fails for directory."""
        with pytest.raises(ValueError, match="not a file"):
            validate_csv_path(str(tmp_path))

    def test_non_csv_file_fails(self, tmp_path: Path):
        """Test validation fails for non-CSV file."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        with pytest.raises(ValueError, match="must be a CSV"):
            validate_csv_path(str(txt_file))


class TestValidateOutputPath:
    """Tests for validate_output_path."""

    def test_valid_directory(self, tmp_path: Path):
        """Test validation passes for existing directory."""
        validate_output_path(str(tmp_path))

    def test_valid_csv_path(self, tmp_path: Path):
        """Test validation passes for CSV path with existing parent."""
        csv_path = tmp_path / "output.csv"
        validate_output_path(str(csv_path))

    def test_relative_path_fails(self):
        """Test validation fails for relative path."""
        with pytest.raises(ValueError, match="must be absolute"):
            validate_output_path("relative/output.csv")

    def test_nonexistent_directory_fails(self, tmp_path: Path):
        """Test validation fails for nonexistent directory."""
        with pytest.raises(ValueError, match="does not exist"):
            validate_output_path(str(tmp_path / "nonexistent"))

    def test_nonexistent_parent_fails(self, tmp_path: Path):
        """Test validation fails for CSV path with nonexistent parent."""
        with pytest.raises(ValueError, match="does not exist"):
            validate_output_path(str(tmp_path / "nonexistent" / "output.csv"))


class TestResolveOutputPath:
    """Tests for resolve_output_path."""

    def test_full_csv_path(self, tmp_path: Path):
        """Test resolution with full CSV path."""
        output = str(tmp_path / "my_output.csv")
        result = resolve_output_path(output, "/input/data.csv", "screened")
        assert result == Path(output)

    def test_directory_generates_filename(self, tmp_path: Path):
        """Test resolution with directory generates filename."""
        result = resolve_output_path(str(tmp_path), "/input/companies.csv", "screened")
        assert result == tmp_path / "screened_companies.csv"

    def test_different_prefixes(self, tmp_path: Path):
        """Test different prefixes generate correct filenames."""
        for prefix in ["screened", "ranked", "deduped", "merged", "agent"]:
            result = resolve_output_path(str(tmp_path), "/data/test.csv", prefix)
            assert result == tmp_path / f"{prefix}_test.csv"


class TestSaveResultToCsv:
    """Tests for save_result_to_csv."""

    def test_save_dataframe(self, tmp_path: Path):
        """Test saving a DataFrame to CSV."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        output_path = tmp_path / "output.csv"

        save_result_to_csv(df, output_path)

        # Verify file was created and has correct content
        assert output_path.exists()
        loaded = pd.read_csv(output_path)
        assert list(loaded.columns) == ["a", "b"]
        assert len(loaded) == 3


class TestValidateUrl:
    """Tests for validate_url."""

    def test_valid_https(self):
        result = validate_url("https://example.com/data.csv")
        assert result == "https://example.com/data.csv"

    def test_valid_http(self):
        result = validate_url("http://example.com/data.csv")
        assert result == "http://example.com/data.csv"

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="http or https"):
            validate_url("ftp://example.com/data.csv")

    def test_missing_host(self):
        with pytest.raises(ValueError, match="missing a host"):
            validate_url("https://")


class TestNormalizeGoogleUrl:
    """Tests for normalize_google_url."""

    def test_sheets_without_gid(self):
        url = "https://docs.google.com/spreadsheets/d/ABC123/edit"
        result = normalize_google_url(url)
        assert (
            result == "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv"
        )

    def test_sheets_with_gid(self):
        url = "https://docs.google.com/spreadsheets/d/ABC123/edit#gid=456"
        result = normalize_google_url(url)
        assert (
            result
            == "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv&gid=456"
        )

    def test_drive_view(self):
        url = "https://drive.google.com/file/d/FILE_ID/view"
        result = normalize_google_url(url)
        assert result == "https://drive.google.com/uc?export=download&id=FILE_ID"

    def test_passthrough(self):
        url = "https://example.com/data.csv"
        assert normalize_google_url(url) == url


class TestFetchCsvFromUrl:
    """Tests for fetch_csv_from_url."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        csv_text = "name,age\nAlice,30\nBob,25\n"
        mock_response = httpx.Response(200, text=csv_text)

        with patch("everyrow_mcp.utils.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            df = await fetch_csv_from_url("https://example.com/data.csv")

        assert len(df) == 2
        assert list(df.columns) == ["name", "age"]

    @pytest.mark.asyncio
    async def test_404_error(self):
        mock_response = httpx.Response(404, text="Not Found")

        with patch("everyrow_mcp.utils.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            with pytest.raises(ValueError, match="HTTP 404"):
                await fetch_csv_from_url("https://example.com/missing.csv")

    @pytest.mark.asyncio
    async def test_empty_csv_error(self):
        csv_text = "name,age\n"
        mock_response = httpx.Response(200, text=csv_text)

        with patch("everyrow_mcp.utils.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            with pytest.raises(ValueError, match="empty CSV"):
                await fetch_csv_from_url("https://example.com/empty.csv")

    @pytest.mark.asyncio
    async def test_google_normalization(self):
        csv_text = "col\nval\n"
        mock_response = httpx.Response(200, text=csv_text)

        with patch("everyrow_mcp.utils.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            df = await fetch_csv_from_url(
                "https://docs.google.com/spreadsheets/d/ABC/edit"
            )

            # Verify the normalized URL was fetched
            called_url = mock_client.get.call_args[0][0]
            assert "export?format=csv" in called_url
            assert len(df) == 1


class TestLoadInput:
    """Tests for load_input."""

    @pytest.mark.asyncio
    async def test_url_dispatch(self):
        csv_text = "x\n1\n"
        mock_response = httpx.Response(200, text=csv_text)

        with patch("everyrow_mcp.utils.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            df = await load_input(input_url="https://example.com/data.csv")

        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_fallback_to_load_csv(self):
        df = await load_input(input_data="a,b\n1,2\n")
        assert len(df) == 1
        assert list(df.columns) == ["a", "b"]

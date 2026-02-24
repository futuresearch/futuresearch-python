"""Tests for utility functions."""

import socket
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from everyrow_mcp.utils import (
    _is_blocked_ip,
    _is_url,
    _normalise_google_sheets_url,
    _validate_url_target,
    load_data,
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

    def test_path_traversal_resolved(self, tmp_path: Path):
        """Path with /../ segments is resolved before validation."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")

        # Construct a path with traversal: /tmp/xxx/sub/../test.csv
        sub = tmp_path / "sub"
        sub.mkdir()
        traversal_path = str(sub) + "/../test.csv"

        # Should resolve to the real file and pass
        validate_csv_path(traversal_path)


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


class TestLoadData:
    """Tests for load_data (internal helper, still used by upload_data)."""

    def test_load_from_csv_file(self, tmp_path: Path):
        """Test loading from a CSV file path."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n3,4\n")
        df = load_data(input_csv=str(csv_file))
        assert list(df.columns) == ["a", "b"]
        assert len(df) == 2

    def test_load_from_csv_string(self):
        """Test loading from an inline CSV string."""
        df = load_data(data="name,score\nAlice,10\nBob,20\n")
        assert list(df.columns) == ["name", "score"]
        assert len(df) == 2

    def test_load_from_json_list(self):
        """Test loading from a list of dicts."""
        records = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]
        df = load_data(data=records)
        assert list(df.columns) == ["x", "y"]
        assert len(df) == 2

    def test_load_from_json_string(self):
        """Test loading from a JSON array string (auto-detected)."""
        df = load_data(data='[{"col": "val1"}, {"col": "val2"}]')
        assert list(df.columns) == ["col"]
        assert len(df) == 2

    def test_rejects_no_source(self):
        """Test that no source raises ValueError."""
        with pytest.raises(ValueError, match="Provide exactly one of"):
            load_data()

    def test_rejects_both_sources(self, tmp_path: Path):
        """Test that both sources raises ValueError."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a\n1\n")
        with pytest.raises(ValueError, match="Provide exactly one of"):
            load_data(data="a\n1\n", input_csv=str(csv_file))

    def test_empty_json_list_raises(self):
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError, match="empty DataFrame"):
            load_data(data=[])

    def test_json_string_fallback_to_csv(self):
        """A string starting with '[' that isn't valid JSON falls back to CSV."""
        # This is a CSV string that happens to start with [
        # It will fail JSON parse and fall through to CSV
        df = load_data(data="[col]\nval1\nval2\n")
        assert len(df) == 2


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


class TestIsUrl:
    """Tests for _is_url."""

    def test_http_url(self):
        assert _is_url("http://example.com") is True

    def test_https_url(self):
        assert _is_url("https://example.com/data.csv") is True

    def test_local_path(self):
        assert _is_url("/Users/test/data.csv") is False

    def test_relative_path(self):
        assert _is_url("data.csv") is False


class TestValidateUrl:
    """Tests for validate_url."""

    def test_valid_https(self):
        url = "https://example.com/data.csv"
        assert validate_url(url) == url

    def test_valid_http(self):
        url = "http://example.com/data.csv"
        assert validate_url(url) == url

    def test_rejects_ftp(self):
        with pytest.raises(ValueError, match="http or https"):
            validate_url("ftp://example.com/data.csv")

    def test_rejects_no_host(self):
        with pytest.raises(ValueError, match="no host"):
            validate_url("https://")


class TestNormaliseGoogleSheetsUrl:
    """Tests for _normalise_google_sheets_url."""

    def test_edit_url_to_export(self):
        url = "https://docs.google.com/spreadsheets/d/1abc/edit"
        result = _normalise_google_sheets_url(url)
        assert result == "https://docs.google.com/spreadsheets/d/1abc/export?format=csv"

    def test_edit_url_with_gid(self):
        url = "https://docs.google.com/spreadsheets/d/1abc/edit#gid=123"
        result = _normalise_google_sheets_url(url)
        assert (
            result
            == "https://docs.google.com/spreadsheets/d/1abc/export?format=csv&gid=123"
        )

    def test_already_export_url(self):
        url = "https://docs.google.com/spreadsheets/d/1abc/export?format=csv"
        result = _normalise_google_sheets_url(url)
        assert result == url

    def test_pub_url_to_export(self):
        url = "https://docs.google.com/spreadsheets/d/1abc/pub?output=html"
        result = _normalise_google_sheets_url(url)
        assert result == "https://docs.google.com/spreadsheets/d/1abc/export?format=csv"

    def test_pub_url_with_gid(self):
        url = "https://docs.google.com/spreadsheets/d/1abc/pub?gid=456&single=true"
        result = _normalise_google_sheets_url(url)
        assert (
            result
            == "https://docs.google.com/spreadsheets/d/1abc/export?format=csv&gid=456"
        )

    def test_non_google_url_unchanged(self):
        url = "https://example.com/data.csv"
        result = _normalise_google_sheets_url(url)
        assert result == url


# ── SSRF protection tests ─────────────────────────────────────


def _mock_resolve(hostname, resolved_ip):  # noqa: ARG001
    """Return a mock getaddrinfo result resolving hostname to a single IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (resolved_ip, 0))]


class TestSsrfProtection:
    """Tests for SSRF protection in URL validation."""

    def test_blocks_localhost(self):
        assert _is_blocked_ip("127.0.0.1") is True

    def test_blocks_10_x(self):
        assert _is_blocked_ip("10.0.0.1") is True

    def test_blocks_172_16_x(self):
        assert _is_blocked_ip("172.16.0.1") is True

    def test_blocks_192_168_x(self):
        assert _is_blocked_ip("192.168.1.1") is True

    def test_blocks_link_local(self):
        assert _is_blocked_ip("169.254.169.254") is True

    def test_blocks_ipv6_loopback(self):
        assert _is_blocked_ip("::1") is True

    def test_allows_public_ip(self):
        assert _is_blocked_ip("8.8.8.8") is False

    def test_allows_public_ip_2(self):
        assert _is_blocked_ip("93.184.216.34") is False

    def test_validate_url_target_blocks_localhost(self):
        with patch(
            "everyrow_mcp.utils.socket.getaddrinfo",
            return_value=_mock_resolve("localhost", "127.0.0.1"),
        ):
            with pytest.raises(ValueError, match="not permitted"):
                _validate_url_target("http://localhost/secret")

    def test_validate_url_target_blocks_10_x(self):
        with patch(
            "everyrow_mcp.utils.socket.getaddrinfo",
            return_value=_mock_resolve("internal.corp", "10.0.0.5"),
        ):
            with pytest.raises(ValueError, match="not permitted"):
                _validate_url_target("http://internal.corp/data")

    def test_validate_url_target_blocks_metadata_endpoint(self):
        with patch(
            "everyrow_mcp.utils.socket.getaddrinfo",
            return_value=_mock_resolve("metadata", "169.254.169.254"),
        ):
            with pytest.raises(ValueError, match="not permitted"):
                _validate_url_target("http://metadata/latest/api-token")

    def test_validate_url_target_allows_public(self):
        with patch(
            "everyrow_mcp.utils.socket.getaddrinfo",
            return_value=_mock_resolve("example.com", "93.184.216.34"),
        ):
            # Should not raise
            _validate_url_target("https://example.com/data.csv")

    def test_validate_url_target_blocks_unresolvable(self):
        with patch(
            "everyrow_mcp.utils.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            with pytest.raises(ValueError, match="Could not resolve"):
                _validate_url_target("http://nonexistent.invalid/data")

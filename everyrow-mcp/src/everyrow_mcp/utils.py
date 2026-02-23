"""Utility functions for the everyrow MCP server."""

import logging
import re
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


def validate_csv_path(path: str) -> None:
    """Validate that a CSV file exists and is readable.

    Args:
        path: Path to the CSV file

    Raises:
        ValueError: If path is not absolute, doesn't exist, or isn't a CSV file
    """
    p = Path(path)

    if not p.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")

    if not p.exists():
        raise ValueError(f"File does not exist: {path}")

    if not p.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if p.suffix.lower() != ".csv":
        raise ValueError(f"File must be a CSV file: {path}")


def validate_output_path(path: str) -> None:
    """Validate that an output path is valid before processing.

    The path can be either:
    - A directory (must exist)
    - A file path ending in .csv (parent directory must exist)

    Args:
        path: Output path to validate

    Raises:
        ValueError: If path is not absolute or parent directory doesn't exist
    """
    p = Path(path)

    if not p.is_absolute():
        raise ValueError(f"Output path must be absolute: {path}")

    is_csv_file = p.suffix.lower() == ".csv"
    dir_to_check = p.parent if is_csv_file else p

    if not dir_to_check.exists():
        label = "Parent directory" if is_csv_file else "Output directory"
        raise ValueError(f"{label} does not exist: {dir_to_check}")

    if not dir_to_check.is_dir():
        label = "Parent path" if is_csv_file else "Output path"
        raise ValueError(f"{label} is not a directory: {dir_to_check}")


def validate_csv_output_path(path: str) -> None:
    """Validate that an output path is a full CSV file path.

    Unlike validate_output_path, this requires a full file path ending in .csv,
    not a directory.

    Args:
        path: Output path to validate (must be absolute and end in .csv)

    Raises:
        ValueError: If path is not absolute, doesn't end in .csv, or parent doesn't exist
    """
    p = Path(path)

    if not p.is_absolute():
        raise ValueError(f"Output path must be absolute: {path}")

    if p.suffix.lower() != ".csv":
        raise ValueError(f"Output path must end in .csv: {path}")

    if not p.parent.exists():
        raise ValueError(f"Parent directory does not exist: {p.parent}")

    if not p.parent.is_dir():
        raise ValueError(f"Parent path is not a directory: {p.parent}")


def resolve_output_path(output_path: str, input_path: str, prefix: str) -> Path:
    """Resolve the output path, generating a filename if needed.

    Args:
        output_path: The output path (directory or full file path)
        input_path: The input file path (used to generate output filename)
        prefix: Prefix to add to the generated filename (e.g., 'screened', 'ranked')

    Returns:
        Full path to the output file
    """
    out = Path(output_path)

    if out.suffix.lower() == ".csv":
        return out

    input_name = Path(input_path).stem
    return out / f"{prefix}_{input_name}.csv"


def load_csv(
    *,
    input_csv: str | None = None,
    input_data: str | None = None,
    input_json: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Load tabular data from a file path, inline CSV string, or JSON records.

    Exactly one of the three sources must be provided.

    Args:
        input_csv: Absolute path to a CSV file on disk.
        input_data: Raw CSV content as a string.
        input_json: List of dicts (JSON records).

    Returns:
        DataFrame with the loaded data.

    Raises:
        ValueError: If no source or multiple sources are provided, or if data is empty.
    """
    sources = sum(1 for s in (input_csv, input_data, input_json) if s is not None)
    if sources != 1:
        raise ValueError("Provide exactly one of input_csv, input_data, or input_json.")

    if input_csv:
        return pd.read_csv(input_csv)

    if input_json:
        df = pd.DataFrame(input_json)
        if df.empty:
            raise ValueError("input_json produced an empty DataFrame.")
        return df

    df = pd.read_csv(StringIO(input_data))  # type: ignore[arg-type]
    if df.empty:
        raise ValueError("input_data produced an empty DataFrame.")
    return df


def validate_url(url: str) -> str:
    """Validate that a string is an http(s) URL.

    Returns the URL unchanged if valid.

    Raises:
        ValueError: If the URL scheme is not http/https or netloc is missing.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https scheme, got '{parsed.scheme}'")
    if not parsed.netloc:
        raise ValueError(f"URL is missing a host: {url}")
    return url


# Regex patterns for Google URL normalization
_SHEETS_EDIT_RE = re.compile(
    r"^https?://docs\.google\.com/spreadsheets/d/([^/]+)/edit(?:\?[^#]*)?(?:#gid=(\d+))?$"
)
_DRIVE_VIEW_RE = re.compile(r"^https?://drive\.google\.com/file/d/([^/]+)/view")


def normalize_google_url(url: str) -> str:
    """Convert common Google Sheets/Drive share URLs to direct download URLs.

    - Sheets edit URL -> CSV export URL (preserving gid if present)
    - Drive view URL -> direct download URL
    - Anything else -> returned as-is
    """
    m = _SHEETS_EDIT_RE.match(url)
    if m:
        doc_id = m.group(1)
        gid = m.group(2)
        export_url = (
            f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv"
        )
        if gid is not None:
            export_url += f"&gid={gid}"
        return export_url

    m = _DRIVE_VIEW_RE.match(url)
    if m:
        file_id = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


def _is_google_url(url: str) -> bool:
    return "docs.google.com" in url or "drive.google.com" in url


async def fetch_csv_from_url(url: str) -> pd.DataFrame:
    """Fetch CSV data from a URL and return as a DataFrame.

    Normalizes Google Sheets/Drive URLs before fetching.
    Automatically authenticates with the user's Google token for
    Google Sheets/Drive URLs.

    Raises:
        ValueError: On non-2xx response or empty data.
    """
    normalized = normalize_google_url(url)
    logger.info("Fetching CSV from URL: %s (normalized: %s)", url, normalized)

    headers: dict[str, str] = {}
    if _is_google_url(normalized):
        try:
            from everyrow_mcp.sheets_client import get_google_token  # noqa: PLC0415

            token = await get_google_token()
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            logger.debug("No Google token available, fetching without auth")

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        response = await client.get(normalized, headers=headers)
    if not response.is_success:
        logger.error("URL fetch failed (HTTP %s): %s", response.status_code, normalized)
        raise ValueError(
            f"Failed to fetch URL (HTTP {response.status_code}): {normalized}"
        )
    df = pd.read_csv(StringIO(response.text))
    if df.empty:
        logger.error("URL returned empty CSV: %s", normalized)
        raise ValueError(f"URL returned empty CSV data: {normalized}")
    logger.info("Fetched %d rows, %d columns from URL", len(df), len(df.columns))
    return df


async def load_input(
    *,
    input_csv: str | None = None,
    input_data: str | None = None,
    input_json: list[dict[str, Any]] | None = None,
    input_url: str | None = None,
) -> pd.DataFrame:
    """Load tabular data from a file path, inline CSV, JSON records, or URL.

    Async dispatcher: delegates to ``fetch_csv_from_url`` for URLs,
    falls back to the synchronous ``load_csv`` for all other sources.
    """
    if input_url:
        return await fetch_csv_from_url(input_url)
    return load_csv(input_csv=input_csv, input_data=input_data, input_json=input_json)


def save_result_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to CSV.

    Args:
        df: DataFrame to save
        path: Path to save to
    """
    df.to_csv(path, index=False)

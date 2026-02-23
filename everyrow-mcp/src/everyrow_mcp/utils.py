"""Utility functions for the everyrow MCP server."""

from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd


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
    sources = sum(1 for s in (input_csv, input_data, input_json) if s)
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


def save_result_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to CSV.

    Args:
        df: DataFrame to save
        path: Path to save to
    """
    df.to_csv(path, index=False)

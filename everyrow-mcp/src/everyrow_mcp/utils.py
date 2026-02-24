"""Utility functions for the everyrow MCP server."""

import ipaddress
import json
import logging
import re
import socket
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)

# ── SSRF protection ────────────────────────────────────────────

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.google.internal.",
    }
)


def _is_blocked_ip(addr: str) -> bool:
    """Check if an IP address falls within a blocked private/internal network."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # unparseable → block
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _validate_hostname(hostname: str) -> None:
    """Validate that a hostname doesn't resolve to blocked IPs or metadata services.

    Called both as a pre-flight check and at transport request time to close
    the TOCTOU gap between DNS validation and HTTP connection.

    Raises:
        ValueError: If the hostname is blocked, resolves to a blocked IP, or cannot be resolved.
    """
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname is not permitted: {hostname}")

    # Direct IP literal — validate without DNS resolution
    try:
        ip = ipaddress.ip_address(hostname)
        if any(ip in net for net in _BLOCKED_NETWORKS):
            raise ValueError(f"Connection to blocked IP: {hostname}")
        return
    except ValueError:
        pass  # Not an IP literal, resolve via DNS

    try:
        addrinfos = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    for _, _, _, _, sockaddr in addrinfos:
        if _is_blocked_ip(sockaddr[0]):
            logger.warning("SSRF blocked: %s resolved to %s", hostname, sockaddr[0])
            raise ValueError(f"URL target is not permitted: {hostname}")


def _validate_url_target(url: str) -> None:
    """Resolve a URL's hostname and reject if any resolved IP is internal.

    Raises:
        ValueError: If the hostname resolves to a blocked network or cannot be resolved.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")
    _validate_hostname(hostname)


def _is_url(value: str) -> bool:
    """Check if a string looks like an HTTP(S) URL."""
    return value.startswith("http://") or value.startswith("https://")


def validate_url(url: str) -> str:
    """Validate and normalise an HTTP(S) URL.

    Returns the URL unchanged (after basic validation).

    Raises:
        ValueError: If the URL scheme is not http/https or the URL has no host.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https scheme: {url}")
    if not parsed.netloc:
        raise ValueError(f"URL has no host: {url}")
    return url


def _normalise_google_sheets_url(url: str) -> str:
    """Convert a Google Sheets URL to its CSV export variant.

    Handles:
    - ``/edit...`` → ``/export?format=csv``
    - ``/pub...`` → ``/export?format=csv``
    - Already has ``/export?format=csv`` → unchanged
    """
    if "docs.google.com/spreadsheets" not in url:
        return url

    # Already an export URL
    if "/export" in url and "format=csv" in url:
        return url

    # /edit, /pub, or bare doc URL → /export?format=csv
    match = re.match(r"(https://docs\.google\.com/spreadsheets/d/[^/]+)", url)
    if match:
        base = match.group(1)
        # Extract gid if present
        gid_match = re.search(r"gid=(\d+)", url)
        if gid_match:
            return f"{base}/export?format=csv&gid={gid_match.group(1)}"
        return f"{base}/export?format=csv"

    return url


async def _check_redirect(response: httpx.Response) -> None:
    """Event hook: validate redirect targets against blocked networks."""
    if response.is_redirect:
        location = response.headers.get("location", "")
        if location:
            try:
                _validate_url_target(location)
            except ValueError:
                raise httpx.TooManyRedirects(
                    f"Redirect to blocked address: {location}",
                    request=response.request,
                )


class _SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Transport that re-validates hostnames at request time.

    Narrows the TOCTOU window between DNS validation and connection to
    near-zero by re-checking every hostname immediately before the inner
    transport opens a TCP connection.
    """

    def __init__(self) -> None:
        self._transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host:
            _validate_hostname(request.url.host)
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()


async def fetch_csv_from_url(url: str) -> pd.DataFrame:
    """Fetch CSV data from a URL and return a DataFrame.

    Automatically normalises Google Sheets URLs to their CSV export endpoint.
    Validates that the URL (and any redirects) do not target internal networks.

    Raises:
        ValueError: If the response cannot be parsed as CSV, or URL targets a blocked network.
        httpx.HTTPStatusError: On non-2xx responses.
    """
    url = _normalise_google_sheets_url(url)
    _validate_url_target(url)

    async with httpx.AsyncClient(
        transport=_SSRFSafeTransport(),
        follow_redirects=True,
        max_redirects=5,
        timeout=60.0,
        event_hooks={"response": [_check_redirect]},
    ) as client:
        # Stream the response to enforce a size limit before buffering
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > settings.max_fetch_size_bytes:
                raise ValueError(
                    f"Response too large ({content_length} bytes, "
                    f"limit {settings.max_fetch_size_bytes})"
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > settings.max_fetch_size_bytes:
                    raise ValueError(
                        f"Response exceeded size limit ({settings.max_fetch_size_bytes} bytes)"
                    )
                chunks.append(chunk)
            raw_bytes = b"".join(chunks)

    content_type = response.headers.get("content-type", "")
    text = raw_bytes.decode("utf-8", errors="replace")

    # Try CSV first
    try:
        df = pd.read_csv(StringIO(text))
        if df.empty:
            raise ValueError(f"URL returned empty CSV data (headers only): {url}")
        return df
    except ValueError:
        raise
    except Exception:
        pass

    # Try JSON array
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            return pd.DataFrame(data)
    except (json.JSONDecodeError, ValueError):
        pass

    raise ValueError(
        f"Could not parse response from {url} as CSV or JSON. "
        f"Content-Type: {content_type}"
    )


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

    # Resolve symlinks and /../ to prevent path traversal
    p = p.resolve()

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


def load_data(
    *,
    data: str | list[dict[str, Any]] | None = None,
    input_csv: str | None = None,
) -> pd.DataFrame:
    """Load tabular data from inline data or a local CSV file path.

    Exactly one of ``data`` or ``input_csv`` must be provided.

    Args:
        data: Inline data — either a CSV string or a JSON array of objects
              (``list[dict]``).  When a string starting with ``[`` is passed it
              is parsed as JSON first; otherwise it is treated as CSV.
        input_csv: Absolute path to a CSV file on disk (stdio mode only).

    Returns:
        DataFrame with the loaded data.

    Raises:
        ValueError: If no source or multiple sources are provided, or if data is empty.
    """
    sources = sum(1 for s in (data, input_csv) if s is not None)
    if sources != 1:
        raise ValueError("Provide exactly one of data, input_csv.")

    if input_csv:
        return pd.read_csv(input_csv)

    # data is not None at this point
    if isinstance(data, list):
        df = pd.DataFrame(data)
        if df.empty:
            raise ValueError("data produced an empty DataFrame.")
        return df

    # str — auto-detect JSON array vs CSV
    assert isinstance(data, str)
    stripped = data.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                df = pd.DataFrame(parsed)
                if df.empty:
                    raise ValueError("data produced an empty DataFrame.")
                return df
        except json.JSONDecodeError:
            pass  # fall through to CSV

    df = pd.read_csv(StringIO(data))
    if df.empty:
        raise ValueError("data produced an empty DataFrame.")
    return df


def save_result_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to CSV.

    Args:
        df: DataFrame to save
        path: Path to save to
    """
    df.to_csv(path, index=False)

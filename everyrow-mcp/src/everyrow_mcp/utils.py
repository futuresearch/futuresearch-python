"""Utility functions for the everyrow MCP server."""

import asyncio
import ipaddress
import json
import logging
import re
import socket
from io import StringIO
from pathlib import Path
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

# Restrict outbound fetches to standard HTTP(S) ports.
_ALLOWED_PORTS: frozenset[int] = frozenset({80, 443, 8080, 8443})


def _validate_port(port: int | None) -> None:
    """Reject non-standard ports for outbound URL fetching.

    Default ports (omitted from the URL) are always allowed.
    Explicit ports must be in the ``_ALLOWED_PORTS`` allowlist.
    """
    if port is None:
        return  # Default port for the scheme — always allowed
    if port not in _ALLOWED_PORTS:
        raise ValueError(
            f"Port {port} is not permitted for URL fetching. "
            f"Allowed: {sorted(_ALLOWED_PORTS)}"
        )


def _is_blocked_ip(addr: str) -> bool:
    """Check if an IP address falls within a blocked private/internal network."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # unparseable → block
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 → 127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _BLOCKED_NETWORKS)


async def _resolve_and_validate(hostname: str) -> str:
    """Resolve a hostname, validate all IPs, and return the first safe IP.

    For IP literals, validates directly and returns the canonical form.
    For DNS names, resolves via ``getaddrinfo`` (offloaded to a thread pool
    to avoid blocking the event loop) and checks every result.

    The returned IP is used by ``_SSRFSafeTransport`` to **pin** the TCP
    connection, eliminating the TOCTOU gap between DNS validation and the
    actual ``connect()`` call.

    Raises:
        ValueError: If the hostname is blocked, resolves to a blocked IP,
                    or cannot be resolved.
    """
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname is not permitted: {hostname}")

    # Direct IP literal — validate without DNS resolution
    parsed_ip = None
    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # Not an IP literal — fall through to DNS

    if parsed_ip is not None:
        # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 → 127.0.0.1)
        if isinstance(parsed_ip, ipaddress.IPv6Address) and parsed_ip.ipv4_mapped:
            parsed_ip = parsed_ip.ipv4_mapped
        if any(parsed_ip in net for net in _BLOCKED_NETWORKS):
            raise ValueError(f"Connection to blocked IP: {hostname}")
        return str(parsed_ip)

    # DNS name — resolve in a thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    try:
        addrinfos = await loop.run_in_executor(
            None,
            socket.getaddrinfo,
            hostname,
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    if not addrinfos:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    for _, _, _, _, sockaddr in addrinfos:
        addr = str(sockaddr[0])
        if _is_blocked_ip(addr):
            logger.warning("SSRF blocked: %s resolved to %s", hostname, addr)
            raise ValueError(f"URL target is not permitted: {hostname}")

    # All addresses safe — return the first resolved IP for connection pinning
    return str(addrinfos[0][4][0])


async def _validate_url_target(url: str) -> None:
    """Resolve a URL's hostname and reject if any resolved IP is internal or port is blocked.

    Raises:
        ValueError: If the hostname resolves to a blocked network, port is not
                    in the allowlist, or hostname cannot be resolved.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")
    _validate_port(parsed.port)
    await _resolve_and_validate(hostname)


def _is_google_url(url: str) -> bool:
    """Check if a URL points to Google Sheets or Drive."""
    return "docs.google.com" in url or "drive.google.com" in url


def is_url(value: str) -> bool:
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
                await _validate_url_target(location)
            except ValueError:
                # TooManyRedirects aborts the redirect chain — httpx
                # has no "redirect rejected" error type.
                raise httpx.TooManyRedirects(
                    f"Redirect to blocked address: {location}",
                    request=response.request,
                )


class _SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Transport that resolves DNS, validates IPs, and pins connections to safe IPs.

    Eliminates the TOCTOU gap between DNS validation and TCP connection
    by:

    1. Resolving the hostname ourselves via ``getaddrinfo``
    2. Validating every resolved IP against the blocklist
    3. Rewriting the request URL to connect directly to the validated IP
    4. Preserving the original hostname in the ``Host`` header and TLS SNI
       extension so the remote server sees the correct virtual host

    Also enforces the port allowlist at transport time as a
    second check complementing the pre-flight validation.
    """

    def __init__(self) -> None:
        self._transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        if not hostname:
            return await self._transport.handle_async_request(request)

        # Validate port (defence-in-depth — also checked pre-flight)
        _validate_port(request.url.port)

        # Resolve DNS and validate — returns the first safe IP
        resolved_ip = await _resolve_and_validate(hostname)

        # Pin the URL to the validated IP so the inner transport connects
        # directly without a second (unvalidated) DNS lookup.
        pinned_url = request.url.copy_with(host=resolved_ip)

        # Preserve the original hostname in the Host header.
        # IPv6 addresses must be wrapped in brackets per RFC 7230 §5.4.
        host_header = f"[{hostname}]" if ":" in hostname else hostname
        if request.url.port and request.url.port not in (80, 443):
            host_header = f"{host_header}:{request.url.port}"
        headers = [
            (name, value)
            for name, value in request.headers.items()
            if name.lower() != "host"
        ]
        headers.insert(0, ("host", host_header))

        # Preserve the original hostname for TLS SNI so the server
        # presents the right certificate.
        extensions = dict(request.extensions)
        if request.url.scheme == "https":
            extensions["sni_hostname"] = hostname.encode("idna")

        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._transport.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._transport.aclose()


async def fetch_csv_from_url(url: str) -> pd.DataFrame:
    """Fetch CSV data from a URL and return a DataFrame.

    Automatically normalises Google Sheets URLs to their CSV export endpoint.
    Authenticates Google URLs with the user's token when available.
    Validates that the URL (and any redirects) do not target internal networks.

    Raises:
        ValueError: If the response cannot be parsed as CSV, or URL targets a blocked network.
        httpx.HTTPStatusError: On non-2xx responses.
    """
    url = _normalise_google_sheets_url(url)
    await _validate_url_target(url)

    # Authenticate Google URLs with the user's OAuth token
    headers: dict[str, str] = {}
    if _is_google_url(url):
        try:
            from everyrow_mcp.sheets_client import get_google_token  # noqa: PLC0415

            token = await get_google_token()
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            logger.debug("No Google token available, fetching without auth")

    async with httpx.AsyncClient(
        transport=_SSRFSafeTransport(),
        follow_redirects=True,
        max_redirects=5,
        timeout=60.0,
        event_hooks={"response": [_check_redirect]},
    ) as client:
        # Stream the response to enforce a size limit before buffering
        async with client.stream("GET", url, headers=headers) as response:
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


def save_result_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to CSV.

    Args:
        df: DataFrame to save
        path: Path to save to
    """
    df.to_csv(path, index=False)

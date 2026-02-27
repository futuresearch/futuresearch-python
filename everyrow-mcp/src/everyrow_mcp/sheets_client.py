"""Async Google Sheets API client using httpx.

Handles token resolution for HTTP mode (Redis-stored OAuth tokens obtained
during the Supabase/Google OAuth flow). Sheets tools are not available in
stdio mode.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from everyrow_mcp.redis_store import (
    build_key,
    decrypt_value,
    encrypt_value,
    get_redis_client,
)

logger = logging.getLogger(__name__)

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

# Google token TTL and refresh buffer
GOOGLE_TOKEN_TTL_DEFAULT = 3600  # 1 hour
GOOGLE_TOKEN_REFRESH_BUFFER = 300  # refresh 5 min before expiry


# ── Token resolution ──────────────────────────────────────────────────


async def get_google_token(user_id: str | None = None) -> str:
    """Resolve a valid Google access token from Redis.

    The token is stored during the OAuth callback when the user logs in
    via Google through Supabase. Auto-refreshes if near expiry.

    Only available in HTTP mode — sheets tools are removed in stdio mode.
    """
    if user_id is None:
        from mcp.server.auth.middleware.auth_context import (  # noqa: PLC0415
            get_access_token,
        )

        access_token = get_access_token()
        user_id = access_token.client_id if access_token else None
        if not user_id:
            raise RuntimeError(
                "No authenticated user. The user must log in with Google "
                "(with Sheets scopes) to use Google Sheets tools."
            )

    redis = get_redis_client()

    token_key = build_key("google_token", user_id)
    raw = await redis.get(token_key)
    if raw:
        data = json.loads(decrypt_value(raw))
        expires_at = data.get("expires_at", 0)
        if time.time() < expires_at - GOOGLE_TOKEN_REFRESH_BUFFER:
            return data["access_token"]

        # Token near expiry — try to refresh
        refresh_token = data.get("refresh_token")
        if refresh_token:
            try:
                return await _refresh_google_token_http(refresh_token, user_id)
            except Exception as e:
                logger.warning("Failed to refresh Google token: %s", type(e).__name__)
                if time.time() < expires_at:
                    return data["access_token"]

    raise RuntimeError(
        "No Google token available. The user must log in with Google "
        "(with Sheets scopes) to use Google Sheets tools."
    )


async def _refresh_google_token_http(refresh_token: str, user_id: str) -> str:
    """Refresh a Google access token using the Supabase-stored refresh token."""
    from everyrow_mcp.config import settings  # noqa: PLC0415

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Refresh through Supabase which proxies to Google
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    provider_token = data.get("provider_token", "")
    provider_refresh_token = data.get("provider_refresh_token", refresh_token)
    expires_in = data.get("expires_in")

    if not provider_token:
        raise RuntimeError("Supabase refresh did not return a Google provider_token")

    await store_google_token(
        user_id, provider_token, provider_refresh_token, expires_in=expires_in
    )
    return provider_token


async def store_google_token(
    user_id: str,
    access_token: str,
    refresh_token: str | None = None,
    *,
    expires_in: int | None = None,
) -> None:
    """Store Google access token in Redis with TTL."""
    try:
        redis = get_redis_client()
    except Exception:
        logger.error("Failed to obtain Redis client for Google token storage")
        raise
    ttl = expires_in if expires_in and expires_in > 0 else GOOGLE_TOKEN_TTL_DEFAULT
    try:
        data: dict[str, Any] = {
            "access_token": access_token,
            "expires_at": time.time() + ttl,
        }
        if refresh_token:
            data["refresh_token"] = refresh_token
        await redis.setex(
            build_key("google_token", user_id),
            ttl,
            encrypt_value(json.dumps(data)),
        )
    except Exception:
        logger.error("Failed to store Google token in Redis for %s", user_id)
        raise


# ── Sheets API client ─────────────────────────────────────────────────


class GoogleSheetsClient:
    """Async Google Sheets API v4 client."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GoogleSheetsClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def read_range(
        self, spreadsheet_id: str, cell_range: str = "Sheet1"
    ) -> list[list[str]]:
        """Read values from a spreadsheet range.

        Returns a 2D list of strings (rows x columns).
        """
        resp = await self._client.get(
            f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{cell_range}",
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("values", [])

    async def write_range(
        self,
        spreadsheet_id: str,
        cell_range: str,
        values: list[list[str]],
    ) -> dict[str, Any]:
        """Write values to a spreadsheet range (overwrite)."""
        resp = await self._client.put(
            f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{cell_range}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": values},
        )
        resp.raise_for_status()
        return resp.json()

    async def append_range(
        self,
        spreadsheet_id: str,
        cell_range: str,
        values: list[list[str]],
    ) -> dict[str, Any]:
        """Append values after existing data in a range."""
        resp = await self._client.post(
            f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{cell_range}:append",
            params={
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
            },
            json={"values": values},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_spreadsheet(self, title: str) -> dict[str, Any]:
        """Create a new spreadsheet. Returns metadata with spreadsheetId and URL."""
        resp = await self._client.post(
            SHEETS_API_BASE,
            json={"properties": {"title": title}},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_spreadsheet_metadata(self, spreadsheet_id: str) -> dict[str, Any]:
        """Get spreadsheet metadata: title, sheets, dimensions."""
        resp = await self._client.get(
            f"{SHEETS_API_BASE}/{spreadsheet_id}",
            params={"fields": "properties.title,sheets.properties"},
        )
        resp.raise_for_status()
        return resp.json()

    async def list_spreadsheets(
        self,
        query: str | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """List the user's Google Sheets via the Drive API.

        Returns a list of dicts with id, name, modifiedTime, and webViewLink.
        """
        q = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        if query:
            safe_query = re.sub(r"[^a-zA-Z0-9 ]", "", query)
            q += f" and name contains '{safe_query}'"

        resp = await self._client.get(
            f"{DRIVE_API_BASE}/files",
            params={
                "q": q,
                "fields": "files(id,name,modifiedTime,webViewLink)",
                "orderBy": "modifiedTime desc",
                "pageSize": str(max_results),
            },
        )
        resp.raise_for_status()
        return resp.json().get("files", [])


# ── Converters ─────────────────────────────────────────────────────────


def values_to_records(values: list[list[str]]) -> list[dict[str, Any]]:
    """Convert 2D values (first row = headers) to list of dicts.

    Example:
        [["name", "age"], ["Alice", "30"]] -> [{"name": "Alice", "age": "30"}]
    """
    if len(values) < 2:
        return []
    headers = values[0]
    records = []
    for row in values[1:]:
        # Pad short rows with empty strings
        padded = row + [""] * (len(headers) - len(row))
        records.append(dict(zip(headers, padded)))
    return records


def records_to_values(records: list[dict[str, Any]]) -> list[list[str]]:
    """Convert list of dicts to 2D values (first row = headers).

    Example:
        [{"name": "Alice", "age": 30}] -> [["name", "age"], ["Alice", "30"]]
    """
    if not records:
        return []

    # Collect all keys in order of first appearance
    headers: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                headers.append(key)
                seen.add(key)

    rows = [headers]
    for record in records:
        rows.append(
            [
                str(v) if v is not None else ""
                for v in (record.get(h, "") for h in headers)
            ]
        )
    return rows

"""Redis-backed result retrieval for the everyrow MCP server.

Handles checking Redis for cached metadata, storing JSON results,
and building the MCP TextContent responses.

Caching strategy:
  - Base metadata (total, columns) cached at  result:{task_id}
  - Per-page previews cached at               result:{task_id}:page:{offset}:{page_size}
  - Full JSON stored at                       result:{task_id}:json  (1h TTL)
  - On a page cache miss, the JSON is read from Redis and the page is sliced.
"""

from __future__ import annotations

import json
import logging
import math
import secrets
from typing import Any

import pandas as pd
from mcp.types import TextContent

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)


def _sanitize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace NaN/Inf float values with None for valid JSON serialization.

    pandas ``to_dict(orient="records")`` preserves ``float('nan')`` which
    ``json.dumps`` serializes as ``NaN`` — invalid JSON that breaks
    ``JSON.parse()`` on the client side.
    """
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


def _format_columns(columns: list[str]) -> str:
    """Format column names for display, truncating after 10."""
    col_names = ", ".join(columns[:10])
    if len(columns) > 10:
        col_names += f", ... (+{len(columns) - 10} more)"
    return col_names


def _estimate_tokens(text: str) -> int:
    """Estimate token count using ~4 characters per token heuristic."""
    return len(text) // 4


def clamp_page_to_budget(
    preview_records: list[dict[str, Any]],
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    estimated = _estimate_tokens(json.dumps(preview_records))
    if estimated <= settings.token_budget:
        return preview_records, page_size

    # Pre-compute per-row token sizes and build a prefix sum so the binary
    # search doesn't need to re-serialize on every iteration.
    # Overhead per-row is ~2 tokens for the JSON array wrapper/commas.
    row_sizes = [_estimate_tokens(json.dumps(r)) + 2 for r in preview_records]
    prefix = [0] * (len(row_sizes) + 1)
    for i, s in enumerate(row_sizes):
        prefix[i + 1] = prefix[i] + s

    lo, hi = 1, len(preview_records)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if prefix[mid] <= settings.token_budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    clamped = preview_records[:best]
    return clamped, best


def _build_result_response(
    task_id: str,
    csv_url: str,
    preview_records: list[dict[str, Any]],
    total: int,
    columns: list[str],
    offset: int,
    page_size: int,
    session_url: str = "",
    poll_token: str = "",
    mcp_server_url: str = "",
    *,
    requested_page_size: int | None = None,
    skip_widget: bool = False,
) -> list[TextContent]:
    """Build MCP TextContent response for Redis-backed results.

    *page_size* is the effective (possibly clamped) size used for display.
    *requested_page_size*, when provided, is the user's original page_size
    and is used in the "next page" hint so the server can re-clamp
    independently on each call.

    The widget fetches full results on demand by minting a fresh download
    token via the ``download-token`` endpoint — no pre-minted URL is baked
    into the response, avoiding stale-token issues on re-render.
    """
    col_names = _format_columns(columns)
    hint_page_size = (
        requested_page_size if requested_page_size is not None else page_size
    )

    has_more = offset + page_size < total
    next_offset = offset + page_size if has_more else None

    # Only emit widget JSON on the first page — the widget already fetches
    # the full dataset independently, so subsequent pages only need the
    # text summary for the LLM.
    # Alternative: track a per-task call counter in Redis and only emit on
    # the first call. Rejected because it adds state, and re-fetching
    # offset=0 (e.g. "show me the results again") should show the widget.
    # Widget JSON is only useful for clients that can render iframes
    # (Claude.ai, Claude Desktop). Clients like Claude Code don't render
    # widgets, so the JSON just wastes context tokens.
    #
    # Detection uses a two-tier whitelist (see tool_helpers.client_supports_widgets):
    #  1. MCP Apps UI capability — clients that advertise
    #     experimental["io.modelcontextprotocol/ui"] explicitly support widgets.
    #  2. Name-based whitelist — Claude.ai/Desktop don't advertise the
    #     capability yet, so we whitelist known widget-capable client names.
    #     Unknown clients default to NO widget (saves context tokens).
    #     This fallback should be removed once clients adopt the capability.
    contents: list[TextContent] = []
    if offset == 0 and not skip_widget:
        widget_data: dict[str, Any] = {
            "csv_url": csv_url,
            "preview": preview_records,
            "total": total,
            "fetch_full_results": True,
        }
        if session_url:
            widget_data["session_url"] = session_url
        if poll_token:
            widget_data["poll_token"] = poll_token
            widget_data["download_token_url"] = (
                f"{mcp_server_url}/api/results/{task_id}/download-token"
            )
        contents.append(TextContent(type="text", text=json.dumps(widget_data)))

    if has_more:
        page_size_arg = f", page_size={hint_page_size}"
        summary = (
            f"Results: {total} rows, {len(columns)} columns ({col_names}). "
            f"Showing rows {offset + 1}-{min(offset + page_size, total)} of {total}.\n"
            f"IMPORTANT: Tell the user that you can only see {min(page_size, total)} of the {total} rows in your context, "
            f"but they have access to all {total} rows via the widget above.\n"
            f"Call everyrow_results(task_id='{task_id}', offset={next_offset}{page_size_arg}) for the next page."
        )
        if offset == 0:
            summary += (
                f"\nFull CSV download: {csv_url}\n"
                "Display this download link to the user as a clickable URL in your response."
            )
    elif offset == 0:
        summary = (
            f"Results: {total} rows, {len(columns)} columns ({col_names}). "
            f"All rows shown.\n"
            f"Full CSV download: {csv_url}\n"
            "IMPORTANT: Display this download link to the user as a clickable URL in your response."
        )
    else:
        summary = (
            f"Results: showing rows {offset + 1}-{min(offset + page_size, total)} "
            f"of {total} (final page)."
        )

    contents.append(TextContent(type="text", text=summary))
    return contents


async def _get_csv_url(
    task_id: str, mcp_server_url: str
) -> tuple[str, str] | tuple[None, None]:
    """Build a CSV download URL with a fresh single-use download token.

    Returns ``(csv_url, poll_token)`` on success, or ``(None, None)``
    if the poll token has expired (used as a proxy for "task is still
    valid").  The download token is short-lived (5 min) and consumed on
    use, so a leaked URL cannot be replayed.
    """
    poll_token = await redis_store.get_poll_token(task_id)
    if poll_token is None:
        return None, None
    download_token = secrets.token_urlsafe(32)
    await redis_store.store_download_token(download_token, task_id)
    csv_url = f"{mcp_server_url}/api/results/{task_id}/download?token={download_token}"
    return csv_url, poll_token


async def try_cached_result(
    task_id: str,
    offset: int,
    page_size: int,
    mcp_server_url: str = "",
    *,
    skip_widget: bool = False,
) -> list[TextContent] | None:
    cached_meta_raw = await redis_store.get_result_meta(task_id)
    if not cached_meta_raw:
        return None

    meta = json.loads(cached_meta_raw)
    cached_page = await redis_store.get_result_page(task_id, offset, page_size)
    if cached_page is not None:
        preview_records = json.loads(cached_page)
    else:
        # Page cache miss — read full JSON from Redis and slice
        try:
            json_text = await redis_store.get_result_json(task_id)
            if json_text is None:
                logger.warning(
                    "JSON expired in Redis for task %s, falling back to API", task_id
                )
                return None
            all_records: list[dict[str, Any]] = json.loads(json_text)
            clamped = min(offset, len(all_records))
            preview_records = all_records[clamped : clamped + page_size]
            await redis_store.store_result_page(
                task_id, offset, page_size, json.dumps(preview_records)
            )
        except Exception:
            logger.warning(
                "Failed to read JSON from Redis for task %s, falling back to API",
                task_id,
            )
            return None

    csv_url, poll_token = await _get_csv_url(task_id, mcp_server_url)
    if csv_url is None:
        logger.warning("Poll token expired for task %s, falling back to API", task_id)
        return None

    preview_records, effective_page_size = clamp_page_to_budget(
        preview_records=preview_records,
        page_size=page_size,
    )

    return _build_result_response(
        task_id=task_id,
        csv_url=csv_url,
        preview_records=preview_records,
        total=meta["total"],
        columns=meta["columns"],
        offset=min(offset, meta["total"]),
        page_size=effective_page_size,
        session_url=meta.get("session_url", ""),
        poll_token=poll_token or "",
        mcp_server_url=mcp_server_url,
        requested_page_size=page_size,
        skip_widget=skip_widget,
    )


async def try_store_result(
    task_id: str,
    df: pd.DataFrame,
    offset: int,
    page_size: int,
    session_url: str = "",
    mcp_server_url: str = "",
    *,
    skip_widget: bool = False,
) -> list[TextContent]:
    """Store a DataFrame in Redis and return a paginated response."""
    try:
        all_records = _sanitize_records(df.to_dict(orient="records"))
        await redis_store.store_result_json(task_id, json.dumps(all_records))

        total = len(df)
        columns = list(df.columns)

        # Store base metadata
        meta: dict[str, Any] = {"total": total, "columns": columns}
        if session_url:
            meta["session_url"] = session_url
        await redis_store.store_result_meta(task_id, json.dumps(meta))

        # Build and cache page preview
        clamped_offset = min(offset, total)
        preview_records = all_records[clamped_offset : clamped_offset + page_size]
        await redis_store.store_result_page(
            task_id=task_id,
            offset=offset,
            page_size=page_size,
            preview_json=json.dumps(preview_records),
        )

        csv_url, poll_token = await _get_csv_url(task_id, mcp_server_url)
        if csv_url is None:
            raise RuntimeError(
                f"Poll token expired for task {task_id}, cannot build download URL"
            )

        preview_records, effective_page_size = clamp_page_to_budget(
            preview_records=preview_records,
            page_size=page_size,
        )

        return _build_result_response(
            task_id=task_id,
            csv_url=csv_url,
            preview_records=preview_records,
            total=total,
            columns=columns,
            offset=clamped_offset,
            page_size=effective_page_size,
            session_url=session_url,
            poll_token=poll_token or "",
            mcp_server_url=mcp_server_url,
            requested_page_size=page_size,
            skip_widget=skip_widget,
        )
    except Exception:
        logger.exception("Failed to store results in Redis for task %s", task_id)
        raise

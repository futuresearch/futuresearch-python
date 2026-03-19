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
import re
import secrets
from typing import Any

import litellm
import pandas as pd
from mcp.types import CallToolResult, TextContent

from everyrow_mcp import redis_store
from everyrow_mcp.config import settings

logger = logging.getLogger(__name__)

_TOKEN_MODEL = "claude-opus-4-6"


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
    """Estimate token count using litellm's model-aware tokenizer."""
    return litellm.token_counter(model=_TOKEN_MODEL, text=text)


# Fields stripped from LLM-facing data (user sees them in the viz pane).
_LLM_STRIP_FIELDS = {"_source_bank", "research", "provenance_and_notes"}


_CITATION_RE = re.compile(r"\[((?:[a-f0-9]{6})(?:\s*,\s*[a-f0-9]{6})*)\]")


def _resolve_citations(text: str, source_bank: dict[str, Any]) -> str:
    """Replace citation codes like ``[c91d21]`` with ``[title](url)`` links."""

    def _replace(match: re.Match[str]) -> str:
        ids = [s.strip() for s in match.group(1).split(",")]
        parts = []
        for cid in ids:
            entry = source_bank.get(cid)
            if not entry or not isinstance(entry, dict):
                parts.append(f"[{cid}]")
                continue
            url = entry.get("url")
            if not url:
                parts.append(f"[{cid}]")
                continue
            title = entry.get("title") or url
            parts.append(f"[{title}]({url})")
        return " ".join(parts)

    return _CITATION_RE.sub(_replace, text)


def resolve_citations_in_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve citation codes in all string fields using each row's ``_source_bank``.

    Returns new records with citation codes replaced by markdown links
    and the ``_source_bank`` field removed.
    """
    out = []
    for row in records:
        sb_raw = row.get("_source_bank")
        if not sb_raw:
            out.append({k: v for k, v in row.items() if k not in _LLM_STRIP_FIELDS})
            continue
        # Parse source bank (may be a JSON string or already a dict)
        if isinstance(sb_raw, str):
            try:
                sb = json.loads(sb_raw)
            except (json.JSONDecodeError, TypeError):
                sb = {}
        else:
            sb = sb_raw
        new_row = {}
        for k, v in row.items():
            if k in _LLM_STRIP_FIELDS:
                continue
            if isinstance(v, str) and sb:
                new_row[k] = _resolve_citations(v, sb)
            else:
                new_row[k] = v
        out.append(new_row)
    return out


def clamp_page_to_budget(
    preview_records: list[dict[str, Any]],
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    # Estimate tokens on resolved records (what the LLM actually sees).
    # resolve_citations_in_records both strips heavy fields and expands
    # citation codes into markdown links, so it's the accurate size.
    resolved = resolve_citations_in_records(preview_records)
    estimated = _estimate_tokens(json.dumps(resolved))
    if estimated <= settings.token_budget:
        return preview_records, page_size

    # Pre-compute per-row token sizes and build a prefix sum so the binary
    # search doesn't need to re-serialize on every iteration.
    # Overhead per-row is ~2 tokens for the JSON array wrapper/commas.
    row_sizes = [_estimate_tokens(json.dumps(r)) + 2 for r in resolved]
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
    artifact_id: str = "",
    *,
    requested_page_size: int | None = None,
    skip_widget: bool = False,
    skip_session: bool = False,
) -> CallToolResult:
    """Build a CallToolResult with separate content and structuredContent.

    *content* (for the LLM): summary text + JSON-serialized preview rows.
    *structuredContent* (for the widget renderer): widget data dict with
    preview_records, CSV URL, etc.  This is NOT sent to the LLM, saving
    significant context tokens.

    *page_size* is the effective (possibly clamped) size used for display.
    *requested_page_size*, when provided, is the user's original page_size
    and is used in the "next page" hint so the server can re-clamp
    independently on each call.
    """
    if skip_session:
        session_url = ""
    visible_columns = [c for c in columns if c not in _LLM_STRIP_FIELDS]
    col_names = _format_columns(visible_columns)
    hint_page_size = (
        requested_page_size if requested_page_size is not None else page_size
    )

    has_more = offset + page_size < total
    next_offset = offset + page_size if has_more else None

    # ── Widget data → structuredContent (client only, NOT the LLM) ───
    #
    # Only emit on the first page — the widget fetches the full dataset
    # independently, so subsequent pages only need the text summary.
    # Widget JSON is only useful for clients that can render iframes
    # (Claude.ai, Claude Desktop).  Unknown clients get skip_widget=True.
    structured: dict[str, Any] | None = None
    if offset == 0 and not skip_widget:
        structured = {
            "csv_url": csv_url,
            "preview": preview_records,
            "total": total,
            "fetch_full_results": True,
        }
        if session_url:
            structured["session_url"] = session_url
        if artifact_id:
            structured["artifact_id"] = artifact_id
        if poll_token:
            structured["poll_token"] = poll_token
            structured["download_token_url"] = (
                f"{mcp_server_url}/api/results/{task_id}/download-token"
            )

    # ── Summary + inline data → content (for the LLM) ───────────────
    if has_more:
        page_size_arg = f", page_size={hint_page_size}"
        summary = (
            f"Results: {total} rows, {len(visible_columns)} columns ({col_names}). "
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
            f"Results: {total} rows, {len(visible_columns)} columns ({col_names}). "
            f"All rows shown.\n"
            f"Full CSV download: {csv_url}\n"
            "IMPORTANT: Display this download link to the user as a clickable URL in your response."
        )
    else:
        summary = (
            f"Results: showing rows {offset + 1}-{min(offset + page_size, total)} "
            f"of {total} (final page)."
        )

    # Inform the LLM when the page was reduced to fit the token budget.
    if requested_page_size is not None and page_size < requested_page_size:
        summary += (
            f"\nNote: page was reduced from {requested_page_size} to {page_size} rows "
            f"to fit within the context token budget."
        )

    if artifact_id:
        summary += f"\nOutput artifact_id (use to chain into next tool): {artifact_id}"

    # Append data rows for the LLM: strip heavy fields (source_bank, research
    # notes) and resolve citation codes like [c91d21] → [title](url).
    data_text = json.dumps(resolve_citations_in_records(preview_records))
    summary += f"\n\nData:\n{data_text}"

    return CallToolResult(
        content=[TextContent(type="text", text=summary)],  # pyright: ignore[reportArgumentType]  # list invariance
        structuredContent=structured,
        isError=False,
    )


async def _get_csv_url(
    task_id: str, mcp_server_url: str
) -> tuple[str, str] | tuple[None, None]:
    """Build a CSV download URL with a fresh download token.

    Returns ``(csv_url, poll_token)`` on success, or ``(None, None)``
    if the poll token has expired (used as a proxy for "task is still
    valid").  The download token is reusable until it expires (1 hour).
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
    skip_session: bool = False,
) -> CallToolResult | None:
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
        artifact_id=meta.get("artifact_id", ""),
        requested_page_size=page_size,
        skip_widget=skip_widget,
        skip_session=skip_session,
    )


async def try_store_result(
    task_id: str,
    df: pd.DataFrame,
    offset: int,
    page_size: int,
    session_url: str = "",
    mcp_server_url: str = "",
    artifact_id: str = "",
    *,
    skip_widget: bool = False,
    skip_session: bool = False,
) -> CallToolResult:
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
        if artifact_id:
            meta["artifact_id"] = artifact_id
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
            artifact_id=artifact_id,
            requested_page_size=page_size,
            skip_widget=skip_widget,
            skip_session=skip_session,
        )
    except Exception:
        logger.exception("Failed to store results in Redis for task %s", task_id)
        raise

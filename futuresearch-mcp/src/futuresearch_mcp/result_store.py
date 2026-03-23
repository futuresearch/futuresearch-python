"""Result response building for the futuresearch MCP server.

Provides helpers for building MCP tool responses from Engine result data
and token budget clamping.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import litellm
from mcp.types import CallToolResult, TextContent

from futuresearch_mcp.config import settings

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


def clamp_page_to_budget(
    preview_records: list[dict[str, Any]],
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """Clamp the page to fit within the LLM token budget.

    Rows are assumed to be already processed (citations resolved, heavy
    fields stripped) by the Engine.
    """
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
    poll_token: str = "",
    mcp_server_url: str = "",
    artifact_id: str = "",
    *,
    requested_page_size: int | None = None,
    skip_widget: bool = False,
) -> CallToolResult:
    """Build a CallToolResult with separate content and structuredContent.

    Rows are assumed to be already processed by the Engine (citations
    resolved, internal/heavy fields stripped).

    *content* (for the LLM): summary text + JSON-serialized preview rows.
    *structuredContent* (for the widget renderer): widget data dict with
    preview_records, CSV URL, etc.  This is NOT sent to the LLM, saving
    significant context tokens.
    """
    col_names = _format_columns(columns)
    hint_page_size = (
        requested_page_size if requested_page_size is not None else page_size
    )

    has_more = offset + page_size < total
    next_offset = offset + page_size if has_more else None

    # ── Widget data → structuredContent (client only, NOT the LLM) ───
    #
    # Only emit on the first page — the widget fetches the full dataset
    # independently, so subsequent pages only need the text summary.
    structured: dict[str, Any] | None = None
    if offset == 0 and not skip_widget:
        structured = {
            "csv_url": csv_url,
            "preview": preview_records,
            "total": total,
            "fetch_full_results": True,
        }
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
            f"Results: {total} rows, {len(columns)} columns ({col_names}). "
            f"Showing rows {offset + 1}-{min(offset + page_size, total)} of {total}.\n"
            f"Call futuresearch_results(task_id='{task_id}', offset={next_offset}{page_size_arg}) for the next page."
        )
        if offset == 0:
            summary += (
                f"\nFull CSV download: {csv_url}\n"
                "Display this download link to the user as a clickable URL in your response."
            )
    elif offset == 0:
        summary = (
            f"Results: {total} rows, {len(columns)} columns ({col_names}). "
            f"All rows shown.\nFull CSV download: {csv_url} in case the user asks."
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

    data_text = json.dumps(preview_records)
    summary += f"\n\nData:\n{data_text}"

    return CallToolResult(
        content=[TextContent(type="text", text=summary)],  # pyright: ignore[reportArgumentType]  # list invariance
        structuredContent=structured,
        isError=False,
    )


def _get_csv_url(task_id: str, mcp_server_url: str) -> str:
    """Build a CSV download URL (no auth token needed)."""
    return f"{mcp_server_url}/api/results/{task_id}/download"

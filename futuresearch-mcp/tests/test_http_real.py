"""HTTP-mode integration tests with real FutureSearch API calls.

These tests spin up a Starlette ASGI server (via httpx + ASGITransport),
configure state for HTTP mode with a real Redis instance, and make real
API calls to the FutureSearch backend. They exercise the full pipeline:

    submit (MCP tool) → poll (REST endpoint) → results (MCP tool)

Requirements:
    - FUTURESEARCH_API_KEY must be set
    - RUN_INTEGRATION_TESTS=1
    - redis-server binary on PATH (auto-started by conftest)

Run with: pytest tests/test_http_real.py -v -s
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
from typing import Any
from unittest.mock import patch

import httpx
import pandas as pd
import pytest
from futuresearch.api_utils import create_client
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.routing import Route

from futuresearch_mcp import redis_store
from futuresearch_mcp.models import AgentInput, HttpResultsInput, ProgressInput
from futuresearch_mcp.routes import api_download, api_progress
from futuresearch_mcp.tools import (
    futuresearch_agent,
    futuresearch_progress,
    futuresearch_results_http,
)
from tests.conftest import make_test_context, override_settings


def _text(result: CallToolResult, idx: int = 0) -> str:
    """Extract text from a content block with type narrowing (for pyright)."""
    block = result.content[idx]
    assert isinstance(block, TextContent)
    return block.text


# Skip unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.",
)

# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def _http_mode(fake_redis):
    """Configure settings for HTTP mode with the shared test Redis."""
    with (
        override_settings(transport="streamable-http", upload_secret="test-secret"),
        patch.object(redis_store, "get_redis_client", return_value=fake_redis),
    ):
        yield


@pytest.fixture
def app(_http_mode):
    """Starlette ASGI app with progress and results endpoints."""
    return Starlette(
        routes=[
            Route(
                "/api/progress/{task_id}",
                api_progress,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/api/results/{task_id}/download",
                api_download,
                methods=["GET", "OPTIONS"],
            ),
        ],
    )


@pytest.fixture
async def client(app):
    """httpx client wired to the ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
async def futuresearch_client(_http_mode):
    """Create a real FutureSearch SDK client for MCP tools."""
    with create_client() as sdk_client:
        yield sdk_client


# ── Helpers ────────────────────────────────────────────────────


def extract_task_id(submit_text: str) -> str:
    """Extract task_id from submit tool response."""
    match = re.search(r"Task ID: ([a-f0-9-]+)", submit_text)
    if not match:
        raise ValueError(f"Could not extract task_id from: {submit_text}")
    return match.group(1)


def extract_poll_token(widget_json: str) -> str:
    """Extract poll token from widget JSON."""
    data = json.loads(widget_json)
    token = data.get("poll_token", "")
    if not token:
        raise ValueError(f"No poll_token in widget JSON: {widget_json}")
    return token


async def poll_via_tool(task_id: str, ctx, max_polls: int = 60) -> str:
    """Poll futuresearch_progress via MCP tool until complete."""
    for _ in range(max_polls):
        result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)
        text = result[-1].text
        print(f"  Progress: {text.splitlines()[0]}")

        if "Completed:" in text or "futuresearch_results" in text:
            return text
        if "failed" in text.lower() or "revoked" in text.lower():
            raise RuntimeError(f"Task failed: {text}")

        await asyncio.sleep(2)

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


async def poll_via_rest(
    client: httpx.AsyncClient,
    task_id: str,
    poll_token: str,
    max_polls: int = 60,
) -> dict[str, Any]:
    """Poll /api/progress via REST endpoint until complete."""
    for _ in range(max_polls):
        resp = await client.get(
            f"/api/progress/{task_id}", params={"token": poll_token}
        )
        assert resp.status_code == 200, f"Progress failed: {resp.text}"
        body = resp.json()
        status = body["status"]
        print(
            f"  REST Progress: {status} — "
            f"{body['completed']}/{body['total']} complete, "
            f"{body.get('failed', 0)} failed"
        )

        if status in ("completed", "failed", "revoked"):
            return body

        await asyncio.sleep(2)

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


# ── Tests ──────────────────────────────────────────────────────


class TestHttpAgentPipeline:
    """Full HTTP pipeline with agent tool: submit → poll → results."""

    @pytest.mark.asyncio
    async def test_agent_end_to_end(
        self,
        client: httpx.AsyncClient,
        futuresearch_client,
    ):
        """Submit an agent task, poll via REST, verify results via MCP tool."""
        # 1. Submit via MCP tool
        ctx = make_test_context(futuresearch_client, mcp_server_url="http://testserver")
        result = await futuresearch_agent(
            AgentInput(
                task="Find the company's headquarters city.",
                data=[{"name": "Anthropic"}, {"name": "OpenAI"}],
                response_schema={
                    "properties": {
                        "headquarters": {
                            "type": "string",
                            "description": "City where HQ is located",
                        },
                    },
                    "required": ["headquarters"],
                },
            ),
            ctx,
        )

        assert result.structuredContent is not None
        widget = result.structuredContent
        human_text = _text(result)
        print(f"\nSubmit: {human_text}")

        task_id = widget["task_id"]
        poll_token = widget.get("poll_token", "")

        # 2. Poll via REST until complete
        progress = await poll_via_rest(client, task_id, poll_token)
        assert progress["status"] == "completed"
        assert progress["completed"] == 2

        # 3. Fetch results via MCP tool — real Redis, page_size=1 for pagination
        results = await futuresearch_results_http(
            HttpResultsInput(task_id=task_id, page_size=1), ctx
        )

        assert results.structuredContent is not None
        result_data = results.structuredContent
        assert result_data["total"] == 2
        assert len(result_data["preview"]) == 1  # page_size=1
        assert "csv_url" in result_data
        print(f"  Page 1: {_text(results)}")

        # 4. Fetch second page (should come from Redis cache)
        results_p2 = await futuresearch_results_http(
            HttpResultsInput(task_id=task_id, offset=1, page_size=1), ctx
        )

        assert results_p2.structuredContent is None  # no widget on page 2
        print(f"  Page 2: {_text(results_p2)}")

        # 5. Download full CSV, verify 2 rows with headquarters column
        csv_url = result_data["csv_url"]
        download_resp = await client.get(csv_url)
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"].startswith("text/csv")
        result_df = pd.read_csv(io.StringIO(download_resp.text))
        assert len(result_df) == 2
        assert "headquarters" in result_df.columns
        print(f"  CSV: {len(result_df)} rows, columns={list(result_df.columns)}")

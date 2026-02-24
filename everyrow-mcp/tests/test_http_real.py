"""HTTP-mode integration tests with real everyrow API calls.

These tests spin up a Starlette ASGI server (via httpx + ASGITransport),
configure state for HTTP mode with a real Redis instance, and make real
API calls to the everyrow backend. They exercise the full pipeline:

    submit (MCP tool) → poll (REST endpoint) → results (MCP tool)

Requirements:
    - EVERYROW_API_KEY must be set
    - RUN_INTEGRATION_TESTS=1
    - Redis running on localhost:6379

Run with: pytest tests/test_http_real.py -v -s
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
from unittest.mock import patch

import httpx
import pandas as pd
import pytest
import redis.asyncio
from everyrow.api_utils import create_client
from starlette.applications import Starlette
from starlette.routing import Route

from everyrow_mcp import redis_store
from everyrow_mcp.models import AgentInput, HttpResultsInput, ProgressInput, ScreenInput
from everyrow_mcp.routes import api_download, api_progress
from everyrow_mcp.tools import (
    everyrow_agent,
    everyrow_progress,
    everyrow_results_http,
    everyrow_screen,
)
from tests.conftest import make_test_context, override_settings

# Skip unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.",
)

REDIS_TEST_DB = 15


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def real_redis():
    """Connect to real Redis on db=15, flush before/after each test."""
    client = redis.asyncio.Redis(
        host="localhost", port=6379, db=REDIS_TEST_DB, decode_responses=True
    )
    try:
        await client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable on localhost:6379")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def _http_mode(real_redis):
    """Configure settings for HTTP mode with real Redis."""
    with (
        override_settings(transport="streamable-http"),
        patch.object(redis_store, "get_redis_client", return_value=real_redis),
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
async def everyrow_client(_http_mode):
    """Create a real everyrow SDK client for MCP tools."""
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
    """Extract poll token from the progress_url in widget JSON."""
    data = json.loads(widget_json)
    progress_url = data.get("progress_url", "")
    match = re.search(r"token=([A-Za-z0-9_-]+)", progress_url)
    if not match:
        raise ValueError(f"No poll token in widget JSON: {widget_json}")
    return match.group(1)


async def poll_via_tool(task_id: str, ctx, max_polls: int = 30) -> str:
    """Poll everyrow_progress via MCP tool until complete."""
    for _ in range(max_polls):
        result = await everyrow_progress(ProgressInput(task_id=task_id), ctx)
        text = result[-1].text
        print(f"  Progress: {text.splitlines()[0]}")

        if "Completed:" in text or "everyrow_results" in text:
            return text
        if "failed" in text.lower() or "revoked" in text.lower():
            raise RuntimeError(f"Task failed: {text}")

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


async def poll_via_rest(
    client: httpx.AsyncClient,
    task_id: str,
    poll_token: str,
    max_polls: int = 30,
) -> dict:
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


class TestHttpScreenPipeline:
    """Full HTTP pipeline: submit → poll via REST → results via MCP tool."""

    @pytest.mark.asyncio
    async def test_screen_end_to_end(
        self,
        client: httpx.AsyncClient,
        everyrow_client,
        jobs_csv: str,
    ):
        """Submit a screen task, poll via REST, fetch results via MCP tool."""
        # 1. Submit via MCP tool (in HTTP mode)
        ctx = make_test_context(everyrow_client, mcp_server_url="http://testserver")
        result = await everyrow_screen(
            ScreenInput(
                task="Filter for remote positions with salary > $100k",
                input_csv=jobs_csv,
            ),
            ctx,
        )

        # HTTP mode: widget JSON + human text
        assert len(result) == 2
        widget_json = result[0].text
        human_text = result[1].text
        print(f"\nSubmit: {human_text}")

        widget = json.loads(widget_json)
        assert widget["status"] == "submitted"
        assert "progress_url" in widget

        task_id = widget["task_id"]
        poll_token = extract_poll_token(widget_json)

        # 2. Poll progress via REST endpoint
        progress = await poll_via_rest(client, task_id, poll_token)
        assert progress["status"] == "completed"
        # Screen tasks don't report row-level totals
        assert "session_url" in progress
        print(f"  Session: {progress['session_url']}")

        # 3. After completion, task token is cleaned up — next poll returns 404
        resp = await client.get(
            f"/api/progress/{task_id}", params={"token": poll_token}
        )
        assert resp.status_code == 404

        # 4. Fetch results via MCP tool — real Redis flow
        results = await everyrow_results_http(HttpResultsInput(task_id=task_id), ctx)

        assert len(results) == 2
        result_data = json.loads(results[0].text)
        assert "csv_url" in result_data
        assert "preview" in result_data
        assert result_data["total"] > 0
        print(f"  Results: {results[1].text}")

        # 5. Download CSV via the csv_url
        csv_url = result_data["csv_url"]
        assert csv_url.startswith("http://testserver/api/results/")
        download_resp = await client.get(csv_url)
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"].startswith("text/csv")
        reader = csv.reader(io.StringIO(download_resp.text))
        rows = list(reader)
        assert len(rows) >= 2  # header + at least one data row
        print(f"  CSV download: {len(rows) - 1} data rows")


class TestHttpAgentPipeline:
    """Full HTTP pipeline with agent tool: submit → poll → results."""

    @pytest.mark.asyncio
    async def test_agent_end_to_end(
        self,
        client: httpx.AsyncClient,
        everyrow_client,
        tmp_path,
    ):
        """Submit an agent task, poll via REST, verify results via MCP tool."""
        # Create small input (2 rows to minimize cost)
        df = pd.DataFrame([{"name": "Anthropic"}, {"name": "OpenAI"}])
        input_csv = tmp_path / "companies.csv"
        df.to_csv(input_csv, index=False)

        # 1. Submit via MCP tool
        ctx = make_test_context(everyrow_client, mcp_server_url="http://testserver")
        result = await everyrow_agent(
            AgentInput(
                task="Find the company's headquarters city.",
                input_csv=str(input_csv),
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

        assert len(result) == 2
        widget = json.loads(result[0].text)
        human_text = result[1].text
        print(f"\nSubmit: {human_text}")

        task_id = widget["task_id"]
        poll_token = extract_poll_token(result[0].text)

        # 2. Poll via REST until complete
        progress = await poll_via_rest(client, task_id, poll_token)
        assert progress["status"] == "completed"
        assert progress["completed"] == 2

        # 3. Fetch results via MCP tool — real Redis, page_size=1 for pagination
        results = await everyrow_results_http(
            HttpResultsInput(task_id=task_id, page_size=1), ctx
        )

        assert len(results) == 2
        result_data = json.loads(results[0].text)
        assert result_data["total"] == 2
        assert len(result_data["preview"]) == 1  # page_size=1
        assert "csv_url" in result_data
        print(f"  Page 1: {results[1].text}")

        # 4. Fetch second page (should come from Redis cache)
        results_p2 = await everyrow_results_http(
            HttpResultsInput(task_id=task_id, offset=1, page_size=1), ctx
        )

        assert len(results_p2) == 2
        result_data_p2 = json.loads(results_p2[0].text)
        assert len(result_data_p2["preview"]) == 1
        assert result_data_p2["total"] == 2
        print(f"  Page 2: {results_p2[1].text}")

        # 5. Download full CSV, verify 2 rows with headquarters column
        csv_url = result_data["csv_url"]
        download_resp = await client.get(csv_url)
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"].startswith("text/csv")
        result_df = pd.read_csv(io.StringIO(download_resp.text))
        assert len(result_df) == 2
        assert "headquarters" in result_df.columns
        print(f"  CSV: {len(result_df)} rows, columns={list(result_df.columns)}")


class TestProgressPollingModes:
    """Verify that both REST and MCP tool polling work for the same task."""

    @pytest.mark.asyncio
    async def test_dual_polling(
        self,
        client: httpx.AsyncClient,
        everyrow_client,
        jobs_csv: str,
    ):
        """Submit a task and poll using both REST endpoint and MCP tool."""
        ctx = make_test_context(everyrow_client, mcp_server_url="http://testserver")
        result = await everyrow_screen(
            ScreenInput(
                task="Filter for engineering roles",
                input_csv=jobs_csv,
            ),
            ctx,
        )

        widget = json.loads(result[0].text)
        task_id = widget["task_id"]
        poll_token = extract_poll_token(result[0].text)

        # Poll once via REST to verify it works
        rest_resp = await client.get(
            f"/api/progress/{task_id}", params={"token": poll_token}
        )
        assert rest_resp.status_code == 200
        rest_progress = rest_resp.json()
        print(
            f"\n  REST: {rest_progress['status']} — {rest_progress['completed']}/{rest_progress['total']}"
        )

        # Continue polling via MCP tool until complete
        final_text = await poll_via_tool(task_id, ctx)

        assert "everyrow_results" in final_text or "Completed:" in final_text

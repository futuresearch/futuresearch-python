"""Integration tests exercising the full HTTP MCP transport.

Unlike test_integration.py which calls tool functions directly as Python,
these tests start the server as a subprocess and connect via the MCP SDK's
streamablehttp_client — the real JSON-RPC-over-HTTP path.

Flow tested:
  streamablehttp_client → HTTP /mcp → JSON-RPC → tool dispatch
    → everyrow API (real LLM) → poll → preview → paginate → CSV download

Prerequisites:
  - Redis on localhost:6379
  - EVERYROW_API_KEY set (via env or ~/.claude/secrets/)

Run:
  RUN_INTEGRATION_TESTS=1 uv run pytest tests/test_http_transport.py -v -s
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import redis
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent

# Skip all tests unless opted in
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.",
)

REDIS_TEST_DB = 15  # isolated DB, flushed before/after


def _free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url: str, timeout: float = 15.0) -> None:
    """Block until GET /health returns 200 or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"Server at {base_url} did not become healthy within {timeout}s")


def _flush_redis_db(db: int = REDIS_TEST_DB) -> None:
    """Synchronously flush a Redis DB."""
    r = redis.Redis(host="localhost", port=6379, db=db)
    r.flushdb()
    r.close()


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def mcp_server() -> Generator[str, None, None]:
    """Start the MCP server subprocess on a random port with Redis DB 15.

    Yields the base URL (e.g. http://127.0.0.1:PORT).
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    _flush_redis_db(REDIS_TEST_DB)

    env = {
        **os.environ,
        "REDIS_DB": str(REDIS_TEST_DB),
        "ALLOW_NO_AUTH": "1",
    }

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "everyrow_mcp.server",
            "--http",
            "--no-auth",
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_health(base_url)
    except Exception:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        print(f"Server stdout:\n{stdout.decode()}", file=sys.stderr)
        print(f"Server stderr:\n{stderr.decode()}", file=sys.stderr)
        raise

    yield base_url

    # Teardown
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    _flush_redis_db(REDIS_TEST_DB)


@asynccontextmanager
async def open_mcp_session(base_url: str):
    """Context manager for an MCP session — must be used within a single task."""
    url = f"{base_url}/mcp"
    async with streamablehttp_client(url=url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


@pytest.fixture
async def http_client(mcp_server: str):
    """httpx.AsyncClient pointed at the MCP server base URL."""
    async with httpx.AsyncClient(base_url=mcp_server, timeout=30.0) as client:
        yield client


# ── Helpers ─────────────────────────────────────────────────────────


async def poll_via_mcp(
    session: ClientSession,
    task_id: str,
    max_polls: int = 60,
    interval: float = 3.0,
) -> str:
    """Poll everyrow_progress via MCP tool call until terminal state.

    Returns the final human-readable text.
    """
    for i in range(max_polls):
        result = await session.call_tool(
            "everyrow_progress", {"params": {"task_id": task_id}}
        )
        texts = [b.text for b in result.content if isinstance(b, TextContent)]
        human_text = texts[-1] if texts else ""
        print(f"  Poll {i + 1}: {human_text.splitlines()[0]}")

        if "everyrow_results" in human_text or "Completed:" in human_text:
            return human_text
        if "failed" in human_text.lower() or "revoked" in human_text.lower():
            raise RuntimeError(f"Task failed: {human_text}")

        await asyncio.sleep(interval)

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


def parse_widget_json(content_blocks) -> dict[str, Any]:
    """Parse the first TextContent block as JSON (the widget data)."""
    for block in content_blocks:
        if isinstance(block, TextContent):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                continue
    raise ValueError("No JSON widget block found in response")


# ── Test classes ────────────────────────────────────────────────────


class TestMcpHttpBasics:
    """Smoke tests for the HTTP transport layer."""

    async def test_health_endpoint(self, http_client: httpx.AsyncClient):
        """GET /health returns {"status": "ok"}."""
        r = await http_client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_list_tools(self, mcp_server: str):
        """session.list_tools() returns all registered tools."""
        async with open_mcp_session(mcp_server) as session:
            resp = await session.list_tools()
            tool_names = sorted(t.name for t in resp.tools)
            expected = sorted(
                [
                    "everyrow_agent",
                    "everyrow_classify",
                    "everyrow_single_agent",
                    "everyrow_rank",
                    "everyrow_dedupe",
                    "everyrow_merge",
                    "everyrow_progress",
                    "everyrow_results",
                ]
            )
            assert tool_names == expected, f"Got tools: {tool_names}"


class TestAgentHttpTransport:
    """Full lifecycle test: submit → poll → preview → paginate → CSV download."""

    async def test_agent_submit_poll_results(
        self,
        mcp_server: str,
        http_client: httpx.AsyncClient,
    ):
        """End-to-end agent task through the real HTTP transport."""

        async with open_mcp_session(mcp_server) as session:
            # ── 1. Submit everyrow_agent ────────────────────────────
            submit_result = await session.call_tool(
                "everyrow_agent",
                {
                    "params": {
                        "task": "Find the company's headquarters city.",
                        "data": "name\nAnthropic\nOpenAI",
                        "response_schema": {
                            "type": "object",
                            "properties": {
                                "headquarters": {
                                    "type": "string",
                                    "description": "City where HQ is located",
                                },
                            },
                            "required": ["headquarters"],
                        },
                    }
                },
            )

            # Fail fast on tool errors
            first_block = submit_result.content[0] if submit_result.content else None
            first_text = (
                first_block.text if isinstance(first_block, TextContent) else ""
            )
            assert not first_text.startswith("Error"), f"Tool error: {first_text}"

            # Parse widget JSON from the first content block
            widget = parse_widget_json(submit_result.content)
            print(f"\nSubmit widget: {json.dumps(widget, indent=2)}")

            assert "task_id" in widget, f"Missing task_id in widget: {widget}"
            task_id = widget["task_id"]
            assert widget.get("status") == "submitted"
            assert "progress_url" in widget, f"Missing progress_url: {widget}"

            # ── 2. Poll until completed ─────────────────────────────
            await poll_via_mcp(session, task_id)

            # ── 3. First page: page_size=1 → 1 row of 2 ───────────
            results_resp = await session.call_tool(
                "everyrow_results",
                {"params": {"task_id": task_id, "page_size": 1}},
            )
            results_texts = [
                b.text for b in results_resp.content if isinstance(b, TextContent)
            ]
            results_widget = parse_widget_json(results_resp.content)
            print(f"\nResults page 1 widget: {json.dumps(results_widget, indent=2)}")

            # Widget assertions
            assert "preview" in results_widget
            assert len(results_widget["preview"]) == 1, (
                f"Expected 1 preview row, got {len(results_widget['preview'])}"
            )
            assert results_widget["total"] == 2
            assert "csv_url" in results_widget

            csv_url = results_widget["csv_url"]

            # Human text assertions
            human_text = results_texts[-1]
            assert "1-1 of 2" in human_text, (
                f"Expected pagination text, got: {human_text}"
            )
            assert "offset=1" in human_text, (
                f"Expected next-page hint, got: {human_text}"
            )

            # ── 4. Second page: offset=1, page_size=1 → final page
            results_resp2 = await session.call_tool(
                "everyrow_results",
                {"params": {"task_id": task_id, "offset": 1, "page_size": 1}},
            )
            results_widget2 = parse_widget_json(results_resp2.content)
            results_texts2 = [
                b.text for b in results_resp2.content if isinstance(b, TextContent)
            ]
            print(f"\nResults page 2 widget: {json.dumps(results_widget2, indent=2)}")

            assert len(results_widget2["preview"]) == 1
            # Final page — human text should say "final page"
            human_text2 = results_texts2[-1]
            assert "final page" in human_text2.lower(), (
                f"Expected 'final page' in text, got: {human_text2}"
            )

        # ── 5. Download full CSV via REST ──────────────────────────
        csv_response = await http_client.get(csv_url)
        assert csv_response.status_code == 200, (
            f"CSV download failed: {csv_response.status_code} {csv_response.text}"
        )
        assert "text/csv" in csv_response.headers.get("content-type", "")

        # Parse CSV and verify
        reader = csv.DictReader(io.StringIO(csv_response.text))
        rows = list(reader)
        assert len(rows) == 2, f"Expected 2 CSV rows, got {len(rows)}"
        assert reader.fieldnames is not None
        assert "headquarters" in reader.fieldnames, (
            f"Expected 'headquarters' column, got columns: {reader.fieldnames}"
        )
        print(f"\nCSV rows: {rows}")

        # ── 6. REST progress endpoint still works ──────────────────
        progress_url = widget["progress_url"]
        progress_resp = await http_client.get(progress_url)
        # After completion, the task token is popped so progress may return
        # 403/404. The key point is the endpoint responds and the poll token
        # was valid during the task lifecycle.
        assert progress_resp.status_code in (200, 403, 404), (
            f"Progress endpoint unexpected status: {progress_resp.status_code}"
        )

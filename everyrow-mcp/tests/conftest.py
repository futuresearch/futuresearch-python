"""Shared pytest fixtures for everyrow MCP server tests."""

from __future__ import annotations

# Set env vars for HttpSettings before any everyrow imports
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("MCP_SERVER_URL", "https://mcp.example.com")
os.environ.setdefault("REDIS_PORT", "6380")

import socket
import subprocess
import time
from pathlib import Path

import pandas as pd
import pytest
import redis.asyncio as aioredis
from everyrow.api_utils import create_client

from everyrow_mcp import app

_REDIS_PORT = 16379  # non-default port to avoid clashing with local Redis


@pytest.fixture(scope="session")
def _redis_server():
    """Start a local redis-server process for the test session."""
    proc = subprocess.Popen(
        [
            "redis-server",
            "--port",
            str(_REDIS_PORT),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for Redis to accept connections
    for _ in range(30):
        try:
            s = socket.create_connection(("localhost", _REDIS_PORT), timeout=0.1)
            s.close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("Test redis-server did not start in time")

    yield

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
async def fake_redis(_redis_server) -> aioredis.Redis:
    """A real Redis client, flushed after each test."""
    r = aioredis.Redis(host="localhost", port=_REDIS_PORT, decode_responses=True)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


@pytest.fixture
async def everyrow_client():
    """Initialize the everyrow client.

    This fixture sets up the global _client in the server module,
    which is normally initialized by the MCP server's lifespan context.
    """
    try:
        with create_client() as client:
            app._client = client
            yield client
    finally:
        app._client = None


@pytest.fixture
def jobs_csv(tmp_path: Path) -> str:
    """Create a jobs CSV for testing."""
    df = pd.DataFrame(
        [
            {
                "company": "Airtable",
                "title": "Senior Engineer",
                "salary": "$185000",
                "location": "Remote",
            },
            {
                "company": "Vercel",
                "title": "Lead Engineer",
                "salary": "Competitive",
                "location": "NYC",
            },
            {
                "company": "Notion",
                "title": "Staff Engineer",
                "salary": "$200000",
                "location": "San Francisco",
            },
            {
                "company": "Linear",
                "title": "Junior Developer",
                "salary": "$85000",
                "location": "Remote",
            },
            {
                "company": "Descript",
                "title": "Principal Architect",
                "salary": "$250000",
                "location": "Remote",
            },
        ]
    )
    path = tmp_path / "jobs.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def companies_csv(tmp_path: Path) -> str:
    """Create a companies CSV for testing."""
    df = pd.DataFrame(
        [
            {"name": "TechStart", "industry": "Software", "size": 50},
            {"name": "AILabs", "industry": "AI/ML", "size": 30},
            {"name": "DataFlow", "industry": "Data", "size": 100},
            {"name": "CloudNine", "industry": "Cloud", "size": 75},
            {"name": "OldBank", "industry": "Finance", "size": 5000},
        ]
    )
    path = tmp_path / "companies.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def contacts_csv(tmp_path: Path) -> str:
    """Create a contacts CSV with duplicates for testing."""
    df = pd.DataFrame(
        [
            {
                "name": "John Smith",
                "email": "john.smith@acme.com",
                "company": "Acme Corp",
            },
            {
                "name": "J. Smith",
                "email": "jsmith@acme.com",
                "company": "Acme Corporation",
            },
            {
                "name": "Alexandra Butoi",
                "email": "a.butoi@tech.io",
                "company": "TechStart",
            },
            {
                "name": "A. Butoi",
                "email": "alexandra.b@tech.io",
                "company": "TechStart Inc",
            },
            {"name": "Mike Johnson", "email": "mike@data.com", "company": "DataFlow"},
        ]
    )
    path = tmp_path / "contacts.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def products_csv(tmp_path: Path) -> str:
    """Create a products CSV for testing."""
    df = pd.DataFrame(
        [
            {
                "product_name": "Photoshop",
                "category": "Design",
                "vendor": "Adobe Systems",
            },
            {
                "product_name": "VSCode",
                "category": "Development",
                "vendor": "Microsoft",
            },
            {
                "product_name": "Slack",
                "category": "Communication",
                "vendor": "Salesforce",
            },
        ]
    )
    path = tmp_path / "products.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def suppliers_csv(tmp_path: Path) -> str:
    """Create a suppliers CSV for testing."""
    df = pd.DataFrame(
        [
            {"company_name": "Adobe Inc", "approved": True},
            {"company_name": "Microsoft Corporation", "approved": True},
            {"company_name": "Salesforce Inc", "approved": True},
        ]
    )
    path = tmp_path / "suppliers.csv"
    df.to_csv(path, index=False)
    return str(path)

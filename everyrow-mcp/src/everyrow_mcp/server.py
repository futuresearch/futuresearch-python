"""MCP server for everyrow SDK operations."""

import logging
import os
import sys

import everyrow_mcp.tools  # noqa: F401  — registers @mcp.tool() decorators

# Re-export models, helpers, and tools so existing imports from
# ``everyrow_mcp.server`` keep working (tests, conftest, etc.).
from everyrow_mcp.app import (  # noqa: F401
    _clear_task_state,
    _client,
    _write_task_state,
    mcp,
)
from everyrow_mcp.models import (  # noqa: F401
    AgentInput,
    DedupeInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ResultsInput,
    ScreenInput,
    SingleAgentInput,
    _schema_to_model,
)
from everyrow_mcp.tools import (  # noqa: F401
    everyrow_agent,
    everyrow_dedupe,
    everyrow_merge,
    everyrow_progress,
    everyrow_rank,
    everyrow_results,
    everyrow_screen,
    everyrow_single_agent,
)


def main():
    """Run the MCP server."""
    # Signal to the SDK that we're inside the MCP server (suppresses plugin hints)
    os.environ["EVERYROW_MCP_SERVER"] = "1"

    # Configure logging to use stderr only (stdout is reserved for JSON-RPC)
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s: %(message)s",
        force=True,
    )

    # Check for API key before starting
    if "EVERYROW_API_KEY" not in os.environ:
        logging.error("EVERYROW_API_KEY environment variable is not set.")
        logging.error("Get an API key at https://everyrow.io/api-key")
        sys.exit(1)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

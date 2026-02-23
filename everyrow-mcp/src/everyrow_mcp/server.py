"""MCP server for everyrow SDK operations."""

import argparse
import logging
import os
import sys
from textwrap import dedent

from pydantic import BaseModel

import everyrow_mcp.tools  # noqa: F401  — registers @mcp.tool() decorators
from everyrow_mcp.app import mcp
from everyrow_mcp.config import settings
from everyrow_mcp.http_config import configure_http_mode
from everyrow_mcp.redis_store import Transport
from everyrow_mcp.tools import (
    _RESULTS_ANNOTATIONS,
    _RESULTS_META,
    everyrow_results_http,
)


class InputArgs(BaseModel):
    http: bool = False
    no_auth: bool = False
    port: int = 8000
    host: str = "0.0.0.0"


def parse_args() -> InputArgs:
    parser = argparse.ArgumentParser(description="everyrow MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use Streamable HTTP transport instead of stdio.",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable OAuth (dev only). Requires EVERYROW_API_KEY.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transport (default: 0.0.0.0).",
    )
    input_args = InputArgs.model_validate(vars(parser.parse_args()))

    if input_args.no_auth and not input_args.http:
        parser.error("--no-auth requires --http")

    if input_args.no_auth and not os.environ.get("ALLOW_NO_AUTH"):
        print(
            dedent("""ERROR: --no-auth requires the ALLOW_NO_AUTH=1 environment variable.\n
            This prevents accidental unauthenticated deployments in production."""),
            file=sys.stderr,
        )
        sys.exit(1)

    return input_args


def main():
    """Run the MCP server."""
    input_args = parse_args()
    # Signal to the SDK that we're inside the MCP server (suppresses plugin hints)
    os.environ["EVERYROW_MCP_SERVER"] = "1"
    transport = Transport.HTTP if input_args.http else Transport.STDIO
    settings.transport = transport.value

    # tools.py registers everyrow_results_stdio by default.
    # Override with the HTTP variant when running in HTTP mode.
    if transport == Transport.HTTP:
        mcp.tool(
            name="everyrow_results",
            structured_output=False,
            annotations=_RESULTS_ANNOTATIONS,
            meta=_RESULTS_META,
        )(everyrow_results_http)

    if input_args.http:
        if input_args.no_auth:
            mcp_server_url = f"http://localhost:{input_args.port}"
        else:
            mcp_server_url = settings.mcp_server_url

        configure_http_mode(
            mcp=mcp,
            host=input_args.host,
            port=input_args.port,
            no_auth=input_args.no_auth,
            mcp_server_url=mcp_server_url,
        )
    else:
        # Configure logging to use stderr only (stdout is reserved for JSON-RPC)
        logging.basicConfig(
            level=logging.WARNING,
            stream=sys.stderr,
            format="%(levelname)s: %(message)s",
            force=True,
        )

        # Validate EVERYROW_API_KEY is set (used by SDK client in lifespan)
        if not os.environ.get("EVERYROW_API_KEY"):
            logging.error("Configuration error: EVERYROW_API_KEY is required")
            logging.error("Get an API key at https://everyrow.io/api-key")
            sys.exit(1)

    mcp.run(transport=transport.value)


if __name__ == "__main__":
    main()

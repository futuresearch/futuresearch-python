#!/usr/bin/env python3
"""Fetch the live OpenAPI spec from the everyrow API and save it for the docs build.

The spec is fetched at build time (not committed) so the docs always reflect
the currently-deployed API. The output file is gitignored.
"""
import json
import sys
import urllib.request
from pathlib import Path

SPEC_URL = "https://everyrow.io/api/v0/openapi.json"
OUTPUT = Path(__file__).resolve().parent.parent / "public" / "openapi.json"


def main() -> None:
    print(f"Fetching OpenAPI spec from {SPEC_URL} ...")
    try:
        req = urllib.request.Request(SPEC_URL, headers={"User-Agent": "everyrow-docs-build/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            spec = json.loads(resp.read())
    except Exception as exc:
        # If the fetch fails and we have a cached copy, use it
        if OUTPUT.exists():
            print(f"WARNING: Fetch failed ({exc}), using cached {OUTPUT}")
            return
        print(f"ERROR: Fetch failed and no cached spec exists: {exc}", file=sys.stderr)
        sys.exit(1)

    # Set the server URL to the public endpoint
    spec["servers"] = [{"url": "https://everyrow.io/api/v0"}]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

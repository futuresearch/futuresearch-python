#!/bin/bash
# Script to generate OpenAPI client files and clean up generated files
#
# By default the spec is fetched from the live public API. Pass
# `--path <spec.json>` to generate from a local spec instead (used by
# cohort/engine/generate_openapi.py to regenerate hermetically from the
# code in this repo).

set -e  # Exit on error

SOURCE_ARGS=(--url "https://futuresearch.ai/api/v0/openapi.json")
if [ "$1" = "--path" ]; then
  if [ -z "$2" ]; then
    echo "Usage: $0 [--path <spec.json>]" >&2
    exit 1
  fi
  SOURCE_ARGS=(--path "$2")
fi

echo "Generating OpenAPI client files..."
uv run openapi-python-client generate \
  "${SOURCE_ARGS[@]}" \
  --config openapi-python-client.yaml \
  --overwrite \
  --meta uv

echo "Removing generated files from futuresearch..."
rm -f src/futuresearch/README.md
rm -f src/futuresearch/.gitignore
rm -f src/futuresearch/pyproject.toml

echo "OpenAPI generation complete!"

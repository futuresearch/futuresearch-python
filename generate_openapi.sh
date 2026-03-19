#!/bin/bash
# Script to generate OpenAPI client files and clean up generated files

set -e  # Exit on error

echo "Generating OpenAPI client files..."
uv run openapi-python-client generate \
  --url "https://futuresearch.ai/api/v0/openapi.json" \
  --config openapi-python-client.yaml \
  --overwrite \
  --meta uv

echo "Removing generated files from futuresearch..."
rm -f src/futuresearch/README.md
rm -f src/futuresearch/.gitignore
rm -f src/futuresearch/pyproject.toml

echo "OpenAPI generation complete!"


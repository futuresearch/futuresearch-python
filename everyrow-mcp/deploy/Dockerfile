# Stage 1: Build Python environment with uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy workspace root pyproject + lock + README, then each package
COPY --link pyproject.toml uv.lock README.md ./
COPY --link src/ ./src/
COPY --link everyrow-mcp/pyproject.toml everyrow-mcp/README.md ./everyrow-mcp/
COPY --link everyrow-mcp/src/ ./everyrow-mcp/src/

# Install everyrow-mcp and its dependencies (includes workspace everyrow package)
RUN uv sync --package everyrow-mcp --no-dev --no-sources --no-editable

# Stage 2: Slim runtime
FROM python:3.13-slim

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["everyrow-mcp", "--http", "--port", "8000", "--host", "0.0.0.0"]

WORKDIR /app
COPY --link --from=build /app/.venv .venv

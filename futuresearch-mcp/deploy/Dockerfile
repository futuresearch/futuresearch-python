# Stage 1: Build Python environment with uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy workspace root pyproject + lock + README, then each package
COPY --link pyproject.toml uv.lock README.md ./
COPY --link src/ ./src/
COPY --link futuresearch-mcp/pyproject.toml futuresearch-mcp/README.md ./futuresearch-mcp/
COPY --link futuresearch-mcp/src/ ./futuresearch-mcp/src/

# Install futuresearch-mcp and its dependencies (includes workspace everyrow package)
RUN uv sync --package futuresearch-mcp --no-dev --no-sources --no-editable

# Stage 2: Slim runtime
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd -r -g 10000 mcp && useradd -r -u 10000 -g mcp -d /app -s /sbin/nologin mcp

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

WORKDIR /app
COPY --link --from=build /app/.venv .venv
RUN chown -R mcp:mcp /app

USER mcp

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["futuresearch-mcp", "--http", "--port", "8000", "--host", "0.0.0.0"]

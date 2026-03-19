---
name: run-mcp-local
description: Run the FutureSearch HTTP MCP server locally with Docker Compose and optionally expose it via Cloudflare tunnel. Use when starting/stopping the local MCP server, debugging startup issues, connecting Claude.ai or Claude Desktop to a local instance, or checking server logs. Triggers on mcp local, mcp server, run mcp, mcp docker, mcp tunnel, cloudflare tunnel, mcp logs.
---

# Running the FutureSearch MCP Server Locally

Two-container stack: **mcp-server** (FastAPI on :8000) and **redis** (on :6379), orchestrated by `futuresearch-mcp/deploy/docker-compose.yaml` with local overrides.

## Pre-flight Checks

**CRITICAL: Always check for stale processes on port 8000 before starting.**

A leftover `futuresearch-mcp --no-auth` or similar process on the host will shadow the Docker container's port binding. All requests hit the stale process instead of the container — this can look like auth routes are broken, sheets tools are missing, etc.

```bash
# Check for anything on port 8000
lsof -i :8000

# Kill if needed
lsof -ti :8000 | xargs kill -9
```

Also check Docker is running:
```bash
docker info --format '{{.ServerVersion}}' || colima start
```

## Quick Start

```bash
cd futuresearch-mcp/deploy

REDIS_PASSWORD=testpass \
MCP_SERVER_URL=http://localhost:8000 \
  docker compose \
    -f docker-compose.yaml \
    -f docker-compose.local.yaml \
  up -d --build
```

Verify: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health` should return `200`.

### Optional env vars

Pass these alongside `REDIS_PASSWORD` and `MCP_SERVER_URL`:

| Env var | Default | Purpose |
|---------|---------|---------|
| `ENABLE_SHEETS_TOOLS` | `false` | Register Google Sheets tools |
| `TRUST_PROXY_HEADERS` | `false` | Trust X-Forwarded-For (required behind tunnel) |
| `EXTRA_ALLOWED_HOSTS` | (empty) | Extra hostnames for DNS rebinding allowlist |

These are templated in `docker-compose.local.yaml` as `${VAR:-default}` — the container must be **recreated** (not just restarted) for env var changes to take effect.

## Secrets

The `.env` file at `futuresearch-mcp/deploy/.env` contains production secrets (Supabase, API keys, upload secret). It is already present and should NOT be committed or overwritten.

`REDIS_PASSWORD` is intentionally NOT in `.env` — always pass it as an env var (`testpass` for local dev).

### Worktrees

The `.env` file is gitignored and won't exist in worktrees. Symlink it:

```bash
ln -s /Users/rafaelpoyiadzi/Documents/git/futuresearch-python/futuresearch-mcp/deploy/.env \
      <worktree-path>/futuresearch-mcp/deploy/.env
```

## Exposing via Cloudflare Tunnel

Required when testing with Claude.ai or Claude Desktop, which can't reach `localhost`.

### Step 1: Kill stale tunnels and processes

```bash
pkill -f cloudflared 2>/dev/null
rm -f /tmp/cf-tunnel.log
lsof -ti :8000 | xargs kill -9 2>/dev/null
```

### Step 2: Start the tunnel

```bash
cloudflared tunnel --url http://localhost:8000 2>/tmp/cf-tunnel.log &
sleep 6
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | head -1
```

This prints a URL like `https://something-something.trycloudflare.com`.

### Step 3: Start (or restart) the MCP server with the tunnel URL

The server must know its public URL for OAuth redirects to work:

```bash
cd futuresearch-mcp/deploy

REDIS_PASSWORD=testpass \
MCP_SERVER_URL=https://something-something.trycloudflare.com \
TRUST_PROXY_HEADERS=true \
ENABLE_SHEETS_TOOLS=true \
  docker compose \
    -f docker-compose.yaml \
    -f docker-compose.local.yaml \
  up -d --build
```

Key: `MCP_SERVER_URL` must match the tunnel URL exactly, and `TRUST_PROXY_HEADERS=true` is required so the server trusts the forwarded headers from Cloudflare.

### Step 4: Verify OAuth discovery works end-to-end

```bash
# Through the tunnel (what Claude.ai sees)
curl -s https://<tunnel-url>/.well-known/oauth-authorization-server | python3 -m json.tool | head -5

# Locally
curl -s http://localhost:8000/.well-known/oauth-authorization-server | python3 -m json.tool | head -5
```

Both should return JSON with `issuer`, `authorization_endpoint`, etc. If local returns 404 but tunnel works (or vice versa), check for stale processes on port 8000.

### Step 5: Connect clients

**Claude.ai / Claude Desktop**: Use the tunnel URL as the MCP server URL in the client config.

**Claude Code**: Add a project-scoped MCP server (writes to `.claude/settings.local.json` in the current dir, not the global config):

```bash
claude mcp add futuresearch --scope project --transport http <TUNNEL_URL>/mcp
```

Then restart Claude Code. Remove with `claude mcp remove futuresearch --scope project`.

## Logs

```bash
# All logs
docker logs deploy-mcp-server-1 -f

# Filter for errors
docker logs deploy-mcp-server-1 2>&1 | grep -iE "error|warn|401|500"

# Check User-Agent strings (for widget/client detection work)
docker logs deploy-mcp-server-1 2>&1 | grep "User-Agent"
```

## Teardown

```bash
cd futuresearch-mcp/deploy

REDIS_PASSWORD=testpass MCP_SERVER_URL=http://localhost:8000 \
  docker compose -f docker-compose.yaml -f docker-compose.local.yaml down
```

Kill the tunnel: `pkill -f cloudflared` or `kill %1` if it was backgrounded.

## No-Auth Mode (without Docker)

Run the server directly with `uv run` — no Docker needed. Useful for quick local testing with the MCP Inspector.

**WARNING:** If you leave this running and later start the Docker stack, the local process will shadow Docker's port 8000. Always kill it first: `lsof -ti :8000 | xargs kill -9`

### Prerequisites

- Redis running on localhost:6379 (e.g. `docker run -d --name test-redis -p 6379:6379 redis:7-alpine`)
- `FUTURESEARCH_API_KEY` (or legacy `FUTURESEARCH_API_KEY`) in `~/.claude/secrets/remote.env`

### Start the server

```bash
cd futuresearch-mcp
ALLOW_NO_AUTH=1 \
UPLOAD_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
EXTRA_ALLOWED_HOSTS="host.docker.internal,localhost" \
  bash scripts/run-no-auth.sh
```

### Connect with MCP Inspector

1. Start the Inspector: `npx @modelcontextprotocol/inspector`
2. Open the URL it prints (includes `MCP_PROXY_AUTH_TOKEN`)
3. Settings:
   - Transport: **Streamable HTTP**
   - Mode: **Via Proxy**
   - URL: `http://localhost:8000/mcp`
   - Leave all OAuth fields **blank**
4. Click **Connect**

Note: Direct mode won't work (CORS). Auth mode won't work (Inspector v0.21.0 doesn't handle the OAuth flow). Use Via Proxy with no-auth.

### Connect with SDK client

```bash
uv run python scripts/mcp_call.py list
uv run python scripts/mcp_call.py call futuresearch_balance
uv run python scripts/mcp_call.py call futuresearch_agent '{"params": {"task": "...", "data": [...]}}'
```

Note: `mcp_call.py` only works against `--no-auth` servers. It doesn't do OAuth, so authenticated servers will show a subset of tools or fail.

## Common Issues

| Problem | Solution |
|---------|----------|
| `required variable REDIS_PASSWORD is missing` | Pass `REDIS_PASSWORD=testpass` as env var |
| `required variable MCP_SERVER_URL is missing` | Pass `MCP_SERVER_URL=http://localhost:8000` (or tunnel URL) |
| OAuth 401 when connecting via tunnel | `MCP_SERVER_URL` doesn't match the tunnel URL, or `TRUST_PROXY_HEADERS=true` is missing |
| OAuth discovery returns 404 | **Check `lsof -i :8000`** — a stale local process is likely shadowing Docker. Kill it and restart containers with `down`/`up` (not just `restart`) |
| Port 8000 already in use | `lsof -ti :8000 | xargs kill -9` then restart |
| Redis connection refused | Check redis container is healthy: `docker ps | grep redis` |
| cloudflared output is empty | It writes to stderr: use `2>/tmp/cf-tunnel.log` redirect |
| Container doesn't pick up code changes | Add `--build` to the `docker compose up` command |
| Container doesn't pick up env var changes | Must recreate: `docker compose ... down && docker compose ... up -d` |
| `.env` not found in worktree | Symlink from main repo: `ln -s <main>/futuresearch-mcp/deploy/.env <worktree>/futuresearch-mcp/deploy/.env` |
| Sheets tools not showing in tool list | Pass `ENABLE_SHEETS_TOOLS=true` and recreate the container |
| `mcp_call.py` shows fewer tools than expected | It connects without auth — authenticated servers may filter tools |
| Docker daemon not running | `colima start` (may need `colima stop && colima start` if socket is stale) |

## Key Files

| File | Purpose |
|------|---------|
| `futuresearch-mcp/deploy/docker-compose.yaml` | Base compose (server + redis) |
| `futuresearch-mcp/deploy/docker-compose.local.yaml` | Local overrides (ports, env passthrough) |
| `futuresearch-mcp/deploy/.env` | Production secrets (DO NOT commit changes) |
| `futuresearch-mcp/deploy/Dockerfile` | Server container build |

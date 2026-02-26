# Stateless HTTP Mode for Multi-Replica Scaling

**Date:** 2026-02-26
**Status:** Implemented + locally verified

## Problem

The MCP server holds sessions in memory — one per client connection. When running >1 pod behind a load balancer, requests from the same client can land on different pods, causing **409 Conflict** errors because the receiving pod has no record of that session.

GKE's Gateway API (via `GCPBackendPolicy`) supports cookie-based session affinity, but the MCP SDK's HTTP client does not propagate cookies. Header-based affinity (e.g. on `Mcp-Session-Id`) is not supported by GCPBackendPolicy. This makes traditional session affinity unreliable for MCP traffic.

## Solution: Stateless HTTP Mode

FastMCP supports `stateless_http=True`, which eliminates in-memory sessions entirely. Each request is independent — no session state, no affinity requirement.

```python
# In configure_http_mode():
mcp.settings.stateless_http = True
```

**Trade-off:** Stateless mode skips the MCP `initialize` handshake, so `ctx.session.client_params` is always `None`. We previously relied on `client_params.clientInfo.name` to detect which client is connecting (Claude.ai vs Claude Code) for the widget whitelist.

## User-Agent Detection (Replacing clientInfo)

### The detection chain

Widget support detection now uses a three-tier approach:

1. **MCP Apps UI capability** (`experimental["io.modelcontextprotocol/ui"]`) — spec-recommended, future-proof. Not available in stateless mode.

2. **Name-based whitelist** (`clientInfo.name`) — pragmatic fallback for stateful connections. Not available in stateless mode.

3. **User-Agent fallback** (NEW) — for stateless HTTP mode where tiers 1 and 2 are unavailable.

### How it works

A `ContextVar[str]` propagates the HTTP `User-Agent` header from the Starlette middleware layer into MCP tool functions. This follows the same pattern as `auth_context_var` in the MCP SDK's auth middleware.

```python
# http_config.py
_user_agent_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_agent", default="")

# Set in _RequestLoggingMiddleware.dispatch():
ua_token = _user_agent_var.set(request.headers.get("user-agent", ""))
```

### Default behaviour in stateless mode

- **Known non-widget UA** (e.g. contains "claude-code") → no widget
- **Unknown UA** → **show widget** (HTTP mode traffic is predominantly Claude.ai/Desktop)

This inverts the default from stateful mode (where unknown = no widget) because the population of HTTP clients is almost entirely widget-capable Claude.ai/Desktop users.

### Observed User-Agent strings (local testing, Feb 2026)

| Client | User-Agent | Widgets? |
|--------|-----------|----------|
| Claude.ai | `Claude-User` | Yes (no blocklist match) |
| Claude Code | `claude-code/2.1.59 (cli)` | No (matches `"claude-code"`) |
| Claude Code OAuth helper | `Bun/1.3.10` | n/a (only hits auth endpoints) |
| MCP SDK test client | `python-httpx/0.28.1` | Yes (no blocklist match) |
| Browser (OAuth redirect) | `Mozilla/5.0 ...Chrome/144` | n/a (only hits auth endpoints) |

The blocklist substring `"claude-code"` correctly matches Claude Code's tool-call UA without false-positiving on the OAuth helper or browser UAs.

**Still unknown:** Claude Desktop's User-Agent (likely `Claude-User` or similar — needs verification).

## Helm Chart: Session Affinity (Defense-in-Depth)

Even though the server is now stateless, we add session affinity as a zero-cost safety net. If we ever need to revert to stateful mode, the infrastructure is already in place.

### GCPBackendPolicy (L7 load balancer)

New `gcpbackendpolicy.yaml`:
```yaml
apiVersion: networking.gke.io/v1
kind: GCPBackendPolicy
spec:
  default:
    sessionAffinity:
      type: GENERATED_COOKIE
      cookieTtlSec: 3600
```

The GKE L7 LB sets a cookie on the first response and routes subsequent requests to the same backend. This only works if the client propagates cookies — which browsers do but MCP SDK clients may not. Hence "defense-in-depth" rather than primary solution.

### Service-level ClientIP affinity (kube-proxy)

```yaml
# service.yaml
sessionAffinity: ClientIP
sessionAffinityConfig:
  clientIP:
    timeoutSeconds: 3600
```

kube-proxy maps source IPs to backends. Works regardless of cookie support. Less precise than cookies (multiple users behind the same NAT get the same pod) but provides a reasonable fallback.

### Configuration

Both are enabled by default in `values.yaml` and can be toggled:
```yaml
sessionAffinity:
  gcpBackendPolicy:
    enabled: true
    cookieTtlSec: 3600
  clientIP:
    enabled: true
    timeoutSeconds: 3600
```

## Files Changed

| File | Change |
|------|--------|
| `src/everyrow_mcp/http_config.py` | Added `_user_agent_var` ContextVar, `get_user_agent()`, set UA in middleware, log UA |
| `src/everyrow_mcp/tool_helpers.py` | `client_supports_widgets()` tier 3 UA fallback, `log_client_info()` logs UA when stateless |
| `src/everyrow_mcp/app.py` | (unchanged — `stateless_http` set in `configure_http_mode`) |
| `deploy/chart/templates/gcpbackendpolicy.yaml` | New: GCPBackendPolicy with GENERATED_COOKIE |
| `deploy/chart/templates/service.yaml` | Conditional `sessionAffinity: ClientIP` |
| `deploy/chart/values.yaml` | New `sessionAffinity` config section |

## Verification Plan

1. `uv run pytest tests/` — **371 passed** (done)
2. Deploy to staging (1 replica), run basic E2E
3. Connect from Claude.ai → check logs for User-Agent, verify widget renders
4. Connect from Claude Code → check logs for User-Agent, verify no widget
5. Scale to 2 replicas, verify no 409 errors
6. `kubectl get gcpbackendpolicy -n everyrow-mcp-staging` — verify resource created

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| UA blocklist misses a new client | Default to showing widgets in HTTP mode — worst case a non-widget client gets widget JSON (wastes tokens but doesn't break) |
| `stateless_http` changes auth behaviour | Auth is handled by middleware before MCP layer; stateless only affects session tracking |
| GCPBackendPolicy not supported on cluster | Guarded by `enabled: true` in values; can toggle off per environment |
| Lifespan runs per-request instead of per-session | Our lifespans already handle this — HTTP lifespans don't hold long-lived resources |

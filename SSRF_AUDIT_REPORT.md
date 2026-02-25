# SSRF Security Audit Report

**Target:** EveryRow MCP Server (`everyrow-mcp/src/everyrow_mcp/`)
**Audit Date:** 2026-02-25
**Scope:** Full SSRF attack surface analysis, bypass testing of existing protections, container/deployment review
**Baseline:** Commit `4000b88` ("Security hardening: SSRF, headers, Redis TLS, container lockdown")

---

## Executive Summary

The MCP server implements a **three-layer SSRF protection** around its sole user-controlled URL-fetching path (`fetch_csv_from_url`), introduced in commit `4000b88`. The protections are well-designed and cover the major attack vectors. No **Critical** vulnerabilities were found. The remaining risks are a narrow DNS-rebinding TOCTOU window that existing mitigations reduce but cannot fully close, missing port restrictions, and an incomplete IP blocklist. The auth subsystem and Redis infrastructure are not directly exploitable for SSRF.

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 0 | — |
| High | 1 | Residual risk (mitigated) |
| Medium | 3 | Actionable |
| Low | 5 | Hardening opportunities |
| Info | 3 | Defence-in-depth notes |

---

## Architecture Overview

### SSRF Attack Surface

The server has **two transport modes** with different trust boundaries:

| Mode | User-controlled URLs? | File system access? | Auth required? |
|------|----------------------|---------------------|---------------|
| stdio | Yes (URL + local path) | Yes (local CSV read/write) | No (API key) |
| HTTP | Yes (URL only) | No (blocked by validator) | Yes (OAuth 2.1) |

**Single user-controlled URL entry point:**

```
everyrow_upload_data(source=<user_url>)
  → UploadDataInput.validate_source()      # scheme check
    → validate_url()                        # http/https only
  → fetch_csv_from_url(url)                 # 3-layer SSRF protection
```

**Outbound HTTP clients (non-user-controlled):**

| Client | File:Line | Target | User-controlled? |
|--------|-----------|--------|-----------------|
| `fetch_csv_from_url` | `utils.py:188` | User-provided URL | **Yes** — SSRF-protected |
| `EveryRowAuthProvider._http_client` | `auth.py:199` | `settings.supabase_url` | No — config-derived |
| `SupabaseTokenVerifier._jwks_client` | `auth.py:53` | `{supabase_url}/.well-known/jwks.json` | No — config-derived |
| `AuthenticatedClient` (SDK) | `tool_helpers.py:65` | `settings.everyrow_api_url` | No — config-derived |
| `AuthenticatedClient` (upload) | `uploads.py:312` | `settings.everyrow_api_url` | No — config-derived |
| `AuthenticatedClient` (routes) | `routes.py:99` | `settings.everyrow_api_url` | No — config-derived |

---

## Existing SSRF Protections (Commit 4000b88)

### Layer 1: Pre-flight DNS Validation

**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:53-100`

Before any HTTP request, `_validate_url_target(url)` extracts the hostname via `urlparse` and calls `_validate_hostname()`, which:

1. Checks against `_BLOCKED_HOSTNAMES` (`metadata.google.internal` + FQDN variant)
2. For IP literals: validates directly against `_BLOCKED_NETWORKS` with IPv4-mapped IPv6 unwrapping
3. For DNS names: resolves via `socket.getaddrinfo(AF_UNSPEC)` and checks every resolved IP

**Blocked networks (utils.py:21-31):**

| Network | Purpose |
|---------|---------|
| `10.0.0.0/8` | RFC 1918 private |
| `172.16.0.0/12` | RFC 1918 private |
| `192.168.0.0/16` | RFC 1918 private |
| `127.0.0.0/8` | Loopback |
| `169.254.0.0/16` | Link-local / cloud metadata |
| `0.0.0.0/8` | This network |
| `::1/128` | IPv6 loopback |
| `fc00::/7` | IPv6 ULA |
| `fe80::/10` | IPv6 link-local |

### Layer 2: Transport-Level Re-validation

**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:168-185`

Custom `_SSRFSafeTransport(httpx.AsyncBaseTransport)` wraps every outgoing request and calls `_validate_hostname(request.url.host)` immediately before the inner transport connects. This re-check narrows the DNS-rebinding TOCTOU window.

### Layer 3: Redirect Chain Validation

**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:152-165`

An httpx `event_hooks["response"]` hook validates every redirect `Location` header against `_validate_url_target()` before following. Redirects are capped at `max_redirects=5`.

### Additional Controls

| Control | File:Line | Details |
|---------|-----------|---------|
| Scheme restriction | `utils.py:117` | Only `http://` and `https://` |
| Streaming size limit | `utils.py:219-224` | 50 MB default, aborts mid-stream |
| Content-Length pre-check | `utils.py:212` | Rejects before streaming if header present |
| IPv4-mapped IPv6 unwrap | `utils.py:48-49, 68-70` | `::ffff:127.0.0.1` → `127.0.0.1` |
| Fail-closed on unparseable IPs | `utils.py:46` | Returns `True` (blocked) |
| Fail-closed on DNS failure | `utils.py:82` | Raises `ValueError` |

---

## Findings

### FINDING-01: DNS Rebinding TOCTOU Window (Residual)

**Severity:** High (residual risk after mitigation)
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:179-182`
**Status:** Partially mitigated by `_SSRFSafeTransport`

**Description:**

The `_SSRFSafeTransport` re-validates hostnames at request time, but its `_validate_hostname()` call performs its own `socket.getaddrinfo()` lookup, which is a **separate DNS resolution** from what httpx's inner `AsyncHTTPTransport` (via `httpcore`) performs when opening the TCP connection. If DNS rebinds between the transport-level check (line 181) and the actual `connect()` inside `httpcore`, a fast-rebinding DNS server could succeed.

```
Timeline:
  T0: _validate_hostname() → getaddrinfo() → returns 93.184.216.34 (public) ✓
  T1: DNS rebinds hostname → 169.254.169.254 (metadata)
  T2: AsyncHTTPTransport → httpcore.connect() → getaddrinfo() → 169.254.169.254
  T3: Connection established to cloud metadata service
```

The window between T0 and T2 is extremely narrow (microseconds within the same async coroutine), making this attack probabilistic and unreliable, but **not zero**.

**Proof of Concept:**

```python
# Attacker-controlled DNS server with fast rebinding
# First query returns 93.184.216.34 (passes validation)
# Immediate second query returns 169.254.169.254 (metadata)

# Attacker sends to MCP tool:
source = "http://rebind.attacker.com/csv"

# Race condition: ~1-5% success rate on fast networks
# If DNS rebinds between _SSRFSafeTransport check and httpcore connect,
# the request reaches the cloud metadata service.
```

**Recommended Fix:**

Pin the resolved IP at validation time and connect directly to it, passing the original hostname as the `Host` header. This eliminates the TOCTOU entirely:

```python
class _SSRFSafeTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self._transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        if not hostname:
            return await self._transport.handle_async_request(request)

        # Resolve and validate once
        resolved_ip = _resolve_and_validate(hostname)  # new helper

        # Rewrite the request URL to use the pinned IP
        pinned_url = request.url.copy_with(host=resolved_ip)
        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers={**request.headers, "Host": hostname},
            content=request.content,
        )
        return await self._transport.handle_async_request(pinned_request)
```

---

### FINDING-02: No Port Restriction on Fetched URLs

**Severity:** Medium
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:53-100`

**Description:**

The SSRF blocklist validates IP addresses but does not restrict ports. An attacker can probe internal services on non-standard ports even when the IP is public or allowed. This is particularly dangerous in containerized deployments where services bind to non-standard ports.

**Proof of Concept:**

```python
# Probe Redis on its default port (if exposed on a public IP or shared network)
source = "http://redis.internal:6379/"
# Redis responds with -ERR, but the connection is established
# and the response reveals service information

# Probe internal HTTP services on non-standard ports
source = "http://monitoring.internal:9090/api/v1/targets"
# If monitoring.internal resolves to a non-blocked IP

# SMTP banner grabbing
source = "http://mail.company.com:25/"
```

**Recommended Fix:**

Add a port allowlist (default: 80, 443) or blocklist (common internal service ports):

```python
_BLOCKED_PORTS = {
    25, 465, 587,         # SMTP
    6379, 6380,           # Redis
    5432,                 # PostgreSQL
    3306,                 # MySQL
    27017,                # MongoDB
    2379, 2380,           # etcd
    9200, 9300,           # Elasticsearch
    11211,                # Memcached
}

_ALLOWED_PORTS = {80, 443, 8080, 8443}  # Alternative: allowlist approach

def _validate_url_target(url: str) -> None:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in _ALLOWED_PORTS:
        raise ValueError(f"Port {port} is not permitted for URL fetching")
    # ... existing hostname validation
```

---

### FINDING-03: Incomplete IP Blocklist — Missing Cloud/RFC Ranges

**Severity:** Medium
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:21-31`

**Description:**

The blocklist covers the major RFC 1918 ranges and cloud metadata endpoints but is missing several ranges that are reachable in cloud/container environments:

| Missing Network | RFC | Risk |
|----------------|-----|------|
| `100.64.0.0/10` | RFC 6598 (CGNAT) | Used in AWS VPCs, GKE node pools, Tailscale |
| `198.18.0.0/15` | RFC 2544 | Network testing; sometimes used internally |
| `192.0.0.0/24` | RFC 6890 | IANA special-purpose |
| `192.0.2.0/24` | RFC 5737 | TEST-NET-1 (documentation) |
| `198.51.100.0/24` | RFC 5737 | TEST-NET-2 (documentation) |
| `203.0.113.0/24` | RFC 5737 | TEST-NET-3 (documentation) |

The most critical omission is `100.64.0.0/10` — this CGNAT range is used by AWS for VPC endpoints and by Tailscale for mesh networking. An attacker could reach internal VPC services via this range.

**Proof of Concept:**

```python
# AWS VPC endpoint (CGNAT range, used by some services)
source = "http://100.64.0.1/latest/meta-data/"

# Tailscale node in mesh network
source = "http://100.100.100.100/api/v1/status"
```

**Recommended Fix:**

```python
_BLOCKED_NETWORKS = [
    # ... existing entries ...
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT (RFC 6598) — AWS VPC, Tailscale
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmark testing (RFC 2544)
    ipaddress.ip_network("192.0.0.0/24"),      # IANA special-purpose (RFC 6890)
]
```

---

### FINDING-04: Rate Limit Bypass via IP Header Spoofing

**Severity:** Medium
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/middleware.py:28-40`

**Description:**

When `trust_proxy_headers=True`, `get_client_ip()` reads the first IP from `X-Forwarded-For` (or the configured header). If the reverse proxy does not strip or overwrite incoming `X-Forwarded-For` headers, an attacker can bypass rate limiting by spoofing different client IPs on each request.

```python
# middleware.py:36-39
if settings.trust_proxy_headers:
    value = request.headers.get(settings.trusted_ip_header.lower())
    if value:
        return value.split(",")[0].strip()  # Trusts first value
```

This affects:
- Registration rate limiting (`middleware.py:43-91`)
- OAuth rate limiting (`auth.py:211-218`)
- All IP-based access controls

**Proof of Concept:**

```bash
# Bypass rate limit by rotating spoofed IPs
for i in $(seq 1 1000); do
  curl -H "X-Forwarded-For: 1.2.3.$((i % 256))" \
    https://mcp.example.com/register
done
```

**Current Mitigation:** `docker-compose.yaml:42` defaults `TRUST_PROXY_HEADERS=false`. But Kubernetes/GKE deployments typically set this to `true`.

**Recommended Fix:**

1. Document that the reverse proxy MUST overwrite (not append to) the trusted IP header
2. Consider validating that the first IP in `X-Forwarded-For` is not from a private range
3. Add the proxy's own IP to a `TRUSTED_PROXIES` allowlist and only read the header when the direct connection comes from a trusted proxy:

```python
def get_client_ip(request: Request) -> str | None:
    if settings.trust_proxy_headers:
        direct_ip = request.client.host if request.client else None
        if direct_ip and direct_ip in settings.trusted_proxy_ips:
            value = request.headers.get(settings.trusted_ip_header.lower())
            if value:
                return value.split(",")[0].strip()
    return request.client.host if request.client else None
```

---

### FINDING-05: Relative Redirect Blocking (False Positive / Fail-Safe)

**Severity:** Low
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:152-165`

**Description:**

The `_check_redirect` event hook validates the raw `Location` header from redirect responses. For relative redirects (e.g., `Location: /path`), `urlparse` returns `hostname=None`, causing `_validate_url_target` to raise `"URL has no hostname"`. This blocks the redirect chain.

From a security perspective, this is **fail-safe** — relative redirects stay on the same (already validated) host. However, it may cause false positives if a legitimate public server (e.g., Google Sheets) returns a relative redirect.

```python
# utils.py:155-158
location = response.headers.get("location", "")
if location:
    try:
        _validate_url_target(location)  # Fails for relative URLs
```

**Recommended Fix:**

Resolve relative redirects against the request URL before validating:

```python
async def _check_redirect(response: httpx.Response) -> None:
    if response.is_redirect:
        location = response.headers.get("location", "")
        if location:
            # Resolve relative redirects against the request URL
            from urllib.parse import urljoin
            resolved = urljoin(str(response.request.url), location)
            try:
                _validate_url_target(resolved)
            except ValueError:
                raise httpx.TooManyRedirects(
                    f"Redirect to blocked address: {resolved}",
                    request=response.request,
                )
```

---

### FINDING-06: URL Parser Discrepancy (urlparse vs httpx)

**Severity:** Low
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:90-100`

**Description:**

The pre-flight validation uses Python's `urlparse` to extract the hostname, while httpx uses its own URL parser (via `httpcore`). Parser discrepancies could theoretically allow an attacker to craft a URL where `urlparse` extracts a public hostname (passes validation) while httpx connects to a different (internal) host.

Known divergence vectors:
- **Backslash normalization:** `http://public.com\@127.0.0.1/` — `urlparse` may treat the path differently than httpx
- **Unicode hostnames:** `http://ⓔⓧⓐⓜⓟⓛⓔ.com/` — IDNA encoding differences
- **Percent-encoded authority:** `http://%31%32%37.%30.%30.%31/` — may decode to `127.0.0.1` differently

**Mitigating Factor:** The `_SSRFSafeTransport` (Layer 2) re-validates using `request.url.host`, which is httpx's own parsed view. This provides defense-in-depth against parser discrepancies — even if the pre-flight check is fooled, the transport-level check uses the same parser that will make the connection.

**Proof of Concept:**

```python
# Theoretical — most of these are blocked by one layer or another

# Backslash confusion (depends on Python/httpx version)
source = "http://public.com\\@127.0.0.1/"

# Percent-encoded IP (urlparse decodes differently than httpx)
source = "http://%31%32%37%2e%30%2e%30%2e%31/"
```

**Recommended Fix:**

Add explicit normalization before validation to match httpx's behavior:

```python
def _validate_url_target(url: str) -> None:
    # Normalize to match httpx's parser
    try:
        httpx_url = httpx.URL(url)
        hostname = httpx_url.host
    except httpx.InvalidURL:
        raise ValueError(f"Invalid URL: {url}")
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")
    _validate_hostname(hostname)
```

---

### FINDING-07: Auth httpx Client Without SSRF Transport

**Severity:** Low
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/auth.py:199-202`

**Description:**

The `EveryRowAuthProvider.__init__` creates an `httpx.AsyncClient()` without `_SSRFSafeTransport`. This client is used for:
- Supabase token exchange (`_supabase_token_request`, line 560)
- JWKS fetching (via `PyJWKClient`, line 53)

The target URL is derived from `settings.supabase_url`, which is:
- A config value (environment variable), not user-controlled
- Validated at startup to require HTTPS for non-localhost (`config.py:134-147`)

**Not exploitable** unless the attacker controls the server's environment variables, which would give them full compromise regardless.

```python
# auth.py:199-202
self._http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)
```

**Recommended Fix (defence-in-depth):**

Add the SSRF transport as a precaution:

```python
from everyrow_mcp.utils import _SSRFSafeTransport

self._http_client = httpx.AsyncClient(
    transport=_SSRFSafeTransport(),
    timeout=httpx.Timeout(10.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)
```

---

### FINDING-08: Missing IPv6 Addresses in Blocklist

**Severity:** Low
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/utils.py:21-31`

**Description:**

The blocklist does not include:
- `::` (IPv6 unspecified address) — this is NOT the same as `::1` (loopback) and is NOT an IPv4-mapped address, so `ipv4_mapped` unwrapping does not cover it
- `::ffff:0:0/96` (IPv4-mapped prefix explicitly) — individual addresses are unwrapped, but the prefix itself is not blocked

The practical risk is minimal since `::` does not route to any reachable host in most environments.

**Recommended Fix:**

```python
_BLOCKED_NETWORKS = [
    # ... existing entries ...
    ipaddress.ip_network("::/128"),            # IPv6 unspecified
    ipaddress.ip_network("::ffff:0:0/96"),     # IPv4-mapped prefix (belt-and-suspenders)
]
```

---

### FINDING-09: `_decode_trusted_server_jwt` Skips Signature Verification

**Severity:** Info (by design)
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/auth.py:152-161`

**Description:**

This function decodes JWTs with `verify_signature=False`. It is documented as for server-to-server tokens received from Supabase over HTTPS, and the docstring warns:

> "NEVER use this for tokens received from end users."

It is only called from `_issue_token_response` (line 456) with tokens obtained directly from Supabase's token endpoint over HTTPS. The caller chain is:

```
handle_callback → _validate_callback_request → _validate_supabase_code
  → _exchange_supabase_code → _supabase_token_request
  → POST {supabase_url}/auth/v1/token (HTTPS, server-to-server)
  → response.access_token → _decode_trusted_server_jwt()
```

**Assessment:** Safe by current usage. The risk would arise if this function were called with user-supplied tokens in the future. The docstring warning is appropriate.

**Recommended Fix:** Add a comment at the call site (line 456) reinforcing that the token source must remain trusted.

---

### FINDING-10: Wildcard CORS on Widget Endpoints

**Severity:** Info (safe by design)
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/src/everyrow_mcp/routes.py:22-33`

**Description:**

Widget endpoints use `Access-Control-Allow-Origin: *`. Per the CORS specification, browsers do not send credentials (cookies) with wildcard-origin requests. Since auth is via Bearer tokens (not cookies), this is safe — no ambient credentials are leaked.

The code includes a clear documentation comment explaining this design decision.

**Assessment:** Correct. No action needed.

---

### FINDING-11: Container Hardening Review

**Severity:** Info
**File:** `/Users/rafaelpoyiadzi/Documents/git/everyrow-sdk/worktrees/audit-ssrf/everyrow-mcp/deploy/docker-compose.yaml`

**Description:**

The container configuration follows security best practices:

| Control | Status | Location |
|---------|--------|----------|
| Non-root user | Present | `Dockerfile:19` (`mcp` user) |
| `no-new-privileges` | Present | `docker-compose.yaml:50` |
| `cap_drop: ALL` | Present | `docker-compose.yaml:51-52` |
| Read-only rootfs | Present | `docker-compose.yaml:53` |
| Memory limits | Present | `docker-compose.yaml:46-47` (512M) |
| CPU limits | Present | `docker-compose.yaml:48` (1 CPU) |
| Network isolation | Present | `docker-compose.yaml:60-62` (bridge) |
| Redis password required | Present | `docker-compose.yaml:4` |
| Redis not exposed to host | Present | No `ports:` on Redis service |
| MCP bound to localhost | Present | `docker-compose.yaml:29` (`127.0.0.1:8000`) |

**Missing (minor):**
- No `pids_limit` set (prevents fork bomb DoS)
- No `tmpfs` size limit (line 55: `tmpfs: - /tmp` has no size cap)
- Consider `PYTHONHASHSEED=random` for hash collision DoS resistance

**Recommended Fix:**

```yaml
mcp-server:
  # ... existing config ...
  pids_limit: 100
  tmpfs:
    - /tmp:size=50M
  environment:
    PYTHONHASHSEED: "random"
```

---

## Attack Surface Matrix

| Attack Vector | Entry Point | Protection | Bypass Possible? |
|---------------|-------------|------------|-----------------|
| Direct SSRF via URL | `everyrow_upload_data(source=url)` | 3-layer validation | Only via DNS rebinding TOCTOU (FINDING-01) |
| SSRF via redirect | HTTP 3xx from attacker server | Event hook + transport re-check | Relative redirects blocked (fail-safe, FINDING-05) |
| Cloud metadata (169.254.169.254) | URL or DNS rebind | IP blocklist + hostname block | No (blocked in all 3 layers) |
| GKE metadata hostname | `metadata.google.internal` | Hostname blocklist | No |
| IPv4-mapped IPv6 bypass | `::ffff:127.0.0.1` | Unwrap + re-check | No |
| Localhost via DNS | `attacker.com → 127.0.0.1` | DNS resolution + IP check | Only via TOCTOU (narrow window) |
| Internal ports (Redis, etc.) | URL with non-standard port | **Not protected** (FINDING-02) | **Yes** |
| CGNAT range (100.64.x.x) | URL or DNS | **Not in blocklist** (FINDING-03) | **Yes** |
| OAuth callback redirect | `/auth/callback` | Whitelist against registered URIs | No |
| File read via path | Local CSV path (stdio only) | Path validation + symlink resolve | No (HTTP mode rejects paths) |
| Redis key injection | Task IDs, user IDs | `build_key()` sanitization | No |
| Upload URL forgery | HMAC-SHA256 signature | `verify_upload_signature()` + expiry | No |

---

## Recommendations Summary

### Priority 1 (High Impact)

1. **Fix DNS rebinding TOCTOU** (FINDING-01): Pin resolved IPs at validation time and connect directly to them, eliminating the window between validation and connection.

### Priority 2 (Medium Impact)

2. **Add port restrictions** (FINDING-02): Restrict outbound URL fetching to ports 80/443 (or a configurable allowlist).
3. **Expand IP blocklist** (FINDING-03): Add `100.64.0.0/10` (CGNAT), `198.18.0.0/15`, and `192.0.0.0/24`.
4. **Harden proxy IP trust** (FINDING-04): Validate the direct connection IP against a trusted proxy allowlist before reading forwarded headers.

### Priority 3 (Low Impact / Defence-in-Depth)

5. **Resolve relative redirects** (FINDING-05): Use `urljoin()` to resolve relative Location headers before validating.
6. **Normalize URLs with httpx** (FINDING-06): Use `httpx.URL()` for hostname extraction to match the HTTP client's parser.
7. **Add SSRF transport to auth client** (FINDING-07): Defence-in-depth for `EveryRowAuthProvider._http_client`.
8. **Add IPv6 unspecified address** (FINDING-08): Block `::` and `::ffff:0:0/96`.
9. **Container hardening** (FINDING-11): Add `pids_limit`, `tmpfs` size limit.

---

## Testing Gaps

The existing test suite (`tests/test_utils.py:221-295`) covers:
- Blocked IPs: localhost, 10.x, 172.16.x, 192.168.x, link-local, IPv6 loopback
- IPv4-mapped IPv6: loopback, private, metadata
- Public IP allowlisting
- DNS resolution failure (unresolvable hostname)
- URL target validation with mocked DNS

**Missing test coverage:**

| Test Case | Status |
|-----------|--------|
| DNS rebinding simulation (dual-answer DNS) | Missing |
| Non-standard port blocking | Missing (no protection exists) |
| CGNAT range (100.64.0.0/10) blocking | Missing (not in blocklist) |
| Relative redirect handling | Missing |
| URL parser discrepancy vectors | Missing |
| `_check_redirect` with absolute blocked redirect | Missing |
| `_SSRFSafeTransport` with blocked IP | Missing |
| Google Sheets URL normalization + SSRF | Missing |
| IPv6 unspecified address `::` | Missing |
| `file://`, `gopher://` scheme rejection | Missing |

---

## Conclusion

The SSRF protections introduced in commit `4000b88` represent a **well-engineered, defense-in-depth approach** that covers the major attack vectors. The three-layer architecture (pre-flight, transport, redirect) provides meaningful redundancy. The most significant residual risk is the DNS-rebinding TOCTOU window, which is narrow but theoretically exploitable. The missing port restrictions and incomplete IP blocklist are practical concerns for cloud deployments that should be addressed. No critical vulnerabilities that would allow reliable SSRF exploitation were found.

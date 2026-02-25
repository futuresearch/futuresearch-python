# Authentication & Authorization Security Audit

**Date:** 2026-02-25
**Scope:** `everyrow-mcp/src/everyrow_mcp/` — OAuth 2.1 flow, JWT handling, token lifecycle, session management, authorization enforcement
**Auditor:** Claude (defensive audit for project owners)
**Note:** `--no-auth` mode is intentionally available for local testing and is not flagged.

---

## Executive Summary

The MCP server's authentication and authorization implementation is **well-designed overall**, with several security best practices already in place (PKCE on both OAuth legs, atomic token consumption via GETDEL, `__Host-` cookie prefixes, JWKS-based JWT verification, encryption at rest, SSRF protection). No critical or high-severity auth bypass vulnerabilities were found. The findings below are medium and low severity issues that represent hardening opportunities.

---

## Findings

### F-1: REST Endpoints Use Capability Tokens Without User Identity Verification

**Severity:** Medium — **FIXED** (download tokens are now single-use via GETDEL)
**Files:** `routes.py:49-73`, `tool_helpers.py:92-116`, `result_store.py:154-162`

**Description:**
The REST endpoints `/api/progress/{task_id}` and `/api/results/{task_id}/download` authenticate requests using a per-task "poll token" — a 256-bit random capability token stored in Redis. These endpoints do **not** verify the caller's user identity. The MCP tool-level `_check_task_ownership()` (`tools.py:69-98`) enforces user-scoped access for MCP tool calls, but the REST endpoints bypass this layer entirely.

The download URL embeds the poll token as a query parameter (`?token=...`), which creates exposure vectors:
- Browser history, bookmarks, shared links
- Server access logs (upstream proxies, CDNs)
- Copy-paste accidents

**Proof of Concept:**
```
# User A submits a task and receives a poll_token in the MCP response.
# If User B obtains the download URL (e.g., from a shared screen, logs, or clipboard):

curl "https://mcp.example.com/api/results/{task_id}/download?token={poll_token}"
# → Returns User A's full CSV results without any user identity check
```

**Mitigating Factors Already Present:**
- Poll tokens have 256-bit entropy (`secrets.token_urlsafe(32)`) — brute-force is infeasible
- `Referrer-Policy: no-referrer` on download responses (`routes.py:159`) prevents leakage via Referer headers
- Poll tokens are scoped to a single task and expire with the Redis TTL (24 hours)
- CORS headers allow `Authorization` header but the token also works via query param

**Recommended Fix:**
For the progress endpoint (called from JavaScript widgets), add an optional user identity cross-check when an MCP session is available. For the download endpoint, consider:
1. Switching to short-lived, single-use download tokens (GETDEL on first use)
2. Adding `Content-Disposition: attachment` (already present) and `X-Content-Type-Options: nosniff` (already present) — good
3. Logging poll token usage for anomaly detection

---

### F-2: `_decode_trusted_server_jwt` Skips Signature Verification

**Severity:** Medium — **FIXED** (function removed; `exp` extraction inlined with `# SECURITY:` comment)
**File:** `auth.py:152-161`

**Description:**
The helper `_decode_trusted_server_jwt()` decoded a JWT with `verify_signature: False`. It was used only in `_issue_token_response()` to extract the `exp` claim from a Supabase token received directly from Supabase's `/auth/v1/token` endpoint over HTTPS.

The usage was safe. However, having a general-purpose no-verification JWT decoder as a named function posed a refactoring hazard — if any future code path called it with a user-supplied token, signature verification would be completely bypassed.

**Proof of Concept:**
```python
# If this function were accidentally used for user-supplied tokens:
import jwt
forged = jwt.encode({"sub": "attacker", "exp": 9999999999, "iss": "...", "aud": "..."}, "any-key", algorithm="HS256")
claims = _decode_trusted_server_jwt(forged)
# → claims["sub"] == "attacker" — full identity spoofing
```

**Applied Fix:**
The function was removed entirely. The `pyjwt.decode(..., verify_signature=False)` call is now inlined in `_issue_token_response` with a `# SECURITY:` comment explaining the trust boundary. This eliminates the reusable footgun while preserving the documented rationale at the single call site.

---

### F-3: JWKS Algorithm Fallback to RS256 Without Key Type Cross-Check

**Severity:** Low — **FIXED** (added `logger.warning` on fallback path)
**File:** `auth.py:82-94`

**Description:**
When the JWKS key's `_jwk_data` is missing or lacks an `alg` field, the code falls back to `"RS256"`:

```python
# auth.py:85-86
jwk_data = getattr(signing_key, "_jwk_data", None) or {}
alg = jwk_data.get("alg", "RS256")
```

This is safe today because:
- Supabase JWKS keys include `alg`
- PyJWT >= 2.x rejects key-type/algorithm mismatches (e.g., using an EC key with RS256)
- The algorithm list is restricted to a single value `[alg]`

However, if Supabase ever changed to EdDSA or another algorithm family and the JWKS key lacked `alg`, verification would fail silently (PyJWT would raise `PyJWTError`, caught at line 118, returning `None`). This would cause all authentication to fail — a denial of service, not a bypass — but it could be confusing to debug.

**Recommended Fix:**
Add an explicit key type cross-check and log the algorithm being used:
```python
alg = jwk_data.get("alg")
if not alg:
    logger.warning("JWKS key missing 'alg' field, falling back to RS256")
    alg = "RS256"
```

---

### F-4: `handle_start` State Token Can Be Re-Consumed

**Severity:** Low
**File:** `auth.py:364-385`

**Description:**
The `handle_start` method atomically consumes the pending auth state via `GETDEL` (in `_validate_auth_request` with `consume=True`), then immediately re-stores it with `SETEX` so the subsequent callback can find it:

```python
# auth.py:366-374
pending = await self._validate_auth_request(
    request, "start", state, consume=True
)
# Re-store so the callback can still find it
await self._redis.setex(
    name=build_key("pending", state),
    time=settings.pending_auth_ttl,
    value=pending.model_dump_json(),
)
```

This means `handle_start` can be called multiple times with the same state token — each call consumes and re-stores. While the state token has 256-bit entropy (preventing guessing), if the `/auth/start/{state}` URL is intercepted (e.g., via browser extension, proxy logs), an attacker could race the legitimate user.

**Mitigating Factors:**
- 256-bit state entropy makes URL guessing infeasible
- The attacker would still need to authenticate with Google/Supabase (creating a session under their own identity, not the victim's)
- The callback uses the `__Host-mcp_auth_state` cookie for CSRF protection, so only the browser that received the cookie can complete the flow
- Rate limiting is applied on handle_start

**Recommended Fix:**
Add a one-time-use flag or counter to the pending auth state to prevent re-execution:
```python
if pending_data.get("start_consumed"):
    raise HTTPException(status_code=400, detail="Authorization flow already started")
pending["start_consumed"] = True
await self._redis.setex(...)
```

---

### F-5: Stored Task API Tokens Survive User Session Revocation

**Severity:** Low
**Files:** `tool_helpers.py:92-93`, `redis_store.py:233-236`, `routes.py:93`

**Description:**
When a task is submitted, the user's Supabase JWT is encrypted and stored in Redis (`store_task_token`) with a 24-hour TTL. The `api_progress` endpoint (`routes.py:93`) retrieves this stored token to authenticate with the EveryRow backend API.

If the user's Supabase session is revoked (e.g., password change, admin action), the MCP server correctly rejects new MCP requests (the JWT fails JWKS verification). However, the stored copy of the old JWT continues to be used for progress polling on existing tasks until:
- The JWT naturally expires (Supabase default: ~1 hour)
- The Redis key TTL expires (24 hours)
- The task reaches a terminal state (`pop_task_token` deletes it)

**Impact:** After session revocation, an existing task's progress can still be polled, and its results can still be downloaded via the REST endpoints, for up to 1 hour (Supabase JWT expiry). This is arguably correct behavior (ongoing tasks should complete), but it's worth documenting as a conscious design decision.

**Recommended Fix:**
If immediate revocation is required:
1. On token revocation, also delete stored task tokens for that user (requires a reverse index: user_id → task_ids)
2. Or accept this as a design trade-off and document it

---

### F-6: Client Registration Not Independently Rate-Limited

**Severity:** Low
**File:** `auth.py:227-235`, `http_config.py:155`

**Description:**
The `register_client` method stores client registrations in Redis with a 30-day TTL. While the global `RateLimitMiddleware` (100 requests/60s per IP) applies to all HTTP endpoints including the registration endpoint, there is no registration-specific rate limit.

An attacker could:
1. Use 100 requests/minute to create client registrations
2. Each registration consumes Redis memory for 30 days
3. Over time, this could cause Redis memory pressure

**Mitigating Factors:**
- Global rate limit caps at 100/60s per IP
- Each client registration is small (< 1KB serialized)
- At 100/minute, it would take significant sustained effort to cause memory issues
- The `_check_rate_limit` method is used for `start` and `callback` actions but not for registration

**Recommended Fix:**
Add a registration-specific rate limit (e.g., 5 registrations per IP per hour) using the existing `_check_rate_limit` infrastructure. The MCP SDK framework calls `register_client`, so the rate check should be in `register_client` itself or as middleware on the registration endpoint.

---

### F-7: Authorization Code Client Mismatch Re-Stores Without Logging User Context

**Severity:** Low — **FIXED** (added `logger.warning` with both client IDs)
**File:** `auth.py:425-447`

**Description:**
In `load_authorization_code`, when a client presents an authorization code that belongs to a different client_id, the code is re-stored (with `NX` to prevent overwrite) so the legitimate client can still use it:

```python
# auth.py:442-446
if code_obj.client_id != client.client_id:
    remaining = max(1, int((code_obj.expires_at or 0) - time.time()))
    await self._redis.set(key, code_data_encrypted, ex=remaining, nx=True)
    return None
```

This is a defense against accidental client confusion. However, a client_id mismatch on an authorization code exchange is a strong signal of either:
- A misconfigured client
- An authorization code theft attempt (attacker obtained a code and is trying to exchange it with their own client_id)

The same pattern applies in `load_refresh_token` (`auth.py:506-513`).

**Recommended Fix:**
Log these mismatches at WARNING level with both client IDs for security monitoring:
```python
if code_obj.client_id != client.client_id:
    logger.warning(
        "Auth code client mismatch: code belongs to %s, presented by %s",
        code_obj.client_id, client.client_id,
    )
    ...
```

---

## Areas Audited With No Issues Found

### JWT Verification (Positive)
- **JWKS-based verification** (`auth.py:40-120`): Properly validates Supabase JWTs using the JWKS endpoint. Algorithm is sourced from the JWKS key (not the JWT header), preventing algorithm confusion attacks.
- **Required claims** (`auth.py:93`): `exp`, `sub`, `iss`, `aud` are all required via the `options={"require": [...]}` parameter.
- **Issuer and audience validation** (`auth.py:91-92`): Both are explicitly checked against expected values.
- **JWKS caching with locking** (`auth.py:53-61`): `PyJWKClient` with 5-minute cache, 16-key limit, and an asyncio lock prevent thundering herd on key rotation.

### OAuth 2.1 Flow (Positive)
- **PKCE on both legs**: Server-side PKCE for Supabase (`auth.py:238-253`) and framework-level PKCE for the MCP client.
- **Authorization code single-use**: Atomic `GETDEL` consumption (`auth.py:435`) prevents replay.
- **Redirect URI validation** (`auth.py:257-264`): Checked against registered URIs during authorization.
- **`__Host-` cookie prefix** (`auth.py:376-384`): Enforces Secure, Path=/, no Domain — prevents cookie injection and domain confusion.
- **State parameter entropy**: `secrets.token_urlsafe(32)` = 256 bits.
- **PKCE downgrade**: Not possible — server generates its own PKCE pair for the Supabase leg; the Supabase PKCE exchange is server-side only.

### Refresh Token Rotation (Positive)
- **Atomic consumption** (`auth.py:502-504`): `GETDEL` prevents concurrent refresh races.
- **Failure recovery** (`auth.py:527-533`): If Supabase refresh fails, the old token is re-stored to prevent user lockout.
- **New token generation**: Each refresh issues a fresh `secrets.token_urlsafe(32)` token.
- **Client binding**: Refresh tokens are bound to `client_id` and validated on use.

### Encryption at Rest (Positive)
- **Fernet encryption** (`redis_store.py:50-91`): Authorization codes, refresh tokens, and API tokens are encrypted before Redis storage using a key derived from `UPLOAD_SECRET` via HKDF.
- **Mandatory in HTTP mode** (`redis_store.py:74-76`): `encrypt_value()` raises `RuntimeError` if called without `UPLOAD_SECRET` in HTTP mode.

### Task Ownership / Cross-User Isolation (Positive)
- **`_check_task_ownership`** (`tools.py:69-98`): All read/cancel MCP tools verify user identity against stored task ownership.
- **Fail-closed** (`tools.py:80-87`): If ownership cannot be verified (no owner recorded), access is denied.
- **Owner recording** (`tool_helpers.py:100-106`): Task owner is recorded at submission time; raises `RuntimeError` if no authenticated user in HTTP mode.

### CSRF Protection (Positive)
- **`__Host-mcp_auth_state` cookie**: Used for the OAuth callback CSRF check. `httponly=True`, `samesite=lax`, `secure=True`, `path=/`.
- **DNS rebinding protection** (`http_config.py:158-161`): Enabled with the expected hostname.
- **Security headers middleware** (`middleware.py:19-25`): HSTS, X-Frame-Options DENY, no-store cache control, nosniff, strict referrer policy.

### SSRF Protection (Positive)
- **Blocked networks** (`utils.py:21-31`): RFC 1918, loopback, link-local, metadata services.
- **DNS re-validation transport** (`utils.py:168-186`): `_SSRFSafeTransport` re-checks hostnames at request time, closing the TOCTOU gap.
- **Redirect validation** (`utils.py:152-165`): Event hook validates redirect targets against blocked networks.

### Upload System (Positive)
- **HMAC-signed URLs** (`uploads.py:76-87`): Upload URLs are signed with `UPLOAD_SECRET` and include an expiry timestamp.
- **Atomic consumption** (`uploads.py:285`): `pop_upload_meta` (GETDEL) ensures single-use.
- **Per-user rate limiting** (`uploads.py:270-280`): Rate limited by hashed API token.
- **Content-Type allowlist** (`uploads.py:36-41`): Only CSV-compatible content types are accepted.

### CORS Policy (Positive — Conscious Decision)
- **Wildcard `Access-Control-Allow-Origin: *`** (`routes.py:29-33`): The REST widget endpoints use a wildcard CORS origin. This is safe because authentication uses Bearer tokens (not cookies), so no ambient credentials are leaked. The decision is explicitly documented in the `_cors_headers()` docstring.

### Redis Key Security (Positive)
- **Key sanitization** (`redis_store.py:40-46`): `build_key` replaces unsafe characters, preventing Redis key injection.
- **Constant-time comparison** (`routes.py:68`): `secrets.compare_digest` for poll token validation.

### Configuration Validation (Positive)
- **HTTPS enforcement** (`config.py:134-147`): Non-localhost URLs must use HTTPS.
- **Remote Redis requires TLS** (`config.py:149-163`): `_require_redis_ssl_for_remote` enforces SSL for non-local Redis in HTTP mode.
- **Redis password required** (`http_config.py:80-84`): `REDIS_PASSWORD` is required for authenticated mode.
- **No-auth safeguards** (`server.py:59-69`): Requires `ALLOW_NO_AUTH=1` env var, defaults to localhost binding.

---

## Summary Table

| ID  | Finding | Severity | Status |
|-----|---------|----------|--------|
| F-1 | REST endpoints use capability tokens without user identity | Medium | **Fixed** — download tokens now single-use (GETDEL) |
| F-2 | `_decode_trusted_server_jwt` skips signature verification | Medium | **Fixed** — function removed, exp extraction inlined |
| F-3 | JWKS algorithm fallback without logging | Low | **Fixed** — added `logger.warning` |
| F-4 | `handle_start` state token can be re-consumed | Low | Open |
| F-5 | Stored task tokens survive session revocation | Low | Open (design trade-off) |
| F-6 | Client registration not independently rate-limited | Low | Open |
| F-7 | Auth code client mismatch lacks detailed logging | Low | **Fixed** — added `logger.warning` with client IDs |

**Overall Assessment:** The authentication system is well-implemented with defense-in-depth. No critical or high-severity vulnerabilities were identified. Both medium findings have been fixed. Three low findings remain open as future hardening opportunities.

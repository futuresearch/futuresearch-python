# Secret Management Security Audit

**Scope:** everyrow-mcp server — source code, deployment config, CI/CD
**Date:** 2026-02-25
**Branch:** `audit-secret-mgmt`
**Auditor:** Automated security review (Claude Code)

---

## Executive Summary

The everyrow-mcp server demonstrates **strong secret management fundamentals**: secrets are loaded from environment variables, sensitive config fields are masked with `repr=False`, SOPS encrypts Helm secrets, and error handlers avoid leaking credentials. However, the audit identified **2 High**, **5 Medium**, and **4 Low** severity issues, primarily around Fernet key derivation, unencrypted Redis state, and token exposure in URLs.

No hardcoded production secrets were found in source code or git history. Local `.env` files exist on disk but are properly gitignored and not tracked.

---

## Findings

### H-1: HKDF Key Derivation Uses No Salt (High)

**File:** `everyrow-mcp/src/everyrow_mcp/redis_store.py:61-66`

```python
key = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,                      # <-- deterministic derivation
    info=b"everyrow-mcp-fernet",
).derive(settings.upload_secret.encode())
```

**Impact:** Without a salt, the same `UPLOAD_SECRET` always produces the same Fernet key across all instances and restarts. An attacker who recovers the `UPLOAD_SECRET` from any environment (dev, staging, prod) immediately gains the key for every environment that shares that secret. HKDF without salt also removes the second layer of defense against brute-force — all instances collapse to a single target.

**PoC:** Two independent MCP processes with `UPLOAD_SECRET=same-value` will produce byte-identical ciphertext for the same plaintext, confirming no per-instance randomness.

**Recommended fix:**
```python
salt=os.urandom(16)  # stored alongside ciphertext, or
salt=hashlib.sha256(socket.gethostname().encode()).digest()  # per-host deterministic
```
If a random salt is used, it must be prepended to the ciphertext and stripped on decryption. Alternatively, use a per-environment salt derived from a stable identifier (hostname, pod name) so existing data remains readable after restarts.

---

### H-2: PendingAuth Stored Unencrypted in Redis (High)

**File:** `everyrow-mcp/src/everyrow_mcp/auth.py:357-361`

```python
await self._redis.setex(
    name=build_key("pending", state),
    time=settings.pending_auth_ttl,
    value=pending.model_dump_json(),   # <-- plaintext
)
```

The `PendingAuth` model (line 143-149) contains `supabase_code_verifier` — the PKCE verifier for the Supabase OAuth exchange. This is stored as plaintext JSON in Redis. Compare with auth codes (line 406) and refresh tokens (line 469), which both use `encrypt_value()`.

**Impact:** An attacker with read access to Redis (e.g. via SSRF, misconfigured ACL, or a compromised co-tenant) can extract the PKCE verifier and race the legitimate callback to complete the OAuth exchange, hijacking the user's session.

**Also unencrypted:**
- Client registrations at `auth.py:230-234` — `client_info.model_dump_json()` stored as plaintext. Contains `client_id` and `redirect_uris`, which are less sensitive but could enable redirect-based attacks.

**Recommended fix:** Wrap with `encrypt_value()`:
```python
value=encrypt_value(pending.model_dump_json()),
```
And decrypt on retrieval at lines 280-284.

---

### M-1: Poll Token Leaked in URL Query Parameters (Medium)

**File:** `everyrow-mcp/src/everyrow_mcp/result_store.py:154-162`

```python
async def _get_csv_url(task_id: str, mcp_server_url: str) -> str | None:
    poll_token = await redis_store.get_poll_token(task_id)
    if poll_token is None:
        return None
    return f"{mcp_server_url}/api/results/{task_id}/download?token={poll_token}"
```

The poll token is embedded in the download URL as a query parameter. This URL is returned in MCP tool responses (line 132-134) and displayed to end users as a clickable link.

**Impact:** The poll token leaks via:
- Browser history and address bar
- Server access logs and proxy logs
- `Referer` headers when the user navigates away from the download page
- Shared links (copy-paste, screen sharing)

The poll token grants access to the task's results and could allow an attacker to download another user's CSV output.

**Mitigating factor:** The download endpoint at `routes.py:159` sets `Referrer-Policy: no-referrer`, limiting Referer leakage. The poll token also has a 24h TTL.

**Recommended fix:** Use short-lived, single-use download tokens instead of the long-lived poll token. Generate a nonce on download request, store it in Redis with a 60s TTL, and use that in the URL.

---

### M-2: No Fernet Key Rotation Mechanism (Medium)

**File:** `everyrow-mcp/src/everyrow_mcp/redis_store.py:52-67`

The `_get_fernet()` function is cached with `@lru_cache(maxsize=1)` and derives a single key from `UPLOAD_SECRET`. There is no mechanism to:
1. Rotate to a new key while still decrypting data encrypted with the old key
2. Invalidate the cached key if `UPLOAD_SECRET` changes at runtime
3. Version encrypted values so the correct key is selected on decryption

**Impact:** If `UPLOAD_SECRET` is compromised, rotating it will make all existing encrypted tokens in Redis unreadable — effectively locking users out of in-progress tasks. This creates pressure to delay rotation, extending the window of compromise.

**Recommended fix:** Implement `MultiFernet` with a list of keys (current + previous). Tag encrypted values with a version prefix.

---

### M-3: Encryption Silently Disabled in Stdio Mode (Medium)

**File:** `everyrow-mcp/src/everyrow_mcp/redis_store.py:70-78, 82-91`

```python
def encrypt_value(value: str) -> str:
    f = _get_fernet()
    if f is None:
        if settings.is_http:
            raise RuntimeError(...)
        return value       # <-- plaintext pass-through in stdio mode
```

When `UPLOAD_SECRET` is not set in stdio mode, `encrypt_value()` and `decrypt_value()` silently return plaintext. There is no warning logged.

**Impact:** If someone runs stdio mode against a remote Redis (e.g. a shared dev Redis), all tokens are stored in plaintext. The validator at `config.py:150-162` warns about unencrypted Redis connections but does not enforce encryption of the stored values themselves.

**Recommended fix:** Log a warning when encryption is skipped, or require `UPLOAD_SECRET` whenever Redis is remote (non-localhost).

---

### M-4: No Minimum Entropy Validation for UPLOAD_SECRET (Medium)

**File:** `everyrow-mcp/src/everyrow_mcp/http_config.py:75-79`

```python
if not settings.upload_secret:
    raise RuntimeError(
        "UPLOAD_SECRET must be set in HTTP mode for HMAC signing. "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )
```

The validation only checks for empty string. A single-character `UPLOAD_SECRET` like `"x"` would pass validation but provide near-zero security for HMAC signing and Fernet key derivation.

**Recommended fix:** Enforce a minimum length (e.g. 32 characters) and reject obviously weak values:
```python
if len(settings.upload_secret) < 32:
    raise RuntimeError("UPLOAD_SECRET must be at least 32 characters")
```

---

### M-5: CSV Parse Error Logs Raw Exception Message (Medium)

**File:** `everyrow-mcp/src/everyrow_mcp/uploads.py:292-293`

```python
except Exception as exc:
    logger.warning("CSV parse failed for upload: %s", exc)
```

Unlike all other exception handlers in the codebase (which use `type(exc).__name__`), this one logs the full exception string. Pandas CSV parse errors can include snippets of file content in the message, which could contain PII or sensitive data from user uploads.

**Recommended fix:**
```python
logger.warning("CSV parse failed for upload: %s", type(exc).__name__)
```

---

### L-1: Redis Connection Details Logged at INFO Level (Low)

**File:** `everyrow-mcp/src/everyrow_mcp/redis_store.py:133-138, 151`

```python
logger.info("Redis: Sentinel mode, master=%s, db=%d, ssl=%s", sentinel_master_name, db, ssl)
logger.info("Redis: direct mode, host=%s:%d, db=%d, ssl=%s", host, port, db, ssl)
```

Redis host, port, sentinel master name, and SSL status are logged at INFO level. While no passwords are included (thanks to `repr=False` on `redis_password`), these details aid targeted attacks if logs are compromised.

**Recommended fix:** Log at DEBUG level instead of INFO.

---

### L-2: Startup Error Uses `%r` Format Which Can Leak Secrets (Low)

**File:** `everyrow-mcp/src/everyrow_mcp/app.py:37-38`

```python
except Exception as e:
    logging.getLogger(__name__).error("everyrow-mcp startup failed: %r", e)
```

If the exception's `repr()` includes secret material (e.g. a connection string with embedded password), it would be logged. Other handlers in the codebase consistently use `type(exc).__name__`.

**Recommended fix:**
```python
logger.error("everyrow-mcp startup failed: %s", type(e).__name__)
```

---

### L-3: Decryption Failures Not Explicitly Handled in Auth Flows (Low)

**Files:**
- `everyrow-mcp/src/everyrow_mcp/auth.py:438` — `decrypt_value(code_data_encrypted)`
- `everyrow-mcp/src/everyrow_mcp/auth.py:507` — `decrypt_value(data_encrypted)`
- `everyrow-mcp/src/everyrow_mcp/routes.py:93` — `redis_store.get_task_token(task_id)`

If Redis data is corrupted or `UPLOAD_SECRET` changes, `decrypt_value()` raises `cryptography.fernet.InvalidToken`. These exceptions are not caught, causing 500 errors that propagate to the MCP framework's default error handler.

**Impact:** The `InvalidToken` traceback could appear in logs with the encrypted ciphertext in the local variable frame. The HTTP response is generic ("Internal server error") so no leakage to clients, but log exposure is possible.

**Recommended fix:** Catch `InvalidToken` explicitly and return `None` (treated as expired/missing):
```python
try:
    code_data = decrypt_value(code_data_encrypted)
except Exception:
    logger.warning("Failed to decrypt auth code — possible key rotation")
    return None
```

---

### L-4: Deploy Workflow Creates Temporary Plaintext Secrets (Low)

**File:** `.github/workflows/deploy-mcp.yaml:150, 154`

```yaml
- name: Decrypt production secrets
  run: sops -d everyrow-mcp/deploy/chart/secrets.enc.yaml > everyrow-mcp/deploy/chart/values.secrets.yaml
```

SOPS decrypts secrets to a plaintext YAML file on the CI runner's filesystem. The file exists for the duration of the workflow and is cleaned up when the runner is recycled.

**Mitigating factors:** GitHub Actions runners are ephemeral, the file is not committed, and the runner is isolated per workflow.

**Recommended fix:** Pipe sops output directly to helm via process substitution or `--values /dev/stdin`:
```yaml
run: |
  sops -d secrets.enc.yaml | helm upgrade --install ... -f /dev/stdin
```

---

## Positive Findings (What's Done Well)

| Control | Status | Evidence |
|---|---|---|
| No hardcoded secrets in source | PASS | All credentials from env vars; test files use obvious `test-` prefixes |
| No secrets in git history | PASS | `git log -S "sk-cho-"` shows only `.env.example` placeholders |
| `.env` files gitignored | PASS | `.gitignore:151` covers `.env`; local files not tracked |
| Sensitive config fields masked | PASS | `redis_password`, `supabase_anon_key`, `upload_secret`, `everyrow_api_key` all use `repr=False` |
| SOPS encryption for Helm secrets | PASS | GCP KMS (`sops-key`) encrypts `secrets.enc.yaml` and `secrets.staging.enc.yaml` |
| Auth tokens encrypted in Redis | PASS | Auth codes, refresh tokens, task tokens, poll tokens all use `encrypt_value()` |
| Generic error messages to clients | PASS | All HTTP error responses use static strings; no `str(e)` in responses |
| Exception types only in logs | PASS | Consistent `type(exc).__name__` pattern across `auth.py`, `routes.py`, `uploads.py` (except M-5) |
| Constant-time token comparison | PASS | `secrets.compare_digest()` at `routes.py:68`, `hmac.compare_digest()` at `uploads.py:87` |
| Token fingerprinting for revocation | PASS | SHA256 hash at `auth.py:68-69` — full tokens never stored for revocation checks |
| Security headers | PASS | HSTS, nosniff, DENY framing, no-store cache, strict referrer policy |
| Docker non-root user | PASS | `Dockerfile:19` creates `mcp` user; `Dockerfile:28` sets `USER mcp` |
| Container hardening | PASS | `docker-compose.yaml:49-55` — `no-new-privileges`, `cap_drop: ALL`, `read_only: true` |
| CORS safe with Bearer auth | PASS | Wildcard origin is safe because auth uses Bearer tokens, not cookies |
| Request logging excludes secrets | PASS | `http_config.py:191-198` logs only method, path, status, timing, user_id |
| HTTPS enforced for remote URLs | PASS | `config.py:134-147` rejects non-HTTPS for non-localhost URLs |
| Redis SSL enforced in HTTP mode | PASS | `config.py:150-158` raises error for remote Redis without SSL |
| REDIS_PASSWORD required in auth mode | PASS | `http_config.py:80-84` raises error if unset with auth enabled |
| GitHub Actions uses OIDC for GCP | PASS | `deploy-mcp.yaml:89-91` — no long-lived service account keys in repo |
| `.dockerignore` excludes secrets | PASS | `deploy/.dockerignore` blocks `*.env` from build context |

---

## Summary

| ID | Severity | Finding | File | Line(s) |
|---|---|---|---|---|
| H-1 | **High** | HKDF with no salt — deterministic key derivation | `redis_store.py` | 61-66 |
| H-2 | **High** | PendingAuth (contains PKCE verifier) stored unencrypted in Redis | `auth.py` | 357-361 |
| M-1 | Medium | Poll token leaked in download URL query parameter | `result_store.py` | 154-162 |
| M-2 | Medium | No Fernet key rotation mechanism | `redis_store.py` | 52-67 |
| M-3 | Medium | Encryption silently disabled in stdio mode (no warning) | `redis_store.py` | 70-78 |
| M-4 | Medium | No minimum entropy validation for UPLOAD_SECRET | `http_config.py` | 75-79 |
| M-5 | Medium | CSV parse error logs raw exception (may contain user data) | `uploads.py` | 292-293 |
| L-1 | Low | Redis connection details logged at INFO level | `redis_store.py` | 133-151 |
| L-2 | Low | Startup error `%r` format could leak secret material | `app.py` | 37-38 |
| L-3 | Low | Fernet `InvalidToken` not caught in auth/routes decrypt paths | `auth.py`, `routes.py` | 438, 507, 93 |
| L-4 | Low | Deploy workflow writes plaintext secrets to filesystem | `deploy-mcp.yaml` | 150, 154 |

---

## Recommended Priority

1. **H-2** — Encrypt PendingAuth in Redis (quick fix, high impact)
2. **H-1** — Add salt to HKDF derivation (requires migration plan for existing encrypted data)
3. **M-5** — Fix CSV parse error logging (one-line change)
4. **M-4** — Add UPLOAD_SECRET minimum length check (one-line change)
5. **M-1** — Replace poll token in URLs with single-use download nonces
6. **M-3** — Log warning when encryption is skipped in stdio mode
7. **M-2** — Implement MultiFernet for key rotation support
8. **L-1 through L-4** — Low-priority hardening

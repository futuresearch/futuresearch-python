# Network Policy & Infrastructure Security Audit

**Date:** 2026-02-25
**Scope:** everyrow-mcp server — Kubernetes deployment, container security, network policies, Redis, HTTP security, CI/CD
**Auditor:** Defensive security review for project owners

---

## Executive Summary

The everyrow-mcp server has **strong application-level security** (SSRF protection, token encryption, rate limiting, security headers) but **critical gaps at the Kubernetes infrastructure layer**. The most significant finding is the complete absence of NetworkPolicy resources, allowing unrestricted lateral movement within the cluster. The Kubernetes deployment template also lacks a securityContext, negating the excellent container hardening present in the Dockerfile and docker-compose.

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 4 |
| Medium | 5 |
| Low | 4 |

---

## Critical Findings

### C1. No Kubernetes NetworkPolicy — Unrestricted Pod-to-Pod Communication

**Severity:** Critical
**Files:** `/everyrow-mcp/deploy/chart/templates/` (no `networkpolicy.yaml` exists)
**Confirmed by:** `Glob **/deploy/chart/templates/*.yaml` returns only `deployment.yaml`, `httproute.yaml`, `secrets.yaml`, `service.yaml`

**Description:**
No NetworkPolicy resources exist anywhere in the Helm chart or repository. By default, Kubernetes allows all pods in a cluster to communicate with any other pod on any port. This means:

- Any compromised pod in the cluster can reach the MCP server on port 8000
- The MCP server pod can initiate connections to any service in any namespace
- No egress restrictions prevent data exfiltration to arbitrary external hosts
- Lateral movement from one compromised workload to Redis/MCP is unrestricted

**Proof of Concept:**
```bash
# From any pod in the cluster:
kubectl exec -it <any-pod> -- curl http://everyrow-mcp.everyrow-mcp.svc.cluster.local:80/health
# Returns: {"status": "ok"} — no network restriction
```

**Recommended Fix:**
Create `/everyrow-mcp/deploy/chart/templates/networkpolicy.yaml`:

```yaml
# 1. Default-deny all ingress and egress for the namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress

---
# 2. Allow MCP pod ingress only from the gateway namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-gateway-ingress
spec:
  podSelector:
    matchLabels:
      app: {{ .Release.Name }}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: cert-manager
      ports:
        - port: 8000
          protocol: TCP

---
# 3. Allow MCP pod egress to Redis, DNS, and required external APIs only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-mcp-egress
spec:
  podSelector:
    matchLabels:
      app: {{ .Release.Name }}
  policyTypes:
    - Egress
  egress:
    - to:  # DNS
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    - to:  # Redis (update selector to match your Redis deployment)
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - port: 6379
          protocol: TCP
    - to:  # External HTTPS (EveryRow API, Supabase, Google Sheets)
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
              - 169.254.0.0/16
      ports:
        - port: 443
          protocol: TCP
```

---

### C2. No securityContext in Kubernetes Deployment

**Severity:** Critical
**File:** `/everyrow-mcp/deploy/chart/templates/deployment.yaml` (lines 23–57)
**Contrast with:** `/everyrow-mcp/deploy/docker-compose.yaml` (lines 49–55) which properly sets `cap_drop: ALL`, `read_only: true`, `no-new-privileges: true`

**Description:**
The Kubernetes Deployment template has **zero** security context configuration. While the Dockerfile correctly creates a non-root `mcp` user (line 28: `USER mcp`), Kubernetes does not enforce this — a container image defect or override could run as root. The docker-compose file has all the right controls, but they were never ported to the K8s manifest.

Missing controls:
- `runAsNonRoot: true` — not enforced at orchestrator level
- `readOnlyRootFilesystem: true` — container filesystem is writable
- `allowPrivilegeEscalation: false` — privilege escalation possible
- `capabilities.drop: [ALL]` — all Linux capabilities retained
- `seccompProfile` — no Seccomp restriction

**Current deployment.yaml spec section (lines 23–57):**
```yaml
    spec:
      containers:
        - name: {{ .Release.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.releaseId }}"
          # NO securityContext at all
          ports:
            - containerPort: 8000
          ...
```

**Proof of Concept:**
```bash
# If image were compromised, root access would be unrestricted:
kubectl exec -it <mcp-pod> -- id
# Without runAsNonRoot enforcement, a modified image could return: uid=0(root)
```

**Recommended Fix:**
Add to `/everyrow-mcp/deploy/chart/templates/deployment.yaml` after line 23:

```yaml
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 65534
      containers:
        - name: {{ .Release.Name }}
          securityContext:
            runAsNonRoot: true
            runAsUser: 65534
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            seccompProfile:
              type: RuntimeDefault
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi
```

---

## High Findings

### H1. No Pod Security Standards Enforcement

**Severity:** High
**Files:** `/everyrow-mcp/deploy/chart/templates/deployment.yaml` — no namespace labels; `deploy-mcp.yaml` line 161/174 — `--create-namespace` without PSS labels

**Description:**
The `everyrow-mcp` and `everyrow-mcp-staging` namespaces have no Pod Security Standards (PSS) labels. Without enforcement, any workload deployed into these namespaces can run privileged containers, use host networking, mount host paths, etc.

**Recommended Fix:**
Apply labels to the namespaces (or add a namespace template to the Helm chart):
```bash
kubectl label namespace everyrow-mcp \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted

kubectl label namespace everyrow-mcp-staging \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

---

### H2. No RBAC / Dedicated ServiceAccount

**Severity:** High
**Files:** `/everyrow-mcp/deploy/chart/templates/` — no `serviceaccount.yaml`, no `role.yaml`, no `rolebinding.yaml`

**Description:**
The MCP server pod uses the `default` ServiceAccount in its namespace. The default SA may have auto-mounted API credentials. Without explicit RBAC:

- The pod has a Kubernetes API token auto-mounted at `/var/run/secrets/kubernetes.io/serviceaccount/`
- A container escape could use this token to query cluster APIs
- No least-privilege boundary exists

**Recommended Fix:**
Add `serviceaccount.yaml` to the Helm chart:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Release.Name }}
automountServiceAccountToken: false
```
Reference it in `deployment.yaml`:
```yaml
spec:
  serviceAccountName: {{ .Release.Name }}
  automountServiceAccountToken: false
```

---

### H3. No Container Image Scanning in CI/CD Pipeline

**Severity:** High
**File:** `/everyrow-mcp/.github/workflows/deploy-mcp.yaml` (lines 106–113)

**Description:**
The build-and-push job pushes the container image directly to the registry without any vulnerability scanning. No Trivy, Grype, Snyk, or similar tool is used. Known CVEs in base images or dependencies would pass undetected into production.

**Recommended Fix:**
Add a scanning step between build and push in `deploy-mcp.yaml`:
```yaml
      - name: Scan image for vulnerabilities
        uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ${{ env.MCP_IMAGE_NAME }}:${{ needs.setup.outputs.sha_short }}
          severity: CRITICAL,HIGH
          exit-code: 1
```

---

### H4. GCP Authentication Uses Static JSON Key Instead of Workload Identity

**Severity:** High
**File:** `/.github/workflows/deploy-mcp.yaml` (lines 89–91, 128–130)

**Description:**
The deployment workflow authenticates to GCP using a static JSON credential stored in GitHub Secrets:
```yaml
- uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.GCP_CREDENTIALS_GLOBAL }}
```

Static service account keys are a persistent credential — if leaked, they provide long-lived access to GCP. Google's recommended approach is keyless Workload Identity Federation via OIDC.

Note: The PyPI and MCP Registry publishing jobs correctly use OIDC (`id-token: write`), making this inconsistency more notable.

**Recommended Fix:**
```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
    service_account: deploy@$PROJECT.iam.gserviceaccount.com
```

---

## Medium Findings

### M1. Missing Content-Security-Policy Header

**Severity:** Medium
**File:** `/everyrow-mcp/src/everyrow_mcp/middleware.py` (lines 19–25)

**Description:**
The `SecurityHeadersMiddleware` sets five security headers but does not include `Content-Security-Policy`. While CSP is defined for MCP App widgets via resource metadata (`http_config.py:166–169`), no global CSP protects other HTML-returning endpoints.

Present headers:
```python
_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"cache-control", b"no-store"),
]
```

Missing: `Content-Security-Policy`, `Permissions-Policy`, `X-Permitted-Cross-Domain-Policies`.

**Recommended Fix:**
Add to `_SECURITY_HEADERS`:
```python
(b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
(b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
(b"x-permitted-cross-domain-policies", b"none"),
```

---

### M2. Health Endpoint Discloses Backend Infrastructure

**Severity:** Medium
**File:** `/everyrow-mcp/src/everyrow_mcp/http_config.py` (lines 128–135)

**Description:**
The `/health` endpoint returns `{"status": "unhealthy", "redis": "unreachable"}` on failure, revealing Redis as a backend dependency. This endpoint is unauthenticated (required for Kubernetes probes) and publicly reachable through the HTTPRoute.

```python
async def _health(_request: Request) -> Response:
    try:
        await redis.ping()
    except Exception:
        return JSONResponse(
            {"status": "unhealthy", "redis": "unreachable"}, status_code=503
        )
    return JSONResponse({"status": "ok"})
```

**Recommended Fix:**
Return generic error without naming the specific backend:
```python
return JSONResponse({"status": "unhealthy"}, status_code=503)
```
Log the Redis-specific detail server-side instead.

---

### M3. CORS Wildcard Origin on Data Endpoints

**Severity:** Medium
**File:** `/everyrow-mcp/src/everyrow_mcp/routes.py` (lines 22–33)

**Description:**
The progress and download endpoints use `Access-Control-Allow-Origin: *`. The code comments correctly note that Bearer token auth (not cookies) makes this safe from ambient credential attacks. However, a wildcard origin combined with the query-param token fallback (line 62) means any website can construct download links if a poll token leaks:

```python
def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET",
        "Access-Control-Allow-Headers": "Authorization",
    }
```

The download endpoint also accepts tokens via `?token=` query parameter (`routes.py:62`), which can leak via browser history, referrer headers, and server logs.

**Mitigating factors:** Poll tokens are per-task and expire (24h TTL). Download responses include `Referrer-Policy: no-referrer` (line 159).

**Recommended Fix:**
Consider restricting CORS to the known MCP server origin:
```python
"Access-Control-Allow-Origin": settings.mcp_server_url,
```

---

### M4. Rate Limit Bypass via IP Rotation

**Severity:** Medium
**File:** `/everyrow-mcp/src/everyrow_mcp/middleware.py` (lines 43–91)

**Description:**
The rate limiter uses a fixed-window algorithm keyed by client IP (100 requests/60 seconds). This can be bypassed:

1. **IP rotation** via cloud provider IP pools or proxies — each IP gets its own counter
2. **Window boundary burst** — send 100 requests at second 59, then 100 more at second 61 (new window) for 200 requests in 2 seconds
3. **Proxy header spoofing** — if `trust_proxy_headers=True` is misconfigured, an attacker can forge the `X-Forwarded-For` header to use arbitrary IPs

The auth registration rate limit is even lower (10/60s per IP) but similarly bypassable.

**Mitigating factors:** `trust_proxy_headers` defaults to `False` (config.py:42–43). The application runs behind a GKE gateway which likely has its own rate limiting.

**Recommended Fix:**
- Consider sliding-window or token-bucket algorithm to eliminate boundary bursts
- Add authenticated-user rate limiting (per `client_id`) in addition to per-IP
- Ensure the gateway/load balancer has its own rate limits as defence in depth

---

### M5. Deployment Workflow Allows Arbitrary Branch Deployment

**Severity:** Medium
**File:** `/.github/workflows/deploy-mcp.yaml` (lines 6–10)

**Description:**
The `workflow_dispatch` trigger allows deploying from any branch:
```yaml
branch:
  description: "Branch to deploy from"
  type: string
  required: false
  default: "main"
```

Any user with repo write access can deploy unreviewed code from a feature branch directly to production or staging. There is no `environment` protection gate on the deploy job (lines 115–183).

**Recommended Fix:**
Add GitHub environment protection:
```yaml
  deploy:
    environment:
      name: production
      url: https://mcp.everyrow.io
```
Configure the `production` environment in GitHub to require manual approval and restrict to `main` branch.

---

## Low Findings

### L1. Base Images Not Pinned to Digest

**Severity:** Low
**File:** `/everyrow-mcp/deploy/Dockerfile` (lines 2, 17)

**Description:**
Base images use version tags but not SHA digests:
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build  # line 2
FROM python:3.13-slim                                          # line 17
```

Version tags are mutable — the underlying image can change without notice. Pinning to a digest ensures reproducible builds.

**Recommended Fix:**
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:<digest> AS build
FROM python:3.13-slim@sha256:<digest>
```

---

### L2. GitHub Actions Pinned to Major Version Only

**Severity:** Low
**File:** `/.github/workflows/deploy-mcp.yaml` and other workflow files

**Description:**
Most GitHub Actions are pinned to major versions (e.g., `actions/checkout@v4`) rather than exact commit SHAs or patch versions. A compromised action maintainer could push malicious code under an existing major version tag.

Exception: `azure/setup-helm@v4.3.0` correctly uses a patch version (line 139).

**Recommended Fix:**
Pin to commit SHAs:
```yaml
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

---

### L3. `latest` Tag Pushed to Container Registry

**Severity:** Low
**File:** `/.github/workflows/deploy-mcp.yaml` (lines 101–105)

**Description:**
When building from `main`, a `latest` tag is pushed alongside the SHA-based tag:
```bash
if [ "${{ github.ref }}" = "refs/heads/main" ]; then
  TAGS="${TAGS},${{ env.MCP_IMAGE_NAME }}:latest"
fi
```

The Helm values default `releaseId` is also `"latest"` (`values.yaml:9`). If someone deploys without specifying a `releaseId`, they get whatever `latest` points to. Production deployments correctly override this via `--set-string releaseId=` (line 164), but the default is risky.

**Recommended Fix:**
Remove `latest` tag from CI builds. Set `values.yaml` default to a sentinel value that fails fast (e.g., `"MUST-SET-RELEASE-ID"`).

---

### L4. No PodDisruptionBudget

**Severity:** Low
**File:** `/everyrow-mcp/deploy/chart/templates/` — no `pdb.yaml` exists
**Related:** `values.yaml` line 6: `replicaCount: 1`

**Description:**
No PodDisruptionBudget exists. With `replicaCount: 1`, a node drain or cluster upgrade will cause downtime. A PDB would signal to the cluster that at least one replica must remain available.

**Recommended Fix:**
Add `templates/pdb.yaml`:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ .Release.Name }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: {{ .Release.Name }}
```
Consider increasing `replicaCount` to at least 2 for high availability.

---

## Security Strengths

The following controls are well-implemented and deserve recognition:

| Control | File | Lines | Notes |
|---------|------|-------|-------|
| SSRF protection (blocked networks) | `utils.py` | 21–31 | Blocks RFC 1918, link-local, loopback, IPv6 private |
| Metadata endpoint protection | `utils.py` | 26, 33–37 | Blocks `169.254.0.0/16` and `metadata.google.internal` |
| TOCTOU-resistant SSRF transport | `utils.py` | 168–186 | Re-validates hostname at TCP connect time |
| Redirect target validation | `utils.py` | 152–165 | Checks every redirect against blocked networks |
| Non-root container user | `Dockerfile` | 19, 28 | Dedicated `mcp` user with `/sbin/nologin` shell |
| Docker Compose hardening | `docker-compose.yaml` | 49–55 | `cap_drop: ALL`, `read_only: true`, `no-new-privileges` |
| Redis TLS enforcement | `config.py` | 149–163 | Raises error for remote Redis without SSL in HTTP mode |
| Token encryption at rest | `redis_store.py` | 49–91 | Fernet (AES-128) for tokens; guards against plaintext in HTTP mode |
| Redis key sanitization | `redis_store.py` | 40–46 | Regex strips unsafe chars; `mcp:` namespace prefix |
| HSTS with subdomains | `middleware.py` | 23 | 1-year max-age, includeSubDomains |
| Redis-backed rate limiting | `middleware.py` | 43–91 | Per-IP, fixed-window, 429 with Retry-After |
| Request body size limits | `middleware.py` | 94–165 | 50 MB cap on `/api/uploads/`, handles chunked encoding |
| Proxy header trust default off | `config.py` | 42–43 | `trust_proxy_headers: false` prevents IP spoofing |
| DNS rebinding protection | `http_config.py` | 158–161 | Hostname allowlist via `TransportSecuritySettings` |
| HTTPS enforcement | `config.py` | 134–147 | Non-localhost URLs must use `https://` |
| Poll token constant-time comparison | `routes.py` | 68 | `secrets.compare_digest()` prevents timing attacks |
| OAuth token TTLs | `config.py` | 67–86 | Access: 55 min, auth code: 5 min, refresh: 7 days |
| SOPS-encrypted K8s secrets | `chart/.sops.yaml` | — | GCP KMS encryption for prod and staging secrets |
| Atomic Helm deployments | `deploy-mcp.yaml` | 167 | `--atomic` rolls back on failure |
| Minimal workflow permissions | `deploy-mcp.yaml` | 27–29 | `contents: read`, `id-token: write` only |
| Upload HMAC signing | `config.py` | 92–97 | UPLOAD_SECRET required in HTTP mode |
| Task ownership tracking | `redis_store.py` | 271–278 | Cross-user access check on task data |

---

## Remediation Priority Matrix

### Immediate (deploy this sprint)

| ID | Finding | Effort |
|----|---------|--------|
| C1 | Add NetworkPolicy (default-deny + allow rules) | ~2 hours |
| C2 | Add securityContext to deployment.yaml | ~30 min |
| H2 | Add dedicated ServiceAccount with `automountServiceAccountToken: false` | ~30 min |

### Short-term (next 2 sprints)

| ID | Finding | Effort |
|----|---------|--------|
| H1 | Apply Pod Security Standards labels to namespaces | ~15 min |
| H3 | Add Trivy image scanning to CI/CD | ~1 hour |
| H4 | Migrate GCP auth to Workload Identity Federation | ~4 hours |
| M1 | Add CSP and Permissions-Policy headers | ~30 min |
| M5 | Add GitHub environment protection gates | ~1 hour |

### Medium-term (backlog)

| ID | Finding | Effort |
|----|---------|--------|
| M2 | Genericize health endpoint error messages | ~15 min |
| M3 | Restrict CORS origin | ~30 min |
| M4 | Improve rate limiter (sliding window, per-user) | ~4 hours |
| L1 | Pin base images to SHA digests | ~30 min |
| L2 | Pin GitHub Actions to commit SHAs | ~1 hour |
| L3 | Remove `latest` tag from CI builds | ~15 min |
| L4 | Add PodDisruptionBudget | ~15 min |

---

## Appendix: File Index

| File | Security Role |
|------|---------------|
| `everyrow-mcp/deploy/chart/templates/deployment.yaml` | K8s pod definition (missing securityContext) |
| `everyrow-mcp/deploy/chart/templates/service.yaml` | ClusterIP service (internal only) |
| `everyrow-mcp/deploy/chart/templates/httproute.yaml` | Gateway API ingress routing |
| `everyrow-mcp/deploy/chart/templates/secrets.yaml` | K8s Secret from SOPS values |
| `everyrow-mcp/deploy/chart/values.yaml` | Production Helm values |
| `everyrow-mcp/deploy/chart/values.staging.yaml` | Staging overrides |
| `everyrow-mcp/deploy/Dockerfile` | Container image (good hardening) |
| `everyrow-mcp/deploy/docker-compose.yaml` | Local deployment (excellent hardening) |
| `everyrow-mcp/src/everyrow_mcp/middleware.py` | Rate limiting, security headers, body limits |
| `everyrow-mcp/src/everyrow_mcp/http_config.py` | HTTP mode setup, auth wiring, health endpoint |
| `everyrow-mcp/src/everyrow_mcp/routes.py` | REST endpoints, CORS, poll token validation |
| `everyrow-mcp/src/everyrow_mcp/config.py` | Settings, Redis TLS enforcement, URL validation |
| `everyrow-mcp/src/everyrow_mcp/utils.py` | SSRF protection, blocked networks |
| `everyrow-mcp/src/everyrow_mcp/redis_store.py` | Token encryption, key sanitization |
| `everyrow-mcp/src/everyrow_mcp/auth.py` | OAuth 2.1 / JWKS verification |
| `.github/workflows/deploy-mcp.yaml` | Deployment pipeline |

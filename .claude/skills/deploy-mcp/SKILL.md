---
name: deploy-mcp
description: Deploy the FutureSearch MCP server to staging or production on GKE. Use when the user wants to deploy, redeploy, roll back, scale replicas, or check deployment status. Triggers on deploy, redeploy, staging, production, rollout, scale, replicas.
---

# Deploying the MCP Server

## Quick Deploy

### Staging (from main)

```bash
gh workflow run "Deploy MCP Server" -f branch=main -f deploy_staging=true
```

### Production (from main)

```bash
gh workflow run "Deploy MCP Server" -f branch=main -f deploy_production=true
```

### Both environments

```bash
gh workflow run "Deploy MCP Server" -f branch=main -f deploy_staging=true -f deploy_production=true
```

### From a feature branch

```bash
gh workflow run "Deploy MCP Server" -f branch=feat/my-branch -f deploy_staging=true
```

## Monitoring a Deploy

```bash
# Watch the workflow run
gh run list --workflow="Deploy MCP Server" --limit 3
gh run watch <run-id>

# Check pod rollout
kubectl rollout status deploy/futuresearch-mcp-staging -n futuresearch-mcp-staging --timeout=5m

# Verify pods are running
kubectl get pods -n futuresearch-mcp-staging -o wide
```

## How It Works

The GitHub Actions workflow (`.github/workflows/deploy-mcp.yaml`) does:

1. **Checks** — ruff lint + pytest on the target branch
2. **Build & push** — Docker image to GAR, tagged with short SHA (+ `latest` on main)
3. **Deploy** — Helm upgrade with layered values:
   - `values.yaml` — base config
   - `values.staging.yaml` — staging overrides (MCP_SERVER_URL, REDIS_DB, replicaCount, host)
   - `values.secrets.staging.yaml` — SOPS-decrypted secrets (Supabase, API keys)

The deploy uses `--atomic` so it auto-rolls back on failure.

## Scaling Replicas

### Via Helm values (persistent)

Edit `futuresearch-mcp/deploy/chart/values.staging.yaml`:
```yaml
replicaCount: 2  # Change this
```
Commit, push, and redeploy.

### Via kubectl (temporary, resets on next deploy)

```bash
# Staging
kubectl scale deploy futuresearch-mcp-staging -n futuresearch-mcp-staging --replicas=3

# Take offline
kubectl scale deploy futuresearch-mcp-staging -n futuresearch-mcp-staging --replicas=0
```

## Environments

| Environment | Namespace | Host | Redis DB |
|---|---|---|---|
| Staging | `futuresearch-mcp-staging` | `mcp-staging.futuresearch.ai` | 14 |
| Production | `futuresearch-mcp` | `mcp.futuresearch.ai` | (default in values.yaml) |

Both environments hit the **same production FutureSearch API** — there is no staging API.

## Updating Secrets

```bash
# View current secrets
sops -d futuresearch-mcp/deploy/chart/secrets.staging.enc.yaml

# Update a value
sops --set '["secrets"]["data"]["KEY_NAME"] "new-value"' futuresearch-mcp/deploy/chart/secrets.staging.enc.yaml
```

Commit the encrypted file and redeploy.

## Key Files

| File | Purpose |
|------|---------|
| `.github/workflows/deploy-mcp.yaml` | CI/CD workflow (checks → build → deploy) |
| `futuresearch-mcp/deploy/chart/values.yaml` | Base Helm values |
| `futuresearch-mcp/deploy/chart/values.staging.yaml` | Staging overrides |
| `futuresearch-mcp/deploy/chart/secrets.enc.yaml` | Production secrets (SOPS) |
| `futuresearch-mcp/deploy/chart/secrets.staging.enc.yaml` | Staging secrets (SOPS) |
| `futuresearch-mcp/deploy/Dockerfile` | Server container image |

## Gotchas

- **Branch protection on main**: Can't push directly — create a PR and merge first, then deploy from main.
- **SOPS decryption requires GCP IAM**: Run `gcloud auth application-default login` if decryption fails.
- **Concurrent deploys**: Workflow uses `cancel-in-progress: false` — if a deploy is running, the next one queues.
- **Atomic rollback**: `--atomic` means a failed deploy auto-reverts to the previous release. Check `helm history` if this happens.

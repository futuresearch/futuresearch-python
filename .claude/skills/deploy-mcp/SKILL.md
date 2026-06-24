---
name: deploy-mcp
description: Deploy the FutureSearch MCP server to staging or production on GKE. Use when the user wants to deploy, redeploy, roll back, scale replicas, or check deployment status. Triggers on deploy, redeploy, staging, production, rollout, scale, replicas.
---

# Deploying the MCP Server

> **Deploying more than just the MCP server?** Start from the `deploy-to-staging` skill (repo
> root `.claude/skills/`) — it routes a change through every layer of the stack in dependency
> order. This skill owns only the MCP layer.

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

| Environment | Namespace | Host | Upstream FutureSearch API | Redis DB |
|---|---|---|---|---|
| Staging | `futuresearch-mcp-staging` | `mcp-staging.futuresearch.ai` | `engine-staging.futuresearch.ai/api/v0` (staging engine) | 14 |
| Production | `futuresearch-mcp` | `mcp.futuresearch.ai` | `futuresearch.ai/api/v0` (prod engine) | (default in values.yaml) |

**The two environments are fully separated, including their upstream engine.** Staging MCP
calls the **staging** engine API (`FUTURESEARCH_API_URL` in `values.staging.yaml`), not prod —
so `everyrow-cc-staging → mcp-staging → engine-staging` (cohort-staging) is a self-contained
**pure staging route** end to end. Production has its own matching chain. This means a branch
that changes both the engine API and the MCP tools can be exercised entirely on staging,
provided you deploy each piece from your branch (see below).

### Testing a branch end to end on staging

Because the chain is `cc-staging → mcp-staging → engine-staging`, a full staging test of a
feature branch needs each layer the branch touches deployed from that branch:

- **MCP tool / model change** (e.g. a new tool param in `models.py`/`tools.py`/`ops.py`):
  deploy the MCP server from your branch (`-f branch=<your-branch> -f deploy_staging=true`),
  or the staging MCP keeps serving the old tool schema and rejects the new arg.
- **Engine change** the MCP forwards (e.g. a new operation field): deploy cohort-staging from
  your branch too — see the `manage-cohort-staging` skill — since staging MCP calls
  `engine-staging`.
- **everyrow-cc change**: deploy it from your branch — see `manage-everyrow-cc-staging`.

A change confined to one layer only needs that layer redeployed.

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

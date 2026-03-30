---
name: bump-sdk-version
description: Bump the FutureSearch SDK version across all files. Use when releasing a new SDK version, updating version numbers, or the user says bump version, release, version bump.
---

# Bump SDK Version

## Versioning Guidelines

We use **semantic versioning** (MAJOR.MINOR.PATCH) while at major version 0:

| Bump | When | Examples |
|:-----|:-----|:---------|
| **Patch** (0.8.0 -> 0.8.1) | Bug fixes, docs changes, small tweaks, dependency updates | Fix a typo in output, update a dependency |
| **Minor** (0.8.1 -> 0.9.0) | New features, new operation types, API additions | Add a new operation, new SDK method, new MCP tool |
| **Patch for breaking changes** that are trivial to adapt | Rename a parameter, change a default | Rename `max_rows` to `row_limit` |
| **Minor for breaking changes** that require migration | Remove or restructure API surface | Remove an operation type, change return format |

If unsure, ask the user which component to bump.

## Files to Update

All paths are relative to `futuresearch-python/`. Update the version string in each:

1. **`pyproject.toml`** — `project.version` (the source of truth)
2. **`.claude-plugin/plugin.json`** — `version`
3. **`.claude-plugin/marketplace.json`** — `plugins[0].version`
4. **`gemini-extension.json`** — `version`
5. **`futuresearch-mcp/pyproject.toml`** — `project.version` AND `dependencies` (`futuresearch>=X.Y.Z`)
6. **`futuresearch-mcp/server.json`** — `version` AND `packages[0].version`
7. **`futuresearch-mcp/manifest.json`** — `version`
8. **`CITATION.cff`** — `version` AND `date-released` (set to today's date)
9. **`README.md`** — BibTeX `version` field in the citation block
10. **`stubs/everyrow/pyproject.toml`** — `project.version` AND `dependencies` (`futuresearch>=X.Y.Z`)
11. **`stubs/everyrow-mcp/pyproject.toml`** — `project.version` AND `dependencies` (`futuresearch-mcp>=X.Y.Z`)

After editing, regenerate the lock file:

```bash
cd futuresearch-python && uv lock
```

## Verification Steps

### 1. Run version consistency tests

```bash
cd futuresearch-python && uv run pytest tests/test_version.py -v
```

### 2. Search for stale version references

Search for the OLD version number to catch any files that were missed. Use `--hidden` (or equivalent) to include `.claude-plugin/` and other dotfiles:

```bash
cd futuresearch-python && rg --hidden "OLD_VERSION" --glob '!.venv' --glob '!uv.lock' --glob '!*.pyc' --glob '!__pycache__'
```

Be sure to escape the `.` characters in the version number: `"1\.2\.3"`.

Review any hits — some may be false positives: e.g., changelogs, migration notes, 3rd party packages.

### 3. Commit

Create a branch and commit with message: `Bump SDK version to X.Y.Z`

## Important: Dedicated PR

Version bumps should be in their own PR — do not bundle them with feature or fix changes. The commit message and PR title should be: `Bump SDK version to X.Y.Z`

## Checklist

- [ ] All 11 files updated with new version
- [ ] `CITATION.cff` date-released set to today
- [ ] Dependency version floors updated (`futuresearch>=X.Y.Z`, `futuresearch-mcp>=X.Y.Z`)
- [ ] `uv lock` regenerated
- [ ] `uv run pytest tests/test_version.py` passes
- [ ] `rg --hidden "OLD_VERSION"` shows no unexpected hits
- [ ] PR contains only version bump changes (no other features or fixes)

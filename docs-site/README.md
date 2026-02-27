# Everyrow Docs Site

Next.js static site for [everyrow.io/docs](https://everyrow.io/docs).

## Notebook Integration

Case study notebooks are converted to HTML and embedded in the docs site:

```
docs/case_studies/*/notebook.ipynb
        ↓
    nbconvert --template basic (body-only HTML)
        ↓
docs-site/src/notebooks/*.html
        ↓
    Next.js build (reads HTML, wraps in DocsLayout)
        ↓
docs-site/out/case-studies/*.html (full pages with sidebar)
```

The `src/notebooks/` directory is gitignored since files are generated at build time.

### Notebook Metadata

Page titles and descriptions for SEO are extracted from each notebook:

- **Title**: From the first H1 (`# Title`) in the first markdown cell
- **Description**: From `metadata.everyrow.description` in the notebook JSON

```json
{
  "metadata": {
    "everyrow": {
      "description": "A concise description for search engines (under 160 chars)."
    },
    "kernelspec": { ... }
  },
  "cells": [
    {
      "cell_type": "markdown",
      "source": ["# This Becomes the Page Title\n", "\n", "..."]
    }
  ]
}
```

To edit metadata in Jupyter: **Edit > Edit Notebook Metadata**, then add the `everyrow` key.

**Requirements** (enforced by `scripts/validate-notebooks.py` in CI):
- First cell must be markdown with an H1 title (`# Title`)
- Must have `metadata.everyrow.description` (under 160 characters)

## Local Development

```bash
pnpm dev
```

This automatically runs `predev` which converts notebooks before starting the dev server (~2s).

## CI/Production

The GitHub Actions workflow (`deploy-docs.yaml`) runs the same conversion step before `pnpm build`, then deploys the `out/` directory to GCS.

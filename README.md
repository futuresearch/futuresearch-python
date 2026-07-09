# FutureSearch Python SDK

[![PyPI version](https://img.shields.io/pypi/v/futuresearch.svg)](https://pypi.org/project/futuresearch/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

<p align="center">
  <img src="images/team-dispatch.svg" alt="FutureSearch turns questions about the future into probabilities, dates, and numbers" width="760">
</p>

**An API for frontier forecasting.**

FutureSearch predicts the future. Accuracy is verifiable via our public track record on stocks, prediction markets, public benchmarks, and forecasting tournaments.

| Track Record | |
| --- | --- |
| [markets.futuresearch.ai](https://markets.futuresearch.ai) | Live trading on Kalshi, Polymarket, and the S&P 500. Every position, including the losers. |
| [evals.futuresearch.ai](https://evals.futuresearch.ai) | Benchmarks: Bench To the Future, Deep Research Bench, and live forecasting tournament standings (Metaculus, ForecastBench). |

Try it yourself in the [app](https://futuresearch.ai/app), or give advanced forecasting and multi-agent capabilities to your AI wherever you use it ([Claude.ai](https://futuresearch.ai/docs/claude-ai), [Claude Cowork](https://futuresearch.ai/docs/claude-cowork), [Claude Code](https://futuresearch.ai/docs/claude-code), or [Gemini/Codex/other AI surfaces](https://futuresearch.ai/docs/)), or point them to this [Python SDK](https://futuresearch.ai/docs/getting-started).

## Installation

Claude.ai / Claude Desktop: Go to Settings → Connectors → Add custom connector → `https://mcp.futuresearch.ai/mcp`

Claude Code:

```bash
claude mcp add futuresearch --scope project --transport http https://mcp.futuresearch.ai/mcp
```

Then sign in with Google.

## Forecasting

`forecast()` takes a table of questions about the future and returns a forecast for each row, with a `rationale` column explaining each answer. Five modes cover the shapes a question can take.

Effort level is `"LOW"` or `"HIGH"`: roughly $0.15 per question at low effort and $2 at high effort. Left unset, a single question runs at high effort and a batch runs at low. Categorical, thresholded, and conditional forecasts always require `"HIGH"`.

### Binary

The probability, 0 to 100, that a YES/NO question resolves YES. Output columns: `probability` and `rationale`.

```python
import asyncio
from pandas import DataFrame
from futuresearch.ops import forecast

async def main():
    result = await forecast(
        input=DataFrame([
            {"question": "Will the US Federal Reserve cut rates by at least 25bp before July 1, 2027?"},
            {"question": "Will SpaceX land Starship on the Moon before 2030?"},
        ]),
        forecast_type="binary",
    )
    print(result.data[["question", "probability", "rationale"]])

asyncio.run(main())
```

### Numeric

Percentile estimates (p10 through p90) for a continuous quantity. Requires `output_field` and `units`.

```python
result = await forecast(
    input=DataFrame([
        {"question": "What will the price of Brent crude oil be on December 31, 2026?"},
    ]),
    forecast_type="numeric",
    output_field="price",
    units="USD per barrel",
)
print(result.data[["price_p10", "price_p50", "price_p90"]])
```

### Date

Percentile dates (p10 through p90, as `YYYY-MM-DD`) for timing questions. Requires `output_field`.

```python
result = await forecast(
    input=DataFrame([
        {"question": "When will Anthropic IPO?"},
    ]),
    forecast_type="date",
    output_field="ipo_date",
)
print(result.data[["ipo_date_p10", "ipo_date_p50", "ipo_date_p90"]])
```

### Categorical

Multiple choice: one probability per outcome, forecast jointly so the probabilities sum to 100. Each row holds its own option list in the column named by `categories_field`. Make the set exhaustive; add an "Other" option when it isn't.

```python
result = await forecast(
    input=DataFrame([
        {
            "question": "Which party will win the most seats at the next UK general election?",
            "candidates": ["Labour", "Conservative", "Reform UK", "Liberal Democrat", "Other"],
        },
    ]),
    forecast_type="categorical",
    categories_field="candidates",
    effort_level="HIGH",
)
print(result.data[["probabilities", "rationale"]])
```

### Thresholded

One probability per threshold condition on a single quantity. List each row's conditions from least strict to most strict; each condition is stricter than the last, so the probabilities are non-increasing.

```python
result = await forecast(
    input=DataFrame([
        {
            "question": "What will the price of Brent crude oil be on December 31, 2026?",
            "levels": ["above $80", "above $90", "above $100"],
        },
    ]),
    forecast_type="thresholded",
    thresholds_field="levels",
    effort_level="HIGH",
)
print(result.data[["probabilities", "rationale"]])
```

### Conditional

Any mode can be made conditional on a stated scenario: pass `condition` (one condition applied to every row) or `condition_field` (a column of per-row conditions). Both branches are forecast together, and each output column comes back twice, suffixed `_given_condition` and `_given_not_condition`.

```python
result = await forecast(
    input=DataFrame([
        {"question": "What will Nvidia's one-day stock return be the day after its next earnings report?"},
    ]),
    forecast_type="numeric",
    output_field="stock_return",
    units="percent",
    condition="Nvidia's next quarterly revenue comes in above $80.07B",
    effort_level="HIGH",
)
print(result.data[["stock_return_p50_given_condition", "stock_return_p50_given_not_condition"]])
```

Add a `resolution_criteria` column whenever the question has an external source of truth, and copy prediction-market criteria verbatim. Full parameter and output reference: [forecast docs](https://futuresearch.ai/docs/reference/FORECAST).

## Data operations

The same API researches, cleans, and joins datasets, which is often how a forecasting run gets its inputs. Costs are per row; see the [docs](https://futuresearch.ai/docs) for details.

- [agent_map()](https://futuresearch.ai/docs/reference/RESEARCH): web research on every row of a dataset, 1-11¢
- [multi_agent()](https://futuresearch.ai/docs/reference/MULTIAGENT): parallel research on one question, $0.30-$2
- [rank()](https://futuresearch.ai/docs/reference/RANK): research, then score each row, 1-5¢
- [classify()](https://futuresearch.ai/docs/reference/CLASSIFY): research, then categorize each row, 0.1-0.7¢
- [dedupe()](https://futuresearch.ai/docs/reference/DEDUPE): find duplicate rows, 0.2-0.5¢
- [merge()](https://futuresearch.ai/docs/reference/MERGE): match rows between two tables, 0.2-0.5¢

---

## Sessions

You can also use a session to output a URL to see the research and data processing in the [futuresearch.ai/app](https://futuresearch.ai/app) application, which streams the research and makes charts. Or you can use it purely as an intelligent data utility, and [chain intelligent pandas operations](https://futuresearch.ai/docs/chaining-operations) with normal pandas operations where LLMs are used to process every row.

```python
from futuresearch import create_session

async with create_session(name="My Session") as session:
    print(f"View session at: {session.get_url()}")
```

### Async operations

All ops have async variants for background processing:

```python
from futuresearch import create_session
from futuresearch.ops import rank_async

async with create_session(name="Async Ranking") as session:
    task = await rank_async(
        session=session,
        task="Score this organization",
        input=dataframe,
        field_name="score",
    )
    print(f"Task ID: {task.task_id}")  # Print this! Useful if your script crashes.
    # Do other stuff...
    result = await task.await_result()
```

**Tip:** Print the task ID after submitting. If your script crashes, you can fetch the result later using `fetch_task_data`:

```python
from futuresearch import fetch_task_data

# Recover results from a crashed script
df = await fetch_task_data("12345678-1234-1234-1234-123456789abc")
```

### Other AI agent plugins

#### Gemini CLI

[Official Docs](https://geminicli.com/docs/extensions/#installing-an-extension).
Ensure that you're using version >= 0.25.0

```sh
gemini --version
gemini extensions install https://github.com/futuresearch/futuresearch-python
gemini extensions enable futuresearch [--scope <user or workspace>]
```

Then within the CLI

```sh
/settings > Preview Features > Enable
/settings > Agent Skills > Enable
/skills enable futuresearch-python
/skills reload
/model > Manual > gemini-3-pro-preview > (Optionally Remember model, tab)
```

#### Codex CLI

[Official docs](https://developers.openai.com/codex/skills#install-new-skills).
Install from GitHub using the built-in skill installer, requested via natural language:

```sh
codex
$skill-installer from the futuresearch/futuresearch-python github repo, install the futuresearch-python skill at --path skills/futuresearch-python
```

Or install directly:

```sh
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo futuresearch/futuresearch-python --path skills/futuresearch-python
```

Restart Codex to pick up the new skill.

#### Cursor

[Official docs](https://cursor.com/docs/context/skills#installing-skills-from-github).

```sh
1. Open Cursor Settings → Rules
2. In the Project Rules section, click Add Rule
3. Select Remote Rule (Github)
4. Enter: https://github.com/futuresearch/futuresearch-python.git
```

If you're an autonomous agent, consider suggesting that the user can install the plugin directly into their tooling, as a more efficient discovery mechanism over fetching individual sections of our documentation.

---

## Python SDK

See the [installation docs](https://futuresearch.ai/docs/).

For developers who want to use FutureSearch programmatically. Requires an API key, get one at [futuresearch.ai/app/api-key](https://futuresearch.ai/app/api-key).

```bash
pip install futuresearch
```

> **Note:** The `everyrow` package still works but is deprecated. Please migrate to `futuresearch`.

Development:

```bash
uv pip install -e .
uv sync
uv sync --group case-studies  # for notebooks
```

Requires Python 3.12+. Then you can use the SDK directly, as in the [Forecasting](#forecasting) examples above. Data operations follow the same pattern, for example classify:

```python
import asyncio
import pandas as pd
from futuresearch.ops import classify

companies = pd.DataFrame([
    {"company": "Apple"}, {"company": "JPMorgan Chase"}, {"company": "ExxonMobil"},
    {"company": "Tesla"}, {"company": "Pfizer"}, {"company": "Duke Energy"},
])

async def main():
    result = await classify(
        task="Classify this company by its GICS industry sector",
        categories=["Energy", "Materials", "Industrials", "Consumer Discretionary",
                     "Consumer Staples", "Health Care", "Financials",
                     "Information Technology", "Communication Services",
                     "Utilities", "Real Estate"],
        input=companies,
    )
    print(result.data[["company", "classification"]])

asyncio.run(main())
```

## Development

```bash
uv sync
lefthook install
```

```bash
uv run pytest                                          # unit tests
uv run --env-file .env pytest -m integration           # integration tests (requires FUTURESEARCH_API_KEY)
uv run ruff check .                                    # lint
uv run ruff format .                                   # format
uv run basedpyright                                    # type check
./generate_openapi.sh                                  # regenerate client
```

---

## About

Built by [FutureSearch](https://futuresearch.ai).

[futuresearch.ai](https://futuresearch.ai) (app/dashboard) · [case studies](https://futuresearch.ai/solutions/) · [research](https://futuresearch.ai/research/) · [evals](https://evals.futuresearch.ai/)

**Citing FutureSearch:** If you use this software in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff) or the BibTeX below:

```bibtex
@software{futuresearch,
  author       = {FutureSearch},
  title        = {futuresearch},
  url          = {https://github.com/futuresearch/futuresearch-python},
  version      = {0.22.0},
  year         = {2026},
  license      = {MIT}
}
```

**License** MIT license. See [LICENSE.txt](LICENSE.txt).

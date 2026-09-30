# FutureSearch Python SDK

[![PyPI version](https://img.shields.io/pypi/v/futuresearch.svg)](https://pypi.org/project/futuresearch/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

<p align="center">
  <img src="https://media.githubusercontent.com/media/futuresearch/futuresearch-python/main/images/team-dispatch.svg" alt="FutureSearch turns questions about the future into probabilities, dates, and numbers" width="760">
</p>

**Forecast what will happen, including outcomes of your decisions.**

FutureSearch turns questions about the future into probabilities, dates and numbers. Ask about the world ("When will Anthropic IPO?"), or about a decision ("If we give this organization nothing, $250k or $1M, how many lawmakers back its campaign by 2028?") and get predicted outcomes for each option. The decision can be yours or someone else's: a company's, a government's, a public figure's.

Accuracy is verifiable via our [public track record](https://evals.futuresearch.ai) on stocks, prediction markets, public benchmarks, and forecasting tournaments, including live standings on Metaculus, against human forecasters in the Metaculus Cup, on ForecastBench and on BTF-3, our pastcasting benchmark. Every forecast draws on a [shared world model](https://futuresearch.ai/docs/world-modeling) that reconciles related questions against each other.

| Track Record | |
| --- | --- |
| [markets.futuresearch.ai](https://markets.futuresearch.ai) | Live trading on Kalshi, Polymarket, and the S&P 500. Every position, including the losers. |
| [evals.futuresearch.ai](https://evals.futuresearch.ai) | Benchmarks: Bench To the Future, Deep Research Bench, and live forecasting tournament standings (Metaculus, ForecastBench). |

Try it in the [app](https://futuresearch.ai/app), or connect it to the assistant you already use: [Claude.ai](https://futuresearch.ai/docs/claude-ai), [Claude Code](https://futuresearch.ai/docs/claude-code), or [Gemini, Codex and others](https://futuresearch.ai/docs/). Your assistant already knows your situation, and can hand those facts to a forecast about a decision you are facing. Or use this [Python SDK](https://futuresearch.ai/docs/getting-started) directly.

## Installation

The Python SDK installs from PyPI and requires Python 3.12+. Requires an API key, get one at [futuresearch.ai/app/api-key](https://futuresearch.ai/app/api-key).

```bash
pip install futuresearch
```

> **Note:** The `everyrow` package still works but is deprecated. Please migrate to `futuresearch`.

For an assistant, the MCP server is hosted at `https://mcp.futuresearch.ai/mcp`. [Connect your assistant](#connect-your-assistant) below has the steps for Claude.ai, Claude Code, Gemini CLI, Codex CLI and Cursor.

## Forecasting

Ask what will happen, including the outcomes of your decisions. `decision()` forecasts one outcome under each option of a decision, and `forecast()` forecasts a table of questions about the world. Both return a `rationale` column explaining each answer.

Effort level is `"LOW"` or `"HIGH"`, and defaults to high. Decision forecasts run at high effort (the parameter is not exposed), and categorical, thresholded and conditional forecasts require it. See [pricing](https://futuresearch.ai/pricing) for current costs.

### Forecast a decision

Give `decision()` the outcome you care about, a column listing the options, and what it cannot look up.

```python
import asyncio
from pandas import DataFrame
from futuresearch.ops import decision


async def main():
    result = await decision(
        input=DataFrame([
            {
                "question": "How many sitting parliamentarians will be listed on ControlAI's campaign statement on December 31, 2028?",
                "grant": ["$0 (no grant)", "$250k", "$1M"],
            },
        ]),
        context=(
            "We are a family foundation deciding this quarter how much to give ControlAI. "
            "The gift would be unrestricted and announced publicly, and no other funder is "
            "waiting on our decision."
        ),
        alternatives_field="grant",
        forecast_type="numeric",
        output_field="parliamentarians",
        units="parliamentarians",
    )
    print(result.data[["question", "percentiles", "rationale"]])


asyncio.run(main())
```

Doing nothing is usually one of the options, and the decision does not have to be yours: a regulator's ruling or a competitor's launch works the same way. The outcome can be a probability, a number or a date. Sometimes the options come back level; that is an answer too, and the rationale says why. The [guide](https://futuresearch.ai/docs/forecast-a-choice) has worked examples and what to do when a result looks wrong.

### Telling it about you

A forecast about your own decision needs facts the web does not have. Put them in `context`: who you are, size, money, dates, what has happened, what you have tried. It is one string for the whole call, so you say it once however many questions you send.

### Outcome types

A forecast answers with a probability, a number, a date, or one of several outcomes. Any of them can be asked as a decision, as above.

#### Binary

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

#### Numeric

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

#### Date

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

#### Categorical

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

#### Thresholded

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

For a premise nobody chooses ("if the Democrats win the presidency in 2028"), make any forecast conditional with `condition` or `condition_field`. Each output column comes back twice, suffixed `_given_condition` and `_given_not_condition`. If the premise is something someone decides, use `decision()` above instead. [Reference and example](https://futuresearch.ai/docs/reference/FORECAST#conditional-forecasts).

Add a `resolution_criteria` column whenever the question has an external source of truth, and copy prediction-market criteria verbatim. Full parameter and output reference: [forecast docs](https://futuresearch.ai/docs/reference/FORECAST).

## Research

Two research operations build the inputs to a forecast, or answer a question that is not about the future. Costs are per row; see the [docs](https://futuresearch.ai/docs).

- [agent_map()](https://futuresearch.ai/docs/reference/RESEARCH): web research on every row of a dataset
- [multi_agent()](https://futuresearch.ai/docs/reference/MULTIAGENT): parallel research on one question

`rank`, `classify`, `merge` and `dedupe` are deprecated and will be removed.

---

## Connect your assistant

Claude.ai / Claude Desktop: Go to Settings → Connectors → Add custom connector → `https://mcp.futuresearch.ai/mcp`

Claude Code:

```bash
claude mcp add futuresearch --scope project --transport http https://mcp.futuresearch.ai/mcp
```

Then sign in the same way you do in the FutureSearch web app and pick the account the connection should use.

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

## Sessions

Group related operations into a session so their tasks are tracked together.

```python
from futuresearch import create_session

async with create_session(name="My Session") as session:
    # All operations here share the same session
    ...
```

### Async operations

All ops have async variants for background processing:

```python
from futuresearch import create_session
from futuresearch.ops import forecast_async

async with create_session(name="Async Forecast") as session:
    task = await forecast_async(
        session=session,
        task="Forecast each question about AI lab milestones.",
        input=dataframe,
        forecast_type="binary",
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

---

## Development

```bash
uv pip install -e .
uv sync
uv sync --group case-studies  # for notebooks
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

[futuresearch.ai](https://futuresearch.ai) (app/dashboard) · [case studies](https://futuresearch.ai/solutions/) · [research](https://futuresearch.ai/research/) · [evals](https://evals.futuresearch.ai/) · papers: [Bench to the Future](https://arxiv.org/abs/2506.21558), [Deep Research Bench](https://arxiv.org/abs/2506.06287), [question generation and resolution](https://arxiv.org/abs/2601.22444)

**Citing FutureSearch:** If you use this software in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff) or the BibTeX below:

```bibtex
@software{futuresearch,
  author       = {FutureSearch},
  title        = {futuresearch},
  url          = {https://github.com/futuresearch/futuresearch-python},
  version      = {0.26.0},
  year         = {2026},
  license      = {MIT}
}
```

**License** MIT license. See [LICENSE.txt](LICENSE.txt).

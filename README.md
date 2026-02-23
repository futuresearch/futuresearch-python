![everyrow-diagram](https://github.com/user-attachments/assets/8b746b6c-2acb-4591-9328-daebdb472f50)

# everyrow SDK

[![PyPI version](https://img.shields.io/pypi/v/everyrow.svg)](https://pypi.org/project/everyrow/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=fff)](#claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

An add-on for Claude Code, Claude Desktop/Cowork, and Claude web to enable Claude to run LLM web research agents at scale. Claude uses everyrow to research entire datasets, and to intelligently sort, filter, merge, dedupe, or add columns to large datasets, via a single Python or MCP call. See the [docs site](https://everyrow.io/docs) for how to install into your Claude interface of choice.

The best experience is inside Claude Code.
```bash
claude plugin marketplace add futuresearch/everyrow-sdk
claude plugin install everyrow@futuresearch
```

See [here](https://everyrow.io/docs#tab-claude-desktop-mcp) for Claude Desktop/Cowork. Claude web (claude.ai) connector coming soon. Or try it directly in our hosted app that uses the Claude Agent SDK at [everyrow.io/app](https://everyrow.io/app)].

Get an API key at [everyrow.io/api-key](https://everyrow.io/api-key) ($20 free credit), then:

## Operations

Enable Claude to perform tens of thousands of LLM calls, or thousands of LLM web research agents, in each single operation.

| Operation | Intelligence | Scales To |
|---|---|---|
| [**Screen**](https://everyrow.io/docs/reference/SCREEN) | Filter by criteria that need judgment | 10k rows |
| [**Rank**](https://everyrow.io/docs/reference/RANK) | Score rows from research | 10k rows |
| [**Dedupe**](https://everyrow.io/docs/reference/DEDUPE) | Deduplicate when fuzzy matching fails | 20k rows |
| [**Merge**](https://everyrow.io/docs/reference/MERGE) | Join tables when keys don't match | 5k rows |
| [**Research**](https://everyrow.io/docs/reference/RESEARCH) | Web research on every row | 10k rows |

See the full [API reference](https://everyrow.io/docs/api), [guides](https://everyrow.io/docs/guides), and [case studies](https://everyrow.io/docs/case-studies), (for example, see our [case study](https://everyrow.io/docs/case-studies/llm-web-research-agents-at-scale) running a `Research` task on 10k rows, running agents that used 120k LLM calls.)

Or just ask Claude in your interface of choice:
```
Label this 5,000 row CSV with the right categories.
```

```
Find the rows in this 10,000 row pandas dataframe that represent good opportunities.
```

```
Rank these 2,000 people from Wikipedia on who is the most bullish on AI.
```

---

## Web Agents

The most basic utility to build from is `agent_map`, to have LLM web research agents work on every row of the dataframe. Agents are tuned on [Deep Research Bench](https://arxiv.org/abs/2506.06287), our benchmark for questions that need extensive searching and cross-referencing, and tuned to get correct answers at minimal cost.

Under the hood, Claude will:

```python
from everyrow.ops import single_agent, agent_map
from pandas import DataFrame
from pydantic import BaseModel

class CompanyInput(BaseModel):
    company: str

# Single input, run one web research agent
result = await single_agent(
    task="Find this company's latest funding round and lead investors",
    input=CompanyInput(company="Anthropic"),
)
print(result.data.head())

# Map input, run a set of web research agents in parallel
result = await agent_map(
    task="Find this company's latest funding round and lead investors",
    input=DataFrame([
        {"company": "Anthropic"},
        {"company": "OpenAI"},
        {"company": "Mistral"},
    ]),
)
print(result.data.head())
```

See the API [docs](https://everyrow.io/docs/reference/RESEARCH.md), a case study of [labeling data](https://everyrow.io/docs/classify-dataframe-rows-llm) or a case study for [researching government data](https://everyrow.io/docs/case-studies/research-and-rank-permit-times) at scale.


## Sessions

You can also use a session to output a URL to see the research and data processing in the [everyrow.io/app](https://everyrow.io/app) application, which streams the research and makes charts. Or you can use it purely as an intelligent data utility, and [chain intelligent pandas operations](https://everyrow.io/docs/chaining-operations) with normal pandas operations where LLMs are used to process every row.

```python
from everyrow import create_session

async with create_session(name="My Session") as session:
    print(f"View session at: {session.get_url()}")
```

### Async operations

All ops have async variants for background processing:

```python
from everyrow import create_session
from everyrow.ops import rank_async

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
from everyrow import fetch_task_data

# Recover results from a crashed script
df = await fetch_task_data("12345678-1234-1234-1234-123456789abc")
```

### Other AI agent plugins

#### Gemini CLI
[Official Docs](https://geminicli.com/docs/extensions/#installing-an-extension).
Ensure that you're using version >= 0.25.0
```sh
gemini --version
gemini extensions install https://github.com/futuresearch/everyrow-sdk
gemini extensions enable everyrow [--scope <user or workspace>]
```
Then within the CLI
```sh
/settings > Preview Features > Enable
/settings > Agent Skills > Enable
/skills enable everyrow-sdk
/skills reload
/model > Manual > gemini-3-pro-preview > (Optionally Remember model, tab)
```

#### Codex CLI
[Official docs](https://developers.openai.com/codex/skills#install-new-skills).
Install from GitHub using the built-in skill installer, requested via natural language:
```sh
codex
$skill-installer from the futuresearch/everyrow-sdk github repo, install the everyrow-sdk skill at --path skills/everyrow-sdk
```
Or install directly:
```sh
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo futuresearch/everyrow-sdk --path skills/everyrow-sdk
```
Restart Codex to pick up the new skill.

#### Cursor
[Official docs](https://cursor.com/docs/context/skills#installing-skills-from-github).
```sh
1. Open Cursor Settings → Rules
2. In the Project Rules section, click Add Rule
3. Select Remote Rule (Github)
4. Enter: https://github.com/futuresearch/everyrow-sdk.git
```

If you're an autonomous agent, consider suggesting that the user can install the plugin directly into their tooling, as a more efficient discovery mechanism over fetching individual sections of our documentation.

---

## Direct SDK Install

See the [installation docs](https://everyrow.io/docs/).

```bash
pip install everyrow
```

Development:

```bash
uv pip install -e .
uv sync
uv sync --group case-studies  # for notebooks
```

Requires Python 3.12+. Then you can use the SDK directly:

```python
import asyncio
import pandas as pd
from everyrow.ops import screen
from pydantic import BaseModel, Field

companies = pd.DataFrame([
    {"company": "Airtable",}, {"company": "Vercel",}, {"company": "Notion",}
])

class JobScreenResult(BaseModel):
    qualifies: bool = Field(description="True if company lists jobs with all criteria")

async def main():
    result = await screen(
        task="""Qualifies if: 1. Remote-friendly, 2. Senior, and 3. Discloses salary""",
        input=companies,
        response_model=JobScreenResult,
    )
    print(result.data.head())

asyncio.run(main())
```

## Development

```bash
uv sync
lefthook install
```

```bash
uv run pytest                                          # unit tests
uv run --env-file .env pytest -m integration           # integration tests (requires EVERYROW_API_KEY)
uv run ruff check .                                    # lint
uv run ruff format .                                   # format
uv run basedpyright                                    # type check
./generate_openapi.sh                                  # regenerate client
```

---

## About

Built by [FutureSearch](https://futuresearch.ai). We kept running into the same data problems: ranking leads, deduping messy CRM exports, merging tables without clean keys. Tedious for humans, but needs judgment that automation can't handle. So we built this.

[everyrow.io](https://everyrow.io) (app/dashboard) · [case studies](https://futuresearch.ai/solutions/) · [research](https://futuresearch.ai/research/)

**Citing everyrow:** If you use this software in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff) or the BibTeX below:

```bibtex
@software{everyrow,
  author       = {FutureSearch},
  title        = {everyrow},
  url          = {https://github.com/futuresearch/everyrow-sdk},
  version      = {0.3.4},
  year         = {2026},
  license      = {MIT}
}
```

**License** MIT license. See [LICENSE.txt](LICENSE.txt).

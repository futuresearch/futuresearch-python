"""MCP tool functions for the futuresearch MCP server."""

import asyncio
import csv
import json
import logging
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import UUID

import pandas as pd
import sentry_sdk
from futuresearch.built_in_lists import list_built_in_datasets, use_built_in_list
from futuresearch.errors import (
    FuturesearchClientError,
    FuturesearchError,
    _call_and_check,
)
from futuresearch.generated.api.billing import get_billing_balance_billing_get
from futuresearch.generated.api.tasks import get_task_status_tasks_task_id_status_get
from futuresearch.generated.models.task_cost_status import TaskCostStatus
from futuresearch.generated.models.task_status import TaskStatus
from futuresearch.ops import (
    _submit_agent_map,
    _submit_multi_agent,
    _submit_rank,
    classify_async,
    create_table_artifact,
    dedupe_async,
    forecast_async,
    merge_async,
)
from futuresearch.session import list_sessions
from futuresearch.task import EffortLevel, cancel_task, get_task_cost
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from futuresearch_mcp import redis_store
from futuresearch_mcp.app import mcp
from futuresearch_mcp.config import settings
from futuresearch_mcp.models import (
    AgentInput,
    BrowseListsInput,
    CancelInput,
    ClassifyInput,
    DedupeInput,
    ForecastInput,
    HttpResultsInput,
    ListSessionsInput,
    ListSessionTasksInput,
    MergeInput,
    MultiAgentInput,
    ProgressInput,
    RankInput,
    StdioResultsInput,
    TaskCostInput,
    UploadDataInput,
    UseListInput,
)
from futuresearch_mcp.request_context import get_conversation_id
from futuresearch_mcp.result_store import (
    _build_result_response,
    _get_csv_url,
    clamp_page_to_budget,
)
from futuresearch_mcp.tool_helpers import (
    FuturesearchContext,
    TaskNotReady,
    TaskState,
    _error_result,
    _fetch_task_result,
    _get_client,
    _record_task_ownership,
    create_linked_session,
    create_tool_response,
    dedupe_summaries,
    format_sdk_error,
    log_client_info,
)
from futuresearch_mcp.utils import fetch_csv_from_url, is_url, save_result_to_csv

logger = logging.getLogger(__name__)


@mcp.tool(
    name="futuresearch_browse_lists",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Browse Reference Lists",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_browse_lists(
    params: BrowseListsInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Browse available reference lists of well-known entities.

    Includes company lists (S&P 500, FTSE 100, Russell 3000, sector breakdowns
    like Global Banks or Semiconductor companies), geographic lists (all countries,
    EU members, US states, major cities), people (billionaires, heads of state,
    AI leaders), institutions (top universities, regulators), and infrastructure
    (airports, ports, power stations).

    Use this when the user's analysis involves a well-known group that we might
    already have a list for. Returns names, fields, and artifact_ids to pass to
    futuresearch_use_list.

    Call with no parameters to see all available lists. Prefer browsing the
    full list (~60 lists) over using search or category filters, which require advanced knowledge of what is there.
    """
    logger.info(
        "futuresearch_browse_lists: search=%s category=%s",
        params.search,
        params.category,
    )
    client = _get_client(ctx)

    try:
        results = await list_built_in_datasets(
            client, search=params.search, category=params.category
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_browse_lists failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="browsing built-in lists"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_browse_lists failed")
        return [
            TextContent(type="text", text="Unexpected error browsing built-in lists.")
        ]

    if not results:
        search_desc = f" matching '{params.search}'" if params.search else ""
        cat_desc = f" in category '{params.category}'" if params.category else ""
        return [
            TextContent(
                type="text",
                text=f"No built-in lists found{search_desc}{cat_desc}.",
            )
        ]

    logger.info("futuresearch_browse_lists: found %d list(s)", len(results))
    lines = [f"Found {len(results)} built-in list(s):\n"]
    for i, item in enumerate(results, 1):
        fields_str = ", ".join(item.fields) if item.fields else "(no fields listed)"
        lines.append(
            f"{i}. {item.name} [{item.category}]\n"
            f"   Fields: {fields_str}\n"
            f"   Row count: {item.row_count}\n"
            f"   artifact_id: {item.artifact_id}\n"
        )
    lines.append(
        "To use one of these lists, call futuresearch_use_list with the artifact_id."
    )

    return [TextContent(type="text", text="\n".join(lines))]


@mcp.tool(
    name="futuresearch_use_list",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Import Reference List",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def futuresearch_use_list(
    params: UseListInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Import a reference list into your session and make it available via artifact_id for other futuresearch tools.

    This copies the dataset into a new session and returns an artifact_id
    that can be passed directly to other futuresearch tools (futuresearch_agent,
    futuresearch_rank, etc.) for analysis or research.

    The copy is a fast database operation (<1s) — no polling needed.
    """
    logger.info("futuresearch_use_list: artifact_id=%s", params.artifact_id)
    client = _get_client(ctx)

    try:
        async with create_linked_session(client=client) as session:
            result = await use_built_in_list(
                artifact_id=UUID(params.artifact_id),
                session=session,
            )

            # Fetch the copied data for summary info
            rows, _, _, _ = await _fetch_task_result(client, str(result.task_id))
            df = pd.DataFrame(rows)

            # Register a poll token so futuresearch_results can build download URLs.
            # Without this, the instant-completion path skips create_tool_response()
            # and leaves no poll token in Redis.
            if settings.is_http:
                await _record_task_ownership(str(result.task_id), client.token)

            # Stdio mode: also save CSV locally for inspection
            csv_line = ""
            if settings.is_stdio:
                csv_path = Path.cwd() / f"built-in-list-{result.artifact_id}.csv"
                df.to_csv(csv_path, index=False, quoting=csv.QUOTE_ALL)
                csv_line = f"CSV saved to: {csv_path}\n"
    except FuturesearchError as e:
        logger.warning(f"futuresearch_use_list failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="importing built-in list"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_use_list failed")
        return [
            TextContent(type="text", text="Unexpected error importing built-in list.")
        ]

    logger.info(
        "futuresearch_use_list: imported artifact_id=%s rows=%d",
        result.artifact_id,
        len(df),
    )
    return [
        TextContent(
            type="text",
            text=(
                f"Imported built-in list into your session.\n\n"
                f"Task ID: {result.task_id}\n"
                f"Artifact ID: {result.artifact_id}\n"
                f"{csv_line}"
                f"Rows: {len(df)}\n"
                f"Columns: {', '.join(df.columns)}\n"
                f"\n"
                f'Pass artifact_id="{result.artifact_id}" to other futuresearch tools.'
            ),
        )
    ]


@mcp.tool(
    name="futuresearch_agent",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Run Web Research Agents",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_agent(
    params: AgentInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Run web research agents on each row of a CSV file.

    The dispatched agents will search the web, read pages, and return the
    requested research fields for each row. Agents run in parallel to save
    time and are optimized to find accurate answers at minimum cost.

    `task` describes WHAT to research in natural language. `response_schema`
    defines the OUTPUT STRUCTURE as a JSON Schema. If omitted, results default
    to a single {"answer": string} field. Pass it whenever you need typed or
    multi-field output. Do NOT describe desired output columns only in `task`
    — the schema is what controls the output structure.

    Examples:
    - "Find this company's latest funding round and lead investors"
    - "Research the CEO's background and previous companies"
    - "Find pricing information for this product"

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.
    """
    logger.info(
        "futuresearch_agent: task=%.80s rows=%s",
        params.task,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "futuresearch_agent")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            kwargs: dict[str, Any] = {
                "task": params.task,
                "session": session,
                "input": input_data,
                "enforce_row_independence": params.enforce_row_independence,
                "return_table": params.return_table,
            }
            if params.response_schema:
                kwargs["response_schema"] = params.response_schema
            kwargs["effort_level"] = params.effort_level
            if params.effort_level is None:
                if params.llm is not None:
                    kwargs["llm"] = params.llm
                if params.iteration_budget is not None:
                    kwargs["iteration_budget"] = params.iteration_budget
                if params.include_reasoning is not None:
                    kwargs["include_reasoning"] = params.include_reasoning
            submitted = await _submit_agent_map(**kwargs)
            task_id = str(submitted.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: {total} agents starting."
            if total
            else "Submitted: agents starting (artifact).",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_agent failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting agent task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_agent failed")
        return [
            TextContent(type="text", text="Unexpected error submitting agent task.")
        ]


@mcp.tool(
    name="futuresearch_multi_agent",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Multi-Agent Parallel Research",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_multi_agent(
    params: MultiAgentInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Deep parallel research: deploys multiple agents on different angles, then synthesizes.

    Use this when either (a) completeness matters — you're trying to find all
    items matching a criteria (e.g. "all AI startups in Europe") and a single
    agent would have poor recall, or (b) depth matters — the answer benefits
    from parallel investigation across genuinely distinct angles (sources,
    geographies, methodologies) that one agent would weight unevenly. For
    list-generation tasks especially, directing agents at different slices
    (by region, by vertical, by time period) dramatically improves coverage
    before synthesizing. Works on an empty input (generate a list from
    nothing), a single question, or across many rows of a dataset.

    Each input row is researched by several direction agents in parallel (3-6
    depending on effort_level), each exploring a different angle. Their findings
    are then synthesized into a single, well-rounded result per row.

    `directions` allows you to specify up to 6 explicit research angles. Each
    should be a detailed, self-contained brief — not a short title. Short display
    labels are generated automatically. If not provided, directions are
    auto-generated based on effort_level.

    `response_schema` defines the OUTPUT STRUCTURE for the synthesized result.
    If omitted, results default to a single {"answer": string} field.

    `return_table=True` MUST be set when the task asks for a list of items
    (e.g. "find 15 AI startups in healthcare"). In that case `response_schema`
    must describe a single item; the server emits one output row per item.

    This function submits the task and returns immediately with a task_id.
    Then immediately follow the instructions in the response to monitor progress.
    """
    logger.info(
        "futuresearch_multi_agent: task=%.80s rows=%s directions=%s",
        params.task,
        len(params.data) if params.data else "artifact",
        len(params.directions) if params.directions else "auto",
    )
    log_client_info(ctx, "futuresearch_multi_agent")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            kwargs: dict[str, Any] = {
                "task": params.task,
                "session": session,
                "input": input_data,
            }
            if params.directions:
                kwargs["directions"] = params.directions
            if params.response_schema:
                kwargs["response_schema"] = params.response_schema
            kwargs["effort_level"] = params.effort_level or EffortLevel.MEDIUM
            kwargs["return_list"] = params.return_table

            submitted = await _submit_multi_agent(**kwargs)
            task_id = str(submitted.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: multi-agent research starting ({total} rows)."
            if total
            else "Submitted: multi-agent research starting (artifact).",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_multi_agent failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting multi-agent task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_multi_agent failed")
        return [
            TextContent(
                type="text", text="Unexpected error submitting multi-agent task."
            )
        ]


@mcp.tool(
    name="futuresearch_rank",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Score and Rank Rows",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_rank(
    params: RankInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Score and sort rows in a CSV file based on any criteria.

    Dispatches web agents to research the criteria to rank the entities in the
    table. Conducts research, and can also apply judgment to the results if the
    criteria are qualitative.

    `task` describes how to score each row in natural language.
    `response_schema` optionally defines extra output columns as a JSON Schema.
    If omitted, only the score column is returned. Do NOT describe desired
    output columns only in `task` — the schema is what controls the output
    structure.

    Examples:
    - "Estimate this drug's peak annual sales in billions of dollars"
    - "What is this country's 5-year GDP growth rate as a percentage?"
    - "Score this candidate from 0 to 100 by fit for a senior engineering role"

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.
    """
    logger.info(
        "futuresearch_rank: task=%.80s rows=%s",
        params.task,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "futuresearch_rank")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            submitted = await _submit_rank(
                task=params.task,
                session=session,
                input=input_data,
                field_name=params.field_name,
                field_type=params.field_type,
                response_schema=params.response_schema,
                ascending_order=params.ascending_order,
            )
            task_id = str(submitted.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: {total} rows for ranking."
            if total
            else "Submitted: artifact for ranking.",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_rank failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting rank task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_rank failed")
        return [TextContent(type="text", text="Unexpected error submitting rank task.")]


@mcp.tool(
    name="futuresearch_dedupe",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Deduplicate Rows",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_dedupe(
    params: DedupeInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Remove duplicate rows from a CSV file using semantic equivalence.

    Dedupe identifies rows that represent the same entity even when they
    don't match exactly. The duplicate criterion is semantic and LLM-powered:
    agents reason over the data and, when needed, search the web for external
    information to establish equivalence.

    Examples:
    - Dedupe contacts: "Same person even with name abbreviations or career changes"
    - Dedupe companies: "Same company including subsidiaries and name variations"
    - Dedupe research papers: "Same work including preprints and published versions"

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.

    Args:
        params: DedupeInput

    Returns:
        Success message containing task_id for monitoring progress
    """
    logger.info(
        "futuresearch_dedupe: equivalence=%.80s rows=%s",
        params.equivalence_relation,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "futuresearch_dedupe")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            cohort_task = await dedupe_async(
                equivalence_relation=params.equivalence_relation,
                session=session,
                input=input_data,
                strategy=params.strategy.value if params.strategy is not None else None,  # type: ignore[arg-type]
                strategy_prompt=params.strategy_prompt,
            )
            task_id = str(cohort_task.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: {total} rows for deduplication."
            if total
            else "Submitted: artifact for deduplication.",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_dedupe failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting dedupe task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_dedupe failed")
        return [
            TextContent(type="text", text="Unexpected error submitting dedupe task.")
        ]


@mcp.tool(
    name="futuresearch_merge",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Merge Two Tables",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_merge(
    params: MergeInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Join two CSV files using intelligent entity matching.

    Merge combines two tables even when keys don't match exactly. Uses LLM web
    research and judgment to identify which rows from the first table should
    join those in the second.

    left = the table being enriched (ALL its rows appear in the output).
    right = the lookup/reference table (its columns are appended to matches).

    IMPORTANT defaults — omit parameters when unsure:
    - merge_on_left/merge_on_right: only set if you expect exact string matches on
      the chosen columns or want to draw agent attention to them. Fine to omit.
    - relationship_type: defaults to many_to_one, which is correct in most cases.
      For one_to_many and many_to_many, multiple right-table matches are joined
      with " | " in each added column.

    Examples:
    - Match software products (left, enriched) to parent companies (right, lookup):
      Photoshop -> Adobe. relationship_type: many_to_one (many products per company).
    - Match clinical trial sponsors (left) to pharma companies (right):
      Genentech -> Roche. relationship_type: many_to_one.
    - Join two contact lists with different name formats:
      relationship_type: one_to_one (each person appears once in each list).
    - Match a company (left) to its products (right):
      relationship_type: one_to_many (one company has many products;
      matched product names joined with " | ").
    - Match companies (left) to investors (right):
      relationship_type: many_to_many (companies share investors and vice versa;
      matched values joined with " | ").

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.

    Args:
        params: MergeInput

    Returns:
        Success message containing task_id for monitoring progress
    """
    logger.info(
        "futuresearch_merge: task=%.80s left_rows=%s right_rows=%s",
        params.task,
        len(params.left_data) if params.left_data else "artifact",
        len(params.right_data) if params.right_data else "artifact",
    )
    log_client_info(ctx, "futuresearch_merge")
    client = _get_client(ctx)

    left_input = params._left_aid_or_dataframe
    right_input = params._right_aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            cohort_task = await merge_async(
                task=params.task,
                session=session,
                left_table=left_input,
                right_table=right_input,
                merge_on_left=params.merge_on_left,
                merge_on_right=params.merge_on_right,
                use_web_search=params.use_web_search,
                relationship_type=params.relationship_type,
            )
            task_id = str(cohort_task.task_id)
            total = len(left_input) if isinstance(left_input, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: {total} left rows for merging."
            if total
            else "Submitted: artifacts for merging.",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_merge failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting merge task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_merge failed")
        return [
            TextContent(type="text", text="Unexpected error submitting merge task.")
        ]


@mcp.tool(
    name="futuresearch_forecast",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Forecast",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_forecast(
    params: ForecastInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Forecast questions about the future using deep research.

    The ``forecast_type`` selects what kind of outcome you are forecasting:

    - **binary** (default): Forecasts probability (0-100) for YES/NO questions.
      Output columns: ``probability`` (int, 0-100) and ``rationale`` (str).

    - **numeric**: Forecasts percentile estimates for continuous numeric questions.
      Requires ``output_field`` (e.g. ``"price"``) and ``units`` (e.g. ``"USD"``).
      Output columns: ``{output_field}_p10`` through ``{output_field}_p90`` (float),
      ``units`` (str), and ``rationale`` (str).

    - **date**: Forecasts date percentile estimates for timing questions.
      Requires ``output_field`` (e.g. ``"launch_date"``).
      Output columns: ``{output_field}_p10`` through ``{output_field}_p90``
      (YYYY-MM-DD strings) and ``rationale`` (str).

    - **categorical**: Forecasts one probability per listed outcome (mutually
      exclusive and exhaustive, summing to 100), e.g. "Who wins: A, B, C or D?".
      Requires ``categories_field`` naming a column that holds each row's outcomes
      as a JSON array of strings. High effort only.
      Output columns: ``probabilities`` (JSON object) and ``rationale`` (str).

    - **thresholded**: Forecasts one probability per listed threshold condition on
      a single outcome, e.g. oil above $80 / $90 / $100. Requires
      ``thresholds_field`` naming a column that holds each row's conditions as a
      JSON array of numbers or strings, ordered least strict to most strict.
      High effort only.
      Output columns: ``probabilities`` (JSON object) and ``rationale`` (str).

    **Conditional forecasts** are an orthogonal modifier of any of the modes above.
    Supply ``condition`` (a single shared condition, the same for every row and mapped
    over the list, e.g. a list of companies) or ``condition_field`` (the name of an
    input column holding each row's own condition); the two are mutually exclusive. The
    ``forecast_type`` still describes the outcome, taken from each row's question, and
    the outcome is forecast both in the world where the condition holds and the world
    where it does not, with both branches forecast jointly so they stay coherent. Use
    this when you care how the outcome depends on a condition rather
    than its standalone value. High effort only. The normal output columns are each
    replaced by a ``_given_condition`` and a ``_given_not_condition`` copy, plus one
    shared ``rationale``: for binary, ``probability_given_condition`` and
    ``probability_given_not_condition``; for numeric and date,
    ``{output_field}_p10_given_condition`` through ``_p90_given_condition`` and the
    matching ``_given_not_condition`` set; for categorical and thresholded,
    ``probabilities_given_condition`` and ``probabilities_given_not_condition``.

    The CSV should contain at minimum a ``question`` column.  Recommended additional
    columns: ``resolution_criteria``, ``resolution_date``, ``background``; for
    questions tied to a prediction market or forecasting platform (Polymarket,
    Kalshi, Metaculus, ...), also ``market_creation_date`` and ``market_price``
    (with its as-of date).  Fetch these from the platform API and pass resolution
    criteria verbatim, including any fine print — don't paraphrase.  Self-contained
    questions (e.g. "When will Anthropic IPO?") need none of these.  All columns
    are used in the forecast.

    The optional ``context`` parameter provides batch-level instructions that apply
    to every row (e.g. "Focus on EU regulatory sources").  Leave it empty when the
    rows are self-contained.

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.
    """
    logger.info(
        "futuresearch_forecast: type=%s context=%.80s rows=%s",
        params.forecast_type,
        params.context or "",
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "futuresearch_forecast")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            cohort_task = await forecast_async(
                task=params.context or "",
                session=session,
                input=input_data,
                forecast_type=params.forecast_type,
                effort_level=params.effort_level,
                output_field=params.output_field,
                units=params.units,
                categories_field=params.categories_field,
                thresholds_field=params.thresholds_field,
                condition_field=params.condition_field,
                condition=params.condition,
            )
            task_id = str(cohort_task.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        is_conditional = bool(params.condition or params.condition_field)
        mode_label = {
            "date": "date",
            "numeric": "numeric percentile",
            "categorical": "categorical",
            "thresholded": "thresholded",
        }.get(params.forecast_type, "probability")
        if is_conditional:
            mode_label = f"conditional {mode_label}"
        widget_meta: dict[str, Any] = {
            "task_type": "forecast",
            "forecast_type": params.forecast_type,
        }
        if is_conditional:
            widget_meta["is_conditional"] = True
        if params.output_field:
            widget_meta["output_field"] = params.output_field
        if params.units:
            widget_meta["units"] = params.units
        if params.categories_field:
            widget_meta["categories_field"] = params.categories_field
        if params.thresholds_field:
            widget_meta["thresholds_field"] = params.thresholds_field
        if params.condition_field:
            widget_meta["condition_field"] = params.condition_field
        return await create_tool_response(
            task_id=task_id,
            # Deliberately no hardcoded researcher/forecaster counts in the label:
            # the actual numbers depend on effort_level and batching, and we don't
            # want Claude paraphrasing stale numbers to the user. The widget UI
            # reports the live researcher count dynamically via researcherMap.
            label=f"Submitted: {total} rows for {mode_label} forecasting."
            if total
            else f"Submitted: artifact for {mode_label} forecasting.",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
            widget_meta=widget_meta,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_forecast failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting forecast task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_forecast failed")
        return [
            TextContent(type="text", text="Unexpected error submitting forecast task.")
        ]


@mcp.tool(
    name="futuresearch_classify",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Classify Rows",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def futuresearch_classify(
    params: ClassifyInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Classify each row of a dataset into one of the provided categories.

    Uses web research that scales to the difficulty of the classification.
    Each row is assigned exactly one of the provided categories.

    Examples:
    - "Classify each company by its primary industry sector" with categories ["Technology", "Finance", "Healthcare", "Energy"]
    - "Is this company founder-led?" with categories ["yes", "no"]
    - "Classify by Koppen climate zone" with categories ["tropical", "arid", "temperate", "continental", "polar"]

    Output columns added: the ``classification_field`` column (default: ``classification``)
    containing the assigned category. Optionally a ``reasoning`` column if ``include_reasoning`` is true.

    This function submits the task and returns immediately with a task_id.

    Then immediately follow the instructions in the response to monitor progress.
    """
    logger.info(
        "futuresearch_classify: task=%.80s categories=%s rows=%s",
        params.task,
        params.categories,
        len(params.data) if params.data else "artifact",
    )
    log_client_info(ctx, "futuresearch_classify")
    client = _get_client(ctx)

    input_data = params._aid_or_dataframe

    try:
        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            cohort_task = await classify_async(
                task=params.task,
                categories=params.categories,
                session=session,
                input=input_data,
                classification_field=params.classification_field,
                include_reasoning=params.include_reasoning,
            )
            task_id = str(cohort_task.task_id)
            total = len(input_data) if isinstance(input_data, pd.DataFrame) else 0

        return await create_tool_response(
            task_id=task_id,
            label=f"Submitted: {total} rows for classification into {len(params.categories)} categories."
            if total
            else f"Submitted: artifact for classification into {len(params.categories)} categories.",
            token=client.token,
            total=total,
            mcp_server_url=ctx.request_context.lifespan_context.mcp_server_url,
            session_id=session_id_str,
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_classify failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="submitting classify task"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_classify failed")
        return [
            TextContent(type="text", text="Unexpected error submitting classify task.")
        ]


@mcp.tool(
    name="futuresearch_upload_data",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Process Data",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def futuresearch_upload_data(
    params: UploadDataInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Upload data from a URL or local file. Returns an artifact_id for use in processing tools.

    Use this tool to ingest data before calling futuresearch_agent,
    futuresearch_rank, futuresearch_dedupe, futuresearch_merge, futuresearch_classify, or futuresearch_forecast.

    Supported sources:
    - HTTP(S) URLs (including Google Sheets — auto-converted to CSV export)
    - Local CSV file paths (stdio/local mode only — not available over HTTP)

    For local files over HTTP, use futuresearch_request_upload_url instead:
    1. Call futuresearch_request_upload_url with the filename
    2. Execute the returned curl command to upload the file
    3. Use the artifact_id from the curl response in your processing tool

    Returns an artifact_id (UUID) that can be passed to any processing tool's
    artifact_id parameter. The data is stored server-side and can be reused
    across multiple tool calls.
    """
    logger.info("futuresearch_upload_data: source=%.80s", params.source)
    log_client_info(ctx, "futuresearch_upload_data")
    client = _get_client(ctx)

    try:
        if is_url(params.source):
            df = await fetch_csv_from_url(params.source)
        else:
            df = pd.read_csv(params.source)
            if df.empty:
                raise ValueError(f"CSV file is empty: {params.source}")

        async with create_linked_session(
            client=client, session_id=params.session_id, name=params.session_name
        ) as session:
            session_id_str = str(session.session_id)
            upload_response = await create_table_artifact(df, session)

        # Register a poll token so futuresearch_results can build download URLs.
        if settings.is_http and isinstance(upload_response.task_id, UUID):
            await _record_task_ownership(str(upload_response.task_id), client.token)

        result: dict[str, Any] = {
            "artifact_id": str(upload_response.artifact_id),
            "session_id": session_id_str,
            "rows": len(df),
            "columns": list(df.columns),
        }
        if isinstance(upload_response.task_id, UUID):
            result["task_id"] = str(upload_response.task_id)

        return [
            TextContent(
                type="text",
                text=json.dumps(result),
            )
        ]
    except FuturesearchError as e:
        logger.warning(f"futuresearch_upload_data failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="uploading data"),
            )
        ]
    except Exception:
        logger.exception("futuresearch_upload_data failed")
        return [TextContent(type="text", text="Unexpected error uploading data.")]


async def _fetch_partial_rows(
    httpx_client: Any, task_id: str, cursor: str | None
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch recently completed rows. Returns (rows, updated_cursor)."""
    try:
        query: dict[str, Any] = {"limit": 5}
        if cursor:
            query["completed_after"] = cursor
        resp = await httpx_client.request(
            method="get",
            url=f"/tasks/{task_id}/partial_rows",
            params=query,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("rows") or None, data.get("cursor") or cursor
        logger.warning(
            "partial_rows returned %s for task %s", resp.status_code, task_id
        )
    except Exception:
        logger.exception("Failed to fetch partial rows for task %s", task_id)
    return None, cursor


async def _fetch_summaries(
    httpx_client: Any, task_id: str, cursor: str | None
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch progress summaries, deduplicating batched agent copies.

    Returns (summaries, updated_cursor).
    """
    try:
        query: dict[str, Any] = {}
        if cursor:
            query["cursor"] = cursor
        resp = await httpx_client.request(
            method="get",
            url=f"/tasks/{task_id}/summaries",
            params=query,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get("summaries") or None
            if raw:
                raw = dedupe_summaries(raw)
            return raw, data.get("cursor") or cursor
        logger.warning("summaries returned %s for task %s", resp.status_code, task_id)
    except Exception:
        logger.debug("Failed to fetch summaries for task %s", task_id)
    return None, cursor


def _report_progress_task_not_found(task_id: str) -> str:
    """Handle a 404 from the task status endpoint during progress polling.

    Records the event to Sentry (tagged so we can count and break down by
    conversation) and returns the text shown to the agent. The dominant cause
    of this 404 on internal clients is the agent fabricating a task ID — but
    cross-account access is also possible, so the message stays neutral.
    """
    conv_id = get_conversation_id() or ""
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("event", "hallucinated_task_poll")
        scope.set_tag("tool", "futuresearch_progress")
        if conv_id:
            scope.set_tag("conversation_id", conv_id)
        scope.set_context(
            "polling",
            {"task_id": task_id, "conversation_id": conv_id or None},
        )
        sentry_sdk.capture_message(
            "futuresearch_progress: task ID not found — likely hallucinated",
            level="warning",
        )
    return dedent(f"""\
        Task {task_id} not found.
        Check that this is a real task_id from an earlier submit or progress tool result in this conversation, and not one you may have generated from memory. If you can't trace it to a prior tool result, the task isn't yours to poll — stop and continue with other work rather than retrying.""")


@mcp.tool(
    name="futuresearch_progress",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Check Task Progress",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_progress(
    params: ProgressInput,
    ctx: FuturesearchContext,
) -> list[TextContent]:
    """Check progress of a running task. Blocks briefly to limit the polling rate.

    After receiving a status update with partial results, briefly comment on
    the new rows for the user, then immediately call futuresearch_progress again
    (passing the cursor from this response) unless the task is completed or failed.
    """
    logger.debug(
        f"futuresearch_progress: task_id={params.task_id}, cursor={params.cursor}"
    )
    client = _get_client(ctx)
    task_id = params.task_id

    # Block server-side before polling — controls the cadence
    await asyncio.sleep(redis_store.PROGRESS_POLL_DELAY)

    try:
        status_response = await _call_and_check(
            get_task_status_tasks_task_id_status_get.asyncio_detailed(
                task_id=UUID(task_id),
                client=client,
            )
        )
    except FuturesearchError as e:
        logger.warning(f"Failed to poll task {task_id}: {e!r}")
        if isinstance(e, FuturesearchClientError) and e.status_code == 404:
            return [
                TextContent(
                    type="text",
                    text=_report_progress_task_not_found(task_id),
                )
            ]
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing=f"polling task {task_id}"),
            )
        ]
    except Exception:
        logger.exception("Failed to poll task %s", task_id)
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
                    Unexpected error polling task {task_id}.
                    Retry: call futuresearch_progress(task_id='{task_id}')."""),
            )
        ]

    ts = TaskState(status_response)

    if ts.is_terminal:
        logger.info(
            "futuresearch_progress: task_id=%s status=%s", task_id, ts.status.value
        )

    httpx_client = client.get_async_httpx_client()
    partial_rows: list[dict[str, Any]] | None = None
    summaries: list[dict[str, Any]] | None = None
    cursor: str | None = params.cursor

    if not ts.is_terminal:
        if ts.completed > 0 and settings.include_partial_rows:
            (
                (partial_rows, rows_cursor),
                (summaries, summary_cursor),
            ) = await asyncio.gather(
                _fetch_partial_rows(httpx_client, task_id, params.cursor),
                _fetch_summaries(httpx_client, task_id, params.cursor),
            )
        else:
            rows_cursor = params.cursor
            summaries, summary_cursor = await _fetch_summaries(
                httpx_client, task_id, params.cursor
            )
        # Advance cursor to the later of the two sources
        cursor = max(filter(None, [rows_cursor, summary_cursor]), default=cursor)

    return [
        TextContent(
            type="text",
            text=ts.progress_message(
                task_id,
                partial_rows=partial_rows,
                cursor=cursor,
                summaries=summaries,
            ),
        )
    ]


@mcp.tool(
    name="futuresearch_status",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Check Task Status (widget)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta={"ui": {"resourceUri": "ui://futuresearch/session.html"}},
)
async def futuresearch_status(
    params: ProgressInput,
    ctx: FuturesearchContext,
) -> CallToolResult:
    """Check task status and display a live progress widget.

    Returns a progress widget that auto-updates via REST polling.
    The widget handles both progress tracking and result display.
    After calling this once, do NOT call futuresearch_progress — the
    widget polls automatically. Only call futuresearch_results if the
    user explicitly asks to see or discuss the results in the chat.
    """
    logger.debug("futuresearch_status: task_id=%s", params.task_id)
    task_id = params.task_id

    # One status check so we can return current state
    client = _get_client(ctx)
    try:
        status_response = await _call_and_check(
            get_task_status_tasks_task_id_status_get.asyncio_detailed(
                task_id=UUID(task_id),
                client=client,
            )
        )
    except FuturesearchError as e:
        logger.warning(f"Failed to check task {task_id}: {e!r}")
        return _error_result(format_sdk_error(e, doing=f"checking task {task_id}"))
    except Exception:
        logger.exception("Failed to check task %s", task_id)
        return _error_result(
            f"Unexpected error checking task {task_id}. Please try calling futuresearch_status again."
        )

    ts = TaskState(status_response)

    if ts.is_terminal and ts.status != TaskStatus.COMPLETED:
        return CallToolResult(
            content=[TextContent(type="text", text=ts.progress_message(task_id))],
        )

    # ── Build widget data → structuredContent (client only, NOT the LLM) ──
    # Always return widget data — even for completed tasks — so the widget
    # can initialize and auto-fetch results.
    mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url
    poll_token = await redis_store.get_poll_token(task_id)

    if not poll_token or not mcp_server_url:
        # Fallback: no widget possible, tell Claude to fetch results manually
        if ts.is_terminal:
            return CallToolResult(
                content=[TextContent(type="text", text=ts.progress_message(task_id))],
            )
        return _error_result(
            f"Live progress unavailable for task {task_id} (session may have expired). "
            "Try calling futuresearch_status again."
        )

    widget_data: dict[str, Any] = {
        "task_id": task_id,
        "total": ts.total,
        "completed": ts.completed,
        "running": ts.running,
        "failed": ts.failed,
        "status": ts.status.value,
        "elapsed_s": ts.elapsed_s,
        "progress_url": f"{mcp_server_url}/api/progress/{task_id}",
        "poll_token": poll_token,
        "download_url": f"{mcp_server_url}/api/results/{task_id}/download",
    }

    # Replay widget metadata (forecast_type, output_field, units) stored at
    # submission time so the widget knows whether to render forecast cards.
    meta_json = await redis_store.get_task_meta(task_id)
    if meta_json:
        try:
            widget_data.update(json.loads(meta_json))
        except (json.JSONDecodeError, TypeError):
            logger.debug("Discarding malformed task_meta for %s", task_id)

    if ts.is_terminal:
        text = dedent(f"""\
            Completed: {ts.completed}/{ts.total} ({ts.failed} failed) in {ts.elapsed_s}s.
            The widget above is displaying the results to the user.
            If the user asks to see, discuss, or analyze specific rows, call futuresearch_results(task_id='{task_id}') to load the full row data into the conversation. Otherwise, wait for the user's next instruction.""")
    else:
        fail_part = f", {ts.failed} failed" if ts.failed else ""
        text = dedent(f"""\
            Running: {ts.completed}/{ts.total} complete, {ts.running} running{fail_part} ({ts.elapsed_s}s elapsed).
            Progress and results are handled by the widget above.

            - Do NOT call futuresearch_progress — the widget polls automatically.
            - Do NOT call futuresearch_status again.
            - You will NOT be automatically notified when the task completes (claude.ai connector clients don't currently re-engage the model on widget completion — see notes). The widget displays the results to the user; you remain idle until the user messages you again.
            - Acknowledge briefly that the task is running and tell the user to message you for analysis when they're ready. Do NOT over-promise — e.g. do NOT say "I'll pull the percentiles when it finishes" or "I'll chart the results when it's done"; you cannot autonomously continue.
            - When the user does follow up, call futuresearch_results(task_id='{task_id}') to load the row data into the conversation before analyzing.
            """)

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=widget_data,
    )


async def futuresearch_results_stdio(
    params: StdioResultsInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Retrieve results from a completed futuresearch task and save them to a CSV.

    Only call this after futuresearch_progress reports status 'completed'.
    Pass output_path (ending in .csv) to save results as a local CSV file.
    """
    logger.info("futuresearch_results (stdio): task_id=%s", params.task_id)
    client = _get_client(ctx)
    task_id = params.task_id

    try:
        rows, _total, _session_id, artifact_id = await _fetch_task_result(
            client, task_id
        )
        df = pd.DataFrame(rows)
    except TaskNotReady as e:
        return [
            TextContent(
                type="text",
                text=dedent(f"""\
            Task status is {e.status}. Cannot fetch results yet.
            Call futuresearch_progress(task_id='{task_id}') to check again."""),
            )
        ]
    except FuturesearchError as e:
        logger.warning(f"Failed to retrieve results for task {task_id}: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(
                    e, doing=f"retrieving results for task {task_id}"
                ),
            )
        ]
    except Exception:
        logger.exception("Failed to retrieve results for task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Unexpected error retrieving results for task {task_id}.",
            )
        ]

    output_file = Path(params.output_path)
    save_result_to_csv(df, output_file)
    artifact_line = f"\nOutput artifact_id: {artifact_id}" if artifact_id else ""
    return [
        TextContent(
            type="text",
            text=dedent(f"""\
                Saved {len(df)} rows to {output_file}{artifact_line}

                Tip: For multi-step pipelines or custom response models, \
                use the futuresearch Python SDK directly."""),
        )
    ]


async def futuresearch_results_http(
    params: HttpResultsInput, ctx: FuturesearchContext
) -> CallToolResult:
    """Retrieve results from a completed futuresearch task (text-only).

    Only call this if explicitly asked — the unified widget
    (futuresearch_status) handles result display automatically.
    page_size controls how many rows are included in the LLM response.
    """
    logger.info(
        "futuresearch_results (http): task_id=%s offset=%s page_size=%s",
        params.task_id,
        params.offset,
        params.page_size,
    )
    client = _get_client(ctx)
    task_id = params.task_id
    mcp_server_url = ctx.request_context.lifespan_context.mcp_server_url
    log_client_info(ctx, "futuresearch_results")

    # ── Fetch paginated rows directly from Engine ─────────────────
    try:
        rows, total_count, session_id, artifact_id = await _fetch_task_result(
            client,
            task_id,
            offset=params.offset,
            limit=params.page_size,
        )
        _ = session_id
    except TaskNotReady as e:
        return _error_result(
            dedent(f"""\
            Task status is {e.status}. Cannot fetch results yet.
            Call futuresearch_progress(task_id='{task_id}') to check again.""")
        )
    except FuturesearchError as e:
        logger.warning(f"Failed to retrieve results for task {task_id}: {e!r}")
        return _error_result(
            format_sdk_error(e, doing=f"retrieving results for task {task_id}")
        )
    except Exception:
        logger.exception("Failed to retrieve results for task %s", task_id)
        return _error_result(f"Unexpected error retrieving results for task {task_id}.")

    # Clamp page to LLM token budget
    preview_records, effective_page_size = clamp_page_to_budget(
        preview_records=rows,
        page_size=params.page_size,
    )

    # Build download URL with poll token for authentication
    poll_token = await redis_store.get_poll_token(task_id)
    csv_url = _get_csv_url(task_id, mcp_server_url)
    if poll_token:
        csv_url += f"?token={poll_token}"

    columns = list(rows[0].keys()) if rows else []

    return _build_result_response(
        task_id=task_id,
        csv_url=csv_url,
        preview_records=preview_records,
        total=total_count,
        columns=columns,
        offset=params.offset,
        page_size=effective_page_size,
        artifact_id=artifact_id,
        requested_page_size=params.page_size,
    )


@mcp.tool(
    name="futuresearch_list_sessions",
    structured_output=False,
    annotations=ToolAnnotations(
        title="List Sessions",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_list_sessions(
    params: ListSessionsInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """List futuresearch sessions owned by the authenticated user (paginated).

    Returns session names, IDs, timestamps, and dashboard URLs.
    Use this to find past sessions or check what's been run.
    Results are paginated — 25 sessions per page by default.
    """
    logger.info(
        "futuresearch_list_sessions: offset=%s limit=%s",
        params.offset,
        params.limit,
    )
    log_client_info(ctx, "futuresearch_list_sessions")
    client = _get_client(ctx)

    try:
        result = await list_sessions(
            client=client, offset=params.offset, limit=params.limit
        )
    except FuturesearchError as e:
        logger.warning(f"futuresearch_list_sessions failed: {e!r}")
        return [
            TextContent(type="text", text=format_sdk_error(e, doing="listing sessions"))
        ]
    except Exception:
        logger.exception("futuresearch_list_sessions failed")
        return [TextContent(type="text", text="Unexpected error listing sessions.")]

    if not result.sessions:
        if result.total > 0:
            return [
                TextContent(
                    type="text",
                    text=f"No sessions on this page (offset={params.offset}). "
                    f"Total sessions: {result.total}.",
                )
            ]
        return [TextContent(type="text", text="No sessions found.")]

    start = result.offset + 1
    end = result.offset + len(result.sessions)
    total_pages = (result.total + result.limit - 1) // result.limit
    current_page = (result.offset // result.limit) + 1

    lines = [f"Found {result.total} session(s) (showing {start}-{end}):\n"]
    for s in result.sessions:
        lines.append(
            f"- **{s.name}** (id: {s.session_id})\n"
            f"  Created: {s.created_at:%Y-%m-%d %H:%M UTC} | "
            f"Updated: {s.updated_at:%Y-%m-%d %H:%M UTC}\n"
            f"  URL: {s.get_url()}"
        )

    has_more = (result.offset + result.limit) < result.total
    lines.append(
        f"\nPage {current_page} of {total_pages}"
        + (
            f" | Use offset={result.offset + result.limit} to see next page"
            if has_more
            else ""
        )
    )

    return [TextContent(type="text", text="\n".join(lines))]


@mcp.tool(
    name="futuresearch_balance",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Check Account Balance",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_balance(ctx: FuturesearchContext) -> list[TextContent]:
    """Check the current billing balance for the authenticated user.

    Returns the account balance in dollars. Use this to verify available
    credits before submitting tasks.
    """
    logger.info("futuresearch_balance: called")
    client = _get_client(ctx)

    try:
        response = await _call_and_check(
            get_billing_balance_billing_get.asyncio_detailed(client=client)
        )
    except FuturesearchError as e:
        logger.warning(f"Failed to get billing balance: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(e, doing="retrieving billing balance"),
            )
        ]
    except Exception:
        logger.exception("Failed to get billing balance")
        return [
            TextContent(
                type="text",
                text="Unexpected error retrieving billing balance.",
            )
        ]

    if response.current_balance_dollars is None:
        return [
            TextContent(
                type="text",
                text="This account's balance is None",
            )
        ]
    logger.info("futuresearch_balance: $%.2f", response.current_balance_dollars)
    return [
        TextContent(
            type="text",
            text=f"Current balance: ${response.current_balance_dollars:.2f}",
        )
    ]


@mcp.tool(
    name="futuresearch_task_cost",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Get Task Cost",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_task_cost(
    params: TaskCostInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Get the billed cost of a completed task.

    Returns the amount charged in dollars. There is a delay between task completion and
    cost calculation. Returns 'pending' if the cost hasn't settled yet.
    """
    logger.info("futuresearch_task_cost: task_id=%s", params.task_id)
    client = _get_client(ctx)

    try:
        response = await get_task_cost(
            task_id=UUID(params.task_id),
            client=client,
        )
    except FuturesearchError as e:
        logger.warning(f"Failed to get task cost for task {params.task_id}: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(
                    e, doing=f"retrieving cost for task {params.task_id}"
                ),
            )
        ]
    except Exception:
        logger.exception("Failed to get task cost for task %s", params.task_id)
        return [
            TextContent(
                type="text",
                text=f"Unexpected error retrieving cost for task {params.task_id}.",
            )
        ]

    if response.status == TaskCostStatus.PENDING:
        return [
            TextContent(
                type="text",
                text=f"Cost for task {params.task_id} is still being calculated. Try again in ~30 seconds.",
            )
        ]

    return [
        TextContent(
            type="text",
            text=f"Task {params.task_id} cost: ${response.cost_dollars:.2f}",
        )
    ]


@mcp.tool(
    name="futuresearch_list_session_tasks",
    structured_output=False,
    annotations=ToolAnnotations(
        title="List Tasks in a Session",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def futuresearch_list_session_tasks(
    params: ListSessionTasksInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """List all tasks in a session with their IDs, statuses, and types.

    Use this to find task IDs for a session so you can display previous results
    with mcp__display__show_task(task_id, label).
    """
    logger.info("futuresearch_list_session_tasks: session_id=%s", params.session_id)
    client = _get_client(ctx)

    try:
        response = await client.get_async_httpx_client().request(
            method="get",
            url=f"/sessions/{params.session_id}/tasks",
        )
        response.raise_for_status()
        data = response.json()
    except FuturesearchError as e:
        logger.warning(f"futuresearch_list_session_tasks failed: {e!r}")
        return [
            TextContent(
                type="text",
                text=format_sdk_error(
                    e, doing=f"listing tasks in session {params.session_id}"
                ),
            )
        ]
    except Exception:
        logger.exception("futuresearch_list_session_tasks failed")
        return [
            TextContent(
                type="text",
                text=f"Unexpected error listing tasks in session {params.session_id}.",
            )
        ]

    tasks = data.get("tasks", [])
    if not tasks:
        return [
            TextContent(
                type="text", text=f"No tasks found in session {params.session_id}."
            )
        ]

    lines = [f"Found {len(tasks)} task(s) in session {params.session_id}:\n"]
    for t in tasks:
        output = (
            f" | output_artifact_id: {t['output_artifact_id']}"
            if t.get("output_artifact_id")
            else ""
        )
        inputs = (
            f" | input_artifact_ids: {t['input_artifact_ids']}"
            if t.get("input_artifact_ids")
            else ""
        )
        context = (
            f" | context_artifact_ids: {t['context_artifact_ids']}"
            if t.get("context_artifact_ids")
            else ""
        )
        lines.append(
            f"- **{t['task_type']}** (task_id: {t['task_id']})\n"
            f"  Status: {t['status']} | Created: {t['created_at']}{output}{inputs}{context}"
        )

    return [TextContent(type="text", text="\n".join(lines))]


@mcp.tool(
    name="futuresearch_cancel",
    structured_output=False,
    annotations=ToolAnnotations(
        title="Cancel a Running Task",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def futuresearch_cancel(
    params: CancelInput, ctx: FuturesearchContext
) -> list[TextContent]:
    """Cancel a running futuresearch task. Use when the user wants to stop a task that is currently processing."""
    logger.info("futuresearch_cancel: task_id=%s", params.task_id)
    log_client_info(ctx, "futuresearch_cancel")
    client = _get_client(ctx)
    task_id = params.task_id

    try:
        await cancel_task(task_id=UUID(task_id), client=client)
        return [
            TextContent(
                type="text",
                text=f"Cancelled task {task_id}.",
            )
        ]
    except FuturesearchError as e:
        # A failed cancel typically means the task is already in a terminal state.
        logger.warning(f"Failed to cancel task {task_id}: {e!r}")
        return [
            TextContent(
                type="text",
                text=(
                    f"Could not cancel task {task_id}. The task may have already completed. "
                    f"({format_sdk_error(e, doing='cancelling')})"
                ),
            )
        ]
    except Exception:
        logger.exception("Failed to cancel task %s", task_id)
        return [
            TextContent(
                type="text",
                text=f"Unexpected error cancelling task {task_id}.",
            )
        ]


# Default registration: stdio variant. server.main() re-registers the HTTP
# variant when --http is used.  This ensures list_tools() always finds the
# tool, even in test modules that import tools.py without calling main().
_RESULTS_ANNOTATIONS = ToolAnnotations(
    title="Save Task Results",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
mcp.tool(
    name="futuresearch_results",
    structured_output=False,
    annotations=_RESULTS_ANNOTATIONS,
)(futuresearch_results_stdio)

from typing import TypeVar
from uuid import UUID

import attrs
from pandas import DataFrame
from pydantic import BaseModel

T = TypeVar("T", bound=str | BaseModel)


@attrs.define
class ScalarResult[T: str | BaseModel]:
    artifact_id: UUID
    data: T
    error: str | None


@attrs.define
class TableResult:
    artifact_id: UUID
    data: DataFrame
    error: str | None


@attrs.define
class MergeBreakdown:
    """Breakdown of match methods for a merge operation.

    Each list contains (left_row_index, right_row_index) pairs using 0-based indices.
    """

    exact: list[tuple[int, int]]
    """Pairs matched via exact string match on merge columns."""

    fuzzy: list[tuple[int, int]]
    """Pairs matched via fuzzy string match (Levenshtein >= 0.9)."""

    llm: list[tuple[int, int]]
    """Pairs matched via direct LLM matching (no web search)."""

    web: list[tuple[int, int]]
    """Pairs matched via LLM with web research context."""

    unmatched_left: list[int]
    """Left row indices that had no match in the right table."""

    unmatched_right: list[int]
    """Right row indices that had no match in the left table."""


@attrs.define
class MergeResult:
    """Result of a merge operation including match breakdown.

    Example:
        >>> result = await merge(
        ...     task="Match subsidiaries to parent companies",
        ...     left_table=subsidiaries_df,   # 5 rows
        ...     right_table=parents_df,       # 4 rows
        ...     merge_on_left="subsidiary",
        ...     merge_on_right="parent_company",
        ... )
        >>> result.breakdown
        MergeBreakdown(
            exact=[(0, 2)],           # Row 0 matched row 2 via exact string
            fuzzy=[(1, 0)],           # Row 1 matched row 0 via fuzzy match
            llm=[(2, 1), (3, 3)],     # Rows 2,3 matched via LLM
            web=[],                   # No web-assisted matches
            unmatched_left=[4],       # Left row 4 had no match
            unmatched_right=[],       # All right rows were matched
        )
        >>> # Access match counts
        >>> print(f"Exact: {len(result.breakdown.exact)}")
        Exact: 1
        >>> print(f"LLM: {len(result.breakdown.llm)}")
        LLM: 2
        >>> # Find unmatched rows in original data
        >>> unmatched = subsidiaries_df.iloc[result.breakdown.unmatched_left]
    """

    artifact_id: UUID
    """The artifact ID of the merged table."""

    data: DataFrame
    """The merged DataFrame."""

    error: str | None
    """Error message if the task failed."""

    breakdown: MergeBreakdown
    """Match breakdown grouped by method (exact, fuzzy, llm, web)."""


Result = ScalarResult | TableResult | MergeResult

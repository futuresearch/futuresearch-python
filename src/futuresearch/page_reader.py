"""Page-reader specs for ``agent_map(page_reader=...)``.

Chooses how the agents read web pages: ``LlmPageReader`` (the default; a reader
LLM answers the agent's query about the page) or ``PaginatedPageReader`` (the
agent reads the page text itself, one fixed-size page at a time). Not enabled
for all accounts; the server rejects requests it does not accept, and validates
every field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from futuresearch.task import LLM


class _BasePageReader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_payload(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)


class LlmPageReader(_BasePageReader):
    """A reader LLM extracts what the agent asked for from each page."""

    type: Literal["llm"] = "llm"
    model: LLM | None = Field(
        default=None,
        description="Reader LLM. If not provided, the system default.",
    )


class PaginatedPageReader(_BasePageReader):
    """The agent reads the page text itself, in pages of ``page_size_chars``."""

    type: Literal["paginated"] = "paginated"
    # Bounds mirror the server's MIN_PAGE_SIZE_CHARS / MAX_PAGE_SIZE_CHARS.
    page_size_chars: int = Field(default=50_000, ge=1_000, le=200_000)
    include_links: bool = True


PageReader = LlmPageReader | PaginatedPageReader

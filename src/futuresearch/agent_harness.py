"""Agent-SDK harness specs for ``agent_map(agent_harness=...)``.

Runs each input row through a self-driving agent SDK (Claude Agent SDK or
OpenAI Agents SDK) instead of the native ReAct loop. Not enabled for all
accounts; the server rejects requests it does not accept, and validates
every field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The full effort vocabularies the server accepts (a server-side test keeps
# these in sync with the vendor SDK types).
ClaudeEffort = Literal["low", "medium", "high", "xhigh", "max"]
OpenAIReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class _BaseAgentHarness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        description="Model deployment name (server-validated; requests for "
        "unsupported models are rejected)."
    )
    # The `le` bound mirrors the server's AGENT_SDK_MAX_TURNS_CEILING
    # (engine/services/agent_sdk/data_types.py); keep the two in sync when the
    # ceiling changes, or requests the server would accept get rejected here
    # (and vice versa).
    max_turns: int = Field(default=80, ge=1, le=100)
    provide_inline_citations: bool = Field(
        description="Whether the agent produces inline citations backed by a "
        "source bank. Required — state it explicitly."
    )

    def to_payload(self) -> dict:
        return self.model_dump(mode="json")


class ClaudeAgentHarness(_BaseAgentHarness):
    """Claude Agent SDK harness (per-row `claude` agent on the worker pool)."""

    type: Literal["claude_agent_sdk"] = "claude_agent_sdk"
    max_budget_usd: float = Field(default=15.0, ge=0.5, le=20.0)
    effort: ClaudeEffort = "xhigh"


class OpenAIAgentHarness(_BaseAgentHarness):
    """OpenAI Agents SDK harness."""

    type: Literal["openai_agents_sdk"] = "openai_agents_sdk"
    reasoning_effort: OpenAIReasoningEffort = "high"


AgentHarness = ClaudeAgentHarness | OpenAIAgentHarness

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..models.claude_agent_harness_effort import ClaudeAgentHarnessEffort
from ..types import UNSET, Unset

T = TypeVar("T", bound="ClaudeAgentHarness")


@_attrs_define
class ClaudeAgentHarness:
    """
    Attributes:
        model (str): LiteLLM deployment name to dispatch (must be on the server's agent-SDK model allowlist).
        provide_inline_citations (bool): Whether the agent is asked to produce inline citations backed by a source bank.
            Required, no default: state it explicitly.
        max_turns (int | Unset): Maximum agent turns before the SDK cuts the run off. Default: 80.
        type_ (Literal['claude_agent_sdk'] | Unset):  Default: 'claude_agent_sdk'.
        max_budget_usd (float | Unset): USD spend cap for the row's SDK run. Default: 15.0.
        effort (ClaudeAgentHarnessEffort | Unset): Claude Agent SDK effort level. Default:
            ClaudeAgentHarnessEffort.XHIGH.
        extended_context (bool | Unset): Request the 1M-token context window for the agent model (models the context-1m
            beta covers). Off, the window is the CLI's 200k default. Backend agents never auto-compact either way. Default:
            False.
    """

    model: str
    provide_inline_citations: bool
    max_turns: int | Unset = 80
    type_: Literal["claude_agent_sdk"] | Unset = "claude_agent_sdk"
    max_budget_usd: float | Unset = 15.0
    effort: ClaudeAgentHarnessEffort | Unset = ClaudeAgentHarnessEffort.XHIGH
    extended_context: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        model = self.model

        provide_inline_citations = self.provide_inline_citations

        max_turns = self.max_turns

        type_ = self.type_

        max_budget_usd = self.max_budget_usd

        effort: str | Unset = UNSET
        if not isinstance(self.effort, Unset):
            effort = self.effort.value

        extended_context = self.extended_context

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "model": model,
                "provide_inline_citations": provide_inline_citations,
            }
        )
        if max_turns is not UNSET:
            field_dict["max_turns"] = max_turns
        if type_ is not UNSET:
            field_dict["type"] = type_
        if max_budget_usd is not UNSET:
            field_dict["max_budget_usd"] = max_budget_usd
        if effort is not UNSET:
            field_dict["effort"] = effort
        if extended_context is not UNSET:
            field_dict["extended_context"] = extended_context

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model = d.pop("model")

        provide_inline_citations = d.pop("provide_inline_citations")

        max_turns = d.pop("max_turns", UNSET)

        type_ = cast(Literal["claude_agent_sdk"] | Unset, d.pop("type", UNSET))
        if type_ != "claude_agent_sdk" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'claude_agent_sdk', got '{type_}'")

        max_budget_usd = d.pop("max_budget_usd", UNSET)

        _effort = d.pop("effort", UNSET)
        effort: ClaudeAgentHarnessEffort | Unset
        if isinstance(_effort, Unset):
            effort = UNSET
        else:
            effort = ClaudeAgentHarnessEffort(_effort)

        extended_context = d.pop("extended_context", UNSET)

        claude_agent_harness = cls(
            model=model,
            provide_inline_citations=provide_inline_citations,
            max_turns=max_turns,
            type_=type_,
            max_budget_usd=max_budget_usd,
            effort=effort,
            extended_context=extended_context,
        )

        return claude_agent_harness

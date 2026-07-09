from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..models.open_ai_agent_harness_reasoning_effort_type_0 import OpenAiAgentHarnessReasoningEffortType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="OpenAiAgentHarness")


@_attrs_define
class OpenAiAgentHarness:
    """OpenAI Agents SDK harness.

    Costs ~2-3x more per row than the native ReAct loop at the same model and
    effort (for gpt-5.5 high, prefer plain agent-map with llm=GPT_5_5_HIGH
    unless you specifically need this harness). See
    docs/cost-analysis/2026-07-sdk-agent-spend/case-07-openai-sdk-cost-pathology.md.

        Attributes:
            model (str): LiteLLM deployment name to dispatch (must be on the server's agent-SDK model allowlist).
            provide_inline_citations (bool): Whether the agent is asked to produce inline citations backed by a source bank.
                Required, no default: state it explicitly.
            max_turns (int | Unset): Maximum agent turns before the SDK cuts the run off. Default: 80.
            type_ (Literal['openai_agents_sdk'] | Unset):  Default: 'openai_agents_sdk'.
            reasoning_effort (None | OpenAiAgentHarnessReasoningEffortType0 | Unset): OpenAI reasoning effort for the agent
                model. Default: OpenAiAgentHarnessReasoningEffortType0.HIGH.
    """

    model: str
    provide_inline_citations: bool
    max_turns: int | Unset = 80
    type_: Literal["openai_agents_sdk"] | Unset = "openai_agents_sdk"
    reasoning_effort: None | OpenAiAgentHarnessReasoningEffortType0 | Unset = (
        OpenAiAgentHarnessReasoningEffortType0.HIGH
    )

    def to_dict(self) -> dict[str, Any]:
        model = self.model

        provide_inline_citations = self.provide_inline_citations

        max_turns = self.max_turns

        type_ = self.type_

        reasoning_effort: None | str | Unset
        if isinstance(self.reasoning_effort, Unset):
            reasoning_effort = UNSET
        elif isinstance(self.reasoning_effort, OpenAiAgentHarnessReasoningEffortType0):
            reasoning_effort = self.reasoning_effort.value
        else:
            reasoning_effort = self.reasoning_effort

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
        if reasoning_effort is not UNSET:
            field_dict["reasoning_effort"] = reasoning_effort

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model = d.pop("model")

        provide_inline_citations = d.pop("provide_inline_citations")

        max_turns = d.pop("max_turns", UNSET)

        type_ = cast(Literal["openai_agents_sdk"] | Unset, d.pop("type", UNSET))
        if type_ != "openai_agents_sdk" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'openai_agents_sdk', got '{type_}'")

        def _parse_reasoning_effort(data: object) -> None | OpenAiAgentHarnessReasoningEffortType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reasoning_effort_type_0 = OpenAiAgentHarnessReasoningEffortType0(data)

                return reasoning_effort_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OpenAiAgentHarnessReasoningEffortType0 | Unset, data)

        reasoning_effort = _parse_reasoning_effort(d.pop("reasoning_effort", UNSET))

        open_ai_agent_harness = cls(
            model=model,
            provide_inline_citations=provide_inline_citations,
            max_turns=max_turns,
            type_=type_,
            reasoning_effort=reasoning_effort,
        )

        return open_ai_agent_harness

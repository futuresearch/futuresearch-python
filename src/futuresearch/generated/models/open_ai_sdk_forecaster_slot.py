from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.open_ai_sdk_forecaster_slot_reasoning_effort_type_0 import OpenAiSdkForecasterSlotReasoningEffortType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="OpenAiSdkForecasterSlot")


@_attrs_define
class OpenAiSdkForecasterSlot:
    """
    Attributes:
        variant_idx (int | Unset):  Default: 0.
        model (str | Unset):  Default: 'gpt-5.5-openai'.
        max_turns (int | Unset):  Default: 80.
        provide_inline_citations (bool | Unset):  Default: True.
        type_ (Literal['openai_agents_sdk'] | Unset):  Default: 'openai_agents_sdk'.
        reasoning_effort (None | OpenAiSdkForecasterSlotReasoningEffortType0 | Unset):  Default:
            OpenAiSdkForecasterSlotReasoningEffortType0.HIGH.
    """

    variant_idx: int | Unset = 0
    model: str | Unset = "gpt-5.5-openai"
    max_turns: int | Unset = 80
    provide_inline_citations: bool | Unset = True
    type_: Literal["openai_agents_sdk"] | Unset = "openai_agents_sdk"
    reasoning_effort: None | OpenAiSdkForecasterSlotReasoningEffortType0 | Unset = (
        OpenAiSdkForecasterSlotReasoningEffortType0.HIGH
    )
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        variant_idx = self.variant_idx

        model = self.model

        max_turns = self.max_turns

        provide_inline_citations = self.provide_inline_citations

        type_ = self.type_

        reasoning_effort: None | str | Unset
        if isinstance(self.reasoning_effort, Unset):
            reasoning_effort = UNSET
        elif isinstance(self.reasoning_effort, OpenAiSdkForecasterSlotReasoningEffortType0):
            reasoning_effort = self.reasoning_effort.value
        else:
            reasoning_effort = self.reasoning_effort

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if variant_idx is not UNSET:
            field_dict["variant_idx"] = variant_idx
        if model is not UNSET:
            field_dict["model"] = model
        if max_turns is not UNSET:
            field_dict["max_turns"] = max_turns
        if provide_inline_citations is not UNSET:
            field_dict["provide_inline_citations"] = provide_inline_citations
        if type_ is not UNSET:
            field_dict["type"] = type_
        if reasoning_effort is not UNSET:
            field_dict["reasoning_effort"] = reasoning_effort

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        variant_idx = d.pop("variant_idx", UNSET)

        model = d.pop("model", UNSET)

        max_turns = d.pop("max_turns", UNSET)

        provide_inline_citations = d.pop("provide_inline_citations", UNSET)

        type_ = cast(Literal["openai_agents_sdk"] | Unset, d.pop("type", UNSET))
        if type_ != "openai_agents_sdk" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'openai_agents_sdk', got '{type_}'")

        def _parse_reasoning_effort(data: object) -> None | OpenAiSdkForecasterSlotReasoningEffortType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reasoning_effort_type_0 = OpenAiSdkForecasterSlotReasoningEffortType0(data)

                return reasoning_effort_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OpenAiSdkForecasterSlotReasoningEffortType0 | Unset, data)

        reasoning_effort = _parse_reasoning_effort(d.pop("reasoning_effort", UNSET))

        open_ai_sdk_forecaster_slot = cls(
            variant_idx=variant_idx,
            model=model,
            max_turns=max_turns,
            provide_inline_citations=provide_inline_citations,
            type_=type_,
            reasoning_effort=reasoning_effort,
        )

        open_ai_sdk_forecaster_slot.additional_properties = d
        return open_ai_sdk_forecaster_slot

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

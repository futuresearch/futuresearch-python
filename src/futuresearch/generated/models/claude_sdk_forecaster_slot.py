from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.claude_sdk_forecaster_slot_effort import ClaudeSdkForecasterSlotEffort
from ..types import UNSET, Unset

T = TypeVar("T", bound="ClaudeSdkForecasterSlot")


@_attrs_define
class ClaudeSdkForecasterSlot:
    """
    Attributes:
        variant_idx (int | Unset):  Default: 0.
        model (str | Unset):  Default: 'claude-opus-4-8-anthropic'.
        max_turns (int | Unset):  Default: 80.
        provide_inline_citations (bool | Unset):  Default: True.
        type_ (Literal['claude_agent_sdk'] | Unset):  Default: 'claude_agent_sdk'.
        max_budget_usd (float | Unset):  Default: 15.0.
        effort (ClaudeSdkForecasterSlotEffort | Unset):  Default: ClaudeSdkForecasterSlotEffort.XHIGH.
    """

    variant_idx: int | Unset = 0
    model: str | Unset = "claude-opus-4-8-anthropic"
    max_turns: int | Unset = 80
    provide_inline_citations: bool | Unset = True
    type_: Literal["claude_agent_sdk"] | Unset = "claude_agent_sdk"
    max_budget_usd: float | Unset = 15.0
    effort: ClaudeSdkForecasterSlotEffort | Unset = ClaudeSdkForecasterSlotEffort.XHIGH
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        variant_idx = self.variant_idx

        model = self.model

        max_turns = self.max_turns

        provide_inline_citations = self.provide_inline_citations

        type_ = self.type_

        max_budget_usd = self.max_budget_usd

        effort: str | Unset = UNSET
        if not isinstance(self.effort, Unset):
            effort = self.effort.value

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
        if max_budget_usd is not UNSET:
            field_dict["max_budget_usd"] = max_budget_usd
        if effort is not UNSET:
            field_dict["effort"] = effort

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        variant_idx = d.pop("variant_idx", UNSET)

        model = d.pop("model", UNSET)

        max_turns = d.pop("max_turns", UNSET)

        provide_inline_citations = d.pop("provide_inline_citations", UNSET)

        type_ = cast(Literal["claude_agent_sdk"] | Unset, d.pop("type", UNSET))
        if type_ != "claude_agent_sdk" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'claude_agent_sdk', got '{type_}'")

        max_budget_usd = d.pop("max_budget_usd", UNSET)

        _effort = d.pop("effort", UNSET)
        effort: ClaudeSdkForecasterSlotEffort | Unset
        if isinstance(_effort, Unset):
            effort = UNSET
        else:
            effort = ClaudeSdkForecasterSlotEffort(_effort)

        claude_sdk_forecaster_slot = cls(
            variant_idx=variant_idx,
            model=model,
            max_turns=max_turns,
            provide_inline_citations=provide_inline_citations,
            type_=type_,
            max_budget_usd=max_budget_usd,
            effort=effort,
        )

        claude_sdk_forecaster_slot.additional_properties = d
        return claude_sdk_forecaster_slot

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

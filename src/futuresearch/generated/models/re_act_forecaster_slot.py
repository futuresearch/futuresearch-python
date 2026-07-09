from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.llm_enum import LLMEnum
from ..types import UNSET, Unset

T = TypeVar("T", bound="ReActForecasterSlot")


@_attrs_define
class ReActForecasterSlot:
    """
    Attributes:
        llm (LLMEnum): All LLM models (public + internal).
        variant_idx (int | Unset):  Default: 0.
        type_ (Literal['react'] | Unset):  Default: 'react'.
    """

    llm: LLMEnum
    variant_idx: int | Unset = 0
    type_: Literal["react"] | Unset = "react"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        llm = self.llm.value

        variant_idx = self.variant_idx

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "llm": llm,
            }
        )
        if variant_idx is not UNSET:
            field_dict["variant_idx"] = variant_idx
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        llm = LLMEnum(d.pop("llm"))

        variant_idx = d.pop("variant_idx", UNSET)

        type_ = cast(Literal["react"] | Unset, d.pop("type", UNSET))
        if type_ != "react" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'react', got '{type_}'")

        re_act_forecaster_slot = cls(
            llm=llm,
            variant_idx=variant_idx,
            type_=type_,
        )

        re_act_forecaster_slot.additional_properties = d
        return re_act_forecaster_slot

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

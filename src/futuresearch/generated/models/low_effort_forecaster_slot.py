from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.llm_enum import LLMEnum

T = TypeVar("T", bound="LowEffortForecasterSlot")


@_attrs_define
class LowEffortForecasterSlot:
    """One model in the LOW-effort forecaster ensemble (same shape as a
    refiner slot: a name labelling the arm + the LLM). Distinct class so a
    config blob reads as what it configures.

        Attributes:
            name (str):
            llm (LLMEnum): All LLM models (public + internal).
    """

    name: str
    llm: LLMEnum
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        llm = self.llm.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "llm": llm,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        llm = LLMEnum(d.pop("llm"))

        low_effort_forecaster_slot = cls(
            name=name,
            llm=llm,
        )

        low_effort_forecaster_slot.additional_properties = d
        return low_effort_forecaster_slot

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

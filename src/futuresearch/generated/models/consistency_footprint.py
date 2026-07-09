from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConsistencyFootprint")


@_attrs_define
class ConsistencyFootprint:
    """Overview of how a forecast was influenced by other forecasts

    Attributes:
        tied_siblings (int | Unset):  Default: 0.
        own_past (int | Unset):  Default: 0.
        public_past (int | Unset):  Default: 0.
    """

    tied_siblings: int | Unset = 0
    own_past: int | Unset = 0
    public_past: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tied_siblings = self.tied_siblings

        own_past = self.own_past

        public_past = self.public_past

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if tied_siblings is not UNSET:
            field_dict["tied_siblings"] = tied_siblings
        if own_past is not UNSET:
            field_dict["own_past"] = own_past
        if public_past is not UNSET:
            field_dict["public_past"] = public_past

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tied_siblings = d.pop("tied_siblings", UNSET)

        own_past = d.pop("own_past", UNSET)

        public_past = d.pop("public_past", UNSET)

        consistency_footprint = cls(
            tied_siblings=tied_siblings,
            own_past=own_past,
            public_past=public_past,
        )

        consistency_footprint.additional_properties = d
        return consistency_footprint

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

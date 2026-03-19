from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="BuiltInListItem")


@_attrs_define
class BuiltInListItem:
    """
    Attributes:
        name (str): Name of the built-in list
        artifact_id (UUID): Artifact ID to use with the /use endpoint
        category (str): Category for grouping lists
        fields (list[str]): Column names available in this list
    """

    name: str
    artifact_id: UUID
    category: str
    fields: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        artifact_id = str(self.artifact_id)

        category = self.category

        fields = self.fields

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "artifact_id": artifact_id,
                "category": category,
                "fields": fields,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        artifact_id = UUID(d.pop("artifact_id"))

        category = d.pop("category")

        fields = cast(list[str], d.pop("fields"))

        built_in_list_item = cls(
            name=name,
            artifact_id=artifact_id,
            category=category,
            fields=fields,
        )

        built_in_list_item.additional_properties = d
        return built_in_list_item

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.built_in_list_item import BuiltInListItem


T = TypeVar("T", bound="BuiltInListsResponse")


@_attrs_define
class BuiltInListsResponse:
    """
    Attributes:
        lists (list[BuiltInListItem]): Available built-in lists
        total (int): Total number of matching lists
    """

    lists: list[BuiltInListItem]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lists = []
        for lists_item_data in self.lists:
            lists_item = lists_item_data.to_dict()
            lists.append(lists_item)

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "lists": lists,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.built_in_list_item import BuiltInListItem

        d = dict(src_dict)
        lists = []
        _lists = d.pop("lists")
        for lists_item_data in _lists:
            lists_item = BuiltInListItem.from_dict(lists_item_data)

            lists.append(lists_item)

        total = d.pop("total")

        built_in_lists_response = cls(
            lists=lists,
            total=total,
        )

        built_in_lists_response.additional_properties = d
        return built_in_lists_response

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

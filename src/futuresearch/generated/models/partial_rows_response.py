from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.partial_rows_response_rows_item import PartialRowsResponseRowsItem


T = TypeVar("T", bound="PartialRowsResponse")


@_attrs_define
class PartialRowsResponse:
    """
    Attributes:
        rows (list[PartialRowsResponseRowsItem]): Recently completed rows (internal columns stripped)
        count (int): Number of rows returned
        cursor (None | str | Unset): Cursor for the next request (max _completed_at timestamp). Pass as completed_after.
    """

    rows: list[PartialRowsResponseRowsItem]
    count: int
    cursor: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)

        count = self.count

        cursor: None | str | Unset
        if isinstance(self.cursor, Unset):
            cursor = UNSET
        else:
            cursor = self.cursor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rows": rows,
                "count": count,
            }
        )
        if cursor is not UNSET:
            field_dict["cursor"] = cursor

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.partial_rows_response_rows_item import PartialRowsResponseRowsItem

        d = dict(src_dict)
        rows = []
        _rows = d.pop("rows")
        for rows_item_data in _rows:
            rows_item = PartialRowsResponseRowsItem.from_dict(rows_item_data)

            rows.append(rows_item)

        count = d.pop("count")

        def _parse_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cursor = _parse_cursor(d.pop("cursor", UNSET))

        partial_rows_response = cls(
            rows=rows,
            count=count,
            cursor=cursor,
        )

        partial_rows_response.additional_properties = d
        return partial_rows_response

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

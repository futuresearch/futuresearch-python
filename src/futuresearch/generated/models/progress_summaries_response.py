from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.progress_summary_entry import ProgressSummaryEntry


T = TypeVar("T", bound="ProgressSummariesResponse")


@_attrs_define
class ProgressSummariesResponse:
    """
    Attributes:
        summaries (list[ProgressSummaryEntry]): Latest summary per trace (only new entries if cursor was provided)
        cursor (None | str | Unset): Cursor for the next request (max updated_at timestamp). Pass as summary_cursor.
    """

    summaries: list[ProgressSummaryEntry]
    cursor: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        summaries = []
        for summaries_item_data in self.summaries:
            summaries_item = summaries_item_data.to_dict()
            summaries.append(summaries_item)

        cursor: None | str | Unset
        if isinstance(self.cursor, Unset):
            cursor = UNSET
        else:
            cursor = self.cursor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "summaries": summaries,
            }
        )
        if cursor is not UNSET:
            field_dict["cursor"] = cursor

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.progress_summary_entry import ProgressSummaryEntry

        d = dict(src_dict)
        summaries = []
        _summaries = d.pop("summaries")
        for summaries_item_data in _summaries:
            summaries_item = ProgressSummaryEntry.from_dict(summaries_item_data)

            summaries.append(summaries_item)

        def _parse_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cursor = _parse_cursor(d.pop("cursor", UNSET))

        progress_summaries_response = cls(
            summaries=summaries,
            cursor=cursor,
        )

        progress_summaries_response.additional_properties = d
        return progress_summaries_response

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

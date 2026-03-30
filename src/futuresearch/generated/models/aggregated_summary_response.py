from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.progress_summary_entry import ProgressSummaryEntry


T = TypeVar("T", bound="AggregatedSummaryResponse")


@_attrs_define
class AggregatedSummaryResponse:
    """
    Attributes:
        aggregate (str): Single-sentence synthesis of recent agent activity
        micro_summaries (list[ProgressSummaryEntry]): The micro-summaries that were aggregated
        cursor (None | str | Unset): Cursor for the next request (max updated_at timestamp).
    """

    aggregate: str
    micro_summaries: list[ProgressSummaryEntry]
    cursor: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aggregate = self.aggregate

        micro_summaries = []
        for micro_summaries_item_data in self.micro_summaries:
            micro_summaries_item = micro_summaries_item_data.to_dict()
            micro_summaries.append(micro_summaries_item)

        cursor: None | str | Unset
        if isinstance(self.cursor, Unset):
            cursor = UNSET
        else:
            cursor = self.cursor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aggregate": aggregate,
                "micro_summaries": micro_summaries,
            }
        )
        if cursor is not UNSET:
            field_dict["cursor"] = cursor

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.progress_summary_entry import ProgressSummaryEntry

        d = dict(src_dict)
        aggregate = d.pop("aggregate")

        micro_summaries = []
        _micro_summaries = d.pop("micro_summaries")
        for micro_summaries_item_data in _micro_summaries:
            micro_summaries_item = ProgressSummaryEntry.from_dict(micro_summaries_item_data)

            micro_summaries.append(micro_summaries_item)

        def _parse_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cursor = _parse_cursor(d.pop("cursor", UNSET))

        aggregated_summary_response = cls(
            aggregate=aggregate,
            micro_summaries=micro_summaries,
            cursor=cursor,
        )

        aggregated_summary_response.additional_properties = d
        return aggregated_summary_response

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

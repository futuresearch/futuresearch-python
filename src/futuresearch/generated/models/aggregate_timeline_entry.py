from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.progress_summary_entry import ProgressSummaryEntry


T = TypeVar("T", bound="AggregateTimelineEntry")


@_attrs_define
class AggregateTimelineEntry:
    """A single aggregate + its linked micro-summaries for the activity timeline.

    Attributes:
        aggregate_id (UUID): The stored aggregate ID
        summary (str): Aggregate summary text
        created_at (str): When this aggregate was created
        micro_summaries (list[ProgressSummaryEntry]): The micro-summaries that were aggregated
    """

    aggregate_id: UUID
    summary: str
    created_at: str
    micro_summaries: list[ProgressSummaryEntry]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aggregate_id = str(self.aggregate_id)

        summary = self.summary

        created_at = self.created_at

        micro_summaries = []
        for micro_summaries_item_data in self.micro_summaries:
            micro_summaries_item = micro_summaries_item_data.to_dict()
            micro_summaries.append(micro_summaries_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aggregate_id": aggregate_id,
                "summary": summary,
                "created_at": created_at,
                "micro_summaries": micro_summaries,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.progress_summary_entry import ProgressSummaryEntry

        d = dict(src_dict)
        aggregate_id = UUID(d.pop("aggregate_id"))

        summary = d.pop("summary")

        created_at = d.pop("created_at")

        micro_summaries = []
        _micro_summaries = d.pop("micro_summaries")
        for micro_summaries_item_data in _micro_summaries:
            micro_summaries_item = ProgressSummaryEntry.from_dict(micro_summaries_item_data)

            micro_summaries.append(micro_summaries_item)

        aggregate_timeline_entry = cls(
            aggregate_id=aggregate_id,
            summary=summary,
            created_at=created_at,
            micro_summaries=micro_summaries,
        )

        aggregate_timeline_entry.additional_properties = d
        return aggregate_timeline_entry

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

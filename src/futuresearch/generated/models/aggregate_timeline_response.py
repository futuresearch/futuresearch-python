from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.aggregate_timeline_entry import AggregateTimelineEntry


T = TypeVar("T", bound="AggregateTimelineResponse")


@_attrs_define
class AggregateTimelineResponse:
    """Full activity timeline for widget rehydration.

    Attributes:
        timeline (list[AggregateTimelineEntry]): Aggregates in chronological order, each with their micro-summaries
    """

    timeline: list[AggregateTimelineEntry]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        timeline = []
        for timeline_item_data in self.timeline:
            timeline_item = timeline_item_data.to_dict()
            timeline.append(timeline_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timeline": timeline,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aggregate_timeline_entry import AggregateTimelineEntry

        d = dict(src_dict)
        timeline = []
        _timeline = d.pop("timeline")
        for timeline_item_data in _timeline:
            timeline_item = AggregateTimelineEntry.from_dict(timeline_item_data)

            timeline.append(timeline_item)

        aggregate_timeline_response = cls(
            timeline=timeline,
        )

        aggregate_timeline_response.additional_properties = d
        return aggregate_timeline_response

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

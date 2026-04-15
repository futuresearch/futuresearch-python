from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProgressSummaryEntry")


@_attrs_define
class ProgressSummaryEntry:
    """
    Attributes:
        trace_id (UUID): The trace this summary belongs to
        task_id (UUID): The task this summary belongs to
        iteration_number (int): Iteration within the trace
        summary (str): LLM-generated progress summary text
        updated_at (str): When this summary was created
        row_indices (list[int] | Unset): Input row indices this trace covers
        row_index (int | None | Unset): Deprecated: use row_indices instead
    """

    trace_id: UUID
    task_id: UUID
    iteration_number: int
    summary: str
    updated_at: str
    row_indices: list[int] | Unset = UNSET
    row_index: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trace_id = str(self.trace_id)

        task_id = str(self.task_id)

        iteration_number = self.iteration_number

        summary = self.summary

        updated_at = self.updated_at

        row_indices: list[int] | Unset = UNSET
        if not isinstance(self.row_indices, Unset):
            row_indices = self.row_indices

        row_index: int | None | Unset
        if isinstance(self.row_index, Unset):
            row_index = UNSET
        else:
            row_index = self.row_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trace_id": trace_id,
                "task_id": task_id,
                "iteration_number": iteration_number,
                "summary": summary,
                "updated_at": updated_at,
            }
        )
        if row_indices is not UNSET:
            field_dict["row_indices"] = row_indices
        if row_index is not UNSET:
            field_dict["row_index"] = row_index

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        trace_id = UUID(d.pop("trace_id"))

        task_id = UUID(d.pop("task_id"))

        iteration_number = d.pop("iteration_number")

        summary = d.pop("summary")

        updated_at = d.pop("updated_at")

        row_indices = cast(list[int], d.pop("row_indices", UNSET))

        def _parse_row_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        row_index = _parse_row_index(d.pop("row_index", UNSET))

        progress_summary_entry = cls(
            trace_id=trace_id,
            task_id=task_id,
            iteration_number=iteration_number,
            summary=summary,
            updated_at=updated_at,
            row_indices=row_indices,
            row_index=row_index,
        )

        progress_summary_entry.additional_properties = d
        return progress_summary_entry

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

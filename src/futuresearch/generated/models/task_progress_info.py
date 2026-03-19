from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TaskProgressInfo")


@_attrs_define
class TaskProgressInfo:
    """
    Attributes:
        pending (int): Number of subtasks pending
        running (int): Number of subtasks currently running
        completed (int): Number of subtasks completed
        failed (int): Number of subtasks failed
        total (int): Total number of subtasks
    """

    pending: int
    running: int
    completed: int
    failed: int
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        pending = self.pending

        running = self.running

        completed = self.completed

        failed = self.failed

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "pending": pending,
                "running": running,
                "completed": completed,
                "failed": failed,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        pending = d.pop("pending")

        running = d.pop("running")

        completed = d.pop("completed")

        failed = d.pop("failed")

        total = d.pop("total")

        task_progress_info = cls(
            pending=pending,
            running=running,
            completed=completed,
            failed=failed,
            total=total,
        )

        task_progress_info.additional_properties = d
        return task_progress_info

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.task_cost_status import TaskCostStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="TaskCostResponse")


@_attrs_define
class TaskCostResponse:
    """
    Attributes:
        task_id (UUID): The task ID
        status (TaskCostStatus):
        cost_dollars (float | None | Unset): The amount charged to the user (null while pending)
    """

    task_id: UUID
    status: TaskCostStatus
    cost_dollars: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_id = str(self.task_id)

        status = self.status.value

        cost_dollars: float | None | Unset
        if isinstance(self.cost_dollars, Unset):
            cost_dollars = UNSET
        else:
            cost_dollars = self.cost_dollars

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_id": task_id,
                "status": status,
            }
        )
        if cost_dollars is not UNSET:
            field_dict["cost_dollars"] = cost_dollars

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_id = UUID(d.pop("task_id"))

        status = TaskCostStatus(d.pop("status"))

        def _parse_cost_dollars(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        cost_dollars = _parse_cost_dollars(d.pop("cost_dollars", UNSET))

        task_cost_response = cls(
            task_id=task_id,
            status=status,
            cost_dollars=cost_dollars,
        )

        task_cost_response.additional_properties = d
        return task_cost_response

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

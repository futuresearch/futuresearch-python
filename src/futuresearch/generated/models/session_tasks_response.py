from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.session_task_item import SessionTaskItem


T = TypeVar("T", bound="SessionTasksResponse")


@_attrs_define
class SessionTasksResponse:
    """
    Attributes:
        session_id (UUID): The session ID
        tasks (list[SessionTaskItem]): Tasks in this session
    """

    session_id: UUID
    tasks: list[SessionTaskItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        tasks = []
        for tasks_item_data in self.tasks:
            tasks_item = tasks_item_data.to_dict()
            tasks.append(tasks_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "tasks": tasks,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.session_task_item import SessionTaskItem

        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        tasks = []
        _tasks = d.pop("tasks")
        for tasks_item_data in _tasks:
            tasks_item = SessionTaskItem.from_dict(tasks_item_data)

            tasks.append(tasks_item)

        session_tasks_response = cls(
            session_id=session_id,
            tasks=tasks,
        )

        session_tasks_response.additional_properties = d
        return session_tasks_response

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

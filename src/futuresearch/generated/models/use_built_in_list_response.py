from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="UseBuiltInListResponse")


@_attrs_define
class UseBuiltInListResponse:
    """
    Attributes:
        artifact_id (UUID): New artifact ID in the user's session
        session_id (UUID): Session containing the new artifact
        task_id (UUID): Task created by the copy operation
    """

    artifact_id: UUID
    session_id: UUID
    task_id: UUID
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        artifact_id = str(self.artifact_id)

        session_id = str(self.session_id)

        task_id = str(self.task_id)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "artifact_id": artifact_id,
                "session_id": session_id,
                "task_id": task_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        artifact_id = UUID(d.pop("artifact_id"))

        session_id = UUID(d.pop("session_id"))

        task_id = UUID(d.pop("task_id"))

        use_built_in_list_response = cls(
            artifact_id=artifact_id,
            session_id=session_id,
            task_id=task_id,
        )

        use_built_in_list_response.additional_properties = d
        return use_built_in_list_response

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

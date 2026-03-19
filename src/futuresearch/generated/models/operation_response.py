from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.task_status import TaskStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="OperationResponse")


@_attrs_define
class OperationResponse:
    """
    Attributes:
        task_id (UUID): The ID of the created task
        session_id (UUID): The session ID (auto-created if not provided)
        status (TaskStatus):
        artifact_id (None | Unset | UUID): Result artifact ID (available when completed)
        error (None | str | Unset): Error message (available when failed)
    """

    task_id: UUID
    session_id: UUID
    status: TaskStatus
    artifact_id: None | Unset | UUID = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_id = str(self.task_id)

        session_id = str(self.session_id)

        status = self.status.value

        artifact_id: None | str | Unset
        if isinstance(self.artifact_id, Unset):
            artifact_id = UNSET
        elif isinstance(self.artifact_id, UUID):
            artifact_id = str(self.artifact_id)
        else:
            artifact_id = self.artifact_id

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_id": task_id,
                "session_id": session_id,
                "status": status,
            }
        )
        if artifact_id is not UNSET:
            field_dict["artifact_id"] = artifact_id
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_id = UUID(d.pop("task_id"))

        session_id = UUID(d.pop("session_id"))

        status = TaskStatus(d.pop("status"))

        def _parse_artifact_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                artifact_id_type_0 = UUID(data)

                return artifact_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        artifact_id = _parse_artifact_id(d.pop("artifact_id", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        operation_response = cls(
            task_id=task_id,
            session_id=session_id,
            status=status,
            artifact_id=artifact_id,
            error=error,
        )

        operation_response.additional_properties = d
        return operation_response

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

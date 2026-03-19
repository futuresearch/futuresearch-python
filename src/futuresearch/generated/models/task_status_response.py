from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.public_task_type import PublicTaskType
from ..models.task_status import TaskStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.task_progress_info import TaskProgressInfo


T = TypeVar("T", bound="TaskStatusResponse")


@_attrs_define
class TaskStatusResponse:
    """
    Attributes:
        task_id (UUID): The task ID
        session_id (UUID): The session this task belongs to
        status (TaskStatus):
        task_type (PublicTaskType):
        created_at (datetime.datetime | None): When the task was created
        updated_at (datetime.datetime | None): When the task was last updated
        progress (None | TaskProgressInfo): Subtask progress counts (available while task is running)
        artifact_id (None | Unset | UUID): Result artifact ID (if the task completed)
        error (None | str | Unset): Error message (if the task failed)
    """

    task_id: UUID
    session_id: UUID
    status: TaskStatus
    task_type: PublicTaskType
    created_at: datetime.datetime | None
    updated_at: datetime.datetime | None
    progress: None | TaskProgressInfo
    artifact_id: None | Unset | UUID = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.task_progress_info import TaskProgressInfo

        task_id = str(self.task_id)

        session_id = str(self.session_id)

        status = self.status.value

        task_type = self.task_type.value

        created_at: None | str
        if isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str
        if isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        progress: dict[str, Any] | None
        if isinstance(self.progress, TaskProgressInfo):
            progress = self.progress.to_dict()
        else:
            progress = self.progress

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
                "task_type": task_type,
                "created_at": created_at,
                "updated_at": updated_at,
                "progress": progress,
            }
        )
        if artifact_id is not UNSET:
            field_dict["artifact_id"] = artifact_id
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_progress_info import TaskProgressInfo

        d = dict(src_dict)
        task_id = UUID(d.pop("task_id"))

        session_id = UUID(d.pop("session_id"))

        status = TaskStatus(d.pop("status"))

        task_type = PublicTaskType(d.pop("task_type"))

        def _parse_created_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        created_at = _parse_created_at(d.pop("created_at"))

        def _parse_updated_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))

        def _parse_progress(data: object) -> None | TaskProgressInfo:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                progress_type_0 = TaskProgressInfo.from_dict(data)

                return progress_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TaskProgressInfo, data)

        progress = _parse_progress(d.pop("progress"))

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

        task_status_response = cls(
            task_id=task_id,
            session_id=session_id,
            status=status,
            task_type=task_type,
            created_at=created_at,
            updated_at=updated_at,
            progress=progress,
            artifact_id=artifact_id,
            error=error,
        )

        task_status_response.additional_properties = d
        return task_status_response

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

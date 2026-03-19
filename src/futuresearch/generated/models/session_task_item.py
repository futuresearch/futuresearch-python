from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.public_task_type import PublicTaskType
from ..models.task_status import TaskStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionTaskItem")


@_attrs_define
class SessionTaskItem:
    """
    Attributes:
        task_id (UUID): The task ID
        status (TaskStatus):
        task_type (PublicTaskType):
        created_at (datetime.datetime): When the task was created
        output_artifact_id (None | Unset | UUID): Output artifact ID
        input_artifact_ids (list[UUID] | None | Unset): Input artifact IDs
        context_artifact_ids (list[UUID] | None | Unset): Context artifact IDs (e.g. right table in merge)
    """

    task_id: UUID
    status: TaskStatus
    task_type: PublicTaskType
    created_at: datetime.datetime
    output_artifact_id: None | Unset | UUID = UNSET
    input_artifact_ids: list[UUID] | None | Unset = UNSET
    context_artifact_ids: list[UUID] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_id = str(self.task_id)

        status = self.status.value

        task_type = self.task_type.value

        created_at = self.created_at.isoformat()

        output_artifact_id: None | str | Unset
        if isinstance(self.output_artifact_id, Unset):
            output_artifact_id = UNSET
        elif isinstance(self.output_artifact_id, UUID):
            output_artifact_id = str(self.output_artifact_id)
        else:
            output_artifact_id = self.output_artifact_id

        input_artifact_ids: list[str] | None | Unset
        if isinstance(self.input_artifact_ids, Unset):
            input_artifact_ids = UNSET
        elif isinstance(self.input_artifact_ids, list):
            input_artifact_ids = []
            for input_artifact_ids_type_0_item_data in self.input_artifact_ids:
                input_artifact_ids_type_0_item = str(input_artifact_ids_type_0_item_data)
                input_artifact_ids.append(input_artifact_ids_type_0_item)

        else:
            input_artifact_ids = self.input_artifact_ids

        context_artifact_ids: list[str] | None | Unset
        if isinstance(self.context_artifact_ids, Unset):
            context_artifact_ids = UNSET
        elif isinstance(self.context_artifact_ids, list):
            context_artifact_ids = []
            for context_artifact_ids_type_0_item_data in self.context_artifact_ids:
                context_artifact_ids_type_0_item = str(context_artifact_ids_type_0_item_data)
                context_artifact_ids.append(context_artifact_ids_type_0_item)

        else:
            context_artifact_ids = self.context_artifact_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_id": task_id,
                "status": status,
                "task_type": task_type,
                "created_at": created_at,
            }
        )
        if output_artifact_id is not UNSET:
            field_dict["output_artifact_id"] = output_artifact_id
        if input_artifact_ids is not UNSET:
            field_dict["input_artifact_ids"] = input_artifact_ids
        if context_artifact_ids is not UNSET:
            field_dict["context_artifact_ids"] = context_artifact_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_id = UUID(d.pop("task_id"))

        status = TaskStatus(d.pop("status"))

        task_type = PublicTaskType(d.pop("task_type"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_output_artifact_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                output_artifact_id_type_0 = UUID(data)

                return output_artifact_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        output_artifact_id = _parse_output_artifact_id(d.pop("output_artifact_id", UNSET))

        def _parse_input_artifact_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                input_artifact_ids_type_0 = []
                _input_artifact_ids_type_0 = data
                for input_artifact_ids_type_0_item_data in _input_artifact_ids_type_0:
                    input_artifact_ids_type_0_item = UUID(input_artifact_ids_type_0_item_data)

                    input_artifact_ids_type_0.append(input_artifact_ids_type_0_item)

                return input_artifact_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        input_artifact_ids = _parse_input_artifact_ids(d.pop("input_artifact_ids", UNSET))

        def _parse_context_artifact_ids(data: object) -> list[UUID] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                context_artifact_ids_type_0 = []
                _context_artifact_ids_type_0 = data
                for context_artifact_ids_type_0_item_data in _context_artifact_ids_type_0:
                    context_artifact_ids_type_0_item = UUID(context_artifact_ids_type_0_item_data)

                    context_artifact_ids_type_0.append(context_artifact_ids_type_0_item)

                return context_artifact_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[UUID] | None | Unset, data)

        context_artifact_ids = _parse_context_artifact_ids(d.pop("context_artifact_ids", UNSET))

        session_task_item = cls(
            task_id=task_id,
            status=status,
            task_type=task_type,
            created_at=created_at,
            output_artifact_id=output_artifact_id,
            input_artifact_ids=input_artifact_ids,
            context_artifact_ids=context_artifact_ids,
        )

        session_task_item.additional_properties = d
        return session_task_item

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

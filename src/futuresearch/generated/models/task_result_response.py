from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.task_status import TaskStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.merge_breakdown_response import MergeBreakdownResponse
    from ..models.task_result_response_data_type_0_item import TaskResultResponseDataType0Item
    from ..models.task_result_response_data_type_1 import TaskResultResponseDataType1


T = TypeVar("T", bound="TaskResultResponse")


@_attrs_define
class TaskResultResponse:
    """
    Attributes:
        task_id (UUID): The task ID
        status (TaskStatus):
        artifact_id (None | Unset | UUID): Result artifact ID
        data (list[TaskResultResponseDataType0Item] | None | TaskResultResponseDataType1 | Unset): Result data: list of
            records for tables, single record for scalars, null if not completed
        error (None | str | Unset): Error message (if the task failed)
        merge_breakdown (MergeBreakdownResponse | None | Unset): Merge breakdown (only for merge tasks)
    """

    task_id: UUID
    status: TaskStatus
    artifact_id: None | Unset | UUID = UNSET
    data: list[TaskResultResponseDataType0Item] | None | TaskResultResponseDataType1 | Unset = UNSET
    error: None | str | Unset = UNSET
    merge_breakdown: MergeBreakdownResponse | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.merge_breakdown_response import MergeBreakdownResponse
        from ..models.task_result_response_data_type_1 import TaskResultResponseDataType1

        task_id = str(self.task_id)

        status = self.status.value

        artifact_id: None | str | Unset
        if isinstance(self.artifact_id, Unset):
            artifact_id = UNSET
        elif isinstance(self.artifact_id, UUID):
            artifact_id = str(self.artifact_id)
        else:
            artifact_id = self.artifact_id

        data: dict[str, Any] | list[dict[str, Any]] | None | Unset
        if isinstance(self.data, Unset):
            data = UNSET
        elif isinstance(self.data, list):
            data = []
            for data_type_0_item_data in self.data:
                data_type_0_item = data_type_0_item_data.to_dict()
                data.append(data_type_0_item)

        elif isinstance(self.data, TaskResultResponseDataType1):
            data = self.data.to_dict()
        else:
            data = self.data

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        merge_breakdown: dict[str, Any] | None | Unset
        if isinstance(self.merge_breakdown, Unset):
            merge_breakdown = UNSET
        elif isinstance(self.merge_breakdown, MergeBreakdownResponse):
            merge_breakdown = self.merge_breakdown.to_dict()
        else:
            merge_breakdown = self.merge_breakdown

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_id": task_id,
                "status": status,
            }
        )
        if artifact_id is not UNSET:
            field_dict["artifact_id"] = artifact_id
        if data is not UNSET:
            field_dict["data"] = data
        if error is not UNSET:
            field_dict["error"] = error
        if merge_breakdown is not UNSET:
            field_dict["merge_breakdown"] = merge_breakdown

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.merge_breakdown_response import MergeBreakdownResponse
        from ..models.task_result_response_data_type_0_item import TaskResultResponseDataType0Item
        from ..models.task_result_response_data_type_1 import TaskResultResponseDataType1

        d = dict(src_dict)
        task_id = UUID(d.pop("task_id"))

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

        def _parse_data(
            data: object,
        ) -> list[TaskResultResponseDataType0Item] | None | TaskResultResponseDataType1 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                data_type_0 = []
                _data_type_0 = data
                for data_type_0_item_data in _data_type_0:
                    data_type_0_item = TaskResultResponseDataType0Item.from_dict(data_type_0_item_data)

                    data_type_0.append(data_type_0_item)

                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_1 = TaskResultResponseDataType1.from_dict(data)

                return data_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[TaskResultResponseDataType0Item] | None | TaskResultResponseDataType1 | Unset, data)

        data = _parse_data(d.pop("data", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        def _parse_merge_breakdown(data: object) -> MergeBreakdownResponse | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                merge_breakdown_type_0 = MergeBreakdownResponse.from_dict(data)

                return merge_breakdown_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MergeBreakdownResponse | None | Unset, data)

        merge_breakdown = _parse_merge_breakdown(d.pop("merge_breakdown", UNSET))

        task_result_response = cls(
            task_id=task_id,
            status=status,
            artifact_id=artifact_id,
            data=data,
            error=error,
            merge_breakdown=merge_breakdown,
        )

        task_result_response.additional_properties = d
        return task_result_response

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

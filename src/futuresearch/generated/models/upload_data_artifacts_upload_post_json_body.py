from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.upload_data_artifacts_upload_post_json_body_data_type_0_item import (
        UploadDataArtifactsUploadPostJsonBodyDataType0Item,
    )
    from ..models.upload_data_artifacts_upload_post_json_body_data_type_1 import (
        UploadDataArtifactsUploadPostJsonBodyDataType1,
    )


T = TypeVar("T", bound="UploadDataArtifactsUploadPostJsonBody")


@_attrs_define
class UploadDataArtifactsUploadPostJsonBody:
    """
    Attributes:
        data (list[UploadDataArtifactsUploadPostJsonBodyDataType0Item] |
            UploadDataArtifactsUploadPostJsonBodyDataType1): List of row objects (table) or a single object (scalar)
        session_id (UUID | Unset): Optional session ID. Auto-created if omitted.
    """

    data: list[UploadDataArtifactsUploadPostJsonBodyDataType0Item] | UploadDataArtifactsUploadPostJsonBodyDataType1
    session_id: UUID | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] | list[dict[str, Any]]
        if isinstance(self.data, list):
            data = []
            for data_type_0_item_data in self.data:
                data_type_0_item = data_type_0_item_data.to_dict()
                data.append(data_type_0_item)

        else:
            data = self.data.to_dict()

        session_id: str | Unset = UNSET
        if not isinstance(self.session_id, Unset):
            session_id = str(self.session_id)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.upload_data_artifacts_upload_post_json_body_data_type_0_item import (
            UploadDataArtifactsUploadPostJsonBodyDataType0Item,
        )
        from ..models.upload_data_artifacts_upload_post_json_body_data_type_1 import (
            UploadDataArtifactsUploadPostJsonBodyDataType1,
        )

        d = dict(src_dict)

        def _parse_data(
            data: object,
        ) -> list[UploadDataArtifactsUploadPostJsonBodyDataType0Item] | UploadDataArtifactsUploadPostJsonBodyDataType1:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                data_type_0 = []
                _data_type_0 = data
                for data_type_0_item_data in _data_type_0:
                    data_type_0_item = UploadDataArtifactsUploadPostJsonBodyDataType0Item.from_dict(
                        data_type_0_item_data
                    )

                    data_type_0.append(data_type_0_item)

                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            data_type_1 = UploadDataArtifactsUploadPostJsonBodyDataType1.from_dict(data)

            return data_type_1

        data = _parse_data(d.pop("data"))

        _session_id = d.pop("session_id", UNSET)
        session_id: UUID | Unset
        if isinstance(_session_id, Unset):
            session_id = UNSET
        else:
            session_id = UUID(_session_id)

        upload_data_artifacts_upload_post_json_body = cls(
            data=data,
            session_id=session_id,
        )

        upload_data_artifacts_upload_post_json_body.additional_properties = d
        return upload_data_artifacts_upload_post_json_body

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

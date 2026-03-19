from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="UploadCompleteResponse")


@_attrs_define
class UploadCompleteResponse:
    """
    Attributes:
        artifact_id (UUID): The ID of the created group artifact
        session_id (UUID): The session ID
        rows (int): Number of data rows in the uploaded CSV
        columns (list[str]): Column names from the CSV header
        size_bytes (int): Size of the uploaded file in bytes
    """

    artifact_id: UUID
    session_id: UUID
    rows: int
    columns: list[str]
    size_bytes: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        artifact_id = str(self.artifact_id)

        session_id = str(self.session_id)

        rows = self.rows

        columns = self.columns

        size_bytes = self.size_bytes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "artifact_id": artifact_id,
                "session_id": session_id,
                "rows": rows,
                "columns": columns,
                "size_bytes": size_bytes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        artifact_id = UUID(d.pop("artifact_id"))

        session_id = UUID(d.pop("session_id"))

        rows = d.pop("rows")

        columns = cast(list[str], d.pop("columns"))

        size_bytes = d.pop("size_bytes")

        upload_complete_response = cls(
            artifact_id=artifact_id,
            session_id=session_id,
            rows=rows,
            columns=columns,
            size_bytes=size_bytes,
        )

        upload_complete_response.additional_properties = d
        return upload_complete_response

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

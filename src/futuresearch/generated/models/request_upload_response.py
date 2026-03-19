from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RequestUploadResponse")


@_attrs_define
class RequestUploadResponse:
    """
    Attributes:
        upload_url (str): Presigned URL to PUT the CSV file to
        upload_id (UUID): Unique identifier for this upload
        expires_in (int): Seconds until the upload URL expires
        max_size_bytes (int): Maximum file size in bytes
        curl_command (str): Ready-to-use curl command for uploading the file
    """

    upload_url: str
    upload_id: UUID
    expires_in: int
    max_size_bytes: int
    curl_command: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        upload_url = self.upload_url

        upload_id = str(self.upload_id)

        expires_in = self.expires_in

        max_size_bytes = self.max_size_bytes

        curl_command = self.curl_command

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "upload_url": upload_url,
                "upload_id": upload_id,
                "expires_in": expires_in,
                "max_size_bytes": max_size_bytes,
                "curl_command": curl_command,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        upload_url = d.pop("upload_url")

        upload_id = UUID(d.pop("upload_id"))

        expires_in = d.pop("expires_in")

        max_size_bytes = d.pop("max_size_bytes")

        curl_command = d.pop("curl_command")

        request_upload_response = cls(
            upload_url=upload_url,
            upload_id=upload_id,
            expires_in=expires_in,
            max_size_bytes=max_size_bytes,
            curl_command=curl_command,
        )

        request_upload_response.additional_properties = d
        return request_upload_response

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from .session_list_item import SessionListItem

T = TypeVar("T", bound="SessionListResponse")


@_attrs_define
class SessionListResponse:
    """
    Attributes:
        sessions (list['SessionListItem']): The list of sessions
    """

    sessions: list[SessionListItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sessions = [s.to_dict() for s in self.sessions]

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sessions": sessions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from .session_list_item import SessionListItem

        d = dict(src_dict)
        sessions = [SessionListItem.from_dict(s) for s in d.pop("sessions")]

        session_list_response = cls(
            sessions=sessions,
        )

        session_list_response.additional_properties = d
        return session_list_response

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

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionListItem")


@_attrs_define
class SessionListItem:
    """
    Attributes:
        session_id (UUID): The session ID
        name (str): Name of the session
        created_at (datetime.datetime): When the session was created
        updated_at (datetime.datetime): When the session was last updated
        owner_account_id (None | str | Unset): Owner account ID
        cc_conversation_id (None | Unset | UUID): Linked everyrow-cc conversation ID
    """

    session_id: UUID
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    owner_account_id: None | str | Unset = UNSET
    cc_conversation_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        name = self.name

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        owner_account_id: None | str | Unset
        if isinstance(self.owner_account_id, Unset):
            owner_account_id = UNSET
        else:
            owner_account_id = self.owner_account_id

        cc_conversation_id: None | str | Unset
        if isinstance(self.cc_conversation_id, Unset):
            cc_conversation_id = UNSET
        elif isinstance(self.cc_conversation_id, UUID):
            cc_conversation_id = str(self.cc_conversation_id)
        else:
            cc_conversation_id = self.cc_conversation_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "name": name,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if owner_account_id is not UNSET:
            field_dict["owner_account_id"] = owner_account_id
        if cc_conversation_id is not UNSET:
            field_dict["cc_conversation_id"] = cc_conversation_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        name = d.pop("name")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_owner_account_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        owner_account_id = _parse_owner_account_id(d.pop("owner_account_id", UNSET))

        def _parse_cc_conversation_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                cc_conversation_id_type_0 = UUID(data)

                return cc_conversation_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        cc_conversation_id = _parse_cc_conversation_id(d.pop("cc_conversation_id", UNSET))

        session_list_item = cls(
            session_id=session_id,
            name=name,
            created_at=created_at,
            updated_at=updated_at,
            owner_account_id=owner_account_id,
            cc_conversation_id=cc_conversation_id,
        )

        session_list_item.additional_properties = d
        return session_list_item

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

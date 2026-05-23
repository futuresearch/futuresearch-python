from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.user_base_auth_method import UserBaseAuthMethod

T = TypeVar("T", bound="UserBase")


@_attrs_define
class UserBase:
    """Base user model with essential user information.

    Attributes:
        id (str):
        email (None | str):
        disabled (bool):
        auth_method (UserBaseAuthMethod):
        is_admin (bool):
        account_id (str):
    """

    id: str
    email: None | str
    disabled: bool
    auth_method: UserBaseAuthMethod
    is_admin: bool
    account_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        email: None | str
        email = self.email

        disabled = self.disabled

        auth_method = self.auth_method.value

        is_admin = self.is_admin

        account_id = self.account_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "email": email,
                "disabled": disabled,
                "auth_method": auth_method,
                "is_admin": is_admin,
                "account_id": account_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_email(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        email = _parse_email(d.pop("email"))

        disabled = d.pop("disabled")

        auth_method = UserBaseAuthMethod(d.pop("auth_method"))

        is_admin = d.pop("is_admin")

        account_id = d.pop("account_id")

        user_base = cls(
            id=id,
            email=email,
            disabled=disabled,
            auth_method=auth_method,
            is_admin=is_admin,
            account_id=account_id,
        )

        user_base.additional_properties = d
        return user_base

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

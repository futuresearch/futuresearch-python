from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.account_info import AccountInfo
    from ..models.user_base import UserBase


T = TypeVar("T", bound="WhoamiResponse")


@_attrs_define
class WhoamiResponse:
    """
    Attributes:
        user (UserBase): Base user model with essential user information.
        accounts (list[AccountInfo]):
    """

    user: UserBase
    accounts: list[AccountInfo]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user = self.user.to_dict()

        accounts = []
        for accounts_item_data in self.accounts:
            accounts_item = accounts_item_data.to_dict()
            accounts.append(accounts_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user": user,
                "accounts": accounts,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_info import AccountInfo
        from ..models.user_base import UserBase

        d = dict(src_dict)
        user = UserBase.from_dict(d.pop("user"))

        accounts = []
        _accounts = d.pop("accounts")
        for accounts_item_data in _accounts:
            accounts_item = AccountInfo.from_dict(accounts_item_data)

            accounts.append(accounts_item)

        whoami_response = cls(
            user=user,
            accounts=accounts,
        )

        whoami_response.additional_properties = d
        return whoami_response

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

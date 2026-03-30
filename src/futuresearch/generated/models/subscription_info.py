from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SubscriptionInfo")


@_attrs_define
class SubscriptionInfo:
    """
    Attributes:
        id (str):
        status (str):
        stripe_price_id (str):
        period_ends_at (str):
    """

    id: str
    status: str
    stripe_price_id: str
    period_ends_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        status = self.status

        stripe_price_id = self.stripe_price_id

        period_ends_at = self.period_ends_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "status": status,
                "stripe_price_id": stripe_price_id,
                "period_ends_at": period_ends_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        status = d.pop("status")

        stripe_price_id = d.pop("stripe_price_id")

        period_ends_at = d.pop("period_ends_at")

        subscription_info = cls(
            id=id,
            status=status,
            stripe_price_id=stripe_price_id,
            period_ends_at=period_ends_at,
        )

        subscription_info.additional_properties = d
        return subscription_info

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

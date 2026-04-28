from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.billing_tier import BillingTier
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.subscription_info import SubscriptionInfo


T = TypeVar("T", bound="SubscriptionStatusResponse")


@_attrs_define
class SubscriptionStatusResponse:
    """
    Attributes:
        tier (BillingTier):
        subscription (None | SubscriptionInfo):
        expires_at (None | str | Unset):
    """

    tier: BillingTier
    subscription: None | SubscriptionInfo
    expires_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.subscription_info import SubscriptionInfo

        tier = self.tier.value

        subscription: dict[str, Any] | None
        if isinstance(self.subscription, SubscriptionInfo):
            subscription = self.subscription.to_dict()
        else:
            subscription = self.subscription

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        else:
            expires_at = self.expires_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tier": tier,
                "subscription": subscription,
            }
        )
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subscription_info import SubscriptionInfo

        d = dict(src_dict)
        tier = BillingTier(d.pop("tier"))

        def _parse_subscription(data: object) -> None | SubscriptionInfo:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                subscription_type_0 = SubscriptionInfo.from_dict(data)

                return subscription_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SubscriptionInfo, data)

        subscription = _parse_subscription(d.pop("subscription"))

        def _parse_expires_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        subscription_status_response = cls(
            tier=tier,
            subscription=subscription,
            expires_at=expires_at,
        )

        subscription_status_response.additional_properties = d
        return subscription_status_response

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="InsufficientBalanceResponse")


@_attrs_define
class InsufficientBalanceResponse:
    """
    Attributes:
        message (str): Human-readable error message
        current_balance_dollars (float): Current balance in dollars
        minimum_required_dollars (float): Minimum required balance in dollars for the task
        error (str | Unset):  Default: 'INSUFFICIENT_BALANCE'.
    """

    message: str
    current_balance_dollars: float
    minimum_required_dollars: float
    error: str | Unset = "INSUFFICIENT_BALANCE"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        current_balance_dollars = self.current_balance_dollars

        minimum_required_dollars = self.minimum_required_dollars

        error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "current_balance_dollars": current_balance_dollars,
                "minimum_required_dollars": minimum_required_dollars,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        current_balance_dollars = d.pop("current_balance_dollars")

        minimum_required_dollars = d.pop("minimum_required_dollars")

        error = d.pop("error", UNSET)

        insufficient_balance_response = cls(
            message=message,
            current_balance_dollars=current_balance_dollars,
            minimum_required_dollars=minimum_required_dollars,
            error=error,
        )

        insufficient_balance_response.additional_properties = d
        return insufficient_balance_response

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

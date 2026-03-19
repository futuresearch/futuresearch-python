from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MergeBreakdownResponse")


@_attrs_define
class MergeBreakdownResponse:
    """Breakdown of match methods for a merge operation.

    Attributes:
        exact (list[list[int]] | Unset): Pairs matched via exact string match (left_idx, right_idx)
        fuzzy (list[list[int]] | Unset): Pairs matched via fuzzy string match (left_idx, right_idx)
        llm (list[list[int]] | Unset): Pairs matched via LLM (left_idx, right_idx)
        web (list[list[int]] | Unset): Pairs matched via LLM with web research (left_idx, right_idx)
        unmatched_left (list[int] | Unset): Left row indices that had no match
        unmatched_right (list[int] | Unset): Right row indices that had no match
    """

    exact: list[list[int]] | Unset = UNSET
    fuzzy: list[list[int]] | Unset = UNSET
    llm: list[list[int]] | Unset = UNSET
    web: list[list[int]] | Unset = UNSET
    unmatched_left: list[int] | Unset = UNSET
    unmatched_right: list[int] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        exact: list[list[int]] | Unset = UNSET
        if not isinstance(self.exact, Unset):
            exact = []
            for exact_item_data in self.exact:
                exact_item = []
                for exact_item_item_data in exact_item_data:
                    exact_item_item: int
                    exact_item_item = exact_item_item_data
                    exact_item.append(exact_item_item)

                exact.append(exact_item)

        fuzzy: list[list[int]] | Unset = UNSET
        if not isinstance(self.fuzzy, Unset):
            fuzzy = []
            for fuzzy_item_data in self.fuzzy:
                fuzzy_item = []
                for fuzzy_item_item_data in fuzzy_item_data:
                    fuzzy_item_item: int
                    fuzzy_item_item = fuzzy_item_item_data
                    fuzzy_item.append(fuzzy_item_item)

                fuzzy.append(fuzzy_item)

        llm: list[list[int]] | Unset = UNSET
        if not isinstance(self.llm, Unset):
            llm = []
            for llm_item_data in self.llm:
                llm_item = []
                for llm_item_item_data in llm_item_data:
                    llm_item_item: int
                    llm_item_item = llm_item_item_data
                    llm_item.append(llm_item_item)

                llm.append(llm_item)

        web: list[list[int]] | Unset = UNSET
        if not isinstance(self.web, Unset):
            web = []
            for web_item_data in self.web:
                web_item = []
                for web_item_item_data in web_item_data:
                    web_item_item: int
                    web_item_item = web_item_item_data
                    web_item.append(web_item_item)

                web.append(web_item)

        unmatched_left: list[int] | Unset = UNSET
        if not isinstance(self.unmatched_left, Unset):
            unmatched_left = self.unmatched_left

        unmatched_right: list[int] | Unset = UNSET
        if not isinstance(self.unmatched_right, Unset):
            unmatched_right = self.unmatched_right

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if exact is not UNSET:
            field_dict["exact"] = exact
        if fuzzy is not UNSET:
            field_dict["fuzzy"] = fuzzy
        if llm is not UNSET:
            field_dict["llm"] = llm
        if web is not UNSET:
            field_dict["web"] = web
        if unmatched_left is not UNSET:
            field_dict["unmatched_left"] = unmatched_left
        if unmatched_right is not UNSET:
            field_dict["unmatched_right"] = unmatched_right

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _exact = d.pop("exact", UNSET)
        exact: list[list[int]] | Unset = UNSET
        if _exact is not UNSET:
            exact = []
            for exact_item_data in _exact:
                exact_item = []
                _exact_item = exact_item_data
                for exact_item_item_data in _exact_item:

                    def _parse_exact_item_item(data: object) -> int:
                        return cast(int, data)

                    exact_item_item = _parse_exact_item_item(exact_item_item_data)

                    exact_item.append(exact_item_item)

                exact.append(exact_item)

        _fuzzy = d.pop("fuzzy", UNSET)
        fuzzy: list[list[int]] | Unset = UNSET
        if _fuzzy is not UNSET:
            fuzzy = []
            for fuzzy_item_data in _fuzzy:
                fuzzy_item = []
                _fuzzy_item = fuzzy_item_data
                for fuzzy_item_item_data in _fuzzy_item:

                    def _parse_fuzzy_item_item(data: object) -> int:
                        return cast(int, data)

                    fuzzy_item_item = _parse_fuzzy_item_item(fuzzy_item_item_data)

                    fuzzy_item.append(fuzzy_item_item)

                fuzzy.append(fuzzy_item)

        _llm = d.pop("llm", UNSET)
        llm: list[list[int]] | Unset = UNSET
        if _llm is not UNSET:
            llm = []
            for llm_item_data in _llm:
                llm_item = []
                _llm_item = llm_item_data
                for llm_item_item_data in _llm_item:

                    def _parse_llm_item_item(data: object) -> int:
                        return cast(int, data)

                    llm_item_item = _parse_llm_item_item(llm_item_item_data)

                    llm_item.append(llm_item_item)

                llm.append(llm_item)

        _web = d.pop("web", UNSET)
        web: list[list[int]] | Unset = UNSET
        if _web is not UNSET:
            web = []
            for web_item_data in _web:
                web_item = []
                _web_item = web_item_data
                for web_item_item_data in _web_item:

                    def _parse_web_item_item(data: object) -> int:
                        return cast(int, data)

                    web_item_item = _parse_web_item_item(web_item_item_data)

                    web_item.append(web_item_item)

                web.append(web_item)

        unmatched_left = cast(list[int], d.pop("unmatched_left", UNSET))

        unmatched_right = cast(list[int], d.pop("unmatched_right", UNSET))

        merge_breakdown_response = cls(
            exact=exact,
            fuzzy=fuzzy,
            llm=llm,
            web=web,
            unmatched_left=unmatched_left,
            unmatched_right=unmatched_right,
        )

        merge_breakdown_response.additional_properties = d
        return merge_breakdown_response

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

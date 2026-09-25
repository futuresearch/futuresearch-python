from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PaginatedPageReader")


@_attrs_define
class PaginatedPageReader:
    """
    Attributes:
        type_ (Literal['paginated'] | Unset):  Default: 'paginated'.
        page_size_chars (int | Unset): Characters per page of the READ_PAGE tool. Default: 50000.
        include_links (bool | Unset): List the page's links in <links> tags on page 1. Default: True.
    """

    type_: Literal["paginated"] | Unset = "paginated"
    page_size_chars: int | Unset = 50000
    include_links: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        page_size_chars = self.page_size_chars

        include_links = self.include_links

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if page_size_chars is not UNSET:
            field_dict["page_size_chars"] = page_size_chars
        if include_links is not UNSET:
            field_dict["include_links"] = include_links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["paginated"] | Unset, d.pop("type", UNSET))
        if type_ != "paginated" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'paginated', got '{type_}'")

        page_size_chars = d.pop("page_size_chars", UNSET)

        include_links = d.pop("include_links", UNSET)

        paginated_page_reader = cls(
            type_=type_,
            page_size_chars=page_size_chars,
            include_links=include_links,
        )

        return paginated_page_reader

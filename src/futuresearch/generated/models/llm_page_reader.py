from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..models.llm_enum_public import LLMEnumPublic
from ..types import UNSET, Unset

T = TypeVar("T", bound="LlmPageReader")


@_attrs_define
class LlmPageReader:
    """
    Attributes:
        type_ (Literal['llm'] | Unset):  Default: 'llm'.
        model (LLMEnumPublic | None | Unset): LLM that reads pages and answers the agent's query about them. If not
            provided, the system default.
    """

    type_: Literal["llm"] | Unset = "llm"
    model: LLMEnumPublic | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        elif isinstance(self.model, LLMEnumPublic):
            model = self.model.value
        else:
            model = self.model

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if model is not UNSET:
            field_dict["model"] = model

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = cast(Literal["llm"] | Unset, d.pop("type", UNSET))
        if type_ != "llm" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'llm', got '{type_}'")

        def _parse_model(data: object) -> LLMEnumPublic | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                model_type_0 = LLMEnumPublic(data)

                return model_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LLMEnumPublic | None | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        llm_page_reader = cls(
            type_=type_,
            model=model,
        )

        return llm_page_reader

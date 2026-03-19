from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.rank_operation_input_type_1_item import RankOperationInputType1Item
    from ..models.rank_operation_input_type_2 import RankOperationInputType2
    from ..models.rank_operation_response_schema_type_0 import RankOperationResponseSchemaType0


T = TypeVar("T", bound="RankOperation")


@_attrs_define
class RankOperation:
    """
    Attributes:
        input_ (list[RankOperationInputType1Item] | RankOperationInputType2 | UUID): The input data as a) the ID of an
            existing artifact, b) a single record in the form of a JSON object, or c) a table of records in the form of a
            list of JSON objects
        task (str): Instructions for the AI to score each row
        sort_by (str): Field name from response_schema to sort results by
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        webhook_url (None | str | Unset): Optional URL to receive a POST callback when the task completes or fails.
        response_schema (None | RankOperationResponseSchemaType0 | Unset): JSON Schema for the response. Must include
            the field specified in sort_by.
        ascending (bool | Unset): Sort order: True for ascending, False for descending Default: True.
    """

    input_: list[RankOperationInputType1Item] | RankOperationInputType2 | UUID
    task: str
    sort_by: str
    session_id: None | Unset | UUID = UNSET
    webhook_url: None | str | Unset = UNSET
    response_schema: None | RankOperationResponseSchemaType0 | Unset = UNSET
    ascending: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.rank_operation_response_schema_type_0 import RankOperationResponseSchemaType0

        input_: dict[str, Any] | list[dict[str, Any]] | str
        if isinstance(self.input_, UUID):
            input_ = str(self.input_)
        elif isinstance(self.input_, list):
            input_ = []
            for input_type_1_item_data in self.input_:
                input_type_1_item = input_type_1_item_data.to_dict()
                input_.append(input_type_1_item)

        else:
            input_ = self.input_.to_dict()

        task = self.task

        sort_by = self.sort_by

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        elif isinstance(self.session_id, UUID):
            session_id = str(self.session_id)
        else:
            session_id = self.session_id

        webhook_url: None | str | Unset
        if isinstance(self.webhook_url, Unset):
            webhook_url = UNSET
        else:
            webhook_url = self.webhook_url

        response_schema: dict[str, Any] | None | Unset
        if isinstance(self.response_schema, Unset):
            response_schema = UNSET
        elif isinstance(self.response_schema, RankOperationResponseSchemaType0):
            response_schema = self.response_schema.to_dict()
        else:
            response_schema = self.response_schema

        ascending = self.ascending

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input": input_,
                "task": task,
                "sort_by": sort_by,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if webhook_url is not UNSET:
            field_dict["webhook_url"] = webhook_url
        if response_schema is not UNSET:
            field_dict["response_schema"] = response_schema
        if ascending is not UNSET:
            field_dict["ascending"] = ascending

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rank_operation_input_type_1_item import RankOperationInputType1Item
        from ..models.rank_operation_input_type_2 import RankOperationInputType2
        from ..models.rank_operation_response_schema_type_0 import RankOperationResponseSchemaType0

        d = dict(src_dict)

        def _parse_input_(data: object) -> list[RankOperationInputType1Item] | RankOperationInputType2 | UUID:
            try:
                if not isinstance(data, str):
                    raise TypeError()
                input_type_0 = UUID(data)

                return input_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                input_type_1 = []
                _input_type_1 = data
                for input_type_1_item_data in _input_type_1:
                    input_type_1_item = RankOperationInputType1Item.from_dict(input_type_1_item_data)

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            input_type_2 = RankOperationInputType2.from_dict(data)

            return input_type_2

        input_ = _parse_input_(d.pop("input"))

        task = d.pop("task")

        sort_by = d.pop("sort_by")

        def _parse_session_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                session_id_type_0 = UUID(data)

                return session_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        webhook_url = _parse_webhook_url(d.pop("webhook_url", UNSET))

        def _parse_response_schema(data: object) -> None | RankOperationResponseSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = RankOperationResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RankOperationResponseSchemaType0 | Unset, data)

        response_schema = _parse_response_schema(d.pop("response_schema", UNSET))

        ascending = d.pop("ascending", UNSET)

        rank_operation = cls(
            input_=input_,
            task=task,
            sort_by=sort_by,
            session_id=session_id,
            webhook_url=webhook_url,
            response_schema=response_schema,
            ascending=ascending,
        )

        rank_operation.additional_properties = d
        return rank_operation

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

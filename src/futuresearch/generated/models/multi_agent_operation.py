from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.public_effort_level import PublicEffortLevel
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.multi_agent_operation_input_type_1_item import MultiAgentOperationInputType1Item
    from ..models.multi_agent_operation_input_type_2 import MultiAgentOperationInputType2
    from ..models.multi_agent_operation_response_schema_type_0 import MultiAgentOperationResponseSchemaType0


T = TypeVar("T", bound="MultiAgentOperation")


@_attrs_define
class MultiAgentOperation:
    """
    Attributes:
        input_ (list[MultiAgentOperationInputType1Item] | MultiAgentOperationInputType2 | UUID): The input data as a)
            the ID of an existing artifact, b) a single record in the form of a JSON object, or c) a table of records in the
            form of a list of JSON objects
        task (str): Instructions for the multi-agent parallel research. Each row in the input will be processed by
            multiple agents exploring different research angles, then synthesized into a single result.
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        webhook_url (None | str | Unset): Optional URL to receive a POST callback when the task completes or fails.
        directions (list[str] | None | Unset): Up to 6 explicit research directions/angles. Each direction becomes a
            self-contained prompt for a research agent. If not provided, directions are auto-generated based on
            effort_level.
        response_schema (MultiAgentOperationResponseSchemaType0 | None | Unset): JSON Schema for the synthesized
            response. If not provided, defaults to a simple {answer: string} schema.
        effort_level (None | PublicEffortLevel | Unset): Controls the number of parallel direction agents: low (3
            agents), medium (4 agents), high (6 agents). Default: PublicEffortLevel.MEDIUM.
        join_with_input (bool | Unset): If True, merge the synthesized output with the input row. Default: True.
    """

    input_: list[MultiAgentOperationInputType1Item] | MultiAgentOperationInputType2 | UUID
    task: str
    session_id: None | Unset | UUID = UNSET
    webhook_url: None | str | Unset = UNSET
    directions: list[str] | None | Unset = UNSET
    response_schema: MultiAgentOperationResponseSchemaType0 | None | Unset = UNSET
    effort_level: None | PublicEffortLevel | Unset = PublicEffortLevel.MEDIUM
    join_with_input: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.multi_agent_operation_response_schema_type_0 import MultiAgentOperationResponseSchemaType0

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

        directions: list[str] | None | Unset
        if isinstance(self.directions, Unset):
            directions = UNSET
        elif isinstance(self.directions, list):
            directions = self.directions

        else:
            directions = self.directions

        response_schema: dict[str, Any] | None | Unset
        if isinstance(self.response_schema, Unset):
            response_schema = UNSET
        elif isinstance(self.response_schema, MultiAgentOperationResponseSchemaType0):
            response_schema = self.response_schema.to_dict()
        else:
            response_schema = self.response_schema

        effort_level: None | str | Unset
        if isinstance(self.effort_level, Unset):
            effort_level = UNSET
        elif isinstance(self.effort_level, PublicEffortLevel):
            effort_level = self.effort_level.value
        else:
            effort_level = self.effort_level

        join_with_input = self.join_with_input

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input": input_,
                "task": task,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if webhook_url is not UNSET:
            field_dict["webhook_url"] = webhook_url
        if directions is not UNSET:
            field_dict["directions"] = directions
        if response_schema is not UNSET:
            field_dict["response_schema"] = response_schema
        if effort_level is not UNSET:
            field_dict["effort_level"] = effort_level
        if join_with_input is not UNSET:
            field_dict["join_with_input"] = join_with_input

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.multi_agent_operation_input_type_1_item import MultiAgentOperationInputType1Item
        from ..models.multi_agent_operation_input_type_2 import MultiAgentOperationInputType2
        from ..models.multi_agent_operation_response_schema_type_0 import MultiAgentOperationResponseSchemaType0

        d = dict(src_dict)

        def _parse_input_(
            data: object,
        ) -> list[MultiAgentOperationInputType1Item] | MultiAgentOperationInputType2 | UUID:
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
                    input_type_1_item = MultiAgentOperationInputType1Item.from_dict(input_type_1_item_data)

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            input_type_2 = MultiAgentOperationInputType2.from_dict(data)

            return input_type_2

        input_ = _parse_input_(d.pop("input"))

        task = d.pop("task")

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

        def _parse_directions(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                directions_type_0 = cast(list[str], data)

                return directions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        directions = _parse_directions(d.pop("directions", UNSET))

        def _parse_response_schema(data: object) -> MultiAgentOperationResponseSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = MultiAgentOperationResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MultiAgentOperationResponseSchemaType0 | None | Unset, data)

        response_schema = _parse_response_schema(d.pop("response_schema", UNSET))

        def _parse_effort_level(data: object) -> None | PublicEffortLevel | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                effort_level_type_0 = PublicEffortLevel(data)

                return effort_level_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PublicEffortLevel | Unset, data)

        effort_level = _parse_effort_level(d.pop("effort_level", UNSET))

        join_with_input = d.pop("join_with_input", UNSET)

        multi_agent_operation = cls(
            input_=input_,
            task=task,
            session_id=session_id,
            webhook_url=webhook_url,
            directions=directions,
            response_schema=response_schema,
            effort_level=effort_level,
            join_with_input=join_with_input,
        )

        multi_agent_operation.additional_properties = d
        return multi_agent_operation

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

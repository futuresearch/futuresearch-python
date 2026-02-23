from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.llm_enum_public import LLMEnumPublic
from ..models.public_effort_level import PublicEffortLevel
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.single_agent_operation_input_type_1_item import SingleAgentOperationInputType1Item
    from ..models.single_agent_operation_input_type_2 import SingleAgentOperationInputType2
    from ..models.single_agent_operation_response_schema_type_0 import SingleAgentOperationResponseSchemaType0


T = TypeVar("T", bound="SingleAgentOperation")


@_attrs_define
class SingleAgentOperation:
    """
    Attributes:
        input_ (list[SingleAgentOperationInputType1Item] | SingleAgentOperationInputType2 | UUID): The input data as a)
            the ID of an existing artifact, b) a single record in the form of a JSON object, or c) a table of records in the
            form of a list of JSON objects
        task (str): Instructions for the AI agent
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        response_schema (None | SingleAgentOperationResponseSchemaType0 | Unset): JSON Schema for the response format.
            If not provided, use default answer schema.
        llm (LLMEnumPublic | None | Unset): LLM to use for the agent. Required when effort_level is not set.
        effort_level (None | PublicEffortLevel | Unset): Effort level preset: low (quick), medium (balanced), high
            (thorough). Mutually exclusive with llm/iteration_budget/include_reasoning - use either a preset or custom
            params, not both. If not specified, you must provide all individual parameters (llm, iteration_budget,
            include_reasoning).
        return_list (bool | Unset): If True, treat the output as a list of responses instead of a single response.
            Default: True.
        iteration_budget (int | None | Unset): Number of agent iterations (0-20). Required when effort_level is not set.
        include_reasoning (bool | None | Unset): Include reasoning notes in the response. Required when effort_level is
            not set.
        include_research (bool | None | Unset): Deprecated: use include_reasoning instead. Include research notes in the
            response. Required when effort_level is not set.
    """

    input_: list[SingleAgentOperationInputType1Item] | SingleAgentOperationInputType2 | UUID
    task: str
    session_id: None | Unset | UUID = UNSET
    response_schema: None | SingleAgentOperationResponseSchemaType0 | Unset = UNSET
    llm: LLMEnumPublic | None | Unset = UNSET
    effort_level: None | PublicEffortLevel | Unset = UNSET
    return_list: bool | Unset = True
    iteration_budget: int | None | Unset = UNSET
    include_reasoning: bool | None | Unset = UNSET
    include_research: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.single_agent_operation_response_schema_type_0 import SingleAgentOperationResponseSchemaType0

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

        response_schema: dict[str, Any] | None | Unset
        if isinstance(self.response_schema, Unset):
            response_schema = UNSET
        elif isinstance(self.response_schema, SingleAgentOperationResponseSchemaType0):
            response_schema = self.response_schema.to_dict()
        else:
            response_schema = self.response_schema

        llm: None | str | Unset
        if isinstance(self.llm, Unset):
            llm = UNSET
        elif isinstance(self.llm, LLMEnumPublic):
            llm = self.llm.value
        else:
            llm = self.llm

        effort_level: None | str | Unset
        if isinstance(self.effort_level, Unset):
            effort_level = UNSET
        elif isinstance(self.effort_level, PublicEffortLevel):
            effort_level = self.effort_level.value
        else:
            effort_level = self.effort_level

        return_list = self.return_list

        iteration_budget: int | None | Unset
        if isinstance(self.iteration_budget, Unset):
            iteration_budget = UNSET
        else:
            iteration_budget = self.iteration_budget

        include_reasoning: bool | None | Unset
        if isinstance(self.include_reasoning, Unset):
            include_reasoning = UNSET
        else:
            include_reasoning = self.include_reasoning

        include_research: bool | None | Unset
        if isinstance(self.include_research, Unset):
            include_research = UNSET
        else:
            include_research = self.include_research

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
        if response_schema is not UNSET:
            field_dict["response_schema"] = response_schema
        if llm is not UNSET:
            field_dict["llm"] = llm
        if effort_level is not UNSET:
            field_dict["effort_level"] = effort_level
        if return_list is not UNSET:
            field_dict["return_list"] = return_list
        if iteration_budget is not UNSET:
            field_dict["iteration_budget"] = iteration_budget
        if include_reasoning is not UNSET:
            field_dict["include_reasoning"] = include_reasoning
        if include_research is not UNSET:
            field_dict["include_research"] = include_research

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.single_agent_operation_input_type_1_item import SingleAgentOperationInputType1Item
        from ..models.single_agent_operation_input_type_2 import SingleAgentOperationInputType2
        from ..models.single_agent_operation_response_schema_type_0 import SingleAgentOperationResponseSchemaType0

        d = dict(src_dict)

        def _parse_input_(
            data: object,
        ) -> list[SingleAgentOperationInputType1Item] | SingleAgentOperationInputType2 | UUID:
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
                    input_type_1_item = SingleAgentOperationInputType1Item.from_dict(input_type_1_item_data)

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            input_type_2 = SingleAgentOperationInputType2.from_dict(data)

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

        def _parse_response_schema(data: object) -> None | SingleAgentOperationResponseSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = SingleAgentOperationResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SingleAgentOperationResponseSchemaType0 | Unset, data)

        response_schema = _parse_response_schema(d.pop("response_schema", UNSET))

        def _parse_llm(data: object) -> LLMEnumPublic | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                llm_type_0 = LLMEnumPublic(data)

                return llm_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LLMEnumPublic | None | Unset, data)

        llm = _parse_llm(d.pop("llm", UNSET))

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

        return_list = d.pop("return_list", UNSET)

        def _parse_iteration_budget(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        iteration_budget = _parse_iteration_budget(d.pop("iteration_budget", UNSET))

        def _parse_include_reasoning(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        include_reasoning = _parse_include_reasoning(d.pop("include_reasoning", UNSET))

        def _parse_include_research(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        include_research = _parse_include_research(d.pop("include_research", UNSET))

        single_agent_operation = cls(
            input_=input_,
            task=task,
            session_id=session_id,
            response_schema=response_schema,
            llm=llm,
            effort_level=effort_level,
            return_list=return_list,
            iteration_budget=iteration_budget,
            include_reasoning=include_reasoning,
            include_research=include_research,
        )

        single_agent_operation.additional_properties = d
        return single_agent_operation

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

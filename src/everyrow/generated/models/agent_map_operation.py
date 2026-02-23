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
    from ..models.agent_map_operation_input_type_1_item import AgentMapOperationInputType1Item
    from ..models.agent_map_operation_input_type_2 import AgentMapOperationInputType2
    from ..models.agent_map_operation_response_schema_type_0 import AgentMapOperationResponseSchemaType0


T = TypeVar("T", bound="AgentMapOperation")


@_attrs_define
class AgentMapOperation:
    """
    Attributes:
        input_ (AgentMapOperationInputType2 | list[AgentMapOperationInputType1Item] | UUID): The input data as a) the ID
            of an existing artifact, b) a single record in the form of a JSON object, or c) a table of records in the form
            of a list of JSON objects
        task (str): Instructions for the AI agent to execute per row
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        response_schema (AgentMapOperationResponseSchemaType0 | None | Unset): JSON Schema for the response format. If
            not provided, use default answer schema.
        llm (LLMEnumPublic | None | Unset): LLM to use for each agent. Required when effort_level is not set.
        effort_level (None | PublicEffortLevel | Unset): Effort level preset: low (quick), medium (balanced), high
            (thorough). Mutually exclusive with llm/iteration_budget/include_reasoning - use either a preset or custom
            params, not both. If not specified, you must provide all individual parameters (llm, iteration_budget,
            include_reasoning).
        join_with_input (bool | Unset): If True, merge agent output with input row. If False, output only agent results.
            Default: True.
        iteration_budget (int | None | Unset): Number of agent iterations per row (0-20). Required when effort_level is
            not set.
        include_reasoning (bool | None | Unset): Include reasoning notes in the response. Required when effort_level is
            not set.
        include_research (bool | None | Unset): Deprecated: use include_reasoning instead. Include research notes in the
            response. Required when effort_level is not set.
        enforce_row_independence (bool | Unset): If True, each agent runs completely independently without being
            affected by other agents. Disables adaptive budget adjustment and straggler management, ensuring agents are not
            hurried or given iteration limits based on other agents' progress. Use this when consistent per-row behavior is
            more important than overall throughput. Default: False.
    """

    input_: AgentMapOperationInputType2 | list[AgentMapOperationInputType1Item] | UUID
    task: str
    session_id: None | Unset | UUID = UNSET
    response_schema: AgentMapOperationResponseSchemaType0 | None | Unset = UNSET
    llm: LLMEnumPublic | None | Unset = UNSET
    effort_level: None | PublicEffortLevel | Unset = UNSET
    join_with_input: bool | Unset = True
    iteration_budget: int | None | Unset = UNSET
    include_reasoning: bool | None | Unset = UNSET
    include_research: bool | None | Unset = UNSET
    enforce_row_independence: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_map_operation_response_schema_type_0 import AgentMapOperationResponseSchemaType0

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
        elif isinstance(self.response_schema, AgentMapOperationResponseSchemaType0):
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

        join_with_input = self.join_with_input

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

        enforce_row_independence = self.enforce_row_independence

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
        if join_with_input is not UNSET:
            field_dict["join_with_input"] = join_with_input
        if iteration_budget is not UNSET:
            field_dict["iteration_budget"] = iteration_budget
        if include_reasoning is not UNSET:
            field_dict["include_reasoning"] = include_reasoning
        if include_research is not UNSET:
            field_dict["include_research"] = include_research
        if enforce_row_independence is not UNSET:
            field_dict["enforce_row_independence"] = enforce_row_independence

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_map_operation_input_type_1_item import AgentMapOperationInputType1Item
        from ..models.agent_map_operation_input_type_2 import AgentMapOperationInputType2
        from ..models.agent_map_operation_response_schema_type_0 import AgentMapOperationResponseSchemaType0

        d = dict(src_dict)

        def _parse_input_(data: object) -> AgentMapOperationInputType2 | list[AgentMapOperationInputType1Item] | UUID:
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
                    input_type_1_item = AgentMapOperationInputType1Item.from_dict(input_type_1_item_data)

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            input_type_2 = AgentMapOperationInputType2.from_dict(data)

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

        def _parse_response_schema(data: object) -> AgentMapOperationResponseSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_schema_type_0 = AgentMapOperationResponseSchemaType0.from_dict(data)

                return response_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentMapOperationResponseSchemaType0 | None | Unset, data)

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

        join_with_input = d.pop("join_with_input", UNSET)

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

        enforce_row_independence = d.pop("enforce_row_independence", UNSET)

        agent_map_operation = cls(
            input_=input_,
            task=task,
            session_id=session_id,
            response_schema=response_schema,
            llm=llm,
            effort_level=effort_level,
            join_with_input=join_with_input,
            iteration_budget=iteration_budget,
            include_reasoning=include_reasoning,
            include_research=include_research,
            enforce_row_independence=enforce_row_independence,
        )

        agent_map_operation.additional_properties = d
        return agent_map_operation

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

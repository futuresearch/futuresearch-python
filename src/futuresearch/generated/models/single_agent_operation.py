from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.llm_enum_public import LLMEnumPublic
from ..models.public_effort_level import PublicEffortLevel
from ..models.single_agent_operation_budget_awareness_type_0 import SingleAgentOperationBudgetAwarenessType0
from ..models.single_agent_operation_prompt_style_type_0 import SingleAgentOperationPromptStyleType0
from ..models.single_agent_operation_tool_description_style_type_0 import SingleAgentOperationToolDescriptionStyleType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.llm_page_reader import LlmPageReader
    from ..models.paginated_page_reader import PaginatedPageReader
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
        webhook_url (None | str | Unset): Optional URL to receive a POST callback when the task completes or fails.
        response_schema (None | SingleAgentOperationResponseSchemaType0 | Unset): JSON Schema for the response format.
            If not provided, use default answer schema.
        llm (LLMEnumPublic | None | Unset): LLM to use for the agent. Required when effort_level is not set.
        effort_level (None | PublicEffortLevel | Unset): Effort level preset: low (quick), medium (balanced), high
            (thorough). Mutually exclusive with llm/iteration_budget/include_reasoning - use either a preset or custom
            params, not both. If not specified, you must provide all individual parameters (llm, iteration_budget,
            include_reasoning).
        return_list (bool | Unset): If True, treat the output as a list of responses instead of a single response.
            Default: False.
        iteration_budget (int | None | Unset): Number of agent iterations (0-100). Required when effort_level is not
            set.
        include_reasoning (bool | None | Unset): Include reasoning notes in the response. Required when effort_level is
            not set.
        include_research (bool | None | Unset): Deprecated: use include_reasoning instead. Include research notes in the
            response. Required when effort_level is not set.
        extra_notification_text (None | str | Unset): Optional text appended to every inter-iteration notification the
            agent receives. Useful for nudging behavior across all steps (e.g. a premortem reminder) without changing the
            task prompt.
        budget_awareness (None | SingleAgentOperationBudgetAwarenessType0 | Unset): How the per-turn status line frames
            the agent budget: 'iterations' (default) is the iteration counter; 'context' replaces it with live context-
            window usage so the agent can pace itself and report before the window runs out. In context mode
            iteration_budget is ignored (pass any valid value): the context give-up is the budget.
        hard_iteration_cap (int | None | Unset): Context budgeting only: end the run after this many iterations through
            the same give-up turn as context exhaustion, so the row still gets an answer. Silent: nothing the agent sees
            mentions it. Requires budget_awareness='context'; default off.
        parallel_tool_calls (bool | None | Unset): When False, each agent turn makes exactly one tool call (sequential
            research). Default keeps parallel tool calls on.
        prompt_style (None | SingleAgentOperationPromptStyleType0 | Unset): 'minimal' strips the agent's system prompt
            and loop scaffold to the bare protocol (no behavioral coaching). Retro tasks keep the one-line date block so the
            agent takes the anchor date as today; live tasks get no date line.
        tool_description_style (None | SingleAgentOperationToolDescriptionStyleType0 | Unset): 'brief' sends each tool's
            plain description instead of the long-form usage guidance.
        page_reader (LlmPageReader | None | PaginatedPageReader | Unset): How the agent reads web pages: {"type": "llm",
            "model": ...} (a reader LLM answers the agent's query about the page; the default) or {"type": "paginated",
            "page_size_chars": 50000} (the agent reads the page text itself, one page at a time). An llm page_reader cannot
            be combined with document_query_llm (give the reader model once, as page_reader.model); a paginated one can, in
            which case document_query_llm is only the checklist-extraction model. Internal accounts only.
    """

    input_: list[SingleAgentOperationInputType1Item] | SingleAgentOperationInputType2 | UUID
    task: str
    session_id: None | Unset | UUID = UNSET
    webhook_url: None | str | Unset = UNSET
    response_schema: None | SingleAgentOperationResponseSchemaType0 | Unset = UNSET
    llm: LLMEnumPublic | None | Unset = UNSET
    effort_level: None | PublicEffortLevel | Unset = UNSET
    return_list: bool | Unset = False
    iteration_budget: int | None | Unset = UNSET
    include_reasoning: bool | None | Unset = UNSET
    include_research: bool | None | Unset = UNSET
    extra_notification_text: None | str | Unset = UNSET
    budget_awareness: None | SingleAgentOperationBudgetAwarenessType0 | Unset = UNSET
    hard_iteration_cap: int | None | Unset = UNSET
    parallel_tool_calls: bool | None | Unset = UNSET
    prompt_style: None | SingleAgentOperationPromptStyleType0 | Unset = UNSET
    tool_description_style: None | SingleAgentOperationToolDescriptionStyleType0 | Unset = UNSET
    page_reader: LlmPageReader | None | PaginatedPageReader | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.llm_page_reader import LlmPageReader
        from ..models.paginated_page_reader import PaginatedPageReader
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

        webhook_url: None | str | Unset
        if isinstance(self.webhook_url, Unset):
            webhook_url = UNSET
        else:
            webhook_url = self.webhook_url

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

        extra_notification_text: None | str | Unset
        if isinstance(self.extra_notification_text, Unset):
            extra_notification_text = UNSET
        else:
            extra_notification_text = self.extra_notification_text

        budget_awareness: None | str | Unset
        if isinstance(self.budget_awareness, Unset):
            budget_awareness = UNSET
        elif isinstance(self.budget_awareness, SingleAgentOperationBudgetAwarenessType0):
            budget_awareness = self.budget_awareness.value
        else:
            budget_awareness = self.budget_awareness

        hard_iteration_cap: int | None | Unset
        if isinstance(self.hard_iteration_cap, Unset):
            hard_iteration_cap = UNSET
        else:
            hard_iteration_cap = self.hard_iteration_cap

        parallel_tool_calls: bool | None | Unset
        if isinstance(self.parallel_tool_calls, Unset):
            parallel_tool_calls = UNSET
        else:
            parallel_tool_calls = self.parallel_tool_calls

        prompt_style: None | str | Unset
        if isinstance(self.prompt_style, Unset):
            prompt_style = UNSET
        elif isinstance(self.prompt_style, SingleAgentOperationPromptStyleType0):
            prompt_style = self.prompt_style.value
        else:
            prompt_style = self.prompt_style

        tool_description_style: None | str | Unset
        if isinstance(self.tool_description_style, Unset):
            tool_description_style = UNSET
        elif isinstance(self.tool_description_style, SingleAgentOperationToolDescriptionStyleType0):
            tool_description_style = self.tool_description_style.value
        else:
            tool_description_style = self.tool_description_style

        page_reader: dict[str, Any] | None | Unset
        if isinstance(self.page_reader, Unset):
            page_reader = UNSET
        elif isinstance(self.page_reader, LlmPageReader):
            page_reader = self.page_reader.to_dict()
        elif isinstance(self.page_reader, PaginatedPageReader):
            page_reader = self.page_reader.to_dict()
        else:
            page_reader = self.page_reader

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
        if extra_notification_text is not UNSET:
            field_dict["extra_notification_text"] = extra_notification_text
        if budget_awareness is not UNSET:
            field_dict["budget_awareness"] = budget_awareness
        if hard_iteration_cap is not UNSET:
            field_dict["hard_iteration_cap"] = hard_iteration_cap
        if parallel_tool_calls is not UNSET:
            field_dict["parallel_tool_calls"] = parallel_tool_calls
        if prompt_style is not UNSET:
            field_dict["prompt_style"] = prompt_style
        if tool_description_style is not UNSET:
            field_dict["tool_description_style"] = tool_description_style
        if page_reader is not UNSET:
            field_dict["page_reader"] = page_reader

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_page_reader import LlmPageReader
        from ..models.paginated_page_reader import PaginatedPageReader
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

        def _parse_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        webhook_url = _parse_webhook_url(d.pop("webhook_url", UNSET))

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

        def _parse_extra_notification_text(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        extra_notification_text = _parse_extra_notification_text(d.pop("extra_notification_text", UNSET))

        def _parse_budget_awareness(data: object) -> None | SingleAgentOperationBudgetAwarenessType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                budget_awareness_type_0 = SingleAgentOperationBudgetAwarenessType0(data)

                return budget_awareness_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SingleAgentOperationBudgetAwarenessType0 | Unset, data)

        budget_awareness = _parse_budget_awareness(d.pop("budget_awareness", UNSET))

        def _parse_hard_iteration_cap(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        hard_iteration_cap = _parse_hard_iteration_cap(d.pop("hard_iteration_cap", UNSET))

        def _parse_parallel_tool_calls(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        parallel_tool_calls = _parse_parallel_tool_calls(d.pop("parallel_tool_calls", UNSET))

        def _parse_prompt_style(data: object) -> None | SingleAgentOperationPromptStyleType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                prompt_style_type_0 = SingleAgentOperationPromptStyleType0(data)

                return prompt_style_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SingleAgentOperationPromptStyleType0 | Unset, data)

        prompt_style = _parse_prompt_style(d.pop("prompt_style", UNSET))

        def _parse_tool_description_style(data: object) -> None | SingleAgentOperationToolDescriptionStyleType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tool_description_style_type_0 = SingleAgentOperationToolDescriptionStyleType0(data)

                return tool_description_style_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SingleAgentOperationToolDescriptionStyleType0 | Unset, data)

        tool_description_style = _parse_tool_description_style(d.pop("tool_description_style", UNSET))

        def _parse_page_reader(data: object) -> LlmPageReader | None | PaginatedPageReader | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                page_reader_type_0_type_0 = LlmPageReader.from_dict(data)

                return page_reader_type_0_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                page_reader_type_0_type_1 = PaginatedPageReader.from_dict(data)

                return page_reader_type_0_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LlmPageReader | None | PaginatedPageReader | Unset, data)

        page_reader = _parse_page_reader(d.pop("page_reader", UNSET))

        single_agent_operation = cls(
            input_=input_,
            task=task,
            session_id=session_id,
            webhook_url=webhook_url,
            response_schema=response_schema,
            llm=llm,
            effort_level=effort_level,
            return_list=return_list,
            iteration_budget=iteration_budget,
            include_reasoning=include_reasoning,
            include_research=include_research,
            extra_notification_text=extra_notification_text,
            budget_awareness=budget_awareness,
            hard_iteration_cap=hard_iteration_cap,
            parallel_tool_calls=parallel_tool_calls,
            prompt_style=prompt_style,
            tool_description_style=tool_description_style,
            page_reader=page_reader,
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

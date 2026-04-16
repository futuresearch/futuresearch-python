from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.llm_enum_public import LLMEnumPublic
from ..models.merge_operation_relationship_type_type_0 import (
    MergeOperationRelationshipTypeType0,
)
from ..models.merge_operation_use_web_search_type_0 import (
    MergeOperationUseWebSearchType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.merge_operation_left_input_type_1_item import (
        MergeOperationLeftInputType1Item,
    )
    from ..models.merge_operation_left_input_type_2 import MergeOperationLeftInputType2
    from ..models.merge_operation_right_input_type_1_item import (
        MergeOperationRightInputType1Item,
    )
    from ..models.merge_operation_right_input_type_2 import (
        MergeOperationRightInputType2,
    )


T = TypeVar("T", bound="MergeOperation")


@_attrs_define
class MergeOperation:
    """
    Attributes:
        left_input (list[MergeOperationLeftInputType1Item] | MergeOperationLeftInputType2 | UUID): Left input: artifact
            UUID, list of records, or single record
        right_input (list[MergeOperationRightInputType1Item] | MergeOperationRightInputType2 | UUID): Right input:
            artifact UUID, list of records, or single record
        task (str): Instructions for the AI to determine how to merge rows
        left_key (None | str | Unset): Column name to merge on from left table
        right_key (None | str | Unset): Column name to merge on from right table
        use_web_search (MergeOperationUseWebSearchType0 | None | Unset): Control web search behavior: 'auto' (default)
            tries LLM merge first then conditionally searches, 'no' skips web search entirely, 'yes' forces web search
            without initial LLM merge Default: MergeOperationUseWebSearchType0.AUTO.
        relationship_type (MergeOperationRelationshipTypeType0 | None | Unset): Control merge relationship behavior:
            'many_to_one' (default) allows multiple left rows to match the same right row, 'one_to_one' enforces unique
            matches and resolves clashes Default: MergeOperationRelationshipTypeType0.MANY_TO_ONE.
        llm (LLMEnumPublic | None | Unset): LLM to use for the merge operation (both initial LLM matching and web
            search agent). If not provided, uses system defaults.
        document_query_llm (LLMEnumPublic | None | Unset): LLM to use for the document query tool (QDLLM) that reads
            and extracts information from web pages. If not provided, defaults to the system default.
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        webhook_url (None | str | Unset): Optional URL to receive a POST callback when the task completes or fails.
    """

    left_input: (
        list[MergeOperationLeftInputType1Item] | MergeOperationLeftInputType2 | UUID
    )
    right_input: (
        list[MergeOperationRightInputType1Item] | MergeOperationRightInputType2 | UUID
    )
    task: str
    left_key: None | str | Unset = UNSET
    right_key: None | str | Unset = UNSET
    use_web_search: MergeOperationUseWebSearchType0 | None | Unset = (
        MergeOperationUseWebSearchType0.AUTO
    )
    relationship_type: MergeOperationRelationshipTypeType0 | None | Unset = (
        MergeOperationRelationshipTypeType0.MANY_TO_ONE
    )
    llm: LLMEnumPublic | None | Unset = UNSET
    document_query_llm: LLMEnumPublic | None | Unset = UNSET
    session_id: None | Unset | UUID = UNSET
    webhook_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        left_input: dict[str, Any] | list[dict[str, Any]] | str
        if isinstance(self.left_input, UUID):
            left_input = str(self.left_input)
        elif isinstance(self.left_input, list):
            left_input = []
            for left_input_type_1_item_data in self.left_input:
                left_input_type_1_item = left_input_type_1_item_data.to_dict()
                left_input.append(left_input_type_1_item)

        else:
            left_input = self.left_input.to_dict()

        right_input: dict[str, Any] | list[dict[str, Any]] | str
        if isinstance(self.right_input, UUID):
            right_input = str(self.right_input)
        elif isinstance(self.right_input, list):
            right_input = []
            for right_input_type_1_item_data in self.right_input:
                right_input_type_1_item = right_input_type_1_item_data.to_dict()
                right_input.append(right_input_type_1_item)

        else:
            right_input = self.right_input.to_dict()

        task = self.task

        left_key: None | str | Unset
        if isinstance(self.left_key, Unset):
            left_key = UNSET
        else:
            left_key = self.left_key

        right_key: None | str | Unset
        if isinstance(self.right_key, Unset):
            right_key = UNSET
        else:
            right_key = self.right_key

        use_web_search: None | str | Unset
        if isinstance(self.use_web_search, Unset):
            use_web_search = UNSET
        elif isinstance(self.use_web_search, MergeOperationUseWebSearchType0):
            use_web_search = self.use_web_search.value
        else:
            use_web_search = self.use_web_search

        relationship_type: None | str | Unset
        if isinstance(self.relationship_type, Unset):
            relationship_type = UNSET
        elif isinstance(self.relationship_type, MergeOperationRelationshipTypeType0):
            relationship_type = self.relationship_type.value
        else:
            relationship_type = self.relationship_type

        llm: None | str | Unset
        if isinstance(self.llm, Unset):
            llm = UNSET
        elif isinstance(self.llm, LLMEnumPublic):
            llm = self.llm.value
        else:
            llm = self.llm

        document_query_llm: None | str | Unset
        if isinstance(self.document_query_llm, Unset):
            document_query_llm = UNSET
        elif isinstance(self.document_query_llm, LLMEnumPublic):
            document_query_llm = self.document_query_llm.value
        else:
            document_query_llm = self.document_query_llm

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "left_input": left_input,
                "right_input": right_input,
                "task": task,
            }
        )
        if left_key is not UNSET:
            field_dict["left_key"] = left_key
        if right_key is not UNSET:
            field_dict["right_key"] = right_key
        if use_web_search is not UNSET:
            field_dict["use_web_search"] = use_web_search
        if relationship_type is not UNSET:
            field_dict["relationship_type"] = relationship_type
        if llm is not UNSET:
            field_dict["llm"] = llm
        if document_query_llm is not UNSET:
            field_dict["document_query_llm"] = document_query_llm
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if webhook_url is not UNSET:
            field_dict["webhook_url"] = webhook_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.merge_operation_left_input_type_1_item import (
            MergeOperationLeftInputType1Item,
        )
        from ..models.merge_operation_left_input_type_2 import (
            MergeOperationLeftInputType2,
        )
        from ..models.merge_operation_right_input_type_1_item import (
            MergeOperationRightInputType1Item,
        )
        from ..models.merge_operation_right_input_type_2 import (
            MergeOperationRightInputType2,
        )

        d = dict(src_dict)

        def _parse_left_input(
            data: object,
        ) -> (
            list[MergeOperationLeftInputType1Item] | MergeOperationLeftInputType2 | UUID
        ):
            try:
                if not isinstance(data, str):
                    raise TypeError()
                left_input_type_0 = UUID(data)

                return left_input_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                left_input_type_1 = []
                _left_input_type_1 = data
                for left_input_type_1_item_data in _left_input_type_1:
                    left_input_type_1_item = MergeOperationLeftInputType1Item.from_dict(
                        left_input_type_1_item_data
                    )

                    left_input_type_1.append(left_input_type_1_item)

                return left_input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            left_input_type_2 = MergeOperationLeftInputType2.from_dict(data)

            return left_input_type_2

        left_input = _parse_left_input(d.pop("left_input"))

        def _parse_right_input(
            data: object,
        ) -> (
            list[MergeOperationRightInputType1Item]
            | MergeOperationRightInputType2
            | UUID
        ):
            try:
                if not isinstance(data, str):
                    raise TypeError()
                right_input_type_0 = UUID(data)

                return right_input_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                right_input_type_1 = []
                _right_input_type_1 = data
                for right_input_type_1_item_data in _right_input_type_1:
                    right_input_type_1_item = (
                        MergeOperationRightInputType1Item.from_dict(
                            right_input_type_1_item_data
                        )
                    )

                    right_input_type_1.append(right_input_type_1_item)

                return right_input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            right_input_type_2 = MergeOperationRightInputType2.from_dict(data)

            return right_input_type_2

        right_input = _parse_right_input(d.pop("right_input"))

        task = d.pop("task")

        def _parse_left_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        left_key = _parse_left_key(d.pop("left_key", UNSET))

        def _parse_right_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        right_key = _parse_right_key(d.pop("right_key", UNSET))

        def _parse_use_web_search(
            data: object,
        ) -> MergeOperationUseWebSearchType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                use_web_search_type_0 = MergeOperationUseWebSearchType0(data)

                return use_web_search_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MergeOperationUseWebSearchType0 | None | Unset, data)

        use_web_search = _parse_use_web_search(d.pop("use_web_search", UNSET))

        def _parse_relationship_type(
            data: object,
        ) -> MergeOperationRelationshipTypeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                relationship_type_type_0 = MergeOperationRelationshipTypeType0(data)

                return relationship_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MergeOperationRelationshipTypeType0 | None | Unset, data)

        relationship_type = _parse_relationship_type(d.pop("relationship_type", UNSET))

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

        def _parse_document_query_llm(data: object) -> LLMEnumPublic | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                document_query_llm_type_0 = LLMEnumPublic(data)

                return document_query_llm_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LLMEnumPublic | None | Unset, data)

        document_query_llm = _parse_document_query_llm(
            d.pop("document_query_llm", UNSET)
        )

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

        merge_operation = cls(
            left_input=left_input,
            right_input=right_input,
            task=task,
            left_key=left_key,
            right_key=right_key,
            use_web_search=use_web_search,
            relationship_type=relationship_type,
            llm=llm,
            document_query_llm=document_query_llm,
            session_id=session_id,
            webhook_url=webhook_url,
        )

        merge_operation.additional_properties = d
        return merge_operation

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.llm_enum import LLMEnum
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.claude_sdk_forecaster_slot import ClaudeSdkForecasterSlot
    from ..models.low_effort_forecaster_slot import LowEffortForecasterSlot
    from ..models.open_ai_sdk_forecaster_slot import OpenAiSdkForecasterSlot
    from ..models.re_act_forecaster_slot import ReActForecasterSlot
    from ..models.refiner_slot import RefinerSlot


T = TypeVar("T", bound="ForecastTaskConfig")


@_attrs_define
class ForecastTaskConfig:
    """Per-task overrides for forecast pipeline internals.

    extra="forbid": a typoed key must 422 at submit, not silently fall back to
    the default mid-run — a researcher would otherwise draw conclusions from a
    run that didn't test what they thought.

        Attributes:
            forecaster_slots (list[ClaudeSdkForecasterSlot | OpenAiSdkForecasterSlot | ReActForecasterSlot] | None | Unset):
                Complete replacement for the HIGH-effort estimate ensemble (default: 2x Claude SDK + ReAct gpt-5.5).
            refiner_slots (list[RefinerSlot] | None | Unset): Complete replacement for the HIGH-effort refiner ensemble
                (default: opus + gpt + gemini).
            summarizer_model (LLMEnum | None | Unset): Model for the HIGH-effort rationale summarizer.
            low_effort_forecaster_models (list[LowEffortForecasterSlot] | None | Unset): Complete replacement for the LOW-
                effort combine ensemble (default: 2x gemini + gpt).
            batch_size (int | None | Unset): Rows per LOW-effort batch (default 4).
            iteration_budget (int | None | Unset): Steps per ReAct estimate / dimension agent (default: 10 HIGH, 5 LOW).
    """

    forecaster_slots: list[ClaudeSdkForecasterSlot | OpenAiSdkForecasterSlot | ReActForecasterSlot] | None | Unset = (
        UNSET
    )
    refiner_slots: list[RefinerSlot] | None | Unset = UNSET
    summarizer_model: LLMEnum | None | Unset = UNSET
    low_effort_forecaster_models: list[LowEffortForecasterSlot] | None | Unset = UNSET
    batch_size: int | None | Unset = UNSET
    iteration_budget: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_sdk_forecaster_slot import ClaudeSdkForecasterSlot
        from ..models.re_act_forecaster_slot import ReActForecasterSlot

        forecaster_slots: list[dict[str, Any]] | None | Unset
        if isinstance(self.forecaster_slots, Unset):
            forecaster_slots = UNSET
        elif isinstance(self.forecaster_slots, list):
            forecaster_slots = []
            for forecaster_slots_type_0_item_data in self.forecaster_slots:
                forecaster_slots_type_0_item: dict[str, Any]
                if isinstance(forecaster_slots_type_0_item_data, ReActForecasterSlot):
                    forecaster_slots_type_0_item = forecaster_slots_type_0_item_data.to_dict()
                elif isinstance(forecaster_slots_type_0_item_data, ClaudeSdkForecasterSlot):
                    forecaster_slots_type_0_item = forecaster_slots_type_0_item_data.to_dict()
                else:
                    forecaster_slots_type_0_item = forecaster_slots_type_0_item_data.to_dict()

                forecaster_slots.append(forecaster_slots_type_0_item)

        else:
            forecaster_slots = self.forecaster_slots

        refiner_slots: list[dict[str, Any]] | None | Unset
        if isinstance(self.refiner_slots, Unset):
            refiner_slots = UNSET
        elif isinstance(self.refiner_slots, list):
            refiner_slots = []
            for refiner_slots_type_0_item_data in self.refiner_slots:
                refiner_slots_type_0_item = refiner_slots_type_0_item_data.to_dict()
                refiner_slots.append(refiner_slots_type_0_item)

        else:
            refiner_slots = self.refiner_slots

        summarizer_model: None | str | Unset
        if isinstance(self.summarizer_model, Unset):
            summarizer_model = UNSET
        elif isinstance(self.summarizer_model, LLMEnum):
            summarizer_model = self.summarizer_model.value
        else:
            summarizer_model = self.summarizer_model

        low_effort_forecaster_models: list[dict[str, Any]] | None | Unset
        if isinstance(self.low_effort_forecaster_models, Unset):
            low_effort_forecaster_models = UNSET
        elif isinstance(self.low_effort_forecaster_models, list):
            low_effort_forecaster_models = []
            for low_effort_forecaster_models_type_0_item_data in self.low_effort_forecaster_models:
                low_effort_forecaster_models_type_0_item = low_effort_forecaster_models_type_0_item_data.to_dict()
                low_effort_forecaster_models.append(low_effort_forecaster_models_type_0_item)

        else:
            low_effort_forecaster_models = self.low_effort_forecaster_models

        batch_size: int | None | Unset
        if isinstance(self.batch_size, Unset):
            batch_size = UNSET
        else:
            batch_size = self.batch_size

        iteration_budget: int | None | Unset
        if isinstance(self.iteration_budget, Unset):
            iteration_budget = UNSET
        else:
            iteration_budget = self.iteration_budget

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if forecaster_slots is not UNSET:
            field_dict["forecaster_slots"] = forecaster_slots
        if refiner_slots is not UNSET:
            field_dict["refiner_slots"] = refiner_slots
        if summarizer_model is not UNSET:
            field_dict["summarizer_model"] = summarizer_model
        if low_effort_forecaster_models is not UNSET:
            field_dict["low_effort_forecaster_models"] = low_effort_forecaster_models
        if batch_size is not UNSET:
            field_dict["batch_size"] = batch_size
        if iteration_budget is not UNSET:
            field_dict["iteration_budget"] = iteration_budget

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claude_sdk_forecaster_slot import ClaudeSdkForecasterSlot
        from ..models.low_effort_forecaster_slot import LowEffortForecasterSlot
        from ..models.open_ai_sdk_forecaster_slot import OpenAiSdkForecasterSlot
        from ..models.re_act_forecaster_slot import ReActForecasterSlot
        from ..models.refiner_slot import RefinerSlot

        d = dict(src_dict)

        def _parse_forecaster_slots(
            data: object,
        ) -> list[ClaudeSdkForecasterSlot | OpenAiSdkForecasterSlot | ReActForecasterSlot] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                forecaster_slots_type_0 = []
                _forecaster_slots_type_0 = data
                for forecaster_slots_type_0_item_data in _forecaster_slots_type_0:

                    def _parse_forecaster_slots_type_0_item(
                        data: object,
                    ) -> ClaudeSdkForecasterSlot | OpenAiSdkForecasterSlot | ReActForecasterSlot:
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            forecaster_slots_type_0_item_type_0 = ReActForecasterSlot.from_dict(data)

                            return forecaster_slots_type_0_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            forecaster_slots_type_0_item_type_1 = ClaudeSdkForecasterSlot.from_dict(data)

                            return forecaster_slots_type_0_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        forecaster_slots_type_0_item_type_2 = OpenAiSdkForecasterSlot.from_dict(data)

                        return forecaster_slots_type_0_item_type_2

                    forecaster_slots_type_0_item = _parse_forecaster_slots_type_0_item(
                        forecaster_slots_type_0_item_data
                    )

                    forecaster_slots_type_0.append(forecaster_slots_type_0_item)

                return forecaster_slots_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ClaudeSdkForecasterSlot | OpenAiSdkForecasterSlot | ReActForecasterSlot] | None | Unset, data
            )

        forecaster_slots = _parse_forecaster_slots(d.pop("forecaster_slots", UNSET))

        def _parse_refiner_slots(data: object) -> list[RefinerSlot] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                refiner_slots_type_0 = []
                _refiner_slots_type_0 = data
                for refiner_slots_type_0_item_data in _refiner_slots_type_0:
                    refiner_slots_type_0_item = RefinerSlot.from_dict(refiner_slots_type_0_item_data)

                    refiner_slots_type_0.append(refiner_slots_type_0_item)

                return refiner_slots_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[RefinerSlot] | None | Unset, data)

        refiner_slots = _parse_refiner_slots(d.pop("refiner_slots", UNSET))

        def _parse_summarizer_model(data: object) -> LLMEnum | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                summarizer_model_type_0 = LLMEnum(data)

                return summarizer_model_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LLMEnum | None | Unset, data)

        summarizer_model = _parse_summarizer_model(d.pop("summarizer_model", UNSET))

        def _parse_low_effort_forecaster_models(data: object) -> list[LowEffortForecasterSlot] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                low_effort_forecaster_models_type_0 = []
                _low_effort_forecaster_models_type_0 = data
                for low_effort_forecaster_models_type_0_item_data in _low_effort_forecaster_models_type_0:
                    low_effort_forecaster_models_type_0_item = LowEffortForecasterSlot.from_dict(
                        low_effort_forecaster_models_type_0_item_data
                    )

                    low_effort_forecaster_models_type_0.append(low_effort_forecaster_models_type_0_item)

                return low_effort_forecaster_models_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[LowEffortForecasterSlot] | None | Unset, data)

        low_effort_forecaster_models = _parse_low_effort_forecaster_models(d.pop("low_effort_forecaster_models", UNSET))

        def _parse_batch_size(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        batch_size = _parse_batch_size(d.pop("batch_size", UNSET))

        def _parse_iteration_budget(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        iteration_budget = _parse_iteration_budget(d.pop("iteration_budget", UNSET))

        forecast_task_config = cls(
            forecaster_slots=forecaster_slots,
            refiner_slots=refiner_slots,
            summarizer_model=summarizer_model,
            low_effort_forecaster_models=low_effort_forecaster_models,
            batch_size=batch_size,
            iteration_budget=iteration_budget,
        )

        return forecast_task_config

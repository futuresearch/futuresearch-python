from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.forecast_effort_level import ForecastEffortLevel
from ..models.forecast_type import ForecastType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.forecast_operation_input_type_1_item import ForecastOperationInputType1Item
    from ..models.forecast_operation_input_type_2 import ForecastOperationInputType2


T = TypeVar("T", bound="ForecastOperation")


@_attrs_define
class ForecastOperation:
    """
    Attributes:
        input_ (ForecastOperationInputType2 | list[ForecastOperationInputType1Item] | UUID): The input data as a) the ID
            of an existing artifact, b) a single record in the form of a JSON object, or c) a table of records in the form
            of a list of JSON objects
        task (str): Overall context or instructions for the forecast. Each row in the input should contain the
            question/scenario to forecast.
        forecast_type (ForecastType):
        session_id (None | Unset | UUID): Session ID. If not provided, a new session is auto-created for this task.
        webhook_url (None | str | Unset): Optional URL to receive a POST callback when the task completes or fails.
        output_field (None | str | Unset): Name of the numeric quantity being forecast (e.g. 'price', 'count'). Required
            when forecast_type is 'numeric'. Output columns will be named {output_field}_p10 through {output_field}_p90.
        units (None | str | Unset): Units for the numeric forecast (e.g. 'USD per barrel', 'thousands'). Required when
            forecast_type is 'numeric'.
        effort_level (ForecastEffortLevel | None | Unset): Effort level for the forecast. 'LOW' tends to be faster and
            cheaper. 'HIGH' tends to be more accurate. When not specified, defaults to 'HIGH' for single-question forecasts
            and 'LOW' for multi-question forecasts.
    """

    input_: ForecastOperationInputType2 | list[ForecastOperationInputType1Item] | UUID
    task: str
    forecast_type: ForecastType
    session_id: None | Unset | UUID = UNSET
    webhook_url: None | str | Unset = UNSET
    output_field: None | str | Unset = UNSET
    units: None | str | Unset = UNSET
    effort_level: ForecastEffortLevel | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

        forecast_type = self.forecast_type.value

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

        output_field: None | str | Unset
        if isinstance(self.output_field, Unset):
            output_field = UNSET
        else:
            output_field = self.output_field

        units: None | str | Unset
        if isinstance(self.units, Unset):
            units = UNSET
        else:
            units = self.units

        effort_level: None | str | Unset
        if isinstance(self.effort_level, Unset):
            effort_level = UNSET
        elif isinstance(self.effort_level, ForecastEffortLevel):
            effort_level = self.effort_level.value
        else:
            effort_level = self.effort_level

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input": input_,
                "task": task,
                "forecast_type": forecast_type,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if webhook_url is not UNSET:
            field_dict["webhook_url"] = webhook_url
        if output_field is not UNSET:
            field_dict["output_field"] = output_field
        if units is not UNSET:
            field_dict["units"] = units
        if effort_level is not UNSET:
            field_dict["effort_level"] = effort_level

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.forecast_operation_input_type_1_item import ForecastOperationInputType1Item
        from ..models.forecast_operation_input_type_2 import ForecastOperationInputType2

        d = dict(src_dict)

        def _parse_input_(data: object) -> ForecastOperationInputType2 | list[ForecastOperationInputType1Item] | UUID:
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
                    input_type_1_item = ForecastOperationInputType1Item.from_dict(input_type_1_item_data)

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            input_type_2 = ForecastOperationInputType2.from_dict(data)

            return input_type_2

        input_ = _parse_input_(d.pop("input"))

        task = d.pop("task")

        forecast_type = ForecastType(d.pop("forecast_type"))

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

        def _parse_output_field(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        output_field = _parse_output_field(d.pop("output_field", UNSET))

        def _parse_units(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        units = _parse_units(d.pop("units", UNSET))

        def _parse_effort_level(data: object) -> ForecastEffortLevel | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                effort_level_type_0 = ForecastEffortLevel(data)

                return effort_level_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ForecastEffortLevel | None | Unset, data)

        effort_level = _parse_effort_level(d.pop("effort_level", UNSET))

        forecast_operation = cls(
            input_=input_,
            task=task,
            forecast_type=forecast_type,
            session_id=session_id,
            webhook_url=webhook_url,
            output_field=output_field,
            units=units,
            effort_level=effort_level,
        )

        forecast_operation.additional_properties = d
        return forecast_operation

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

from enum import Enum


class ForecastOperationForecastType(str, Enum):
    BINARY = "binary"
    NUMERIC = "numeric"
    DATE = "date"

    def __str__(self) -> str:
        return str(self.value)

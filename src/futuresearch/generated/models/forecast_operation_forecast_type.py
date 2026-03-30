from enum import Enum


class ForecastOperationForecastType(str, Enum):
    BINARY = "binary"
    NUMERIC = "numeric"

    def __str__(self) -> str:
        return str(self.value)

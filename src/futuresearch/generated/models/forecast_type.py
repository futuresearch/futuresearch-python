from enum import Enum


class ForecastType(str, Enum):
    BINARY = "binary"
    DATE = "date"
    NUMERIC = "numeric"

    def __str__(self) -> str:
        return str(self.value)

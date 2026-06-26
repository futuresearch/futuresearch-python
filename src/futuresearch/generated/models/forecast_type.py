from enum import Enum


class ForecastType(str, Enum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    CONDITIONAL = "conditional"
    DATE = "date"
    NUMERIC = "numeric"
    THRESHOLDED = "thresholded"

    def __str__(self) -> str:
        return str(self.value)

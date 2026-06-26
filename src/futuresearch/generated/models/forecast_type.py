from enum import Enum


class ForecastType(str, Enum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    DATE = "date"
    NUMERIC = "numeric"
    THRESHOLDED = "thresholded"

    def __str__(self) -> str:
        return str(self.value)

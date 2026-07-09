from enum import Enum


class ClaudeSdkForecasterSlotEffort(str, Enum):
    HIGH = "high"
    LOW = "low"
    MAX = "max"
    MEDIUM = "medium"
    XHIGH = "xhigh"

    def __str__(self) -> str:
        return str(self.value)

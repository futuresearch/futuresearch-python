from enum import Enum


class OpenAiSdkForecasterSlotReasoningEffortType0(str, Enum):
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"
    MINIMAL = "minimal"
    NONE = "none"
    XHIGH = "xhigh"

    def __str__(self) -> str:
        return str(self.value)

from enum import Enum


class PublicTaskType(str, Enum):
    AGENT = "agent"
    CLASSIFY = "classify"
    DEDUPE = "dedupe"
    FORECAST = "forecast"
    MERGE = "merge"
    RANK = "rank"
    SCREEN = "screen"

    def __str__(self) -> str:
        return str(self.value)

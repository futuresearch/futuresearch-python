from enum import Enum


class PublicTaskType(str, Enum):
    AGENT = "agent"
    CLASSIFY = "classify"
    DEDUPE = "dedupe"
    FORECAST = "forecast"
    MULTI_AGENT = "multi_agent"
    MERGE = "merge"
    RANK = "rank"
    SCREEN = "screen"
    UPLOAD_CSV = "upload_csv"
    UPLOAD_DATA = "upload_data"

    def __str__(self) -> str:
        return str(self.value)

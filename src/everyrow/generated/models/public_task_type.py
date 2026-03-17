from enum import Enum


class PublicTaskType(str, Enum):
    AGENT = "agent"
    CLASSIFY = "classify"
    DEDUPE = "dedupe"
    FORECAST = "forecast"
    MERGE = "merge"
    RANK = "rank"
    UPLOAD_CSV = "upload_csv"
    UPLOAD_DATA = "upload_data"

    def __str__(self) -> str:
        return str(self.value)

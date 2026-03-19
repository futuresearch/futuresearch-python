from enum import Enum


class DedupeOperationStrategy(str, Enum):
    COMBINE = "combine"
    IDENTIFY = "identify"
    SELECT = "select"

    def __str__(self) -> str:
        return str(self.value)

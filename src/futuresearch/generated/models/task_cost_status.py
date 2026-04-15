from enum import Enum


class TaskCostStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"

    def __str__(self) -> str:
        return str(self.value)

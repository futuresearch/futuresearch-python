from enum import Enum


class SingleAgentOperationBudgetAwarenessType0(str, Enum):
    CONTEXT = "context"
    ITERATIONS = "iterations"

    def __str__(self) -> str:
        return str(self.value)

from enum import Enum


class AgentMapOperationBudgetAwarenessType0(str, Enum):
    CONTEXT = "context"
    ITERATIONS = "iterations"

    def __str__(self) -> str:
        return str(self.value)

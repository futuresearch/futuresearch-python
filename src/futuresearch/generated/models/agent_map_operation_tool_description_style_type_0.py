from enum import Enum


class AgentMapOperationToolDescriptionStyleType0(str, Enum):
    BRIEF = "brief"
    FULL = "full"

    def __str__(self) -> str:
        return str(self.value)

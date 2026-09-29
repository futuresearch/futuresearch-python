from enum import Enum


class AgentMapOperationPromptStyleType0(str, Enum):
    MINIMAL = "minimal"
    MINIMAL_RETRO = "minimal_retro"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)

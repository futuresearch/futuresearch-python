from enum import Enum


class SingleAgentOperationPromptStyleType0(str, Enum):
    BARE = "bare"
    MINIMAL = "minimal"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)

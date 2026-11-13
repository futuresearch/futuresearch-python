from enum import Enum


class WorldModel(str, Enum):
    ACCOUNT = "account"
    FULL = "full"
    OFF = "off"

    def __str__(self) -> str:
        return str(self.value)

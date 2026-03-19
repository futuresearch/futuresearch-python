from enum import Enum


class MergeOperationUseWebSearchType0(str, Enum):
    AUTO = "auto"
    NO = "no"
    YES = "yes"

    def __str__(self) -> str:
        return str(self.value)

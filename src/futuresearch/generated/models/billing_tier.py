from enum import Enum


class BillingTier(str, Enum):
    ANALYST = "analyst"
    EXPERT = "expert"
    FREE = "free"
    RESEARCH = "research"

    def __str__(self) -> str:
        return str(self.value)

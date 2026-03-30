from enum import Enum


class SubscriptionTier(str, Enum):
    ANALYST_STARTER = "analyst_starter"
    FREE = "free"
    RESEARCH_TEAM = "research_team"

    def __str__(self) -> str:
        return str(self.value)

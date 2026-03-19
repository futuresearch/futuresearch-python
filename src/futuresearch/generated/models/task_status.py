from enum import Enum


class TaskStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    REVOKED = "revoked"
    RUNNING = "running"

    def __str__(self) -> str:
        return str(self.value)

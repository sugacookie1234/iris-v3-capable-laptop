"""Validated task data. All instants are stored in UTC."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Use an ISO 8601 date/time with a timezone.")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Date/time requires a timezone, such as +00:00.")
    return parsed.astimezone(timezone.utc).isoformat()


def task_id(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Provide a full lowercase task UUID.")
    return value


class TaskStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    DELETED = "deleted"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True)
class Task:
    title: str
    notes: str = ""
    due_at: str | None = None
    status: TaskStatus = TaskStatus.OPEN
    priority: TaskPriority = TaskPriority.NORMAL
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    revision: int = 1
    goal_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 500:
            raise ValueError("Title must contain 1 to 500 characters.")
        if not isinstance(self.notes, str) or len(self.notes) > 10000:
            raise ValueError("Notes must contain at most 10000 characters.")
        task_id(self.id)
        if self.goal_id is not None:
            if not isinstance(self.goal_id, str) or str(UUID(self.goal_id)) != self.goal_id:
                raise ValueError("Goal reference must be a full lowercase goal UUID.")
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "status", TaskStatus(self.status))
        object.__setattr__(self, "priority", TaskPriority(self.priority))
        for name in ("created_at", "updated_at", "due_at"):
            value = getattr(self, name)
            if value is not None or name != "due_at":
                object.__setattr__(self, name, instant(value))
        if self.updated_at < self.created_at:
            raise ValueError("Updated timestamp precedes creation.")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Revision must be a positive integer.")

    def is_overdue(self, at: str | None = None) -> bool:
        return (self.status == TaskStatus.OPEN and self.due_at is not None
                and datetime.fromisoformat(self.due_at) < datetime.fromisoformat(instant(at or now())))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TaskRevision:
    task_id: str
    revision: int
    action: str
    snapshot: Task

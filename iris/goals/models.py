"""Typed persistent goal records, with local calendar target dates."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def goal_id(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Provide a full lowercase goal UUID.")
    return value


class GoalCategory(StrEnum):
    PERSONAL = "personal"
    CAREER = "career"
    HEALTH = "health"
    LEARNING = "learning"
    PROJECT = "project"
    FINANCIAL = "financial"
    OTHER = "other"


class GoalPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass(frozen=True)
class Goal:
    title: str
    description: str = ""
    category: GoalCategory = GoalCategory.PERSONAL
    priority: GoalPriority = GoalPriority.NORMAL
    status: GoalStatus = GoalStatus.ACTIVE
    target_date: str | None = None
    progress: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    revision: int = 1

    def __post_init__(self):
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 200:
            raise ValueError("Goal title must contain 1 to 200 characters.")
        if not isinstance(self.description, str) or len(self.description) > 4000:
            raise ValueError("Goal description must contain at most 4000 characters.")
        goal_id(self.id)
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "category", GoalCategory(self.category))
        object.__setattr__(self, "priority", GoalPriority(self.priority))
        object.__setattr__(self, "status", GoalStatus(self.status))
        if self.target_date is not None:
            if not isinstance(self.target_date, str):
                raise ValueError("Target date must use YYYY-MM-DD.")
            parsed = date.fromisoformat(self.target_date)
            if parsed.isoformat() != self.target_date:
                raise ValueError("Target date must use YYYY-MM-DD.")
        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError("Goal timestamps must be ISO date/time values.")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError("Goal timestamps must include a timezone.")
            object.__setattr__(self, name, parsed.astimezone(timezone.utc).isoformat())
        if self.updated_at < self.created_at:
            raise ValueError("Updated timestamp precedes creation.")
        if type(self.progress) is not int or not 0 <= self.progress <= 100:
            raise ValueError("Goal progress must be an integer from 0 to 100.")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Revision must be a positive integer.")
        if self.status == GoalStatus.COMPLETED and self.progress != 100:
            raise ValueError("Completed goals must have 100 percent progress.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GoalRevision:
    goal_id: str
    revision: int
    action: str
    snapshot: Goal

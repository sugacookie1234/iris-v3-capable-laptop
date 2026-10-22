"""Typed records used by IRIS persistent memory."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class MemoryCategory(StrEnum):
    PREFERENCE = "preference"
    GOAL = "goal"
    PROJECT = "project"
    COMMITMENT = "commitment"
    RELATIONSHIP = "relationship"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    LESSON = "lesson"
    PROFILE = "profile"
    FACT = "fact"
    EVENT = "event"


class MemorySensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class MemoryConfirmation(StrEnum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    REJECTED = "rejected"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MemoryItem:
    category: MemoryCategory | str
    subject: str
    key: str
    value: Any
    summary: str
    source_type: str
    source_ref: str | None = None
    confidence: float = 1.0
    confirmation: MemoryConfirmation | str = MemoryConfirmation.PENDING
    sensitivity: MemorySensitivity | str = MemorySensitivity.NORMAL
    status: MemoryStatus | str = MemoryStatus.ACTIVE
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_accessed_at: str | None = None
    expires_at: str | None = None
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        if not self.subject.strip() or not self.key.strip():
            raise ValueError("Memory subject and key cannot be empty.")
        if not self.summary.strip() or not self.source_type.strip():
            raise ValueError("Memory summary and source_type cannot be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Memory confidence must be between 0 and 1.")

    def value_json(self) -> str:
        return json.dumps(self.value, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_row(cls, row: Any) -> "MemoryItem":
        return cls(
            id=row["id"], category=row["category"], subject=row["subject"],
            key=row["key"], value=json.loads(row["value_json"]),
            summary=row["summary"], source_type=row["source_type"],
            source_ref=row["source_ref"], confidence=row["confidence"],
            confirmation=row["confirmation"], sensitivity=row["sensitivity"],
            status=row["status"], created_at=row["created_at"],
            updated_at=row["updated_at"], last_accessed_at=row["last_accessed_at"],
            expires_at=row["expires_at"], supersedes_id=row["supersedes_id"],
        )


@dataclass(frozen=True)
class MemoryRevision:
    id: str
    memory_id: str
    old_value: Any
    new_value: Any
    reason: str
    created_at: str


@dataclass(frozen=True)
class MemoryCandidate:
    item: MemoryItem
    rationale: str = ""

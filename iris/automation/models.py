"""Typed local automation schedule and execution records."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from enum import StrEnum
from uuid import UUID, uuid4

MAX_RECURRENCE_SECONDS = 365 * 24 * 60 * 60


def _utc(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Schedule time must be an ISO timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Schedule time must be a valid ISO timestamp.") from None
    if parsed.tzinfo is None:
        raise ValueError("Schedule time must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AutomationSchedule:
    id: str
    workflow_name: str
    run_at: str
    recurrence_seconds: int | None = None
    enabled: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise ValueError("Schedule ID is required.")
        try:
            UUID(self.id)
        except (ValueError, AttributeError):
            raise ValueError("Schedule ID must be a UUID.") from None
        if not isinstance(self.workflow_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.workflow_name):
            raise ValueError("Workflow name must be a lowercase identifier.")
        object.__setattr__(self, "run_at", _utc(self.run_at))
        if self.recurrence_seconds is not None and (
            type(self.recurrence_seconds) is not int or not 1 <= self.recurrence_seconds <= MAX_RECURRENCE_SECONDS
        ):
            raise ValueError(f"recurrence_seconds must be between 1 and {MAX_RECURRENCE_SECONDS}.")
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be boolean.")
        for value in (self.created_at, self.updated_at):
            if value:
                _utc(value)

    @classmethod
    def new(cls, workflow_name: str, run_at: str, recurrence_seconds: int | None = None,
            enabled: bool = False, now: str | None = None) -> "AutomationSchedule":
        stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return cls(str(uuid4()), workflow_name, run_at, recurrence_seconds, enabled, stamp, stamp)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "workflow_name": self.workflow_name, "run_at": self.run_at,
                "recurrence_seconds": self.recurrence_seconds, "enabled": self.enabled,
                "created_at": self.created_at, "updated_at": self.updated_at}


class AutomationRunStatus(StrEnum):
    DRY_RUN = "dry_run"
    SUCCESS = "success"
    FAILED = "failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class AutomationRun:
    id: str
    schedule_id: str
    occurrence: str
    workflow_name: str
    status: AutomationRunStatus
    workflow_id: str | None
    started_at: str
    finished_at: str
    failure: str | None = None


@dataclass(frozen=True)
class AutomationApproval:
    id: str
    schedule_id: str
    execution_id: str
    workflow_name: str
    occurrence: str
    created_at: str
    details: tuple[tuple[str, str], ...]
    definition_signature: str = ""
    permissions: tuple[str, ...] = ()
    explicitly_requested: bool = True
    proposal: tuple[tuple[str, str], ...] = ()
    expires_at: str = ""
    status: str = "pending"
    resolved_at: str | None = None
    resolved: bool = False

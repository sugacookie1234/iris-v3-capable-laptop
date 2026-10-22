"""Typed, bounded local notification events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from uuid import UUID, uuid4


class NotificationKind(StrEnum):
    REMINDER = "reminder"
    WORKFLOW_RESULT = "workflow_result"
    APPROVAL_REQUEST = "approval_request"
    FAILURE = "failure"
    EXPIRATION = "expiration"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


_BLOCKED_KEYS = {"credential", "credentials", "api_key", "token", "password",
                 "transcript", "conversation", "note_content", "content", "arguments"}


def safe_payload(value, *, _depth: int = 0):
    if _depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key).casefold()
            if any(blocked in key_text for blocked in _BLOCKED_KEYS):
                continue
            result[str(key)[:64]] = safe_payload(item, _depth=_depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [safe_payload(item, _depth=_depth + 1) for item in value[:32]]
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value[:500]
    return str(value)[:200]


@dataclass(frozen=True)
class NotificationEvent:
    id: str
    kind: NotificationKind
    severity: NotificationSeverity
    source: str
    created_at: str
    payload: dict
    dedup_key: str
    read: bool = False
    dismissed: bool = False

    def __post_init__(self):
        try:
            UUID(self.id)
        except (ValueError, AttributeError):
            raise ValueError("Notification ID must be a UUID.") from None
        if not isinstance(self.kind, NotificationKind):
            object.__setattr__(self, "kind", NotificationKind(self.kind))
        if not isinstance(self.severity, NotificationSeverity):
            object.__setattr__(self, "severity", NotificationSeverity(self.severity))
        if not self.source or len(self.source) > 100:
            raise ValueError("Notification source is required and bounded.")
        try:
            stamp = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Notification timestamp must be ISO formatted.") from None
        if stamp.tzinfo is None:
            raise ValueError("Notification timestamp must include a timezone.")
        if not self.dedup_key or len(self.dedup_key) > 256:
            raise ValueError("Notification deduplication key is required and bounded.")
        object.__setattr__(self, "payload", safe_payload(self.payload))
        if type(self.read) is not bool or type(self.dismissed) is not bool:
            raise ValueError("Notification state must be boolean.")

    @classmethod
    def create(cls, kind, severity, source, payload, dedup_key, *, created_at=None):
        stamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return cls(str(uuid4()), NotificationKind(kind), NotificationSeverity(severity),
                   source, stamp, payload, dedup_key)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind.value, "severity": self.severity.value,
                "source": self.source, "created_at": self.created_at, "payload": self.payload,
                "dedup_key": self.dedup_key, "read": self.read, "dismissed": self.dismissed}

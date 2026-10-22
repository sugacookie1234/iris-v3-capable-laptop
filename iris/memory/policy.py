"""Memory write policy; deliberately independent of model calls and authority tools."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from iris.memory.models import (
    MemoryCandidate, MemoryCategory, MemoryConfirmation, MemorySensitivity,
)
from iris.memory.redaction import reject_secrets


class MemoryWriteAction(StrEnum):
    AUTOMATIC = "automatic"
    CONFIRM = "confirm"
    REJECT = "reject"


_CONFIRM_CATEGORIES = {
    MemoryCategory.RELATIONSHIP,
    MemoryCategory.DECISION,
    MemoryCategory.CONSTRAINT,
    MemoryCategory.PROFILE,
}


@dataclass(frozen=True)
class MemoryPolicyDecision:
    action: MemoryWriteAction
    reason: str


def decide_write(candidate: MemoryCandidate) -> MemoryPolicyDecision:
    """Classify a proposed write without persisting or invoking a model."""
    item = candidate.item
    reject_secrets(item.value, item.summary, item.subject, item.key)
    if item.sensitivity == MemorySensitivity.RESTRICTED:
        return MemoryPolicyDecision(MemoryWriteAction.REJECT, "restricted memory is not stored")
    if item.confirmation == MemoryConfirmation.REJECTED:
        return MemoryPolicyDecision(MemoryWriteAction.REJECT, "user rejected this memory")
    if item.confirmation == MemoryConfirmation.CONFIRMED:
        return MemoryPolicyDecision(MemoryWriteAction.AUTOMATIC, "explicitly confirmed")
    if item.sensitivity == MemorySensitivity.SENSITIVE or item.category in _CONFIRM_CATEGORIES:
        return MemoryPolicyDecision(MemoryWriteAction.CONFIRM, "user confirmation is required")
    return MemoryPolicyDecision(MemoryWriteAction.AUTOMATIC, "low-risk structured memory")

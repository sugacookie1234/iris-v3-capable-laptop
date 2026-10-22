import unittest

from iris.memory.models import (
    MemoryCandidate, MemoryCategory, MemoryConfirmation, MemoryItem,
    MemorySensitivity,
)
from iris.memory.policy import MemoryWriteAction, decide_write


def candidate(**kwargs):
    values = dict(
        category=MemoryCategory.PREFERENCE, subject="user", key="style",
        value="concise", summary="Prefers concise answers.", source_type="explicit",
    )
    values.update(kwargs)
    return MemoryCandidate(MemoryItem(**values))


class MemoryPolicyTests(unittest.TestCase):
    def test_low_risk_pending_memory_can_be_automatic(self):
        self.assertEqual(decide_write(candidate()).action, MemoryWriteAction.AUTOMATIC)

    def test_sensitive_and_consequential_memory_requires_confirmation(self):
        self.assertEqual(
            decide_write(candidate(category=MemoryCategory.CONSTRAINT)).action,
            MemoryWriteAction.CONFIRM,
        )
        self.assertEqual(
            decide_write(candidate(sensitivity=MemorySensitivity.SENSITIVE)).action,
            MemoryWriteAction.CONFIRM,
        )

    def test_restricted_or_rejected_memory_is_rejected(self):
        self.assertEqual(
            decide_write(candidate(sensitivity=MemorySensitivity.RESTRICTED)).action,
            MemoryWriteAction.REJECT,
        )
        self.assertEqual(
            decide_write(candidate(confirmation=MemoryConfirmation.REJECTED)).action,
            MemoryWriteAction.REJECT,
        )

import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from iris.notifications import NotificationEvent, NotificationKind, NotificationSeverity, NotificationStore


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NotificationStore(Path(self.tmp.name) / "notifications.sqlite3")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, key, stamp="2026-01-01T00:00:00Z", payload=None):
        return NotificationEvent.create(NotificationKind.FAILURE, NotificationSeverity.ERROR, "test",
                                        payload or {"workflow": "demo"}, key, created_at=stamp)

    def test_ordering_deduplication_and_state(self):
        first = self.store.publish(self.event("same", "2026-01-01T00:00:00Z"))
        duplicate = self.store.publish(self.event("same", "2026-01-02T00:00:00Z", {"workflow": "new"}))
        self.assertEqual(duplicate.id, first.id)
        second = self.store.publish(self.event("later", "2026-01-03T00:00:00Z"))
        self.assertEqual(self.store.list()[0].id, second.id)
        self.store.mark_read(first.id)
        self.assertEqual(self.store.list(include_read=False), (second,))
        self.store.dismiss(first.id)
        self.store.dismiss(second.id)
        self.assertEqual(self.store.list(), ())

    def test_redaction_and_bounded_payload(self):
        event = self.store.publish(self.event("safe", payload={"api_key": "secret", "arguments": {"token": "x"},
                                                                 "workflow": "demo", "nested": {"value": "ok"}}))
        self.assertNotIn("api_key", event.payload)
        self.assertNotIn("arguments", event.payload)
        self.assertEqual(event.payload["workflow"], "demo")

    def test_retention_by_age_and_count(self):
        self.store.publish(self.event("old", "2025-01-01T00:00:00Z"))
        for index in range(3):
            self.store.publish(self.event(f"new-{index}", f"2026-01-0{index + 1}T00:00:00Z"))
        removed = self.store.prune(now=datetime(2026, 2, 1, tzinfo=timezone.utc), max_events=2, max_age_days=30)
        self.assertEqual(removed, 2)
        self.assertEqual(len(self.store.list()), 2)


if __name__ == "__main__":
    unittest.main()

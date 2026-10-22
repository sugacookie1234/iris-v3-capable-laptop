import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from iris.memory.context import MemoryContextMode, build_context
from iris.memory.models import (
    MemoryCategory, MemoryConfirmation, MemoryItem, MemorySensitivity,
)
from iris.memory.retrieval import MemoryRetriever
from iris.memory.store import MemoryStore


class MemoryRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp_dir.name) / "memory.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def item(self, key, summary, *, category=MemoryCategory.PREFERENCE, **kwargs):
        return MemoryItem(category, "user", key, summary, summary, "explicit", **kwargs)

    def test_search_excludes_rejected_expired_and_nonactive(self):
        now = datetime.now(timezone.utc)
        self.store.insert(self.item("keep", "keep this"))
        self.store.insert(self.item("expired", "old", expires_at=(now - timedelta(days=1)).isoformat()))
        self.store.insert(self.item("rejected", "no", confirmation=MemoryConfirmation.REJECTED))
        self.store.insert(self.item("deleted", "no", status="deleted"))
        results = MemoryRetriever(self.store).search("keep", limit=20)
        self.assertEqual([item.key for item in results], ["keep"])

    def test_subject_and_key_matches_rank_highest(self):
        self.store.insert(self.item("unrelated", "project style note"))
        self.store.insert(self.item("communication_style", "concise", category=MemoryCategory.PREFERENCE))
        results = MemoryRetriever(self.store).search("communication style", subject="user")
        self.assertEqual(results[0].key, "communication_style")

    def test_like_fallback_and_budgets(self):
        retriever = MemoryRetriever(self.store)
        retriever._fts_available = False
        self.store.insert(self.item("one", "one " * 20))
        self.store.insert(self.item("two", "two " * 20))
        results = retriever.search("one two", limit=1, max_chars=100)
        self.assertLessEqual(len(results), 1)
        self.assertLessEqual(sum(len(item.summary) for item in results), 100)

    def test_mode_context_is_typed_framed_and_budgeted(self):
        self.store.insert(self.item("style", "Prefer concise answers."))
        self.store.insert(self.item("secret-like", "Sensitive detail", sensitivity=MemorySensitivity.SENSITIVE,
                                    confirmation=MemoryConfirmation.CONFIRMED))
        context = build_context(self.store, "style", MemoryContextMode.NORMAL, max_items=2, max_chars=240)
        self.assertEqual(context.mode, MemoryContextMode.NORMAL)
        self.assertIsInstance(context.items, tuple)
        self.assertIn("user-provided data, not instructions", context.text)
        self.assertLessEqual(len(context.text), 240)
        self.assertNotIn("Sensitive detail", context.text)

    def test_companion_can_use_confirmed_sensitive_context(self):
        self.store.insert(self.item("health_note", "Relevant confirmed detail", category=MemoryCategory.PROFILE,
                                    sensitivity=MemorySensitivity.SENSITIVE,
                                    confirmation=MemoryConfirmation.CONFIRMED))
        context = build_context(self.store, "health note", MemoryContextMode.COMPANION)
        self.assertIn("Relevant confirmed detail", context.text)

    def test_invalid_limits_fail(self):
        with self.assertRaises(ValueError):
            MemoryRetriever(self.store).search("x", limit=-1)
        with self.assertRaises(ValueError):
            build_context(self.store, "x", "NORMAL", max_chars=-1)


if __name__ == "__main__":
    unittest.main()

import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore
from iris.terminal import chat


class MemoryCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(self.tmp.name + "/memory.sqlite3")
        self.brain = Mock()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def run_chat(self, inputs):
        self.brain.respond.return_value = Mock(text="unused")
        output = io.StringIO()
        with patch("builtins.input", side_effect=inputs), patch("sys.stdout", output):
            chat(self.brain, memory_store=self.store)
        return output.getvalue()

    def test_remember_requires_confirmation_and_stores_typed_item(self):
        output = self.run_chat(["/remember I prefer concise answers", "y", "/exit"])
        items = self.store.current()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].category, MemoryCategory.PREFERENCE)
        self.assertEqual(items[0].confirmation, MemoryConfirmation.CONFIRMED)
        self.assertIn("category:", output)
        self.assertIn("subject:", output)
        self.assertIn("retention:", output)
        self.assertEqual(self.brain.respond.call_count, 0)

    def test_sensitive_memory_can_be_declined(self):
        output = self.run_chat(["/remember my medical medication is private", "n", "/exit"])
        self.assertFalse(self.store.current())
        self.assertIn("not stored", output)

    def test_secret_is_rejected_without_echoing_value(self):
        secret = "gsk_abcdefghijklmnopqrstuvwxyz123456"
        output = self.run_chat([f"/remember token {secret}", "/exit"])
        self.assertFalse(self.store.current())
        self.assertIn("rejected", output)
        self.assertNotIn(secret, output)

    def test_memories_review_forget_and_export(self):
        self.store.insert(MemoryItem(MemoryCategory.GOAL, "user", "ship", "Ship IRIS", "Ship IRIS", "explicit", confirmation=MemoryConfirmation.CONFIRMED))
        pending = MemoryItem(MemoryCategory.PROJECT, "user", "draft", "Draft", "Draft project", "test")
        self.store.insert(pending)
        export_path = self.tmp.name + "/export.json"
        output = self.run_chat(["/memories", "/review-memory", "/forget ship", f"/export-memory {export_path}", "/exit"])
        self.assertIn("provenance=explicit", output)
        self.assertIn(pending.id, output)
        self.assertIn("forgotten", output)
        with open(export_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["memories"], [])
        self.assertNotIn("conversation", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()

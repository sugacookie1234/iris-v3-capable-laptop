import json
import os
import tempfile
import unittest
from pathlib import Path

from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore, SCHEMA_VERSION
from iris.memory.redaction import MemoryRedactionError


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "nested" / "memory.sqlite3"
        self.store = MemoryStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def item(self, key="style", value="concise"):
        return MemoryItem(
            MemoryCategory.PREFERENCE, "user", key, value,
            f"User preference: {value}.", "explicit",
            confirmation=MemoryConfirmation.CONFIRMED,
        )

    def test_creates_schema_and_secure_file(self):
        self.assertEqual(self.store._connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()[0], str(SCHEMA_VERSION))
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_insert_fetch_and_export(self):
        item = self.store.insert(self.item())
        self.assertEqual(self.store.fetch(item.id).value, "concise")
        exported = self.store.export()
        self.assertEqual(len(exported["memory_items"]), 1)
        self.assertEqual(json.loads(exported["memory_items"][0]["value_json"]), "concise")

    def test_supersede_is_append_only_and_records_revision(self):
        original = self.store.insert(self.item(value="brief"))
        replacement = self.store.supersede(original.id, self.item(value="detailed"), "user correction")
        self.assertEqual(self.store.fetch(original.id).status, "superseded")
        self.assertEqual(self.store.fetch(replacement.id).supersedes_id, original.id)
        revision = self.store._connection.execute("SELECT * FROM memory_revisions").fetchone()
        self.assertEqual(revision["reason"], "user correction")

    def test_forget_and_hard_purge(self):
        item = self.store.insert(self.item())
        self.assertTrue(self.store.forget(item.id))
        self.assertEqual(self.store.fetch(item.id).status, "deleted")
        self.assertTrue(self.store.hard_purge(item.id))
        self.assertIsNone(self.store.fetch(item.id))
        self.assertFalse(self.store.hard_purge(item.id))

    def test_secret_is_rejected_before_insert(self):
        with self.assertRaises(MemoryRedactionError):
            self.store.insert(self.item(value={"password": "private"}))

    def test_environment_path_override(self):
        other = Path(self.temp_dir.name) / "override.sqlite3"
        self.store.close()
        old = os.environ.get("IRIS_MEMORY_PATH")
        try:
            os.environ["IRIS_MEMORY_PATH"] = str(other)
            with MemoryStore() as override:
                self.assertEqual(override.path, other)
        finally:
            if old is None:
                os.environ.pop("IRIS_MEMORY_PATH", None)
            else:
                os.environ["IRIS_MEMORY_PATH"] = old


if __name__ == "__main__":
    unittest.main()

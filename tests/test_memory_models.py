import unittest

from iris.memory.models import (
    MemoryCategory, MemoryConfirmation, MemoryItem, MemorySensitivity,
)


class MemoryModelTests(unittest.TestCase):
    def test_item_serializes_structured_value(self):
        item = MemoryItem(
            category=MemoryCategory.PREFERENCE,
            subject="user",
            key="answer_style",
            value={"concise": True, "format": "commands"},
            summary="Prefer concise answers with commands.",
            source_type="explicit",
            confirmation=MemoryConfirmation.CONFIRMED,
        )
        self.assertIn('"concise": true', item.value_json())
        self.assertEqual(item.sensitivity, MemorySensitivity.NORMAL)

    def test_invalid_item_is_rejected(self):
        with self.assertRaises(ValueError):
            MemoryItem("preference", "", "style", "x", "summary", "explicit")
        with self.assertRaises(ValueError):
            MemoryItem("preference", "user", "style", "x", "summary", "explicit", confidence=2)

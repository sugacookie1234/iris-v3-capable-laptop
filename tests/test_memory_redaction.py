import unittest

from iris.memory.redaction import MemoryRedactionError, contains_secret, reject_secrets


class MemoryRedactionTests(unittest.TestCase):
    def test_rejects_credentials_and_headers(self):
        values = (
            "Authorization: Bearer abcdefghijkl",
            "password=do-not-store",
            "Cookie: session=private",
            "-----BEGIN PRIVATE KEY-----",
            {"api_key": "sk-test-123456789012"},
            "gsk_1234567890123456",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(contains_secret(value))
                with self.assertRaises(MemoryRedactionError):
                    reject_secrets(value)

    def test_allows_ordinary_structured_memory(self):
        self.assertFalse(contains_secret({"preference": "concise answers", "count": 2}))
        reject_secrets("Prefer dark mode and short responses.")

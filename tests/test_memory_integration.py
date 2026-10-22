import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from iris.brain.llm import LLMMessage, MessageRole
from iris.memory.integration import assemble_reasoning_context, respond_with_memory
from iris.memory.context import MemoryContextMode, build_context
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore


class MemoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        saved = patch("iris.local_config.read_saved", return_value={})
        saved.start()
        self.addCleanup(saved.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp_dir.name) / "memory.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def add(self, key, summary, *, category=MemoryCategory.PREFERENCE, **kwargs):
        item = MemoryItem(category, "user", key, summary, summary, "test", **kwargs)
        self.store.insert(item)
        return item

    def test_assembler_retrieves_relevant_memory_and_excludes_unrelated(self):
        self.add("coffee", "The user prefers dark roast coffee.")
        self.add("holiday", "The user plans a holiday in July.")
        context = assemble_reasoning_context(self.store, "Which coffee should I buy?")
        self.assertIsNotNone(context)
        self.assertIn("dark roast", context.text)
        self.assertNotIn("holiday", context.text)

    def test_assembler_enforces_category_expiry_and_size(self):
        now = datetime.now(timezone.utc)
        self.add("expired", "coffee expired", expires_at=(now - timedelta(days=1)).isoformat())
        self.add("relationship", "Launch the coffee project.", category=MemoryCategory.RELATIONSHIP)
        self.add("preference", "Use a short answer.")
        context = assemble_reasoning_context(self.store, "coffee preference",)
        self.assertIsNotNone(context)
        self.assertNotIn("coffee expired", context.text)
        self.assertNotIn("Launch the coffee project", context.text)
        self.assertLessEqual(len(context.text), context.max_chars)

    def test_empty_store_and_empty_message_produce_no_context(self):
        self.assertIsNone(assemble_reasoning_context(self.store, "hello"))
        self.assertIsNone(assemble_reasoning_context(None, "hello"))
        self.assertIsNone(assemble_reasoning_context(self.store, "  "))

    def test_secret_rows_are_redacted_before_prompt_rendering(self):
        secret = MemoryItem(
            MemoryCategory.PREFERENCE, "user", "credential", "api_key=hidden",
            "api_key=hidden", "legacy-import",
        )
        with patch("iris.memory.context.MemoryRetriever.search", return_value=(secret,)):
            context = build_context(self.store, "credential", MemoryContextMode.NORMAL)
        self.assertEqual(context.text, "")

    def test_latest_message_retrieval_keeps_history_separate(self):
        self.add("latest", "Use concise coffee recommendations.")
        brain = Mock()
        brain.respond.return_value = Mock(text="done")
        response = respond_with_memory(
            brain,
            "coffee recommendation",
            memory_store=self.store,
            history=(LLMMessage(MessageRole.USER, "unrelated old topic"),),
        )
        self.assertEqual(response.text, "done")
        self.assertEqual(brain.respond.call_args.kwargs["history"][0].content, "unrelated old topic")
        self.assertNotIn("unrelated old topic", brain.respond.call_args.kwargs["memory_context"].text)

    def test_failed_turn_does_not_persist_any_memory(self):
        before = self.store.current()
        brain = Mock()
        brain.respond.side_effect = RuntimeError("provider failure")
        with self.assertRaises(RuntimeError):
            respond_with_memory(brain, "remember this failed request", memory_store=self.store)
        self.assertEqual(self.store.current(), before)

    def test_one_shot_voice_uses_canonical_memory_context(self):
        self.add("coffee", "Prefer dark roast coffee recommendations.")
        captured = {}

        class FakeBrain:
            def respond(self, text, **kwargs):
                captured["text"] = text
                captured["kwargs"] = kwargs
                return Mock(text="response")

        class FakeRunner:
            pass

        def fake_input(session, **_kwargs):
            captured["session"] = session
            return FakeRunner()

        with patch("iris.voice_once.load_config", return_value=object()), \
             patch("iris.voice_once.create_brain", return_value=FakeBrain()), \
             patch("iris.voice_once._one_shot_transcriber", return_value=object()), \
             patch("iris.voice_once.WindowsInteropAudioSink"), \
             patch("iris.voice_once.FishAudioSynthesizer"), \
             patch("iris.voice_once.SoundDeviceOneShotInput", side_effect=fake_input):
            from iris.voice_once import build_voice_flow
            runner, _sink = build_voice_flow(memory_store=self.store)
            self.assertIsNotNone(runner)
            self.assertEqual(captured["session"].responder("coffee recommendation"), "response")
            self.assertEqual(captured["text"], "coffee recommendation")
            self.assertIn("dark roast", captured["kwargs"]["memory_context"].text)


if __name__ == "__main__":
    unittest.main()

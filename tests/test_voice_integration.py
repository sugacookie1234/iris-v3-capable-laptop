import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from iris.memory.integration import respond_with_memory
from iris.memory.store import MemoryStore
from iris.obsidian import ObsidianKnowledgeAdapter
from iris.voice import InMemoryPcmRecorder, LocalPushToTalkRecognizer, VoiceSession
from iris.voice_clap import _VoskTranscriber


class _FakeVosk:
    def __init__(self, _model, _rate):
        pass

    def AcceptWaveform(self, _audio):
        return True

    def Result(self):
        return '{"text":"what is the launch plan"}'

    def FinalResult(self):
        return '{"text":""}'


class VoiceIntegrationTests(unittest.TestCase):
    def test_injected_audio_reaches_canonical_context_brain_and_fish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vault index.md").write_text(
                "# Plans\n[Launch plan](Launch.md)\n", encoding="utf-8"
            )
            (root / "Launch.md").write_text(
                "The launch plan uses a staged release.", encoding="utf-8"
            )
            store = MemoryStore(root / "memory.sqlite3")
            brain = Mock()
            brain.respond.return_value = Mock(text="staged response")
            fish = Mock()
            transcriber = _VoskTranscriber(object(), _FakeVosk)
            recorder = InMemoryPcmRecorder()
            recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
            knowledge = ObsidianKnowledgeAdapter(str(root))

            session = VoiceSession(
                recognizer=recognizer,
                synthesizer=fish,
                responder=lambda text: respond_with_memory(
                    brain, text, memory_store=store, obsidian=knowledge
                ).text,
            )
            session.press()
            recorder.append([0.1, -0.1, 0.2])
            turn = session.release()

            self.assertEqual(turn.transcript, "what is the launch plan")
            self.assertEqual(turn.response, "staged response")
            self.assertEqual(fish.speak.call_count, 1)
            context = brain.respond.call_args.kwargs["memory_context"].text
            self.assertIn("staged release", context)
            self.assertEqual(store.current(), ())
            store.close()

    def test_empty_recognition_stops_before_brain_action_or_memory_write(self):
        class EmptyVosk(_FakeVosk):
            def Result(self):
                return '{"text":""}'

        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.sqlite3")
            brain = Mock()
            fish = Mock()
            transcriber = _VoskTranscriber(object(), EmptyVosk)
            recorder = InMemoryPcmRecorder()
            session = VoiceSession(
                recognizer=LocalPushToTalkRecognizer(recorder, transcriber),
                synthesizer=fish,
                responder=lambda text: respond_with_memory(
                    brain, text, memory_store=store
                ).text,
            )
            session.press()
            recorder.append([0.1, 0.0])
            self.assertIsNone(session.release())
            brain.respond.assert_not_called()
            fish.speak.assert_not_called()
            self.assertEqual(store.current(), ())
            store.close()


if __name__ == "__main__":
    unittest.main()

import sys
import types
import unittest
from unittest.mock import patch

from iris.voice import (LocalSpeechRecognizerAdapter, LocalSpeechSynthesizerAdapter,
                        VoiceBackendError, VoiceSession, VoskSpeechRecognizer)
from iris.voice.__main__ import main


class FakeRecognizer:
    def __init__(self): self.started = 0; self.stopped = 0
    def start_listening(self): self.started += 1
    def stop_listening(self): self.stopped += 1; return "local words"


class FakeSynth:
    def __init__(self): self.spoken = []
    def speak(self, text): self.spoken.append(text)
    def stop(self): pass


class VoiceAdapterTests(unittest.TestCase):
    def test_injected_fake_adapters_work_with_session(self):
        recognizer, synth = FakeRecognizer(), FakeSynth()
        session = VoiceSession(recognizer=LocalSpeechRecognizerAdapter(recognizer),
                               synthesizer=LocalSpeechSynthesizerAdapter(synth),
                               responder=lambda text: "reply: " + text)
        session.press(); turn = session.release()
        self.assertEqual(turn.response, "reply: local words")
        self.assertEqual(synth.spoken, ["reply: local words"])

    def test_missing_optional_backend_is_clear_and_lazy(self):
        adapter = LocalSpeechRecognizerAdapter(module_name="iris_missing_voice_backend")
        with self.assertRaises(VoiceBackendError) as context:
            adapter.start_listening()
        self.assertIn("not installed", str(context.exception))
        self.assertNotIn("iris_missing_voice_backend", sys.modules)

    def test_vosk_adapter_does_not_import_until_push_to_talk(self):
        adapter = VoskSpeechRecognizer()
        self.assertNotIn("vosk", sys.modules)
        with patch("iris.voice.adapters.importlib.import_module", side_effect=ImportError):
            with self.assertRaises(VoiceBackendError):
                adapter.start_listening()

    def test_one_shot_text_mode_never_requires_audio_backend(self):
        self.assertEqual(main(["--text", "hello"]), 0)

    def test_one_shot_missing_backend_does_not_crash(self):
        with patch("iris.voice.adapters.importlib.import_module", side_effect=ImportError):
            self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()

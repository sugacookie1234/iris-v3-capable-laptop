import struct
import unittest

from iris.voice import FasterWhisperSpeechRecognizer


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisperModel:
    def __init__(self, segments):
        self.segments = segments
        self.audio = None
        self.options = None

    def transcribe(self, audio, **options):
        self.audio = audio
        self.options = options
        return iter(self.segments), object()


class WhisperTests(unittest.TestCase):
    def test_fake_whisper_receives_in_memory_pcm_and_returns_joined_text(self):
        model = FakeWhisperModel([FakeSegment("hello"), FakeSegment("IRIS")])
        recognizer = FasterWhisperSpeechRecognizer(model=model)
        audio = struct.pack("<4h", 0, 1200, -1200, 0)

        self.assertEqual(recognizer.transcribe(audio), "hello IRIS")
        self.assertIsNotNone(model.audio)
        self.assertNotIsInstance(model.audio, (bytes, bytearray, str))
        self.assertEqual(model.options["language"], "en")
        self.assertTrue(model.options["vad_filter"])

    def test_fake_whisper_empty_segments_return_empty_text(self):
        recognizer = FasterWhisperSpeechRecognizer(model=FakeWhisperModel([]))
        audio = struct.pack("<2h", 0, 0)
        self.assertEqual(recognizer.transcribe(audio), "")


if __name__ == "__main__":
    unittest.main()

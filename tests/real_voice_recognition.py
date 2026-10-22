"""Opt-in real local speech validation; intentionally excluded from discovery.

The fixture is supplied by the operator through IRIS_REAL_SPEECH_FIXTURE and
must be a small non-private mono 16-bit PCM WAV whose known wording is supplied
through IRIS_REAL_SPEECH_TEXT.  No fixture or model is downloaded by this test.
Run explicitly with IRIS_RUN_REAL_RECOGNITION=1.
"""
from __future__ import annotations

import os
import struct
import unittest
import wave
from pathlib import Path


class RealVoiceRecognitionTests(unittest.TestCase):
    def test_configured_local_backend_recognizes_fixture(self):
        if os.environ.get("IRIS_RUN_REAL_RECOGNITION") != "1":
            raise unittest.SkipTest("real recognition validation is opt-in")
        fixture = os.environ.get("IRIS_REAL_SPEECH_FIXTURE", "").strip()
        expected = os.environ.get("IRIS_REAL_SPEECH_TEXT", "").strip().casefold()
        if not fixture or not expected:
            raise unittest.SkipTest("set a known-wording local speech fixture and expected text")
        path = Path(fixture)
        if not path.is_file():
            raise unittest.SkipTest("configured speech fixture is unavailable")
        with wave.open(str(path), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                if source.getsampwidth() != 2:
                    raise unittest.SkipTest("speech fixture must use 16-bit PCM")
            channels = source.getnchannels()
            raw = source.readframes(source.getnframes())
            rate = source.getframerate()
        # Canonicalize the public fixture in memory to the same mono/16 kHz
        # PCM16LE shape produced by IRIS capture. No derived recording is saved.
        samples = list(struct.iter_unpack("<h", raw))
        if channels > 1:
            mono = [sum(samples[index + offset][0] for offset in range(channels)) // channels
                    for index in range(0, len(samples), channels)]
        else:
            mono = [item[0] for item in samples]
        target_rate = 16_000
        if rate != target_rate:
            target_count = max(1, round(len(mono) * target_rate / rate))
            mono = [mono[min(len(mono) - 1, round(index * rate / target_rate))]
                    for index in range(target_count)]
        audio = b"".join(struct.pack("<h", max(-32768, min(32767, value))) for value in mono)
        rate = target_rate
        backend = os.environ.get("IRIS_REAL_RECOGNIZER", "vosk").strip().lower()
        if backend == "vosk":
            model_path = os.environ.get("IRIS_VOSK_MODEL", "").strip()
            if not model_path:
                raise unittest.SkipTest("IRIS_VOSK_MODEL is unavailable")
            try:
                from vosk import KaldiRecognizer, Model
                from iris.voice_clap import _VoskTranscriber
                recognizer = _VoskTranscriber(Model(model_path), KaldiRecognizer)
                recognizer.start_stream(rate)
                recognizer.accept_stream(audio)
                actual = recognizer.transcribe(audio)
            except ImportError:
                raise unittest.SkipTest("Vosk is unavailable") from None
        elif backend == "whisper":
            model_path = os.environ.get("IRIS_WHISPER_MODEL_PATH", "").strip()
            if not model_path or not Path(model_path).exists():
                raise unittest.SkipTest("IRIS_WHISPER_MODEL_PATH is unavailable")
            try:
                from iris.voice.adapters import FasterWhisperSpeechRecognizer
                actual = FasterWhisperSpeechRecognizer(
                    model_name=model_path,
                    device=os.environ.get("IRIS_WHISPER_DEVICE", "cpu"),
                    compute_type=os.environ.get("IRIS_WHISPER_COMPUTE_TYPE", "int8"),
                ).transcribe(audio)
            except ImportError:
                raise unittest.SkipTest("faster-whisper is unavailable") from None
        else:
            raise unittest.SkipTest("IRIS_REAL_RECOGNIZER must be vosk or whisper")
        self.assertIn(expected, actual.casefold())


if __name__ == "__main__":
    unittest.main()

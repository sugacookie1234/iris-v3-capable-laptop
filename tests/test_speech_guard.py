"""Real local VAD checks with public speech and synthetic non-speech; no API calls."""
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import wave

from iris.desktop.speech_guard import accepted_text, has_speech


class TranscriptGuardTests(unittest.TestCase):
    def test_english_commands_names_and_numbers_survive(self):
        for text in ('Stop.', 'No', '40', 'Open Chrome', 'Search for Beyoncé', 'What does 東京 mean?'):
            self.assertEqual(accepted_text(text, 'en'), text)

    def test_language_conflict_and_non_speech_are_not_commands(self):
        for text, code in (('こんにちは', None), ('これはノイズです', 'en'),
                           ('Bonjour', 'fr'), ('...', None), ('[laughter]', 'en')):
            self.assertEqual(accepted_text(text, 'en', code), '')
        self.assertEqual(accepted_text('こんにちは', 'auto', 'ja'), 'こんにちは')


@unittest.skipUnless(importlib.util.find_spec('faster_whisper') and importlib.util.find_spec('numpy'),
                     'Installed speech dependencies required for bundled VAD acceptance')
class RealSpeechGuardTests(unittest.TestCase):
    @staticmethod
    def wav(samples):
        output = io.BytesIO()
        with wave.open(output, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes((samples.clip(-1, 1) * 32767).astype('<i2').tobytes())
        return output.getvalue()

    def test_silence_hum_tone_claps_and_random_noise_do_not_qualify(self):
        import numpy as np
        rng = np.random.default_rng(43)
        t = np.arange(32000) / 16000
        claps = np.zeros(32000)
        for start in (4000, 9000):
            claps[start:start + 640] = rng.uniform(-1, 1, 640) * np.exp(-np.arange(640) / 90)
        sounds = {'silence': np.zeros(32000), 'hum': .1 * np.sin(2 * np.pi * 60 * t),
            'tone': .2 * np.sin(2 * np.pi * 880 * t), 'claps': claps,
            'noise': rng.normal(0, .12, 32000)}
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network allowed')):
            for name, samples in sounds.items():
                with self.subTest(sound=name):
                    self.assertFalse(has_speech(self.wav(samples)))

    def test_public_speech_and_quieter_speech_are_accepted_without_whisper_loading(self):
        from faster_whisper.audio import decode_audio
        fixture = Path(__file__).parent / 'fixtures' / 'harvard.wav'
        if not fixture.is_file():
            self.skipTest('Public Harvard speech fixture is unavailable')
        samples = decode_audio(str(fixture), sampling_rate=16000)[:6 * 16000]
        with patch('faster_whisper.WhisperModel', side_effect=AssertionError('No speech decoder needed')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('No network allowed')):
            self.assertTrue(has_speech(self.wav(samples)))
            self.assertTrue(has_speech(self.wav(samples * .1)))

    def test_missing_vad_never_silently_disables_guard(self):
        import numpy as np
        with patch('faster_whisper.vad.get_speech_timestamps', side_effect=RuntimeError('private-path')):
            with self.assertRaisesRegex(ValueError, 'Run setup.bat') as error:
                has_speech(self.wav(np.ones(8000) * .1))
        self.assertNotIn('private-path', str(error.exception))


if __name__ == '__main__':
    unittest.main()

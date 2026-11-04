import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch
from iris.desktop import recognition as module
from tests.test_desktop_transcription import wav


class RecognitionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.audio = wav()
        self.settings = {'IRIS_FISH_API_KEY': 'test-only-key'}
        self.local_status = {'engine': 'faster-whisper', 'model': 'large-v3-turbo',
                             'device': 'cpu', 'compute_type': 'int8', 'fallback': 'No NVIDIA device.'}
        self.opener = Mock()
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.read.return_value = b'{"text":" Fish works "}'
        self.opener.open.return_value = self.response
        for item in [patch.object(module.urllib.request, 'build_opener', return_value=self.opener),
                     patch.object(module, 'has_speech', return_value=True),
                     patch.object(module.local, 'speech_status', return_value=dict(self.local_status)),
                     patch.object(module, '_status', {})]:
            item.start()
            self.addCleanup(item.stop)
        local_patch = patch.object(module.local, 'transcribe', return_value='Local works')
        self.local = local_patch.start()
        self.addCleanup(local_patch.stop)

    def call(self, settings=None):
        return module.transcribe(self.settings if settings is None else settings, self.audio, 'audio/wav')

    def test_fish_success_has_correct_request_and_never_loads_whisper(self):
        self.assertEqual(self.call(), 'Fish works')
        self.local.assert_not_called()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.fish.audio/v1/asr')
        self.assertEqual(request.get_header('Model'), 'transcribe-1-pro')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-key')
        self.assertIn(b'name="audio"; filename="request.wav"', request.data)
        self.assertIn(self.audio, request.data)
        self.assertIn(b'name="diarize"\r\n\r\nfalse', request.data)
        self.assertEqual(self.opener.open.call_args.kwargs['timeout'], 12)
        self.assertEqual(module.speech_status()['engine'], 'fish')

    def test_credit_key_rate_and_server_failures_fall_back_without_leaking_response(self):
        for code in (401, 402, 403, 429, 500, 503):
            with self.subTest(code=code):
                self.opener.open.side_effect = urllib.error.HTTPError(
                    'https://api.fish.audio/v1/asr', code, 'private server detail', {}, io.BytesIO(b'private body'))
                self.assertEqual(self.call(), 'Local works')
                status = module.speech_status()
                self.assertEqual(status['engine'], 'faster-whisper')
                self.assertIn('Using local Whisper', status['fallback'])
                self.assertNotIn('private', status['fallback'])
        self.assertEqual(self.local.call_count, 6)

    def test_network_errors_fall_back_and_next_recording_retries_fish(self):
        self.opener.open.side_effect = TimeoutError('private address')
        self.assertEqual(self.call(), 'Local works')
        self.opener.open.side_effect = None
        self.assertEqual(self.call(), 'Fish works')
        self.assertIsNone(module.speech_status()['fallback'])
        self.local.assert_called_once()

    def test_invalid_responses_fall_back(self):
        for raw in (b'bad json', b'{}', b'[]', b'{"text":null}', b'x' * 64001):
            with self.subTest(raw=raw[:20]):
                self.response.read.return_value = raw
                self.assertEqual(self.call(), 'Local works')
        self.assertEqual(self.local.call_count, 5)

    def test_silence_is_not_a_provider_failure(self):
        self.response.read.return_value = b'{"text":""}'
        self.assertEqual(self.call(), '')
        self.local.assert_not_called()

    def test_local_noise_gate_prevents_cloud_and_whisper_calls(self):
        with patch.object(module, 'has_speech', return_value=False):
            self.assertEqual(self.call(), '')
        self.opener.open.assert_not_called()
        self.local.assert_not_called()
        self.assertEqual(module.speech_status()['engine'], 'speech-guard')

    def test_broken_noise_gate_never_uploads_audio(self):
        with patch.object(module, 'has_speech', side_effect=ValueError('Repair voice input')):
            with self.assertRaisesRegex(ValueError, 'Repair voice input'):
                self.call()
        self.opener.open.assert_not_called()
        self.local.assert_not_called()
        self.assertFalse(module._lock.locked())

    def test_english_mode_rejects_language_conflicts_without_retrying_noise(self):
        for response in ({'text': 'ランダムな音', 'language_code': 'ja'},
                         {'text': 'ランダムな音'}, {'text': 'Bonjour', 'language_code': 'fr'},
                         {'text': '[laughter]'}, {'text': '...'}):
            self.response.read.return_value = json.dumps(response).encode()
            self.assertEqual(self.call(), '')
        self.local.assert_not_called()

    def test_auto_language_preserves_multilingual_requests(self):
        self.response.read.return_value = json.dumps({'text': 'こんにちは', 'language_code': 'ja'}).encode()
        self.assertEqual(self.call({**self.settings, 'IRIS_STT_LANGUAGE': 'auto'}), 'こんにちは')
        self.assertNotIn(b'name="language"', self.opener.open.call_args.args[0].data)

    def test_local_only_never_contacts_fish(self):
        self.assertEqual(self.call({'IRIS_STT_PROVIDER': 'local'}), 'Local works')
        self.opener.open.assert_not_called()
        self.assertEqual(module.speech_status()['engine'], 'faster-whisper')

    def test_missing_key_uses_local(self):
        self.assertEqual(self.call({}), 'Local works')
        self.opener.open.assert_not_called()
        self.assertIn('key', module.speech_status()['fallback'])

    def test_missing_local_model_after_cloud_failure_is_actionable(self):
        self.local.side_effect = ValueError('Run setup.bat to install voice input.')
        with self.assertRaisesRegex(ValueError, 'Local fallback failed.*setup.bat'):
            self.call({})
        self.assertEqual(module.speech_status()['device'], 'unavailable')
        self.assertFalse(module._lock.locked())

    def test_bad_audio_never_leaves_computer(self):
        with self.assertRaises(ValueError):
            module.transcribe(self.settings, b'bad', 'audio/wav')
        self.opener.open.assert_not_called()
        self.local.assert_not_called()

    def test_busy_request_does_not_send_audio(self):
        module._lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'another recording'):
                self.call()
        finally:
            module._lock.release()
        self.opener.open.assert_not_called()

    def test_redirect_cannot_forward_audio_or_key(self):
        self.assertIsNone(module._NoRedirect().redirect_request(None, None, None, None, None, None))


if __name__ == '__main__':
    unittest.main()


def setUpModule():
    import tempfile
    import unittest
    from pathlib import Path
    from unittest.mock import patch
    from iris.usage import ProviderUsage
    temporary=tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(temporary.cleanup)
    replacement=patch('iris.usage.default_usage',return_value=ProviderUsage(Path(temporary.name)/'usage.sqlite3',{'IRIS_PROVIDER_LIMIT_HOUR':'10000','IRIS_PROVIDER_LIMIT_DAY':'10000','IRIS_PROVIDER_LIMIT_SESSION':'10000'}))
    replacement.start()
    unittest.addModuleCleanup(replacement.stop)

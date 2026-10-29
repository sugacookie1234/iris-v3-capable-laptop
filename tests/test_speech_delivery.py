"""Offline speech rendering and wire contracts; no synthesis or playback."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from iris.desktop.runtime import DesktopRuntime
from iris.desktop.server import DesktopServer, voice_request
from iris.voice.fish_audio import FishAudioSynthesizer, normalize_tts_text
from tests.test_desktop import FakeBrain
from tests.test_fish_audio import Response


class DeliveryTests(unittest.TestCase):
    def test_sentence_ending_name_is_pronounced_without_rewriting_identifiers(self):
        self.assertEqual(normalize_tts_text('Ready, IRIS. IRIS.txt IRIS-v2 /IRIS'),
                         'Ready, Iris. IRIS.txt IRIS-v2 /IRIS')

    def test_removes_stage_directions_without_removing_ordinary_explanations(self):
        text = '[sigh] IRIS is ready. (clears throat) *chuckles softly* All set. (At 3 PM.)'
        self.assertEqual(normalize_tts_text(text), 'Iris is ready. All set. (At 3 PM.)')
        self.assertEqual(normalize_tts_text('The word sigh means an audible exhalation.'),
                         'The word sigh means an audible exhalation.')
        self.assertEqual(normalize_tts_text('(A sigh can indicate relief.)'), '(A sigh can indicate relief.)')
        self.assertEqual(normalize_tts_text('[with a weary sigh] (deep breath) Ready.'), 'Ready.')

    def test_preserves_labels_links_numeric_data_and_literal_code(self):
        text = '[Orion](https://example.test) [Project status] [1, 2] `items[0]` `print("(sigh)")`'
        rendered = normalize_tts_text(text)
        self.assertIn('Orion Project status', rendered)
        self.assertIn('open bracket 1, 2 close bracket', rendered)
        self.assertIn('items open bracket 0 close bracket', rendered)
        self.assertIn('sigh', rendered)  # Quoted code remains information, not an acting instruction.
        self.assertNotIn('[', rendered)
        self.assertNotIn('(sigh)', rendered)
        self.assertEqual(normalize_tts_text('[sigh](https://example.test)'), 'sigh')
        self.assertEqual(normalize_tts_text(rendered), rendered)

    def test_desktop_request_is_cleaner_and_keeps_selected_model_voice(self):
        request = voice_request({'IRIS_FISH_API_KEY': 'synthetic', 'IRIS_FISH_MODEL': 's2.1-pro-free',
                                 'IRIS_FISH_VOICE_ID': 'chosen-voice-id'}, '[sighing] Ready, IRIS.')
        data = json.loads(request.data)
        self.assertEqual(data['text'], 'Ready, Iris.')
        self.assertEqual(data['reference_id'], 'chosen-voice-id')
        self.assertEqual(request.get_header('Model'), 's2.1-pro-free')
        self.assertEqual(data['temperature'], 0.3)
        self.assertEqual(data['top_p'], 0.7)

    def test_cli_uses_same_cleanup_and_does_not_request_audio_for_only_cues(self):
        with patch.dict(os.environ, {'IRIS_FISH_API_KEY': 'synthetic'}, clear=True), \
             patch('iris.voice.fish_audio.urlopen', return_value=Response()) as generate:
            synth = FishAudioSynthesizer(audio_sink=lambda audio: None)
            synth.speak('[sigh] (clears throat) *chuckles*')
            generate.assert_not_called()
            synth.speak('[sigh] Good morning, IRIS.')
            self.assertEqual(json.loads(generate.call_args.args[0].data)['text'], 'Good morning, Iris.')

    def test_spoken_bracket_expansion_still_respects_request_size_limit(self):
        with patch('iris.voice.fish_audio.MAX_TTS_CHARACTERS', 20), \
             patch('iris.voice.fish_audio.urlopen') as generate:
            with self.assertRaisesRegex(ValueError, 'Rendered speech'):
                FishAudioSynthesizer(audio_sink=lambda audio: None).speak('values[1, 2, 3]')
        generate.assert_not_called()

    def test_voice_ticket_supplies_clean_device_fallback_and_skips_empty_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = DesktopRuntime(settings={'IRIS_MODEL': 'synthetic', 'IRIS_PROVIDER_URL': 'http://127.0.0.1:9',
                'IRIS_AUTO_ORGANIZE_ENABLED': 'false'}, data_dir=Path(directory), brain=FakeBrain())
            server = DesktopServer(('127.0.0.1', 0), runtime)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            connection = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                           'Content-Type': 'application/json'}
                for source, expected in (('[sigh] Hello IRIS.', 'Hello Iris.'), ('[sighing] *laughs*', '')):
                    connection.request('POST', '/api/voice', json.dumps({'text': source}), headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    ticket = json.loads(response.read())
                    self.assertEqual(ticket['fallback_text'], expected)
                    if expected:
                        self.assertEqual(runtime.consume_audio(ticket['url'].rsplit('/', 1)[1]), expected)
                    else:
                        self.assertIsNone(ticket['url'])
                        self.assertEqual(runtime.audio_tickets, {})
                self.assertEqual(runtime.history, [])
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                runtime.close()


if __name__ == '__main__':
    unittest.main()

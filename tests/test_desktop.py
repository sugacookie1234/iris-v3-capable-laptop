"""Integrated Windows/browser contracts with fake models and real local storage."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from iris.desktop.runtime import DesktopRuntime, BusyError
from iris.desktop.server import DesktopServer
from iris.brain.router import route_message
from iris.local_config import save_updates, read_saved, LocalConfigError


class FakeBrain:
    def __init__(self):
        self.calls = []
        self.fail = False

    def respond(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if self.fail:
            raise RuntimeError('Synthetic provider failure')
        return SimpleNamespace(text='Iris is ready.', route=route_message(text), council=None)


class DesktopTests(unittest.TestCase):
    def test_failed_tool_cannot_be_described_as_successful(self):
        from iris.brain.engine import BrainResult
        from iris.tools.models import ToolResult, ToolFailure, ResultStatus, FailureCode
        failure = ToolResult(ResultStatus.FAILED, failure=ToolFailure(
            FailureCode.EXECUTION_FAILED, 'Worker failed.'))
        result = BrainResult(text='I successfully added your task.', route=route_message('Add a task'),
                             provider='test', model='test', tool_result=failure)
        with patch.object(self.brain, 'respond', return_value=result):
            answer = self.app.chat('Add a task')
        self.assertNotIn('successfully added', answer['reply'])
        self.assertIn('could not confirm', answer['reply'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.brain = FakeBrain()
        self.app = DesktopRuntime(settings={'IRIS_PROVIDER_URL': 'http://127.0.0.1:9',
            'IRIS_MODEL': 'synthetic', 'IRIS_TIMEZONE': 'America/New_York'},
            data_dir=self.temp.name, brain=self.brain)

    def wait_pending(self):
        for _ in range(200):
            pending = self.app.pending_approval()
            if pending:
                return pending
            time.sleep(.01)
        self.fail('No approval was requested.')

    def test_shared_history_council_and_reset(self):
        self.app.chat('My project is Orion.')
        self.app.chat('Compare the options.', 'council')
        text, kwargs = self.brain.calls[-1]
        self.assertTrue(text.startswith('Ask the council:'))
        self.assertEqual(kwargs['history'][0].content, 'My project is Orion.')
        self.assertEqual(len(self.app.history), 4)
        self.app.reset()
        self.assertEqual(self.app.history, [])

    def test_failed_turn_is_not_added_to_history(self):
        self.brain.fail = True
        with self.assertRaises(RuntimeError):
            self.app.chat('A failing request')
        self.assertEqual(self.app.history, [])
        self.assertFalse(self.app.turn_lock.locked())

    def test_memory_requires_approval_persists_and_is_retrieved(self):
        thread = threading.Thread(target=self.app.chat, args=('/remember I prefer short answers',))
        thread.start()
        pending = self.wait_pending()
        self.assertEqual(self.app.memories(), [])
        self.app.resolve_approval(pending['id'], True)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.app.memories()), 1)
        self.app.chat('What kind of answers do I prefer?')
        context = self.brain.calls[-1][1].get('memory_context')
        self.assertIsNotNone(context)
        self.assertIn('short answers', context.text)
        self.app.reset()
        self.assertEqual(len(self.app.memories()), 1)

    def test_declined_memory_is_not_saved_and_duplicate_approval_is_rejected(self):
        thread = threading.Thread(target=self.app.chat, args=('/remember I enjoy hiking',))
        thread.start()
        pending = self.wait_pending()
        self.app.resolve_approval(pending['id'], False)
        with self.assertRaises(ValueError):
            self.app.resolve_approval(pending['id'], True)
        thread.join(3)
        self.assertEqual(self.app.memories(), [])

    def test_secret_memory_rejected_before_approval(self):
        with self.assertRaises(ValueError):
            self.app.chat('/remember API key sk-or-v1-' + 'a' * 60)
        self.assertIsNone(self.app.pending_approval())

    def test_voice_tickets_are_single_use_and_bounded(self):
        token = self.app.issue_audio('Hello Iris')
        self.assertEqual(self.app.consume_audio(token), 'Hello Iris')
        with self.assertRaises(ValueError):
            self.app.consume_audio(token)
        for _ in range(32):
            self.app.issue_audio('Hi')
        with self.assertRaises(BusyError):
            self.app.issue_audio('Overflow')

    def test_audio_first_chunk_arrives_before_upstream_finishes(self):
        release = threading.Event()
        class Upstream:
            headers = {'Content-Type': 'audio/mpeg'}
            count = 0
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read1(self, size):
                self.count += 1
                if self.count == 1: return b'ID3-first-chunk'
                if self.count == 2:
                    if not release.wait(5): raise TimeoutError()
                    return b'-last-chunk'
                return b''
        self.app.settings['IRIS_FISH_API_KEY'] = 'synthetic'
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)
        token = self.app.issue_audio('Synthetic speech')
        with patch('iris.desktop.server.urllib.request.urlopen', return_value=Upstream()):
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            try:
                connection.request('GET', '/api/audio/' + token,
                    headers={'Cookie': 'iris_session=' + server.session})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(len(b'ID3-first-chunk')), b'ID3-first-chunk')
                self.assertFalse(release.is_set())
                release.set()
                self.assertEqual(response.read(), b'-last-chunk')
            finally:
                release.set()
                connection.close()

    def test_http_rejects_unauthenticated_and_cross_origin_writes(self):
        server = DesktopServer(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address)
        self.addCleanup(connection.close)
        connection.request('GET', '/api/memories')
        response = connection.getresponse()
        self.assertEqual(response.status, 403); response.read()
        connection.request('GET', '/')
        response = connection.getresponse()
        cookie = response.getheader('Set-Cookie').split(';')[0]
        self.assertEqual(response.status, 200); response.read()
        headers = {'Cookie': cookie, 'X-IRIS-Request': '1', 'Content-Type': 'application/json',
                   'Origin': 'https://untrusted.example'}
        connection.request('POST', '/api/chat', json.dumps({'text': 'hello'}), headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 403); response.read()
        del headers['Origin']
        connection.request('POST', '/api/chat', json.dumps({'text': 'hello'}), headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())['reply'], 'Iris is ready.')

    def test_transcription_endpoint_requires_session_and_reports_engine(self):
        from tests.test_desktop_transcription import wav
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address)
        self.addCleanup(connection.close)
        speech = {'engine': 'fish', 'device': 'cloud', 'fallback': None}
        with patch('iris.desktop.server.transcribe', return_value='hello') as recognize, \
             patch('iris.desktop.server.speech_status', return_value=speech):
            connection.request('POST', '/api/transcribe', wav(), {'Content-Type': 'audio/wav'})
            response = connection.getresponse()
            self.assertEqual(response.status, 403); response.read()
            recognize.assert_not_called()
            headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                       'Content-Type': 'audio/wav'}
            connection.request('POST', '/api/transcribe', wav(), headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()), {'text': 'hello', 'speech': speech})

    def test_status_reports_native_host_only_when_enabled(self):
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address)
        self.addCleanup(connection.close)
        with patch('iris.desktop.server.speech_status', return_value={}):
            for desktop in (False, True):
                if desktop:
                    server.desktop_window = True
                connection.request('GET', '/api/status', headers={'Cookie': 'iris_session=' + server.session})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIs(json.loads(response.read())['desktop_window'], desktop)


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI contract')
class WindowsConfigurationTests(unittest.TestCase):
    def test_encrypted_roundtrip_merge_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.dpapi'
            values = {'IRIS_API_KEY': 'synthetic-secret-only', 'IRIS_MODEL': 'test-model'}
            save_updates(values, path)
            self.assertNotIn(b'synthetic-secret-only', path.read_bytes())
            self.assertEqual(read_saved(path), values)
            save_updates({'IRIS_MODEL': 'new-model', 'IRIS_API_KEY': ''}, path)
            self.assertEqual(read_saved(path)['IRIS_API_KEY'], values['IRIS_API_KEY'])
            path.write_bytes(b'invalid-data')
            with self.assertRaises(LocalConfigError):
                read_saved(path)


class DesktopSetupTests(unittest.TestCase):
    def test_setup_validates_all_role_provider_names(self):
        from iris.desktop.setup import main
        with patch('iris.desktop.setup.read_saved', return_value={}), \
             patch('builtins.input', return_value=''), \
             patch('iris.desktop.setup.getpass', return_value='synthetic-key'), \
             patch('iris.desktop.setup.save_updates') as save:
            self.assertEqual(main(), 0)
            values = save.call_args.args[0]
            self.assertEqual(values['IRIS_FAST_PROVIDER'], 'terminal')
            self.assertEqual(values['IRIS_COUNCIL_SKEPTIC_PROVIDER'], 'terminal')


if __name__ == '__main__':
    unittest.main()

"""Native clap HTTP boundary: real loopback requests, no microphone access."""
import http.client
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from iris.desktop import server as module


class NativeClapApiTests(unittest.TestCase):
    def setUp(self):
        self.listener = Mock(spec=['update', 'stop', 'close'])
        self.state = {'active': True, 'starting': False, 'sequence': 3, 'error': None,
                      'device': 'Test input', 'sample_rate': 44100, 'block_ms': 40}
        self.listener.update.return_value = self.state
        self.listener.stop.return_value = {**self.state, 'active': False}
        listener_patch = patch.object(module, 'NativeClapListener', return_value=self.listener)
        self.factory = listener_patch.start()
        self.addCleanup(listener_patch.stop)
        speech_patch = patch.object(module, 'speech_status', return_value={})
        speech_patch.start()
        self.addCleanup(speech_patch.stop)
        runtime = SimpleNamespace(settings={}, last_route='FAST', last_seconds=None,
            autonomy=SimpleNamespace(status=lambda: {'enabled': False}),
            config=SimpleNamespace(model='synthetic', obsidian_root=None, obsidian_vault=None))
        self.server = module.DesktopServer(('127.0.0.1', 0), runtime)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.shutdown)
        self.headers = {'Cookie': 'iris_session=' + self.server.session,
            'X-IRIS-Request': '1', 'Content-Type': 'application/json'}

    def request(self, method, path, body=None, headers=None, *, raw=False):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            encoded = body if raw else None if body is None else json.dumps(body)
            connection.request(method, path, encoded,
                               self.headers if headers is None else headers)
            response = connection.getresponse()
            content = response.read()
            if response.getheader('Content-Type', '').startswith('application/json'):
                content = json.loads(content)
            return response.status, content
        finally:
            connection.close()

    def test_startup_and_status_do_not_enable_microphone(self):
        self.factory.assert_called_once_with()
        status, body = self.request('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(body['clap']['engine'], 'sounddevice')
        self.assertEqual(body['clap']['sample_rate'], 44100)
        self.assertEqual(body['clap']['block_ms'], 40)
        self.assertEqual(self.listener.mock_calls, [])

    def test_native_asset_is_served_without_starting_listener(self):
        status, body = self.request('GET', '/native-standby.js')
        self.assertEqual(status, 200)
        self.assertIn(b'NativeStandbyMonitor', body)
        self.assertEqual(self.listener.mock_calls, [])

    def test_update_requires_session_write_header_and_same_origin(self):
        invalid_headers = [
            {'Content-Type': 'application/json'},
            {**self.headers, 'Cookie': 'iris_session=wrong'},
            {key: value for key, value in self.headers.items() if key != 'X-IRIS-Request'},
            {**self.headers, 'Origin': 'https://untrusted.example'},
            {**self.headers, 'Sec-Fetch-Site': 'cross-site'},
            {**self.headers, 'Host': 'untrusted.example'},
        ]
        for headers in invalid_headers:
            with self.subTest(headers=tuple(headers.keys())):
                status, _ = self.request('POST', '/api/clap',
                    {'action': 'update', 'owner': 'window-a', 'busy': False}, headers)
                self.assertEqual(status, 403)
        self.assertEqual(self.listener.mock_calls, [])

    def test_update_passes_owner_and_explicit_busy_state(self):
        for busy in (False, True):
            with self.subTest(busy=busy):
                status, body = self.request('POST', '/api/clap',
                    {'action': 'update', 'owner': 'window-a', 'busy': busy})
                self.assertEqual(status, 200)
                self.assertEqual(body, self.state)
                self.listener.update.assert_called_with('window-a', busy=busy)
        self.assertEqual(self.listener.update.call_count, 2)
        self.listener.stop.assert_not_called()

    def test_update_rejects_nonboolean_or_missing_busy_before_listener(self):
        for busy in (None, 0, 1, 'false', [], {}):
            with self.subTest(busy=busy):
                status, _ = self.request('POST', '/api/clap',
                    {'action': 'update', 'owner': 'window-a', 'busy': busy})
                self.assertEqual(status, 400)
        status, _ = self.request('POST', '/api/clap',
            {'action': 'update', 'owner': 'window-a'})
        self.assertEqual(status, 400)
        self.assertEqual(self.listener.mock_calls, [])

    def test_stop_requires_authorization_and_dispatches_owner(self):
        value = {'action': 'stop', 'owner': 'window-a'}
        status, _ = self.request('POST', '/api/clap', value,
            {'Content-Type': 'application/json'})
        self.assertEqual(status, 403)
        self.listener.stop.assert_not_called()
        status, body = self.request('POST', '/api/clap', value)
        self.assertEqual(status, 200)
        self.assertEqual(body, self.listener.stop.return_value)
        self.listener.stop.assert_called_once_with('window-a')
        self.listener.update.assert_not_called()

    def test_listener_validation_errors_return_bad_request(self):
        for action in ('update', 'stop'):
            with self.subTest(action=action):
                method = getattr(self.listener, action)
                method.side_effect = ValueError('Invalid listener owner.')
                status, body = self.request('POST', '/api/clap',
                    {'action': action, 'owner': '', 'busy': False})
                self.assertEqual(status, 400)
                self.assertEqual(body['error'], 'Invalid listener owner.')
                method.assert_called_once()

    def test_unknown_action_and_malformed_bodies_never_touch_microphone(self):
        for value in ({}, {'action': 'start'}, {'action': None}, {'action': []}):
            with self.subTest(value=value):
                status, _ = self.request('POST', '/api/clap', value)
                self.assertEqual(status, 400)
        for content in ('[]', 'null', '{broken'):
            with self.subTest(content=content):
                status, _ = self.request('POST', '/api/clap', content, raw=True)
                self.assertEqual(status, 400)
        self.assertEqual(self.listener.mock_calls, [])

    def test_server_close_releases_listener(self):
        self.server.shutdown()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.server.server_close()
        self.listener.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()

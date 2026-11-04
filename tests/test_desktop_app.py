"""Desktop server ownership, navigation boundary, and explicit Chrome launch."""
import http.client
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
import webbrowser

from iris.desktop import app, browser


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWebview:
    def __init__(self, fail=False):
        self.settings = {}
        self.fail = fail
        self.url = None
        self.window = SimpleNamespace(events=SimpleNamespace(before_show=Event(), loaded=Event()))

    def create_window(self, title, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        return self.window

    def start(self, **kwargs):
        self.start_kwargs = kwargs
        target = urlsplit(self.url)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=3)
        try:
            connection.request('GET', '/')
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader('Set-Cookie') is None
            assert b'/pair.js' in response.read()
            token = target.fragment.removeprefix('pair=')
            connection.request('POST', '/api/pair', json.dumps({'token': token}),
                {'Origin': f'http://127.0.0.1:{target.port}', 'Content-Type': 'application/json', 'X-IRIS-Request': '1'})
            response = connection.getresponse()
            assert response.status == 200
            cookie = response.getheader('Set-Cookie').split(';')[0]
            response.read()
            connection.request('GET', '/', headers={'Cookie': cookie})
            response = connection.getresponse()
            assert b'LOCAL WEATHER' in response.read()
        finally:
            connection.close()
        if self.fail:
            raise RuntimeError('Synthetic renderer failure')


class DesktopAppTests(unittest.TestCase):
    def test_secondary_can_activate_after_nonactivating_initial_show(self):
        native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda:123))
        child=SimpleNamespace(native=native,focus=False)
        api=SimpleNamespace(GetWindowLongW=Mock(return_value=0x08000080),SetWindowLongW=Mock())
        with patch.object(app.ctypes,'WinDLL',return_value=api):
            app.allow_visual_activation(child)
        self.assertTrue(child.focus)
        api.SetWindowLongW.assert_called_once_with(123,-20,0x80)

    def test_exhausted_ports_close_native_runtime(self):
        runtime = SimpleNamespace(close=Mock())
        with patch.object(app, 'DesktopServer', side_effect=OSError('Synthetic occupied port')):
            with self.assertRaisesRegex(RuntimeError, 'No available IRIS port'):
                app.run_window(FakeWebview(), runtime)
        runtime.close.assert_called_once_with()

    def test_owned_server_stops_on_close_and_renderer_failure(self):
        for fails in (False, True):
            with self.subTest(failure=fails), tempfile.TemporaryDirectory() as data, patch.dict(os.environ):
                view = FakeWebview(fails)
                original_open = webbrowser.open
                if fails:
                    with self.assertRaisesRegex(RuntimeError, 'Synthetic'):
                        app.run_window(view, SimpleNamespace(data_dir=data), port=0)
                else:
                    app.run_window(view, SimpleNamespace(data_dir=data), port=0)
                self.assertIs(webbrowser.open, original_open)
                target = urlsplit(view.url)
                with self.assertRaises(OSError):
                    socket.create_connection((target.hostname, target.port), timeout=.5)
                self.assertEqual(view.start_kwargs['gui'], 'edgechromium')
                self.assertFalse(view.start_kwargs['private_mode'])
                self.assertEqual(Path(view.start_kwargs['storage_path']), Path(data) / 'webview')
                self.assertFalse(view.settings['ALLOW_FILE_URLS'])
                self.assertFalse(view.settings['IGNORE_SSL_ERRORS'])
                self.assertIsNone(view.settings['REMOTE_DEBUGGING_PORT'])
                flags = os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'].split()
                self.assertIn('--disable-background-timer-throttling', flags)
                self.assertIn('--autoplay-policy=no-user-gesture-required', flags)

    def test_external_pages_cannot_replace_the_embedded_app(self):
        origin = 'http://127.0.0.1:8766/'
        self.assertTrue(app.local_navigation(origin, origin))
        self.assertTrue(app.local_navigation(origin + '#conversation', origin))
        for url in ('http://127.0.0.1:8767/', 'http://localhost:8766/', 'https://example.com/',
                    'file:///C:/Windows/win.ini', 'javascript:alert(1)',
                    'http://127.0.0.1:8766@evil.example/', 'http://user@127.0.0.1:8766/',
                    'http://127.0.0.1:bad/', 'http://[bad'):
            with self.subTest(url=url):
                self.assertFalse(app.local_navigation(url, origin))
        control = SimpleNamespace(NavigationStarting=Event())
        app.guard_navigation(SimpleNamespace(native=SimpleNamespace(webview=control)), origin)
        event = SimpleNamespace(Uri='https://example.com/', Cancel=False)
        control.NavigationStarting.handlers[0](None, event)
        self.assertTrue(event.Cancel)

    def test_chrome_launch_passes_url_as_argument_without_shell(self):
        with patch.object(browser, 'chrome_path', return_value='C:/Chrome/chrome.exe'), \
             patch.object(browser.subprocess, 'Popen') as launch:
            self.assertTrue(browser.open_chrome('https://example.com/?x=a&y=b'))
            launch.assert_called_once_with(['C:/Chrome/chrome.exe', '--new-window',
                                           'https://example.com/?x=a&y=b'], close_fds=True)

    def test_no_other_browser_fallback_or_local_file_launch(self):
        with patch.object(browser, 'chrome_path', return_value=None), \
             patch.object(browser.subprocess, 'Popen') as launch:
            self.assertFalse(browser.ChromeBrowser().open('https://example.com/'))
            with self.assertRaises(RuntimeError):
                browser.open_chrome('http://127.0.0.1:8766/')
            for url in ('file:///C:/secret', 'javascript:alert(1)', 'https://key:secret@example.com/'):
                with self.assertRaises(ValueError):
                    browser.open_chrome(url)
            launch.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows session mutex')
    def test_duplicate_instance_is_rejected_and_mutex_released(self):
        with tempfile.TemporaryDirectory() as root, patch.object(app, 'ROOT', Path(root)):
            with app.single_instance():
                with self.assertRaises(app.AlreadyRunning):
                    with app.single_instance():
                        self.fail('Duplicate instance started')
            with app.single_instance():
                pass


if __name__ == '__main__':
    unittest.main()

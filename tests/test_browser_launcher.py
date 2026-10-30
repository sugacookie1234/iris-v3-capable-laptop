"""Both launchers reserve one owner before touching durable application state."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from iris.desktop import app, server
from iris.desktop.instance import AlreadyRunning, instance_guard


class BrowserLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for module in (app, server):
            patched = patch.object(module, 'ROOT', self.root)
            patched.start()
            self.addCleanup(patched.stop)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows launcher')
    def test_browser_cannot_recover_jobs_while_native_owns_checkout(self):
        with app.single_instance(), patch.object(server, 'DesktopRuntime') as runtime:
            self.assertEqual(server.main(['--no-browser']), 0)
            runtime.assert_not_called()
        with instance_guard(self.root):
            pass

    def test_browser_owns_guard_before_runtime_construction_and_through_close(self):
        runtime = SimpleNamespace(close=Mock())

        def verify_owned():
            with self.assertRaises(AlreadyRunning):
                with instance_guard(self.root):
                    self.fail('A second runtime could start.')

        def construct():
            verify_owned()
            return runtime

        def close_server():
            verify_owned()
            runtime.close()

        owned_server = SimpleNamespace(server_address=('127.0.0.1', 8766),
            serve_forever=Mock(side_effect=KeyboardInterrupt), server_close=close_server)
        with patch.object(server, 'DesktopRuntime', side_effect=construct), \
             patch.object(server, 'DesktopServer', return_value=owned_server):
            self.assertEqual(server.main(['--no-browser']), 0)
        runtime.close.assert_called_once_with()
        with instance_guard(self.root):
            pass

    def test_configuration_failure_releases_guard_without_starting_server(self):
        with patch.object(server, 'DesktopRuntime', side_effect=ValueError('Synthetic configuration failure')), \
             patch.object(server, 'DesktopServer') as host:
            self.assertEqual(server.main(['--no-browser']), 1)
        host.assert_not_called()
        with instance_guard(self.root):
            pass

    def test_exhausted_ports_close_runtime_and_release_guard(self):
        runtime = SimpleNamespace(close=Mock())
        with patch.object(server, 'DesktopRuntime', return_value=runtime), \
             patch.object(server, 'DesktopServer', side_effect=OSError('Synthetic occupied port')) as host:
            self.assertEqual(server.main(['--port', '65535', '--no-browser']), 1)
        self.assertEqual(host.call_count, 1)
        runtime.close.assert_called_once_with()
        with instance_guard(self.root):
            pass

    def test_failed_bind_does_not_close_runtime_needed_by_next_port(self):
        runtime = SimpleNamespace(start_background=Mock(), close=Mock())
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            with self.assertRaises(OSError):
                server.DesktopServer(occupied.getsockname(), runtime)
            runtime.start_background.assert_not_called()
            runtime.close.assert_not_called()
            host = server.DesktopServer(('127.0.0.1', 0), runtime)
            try:
                runtime.start_background.assert_called_once_with()
                runtime.close.assert_not_called()
            finally:
                host.server_close()
            host.server_close()
        runtime.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()

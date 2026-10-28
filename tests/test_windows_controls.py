"""Bounded desktop actions use fixed executables and report observed results."""
from pathlib import Path
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from iris.desktop import windows_controls as controls


class WindowsControlTests(unittest.TestCase):
    def make_controls(self, observed=True, audio=None):
        launch = Mock()
        observer = Mock(return_value=observed)
        adapter = controls.WindowsControls(
            resolver=lambda alias: Path('C:/Trusted') / controls.APPS[alias][1],
            launcher=launch, observer=observer, sleep=lambda seconds: None,
            audio=audio or SimpleNamespace(volume=Mock(return_value={'percent': 40, 'muted': False})))
        return adapter, launch, observer

    def test_launch_uses_only_fixed_alias_without_shell_or_arguments(self):
        adapter, launch, _ = self.make_controls()
        result = adapter.open_app('chrome')
        launch.assert_called_once_with([str(Path('C:/Trusted/chrome.exe'))], shell=False, close_fds=True)
        self.assertEqual(result['state'], 'visible')
        self.assertTrue(result['verified'])
        self.assertEqual(result['name'], 'Google Chrome')
        self.assertEqual(result['detail'], 'Google Chrome has a visible window.')
        launch.reset_mock()
        for value in ('edge', 'chrome https://example.com', 'chrome.exe', '../calc', '', None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapter.open_app(value)
        launch.assert_not_called()

    def test_started_process_is_not_misreported_as_visible_window(self):
        adapter, launch, observer = self.make_controls(observed=False)
        result = adapter.open_app('calculator')
        self.assertEqual(result['state'], 'requested')
        self.assertFalse(result['verified'])
        self.assertIn('could not verify', result['detail'])
        self.assertEqual(observer.call_count, 6)
        launch.assert_called_once()

    def test_failed_launch_is_not_a_success_and_missing_app_does_not_fallback(self):
        adapter, launch, observer = self.make_controls()
        launch.side_effect = OSError('private process details')
        with self.assertRaisesRegex(controls.ControlUnavailable, r'^Windows could not launch Notepad\.$'):
            adapter.open_app('notepad')
        observer.assert_not_called()
        launch.reset_mock()
        adapter.resolver = Mock(side_effect=controls.ControlUnavailable('Chrome is not installed'))
        with self.assertRaisesRegex(controls.ControlUnavailable, 'Chrome is not installed'):
            adapter.open_app('chrome')
        launch.assert_not_called()

    def test_observation_failure_retains_honest_request_status(self):
        adapter, _, observer = self.make_controls()
        observer.side_effect = OSError('inspection unavailable')
        self.assertEqual(adapter.open_app('obsidian')['state'], 'requested')

    def test_configured_folder_is_one_argument_and_not_claimed_verified(self):
        adapter, launch, _ = self.make_controls()
        with tempfile.TemporaryDirectory(prefix='IRIS folder ') as folder:
            adapter.folder_check = lambda path: self.assertTrue(path.is_dir())
            result = adapter.open_folder(folder)
            launch.assert_called_once_with([str(Path('C:/Trusted/explorer.exe')), str(Path(folder))],
                                           shell=False, close_fds=True)
            self.assertEqual(result['state'], 'requested')
            self.assertFalse(result['verified'])
        for path in ('relative/path', '//server/share/folder'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                adapter.open_folder(path)

    def test_folder_validation_precedes_launch(self):
        adapter, launch, _ = self.make_controls()
        adapter.folder_check = Mock(side_effect=PermissionError('junction'))
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(PermissionError):
            adapter.open_folder(folder)
        launch.assert_not_called()

    def test_volume_read_and_change_use_readback(self):
        audio = SimpleNamespace(volume=Mock(return_value={'percent': 40, 'muted': False}))
        adapter, _, _ = self.make_controls(audio=audio)
        self.assertTrue(adapter.volume()['verified'])
        audio.volume.assert_called_once_with(percent=None, muted=None)
        self.assertTrue(adapter.volume(percent=40, muted=False)['verified'])
        audio.volume.return_value = {'percent': 20, 'muted': True}
        result = adapter.volume(percent=40, muted=False)
        self.assertEqual(result['state'], 'mismatch')
        self.assertFalse(result['verified'])
        self.assertEqual(result['percent'], 20)
        self.assertTrue(result['muted'])

    def test_invalid_volume_inputs_never_reach_windows(self):
        audio = SimpleNamespace(volume=Mock())
        adapter, _, _ = self.make_controls(audio=audio)
        for percent in (-1, 101, True, 3.5, '40'):
            with self.subTest(percent=percent), self.assertRaises(ValueError):
                adapter.volume(percent=percent)
        for muted in ('false', 0, 1):
            with self.subTest(muted=muted), self.assertRaises(ValueError):
                adapter.volume(muted=muted)
        audio.volume.assert_not_called()

    def test_invalid_audio_reading_is_not_reported_as_verified(self):
        audio = SimpleNamespace(volume=Mock(return_value={'percent': 200, 'muted': False}))
        adapter, _, _ = self.make_controls(audio=audio)
        with self.assertRaises(controls.ControlUnavailable):
            adapter.volume()


@unittest.skipUnless(os.name == 'nt', 'Windows installation discovery')
class AppDiscoveryTests(unittest.TestCase):
    def test_known_installation_resolves_without_path_search(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chrome = root / 'Google/Chrome/Application/chrome.exe'
            chrome.parent.mkdir(parents=True)
            chrome.write_bytes(b'fixture, never executed')
            with patch.dict(controls.os.environ, {'ProgramFiles': folder}, clear=True), \
                    patch.object(controls, '_windows_directory', return_value=root), \
                    patch.object(controls, '_registered_path', return_value=()):
                self.assertEqual(controls.find_app('chrome'), chrome)

    def test_registry_commands_and_other_executables_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            other = root / 'msedge.exe'
            other.write_bytes(b'fixture, never executed')
            with patch.dict(controls.os.environ, {}, clear=True), \
                    patch.object(controls, '_windows_directory', return_value=root), \
                    patch.object(controls, '_registered_path', return_value=(
                        str(other), str(root / 'chrome.exe') + ' --profile-directory=x',
                        'https://example.com/chrome.exe', 'chrome.exe')):
                with self.assertRaises(controls.ControlUnavailable):
                    controls.find_app('chrome')


if __name__ == '__main__':
    unittest.main()

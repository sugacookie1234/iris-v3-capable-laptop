"""Desktop integration: nonblocking capture, standing authority, API boundaries."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from iris.desktop.autonomy import Autonomy
from iris.desktop.runtime import DesktopRuntime, BusyError
from iris.desktop.server import DesktopServer
from iris.desktop import notification_alerts
from iris.tools.models import ExecutionPlan, ToolSpec, AuthorityLevel, RequestOrigin
from tests.test_desktop import FakeBrain


class AutonomyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = {'IRIS_PROVIDER_URL': 'http://127.0.0.1:9', 'IRIS_MODEL': 'synthetic',
                         'IRIS_TIMEZONE': 'America/New_York', 'IRIS_AUTO_ORGANIZE_ENABLED': 'true'}
        self.app = DesktopRuntime(settings=self.settings, data_dir=self.temp.name, brain=FakeBrain())
        self.addCleanup(self.app.close)
        self.app.autonomy.reminders.notifier = Mock()

    def test_user_commitment_saved_without_tool_command_or_approval(self):
        # Real stores, planner disabled: the common phrase parser owns this case.
        self.app.autonomy.organizer._planner = Mock(return_value={'operations': []})
        self.app.chat('I need to submit the report tomorrow at 3 PM')
        self.app.autonomy._queue.join()
        tasks = self.app.tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['title'], 'submit the report')
        self.assertIsNotNone(tasks[0]['due_at'])
        self.assertIsNone(self.app.pending_approval())
        event = self.app.autonomy.events()['activity'][0]
        self.app.autonomy.undo(event['id'])
        self.assertEqual(self.app.tasks(), [])

    def test_capture_does_not_wait_for_background_planner(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow(*args, **kwargs):
            entered.set()
            release.wait(2)
            return []
        self.app.autonomy.organizer.process = Mock(side_effect=slow)
        result = self.app.chat('My project uses a new architecture')
        self.assertEqual(result['reply'], 'Iris is ready.')
        self.assertTrue(entered.wait(1))
        self.assertFalse(release.is_set())
        release.set()
        self.app.autonomy._queue.join()

    def test_standing_approval_is_limited_to_local_organizer_tools(self):
        def plan(name, local=True):
            return ExecutionPlan(ToolSpec(name, '', AuthorityLevel.YELLOW, True, (), (), 5, (), local),
                                 (), RequestOrigin.USER, 'Test')
        self.app.approve = Mock(return_value=False)
        self.assertTrue(self.app._tool_approval(plan('tasks_create')).approved)
        self.app.approve.assert_not_called()
        self.assertFalse(self.app._tool_approval(plan('tasks_create', False)).approved)
        self.assertFalse(self.app._tool_approval(plan('send_email')).approved)

    def test_pause_keeps_activity_but_hides_pending_delivery(self):
        event = self.app.autonomy.organizer.process('I need to renew my passport')[0]
        self.app.autonomy.reminders.pending = Mock(return_value=[{'id': 'due'}])
        self.app.settings['IRIS_AUTO_ORGANIZE_ENABLED'] = 'false'
        snapshot = self.app.autonomy.events()
        self.assertFalse(snapshot['status']['enabled'])
        self.assertEqual(snapshot['reminders'], [])
        self.assertEqual(snapshot['activity'][0]['id'], event['id'])
        self.app.autonomy.undo(event['id'])
        self.assertEqual(self.app.tasks(), [])

    def test_missing_vault_does_not_disable_tasks_or_start_network(self):
        config = self.app.config
        from dataclasses import replace
        with patch('iris.desktop.notebook.Notebook', side_effect=OSError('offline drive')):
            auto = Autonomy(self.temp.name, self.settings, replace(config, obsidian_vault='Z:/missing'))
        self.addCleanup(auto.close)
        self.assertIsNone(auto.notebook)
        self.assertIn('notes folder is unavailable', auto.status()['error'])
        self.assertEqual(auto.organizer.process('I need to renew my passport')[0]['kind'], 'task')

    def test_model_fallback_status_reaches_ui(self):
        self.app.autonomy.organizer._last_error = 'Offline fallback'
        self.assertEqual(self.app.autonomy.status()['error'], 'Offline fallback')

    def test_overlapping_toggles_close_every_replaced_worker(self):
        entered, release, second_requested, second_saved = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        original = self.app.autonomy
        created, failures = [], []
        def save(*args):
            if not entered.is_set():
                entered.set()
                release.wait(2)
            else:
                second_saved.set()
        def build(*args):
            worker = Mock()
            worker.status.return_value = {}
            created.append(worker)
            return worker
        def toggle(second=False):
            if second:
                second_requested.set()
            try:
                self.app.set_automatic_organization(True)
            except Exception as exc:
                failures.append(exc)
        with patch('iris.local_config.save_updates', side_effect=save), \
                patch('iris.desktop.runtime.Autonomy', side_effect=build):
            first = threading.Thread(target=toggle)
            second = threading.Thread(target=toggle, args=(True,))
            first.start()
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertTrue(second_requested.wait(1))
            try:
                self.assertFalse(second_saved.wait(.1))
            finally:
                release.set()
                first.join(3)
                second.join(3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(original._stop.is_set())
        self.assertEqual(len(created), 2)
        created[0].close.assert_called_once()
        created[1].close.assert_not_called()
        self.app.close()
        created[1].close.assert_called_once()

    def test_shutdown_cannot_restart_organization(self):
        self.app.close()
        with patch('iris.local_config.save_updates') as save:
            with self.assertRaises(BusyError):
                self.app.set_automatic_organization(True)
            save.assert_not_called()
        self.app.autonomy.start = Mock()
        self.app.start_background()
        self.app.autonomy.start.assert_not_called()

    def test_authenticated_activity_and_undo_endpoints(self):
        event = self.app.autonomy.organizer.process('I need to renew my passport')[0]
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        self.addCleanup(connection.close)
        connection.request('GET', '/api/activity')
        response = connection.getresponse()
        self.assertEqual(response.status, 403); response.read()
        headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                   'Content-Type': 'application/json'}
        connection.request('GET', '/api/activity', headers=headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())['activity'][0]['id'], event['id'])
        connection.request('POST', '/api/activity/undo', json.dumps({'id': event['id']}),
                           {**headers, 'Origin': 'https://outside.example'})
        response = connection.getresponse()
        self.assertEqual(response.status, 403); response.read()
        self.assertEqual(len(self.app.tasks()), 1)
        connection.request('POST', '/api/activity/undo', json.dumps({'id': event['id']}), headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200); response.read()
        self.assertEqual(self.app.tasks(), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows notification contract')
    def test_notification_text_is_stdin_data_not_shell_code(self):
        hostile = '$(Remove-Item anything); "quoted"'
        with patch.object(notification_alerts.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(notification_alerts.notify('IRIS', hostile))
        args, kwargs = run.call_args
        self.assertNotIn(hostile, str(args))
        self.assertEqual(json.loads(kwargs['input'])['body'], hostile)
        self.assertEqual(kwargs['creationflags'], notification_alerts.subprocess.CREATE_NO_WINDOW)
        self.assertFalse(notification_alerts._SCRIPT.startswith('+'))


if __name__ == '__main__':
    unittest.main()

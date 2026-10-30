"""Background jobs use local authenticated controls, independently of chat."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from iris.agent_jobs.notes import NotesJobs
from iris.desktop.runtime import DesktopRuntime
from iris.desktop.server import DesktopServer
from tests.test_desktop import FakeBrain


class DesktopJobTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.started, self.release = threading.Event(), threading.Event()
        self.brain = FakeBrain()
        self.app = DesktopRuntime(settings={'IRIS_PROVIDER_URL': 'http://127.0.0.1:9',
            'IRIS_MODEL': 'synthetic', 'IRIS_OBSIDIAN_VAULT': str(self.root),
            'IRIS_AUTO_ORGANIZE_ENABLED': 'false'}, data_dir=self.root / '.data', brain=self.brain)
        self.app.jobs.close()
        owner = self

        class Runner:
            def __init__(self, *_args, **_kwargs):
                pass

            def run(self, topic, cancelled, progress):
                progress({'stage': 'search', 'completed_steps': []})
                owner.started.set()
                while not owner.release.wait(.01):
                    if cancelled():
                        return {'reply': 'Stopped.', 'spoken_reply': 'Stopped.', 'route': 'LOCAL',
                            'briefing': {'status': 'cancelled', 'completed_steps': [], 'model_calls': 0}}
                progress({'stage': 'done', 'completed_steps': ['search']})
                return {'reply': 'Synthetic private source excerpt.', 'spoken_reply': 'Ready.', 'route': 'LOCAL',
                    'briefing': {'status': 'complete', 'completed_steps': ['search'], 'model_calls': 0}}

        self.app.jobs = NotesJobs(self.root / '.data/jobs.sqlite3', self.root, runner_factory=Runner)
        self.addCleanup(self.app.close)
        self.addCleanup(self.release.set)

    def wait_terminal(self, identifier):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            detail = self.app.jobs.detail(identifier)
            if detail['status'] not in {'queued', 'running', 'cancelling'}:
                return detail
            time.sleep(.01)
        self.fail('The background job did not finish.')

    def test_chat_remains_free_and_local_commands_do_not_enter_provider_history(self):
        with patch.object(self.app.autonomy, 'submit') as organize:
            answer = self.app.chat('Make a briefing from my notes on Orion')
            self.assertTrue(self.started.wait(2))
            self.assertIn('job', answer)
            self.assertFalse(self.release.is_set())
            self.assertFalse(self.app.turn_lock.locked())
            duplicate = self.app.chat('Make a briefing from my notes on Orion')
            self.assertEqual(answer['job']['id'], duplicate['job']['id'])
            status = self.app.chat('Show jobs')
            self.assertEqual(len(status['jobs']), 1)
            self.app.chat('Cancel briefing')
            self.assertEqual(self.wait_terminal(answer['job']['id'])['status'], 'cancelled')
            organize.assert_not_called()
        self.assertEqual(self.app.history, [])
        self.assertEqual(self.brain.calls, [])

    def test_reset_keeps_job_and_results_only_appear_in_explicit_detail(self):
        identifier = self.app.chat('Make a briefing from my notes on Orion')['job']['id']
        self.assertTrue(self.started.wait(2))
        self.app.reset()
        self.release.set()
        self.assertEqual(self.wait_terminal(identifier)['result']['reply'], 'Synthetic private source excerpt.')
        self.assertNotIn('result', self.app.jobs.list()[0])
        self.assertNotIn('private source', self.app.chat('Show jobs')['reply'])
        self.assertEqual(self.app.history, [])
        self.assertEqual(self.brain.calls, [])

    def test_http_session_origin_write_guard_and_job_lifecycle(self):
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                   'Content-Type': 'application/json'}

        def request(method, path, value=None, supplied=None):
            connection = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                connection.request(method, path, json.dumps(value) if value is not None else None,
                                   headers if supplied is None else supplied)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        self.assertEqual(request('GET', '/api/jobs', supplied={})[0], 403)
        for endpoint in ('start', 'read', 'cancel', 'resume', 'delete'):
            path = '/api/jobs/' + endpoint
            self.assertEqual(request('POST', path, {}, {})[0], 403)
            self.assertEqual(request('POST', path, {}, {'Cookie': headers['Cookie']})[0], 403)
            self.assertEqual(request('POST', path, {}, {**headers, 'Origin': 'https://untrusted.example'})[0], 403)
        status, job = request('POST', '/api/jobs/start', {'topic': 'Orion', 'request_id': 'synthetic-request'})
        self.assertEqual(status, 200)
        identifier = job['id']
        self.assertTrue(self.started.wait(2))
        self.assertEqual(request('POST', '/api/jobs/start', {'topic': 'Orion', 'request_id': 'synthetic-request'})[1]['id'], identifier)
        self.assertEqual(request('POST', '/api/jobs/read', {'id': '../outside'})[0], 400)
        self.assertEqual(request('POST', '/api/jobs/delete', {'id': identifier})[0], 400)
        self.assertEqual(len(request('GET', '/api/jobs')[1]['jobs']), 1)
        self.assertEqual(request('POST', '/api/jobs/cancel', {'id': identifier})[0], 200)
        self.assertEqual(self.wait_terminal(identifier)['status'], 'cancelled')
        self.assertNotIn('result', request('POST', '/api/jobs/read', {'id': identifier})[1])
        self.assertEqual(request('POST', '/api/jobs/resume', {'id': identifier})[0], 400)
        self.assertEqual(request('POST', '/api/jobs/delete', {'id': identifier})[1], {'ok': True})
        self.assertEqual(request('GET', '/api/jobs')[1], {'jobs': []})

    def test_no_vault_produces_actionable_local_reply_without_provider(self):
        self.app._notes_briefing = None
        with patch.object(self.app, '_briefing_runner', side_effect=ValueError('Missing vault')):
            reply = self.app.chat('Make a briefing from my notes on Orion')
        self.assertIn('setup.bat', reply['reply'])
        self.assertEqual(self.brain.calls, [])


if __name__ == '__main__':
    unittest.main()

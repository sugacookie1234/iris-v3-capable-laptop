"""Local recipe evidence reaches review without leaking source content."""
import json
import http.client
import threading
import time
from unittest.mock import patch

from iris.agent_jobs.notes import NotesJobs
from iris.desktop.server import DesktopServer
from tests import test_desktop_jobs


class DesktopExperienceTests(test_desktop_jobs.DesktopJobTests):
    def setUp(self):
        super().setUp()
        self.app.jobs.close()

        class Runner:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, topic, cancelled, progress):
                return {'route': 'LOCAL', 'reply': 'PRIVATE EXCERPT', 'spoken_reply': 'Ready.',
                    'briefing': {'status': 'complete', 'model_calls': 0,
                        'completed_steps': ['search', 'read_1', 'draft'],
                        'verification': 'source_revision_and_excerpt_match',
                        'sources': [{'path': 'PRIVATE PATH.md', 'sha256': 'a' * 64}]}}

        self.app.jobs = NotesJobs(self.root / '.data/experience-jobs.sqlite3', self.root,
            runner_factory=Runner, on_completed=self.app._record_experience)

    # Parent lifecycle tests exercise a different blocking runner.
    test_chat_remains_free_and_local_commands_do_not_enter_provider_history = None
    test_reset_keeps_job_and_results_only_appear_in_explicit_detail = None
    test_http_session_origin_write_guard_and_job_lifecycle = None

    def test_capture_review_preview_and_forget_reconciliation(self):
        job = self.app.jobs.submit('PRIVATE TOPIC')
        self.wait_terminal(job['id'])
        items = self.app.experiences()
        self.assertEqual(len(items), 1)
        self.assertNotIn('PRIVATE', json.dumps(items))
        item = items[0]
        preview = 'Plan a briefing from my notes on Orion'
        self.assertNotIn('Reviewed local', self.app.chat(preview)['reply'])
        self.app.review_experience(item['id'], 1, 'keep')
        self.assertIn('Reviewed local', self.app.chat(preview)['reply'])
        self.app.review_experience(item['id'], 2, 'dispute')
        self.assertNotIn('Reviewed local', self.app.chat(preview)['reply'])
        self.app.forget_experience(item['id'], 3)
        self.app._experience_seen.clear()
        self.app._experiences = None
        self.assertEqual(self.app.experiences(), [])
        self.assertEqual(self.app.history, [])
        self.assertEqual(self.brain.calls, [])

    def test_capture_failure_preserves_result_and_later_reconciles(self):
        with patch.object(self.app, '_experience_store', side_effect=OSError('private error')):
            job = self.app.jobs.submit('PRIVATE TOPIC')
            self.assertEqual(self.wait_terminal(job['id'])['status'], 'completed')
            deadline = time.monotonic() + 3
            while not self.app.jobs.experience_capture_failed and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.app.jobs.experience_capture_failed)
        self.assertEqual(len(self.app.experiences()), 1)
        self.assertEqual(self.app.jobs.detail(job['id'])['result']['reply'], 'PRIVATE EXCERPT')

    def test_http_reviews_require_session_origin_and_current_revision(self):
        job = self.app.jobs.submit('PRIVATE TOPIC')
        self.wait_terminal(job['id'])
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                   'Content-Type': 'application/json'}

        def request(method, path, value=None, supplied=None):
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request(method, path, json.dumps(value) if value else None,
                                   headers if supplied is None else supplied)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        self.assertEqual(request('GET', '/api/experiences', supplied={})[0], 403)
        item = request('GET', '/api/experiences')[1]['items'][0]
        value = {'id': item['id'], 'revision': 1, 'decision': 'keep'}
        for endpoint in ('review', 'forget'):
            path = '/api/experiences/' + endpoint
            self.assertEqual(request('POST', path, value, {})[0], 403)
            self.assertEqual(request('POST', path, value, {'Cookie': headers['Cookie']})[0], 403)
            self.assertEqual(request('POST', path, value, {**headers, 'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(request('POST', '/api/experiences/review', value)[1]['state'], 'kept')
        self.assertEqual(request('POST', '/api/experiences/forget', value)[0], 400)
        value['revision'] = 2
        self.assertEqual(request('POST', '/api/experiences/forget', value)[0], 200)
        self.assertEqual(request('GET', '/api/experiences')[1]['items'], [])

    def test_missing_source_checks_cannot_become_experience(self):
        job = self.app.jobs.submit('PRIVATE TOPIC')
        result = self.wait_terminal(job['id'])['result']
        result['briefing']['verification'] = 'unverified'
        with patch.object(self.app.jobs, '_decode', return_value=result):
            self.assertIsNone(self.app.jobs.experience_event(job['id']))

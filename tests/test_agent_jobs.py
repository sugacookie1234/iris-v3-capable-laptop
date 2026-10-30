from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from iris.agent_jobs.notes import JobError, NotesJobs


def seal_fixture(data):
    """Deterministic test codec, never used by the application."""
    return b'test-only:' + bytes(byte ^ 0xA5 for byte in data)


def open_fixture(data):
    if not data.startswith(b'test-only:'):
        raise ValueError('Fixture is damaged')
    return bytes(byte ^ 0xA5 for byte in data[len(b'test-only:'):])


CODEC = (seal_fixture, open_fixture)


def answer(status='complete', reply='Synthetic private source excerpt.'):
    return {'route': 'LOCAL', 'reply': reply, 'spoken_reply': 'Briefing ready.',
            'briefing': {'status': status, 'model_calls': 0,
                         'completed_steps': ['search', 'read_1', 'draft']}}


class HeldRunner:
    def __init__(self, *, stop_on_cancel=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.stop_on_cancel = stop_on_cancel

    def factory(self, vault, history=None):
        return self

    def run(self, topic, cancelled=None, progress=None):
        self.calls.append(topic)
        progress({'stage': 'search', 'completed_steps': []})
        self.started.set()
        while not self.release.wait(.01):
            if self.stop_on_cancel and cancelled():
                return answer('cancelled')
        progress({'stage': 'done', 'completed_steps': ['search', 'read_1', 'draft']})
        return answer(reply='Synthetic private source excerpt about ' + topic)


class NotesJobsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'state' / 'jobs.sqlite3'
        self.vault = self.root / 'vault'
        self.vault.mkdir()

    def store(self, runner=None, **kwargs):
        kwargs.setdefault('codec', CODEC)
        store = NotesJobs(self.path, kwargs.pop('vault_path', self.vault), runner_factory=runner, **kwargs)
        self.addCleanup(store.close)
        return store

    def held(self, **kwargs):
        runner = HeldRunner(**kwargs)
        store = self.store(runner.factory)
        self.addCleanup(runner.release.set)
        return store, runner

    @contextmanager
    def database(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def wait_status(self, store, identifier, expected, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            detail = store.detail(identifier)
            if detail['status'] == expected:
                return detail
            time.sleep(.01)
        self.fail('Expected status %s, got %s' % (expected, detail['status']))

    @staticmethod
    def immediate(status='complete'):
        return lambda vault, history=None: SimpleNamespace(run=lambda *args, **kwargs: answer(status))

    def test_missing_vault_keeps_history_available_without_a_worker(self):
        store = self.store(vault_path=None)
        self.assertEqual(store.list(), [])
        self.assertIsNone(store._thread)
        with self.assertRaisesRegex(JobError, 'Configure an Obsidian vault'):
            store.submit('Orion')
        self.assertEqual(store.list(), [])
        store.close()
        store.close()

    def test_progress_and_result_detail_are_distinct_from_list(self):
        store, runner = self.held()
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        detail = store.detail(job['id'])
        self.assertEqual((detail['status'], detail['stage'], detail['completed_steps']), ('running', 'search', []))
        self.assertNotIn('result', detail)
        runner.release.set()
        detail = self.wait_status(store, job['id'], 'completed')
        self.assertEqual(detail['completed_steps'], ['search', 'read_1', 'draft'])
        self.assertEqual(detail['stage'], 'done')
        self.assertTrue(detail['result_available'])
        self.assertIn('Synthetic private source excerpt', detail['result']['reply'])
        self.assertNotIn('result', store.list()[0])
        self.assertGreater(detail['revision'], job['revision'])
        self.assertFalse(detail['can_cancel'])
        self.assertFalse(detail['can_resume'])

    def test_request_id_is_idempotent_across_concurrent_requests_and_reopen(self):
        store, runner = self.held()
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = list(pool.map(lambda _: store.submit('Orion', request_id='synthetic-request-123'), range(12)))
        self.assertEqual(len({job['id'] for job in jobs}), 1)
        self.assertTrue(runner.started.wait(3))
        self.assertEqual(runner.calls, ['Orion'])
        with self.assertRaisesRegex(JobError, 'different job'):
            store.submit('French', request_id='synthetic-request-123')
        runner.release.set()
        self.wait_status(store, jobs[0]['id'], 'completed')
        store.close()
        reopened = self.store(self.immediate())
        again = reopened.submit('Orion', request_id='synthetic-request-123')
        self.assertEqual(again['id'], jobs[0]['id'])
        self.assertEqual(again['attempts'], 1)
        self.assertIsNone(reopened._thread)

    def test_repeated_active_topic_joins_existing_job_without_request_id(self):
        store, runner = self.held()
        first = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        same = store.submit('  ORION  ')
        self.assertEqual(first['id'], same['id'])
        self.assertEqual(len(store.list()), 1)

    def test_pending_queue_is_bounded_and_cancelled_queued_job_never_runs(self):
        store, runner = self.held()
        first = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        queued = [store.submit('Queued topic %s' % index) for index in range(4)]
        with self.assertRaisesRegex(JobError, 'queue is full'):
            store.submit('Overflow')
        with self.assertRaisesRegex(JobError, 'Cancel this job'):
            store.delete(first['id'])
        cancelled = store.cancel(queued[0]['id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        replacement = store.submit('Replacement')
        runner.release.set()
        self.wait_status(store, replacement['id'], 'completed')
        self.assertNotIn('Queued topic 0', runner.calls)
        self.assertEqual(len(runner.calls), 5)

    def test_cancellation_wins_a_late_successful_result(self):
        store, runner = self.held()
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        self.assertEqual(store.cancel(job['id'])['status'], 'cancelling')
        runner.release.set()
        final = self.wait_status(store, job['id'], 'cancelled')
        self.assertFalse(final['result_available'])
        self.assertNotIn('result', final)
        with self.database() as db:
            self.assertIsNone(db.execute('SELECT result FROM notes_jobs').fetchone()[0])

    def test_startup_recovers_all_active_states_without_automatic_execution(self):
        store = self.store(self.immediate())
        with patch.object(store, '_start'):
            jobs = [store.submit('Synthetic topic %s' % i) for i in range(3)]
        store.close()
        with self.database() as db:
            for job, state in zip(jobs, ('queued', 'running', 'cancelling')):
                db.execute("UPDATE notes_jobs SET status=?,stage='read_1',steps='[\"search\"]' WHERE id=?", (state, job['id']))
        reopened = self.store(self.immediate())
        self.assertIsNone(reopened._thread)
        for job in reopened.list():
            self.assertEqual(job['status'], 'interrupted')
            self.assertEqual(job['error_code'], 'restart')
            self.assertEqual(job['completed_steps'], ['search'])
            self.assertEqual(job['attempts'], 1)
            self.assertTrue(job['can_resume'])
            self.assertFalse(job['result_available'])

    def test_resume_is_explicit_restarts_with_current_note_revisions_and_no_provider(self):
        note = self.vault / 'Orion.md'
        note.write_text('Orion original synthetic source.', encoding='utf-8')
        store = self.store()
        with patch.object(store, '_start'):
            job = store.submit('Orion')
        store.close()
        note.write_text('Orion updated synthetic source.', encoding='utf-8')
        reopened = self.store()
        with patch('iris.brain.providers.openai_compatible.OpenAICompatibleProvider.generate', side_effect=AssertionError('No provider')):
            resumed = reopened.resume(job['id'])
            self.assertEqual(resumed['completed_steps'], [])
            self.assertEqual(resumed['attempts'], 2)
            final = self.wait_status(reopened, job['id'], 'completed')
        self.assertIn('updated synthetic source', final['result']['reply'])
        self.assertNotIn('original synthetic source', final['result']['reply'])
        self.assertEqual(note.read_text(encoding='utf-8'), 'Orion updated synthetic source.')

    def test_resume_rejects_a_changed_vault(self):
        store = self.store()
        with patch.object(store, '_start'):
            job = store.submit('Orion')
        store.close()
        other = self.root / 'other-vault'
        other.mkdir()
        reopened = self.store(vault_path=other)
        self.assertFalse(reopened.detail(job['id'])['can_resume'])
        with self.assertRaisesRegex(JobError, 'vault changed'):
            reopened.resume(job['id'])
        self.assertEqual(reopened.detail(job['id'])['attempts'], 1)

    def test_failed_attempts_are_bounded(self):
        store = self.store(self.immediate('failed'))
        job = store.submit('Orion')
        for attempt in range(1, 4):
            final = self.wait_status(store, job['id'], 'failed')
            self.assertEqual(final['attempts'], attempt)
            self.assertEqual(final['can_resume'], attempt < 3)
            if attempt < 3:
                store.resume(job['id'])
        with self.assertRaisesRegex(JobError, 'cannot be resumed'):
            store.resume(job['id'])

    def test_shutdown_marks_interrupted_and_rejects_late_progress_and_result(self):
        store, runner = self.held(stop_on_cancel=True)
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        store.close()
        snapshot = self.path.read_bytes()
        store._progress(job['id'], 1, {'stage': 'draft', 'completed_steps': ['search']})
        self.assertEqual(self.path.read_bytes(), snapshot)
        with self.assertRaisesRegex(JobError, 'closing'):
            store.submit('French')
        reopened = self.store()
        self.assertEqual(reopened.detail(job['id'])['status'], 'interrupted')
        self.assertFalse(reopened.detail(job['id'])['result_available'])

    def test_shutdown_preserves_an_explicit_cancellation(self):
        store, runner = self.held(stop_on_cancel=True)
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        store.cancel(job['id'])
        store.close()
        reopened = self.store()
        self.assertEqual(reopened.detail(job['id'])['status'], 'cancelled')

    def test_idle_worker_releases_ownership_before_thread_exit(self):
        store = self.store(self.immediate())
        # Simulate the old thread still being alive while its target is returning.
        store._thread = SimpleNamespace(is_alive=lambda: True)
        store._work()
        self.assertIsNone(store._thread)
        job = store.submit('Orion')
        self.wait_status(store, job['id'], 'completed')

    def test_encryption_failure_before_submit_saves_nothing_and_starts_nothing(self):
        def unavailable(_):
            raise OSError('PRIVATE operating system details')
        store = self.store(codec=(unavailable, open_fixture))
        with self.assertRaisesRegex(JobError, 'could not be protected') as caught:
            store.submit('Synthetic private topic')
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(store.list(), [])
        self.assertIsNone(store._thread)
        self.assertNotIn(b'Synthetic private topic', self.path.read_bytes())

    def test_result_encryption_failure_is_failed_without_plaintext_persistence(self):
        def topics_only(raw):
            if not raw.startswith(b'"'):
                raise OSError('PRIVATE crypto exception')
            return seal_fixture(raw)
        store = self.store(self.immediate(), codec=(topics_only, open_fixture))
        job = store.submit('Orion')
        final = self.wait_status(store, job['id'], 'failed')
        self.assertFalse(final['result_available'])
        self.assertEqual(final['error_code'], 'worker_failure')
        self.assertNotIn('PRIVATE', str(final))
        self.assertNotIn(b'Synthetic private source excerpt', self.path.read_bytes())

    def test_corrupt_queued_topic_fails_once_without_stalling_queue(self):
        store = self.store(self.immediate())
        with patch.object(store, '_start'):
            bad = store.submit('Orion')
            good = store.submit('French')
        with self.database() as db:
            db.execute('UPDATE notes_jobs SET topic=? WHERE id=?', (b'PRIVATE corrupt payload', bad['id']))
        with store._condition:
            store._start()
        self.wait_status(store, good['id'], 'completed')
        with self.database() as db:
            self.assertEqual(db.execute('SELECT status FROM notes_jobs WHERE id=?', (bad['id'],)).fetchone()[0], 'failed')
        with self.assertRaisesRegex(JobError, 'cannot be unlocked'):
            store.detail(bad['id'])
        listed = {job['id']: job for job in store.list()}
        self.assertEqual(listed[good['id']]['topic'], 'French')
        unavailable = listed[bad['id']]
        self.assertEqual(unavailable['topic'], 'Unavailable encrypted topic')
        self.assertEqual(unavailable['status'], 'failed')
        self.assertTrue(unavailable['details_unavailable'])
        self.assertFalse(unavailable['can_resume'])
        self.assertFalse(unavailable['result_available'])
        self.assertNotIn('result', unavailable)
        self.assertNotIn('PRIVATE', str(listed))
        self.assertTrue(store.delete(bad['id'])['deleted'])
        self.assertEqual([job['id'] for job in store.list()], [good['id']])

    def test_corrupt_queued_topic_remains_cancellable_without_decrypting_it(self):
        store = self.store(self.immediate())
        with patch.object(store, '_start'):
            job = store.submit('Orion')
        with self.database() as db:
            db.execute('UPDATE notes_jobs SET topic=? WHERE id=?', (b'PRIVATE corrupt payload', job['id']))
        self.assertTrue(store.list()[0]['can_cancel'])
        cancelled = store.cancel(job['id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertTrue(cancelled['details_unavailable'])
        self.assertFalse(cancelled['can_cancel'])
        self.assertNotIn('PRIVATE', str(cancelled))
        self.assertEqual(store.list()[0]['status'], 'cancelled')
        self.assertTrue(store.delete(job['id'])['deleted'])

    def test_corrupt_running_topic_remains_cancellable_and_withholds_late_result(self):
        store, runner = self.held()
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        with self.database() as db:
            db.execute('UPDATE notes_jobs SET topic=? WHERE id=?', (b'PRIVATE corrupt payload', job['id']))
        self.assertTrue(store.list()[0]['can_cancel'])
        self.assertEqual(store.cancel(job['id'])['status'], 'cancelling')
        runner.release.set()
        deadline = time.monotonic() + 3
        while store.list()[0]['status'] != 'cancelled' and time.monotonic() < deadline:
            time.sleep(.01)
        final = store.list()[0]
        self.assertEqual(final['status'], 'cancelled')
        self.assertFalse(final['result_available'])
        self.assertFalse(final['can_cancel'])
        self.assertNotIn('PRIVATE', str(final))
        self.assertTrue(store.delete(job['id'])['deleted'])

    def test_transient_completion_write_failure_never_claims_success(self):
        store, runner = self.held()
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        original_db = store._db
        failed = threading.Event()

        @contextmanager
        def fail_completion_once():
            if threading.current_thread().name == 'iris-notes-jobs' and not failed.is_set():
                failed.set()
                raise sqlite3.OperationalError('PRIVATE storage failure')
            with original_db() as db:
                yield db

        store._db = fail_completion_once
        # Avoid consuming the fault with progress; inject exactly at result commit.
        with patch.object(store, '_progress'):
            runner.release.set()
            final = self.wait_status(store, job['id'], 'failed')
        self.assertTrue(failed.is_set())
        self.assertFalse(final['result_available'])
        self.assertNotIn('PRIVATE', str(final))
        with self.database() as db:
            self.assertIsNone(db.execute('SELECT result FROM notes_jobs').fetchone()[0])

    def test_terminal_delete_and_retention_bound(self):
        now = [datetime(2026, 10, 29, tzinfo=timezone.utc)]
        store = self.store(self.immediate(), clock=lambda: now[0])
        job = store.submit('Orion')
        self.wait_status(store, job['id'], 'completed')
        with self.database() as db:
            original = db.execute('SELECT * FROM notes_jobs').fetchone()
            for index in range(110):
                record = list(original)
                record[0] = '%032x' % index
                db.execute('INSERT INTO notes_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', record)
        self.assertEqual(len(store.list()), 100)
        identifier = store.list()[0]['id']
        self.assertTrue(store.delete(identifier)['deleted'])
        with self.assertRaisesRegex(JobError, 'no longer available'):
            store.detail(identifier)
        now[0] += timedelta(days=8)
        self.assertEqual(store.list(), [])

    def test_invalid_progress_and_worker_errors_have_no_private_error_text(self):
        def invalid(topic, cancelled=None, progress=None):
            progress({'stage': 'read_secret_file', 'completed_steps': ['PRIVATE source path']})
            return answer()
        store = self.store(lambda vault, history=None: SimpleNamespace(run=invalid))
        job = store.submit('Orion')
        final = self.wait_status(store, job['id'], 'failed')
        self.assertNotIn('PRIVATE', str(final))
        self.assertNotIn(b'PRIVATE source path', self.path.read_bytes())
        self.assertNotIn(b'read_secret_file', self.path.read_bytes())

    def test_action_receipt_failure_is_sticky_without_invalidating_verified_results(self):
        executor = SimpleNamespace(observer_failed=True)
        runner = SimpleNamespace(executor=executor, run=lambda *args, **kwargs: answer())
        store = self.store(lambda vault, history=None: runner)
        job = store.submit('Orion')
        self.wait_status(store, job['id'], 'completed')
        self.assertTrue(store.observer_failed)
        executor.observer_failed = False
        second = store.submit('French')
        self.wait_status(store, second['id'], 'completed')
        self.assertTrue(store.observer_failed)

    def test_oversized_serialized_result_fails_without_persisting_payload(self):
        result = answer()
        result['briefing']['unexpected_large_data'] = 'PRIVATE oversized marker ' * 4000
        store = self.store(lambda vault, history=None: SimpleNamespace(run=lambda *args, **kwargs: result))
        job = store.submit('Orion')
        final = self.wait_status(store, job['id'], 'failed')
        self.assertFalse(final['result_available'])
        self.assertNotIn(b'PRIVATE oversized marker', self.path.read_bytes())

    def test_old_attempt_callback_cannot_change_resumed_job_progress(self):
        callbacks = []
        retry = HeldRunner()

        def run(topic, cancelled=None, progress=None):
            callbacks.append(progress)
            if len(callbacks) == 1:
                return answer('failed')
            return retry.run(topic, cancelled=cancelled, progress=progress)

        store = self.store(lambda vault, history=None: SimpleNamespace(run=run))
        self.addCleanup(retry.release.set)
        job = store.submit('Orion')
        self.wait_status(store, job['id'], 'failed')
        store.resume(job['id'])
        self.assertTrue(retry.started.wait(3))
        callbacks[0]({'stage': 'draft', 'completed_steps': ['search', 'read_1']})
        current = store.detail(job['id'])
        self.assertEqual(current['attempts'], 2)
        self.assertEqual(current['stage'], 'search')
        self.assertEqual(current['completed_steps'], [])

    def test_persistent_storage_failure_exposes_error_and_recovers_as_interrupted(self):
        store, runner = self.held()
        job = store.submit('Orion')
        self.assertTrue(runner.started.wait(3))
        original = store._db

        @contextmanager
        def unavailable_to_worker():
            if threading.current_thread().name == 'iris-notes-jobs':
                raise sqlite3.OperationalError('PRIVATE storage details')
            with original() as db:
                yield db

        store._db = unavailable_to_worker
        runner.release.set()
        deadline = time.monotonic() + 3
        while not store._storage_failed and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(store._storage_failed)
        with self.assertRaisesRegex(JobError, 'storage failed') as caught:
            store.list()
        self.assertNotIn('PRIVATE', str(caught.exception))
        store.close()
        reopened = self.store()
        final = reopened.detail(job['id'])
        self.assertEqual(final['status'], 'interrupted')
        self.assertFalse(final['result_available'])

    @unittest.skipUnless(os.name == 'nt', 'Real Windows DPAPI protection')
    def test_real_dpapi_encrypts_topics_results_and_database_journal(self):
        store = self.store(self.immediate(), codec=None)
        job = store.submit('Synthetic private Orion topic', request_id='private-request-marker')
        final = self.wait_status(store, job['id'], 'completed')
        self.assertIn('Synthetic private source excerpt', final['result']['reply'])
        for path in self.path.parent.iterdir():
            raw = path.read_bytes()
            for value in (b'Synthetic private Orion topic', b'Synthetic private source excerpt',
                          b'private-request-marker', str(self.vault).encode()):
                self.assertNotIn(value, raw)
        # Keep a live rollback journal during a payload update, then inspect it too.
        with store._db() as db:
            db.execute('UPDATE notes_jobs SET topic=? WHERE id=?', (store._encode('Synthetic replacement topic'), job['id']))
            journal = Path(str(self.path) + '-journal')
            self.assertTrue(journal.exists())
            self.assertNotIn(b'Synthetic private Orion topic', journal.read_bytes())
            self.assertNotIn(b'Synthetic replacement topic', journal.read_bytes())


if __name__ == '__main__':
    unittest.main()

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import threading
import sys
from unittest.mock import patch

from cryptography.fernet import Fernet
from iris.generalist.continuity import ProjectContinuity, ContinuityError
from iris.tasks.models import Task
from iris.generalist.continuity import ProjectJournal
from iris.generalist.controlled_plan import PlanRun
from tests import test_controlled_plan as plan_fixtures


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'projects.sqlite3'
        cipher = Fernet(Fernet.generate_key())
        self.codec = (cipher.encrypt, cipher.decrypt)
        self.store = ProjectContinuity(self.path, codec=self.codec)

    def test_protected_restart_revision_and_delete_isolation(self):
        project = self.store.create('Orion synthetic', 'Owner supplied objective')
        task = Task('Synthetic linked task')
        project = self.store.link_task(project['id'], 1, task)
        restarted = ProjectContinuity(self.path, codec=self.codec)
        self.assertEqual(restarted.get(project['id']), project)
        self.assertNotIn(b'Orion synthetic', self.path.read_bytes())
        self.assertNotIn(task.id.encode(), self.path.read_bytes())
        with self.assertRaises(ContinuityError): restarted.delete(project['id'], 1)
        restarted.delete(project['id'], 2)
        self.assertEqual(restarted.list(), [])
        self.assertEqual(task.revision, 1)

    def test_bounds_duplicate_and_secret_rejection(self):
        for title in ('', 'x'*81, 'bad\nname'):
            with self.assertRaises(ContinuityError): self.store.create(title)
        with self.assertRaises(ContinuityError): self.store.create('test', 'x'*401)
        self.store.create('Orion')
        with self.assertRaises(ContinuityError): self.store.create('ORION')
        for i in range(9): self.store.create('project '+str(i))
        with self.assertRaises(ContinuityError): self.store.create('overflow')
        with self.assertRaises(ContinuityError): self.store.get('../file')

    def test_corruption_wrong_key_and_unsupported_version_fail_closed(self):
        project = self.store.create('Synthetic')
        wrong = Fernet(Fernet.generate_key())
        with self.assertRaises(ContinuityError):
            ProjectContinuity(self.path, codec=(wrong.encrypt, wrong.decrypt)).get(project['id'])
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('UPDATE projects SET payload=?', (b'corrupt',))
        with self.assertRaises(ContinuityError): self.store.get(project['id'])
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db: db.execute('PRAGMA user_version=99')
        with self.assertRaises(ContinuityError): ProjectContinuity(self.path, codec=self.codec)

    def test_failed_encryption_does_not_save_plaintext(self):
        with patch.object(self.store, '_seal', side_effect=OSError('synthetic')):
            with self.assertRaises(ContinuityError): self.store.create('Protected only')
        self.assertEqual(self.store.list(), [])

    def test_unknown_payload_fields_and_version_rejected(self):
        project = self.store.create('Synthetic')
        for changed in (dict(project, approved=True), dict(project, version=2)):
            payload = self.codec[0](json.dumps(changed).encode())
            with self.assertRaises(ContinuityError): self.store._decode(project['id'], payload)

    def test_path_redirection_denied(self):
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaises(ContinuityError): ProjectContinuity(self.path, codec=self.codec)

    def test_task_reference_limits_and_stale_revision(self):
        project = self.store.create('Synthetic')
        for i in range(5):
            project = self.store.link_task(project['id'], project['revision'], Task(str(i)))
        with self.assertRaises(ContinuityError): self.store.link_task(project['id'], project['revision'], Task('six'))
        with self.assertRaises(ContinuityError): self.store.link_task(project['id'], 1, Task('stale'))

    def test_concurrent_revision_conflicts_do_not_overwrite(self):
        project = self.store.create('Concurrent synthetic')
        outcomes = []
        def link():
            try:
                self.store.link_task(project['id'], 1, Task('Synthetic'))
                outcomes.append('saved')
            except ContinuityError:
                outcomes.append('stale')
        threads = [threading.Thread(target=link) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertCountEqual(outcomes, ['saved','stale'])
        self.assertEqual(len(self.store.get(project['id'])['resources']), 1)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows DPAPI account-bound protection')
    def test_actual_windows_protection_synthetic_only(self):
        store = ProjectContinuity(Path(self.temp.name) / 'dpapi.sqlite3')
        project = store.create('Synthetic account protected')
        self.assertEqual(ProjectContinuity(store.path).get(project['id']), project)
        self.assertNotIn(b'Synthetic account protected', store.path.read_bytes())


if __name__ == '__main__':
    unittest.main()


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = plan_fixtures.PlanRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app = self.fixture.app
        cipher = Fernet(Fernet.generate_key())
        self.codec = cipher.encrypt, cipher.decrypt
        self.path = self.app.data_dir / 'projects.sqlite3'
        self.app._projects = ProjectContinuity(self.path, codec=self.codec)
        self.project = self.app._projects.create('Orion synthetic', 'Read only demonstration')
        self.app.chat('/project select ' + self.project['id'])

    def test_real_handlers_restart_evidence_fresh_preview_and_no_replay(self):
        preview = self.fixture.preview()
        self.assertIn('No actions have been executed', preview['reply'])
        self.assertEqual(self.app.action_history.rows(), [])
        old = self.app._pending_host_plan
        result = self.fixture.confirm()
        self.assertEqual([r['status'] for r in result['plan_receipts']], ['completed','completed'])
        restarted = ProjectContinuity(self.path, codec=self.codec)
        summary = restarted.summary(self.project['id'], self.app.action_history)
        self.assertEqual(summary.count('previously verified returned data'), 2)
        self.assertIn('Nothing has been resumed', summary)
        self.app._plan_run = None; self.app._selected_project = None
        self.app._plan_session = 'new-session'
        self.assertIn('No matching pending', self.app.chat(f'/confirm-plan {old.id} 1 {old.digest}')['reply'])
        self.app.chat('/project select ' + self.project['id'])
        self.fixture.preview()
        self.assertNotEqual(old.id, self.app._pending_host_plan.id)
        self.assertEqual(len(self.app.action_history.rows()), 2)
        self.assertNotIn(b'Synthetic project notes', self.path.read_bytes())
        self.assertNotIn(b'README.md', self.path.read_bytes())

    def test_interrupted_states_never_become_verified_or_resume(self):
        self.fixture.preview()
        run = self.app._plan_run
        for state in ('awaiting_confirmation','awaiting_approval','running','verifying','cancelled','uncertain'):
            run.state = state
            run.active_step = None if state == 'awaiting_confirmation' else run.plan.plan.nodes[0].id
            run._checkpoint()
            before = self.path.read_bytes()
            for _ in range(2):
                recovered = ProjectContinuity(self.path, codec=self.codec)
                summary = recovered.summary(self.project['id'], self.app.action_history)
                self.assertNotIn('previously verified', summary)
                self.assertIn('Nothing has been resumed', summary)
            self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.app.action_history.rows(), [])

    def test_missing_action_evidence_invalidates_completion_claim(self):
        self.fixture.preview(); self.fixture.confirm()
        self.app.action_history.clear()
        summary = self.app._projects.summary(self.project['id'], self.app.action_history)
        self.assertNotIn('previously verified', summary)
        self.assertIn('outcome unknown', summary)

    def test_private_local_context_and_default_off(self):
        local = self.app.working_context.local_project()
        self.assertEqual(local['id'], self.project['id'])
        snapshot = self.app.working_context.snapshot(self.app.orchestrator)
        self.assertNotIn(self.project['id'], json.dumps(snapshot))
        self.app.working_context.clock = lambda: local['expires_at'] + 1
        self.assertIsNone(self.app.working_context.local_project())
        self.assertEqual(self.app._selected_project, self.project['id'])
        self.app.settings['IRIS_EXPERIMENTAL_INTERPRETATION'] = 'false'
        self.assertIn('disabled', self.app.chat('/project create not saved')['reply'])
        self.assertEqual(len(self.app._projects.list()), 1)

    def test_deletion_invalidates_pending_plan_without_deleting_sources(self):
        self.fixture.preview()
        project = self.app._projects.get(self.project['id'])
        self.app.chat(f"/project delete {project['id']} {project['revision']}")
        result = self.fixture.confirm()
        self.assertEqual(result['plan_receipts'][0]['verification'], 'unknown')
        self.assertEqual(self.app.action_history.rows(), [])
        self.assertTrue((self.fixture.root / 'README.md').exists())

    def test_failed_journal_before_invocation_blocks_tools(self):
        self.fixture.preview()
        with patch.object(self.app._projects, '_seal', side_effect=OSError('synthetic storage failure')):
            answer = self.fixture.confirm()
        self.assertEqual(answer['plan_receipts'][0]['status'], 'uncertain')
        self.assertEqual(self.app.action_history.rows(), [])

    def test_crash_after_tool_return_before_verification_is_uncertain(self):
        self.fixture.preview()
        with patch('iris.generalist.controlled_plan.verify_result', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.fixture.confirm()
        summary = ProjectContinuity(self.path, codec=self.codec).summary(self.project['id'], self.app.action_history)
        self.assertIn('outcome unknown', summary)
        self.assertNotIn('previously verified', summary)
        self.assertEqual(len(self.app.action_history.rows()), 1)

    def test_retention_and_schema_authority_refusal(self):
        for _ in range(12): self.fixture.preview()
        project = self.app._projects.get(self.project['id'])
        self.assertEqual(len(project['workflows']), 10)
        bad = dict(project['workflows'][0], approved=True)
        with self.assertRaises(ContinuityError): self.app._projects.journal(project['id'], project['revision'], bad)
        self.assertEqual(self.app.action_history.rows(), [])

    def test_task_revision_changes_block_execution_and_deletion_preserves_task(self):
        from iris.tasks.store import TaskStore
        with TaskStore(self.app.tasks_path) as tasks:
            task = tasks.create('Synthetic task')
        self.assertIn('linked locally', self.app.chat(f'/project link-task {task.id} {task.revision}')['reply'])
        self.fixture.preview()
        with closing(sqlite3.connect(self.app.tasks_path, isolation_level=None)) as db:
            raw = json.loads(db.execute('SELECT data FROM tasks WHERE id=?', (task.id,)).fetchone()[0])
            raw['revision'] += 1
            db.execute('UPDATE tasks SET data=? WHERE id=?', (json.dumps(raw), task.id))
        self.assertEqual(self.fixture.confirm()['plan_receipts'][0]['verification'], 'not_executed')
        self.assertEqual(self.app.action_history.rows(), [])
        self.assertIn('changed or unavailable', self.app.chat('/project show '+self.project['id'])['reply'])
        project = self.app._projects.get(self.project['id'])
        self.app.chat(f"/project delete {project['id']} {project['revision']}")
        with TaskStore(self.app.tasks_path, read_only=True) as tasks:
            self.assertEqual(tasks.fetch(task.id).revision, 2)

    def test_approval_denial_and_permission_revocation_remain_authoritative(self):
        from iris.tools import Approval
        self.fixture.preview()
        denied = self.fixture.confirm(lambda operation, **_: Approval(operation.id, False))
        self.assertEqual(denied['plan_receipts'][0]['failure'], 'approval_rejected')
        self.fixture.preview()
        self.app.brain._tool_permissions = frozenset()
        self.assertEqual(self.fixture.confirm()['plan_receipts'][0]['verification'], 'not_executed')

    def test_explicit_selection_only_and_no_provider_history_export(self):
        self.assertIn('could not be validated', self.app.chat('/project select that project')['reply'])
        self.assertEqual(self.app.history, [])
        self.assertIn('Nothing has been resumed', self.app.chat('/project resume '+self.project['id'])['reply'])
        self.assertEqual(self.app.history, [])
        self.assertEqual(len(self.fixture.fast.requests), 0)

    def test_fresh_runtime_requires_selection_and_new_confirmation(self):
        from iris.desktop.runtime import DesktopRuntime
        from iris.tools import ToolExecutor
        from iris.tools.workspace import workspace_registry
        from tests import test_brain_engine as brain_fixtures
        self.fixture.preview(); self.fixture.confirm()
        old = self.app._pending_host_plan
        self.app.close()
        brain, fast, _ = brain_fixtures.BrainEngineTests().make_brain()
        brain._tool_executor = ToolExecutor(workspace_registry(self.fixture.root))
        brain._tool_permissions = frozenset({'workspace.read'})
        restarted = DesktopRuntime(settings=self.app.settings, data_dir=self.app.data_dir, brain=brain)
        self.addCleanup(restarted.close)
        restarted._projects = ProjectContinuity(self.path, codec=self.codec)
        self.assertIsNone(restarted._selected_project)
        self.assertIsNone(restarted._plan_run)
        self.assertIsNone(restarted.working_context.local_project())
        self.assertIn('No matching pending', restarted.chat(f'/confirm-plan {old.id} 1 {old.digest}')['reply'])
        answer = restarted.chat('/project resume '+self.project['id'])
        self.assertEqual(answer['reply'].count('previously verified returned data'), 2)
        self.assertIsNone(restarted._selected_project)  # Inspect is not select or execute.
        self.assertEqual(len(fast.requests), 0)

    def test_cancel_and_close_survive_missing_store_evidence(self):
        self.fixture.preview()
        project = self.app._projects.get(self.project['id'])
        self.app._projects.delete(project['id'], project['revision'])
        self.app.close()
        self.assertTrue(self.app._plan_run.cancel_event.is_set())
        self.assertEqual(self.app.action_history.rows(), [])

    def test_cancel_during_approval_blocks_tool_and_records_uncertainty(self):
        from iris.tools import Approval
        self.fixture.preview()
        def cancel(operation, **_):
            self.app._plan_run.cancel(self.app._pending_host_plan.id)
            return Approval(operation.id, True)
        result = self.fixture.confirm(cancel)
        self.assertNotEqual(result['plan_receipts'][0]['status'], 'completed')
        self.assertNotIn('previously verified', self.app._projects.summary(self.project['id'], self.app.action_history))

    def test_failed_final_journal_does_not_report_verified_completion(self):
        self.fixture.preview()
        original = self.app._projects.journal
        def fail_on_receipt(identifier, revision, record):
            if any(step['state'] == 'completed' for step in record['steps']):
                raise ContinuityError('Synthetic interruption before durable completion')
            return original(identifier, revision, record)
        with patch.object(self.app._projects, 'journal', side_effect=fail_on_receipt):
            result = self.fixture.confirm()
        self.assertEqual(result['plan_receipts'][0]['status'], 'uncertain')
        self.assertEqual(len(self.app.action_history.rows()), 1)
        self.assertNotIn('previously verified', self.app._projects.summary(self.project['id'], self.app.action_history))


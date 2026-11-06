"""Disposable encrypted portability tests; no owner stores or network providers."""
import base64
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from iris import backup
from iris.generalist.continuity import ProjectContinuity, ContinuityError


class ProjectBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'; self.source.mkdir()
        self.archive = self.root/'portable.iris'; self.target = self.root/'restored'
        self.a, self.b = Fernet(Fernet.generate_key()), Fernet(Fernet.generate_key())
        self.archive_cipher = Fernet(Fernet.generate_key())
        # Existing BackupTests exercises production Scrypt; these isolate transforms.
        self.cipher_patch = patch('iris.backup._cipher', return_value=self.archive_cipher)
        self.cipher_patch.start(); self.addCleanup(self.cipher_patch.stop)
        self.store = ProjectContinuity(self.source/'projects.sqlite3', codec=(self.a.encrypt,self.a.decrypt))
        self.project = self.store.create('Synthetic portable Orion', 'Private synthetic recovery objective')
        self.before = self.store.path.read_bytes()

    def create(self):
        with patch('iris.desktop.secrets.unprotect', side_effect=self.a.decrypt):
            return backup.create(self.source,self.archive,'synthetic passphrase',app_stopped=True)

    def restore(self):
        with patch('iris.desktop.secrets.protect', side_effect=self.b.encrypt), patch('iris.desktop.secrets.unprotect', side_effect=self.b.decrypt):
            return backup.restore(self.archive,self.target,'synthetic passphrase',app_stopped=True)

    def manifest(self):
        return json.loads(self.archive_cipher.decrypt(self.archive.read_bytes()[len(backup.MAGIC)+16:]))

    def write_manifest(self, manifest):
        self.archive.write_bytes(backup.MAGIC+b'0'*16+self.archive_cipher.encrypt(json.dumps(manifest).encode()))

    def test_cross_account_transform_and_plaintext_disk_exclusion(self):
        with self.assertRaises(ContinuityError):
            ProjectContinuity(self.store.path,codec=(self.b.encrypt,self.b.decrypt)).get(self.project['id'])
        self.create()
        manifest = self.manifest()
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(base64.b64decode(manifest['stores']['projects.sqlite3']))
            raw = db.execute('SELECT payload FROM projects').fetchone()[0]
            self.assertEqual(json.loads(raw),self.project)
        original_write = Path.write_bytes
        staged = []
        def inspect(path, data):
            if path.name == 'projects.sqlite3':
                self.assertNotIn(b'Synthetic portable Orion',data)
                self.assertNotIn(b'Private synthetic recovery objective',data)
                staged.append(path)
            return original_write(path,data)
        with patch.object(Path,'write_bytes',new=inspect): self.restore()
        self.assertEqual(len(staged),1)
        restored = ProjectContinuity(self.target/'projects.sqlite3',codec=(self.b.encrypt,self.b.decrypt))
        self.assertEqual(restored.get(self.project['id']),self.project)
        self.assertNotEqual(restored.path.read_bytes(),self.before)
        self.assertEqual(self.store.path.read_bytes(),self.before)
        self.assertNotIn(b'Synthetic portable Orion',self.archive.read_bytes())
        self.assertFalse(list(self.root.glob('.iris-*')))
        with self.assertRaises(backup.BackupError): self.restore()

    def test_unreadable_envelope_aborts_entire_export(self):
        with closing(sqlite3.connect(self.store.path, isolation_level=None)) as db:
            db.execute('UPDATE projects SET payload=?',(b'wrong account or corrupt',))
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(backup.BackupError,'original Windows'): self.create()
        self.assertFalse(self.archive.exists())
        self.assertEqual(self.store.path.read_bytes(),before)

    def test_schema_and_envelope_refusals(self):
        statements = ('PRAGMA user_version=9', 'CREATE TABLE surprise (x TEXT)',
                      'CREATE TRIGGER unexpected AFTER UPDATE ON projects BEGIN DELETE FROM projects; END')
        for statement in statements:
            self.store.path.write_bytes(self.before)
            with closing(sqlite3.connect(self.store.path,isolation_level=None)) as db: db.execute(statement)
            with self.assertRaises(backup.BackupError): self.create()
            self.assertFalse(self.archive.exists())
        for changed in (dict(self.project,version=2), dict(self.project,approved=True), dict(self.project,title='x'*81)):
            self.store.path.write_bytes(self.before)
            with closing(sqlite3.connect(self.store.path,isolation_level=None)) as db:
                db.execute('UPDATE projects SET payload=?',(self.a.encrypt(json.dumps(changed).encode()),))
            with self.assertRaises(backup.BackupError): self.create()

    def test_duplicate_identity_schema_and_duplicate_json_refused(self):
        self.store.path.unlink()
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('CREATE TABLE projects (id TEXT, payload BLOB NOT NULL)')
            db.execute('PRAGMA user_version=1')
            db.executemany('INSERT INTO projects VALUES (?,?)',[(self.project['id'],self.a.encrypt(json.dumps(self.project).encode()))]*2)
            db.commit()
        with self.assertRaises(backup.BackupError): self.create()
        self.store.path.write_bytes(self.before)
        raw=json.dumps(self.project).replace('"version": 1','"version": 1, "version": 1')
        with closing(sqlite3.connect(self.store.path,isolation_level=None)) as db:
            db.execute('UPDATE projects SET payload=?',(self.a.encrypt(raw.encode()),))
        with self.assertRaises(backup.BackupError): self.create()

    def test_strict_manifest_compatibility(self):
        self.create(); valid=self.manifest()
        for invalid in (dict(valid,version=2),dict(valid,unexpected=True),{'version':1,'stores':{'other.sqlite3':'AA=='}}):
            self.write_manifest(invalid)
            with self.assertRaises(backup.BackupError): self.restore()
            self.assertFalse(self.target.exists())
        self.write_manifest(valid)
        self.restore()

    def test_corrupt_and_oversized_source(self):
        with patch('iris.backup.MAX_BYTES',1):
            with self.assertRaises(backup.BackupError): self.create()
        self.store.path.write_bytes(b'not sqlite')
        with self.assertRaises((backup.BackupError,sqlite3.Error)): self.create()
        self.assertFalse(self.archive.exists())

    def test_reprotection_failure_and_interrupted_publication_leave_no_destination(self):
        self.create()
        with patch('iris.desktop.secrets.protect',side_effect=OSError('synthetic failure')):
            with self.assertRaises(backup.BackupError):
                backup.restore(self.archive,self.target,'synthetic passphrase',app_stopped=True)
        self.assertFalse(self.target.exists())
        with patch('iris.backup.os.rename',side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError): self.restore()
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.iris-restore-*')))
        self.assertEqual(self.store.path.read_bytes(),self.before)

    def test_protection_must_roundtrip_before_writing_any_project_file(self):
        self.create()
        with patch('iris.desktop.secrets.protect',return_value=b'invalid protection'):
            with self.assertRaises(backup.BackupError):
                backup.restore(self.archive,self.target,'synthetic passphrase',app_stopped=True)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('.iris-restore-*')))

    def test_path_redirection_rejected(self):
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(backup.BackupError): self.create()
        if hasattr(Path,'is_junction'):
            with patch.object(Path,'is_junction',return_value=True):
                with self.assertRaises(backup.BackupError): self.create()

    @unittest.skipUnless(sys.platform=='win32','Windows DPAPI')
    def test_actual_windows_dpapi_roundtrip(self):
        from iris.desktop.secrets import protect,unprotect
        with closing(sqlite3.connect(self.store.path,isolation_level=None)) as db:
            db.execute('UPDATE projects SET payload=?',(protect(json.dumps(self.project).encode()),))
        backup.create(self.source,self.archive,'synthetic passphrase',app_stopped=True)
        backup.restore(self.archive,self.target,'synthetic passphrase',app_stopped=True)
        self.assertEqual(ProjectContinuity(self.target/'projects.sqlite3').get(self.project['id']),self.project)

    def test_authenticated_malformed_portable_records_do_not_publish(self):
        self.create(); original=self.manifest()
        for malformed in (dict(self.project,version=99),dict(self.project,export='configured_reasoning')):
            manifest=json.loads(json.dumps(original))
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(base64.b64decode(manifest['stores']['projects.sqlite3']))
                db.execute('UPDATE projects SET payload=?',(json.dumps(malformed).encode(),)); db.commit()
                manifest['stores']['projects.sqlite3']=base64.b64encode(db.serialize()).decode()
            self.write_manifest(manifest)
            with self.assertRaises(backup.BackupError): self.restore()
            self.assertFalse(self.target.exists())
            self.assertFalse(list(self.root.glob('.iris-restore-*')))

    def test_archive_encryption_failure_never_publishes_plaintext(self):
        with patch.object(self.archive_cipher,'encrypt',side_effect=OSError('synthetic encryption failure')):
            with self.assertRaises(OSError): self.create()
        self.assertFalse(self.archive.exists())
        self.assertFalse(list(self.root.glob('.iris-backup-*')))
        self.assertEqual(self.store.path.read_bytes(),self.before)

    def test_legacy_archive_without_projects_keeps_task_goal_and_notes_data(self):
        from iris.tasks.store import TaskStore
        from iris.goals.store import GoalStore
        self.store.path.unlink()
        with TaskStore(self.source/'tasks.sqlite3') as tasks: task=tasks.create('Synthetic task')
        with GoalStore(self.source/'goals.sqlite3') as goals: goal=goals.create('Synthetic goal')
        with closing(sqlite3.connect(self.source/'jobs.sqlite3')) as db:
            db.execute('CREATE TABLE notes_jobs (id TEXT, topic BLOB, result BLOB)')
            db.execute('INSERT INTO notes_jobs VALUES (?,?,?)',('synthetic',self.a.encrypt(b'topic'),self.a.encrypt(b'result')))
            db.commit()
        self.assertNotIn('projects.sqlite3',self.create())
        self.restore()
        with TaskStore(self.target/'tasks.sqlite3',read_only=True) as tasks: self.assertEqual(tasks.fetch(task.id),task)
        with GoalStore(self.target/'goals.sqlite3',read_only=True) as goals: self.assertEqual(goals.fetch(goal.id),goal)
        with closing(sqlite3.connect(self.target/'jobs.sqlite3')) as db:
            topic,result=db.execute('SELECT topic,result FROM notes_jobs').fetchone()
        self.assertEqual(self.b.decrypt(topic),b'topic'); self.assertEqual(self.b.decrypt(result),b'result')


class PortableWorkflowTests(unittest.TestCase):
    def test_restored_real_workflow_requires_fresh_authority(self):
        from tests import test_project_continuity as fixtures
        from tests import test_brain_engine as brain_fixtures
        from tests.test_controlled_plan import proposal
        from iris.desktop.runtime import DesktopRuntime
        from iris.tasks.store import TaskStore
        from iris.tools import ToolExecutor
        from iris.tools.workspace import workspace_registry
        from iris.brain.llm import LLMResponse
        fixture=fixtures.ProjectLifecycleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        app=fixture.app
        with TaskStore(app.tasks_path) as tasks: task=tasks.create('Portable synthetic task')
        app.chat(f'/project link-task {task.id} {task.revision}')
        fixture.fixture.preview(); fixture.fixture.confirm()
        fixture.fixture.preview()
        app._plan_run.state='verifying'  # Simulated interruption; no third read occurs.
        app._plan_run.active_step=app._pending_host_plan.plan.nodes[0].id
        app._plan_run._checkpoint()
        old=app._pending_host_plan
        project=app._projects.get(fixture.project['id'])
        app.close()
        archive=app.data_dir.parent/'portable.iris'; target=app.data_dir.parent/'restored'
        cipher=Fernet(Fernet.generate_key()); account_b=Fernet(Fernet.generate_key())
        with patch('iris.backup._cipher',return_value=cipher):
            with patch('iris.desktop.secrets.unprotect',side_effect=fixture.codec[1]):
                backup.create(app.data_dir,archive,'synthetic passphrase',app_stopped=True)
            with patch('iris.desktop.secrets.protect',side_effect=account_b.encrypt), patch('iris.desktop.secrets.unprotect',side_effect=account_b.decrypt):
                backup.restore(archive,target,'synthetic passphrase',app_stopped=True)
        brain,fast,_=brain_fixtures.BrainEngineTests().make_brain()
        brain._tool_executor=ToolExecutor(workspace_registry(fixture.fixture.root))
        brain._tool_permissions=frozenset({'workspace.read'})
        new=DesktopRuntime(settings=app.settings,data_dir=target,brain=brain); self.addCleanup(new.close)
        new._projects=ProjectContinuity(target/'projects.sqlite3',codec=(account_b.encrypt,account_b.decrypt))
        self.assertEqual(new._projects.get(project['id']),project)
        self.assertIsNone(new._selected_project); self.assertIsNone(new._plan_run)
        self.assertIn('No matching pending',new.chat(f'/confirm-plan {old.id} 1 {old.digest}')['reply'])
        recovered=new.chat('/project resume '+project['id'])['reply']
        self.assertEqual(recovered.count('previously verified returned data'),2)
        self.assertIn('outcome unknown',recovered)
        self.assertIn('1 task references match',recovered)
        self.assertEqual(len(fast.requests),0)
        new.chat('/project select '+project['id'])
        def generate(request):
            turn=json.loads(request.messages[-1].content)['turn']
            return LLMResponse(proposal(turn),'fast','fast-model')
        with patch.object(fast,'generate',side_effect=generate):
            self.assertIn('No actions have been executed',new.chat('/plan workspace List and read README.md')['reply'])
        self.assertNotEqual(old.id,new._pending_host_plan.id)
        self.assertEqual(len(new.action_history.rows()),2)
        new.action_history.clear()
        self.assertNotIn('previously verified',new.chat('/project resume '+project['id'])['reply'])
        with TaskStore(new.tasks_path) as tasks: tasks.complete(task.id)
        self.assertIn('changed or unavailable',new.chat('/project show '+project['id'])['reply'])
        with patch.object(new,'_tool_approval',side_effect=AssertionError('No approval may be requested')):
            run=new._pending_host_plan
            failed=new.chat(f'/confirm-plan {run.id} 1 {run.digest}')
        self.assertEqual(failed['plan_receipts'][0]['verification'],'not_executed')
        missing=new.tasks_path.with_suffix('.missing')
        new.tasks_path.rename(missing)
        try:
            self.assertIn('changed or unavailable',new.chat('/project show '+project['id'])['reply'])
        finally:
            missing.rename(new.tasks_path)
        current=new._projects.get(project['id'])
        new.chat(f"/project delete {project['id']} {current['revision']}")
        with TaskStore(new.tasks_path,read_only=True) as tasks: self.assertIsNotNone(tasks.fetch(task.id))

    def test_recovery_options_are_non_destructive_without_unlocking_store(self):
        from tests import test_project_continuity as fixtures
        fixture=fixtures.ProjectLifecycleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        app=fixture.app
        with patch.object(app._projects,'get',side_effect=ContinuityError('unreadable')):
            self.assertIn('/project recovery',app.chat('/project show '+fixture.project['id'])['reply'])
        app.settings['IRIS_EXPERIMENTAL_INTERPRETATION']='false'
        with patch.object(app,'_project_store',side_effect=AssertionError('No store access')):
            answer=app.chat('/project recovery')['reply']
        self.assertIn('original Windows',answer)
        self.assertIn('nothing was changed',answer)
        self.assertEqual(len(fixture.fixture.fast.requests),0)


if __name__=='__main__': unittest.main()

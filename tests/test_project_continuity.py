from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from iris.generalist.continuity import ProjectContinuity, ContinuityError
from iris.tasks.models import Task


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


if __name__ == '__main__':
    unittest.main()


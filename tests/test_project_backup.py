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


if __name__=='__main__': unittest.main()

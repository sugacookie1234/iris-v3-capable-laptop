from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from iris.backup import create,restore,BackupError

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.archive=self.root/'backup.iris';self.target=self.root/'recovered'
        self.password='synthetic recovery phrase only'
        with closing(sqlite3.connect(self.source/'memory.sqlite3')) as db:
            db.execute('CREATE TABLE reviews (id TEXT, state TEXT)')
            db.execute("INSERT INTO reviews VALUES ('synthetic','pending')");db.commit()
        (self.source/'config.dpapi').write_bytes(b'excluded synthetic credential')
        self.before=(self.source/'memory.sqlite3').read_bytes()
    def backup(self):return create(self.source,self.archive,self.password,app_stopped=True)
    def test_roundtrip_pending_reviews_and_exclusions(self):
        self.assertEqual(self.backup(),('memory.sqlite3',))
        self.assertNotIn(b'pending',self.archive.read_bytes())
        restore(self.archive,self.target,self.password,app_stopped=True)
        with closing(sqlite3.connect(self.target/'memory.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT state FROM reviews').fetchone(),('pending',))
        self.assertFalse((self.target/'config.dpapi').exists())
        self.assertEqual((self.source/'memory.sqlite3').read_bytes(),self.before)
    def test_wrong_password_tamper_and_truncation(self):
        self.backup();valid=self.archive.read_bytes()
        for value,password in [(valid,'wrong synthetic password'),(valid[:-10],self.password),(valid[:-20]+b'Z'*20,self.password),(b'invalid',self.password)]:
            self.archive.write_bytes(value)
            with self.assertRaises(BackupError):restore(self.archive,self.target,password,app_stopped=True)
            self.assertFalse(self.target.exists())
    def test_conflicts_and_interrupted_publication(self):
        self.backup()
        with self.assertRaises(BackupError):self.backup()
        self.target.mkdir();(self.target/'owner').write_bytes(b'preserve')
        with self.assertRaises(BackupError):restore(self.archive,self.target,self.password,app_stopped=True)
        self.assertEqual((self.target/'owner').read_bytes(),b'preserve')
        with patch('iris.backup.os.link',side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError):create(self.source,self.root/'another.iris',self.password,app_stopped=True)
        self.assertFalse(list(self.root.glob('.iris-backup-*')))
        with patch('iris.backup.os.rename',side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError):restore(self.archive,self.root/'new',self.password,app_stopped=True)
        self.assertFalse((self.root/'new').exists())
        self.assertFalse(list(self.root.glob('.iris-restore-*')))
    def test_stop_assertion_required(self):
        with self.assertRaises(BackupError):create(self.source,self.archive,self.password)

    def test_authenticated_hostile_manifest_cannot_escape_or_publish_invalid_database(self):
        import base64,json,os
        from iris.backup import MAGIC,_cipher
        for name in ('../escape.sqlite3','memory.sqlite3'):
            salt=os.urandom(16)
            manifest={'version':1,'stores':{name:base64.b64encode(b'not a sqlite database').decode()}}
            self.archive.write_bytes(MAGIC+salt+_cipher(self.password,salt).encrypt(json.dumps(manifest).encode()))
            with self.assertRaises((BackupError,sqlite3.Error)):
                restore(self.archive,self.target,self.password,app_stopped=True)
            self.assertFalse(self.target.exists())
            self.assertFalse((self.root/'escape.sqlite3').exists())
            self.assertFalse(list(self.root.glob('.iris-restore-*')))
            self.assertEqual((self.source/'memory.sqlite3').read_bytes(),self.before)
    def test_jobs_payloads_are_reprotected_on_restore(self):
        from iris.desktop.secrets import protect,unprotect
        with closing(sqlite3.connect(self.source/'jobs.sqlite3')) as db:
            db.execute('CREATE TABLE notes_jobs (id TEXT, topic BLOB, result BLOB)')
            db.execute('INSERT INTO notes_jobs VALUES (?,?,?)',('synthetic',protect(b'synthetic topic'),protect(b'synthetic result')));db.commit()
        self.backup();restore(self.archive,self.target,self.password,app_stopped=True)
        with closing(sqlite3.connect(self.target/'jobs.sqlite3')) as db:
            topic,result=db.execute('SELECT topic,result FROM notes_jobs').fetchone()
            self.assertEqual(unprotect(topic),b'synthetic topic');self.assertEqual(unprotect(result),b'synthetic result')

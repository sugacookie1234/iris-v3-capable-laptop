"""One bounded notes worker; encrypted payloads and explicit restart recovery.

Only this fixed read-only recipe can run. Stored data cannot name handlers,
change permissions, or silently replay a job after the application restarts.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from uuid import uuid4

from iris.desktop.secrets import protect, unprotect
from iris.generalist.notes_briefing import NotesBriefing
from iris.memory.redaction import contains_secret

ACTIVE = frozenset({'queued', 'running', 'cancelling'})
TERMINAL = frozenset({'interrupted', 'completed', 'partial', 'no_matches', 'failed', 'cancelled'})
RESULT_STATES = frozenset({'completed', 'partial', 'no_matches'})
STEPS = ('search', 'read_1', 'read_2', 'read_3', 'draft')
MAX_PENDING = 4
MAX_ATTEMPTS = 3
MAX_RECORDS = 100
RETENTION_DAYS = 7
MAX_RESULT_BYTES = 65536
_MESSAGES = {
    'queued': 'Waiting to start.', 'running': 'Working on your notes briefing.',
    'cancelling': 'Stopping the notes briefing.', 'interrupted': 'Interrupted when IRIS stopped. Resume starts a fresh read.',
    'completed': 'Briefing ready.', 'partial': 'Briefing ready with limited source coverage.',
    'no_matches': 'No matching notes found.', 'failed': 'The briefing could not be completed.',
    'cancelled': 'Briefing cancelled.',
}


class JobError(ValueError):
    """Only fixed, safe text is exposed to the local UI."""


def _steps(value):
    if (type(value) is not list or len(value) > 5 or any(type(item) is not str or item not in STEPS for item in value)
            or len(value) != len(set(value))):
        raise JobError('Invalid job progress.')
    return value


class NotesJobs:
    """Single-host owner. The desktop's per-checkout mutex prevents two owners."""

    def __init__(self, path, vault_path, history=None, runner_factory=None, *, codec=None, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise JobError('Job storage cannot use symbolic links.')
        self.vault_path = str(Path(vault_path).absolute()) if vault_path else None
        normalized = os.path.normcase(self.vault_path) if self.vault_path else ''
        self._vault = hashlib.sha256(normalized.encode('utf-8')).hexdigest() if normalized else ''
        self.history = history
        self.observer_failed = False
        self._factory = runner_factory or NotesBriefing
        self._seal, self._open = codec or (protect, unprotect)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._thread = None
        self._closed = False
        self._storage_failed = False
        self._active_id = None
        self._cancel = threading.Event()
        try:
            with self._db() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS notes_jobs (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE, vault TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL, steps TEXT NOT NULL,
                    attempts INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    revision INTEGER NOT NULL, topic BLOB NOT NULL, result BLOB, error_code TEXT)''')
                db.execute("UPDATE notes_jobs SET status='interrupted', stage='interrupted', updated_at=?, "
                           "revision=revision+1, result=NULL, error_code='restart' "
                           "WHERE status IN ('queued','running','cancelling')", (self._now(),))
                self._prune(db)
        except sqlite3.Error:
            raise JobError('Job storage is unavailable.') from None

    def _now(self):
        return self._clock().astimezone(timezone.utc).isoformat(timespec='milliseconds')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA secure_delete=ON')
            with db:
                yield db
        finally:
            db.close()

    def _prune(self, db):
        cutoff = (self._clock() - timedelta(days=RETENTION_DAYS)).astimezone(timezone.utc).isoformat(timespec='milliseconds')
        db.execute("DELETE FROM notes_jobs WHERE status NOT IN ('queued','running','cancelling') AND updated_at<?", (cutoff,))
        excess = db.execute('SELECT MAX(COUNT(*)-?,0) FROM notes_jobs', (MAX_RECORDS,)).fetchone()[0]
        if excess:
            db.execute("DELETE FROM notes_jobs WHERE id IN (SELECT id FROM notes_jobs "
                       "WHERE status NOT IN ('queued','running','cancelling') ORDER BY updated_at,rowid LIMIT ?)", (excess,))

    def _encode(self, value):
        try:
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(raw) > MAX_RESULT_BYTES:
                raise ValueError
            encoded = self._seal(raw)
            if not isinstance(encoded, bytes) or not encoded:
                raise ValueError
            return encoded
        except Exception:
            raise JobError('Job details could not be protected for this Windows account.') from None

    def _decode(self, blob):
        try:
            if len(blob) > MAX_RESULT_BYTES + 4096:
                raise ValueError
            return json.loads(self._open(bytes(blob)).decode('utf-8'))
        except Exception:
            raise JobError('Stored job details cannot be unlocked for this Windows account.') from None

    @staticmethod
    def _topic(value):
        if type(value) is not str or not value.strip() or len(value) > 200 or contains_secret(value):
            raise JobError('Give a notes topic of 1 to 200 characters without credentials.')
        return value.strip()

    @staticmethod
    def _id(value):
        if type(value) is not str or not re.fullmatch('[a-f0-9]{32}', value):
            raise JobError('Choose an existing job.')
        return value

    def _ready(self, *, vault=False):
        if self._closed:
            raise JobError('IRIS is closing. Reopen it to manage jobs.')
        if self._storage_failed:
            raise JobError('Job storage failed. Reopen IRIS before starting or resuming work.')
        if vault and not self.vault_path:
            raise JobError('Configure an Obsidian vault in setup.bat before starting this job.')

    def _row(self, db, identifier):
        row = db.execute('SELECT * FROM notes_jobs WHERE id=?', (self._id(identifier),)).fetchone()
        if row is None:
            raise JobError('That job is no longer available.')
        return row

    def _public(self, row, detail=False):
        topic = self._decode(row['topic'])
        if type(topic) is not str or not topic or len(topic) > 200:
            raise JobError('Stored job details are invalid.')
        status = row['status']
        available = status in RESULT_STATES and row['result'] is not None
        result = {'id': row['id'], 'kind': 'notes_briefing', 'topic': topic, 'status': status,
                  'stage': row['stage'], 'completed_steps': _steps(json.loads(row['steps'])),
                  'created_at': row['created_at'], 'updated_at': row['updated_at'], 'revision': row['revision'],
                  'attempts': row['attempts'], 'result_available': available, 'message': _MESSAGES[status],
                  'error_code': row['error_code'], 'can_cancel': status in {'queued', 'running'},
                  'can_resume': status in {'interrupted', 'failed'} and row['attempts'] < MAX_ATTEMPTS
                                and bool(self._vault) and row['vault'] == self._vault}
        if detail and available:
            result['result'] = self._decode(row['result'])
        return result

    def _listed(self, row):
        """Keep other jobs and terminal deletion usable when one payload is unreadable."""
        try:
            return self._public(row)
        except JobError:
            status = row['status']
            return {'id': row['id'], 'kind': 'notes_briefing', 'topic': 'Unavailable encrypted topic',
                    'status': status, 'stage': status, 'completed_steps': [],
                    'created_at': row['created_at'], 'updated_at': row['updated_at'], 'revision': row['revision'],
                    'attempts': row['attempts'], 'result_available': False, 'details_unavailable': True,
                    'message': 'Saved job details are unavailable. You can delete this job once it has stopped.',
                    'error_code': 'unavailable_details', 'can_cancel': status in {'queued', 'running'},
                    'can_resume': False}

    def _start(self):
        # Caller holds the same lock used by the worker's queue claim.
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, name='iris-notes-jobs', daemon=True)
            self._thread.start()
        self._condition.notify_all()

    def submit(self, topic, request_id=None):
        topic = self._topic(topic)
        if request_id is not None and (type(request_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{8,128}', request_id)):
            raise JobError('Invalid job request identifier.')
        request_key = hashlib.sha256(request_id.encode()).hexdigest() if request_id is not None else None
        with self._condition:
            self._ready(vault=True)
            try:
                with self._db() as db:
                    self._prune(db)
                    if request_key:
                        prior = db.execute('SELECT * FROM notes_jobs WHERE request_key=?', (request_key,)).fetchone()
                        if prior is not None:
                            if self._decode(prior['topic']) != topic or prior['vault'] != self._vault:
                                raise JobError('This request identifier was already used for a different job.')
                            return self._public(prior)
                    else:
                        for prior in db.execute("SELECT * FROM notes_jobs WHERE vault=? AND status IN ('queued','running','cancelling')", (self._vault,)):
                            if self._decode(prior['topic']).casefold() == topic.casefold():
                                return self._public(prior)
                    count = db.execute("SELECT COUNT(*) FROM notes_jobs WHERE status='queued'").fetchone()[0]
                    if count >= MAX_PENDING:
                        raise JobError('The job queue is full. Wait for a job to finish or cancel one.')
                    identifier, now = uuid4().hex, self._now()
                    db.execute('INSERT INTO notes_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (identifier, request_key, self._vault, 'queued', 'queued', '[]', 1, now, now, 1,
                         self._encode(topic), None, None))
                    self._prune(db)
                    public = self._public(self._row(db, identifier))
                self._start()
                return public
            except sqlite3.Error:
                raise JobError('The job could not be saved. No new work was started.') from None

    def list(self):
        with self._lock:
            self._ready()
            try:
                with self._db() as db:
                    self._prune(db)
                    return [self._listed(row) for row in db.execute('SELECT * FROM notes_jobs ORDER BY created_at DESC,rowid DESC')]
            except sqlite3.Error:
                raise JobError('Job storage is unavailable.') from None

    def detail(self, identifier):
        with self._lock:
            self._ready()
            try:
                with self._db() as db:
                    self._prune(db)
                    return self._public(self._row(db, identifier), detail=True)
            except sqlite3.Error:
                raise JobError('Job storage is unavailable.') from None

    def cancel(self, identifier):
        with self._condition:
            self._ready()
            if identifier == self._active_id:
                self._cancel.set()  # Stop even if persisting the cancellation fails.
            try:
                with self._db() as db:
                    row = self._row(db, identifier)
                    if row['status'] in ACTIVE:
                        status = 'cancelled' if row['status'] == 'queued' else 'cancelling'
                        db.execute('UPDATE notes_jobs SET status=?,stage=?,updated_at=?,revision=revision+1,result=NULL WHERE id=?',
                                   (status, status, self._now(), identifier))
                    public = self._listed(self._row(db, identifier))
                self._condition.notify_all()
                return public
            except sqlite3.Error:
                self._storage_failed = True
                raise JobError('Cancellation was requested, but its record could not be saved. Reopen IRIS.') from None

    def resume(self, identifier):
        with self._condition:
            self._ready(vault=True)
            try:
                with self._db() as db:
                    row = self._row(db, identifier)
                    if row['status'] not in {'interrupted', 'failed'} or row['attempts'] >= MAX_ATTEMPTS:
                        raise JobError('This job cannot be resumed. Start a new briefing if needed.')
                    if row['vault'] != self._vault:
                        raise JobError('The configured vault changed. Start a new briefing for this vault.')
                    self._topic(self._decode(row['topic']))
                    if db.execute("SELECT COUNT(*) FROM notes_jobs WHERE status='queued'").fetchone()[0] >= MAX_PENDING:
                        raise JobError('The job queue is full. Wait or cancel a queued job.')
                    db.execute("UPDATE notes_jobs SET status='queued',stage='queued',steps='[]',attempts=attempts+1,"
                               "updated_at=?,revision=revision+1,result=NULL,error_code=NULL WHERE id=?", (self._now(), identifier))
                    public = self._public(self._row(db, identifier))
                self._start()
                return public
            except sqlite3.Error:
                raise JobError('The resumed job could not be saved. No new work was started.') from None

    def delete(self, identifier):
        with self._lock:
            self._ready()
            try:
                with self._db() as db:
                    if self._row(db, identifier)['status'] not in TERMINAL:
                        raise JobError('Cancel this job before deleting it.')
                    db.execute('DELETE FROM notes_jobs WHERE id=?', (identifier,))
                return {'deleted': True, 'id': identifier}
            except sqlite3.Error:
                raise JobError('The job could not be deleted.') from None

    def _progress(self, identifier, attempt, value):
        if type(value) is not dict or set(value) != {'stage', 'completed_steps'}:
            raise JobError('Invalid job progress.')
        stage, steps = value['stage'], _steps(value['completed_steps'])
        if stage not in (*STEPS, 'done'):
            raise JobError('Invalid job stage.')
        with self._lock:
            if self._closed or self._cancel.is_set() or identifier != self._active_id:
                return
            with self._db() as db:
                db.execute("UPDATE notes_jobs SET stage=?,steps=?,updated_at=?,revision=revision+1 "
                           "WHERE id=? AND attempts=? AND status='running'",
                           (stage, json.dumps(steps), self._now(), identifier, attempt))

    @staticmethod
    def _outcome(result):
        if (type(result) is not dict or result.get('route') != 'LOCAL' or type(result.get('reply')) is not str
                or len(result['reply']) > 20000 or type(result.get('spoken_reply')) is not str
                or len(result['spoken_reply']) > 1000 or type(result.get('briefing')) is not dict):
            raise JobError('Invalid job result.')
        report = result['briefing']
        status = {'complete': 'completed', 'partial': 'partial', 'no_matches': 'no_matches',
                  'failed': 'failed', 'timeout': 'failed', 'cancelled': 'cancelled'}.get(report.get('status'))
        if status is None or report.get('model_calls') != 0:
            raise JobError('Invalid job result.')
        steps = _steps(report.get('completed_steps'))
        return status, steps, 'time_limit' if report['status'] == 'timeout' else None

    def _work(self):
        while True:
            identifier = None
            try:
                with self._condition:
                    if self._closed or self._storage_failed:
                        return
                    with self._db() as db:
                        row = db.execute("SELECT * FROM notes_jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
                        if row is None:
                            self._thread = None  # A concurrent submit must start a new worker even before this thread exits.
                            return  # Do not retain an idle worker/thread.
                        identifier, attempt = row['id'], row['attempts']
                        self._active_id = identifier
                        self._cancel = threading.Event()
                        db.execute("UPDATE notes_jobs SET status='running',stage='search',updated_at=?,revision=revision+1 WHERE id=?",
                                   (self._now(), identifier))
                    # Claim durably before decoding; an unreadable payload must fail once, never loop in the queue.
                    topic = self._topic(self._decode(row['topic']))
                    if row['vault'] != self._vault or not self.vault_path:
                        raise JobError('The configured vault changed.')
                runner = self._factory(self.vault_path, history=self.history)
                try:
                    result = runner.run(topic, cancelled=self._cancel.is_set,
                                        progress=lambda value, job_id=identifier, generation=attempt:
                                            self._progress(job_id, generation, value))
                finally:
                    with self._lock:
                        self.observer_failed = self.observer_failed or bool(
                            getattr(getattr(runner, 'executor', None), 'observer_failed', False))
                status, steps, error = self._outcome(result)
                payload = self._encode(result) if status in RESULT_STATES else None
                with self._lock:
                    if self._closed:
                        return
                    with self._db() as db:
                        row = self._row(db, identifier)
                        if row['status'] == 'cancelling' or self._cancel.is_set():
                            status, payload, error = 'cancelled', None, None
                        db.execute('UPDATE notes_jobs SET status=?,stage=?,steps=?,updated_at=?,revision=revision+1,result=?,error_code=? '
                                   'WHERE id=? AND attempts=? AND status IN (\'running\',\'cancelling\')',
                                   (status, 'done' if status in RESULT_STATES else status, json.dumps(steps), self._now(),
                                    payload, error, identifier, attempt))
                        self._prune(db)
                    self._active_id = None
            except Exception:
                with self._lock:
                    if self._closed:
                        return
                    if identifier is not None:
                        try:
                            with self._db() as db:
                                row = self._row(db, identifier)
                                state = 'cancelled' if self._cancel.is_set() or row['status'] == 'cancelling' else 'failed'
                                db.execute('UPDATE notes_jobs SET status=?,stage=?,updated_at=?,revision=revision+1,result=NULL,'
                                           "error_code='worker_failure' WHERE id=? AND attempts=? AND status IN ('running','cancelling')",
                                           (state, state, self._now(), identifier, attempt))
                        except Exception:
                            self._storage_failed = True
                    else:
                        self._storage_failed = True
                    self._active_id = None
                    if self._storage_failed:
                        return

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            requested_cancel_id = self._active_id if self._cancel.is_set() else None
            self._cancel.set()
            try:
                with self._db() as db:
                    db.execute("UPDATE notes_jobs SET status=CASE WHEN status='cancelling' OR id=? THEN 'cancelled' ELSE 'interrupted' END, "
                               "stage=CASE WHEN status='cancelling' OR id=? THEN 'cancelled' ELSE 'interrupted' END, updated_at=?,"
                               "revision=revision+1,result=NULL,error_code='shutdown' WHERE status IN ('queued','running','cancelling')",
                               (requested_cancel_id, requested_cancel_id, self._now()))
            except sqlite3.Error:
                self._storage_failed = True  # Reopen recovers durable active records.
            thread = self._thread
            self._condition.notify_all()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)

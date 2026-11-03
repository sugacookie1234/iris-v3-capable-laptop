"""Reviewed, metadata-only observations of the fixed local notes recipe.

These additive tables share MemoryStore's database, but never enter personal
memory retrieval or exports. Evidence is immutable; review changes only its
state. Nothing here invokes a model or turns saved text into instructions.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import threading
from uuid import uuid4

from iris.memory.store import MemoryStore


SCHEMA_VERSION = 1
MAX_RECORDS = 100
MAX_MARKERS = 1000
SOURCE_RETENTION = timedelta(days=7)
REVIEWED_RETENTION = timedelta(days=30)
_VERSION_KEY = 'experiences_version'
_CUTOFF_KEY = 'experiences_capture_cutoff'
_EVENT_FIELDS = frozenset({
    'schema_version', 'recipe', 'job_id', 'attempt', 'scope', 'completed_at',
    'outcome', 'completed_steps', 'source_count', 'verification', 'model_calls',
})
_PUBLIC_FIELDS = (
    'id', 'revision', 'state', 'summary', 'lesson', 'job_id', 'attempt',
    'completed_at', 'expires_at', 'outcome', 'source_count', 'verification', 'scope',
)
_VERIFICATION = 'source_revision_and_excerpt_match'
_SUCCESS_GUIDANCE = (
    'Reviewed local notes procedure: search, read selected notes, then recheck '
    'source revisions and exact excerpts before presenting the briefing. '
    'This does not independently fact-check note claims.'
)
_PARTIAL_GUIDANCE = (
    'Reviewed coverage caution: a bounded search can produce only a partial '
    'briefing; disclose limited coverage and narrow the topic for other results.'
)


def _timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _event(value):
    """Validate the complete host metadata contract without retaining payloads."""
    if type(value) is not dict or set(value) != _EVENT_FIELDS:
        raise ValueError('Invalid experience source metadata.')
    if (type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['recipe']) is not str or value['recipe'] != 'notes_briefing_v1'
            or not _hex(value['job_id'], 32) or not _hex(value['scope'], 64)
            or type(value['attempt']) is not int or not 1 <= value['attempt'] <= 3
            or type(value['source_count']) is not int or not 1 <= value['source_count'] <= 3
            or type(value['outcome']) is not str or value['outcome'] not in ('completed', 'partial')
            or type(value['verification']) is not str or value['verification'] != _VERIFICATION
            or type(value['model_calls']) is not int or value['model_calls'] != 0):
        raise ValueError('Invalid experience source metadata.')
    steps = ['search', *[f'read_{index}' for index in range(1, value['source_count'] + 1)], 'draft']
    if type(value['completed_steps']) is not list or value['completed_steps'] != steps:
        raise ValueError('Invalid experience source metadata.')
    completed_at = value['completed_at']
    if (type(completed_at) is not str or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', completed_at)):
        raise ValueError('Invalid experience source metadata.')
    try:
        completed = datetime.fromisoformat(completed_at.replace('Z', '+00:00')).astimezone(timezone.utc)
        completed + REVIEWED_RETENTION
    except (ValueError, OverflowError):
        raise ValueError('Invalid experience source metadata.') from None
    normalized = {**value, 'completed_at': _timestamp(completed), 'completed_steps': steps}
    evidence = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    source = hashlib.sha256(f"notes_briefing_v1:{value['job_id']}:{value['attempt']}".encode()).hexdigest()
    return normalized, completed, evidence, source


def _description(event):
    count = event['source_count']
    sources = f'{count} source' + ('s' if count != 1 else '')
    if event['outcome'] == 'partial':
        summary = f'Partial local notes briefing using {sources}; coverage was limited. '
        lesson = 'Disclose limited coverage and narrow the topic when other matching notes are needed.'
    else:
        summary = f'Completed a local notes briefing using {sources}. '
        lesson = 'Recheck selected source revisions and exact excerpts before presenting a local notes briefing.'
    summary += 'Source revisions and excerpts matched; note claims were not independently fact-checked.'
    return summary, lesson


class Experiences:
    """A bounded review queue; every operation uses its own SQLite connection.

    ``clock`` is an optional callable returning an aware datetime. Old unseen
    evidence is accepted only during its source job's seven-day lifetime. At
    unusually high deletion/eviction volume, a conservative completion cutoff
    bounds one-way deletion markers without allowing old evidence to reappear.
    """

    def __init__(self, path, clock=None):
        self.path = path
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        with self._database() as connection:
            self._prune(connection, self._now())

    def _now(self):
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Experience clock must return a timezone-aware datetime.')
        return value.astimezone(timezone.utc)

    @contextmanager
    def _database(self):
        with self._lock, MemoryStore(self.path) as memory:
            connection = memory._connection
            connection.execute('PRAGMA secure_delete = ON')
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._schema(connection)
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _schema(connection):
        row = connection.execute('SELECT value FROM schema_meta WHERE key = ?', (_VERSION_KEY,)).fetchone()
        if row is not None and row['value'] != str(SCHEMA_VERSION):
            raise RuntimeError('Unsupported experience database schema version.')
        connection.execute('''CREATE TABLE IF NOT EXISTS experiences (
            id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL,
            summary TEXT NOT NULL, lesson TEXT NOT NULL, job_id TEXT NOT NULL,
            attempt INTEGER NOT NULL, completed_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            outcome TEXT NOT NULL, source_count INTEGER NOT NULL, verification TEXT NOT NULL,
            scope TEXT NOT NULL, source_fingerprint TEXT NOT NULL UNIQUE,
            evidence_fingerprint TEXT NOT NULL
        )''')
        connection.execute('''CREATE TABLE IF NOT EXISTS experience_source_markers (
            source_fingerprint TEXT PRIMARY KEY, expires_at TEXT NOT NULL
        )''')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_experiences_expiry ON experiences(expires_at)')
        connection.execute('INSERT OR IGNORE INTO schema_meta(key, value) VALUES (?, ?)',
                           (_VERSION_KEY, str(SCHEMA_VERSION)))

    @staticmethod
    def _public(row):
        return {field: row[field] for field in _PUBLIC_FIELDS}

    @staticmethod
    def _mark(connection, row, now):
        expires = _timestamp(datetime.fromisoformat(row['completed_at']) + SOURCE_RETENTION)
        if expires > _timestamp(now):
            connection.execute('INSERT OR IGNORE INTO experience_source_markers VALUES (?, ?)',
                               (row['source_fingerprint'], expires))

    def _prune(self, connection, now):
        stamp = _timestamp(now)
        connection.execute('DELETE FROM experiences WHERE expires_at <= ?', (stamp,))
        connection.execute('DELETE FROM experience_source_markers WHERE expires_at <= ?', (stamp,))
        excess = connection.execute(
            'SELECT * FROM experiences ORDER BY completed_at DESC, rowid DESC LIMIT -1 OFFSET ?',
            (MAX_RECORDS,),
        ).fetchall()
        for row in excess:
            self._mark(connection, row, now)
            connection.execute('DELETE FROM experiences WHERE id = ?', (row['id'],))
        # Removing only old markers would let their source jobs be reconciled
        # again. Keep a monotonic lower bound for accepting unseen completions.
        overflow = connection.execute('''SELECT expires_at FROM experience_source_markers
            ORDER BY expires_at DESC, source_fingerprint DESC LIMIT -1 OFFSET ?''', (MAX_MARKERS,)).fetchall()
        if overflow:
            cutoff = _timestamp(datetime.fromisoformat(overflow[0]['expires_at']) - SOURCE_RETENTION)
            previous = connection.execute('SELECT value FROM schema_meta WHERE key = ?', (_CUTOFF_KEY,)).fetchone()
            if previous is not None:
                cutoff = max(cutoff, previous['value'])
            connection.execute('INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)', (_CUTOFF_KEY, cutoff))
            expiry = _timestamp(datetime.fromisoformat(cutoff) + SOURCE_RETENTION)
            connection.execute('DELETE FROM experience_source_markers WHERE expires_at <= ?', (expiry,))
        previous = connection.execute('SELECT value FROM schema_meta WHERE key = ?', (_CUTOFF_KEY,)).fetchone()
        if previous is not None and datetime.fromisoformat(previous['value']) + SOURCE_RETENTION <= now:
            connection.execute('DELETE FROM schema_meta WHERE key = ?', (_CUTOFF_KEY,))

    def capture(self, event):
        event, completed, evidence, source = _event(event)
        with self._database() as connection:
            now = self._now()
            if completed > now:
                raise ValueError('Experience source completion cannot be in the future.')
            self._prune(connection, now)
            existing = connection.execute('SELECT * FROM experiences WHERE source_fingerprint = ?', (source,)).fetchone()
            if existing is not None:
                if existing['evidence_fingerprint'] != evidence:
                    raise ValueError('Experience source metadata conflicts with saved evidence.')
                return self._public(existing)
            if completed + SOURCE_RETENTION <= now:
                return None
            if connection.execute('SELECT 1 FROM experience_source_markers WHERE source_fingerprint = ?', (source,)).fetchone():
                return None
            cutoff = connection.execute('SELECT value FROM schema_meta WHERE key = ?', (_CUTOFF_KEY,)).fetchone()
            if cutoff is not None and event['completed_at'] <= cutoff['value']:
                return None
            identifier = uuid4().hex
            summary, lesson = _description(event)
            connection.execute('''INSERT INTO experiences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                identifier, 1, 'pending', summary, lesson, event['job_id'], event['attempt'], event['completed_at'],
                _timestamp(completed + SOURCE_RETENTION), event['outcome'], event['source_count'], event['verification'],
                event['scope'], source, evidence,
            ))
            self._prune(connection, now)
            row = connection.execute('SELECT * FROM experiences WHERE id = ?', (identifier,)).fetchone()
            return self._public(row) if row is not None else None

    def list(self):
        with self._database() as connection:
            self._prune(connection, self._now())
            return [self._public(row) for row in connection.execute(
                'SELECT * FROM experiences ORDER BY completed_at DESC, rowid DESC')]

    @staticmethod
    def _reviewed_row(connection, identifier, revision):
        if not _hex(identifier, 32) or type(revision) is not int or revision < 1:
            raise ValueError('Invalid experience review request.')
        row = connection.execute('SELECT * FROM experiences WHERE id = ?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Experience is unavailable or expired.')
        if row['revision'] != revision:
            raise ValueError('Experience changed; refresh before reviewing it.')
        return row

    def review(self, identifier, revision, decision):
        if type(decision) is not str or decision not in ('keep', 'dismiss', 'dispute'):
            raise ValueError('Invalid experience review decision.')
        with self._database() as connection:
            self._prune(connection, self._now())
            row = self._reviewed_row(connection, identifier, revision)
            state = {'keep': 'kept', 'dismiss': 'dismissed', 'dispute': 'disputed'}[decision]
            expires = _timestamp(datetime.fromisoformat(row['completed_at']) + REVIEWED_RETENTION)
            connection.execute('UPDATE experiences SET state = ?, revision = revision + 1, expires_at = ? WHERE id = ?',
                               (state, expires, identifier))
            return self._public(connection.execute('SELECT * FROM experiences WHERE id = ?', (identifier,)).fetchone())

    def forget(self, identifier, revision):
        with self._database() as connection:
            now = self._now()
            self._prune(connection, now)
            row = self._reviewed_row(connection, identifier, revision)
            self._mark(connection, row, now)
            connection.execute('DELETE FROM experiences WHERE id = ?', (identifier,))
            self._prune(connection, now)

    def guidance(self, scope):
        if not _hex(scope, 64):
            raise ValueError('Invalid experience scope.')
        with self._database() as connection:
            self._prune(connection, self._now())
            outcomes = {row['outcome'] for row in connection.execute(
                "SELECT outcome FROM experiences WHERE state = 'kept' AND scope = ?", (scope,))}
            return ' '.join(text for outcome, text in (
                ('completed', _SUCCESS_GUIDANCE), ('partial', _PARTIAL_GUIDANCE),
            ) if outcome in outcomes)

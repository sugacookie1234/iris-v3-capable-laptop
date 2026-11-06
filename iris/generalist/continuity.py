"""Private, owner-selected continuity. Stored evidence never restores authority."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from iris.desktop.secrets import protect, unprotect
from iris.memory.redaction import contains_secret


class ContinuityError(ValueError):
    pass


def _text(value, limit, empty=False):
    if (type(value) is not str or len(value) > limit or (not empty and not value.strip())
            or contains_secret(value) or any(ord(c) < 32 for c in value)):
        raise ContinuityError('Use bounded plain text without credentials or control characters.')
    return value.strip()


def _id(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{32}', value):
        raise ContinuityError('Select a full project identifier.')
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


class ProjectContinuity:
    """Ten encrypted project envelopes; no source contents or reusable approvals.

    Lazy runtime creation avoids touching stores unless the owner uses /project.
    SQLite transactions serialize mutations; callers supply current revisions.
    Windows account-bound DPAPI is mandatory outside synthetic codec tests.
    """
    def __init__(self, path, *, codec=None):
        self.path = Path(path).absolute()
        self._seal, self._open = codec or (protect, unprotect)
        self._paths()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ContinuityError('Unsupported project store version.')
            db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
            if version == 0:
                db.execute('PRAGMA user_version=1')

    def _paths(self):
        for path in (self.path, *self.path.parents):
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ContinuityError('Project storage cannot use redirected paths.')
        for suffix in ('-journal', '-wal', '-shm'):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.is_symlink() or (hasattr(sidecar, 'is_junction') and sidecar.is_junction()):
                raise ContinuityError('Project storage cannot use redirected paths.')

    @contextmanager
    def _db(self):
        self._paths()
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except sqlite3.Error:
            raise ContinuityError('Project storage is unavailable; nothing may resume.') from None
        finally:
            db.close()

    def _decode(self, identifier, payload):
        return self.decode_envelope(identifier, payload, self._open)

    @staticmethod
    def decode_envelope(identifier, payload, opener):
        """Validate a protected or portable envelope without opening a live store."""
        try:
            if type(payload) is not bytes or len(payload) > 70000:
                raise ValueError
            raw = opener(payload)
            if type(raw) is not bytes or len(raw) > 64000:
                raise ValueError
            value = json.loads(raw, object_pairs_hook=unique_pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite value.')))
            if (type(value) is not dict or set(value) != {'version','id','title','description',
                    'created','updated','revision','privacy','export','resources','workflows'}
                    or type(value['version']) is not int or value['version'] != 1
                    or value['id'] != identifier or value['privacy'] != 'private' or value['export'] != 'none'
                    or type(value['revision']) is not int or value['revision'] < 1):
                raise ValueError
            _id(value['id']); _text(value['title'], 80); _text(value['description'], 400, True)
            for field in ('created','updated'):
                if datetime.fromisoformat(value[field]).tzinfo is None:
                    raise ValueError
            if type(value['resources']) is not list or len(value['resources']) > 5:
                raise ValueError
            for ref in value['resources']:
                from iris.tasks.models import task_id
                if (set(ref) != {'kind','id','revision'} or ref['kind'] != 'task'
                        or type(ref['revision']) is not int or ref['revision'] < 1):
                    raise ValueError
                task_id(ref['id'])
            if type(value['workflows']) is not list or len(value['workflows']) > 10:
                raise ValueError
            for workflow in value['workflows']:
                _validate_workflow(workflow)
            if (len({r['id'] for r in value['resources']}) != len(value['resources'])
                    or len({w['id'] for w in value['workflows']}) != len(value['workflows'])):
                raise ValueError
            return value
        except Exception:
            raise ContinuityError('Project evidence cannot be unlocked or validated. No recovery action is permitted.') from None

    def _write(self, db, value):
        try:
            raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
            if len(raw) > 64000:
                raise ValueError
            payload = self._seal(raw)
            if type(payload) is not bytes or not payload or self._decode(value['id'], payload) != value:
                raise ValueError
        except Exception:
            raise ContinuityError('Project evidence could not be protected and verified.') from None
        db.execute('INSERT OR REPLACE INTO projects VALUES (?,?)', (value['id'], payload))

    def _get(self, db, identifier, revision=None):
        row = db.execute('SELECT payload FROM projects WHERE id=?', (_id(identifier),)).fetchone()
        if row is None:
            raise ContinuityError('Project is unavailable. Select an existing identifier.')
        value = self._decode(identifier, row[0])
        if revision is not None and (type(revision) is not int or value['revision'] != revision):
            raise ContinuityError('Project revision changed. Inspect and select it again.')
        return value

    def create(self, title, description=''):
        title, description = _text(title, 80), _text(description, 400, True)
        with self._db() as db:
            rows = db.execute('SELECT id,payload FROM projects').fetchall()
            if len(rows) >= 10:
                raise ContinuityError('Ten projects are retained. Explicitly delete one first.')
            if any(self._decode(i, p)['title'].casefold() == title.casefold() for i, p in rows):
                raise ContinuityError('That title already exists. Select its identifier.')
            value = dict(version=1, id=uuid4().hex, title=title, description=description,
                         created=_now(), updated=_now(), revision=1, privacy='private', export='none',
                         resources=[], workflows=[])
            self._write(db, value)
            return value

    def get(self, identifier, revision=None):
        with self._db() as db:
            return self._get(db, identifier, revision)

    def list(self):
        with self._db() as db:
            return [self._decode(i, p) for i, p in db.execute('SELECT id,payload FROM projects LIMIT 11')]

    def delete(self, identifier, revision):
        with self._db() as db:
            # Unreadable evidence cannot supply a validated deletion revision.
            # Retain it for owner recovery rather than silently overwriting it.
            self._get(db, identifier, revision)
            db.execute('DELETE FROM projects WHERE id=?', (identifier,))

    def link_task(self, identifier, revision, task):
        from iris.tasks.models import Task, TaskStatus
        if not isinstance(task, Task) or task.status == TaskStatus.DELETED:
            raise ContinuityError('Select an available task from the existing task store.')
        with self._db() as db:
            value = self._get(db, identifier, revision)
            refs = [r for r in value['resources'] if r['id'] != task.id]
            if len(refs) >= 5:
                raise ContinuityError('At most five task references can be retained.')
            value['resources'] = refs + [dict(kind='task', id=task.id, revision=task.revision)]
            self._update(db, value)
            return value

    def _update(self, db, value):
        value['revision'] += 1
        value['updated'] = _now()
        self._write(db, value)

    def journal(self, identifier, revision, record):
        _validate_workflow(record)
        with self._db() as db:
            value = self._get(db, identifier, revision)
            workflows = [w for w in value['workflows'] if w['id'] != record['id']]
            value['workflows'] = (workflows + [record])[-10:]
            self._update(db, value)
            return value

    def summary(self, identifier, history):
        value = self.get(identifier)
        evidence = {row['id']: row for row in history.rows()}
        lines = [f"{value['title']} — {value['id']}, revision {value['revision']}."]
        for workflow in value['workflows']:
            lines.append(f"Workflow {workflow['id']}: historical {workflow['state']}.")
            for step in workflow['steps']:
                row = evidence.get(step['evidence'])
                supported = (step['state'] == 'completed' and step['verification'] == 'validated_returned_data'
                             and row and row['tool'] == step['capability'] and row['outcome'] == 'returned'
                             and row['approval'] == 'approved' and row['origin'] == 'model')
                status = ('previously verified returned data (not current file state)' if supported else
                          'pending; not executed' if step['state'] == 'pending' else
                          'not executed; fresh confirmation required' if step['verification'] == 'not_executed' else
                          'interrupted or unverified; outcome unknown')
                lines.append(f"{step['id']}: {status}.")
        lines.append('Nothing has been resumed. Historical approvals are not authority. '
                     'Use /plan workspace <new request> for a fresh preview and new approvals. '
                     'Project correctness and current file contents have not been verified.')
        return '\n'.join(lines)


STATES = {'awaiting_confirmation','running','awaiting_approval','verifying','completed',
          'failed','cancelled','uncertain'}


def _validate_workflow(value):
    if (type(value) is not dict or set(value) != {'id','revision','state','updated','steps'}
            or type(value['revision']) is not int or value['revision'] < 1 or value['state'] not in STATES):
        raise ContinuityError('Invalid workflow evidence.')
    _id(value['id'])
    if datetime.fromisoformat(value['updated']).tzinfo is None:
        raise ContinuityError('Invalid evidence timestamp.')
    steps = value['steps']
    if type(steps) is not list or not 1 <= len(steps) <= 3:
        raise ContinuityError('Invalid step count.')
    seen = set()
    for step in steps:
        if (type(step) is not dict or set(step) != {'id','capability','digest','dependencies','state','verification','evidence'}
                or type(step['id']) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,63}', step['id'])
                or step['id'] in seen or step['capability'] not in {'workspace_list','workspace_read'}
                or type(step['digest']) is not str or not re.fullmatch('[a-f0-9]{64}', step['digest'])
                or type(step['dependencies']) is not list or not set(step['dependencies']) <= seen
                or step['state'] not in STATES | {'pending'}
                or step['verification'] not in {'not_executed','unknown','unverified','validated_returned_data'}):
            raise ContinuityError('Invalid step evidence.')
        if step['evidence'] is not None:
            from iris.tasks.models import task_id
            task_id(step['evidence'])
        seen.add(step['id'])


class ProjectJournal:
    """In-process observer only. There is deliberately no deserializer for PlanRun."""
    def __init__(self, store, identifier, revision, check_resources, on_update=None):
        self.store, self.identifier, self.revision = store, identifier, revision
        self.check_resources = check_resources
        self.on_update = on_update

    def validate(self):
        value = self.store.get(self.identifier, self.revision)
        self.check_resources(value)

    def __call__(self, run):
        from iris.generalist.controlled_plan import digest
        receipts = {r.step_id: r for r in run.receipts}
        steps = []
        for node, prepared in zip(run.plan.plan.nodes, run.plan.prepared):
            receipt = receipts.get(node.id)
            active = node.id == getattr(run, 'active_step', None)
            steps.append(dict(id=node.id, capability=node.tool,
                digest=digest({'capability': node.tool, 'arguments': dict(prepared.arguments)}),
                dependencies=list(node.depends_on), state=receipt.status if receipt else run.state if active else 'pending',
                verification=receipt.verification if receipt else 'unknown' if active else 'not_executed',
                evidence=receipt.evidence_ref if receipt else None))
        value = self.store.journal(self.identifier, self.revision,
            dict(id=run.plan.id, revision=run.plan.revision, state=run.state, updated=_now(), steps=steps))
        self.revision = value['revision']
        if self.on_update is not None:
            self.on_update(self.identifier, self.revision)

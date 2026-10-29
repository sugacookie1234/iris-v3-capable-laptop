"""Bounded local execution receipts. Never store arguments, content or errors' text.

The desktop owns one store. Interrupted receipts are unknown, never retried.
This is an observation layer, not a source of permissions or personal memory.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from iris.tools.models import FailureCode, RequestOrigin, ResultStatus

LOCAL_READS = {'desktop_daily_briefing', 'desktop_find_files'}
COVERAGE = ('Records cover desktop controls, filename searches, briefings and registered '
            'chat tools since this update. Automatic organization has its own Activity history. '
            'Phone, speech, web requests and ordinary chat are not recorded here.')


class ActionHistory:
    def __init__(self, path, *, max_records=1000, retention_days=30, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_records = max(1, min(int(max_records), 1000))
        self.retention_days = max(1, min(int(retention_days), 30))
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.names = set(LOCAL_READS)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS action_receipts (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                tool TEXT NOT NULL, origin TEXT NOT NULL, started TEXT NOT NULL,
                finished TEXT, approval TEXT NOT NULL, outcome TEXT NOT NULL,
                verification TEXT NOT NULL, failure TEXT, components TEXT NOT NULL)''')
            # The previous host died before returning a receipt. Effects may remain.
            db.execute("UPDATE action_receipts SET outcome='interrupted', verification='unknown', "
                       "finished=? WHERE finished IS NULL", (self._now(),))
            self._prune(db)

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

    def _now(self):
        return self.clock().astimezone(timezone.utc).isoformat()

    def _prune(self, db):
        cutoff = (self.clock() - timedelta(days=self.retention_days)).astimezone(timezone.utc).isoformat()
        db.execute('DELETE FROM action_receipts WHERE started < ?', (cutoff,))
        db.execute('DELETE FROM action_receipts WHERE sequence NOT IN '
                   '(SELECT sequence FROM action_receipts ORDER BY sequence DESC LIMIT ?)', (self.max_records,))

    def register(self, specs):
        # Only host registration contributes names; never accept proposal names verbatim.
        self.names.update(spec.name for spec in specs
                          if re.fullmatch(r'[a-z][a-z0-9_]{0,63}', spec.name))

    def begin(self, name, origin):
        name = name if type(name) is str and name in self.names else 'unknown_tool'
        origin = origin.value if isinstance(origin, RequestOrigin) else 'unknown'
        identifier = str(uuid4())
        with self._db() as db:
            db.execute('INSERT INTO action_receipts '
                       '(id,tool,origin,started,approval,outcome,verification,components) '
                       'VALUES (?,?,?,?,?,?,?,?)',
                       (identifier, name, origin, self._now(), 'not_requested', 'pending', 'unknown', '{}'))
            self._prune(db)
        return identifier

    def approval(self, identifier, state):
        if state not in {'required', 'approved', 'not_required'}:
            raise ValueError('Unknown approval state.')
        with self._db() as db:
            db.execute('UPDATE action_receipts SET approval=? WHERE id=? AND finished IS NULL',
                       (state, identifier))

    @staticmethod
    def _verification(name, value):
        # Only the existing Windows adapters supply independently checked evidence.
        # Other handlers returning {verified: true} cannot promote their own claims.
        if not isinstance(value, dict):
            return 'unverified', {}
        if name in {'desktop_volume_read', 'desktop_volume_set'}:
            return ('verified' if value.get('verified') is True and value.get('state') == 'verified'
                    else 'unverified'), {}
        if name == 'desktop_open_app':
            return ('verified' if value.get('verified') is True and value.get('state') == 'visible'
                    else 'unverified'), {}
        if name == 'desktop_start_workspace':
            components = {}
            actions = value.get('actions')
            if isinstance(actions, list):
                for item in actions[:3]:
                    if not isinstance(item, dict):
                        continue
                    label = item.get('component')
                    if label not in {'Chrome', 'Obsidian', 'Workspace folder'}:
                        continue
                    state = item.get('state')
                    components[label] = ('failed' if state == 'failed' else
                        'verified' if label != 'Workspace folder' and state == 'visible'
                        and item.get('verified') is True else 'unverified')
            return ('partial' if 'failed' in components.values() else 'unverified'), components
        return 'unverified', {}

    def finish(self, identifier, result):
        outcome, verification, failure, components = 'interrupted', 'unknown', None, {}
        if result is not None:
            if result.status == ResultStatus.SUCCESS:
                outcome = 'returned'
                name = result.plan.spec.name if result.plan is not None else ''
                verification, components = self._verification(name, result.value)
            elif result.status == ResultStatus.FAILED:
                outcome = 'failed'
                code = result.failure.code if result.failure else None
                failure = code.value if isinstance(code, FailureCode) else 'execution_failed'
                if code in {FailureCode.APPROVAL_REJECTED, FailureCode.APPROVAL_REQUIRED,
                            FailureCode.AUTHORITY_DENIED, FailureCode.INVALID_ARGUMENTS, FailureCode.UNKNOWN_TOOL}:
                    verification = 'not_executed'
            else:
                outcome = 'preview'
                verification = 'not_executed'
        with self._db() as db:
            db.execute('UPDATE action_receipts SET finished=?,outcome=?,verification=?,failure=?,components=?, '
                       "approval=CASE WHEN ?='approval_rejected' THEN 'rejected' ELSE approval END "
                       'WHERE id=? AND finished IS NULL',
                       (self._now(), outcome, verification, failure, json.dumps(components), failure, identifier))
            self._prune(db)

    def read_completed(self, name, operation):
        """Fixed read-only command; no parameters or result content reach SQLite."""
        from iris.tools.models import ToolResult, ToolFailure
        identifier = self.begin(name, RequestOrigin.USER)
        self.approval(identifier, 'not_required')
        try:
            result = operation()
        except Exception:
            self.finish(identifier, ToolResult(ResultStatus.FAILED,
                failure=ToolFailure(FailureCode.EXECUTION_FAILED, 'Local read failed.')))
            raise
        self.finish(identifier, ToolResult(ResultStatus.SUCCESS))
        return result

    def rows(self):
        with self._db() as db:
            self._prune(db)
            rows = [dict(row) for row in db.execute('SELECT * FROM action_receipts ORDER BY sequence DESC')]
        for row in rows:
            row['components'] = json.loads(row['components'])
        return rows

    def clear(self):
        with self._db() as db:
            db.execute('DELETE FROM action_receipts')

    def report(self, zone, *, today=True):
        local = ZoneInfo(zone)
        date = self.clock().astimezone(local).date()
        rows = [row for row in self.rows() if not today or
                datetime.fromisoformat(row['started']).astimezone(local).date() == date]
        lines = [f"I have {len(rows)} recorded tool attempts {'today' if today else 'in retained history'}." +
                 (' Here are the latest 20:' if len(rows) > 20 else '')]
        for row in rows[:20]:
            when = datetime.fromisoformat(row['started']).astimezone(local).strftime('%H:%M' if today else '%m-%d %H:%M')
            label = row['tool'].replace('desktop_', '').replace('_', ' ')
            status = ('verified' if row['verification'] == 'verified' else
                      'partial result' if row['verification'] == 'partial' else
                      'returned; result unverified' if row['outcome'] == 'returned' else
                      row['outcome'])
            if row['failure']:
                status += ' (' + row['failure'].replace('_', ' ') + ')'
            if row['verification'] == 'unknown' and row['outcome'] != 'pending':
                status += '; effects unknown, check before retrying'
            lines.append(f"{when} — {label}: {status}; approval: {row['approval'].replace('_', ' ')}.")
            if row['components']:
                lines.append('  ' + '; '.join(f'{key}: {value}' for key, value in row['components'].items()))
        lines.append(COVERAGE)
        lines.append('Kept locally for up to 30 days / 1,000 records. Say “clear action history” to erase these receipts.')
        return '\n'.join(lines)

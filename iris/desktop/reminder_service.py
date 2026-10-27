"""Durable desktop reminders and optional, bounded owner-only SMS.

The UI only reads/acknowledges this outbox. All notification and phone I/O runs
on the worker. Acknowledging a reminder does not complete the underlying task.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, time as daytime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import time
import unicodedata

from iris.goals.store import GoalStore
from iris.tasks.deadlines import local_zone
from iris.tasks.store import TaskStore


LEAD_SECONDS = 15 * 60
CATCH_UP_SECONDS = 24 * 3600
SMS_CATCH_UP_SECONDS = 3600
POLL_SECONDS = 15
MAX_PENDING = 3
MAX_NEW_PER_FIVE_MINUTES = 3
SMS_PER_HOUR = 2
SMS_PER_DAY = 10


class ReminderService:
    def __init__(self, data_dir, settings, clock=None, transport_factory=None, notifier=None):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / 'reminders.sqlite3'
        self.settings = dict(settings)
        self.clock = clock or time.time
        self.notifier = notifier
        self.enabled = str(self.settings.get('IRIS_AUTO_REMINDERS', 'true')).lower() == 'true'
        self.zone = local_zone(self.settings.get('IRIS_TIMEZONE', 'America/New_York'))
        self._transport_factory = transport_factory
        self._transport = None
        self._phone_config = None
        self._sms_requested = str(self.settings.get('IRIS_AUTO_REMINDER_SMS', 'false')).lower() == 'true'
        self._error = None
        self._stop = threading.Event()
        self._thread = None
        self._lifecycle_lock = threading.Lock()
        if self._sms_requested:
            from iris.phone.config import PhoneConfig
            try:
                self._phone_config = PhoneConfig.from_environment(self.settings)
            except ValueError:
                pass
        with self._connection(write=True) as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('Reminder storage is from a newer IRIS version.')
            connection.execute('''CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
                title TEXT NOT NULL, due_at TEXT NOT NULL, due REAL NOT NULL,
                created REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                alert_attempted INTEGER NOT NULL DEFAULT 0,
                sms_state TEXT NOT NULL, sms_attempted REAL, sms_sid TEXT
            )''')
            connection.execute('CREATE INDEX IF NOT EXISTS reminders_state ON reminders(state, due)')
            connection.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            # A crash after provider submission must never cause an automatic resend.
            connection.execute("UPDATE reminders SET sms_state = 'unknown' WHERE sms_state = 'sending'")
            if self._phone_config is not None:
                connection.execute("INSERT OR IGNORE INTO settings VALUES ('sms_activated_at', ?)", (str(self._now()),))
            connection.execute('PRAGMA user_version = 1')
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _now(self):
        value = self.clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError('Reminder clock must include a timezone.')
            return value.timestamp()
        return float(value)

    @contextmanager
    def _connection(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA secure_delete = ON')
            if write:
                connection.execute('BEGIN IMMEDIATE')
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _identifier(kind, entity_id, due_at):
        return hashlib.sha256((kind + ':' + entity_id + ':' + due_at).encode('utf-8')).hexdigest()[:40]

    def _entities(self):
        """Read current stores without creating/migrating them or holding a DB lock."""
        entities = {}
        linked_dates = set()
        task_path = self.data_dir / 'tasks.sqlite3'
        if task_path.is_file():
            with TaskStore(task_path, read_only=True) as store:
                for task in store.list():
                    if task.status != 'open' or task.due_at is None:
                        continue
                    due = datetime.fromisoformat(task.due_at)
                    identifier = self._identifier('task', task.id, task.due_at)
                    entities[identifier] = {'id': identifier, 'kind': 'task', 'entity_id': task.id,
                                            'title': task.title, 'due_at': task.due_at, 'due': due.timestamp()}
                    if task.goal_id:
                        linked_dates.add((task.goal_id, due.astimezone(self.zone).date().isoformat()))
        goal_path = self.data_dir / 'goals.sqlite3'
        if goal_path.is_file():
            with GoalStore(goal_path, read_only=True) as store:
                for goal in store.list():
                    if goal.status != 'active' or not goal.target_date or (goal.id, goal.target_date) in linked_dates:
                        continue
                    due = datetime.combine(datetime.fromisoformat(goal.target_date).date(), daytime(9), self.zone)
                    due_at = due.astimezone(timezone.utc).isoformat()
                    identifier = self._identifier('goal', goal.id, due_at)
                    entities[identifier] = {'id': identifier, 'kind': 'goal', 'entity_id': goal.id,
                                            'title': goal.title, 'due_at': due_at, 'due': due.timestamp()}
        return entities

    def _read_entities(self):
        try:
            result = self._entities()
            self._error = None
            return result
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
            # Fail closed: never send an alert based on an unreadable or stale task snapshot.
            self._error = 'Reminders are waiting for the local task and goal stores.'
            return None

    @staticmethod
    def _invalidate(connection, entities, now):
        rows = connection.execute("SELECT id, due FROM reminders WHERE state = 'pending' OR sms_state = 'queued'").fetchall()
        for row in rows:
            if row['id'] not in entities or now - row['due'] > CATCH_UP_SECONDS:
                connection.execute("UPDATE reminders SET state = CASE WHEN state = 'pending' THEN 'stale' ELSE state END, "
                                   "sms_state = CASE WHEN sms_state = 'queued' THEN 'suppressed' ELSE sms_state END WHERE id = ?",
                                   (row['id'],))

    def tick(self):
        """Discover due reminders locally. This method never performs network I/O."""
        if not self.enabled:
            return []
        entities = self._read_entities()
        if entities is None:
            return []
        now = self._now()
        with self._connection(write=True) as connection:
            self._invalidate(connection, entities, now)
            recent = connection.execute('SELECT COUNT(*) FROM reminders WHERE created > ?', (now - 300,)).fetchone()[0]
            available = max(0, MAX_NEW_PER_FIVE_MINUTES - recent)
            activation = connection.execute("SELECT value FROM settings WHERE name = 'sms_activated_at'").fetchone()
            activated_at = float(activation[0]) if activation else now
            # Upcoming deadlines come first; catch-up is bounded to the previous day.
            eligible = [item for item in entities.values()
                        if item['due'] - (LEAD_SECONDS if item['kind'] == 'task' else 0)
                        <= now <= item['due'] + CATCH_UP_SECONDS]
            eligible.sort(key=lambda item: (item['due'] < now, abs(item['due'] - now), item['id']))
            for item in eligible:
                if available <= 0:
                    break
                sms = ('queued' if self._phone_config is not None and item['due'] >= activated_at
                       and now <= item['due'] + SMS_CATCH_UP_SECONDS else 'disabled')
                result = connection.execute('''INSERT OR IGNORE INTO reminders
                    (id,kind,entity_id,title,due_at,due,created,sms_state) VALUES (?,?,?,?,?,?,?,?)''',
                    (item['id'], item['kind'], item['entity_id'], item['title'], item['due_at'], item['due'], now, sms))
                available -= result.rowcount
            # Keep deduplication IDs but discard old acknowledged message text.
            connection.execute("UPDATE reminders SET title = '' WHERE state != 'pending' AND created < ?", (now - 30 * 86400,))
        return self.pending()

    def _public(self, row, entity=None):
        now = self._now()
        title = (entity or row)['title']
        due = datetime.fromtimestamp(row['due'], timezone.utc).astimezone(self.zone)
        stamp = due.strftime('%a %b %d, %I:%M %p %Z')
        if row['kind'] == 'goal':
            message = f'Goal target today: {title}. Check-in: {stamp} ({self.zone.key}).'
            if due.date() != datetime.fromtimestamp(now, timezone.utc).astimezone(self.zone).date():
                message = f'Goal target: {title}. Check-in was {stamp} ({self.zone.key}).'
        else:
            label = 'was due' if now > row['due'] else 'is due'
            message = f'{title} {label} {stamp} ({self.zone.key}).'
        return {'id': row['id'], 'kind': row['kind'], 'entity_id': row['entity_id'],
                'task_id': row['entity_id'] if row['kind'] == 'task' else None,
                'title': title, 'message': message, 'due_at': row['due_at'],
                'due_local': due.isoformat(), 'created_at': datetime.fromtimestamp(row['created'], timezone.utc).isoformat(),
                'catch_up': row['created'] > row['due'], 'sms_state': row['sms_state']}

    def pending(self):
        if not self.enabled:
            return []
        entities = self._read_entities()
        if entities is None:
            return []
        with self._connection(write=True) as connection:
            self._invalidate(connection, entities, self._now())
            rows = connection.execute("SELECT * FROM reminders WHERE state = 'pending' ORDER BY created, due LIMIT ?",
                                      (MAX_PENDING,)).fetchall()
        return [self._public(row, entities[row['id']]) for row in rows]

    def acknowledge(self, event_id):
        if not isinstance(event_id, str) or len(event_id) != 40:
            raise ValueError('Unknown reminder.')
        with self._connection(write=True) as connection:
            row = connection.execute('SELECT * FROM reminders WHERE id = ?', (event_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown reminder.')
            if row['state'] == 'pending':
                connection.execute("UPDATE reminders SET state = 'acknowledged' WHERE id = ?", (event_id,))
        return {'id': event_id, 'acknowledged': True}

    def status(self):
        with self._connection() as connection:
            pending = connection.execute("SELECT COUNT(*) FROM reminders WHERE state = 'pending'").fetchone()[0]
            sms = dict(connection.execute('SELECT sms_state, COUNT(*) FROM reminders GROUP BY sms_state').fetchall())
        return {'enabled': self.enabled, 'running': bool(self._thread and self._thread.is_alive()),
                'pending': pending, 'timezone': self.zone.key, 'lead_minutes': LEAD_SECONDS // 60,
                'sms_requested': self._sms_requested, 'sms_enabled': self._phone_config is not None,
                'sms_counts': sms, 'last_error': self._error}

    def _deliver_desktop_alerts(self):
        if self.notifier is None or not self.enabled:
            return
        entities = self._read_entities()
        if entities is None:
            return
        with self._connection(write=True) as connection:
            self._invalidate(connection, entities, self._now())
            rows = connection.execute("SELECT * FROM reminders WHERE state = 'pending' AND alert_attempted = 0 "
                                      "ORDER BY created, due LIMIT ?", (MAX_PENDING,)).fetchall()
        # Previously shown but unacknowledged HUD reminders must not prevent
        # later native alerts while the user has minimized the window.
        for row in rows:
            event = self._public(row, entities[row['id']])
            if self._stop.is_set():
                return
            with self._connection(write=True) as connection:
                claimed = connection.execute("UPDATE reminders SET alert_attempted = 1 WHERE id = ? "
                                             "AND alert_attempted = 0 AND state = 'pending'", (event['id'],)).rowcount
            if claimed:
                try:
                    self.notifier('IRIS reminder', event['message'])
                except Exception:
                    # The HUD still has the durable event when the OS notification is unavailable.
                    pass

    def _sms_text(self, row, entity):
        # Restrict to single-width GSM characters; ASCII extension characters such
        # as brackets, backslash and tilde would consume two septets each.
        title = unicodedata.normalize('NFKD', entity['title']).encode('ascii', 'ignore').decode('ascii')
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?'-():/"
        title = ' '.join(''.join(char if char in allowed else ' ' for char in title).split())
        title = title or ('Your goal' if row['kind'] == 'goal' else 'Your task')
        due = datetime.fromtimestamp(row['due'], timezone.utc).astimezone(self.zone)
        suffix = due.strftime(' - %b %d %I:%M %p %Z') + '. Reply STOP to stop.'
        return ('IRIS reminder: ' + title)[:155 - len(suffix)].rstrip() + suffix

    def _deliver_sms(self):
        if not self.enabled or self._phone_config is None:
            return
        from iris.phone.store import PhoneStore
        try:
            phone_store = PhoneStore(self.data_dir / 'phone.sqlite3', clock=self._now)
            entities = self._read_entities()
            if entities is None:
                return
            now = self._now()
            with self._connection(write=True) as connection:
                self._invalidate(connection, entities, now)
                rows = connection.execute("SELECT * FROM reminders WHERE sms_state = 'queued' ORDER BY due, created").fetchall()
            for row in rows:
                if self._stop.is_set():
                    return
                # Re-read before each external submission: a task may have changed during a previous send.
                entities = self._read_entities()
                if entities is None:
                    return
                now = self._now()
                stale = row['id'] not in entities or now > row['due'] + SMS_CATCH_UP_SECONDS
                opted_out = phone_store.opted_out()
                with self._connection(write=True) as connection:
                    hour = connection.execute('SELECT COUNT(*) FROM reminders WHERE sms_attempted > ?', (now - 3600,)).fetchone()[0]
                    day = connection.execute('SELECT COUNT(*) FROM reminders WHERE sms_attempted > ?', (now - 86400,)).fetchone()[0]
                    if stale or opted_out or hour >= SMS_PER_HOUR or day >= SMS_PER_DAY:
                        connection.execute("UPDATE reminders SET sms_state = 'suppressed' WHERE id = ? AND sms_state = 'queued'", (row['id'],))
                        continue
                    claimed = connection.execute("UPDATE reminders SET sms_state = 'sending', sms_attempted = ? "
                                                 "WHERE id = ? AND sms_state = 'queued'", (now, row['id'])).rowcount
                if not claimed:
                    continue
                if phone_store.opted_out():
                    with self._connection(write=True) as connection:
                        connection.execute("UPDATE reminders SET sms_state = 'suppressed' WHERE id = ? AND sms_state = 'sending'", (row['id'],))
                    continue
                try:
                    if self._transport is None:
                        if self._transport_factory is None:
                            from iris.phone.transport import TwilioTransport
                            self._transport_factory = TwilioTransport
                        self._transport = self._transport_factory(self._phone_config)
                    # Initialization may have taken time. Check shutdown, STOP and
                    # the current deadline again immediately before the network call.
                    current = self._read_entities()
                    if (self._stop.is_set() or current is None or row['id'] not in current
                            or phone_store.opted_out() or self._now() > row['due'] + SMS_CATCH_UP_SECONDS):
                        with self._connection(write=True) as connection:
                            connection.execute("UPDATE reminders SET sms_state = 'suppressed' WHERE id = ? AND sms_state = 'sending'", (row['id'],))
                        continue
                    sid = self._transport.send_sms(self._sms_text(row, current[row['id']]))
                    with self._connection(write=True) as connection:
                        connection.execute("UPDATE reminders SET sms_state = 'accepted', sms_sid = ? WHERE id = ? AND sms_state = 'sending'",
                                           (sid, row['id']))
                except Exception:
                    with self._connection(write=True) as connection:
                        connection.execute("UPDATE reminders SET sms_state = 'unknown' WHERE id = ? AND sms_state = 'sending'", (row['id'],))
        except (OSError, ValueError, sqlite3.Error):
            self._error = 'SMS reminders are waiting for the local phone store.'

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
                self._deliver_desktop_alerts()
                if not self._stop.is_set():
                    self._deliver_sms()
            except Exception:
                self._error = 'Reminder monitoring will try again shortly.'
            self._stop.wait(POLL_SECONDS)

    def start(self):
        with self._lifecycle_lock:
            if not self.enabled or (self._thread and self._thread.is_alive()):
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='iris-reminders', daemon=True)
            self._thread.start()

    def stop(self):
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)

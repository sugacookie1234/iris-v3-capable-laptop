"""Durable local notification outbox."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3

from iris.notifications.models import NotificationEvent

DEFAULT_NOTIFICATIONS_PATH = Path("~/.local/share/iris-v2/notifications.sqlite3")


def configured_path(path=None) -> Path:
    return Path(path or os.environ.get("IRIS_NOTIFICATIONS_PATH") or DEFAULT_NOTIFICATIONS_PATH).expanduser().resolve()


class NotificationStore:
    def __init__(self, path=None):
        self.path = configured_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.close()
            raise ValueError("Notification database schema is newer than this IRIS version.")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, dedup_key TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
            PRAGMA user_version = 1;
        """)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def publish(self, event: NotificationEvent) -> NotificationEvent:
        if not isinstance(event, NotificationEvent):
            raise ValueError("Expected a typed NotificationEvent.")
        existing = self._connection.execute("SELECT data FROM notifications WHERE dedup_key = ?", (event.dedup_key,)).fetchone()
        if existing:
            return self._decode(existing[0])
        with self._connection:
            self._connection.execute("INSERT INTO notifications VALUES (?, ?, ?)",
                                     (event.id, event.dedup_key, json.dumps(event.to_dict(), ensure_ascii=True)))
        return event

    def _decode(self, raw: str) -> NotificationEvent:
        return NotificationEvent(**json.loads(raw))

    def get(self, identifier: str) -> NotificationEvent | None:
        row = self._connection.execute("SELECT data FROM notifications WHERE id = ?", (identifier,)).fetchone()
        return self._decode(row[0]) if row else None

    def list(self, *, include_read=True, include_dismissed=False, limit=100) -> tuple[NotificationEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Notification limit must be between 1 and 1000.")
        rows = self._connection.execute("SELECT data FROM notifications ORDER BY json_extract(data, '$.created_at') DESC LIMIT ?", (limit,))
        values = []
        for row in rows:
            event = self._decode(row[0])
            if not include_read and event.read:
                continue
            if not include_dismissed and event.dismissed:
                continue
            values.append(event)
        return tuple(values)

    def _state(self, identifier, *, read=None, dismissed=None) -> NotificationEvent:
        event = self.get(identifier)
        if event is None:
            raise ValueError("Notification not found.")
        updated = replace(event, read=event.read if read is None else read,
                          dismissed=event.dismissed if dismissed is None else dismissed)
        with self._connection:
            self._connection.execute("UPDATE notifications SET data = ? WHERE id = ?",
                                     (json.dumps(updated.to_dict(), ensure_ascii=True), identifier))
        return updated

    def mark_read(self, identifier):
        return self._state(identifier, read=True)

    def dismiss(self, identifier):
        return self._state(identifier, dismissed=True, read=True)

    def prune(self, *, now=None, max_events=1000, max_age_days=30):
        if type(max_events) is not int or max_events < 1 or type(max_age_days) is not int or max_age_days < 1:
            raise ValueError("Notification retention limits must be positive integers.")
        reference = now or datetime.now(timezone.utc)
        cutoff = reference.astimezone(timezone.utc) - timedelta(days=max_age_days)
        rows = self._connection.execute("SELECT id, data FROM notifications")
        remove = []
        for row in rows:
            event = self._decode(row[1])
            stamp = datetime.fromisoformat(event.created_at.replace("Z", "+00:00"))
            if stamp < cutoff:
                remove.append(event.id)
        remaining = self._connection.execute("SELECT id FROM notifications ORDER BY json_extract(data, '$.created_at') DESC").fetchall()
        remove.extend(row[0] for row in remaining[max_events:])
        with self._connection:
            self._connection.executemany("DELETE FROM notifications WHERE id = ?", ((identifier,) for identifier in set(remove)))
        return len(set(remove))

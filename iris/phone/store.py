"""Durable phone jobs with bounded retention and no automatic resend."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import re
import sqlite3
import time


EXECUTION_STATES = ("queued", "working", "ready", "sending", "sent", "unknown", "failed", "suppressed")
DELIVERY_STATES = frozenset({
    "accepted", "scheduled", "queued", "sending", "sent", "delivered", "undelivered",
    "failed", "canceled", "read", "receiving", "received", "ringing", "in-progress",
    "completed", "busy", "no-answer",
})
FINAL_DELIVERY_STATES = frozenset({"delivered", "undelivered", "failed", "canceled", "read", "completed", "busy", "no-answer"})


def _identifier(value: str) -> str:
    # Session identifiers must be opaque IDs, never phone numbers or PINs.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value):
        raise ValueError("Invalid phone identifier.")
    return value


class PhoneStore:
    def __init__(self, path, clock=time.time):
        self.path = Path(path).expanduser().resolve()
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(write=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("Phone storage is from a newer IRIS version.")
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, channel TEXT NOT NULL CHECK(channel IN ('sms','voice')),
                session TEXT NOT NULL, prompt TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL, created REAL NOT NULL, sid TEXT,
                delivery TEXT NOT NULL DEFAULT ''
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_state_created ON jobs(state, created)")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_channel_created ON jobs(channel, created)")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_sid ON jobs(sid)")
            connection.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO settings VALUES ('opt_out', '0')")
            connection.execute("CREATE TABLE IF NOT EXISTS calls (sid TEXT PRIMARY KEY, created REAL NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS calls_created ON calls(created)")
            connection.execute("CREATE TABLE IF NOT EXISTS controls (id TEXT PRIMARY KEY, created REAL NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS controls_created ON controls(created)")
            connection.execute("PRAGMA user_version = 1")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @contextmanager
    def _connection(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA secure_delete = ON")
            if write:
                connection.execute("BEGIN IMMEDIATE")
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
    def _opted_out(connection) -> bool:
        return connection.execute("SELECT value FROM settings WHERE name = 'opt_out'").fetchone()[0] == "1"

    def enqueue(self, job_id, channel, session, prompt) -> bool:
        _identifier(job_id)
        _identifier(session)
        if channel not in ("sms", "voice") or not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
            raise ValueError("Invalid phone request.")
        now = self.clock()
        with self._connection(write=True) as connection:
            if connection.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone():
                return False
            if channel == "sms" and self._opted_out(connection):
                raise ValueError("SMS replies are paused.")
            count = connection.execute("SELECT count(*) FROM jobs WHERE channel = ? AND created > ?",
                                       (channel, now - 3600)).fetchone()[0]
            if count >= (20 if channel == "sms" else 60):
                raise ValueError("Phone request limit reached. Try again later.")
            pending = connection.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','working')").fetchone()[0]
            if pending >= 8:
                raise ValueError("IRIS is handling other phone requests. Try again later.")
            connection.execute("INSERT INTO jobs (id,channel,session,prompt,state,created) VALUES (?,?,?,?,?,?)",
                               (job_id, channel, session, prompt, "queued", now))
        return True

    def claim(self) -> dict | None:
        with self._connection(write=True) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE state = 'queued' ORDER BY created, rowid LIMIT 1").fetchone()
            if row is None:
                return None
            connection.execute("UPDATE jobs SET state = 'working' WHERE id = ?", (row["id"],))
            return {**dict(row), "state": "working"}

    def ready(self, job_id, reply) -> None:
        _identifier(job_id)
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 4000:
            raise ValueError("Invalid phone reply.")
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET reply = ?, state = 'ready' WHERE id = ? AND state = 'working'",
                               (reply, job_id))

    def get(self, job_id) -> dict | None:
        _identifier(job_id)
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def begin_send(self, job_id) -> bool:
        _identifier(job_id)
        with self._connection(write=True) as connection:
            row = connection.execute("SELECT channel, state FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or row["state"] != "ready":
                return False
            if row["channel"] == "sms" and self._opted_out(connection):
                connection.execute("UPDATE jobs SET state = 'suppressed' WHERE id = ?", (job_id,))
                return False
            connection.execute("UPDATE jobs SET state = 'sending' WHERE id = ?", (job_id,))
            return True

    def sent(self, job_id, sid) -> None:
        _identifier(job_id)
        _identifier(sid)
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET state = 'sent', sid = ? WHERE id = ? AND state = 'sending'",
                               (sid, job_id))

    def uncertain(self, job_id) -> None:
        _identifier(job_id)
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET state = 'unknown' WHERE id = ? AND state = 'sending'", (job_id,))

    def abort(self, job_id) -> None:
        _identifier(job_id)
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET state = 'failed' WHERE id = ? AND state IN ('queued','working','ready')",
                               (job_id,))

    def status(self, sid, state) -> None:
        _identifier(sid)
        if not isinstance(state, str) or state not in DELIVERY_STATES:
            raise ValueError("Invalid phone delivery status.")
        with self._connection(write=True) as connection:
            rows = connection.execute("SELECT id, delivery FROM jobs WHERE sid = ?", (sid,)).fetchall()
            for row in rows:
                # A delayed queue callback must not replace a final outcome.
                if row["delivery"] in FINAL_DELIVERY_STATES and state not in FINAL_DELIVERY_STATES:
                    continue
                connection.execute("UPDATE jobs SET delivery = ? WHERE id = ?", (state, row["id"]))

    def opted_out(self) -> bool:
        with self._connection() as connection:
            return self._opted_out(connection)

    def set_opt_out(self, value: bool) -> None:
        if type(value) is not bool:
            raise ValueError("Invalid phone opt-out setting.")
        with self._connection(write=True) as connection:
            self._set_opt_out(connection, value)

    @staticmethod
    def _set_opt_out(connection, value):
        connection.execute("UPDATE settings SET value = ? WHERE name = 'opt_out'", ("1" if value else "0",))
        if value:
            connection.execute("UPDATE jobs SET state = 'suppressed' WHERE channel = 'sms' AND state IN ('queued','ready')")

    def apply_opt_out(self, message_sid, opted_out: bool) -> bool:
        """Apply a signed STOP/START once, so webhook retries cannot undo newer consent."""
        _identifier(message_sid)
        if type(opted_out) is not bool:
            raise ValueError("Invalid phone opt-out setting.")
        with self._connection(write=True) as connection:
            if connection.execute("SELECT 1 FROM controls WHERE id = ?", (message_sid,)).fetchone():
                return False
            connection.execute("INSERT INTO controls VALUES (?,?)", (message_sid, self.clock()))
            self._set_opt_out(connection, opted_out)
            return True

    def recover(self) -> None:
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET state = 'failed' WHERE state = 'working'")
            connection.execute("UPDATE jobs SET state = 'unknown' WHERE state = 'sending'")
            connection.execute("UPDATE jobs SET state = 'failed' WHERE state = 'queued' AND created < ?",
                               (self.clock() - 120,))

    def maintenance(self) -> None:
        now = self.clock()
        with self._connection(write=True) as connection:
            connection.execute("UPDATE jobs SET prompt = '', reply = '' WHERE created < ? AND (prompt != '' OR reply != '')",
                               (now - 86400,))
            connection.execute("DELETE FROM jobs WHERE created < ?", (now - 7 * 86400,))
            connection.execute("DELETE FROM calls WHERE created < ?", (now - 7 * 86400,))
            connection.execute("DELETE FROM controls WHERE created < ?", (now - 7 * 86400,))

    def register_call(self, call_sid) -> bool:
        _identifier(call_sid)
        now = self.clock()
        with self._connection(write=True) as connection:
            if connection.execute("SELECT 1 FROM calls WHERE sid = ?", (call_sid,)).fetchone():
                return False
            if connection.execute("SELECT count(*) FROM calls WHERE created > ?", (now - 3600,)).fetchone()[0] >= 10:
                raise ValueError("Phone call limit reached. Try again later.")
            connection.execute("INSERT INTO calls VALUES (?,?)", (call_sid, now))
        return True

    def counts(self) -> dict:
        with self._connection() as connection:
            rows = connection.execute("SELECT state, count(*) AS total FROM jobs GROUP BY state").fetchall()
            result = dict.fromkeys(EXECUTION_STATES, 0)
            for row in rows:
                if row["state"] in result:
                    result[row["state"]] = row["total"]
            return result

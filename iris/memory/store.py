"""Local SQLite persistence for structured IRIS memories."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from iris.memory.models import MemoryItem, MemoryRevision, utc_now
from iris.memory.redaction import reject_secrets


DEFAULT_MEMORY_PATH = Path("~/.local/share/iris-v2/memory.sqlite3")
SCHEMA_VERSION = 1


class MemoryStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        configured = path or os.environ.get("IRIS_MEMORY_PATH")
        self.path = Path(configured).expanduser() if configured else DEFAULT_MEMORY_PATH.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        self._secure_file()

    def _secure_file(self) -> None:
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _migrate(self) -> None:
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY, category TEXT NOT NULL, subject TEXT NOT NULL,
                key TEXT NOT NULL, value_json TEXT NOT NULL, summary TEXT NOT NULL,
                source_type TEXT NOT NULL, source_ref TEXT, confidence REAL NOT NULL,
                confirmation TEXT NOT NULL, sensitivity TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                last_accessed_at TEXT, expires_at TEXT, supersedes_id TEXT,
                FOREIGN KEY (supersedes_id) REFERENCES memory_items(id)
            );
            CREATE INDEX IF NOT EXISTS idx_memory_lookup
                ON memory_items(category, subject, key, status);
            CREATE INDEX IF NOT EXISTS idx_memory_expiry
                ON memory_items(status, expires_at);
            CREATE TABLE IF NOT EXISTS memory_revisions (
                id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                old_value_json TEXT NOT NULL, new_value_json TEXT NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memory_items(id)
            );
            CREATE TABLE IF NOT EXISTS memory_events (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, memory_id TEXT,
                created_at TEXT NOT NULL, metadata_json TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memory_items(id)
            );
        """)
        row = self._connection.execute(
            "SELECT value FROM schema_meta WHERE key = ?", ("version",)
        ).fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
                ("version", str(SCHEMA_VERSION)),
            )
        elif int(row["value"]) > SCHEMA_VERSION:
            raise RuntimeError("Memory database schema is newer than this IRIS version.")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def insert(self, item: MemoryItem) -> MemoryItem:
        reject_secrets(item.value, item.summary, item.subject, item.key)
        self._connection.execute(
            """INSERT INTO memory_items
            (id, category, subject, key, value_json, summary, source_type, source_ref,
             confidence, confirmation, sensitivity, status, created_at, updated_at,
             last_accessed_at, expires_at, supersedes_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.id, str(item.category), item.subject, item.key, item.value_json(),
             item.summary, item.source_type, item.source_ref, item.confidence,
             str(item.confirmation), str(item.sensitivity), str(item.status),
             item.created_at, item.updated_at, item.last_accessed_at,
             item.expires_at, item.supersedes_id),
        )
        self._connection.commit()
        self._secure_file()
        return item

    add = insert

    def fetch(self, memory_id: str) -> MemoryItem | None:
        row = self._connection.execute(
            "SELECT * FROM memory_items WHERE id = ?", (memory_id,)
        ).fetchone()
        return MemoryItem.from_row(row) if row else None

    def active(self, *, category: str | None = None) -> tuple[MemoryItem, ...]:
        query = "SELECT * FROM memory_items WHERE status = ?"
        params: list[str] = ["active"]
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY updated_at DESC"
        return tuple(MemoryItem.from_row(row) for row in self._connection.execute(query, params))

    def current(self) -> tuple[MemoryItem, ...]:
        """Return active, non-rejected, non-expired structured memories."""
        now = utc_now()
        rows = self._connection.execute(
            """SELECT * FROM memory_items
               WHERE status = ? AND confirmation != ?
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY updated_at DESC""",
            ("active", "rejected", now),
        ).fetchall()
        return tuple(MemoryItem.from_row(row) for row in rows)

    def pending(self) -> tuple[MemoryItem, ...]:
        """Return active memories awaiting explicit confirmation."""
        now = utc_now()
        rows = self._connection.execute(
            """SELECT * FROM memory_items
               WHERE status = ? AND confirmation = ?
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY updated_at DESC""",
            ("active", "pending", now),
        ).fetchall()
        return tuple(MemoryItem.from_row(row) for row in rows)

    def export_structured(self, path: str | os.PathLike[str]) -> Path:
        """Write current memories as a sanitized JSON document."""
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        memories = []
        for item in self.current():
            if str(item.confirmation) != "confirmed":
                continue
            reject_secrets(item.value, item.summary, item.subject, item.key)
            memories.append({
                "id": item.id, "category": str(item.category), "subject": item.subject,
                "key": item.key, "value": item.value, "summary": item.summary,
                "source_type": item.source_type, "source_ref": item.source_ref,
                "confidence": item.confidence, "confirmation": str(item.confirmation),
                "sensitivity": str(item.sensitivity), "status": str(item.status),
                "created_at": item.created_at, "updated_at": item.updated_at,
                "expires_at": item.expires_at, "supersedes_id": item.supersedes_id,
            })
        payload = {"version": 1, "exported_at": utc_now(), "memories": memories}
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        return destination

    def supersede(self, memory_id: str, replacement: MemoryItem, reason: str) -> MemoryItem:
        current = self.fetch(memory_id)
        if current is None:
            raise KeyError(f"Memory not found: {memory_id}")
        if replacement.supersedes_id not in (None, memory_id):
            raise ValueError("Replacement supersedes_id must match the replaced memory.")
        replacement = MemoryItem(**{**replacement.__dict__, "supersedes_id": memory_id})
        reject_secrets(replacement.value, replacement.summary, reason)
        now = utc_now()
        with self._connection:
            self._connection.execute(
                "UPDATE memory_items SET status = ?, updated_at = ? WHERE id = ?",
                ("superseded", now, memory_id),
            )
            self._connection.execute(
                "INSERT INTO memory_revisions VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), memory_id, current.value_json(), replacement.value_json(), reason, now),
            )
            self._insert_event("superseded", memory_id, {"replacement_id": replacement.id})
            self._insert_item_no_commit(replacement)
        return replacement

    update = supersede

    def forget(self, memory_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE memory_items SET status = ?, updated_at = ? WHERE id = ? AND status != ?",
                ("deleted", utc_now(), memory_id, "deleted"),
            )
            if cursor.rowcount:
                self._insert_event("forgotten", memory_id, {})
        return bool(cursor.rowcount)

    def hard_purge(self, memory_id: str) -> bool:
        with self._connection:
            self._connection.execute("DELETE FROM memory_revisions WHERE memory_id = ?", (memory_id,))
            self._connection.execute("DELETE FROM memory_events WHERE memory_id = ?", (memory_id,))
            cursor = self._connection.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
        return bool(cursor.rowcount)

    def export(self) -> dict[str, list[dict[str, object]]]:
        result: dict[str, list[dict[str, object]]] = {}
        for table in ("memory_items", "memory_revisions", "memory_events"):
            rows = self._connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            result[table] = [dict(row) for row in rows]
        return result

    def _insert_item_no_commit(self, item: MemoryItem) -> None:
        reject_secrets(item.value, item.summary, item.subject, item.key)
        self._connection.execute(
            "INSERT INTO memory_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item.id, str(item.category), item.subject, item.key, item.value_json(), item.summary,
             item.source_type, item.source_ref, item.confidence, str(item.confirmation),
             str(item.sensitivity), str(item.status), item.created_at, item.updated_at,
             item.last_accessed_at, item.expires_at, item.supersedes_id),
        )

    def _insert_event(self, kind: str, memory_id: str | None, metadata: dict[str, object]) -> None:
        self._connection.execute(
            "INSERT INTO memory_events VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), kind, memory_id, utc_now(), json.dumps(metadata, sort_keys=True)),
        )

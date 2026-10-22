"""Deterministic, local retrieval of relevant structured memories."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem, MemoryStatus
from iris.memory.store import MemoryStore


_WORD_RE = re.compile(r"[A-Za-z0-9_'-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryRetriever:
    """Search active memory without invoking models or external services."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self._fts_available = self._ensure_fts()

    def _ensure_fts(self) -> bool:
        try:
            self.store._connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
                "memory_id UNINDEXED, subject, key, summary)"
            )
            self.store._connection.commit()
            return True
        except sqlite3.OperationalError:
            return False

    def _refresh_fts(self) -> None:
        if not self._fts_available:
            return
        connection = self.store._connection
        connection.execute("DELETE FROM memory_fts")
        rows = connection.execute(
            """SELECT id, subject, key, summary FROM memory_items
            WHERE status = ? AND confirmation != ?
            AND (expires_at IS NULL OR expires_at > ?)""",
            (MemoryStatus.ACTIVE, MemoryConfirmation.REJECTED, _now()),
        )
        connection.executemany(
            "INSERT INTO memory_fts(memory_id, subject, key, summary) VALUES (?, ?, ?, ?)",
            ((row["id"], row["subject"], row["key"], row["summary"]) for row in rows),
        )
        connection.commit()

    @staticmethod
    def _terms(query: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(word.lower() for word in _WORD_RE.findall(query)))

    def _candidate_ids(self, query: str, terms: tuple[str, ...]) -> set[str] | None:
        if not terms:
            return None
        if self._fts_available:
            self._refresh_fts()
            expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
            rows = self.store._connection.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?", (expression,)
            )
            return {row["memory_id"] for row in rows}
        return None

    def search(
        self,
        query: str,
        *,
        categories: tuple[str, ...] = (),
        subject: str | None = None,
        limit: int = 8,
        max_chars: int = 4000,
    ) -> tuple[MemoryItem, ...]:
        if limit < 0 or max_chars < 0:
            raise ValueError("Retrieval limits must be non-negative.")
        terms = self._terms(query)
        params: list[object] = [MemoryStatus.ACTIVE, MemoryConfirmation.REJECTED, _now()]
        clauses = [
            "status = ?", "confirmation != ?",
            "(expires_at IS NULL OR expires_at > ?)",
        ]
        if categories:
            placeholders = ", ".join("?" for _ in categories)
            clauses.append(f"category IN ({placeholders})")
            params.extend(categories)
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        candidate_ids = self._candidate_ids(query, terms)
        if candidate_ids is not None:
            if not candidate_ids:
                return ()
            placeholders = ", ".join("?" for _ in candidate_ids)
            clauses.append(f"id IN ({placeholders})")
            params.extend(sorted(candidate_ids))
        elif terms:
            text_clauses = []
            for term in terms:
                text_clauses.append("(subject LIKE ? OR key LIKE ? OR summary LIKE ?)")
                pattern = f"%{term}%"
                params.extend((pattern, pattern, pattern))
            clauses.append("(" + " OR ".join(text_clauses) + ")")
        rows = self.store._connection.execute(
            "SELECT * FROM memory_items WHERE " + " AND ".join(clauses), params
        ).fetchall()
        items = [MemoryItem.from_row(row) for row in rows]
        category_set = {str(category) for category in categories}

        def score(item: MemoryItem) -> tuple[float, str]:
            haystack = " ".join((item.subject, item.key, item.summary)).lower()
            subject_match = 1.0 if subject and item.subject.lower() == subject.lower() else 0.0
            key_match = sum(1.0 for term in terms if term in item.key.lower())
            text_match = sum(1.0 for term in terms if term in haystack)
            category_match = 1.0 if str(item.category) in category_set else 0.0
            confirmation = 1.0 if str(item.confirmation) == MemoryConfirmation.CONFIRMED else 0.0
            try:
                age_days = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(item.updated_at)).total_seconds() / 86400)
            except ValueError:
                age_days = 3650.0
            recency = 1.0 / (1.0 + age_days / 30.0)
            expiry = 0.0
            if item.expires_at:
                try:
                    days = (datetime.fromisoformat(item.expires_at) - datetime.now(timezone.utc)).total_seconds() / 86400
                    expiry = 1.0 / (1.0 + max(0.0, days) / 30.0)
                except ValueError:
                    pass
            return (subject_match * 100 + key_match * 20 + text_match * 5 + category_match * 8
                    + confirmation * 4 + item.confidence * 3 + recency + expiry, item.id)

        items.sort(key=score, reverse=True)
        selected: list[MemoryItem] = []
        used_chars = 0
        for item in items:
            if len(selected) >= limit:
                break
            item_chars = len(item.summary)
            if used_chars + item_chars > max_chars:
                continue
            selected.append(item)
            used_chars += item_chars
        return tuple(selected)


def search_memories(store: MemoryStore, query: str, **kwargs: object) -> tuple[MemoryItem, ...]:
    return MemoryRetriever(store).search(query, **kwargs)


retrieve_memories = search_memories

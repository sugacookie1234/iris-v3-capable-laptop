"""Separate local SQLite goal storage with atomic revision snapshots."""
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from iris.goals.models import Goal, GoalRevision, GoalStatus, goal_id, utc_now

DEFAULT_GOALS_PATH = Path("~/.local/share/iris-v2/goals.sqlite3")


def configured_path(path=None) -> Path:
    return Path(path or os.environ.get("IRIS_GOALS_PATH") or DEFAULT_GOALS_PATH).expanduser().resolve()


class GoalStore:
    def __init__(self, path=None, *, read_only: bool = False):
        self.path = configured_path(path)
        if read_only:
            self._connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            self._connection.row_factory = sqlite3.Row
            try:
                if self._connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Goal database schema is not initialized or is unsupported.")
                self._connection.execute("SELECT id, data FROM goals LIMIT 0")
            except Exception:
                self.close()
                raise
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.close()
            raise ValueError("Goal database schema is newer than this IRIS version.")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS goals (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS goal_revisions (
                goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (goal_id, revision)
            );
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

    def fetch(self, identifier: str) -> Goal | None:
        row = self._connection.execute("SELECT data FROM goals WHERE id = ?", (goal_id(identifier),)).fetchone()
        return Goal(**json.loads(row[0])) if row else None

    def list(self, query: str = "") -> tuple[Goal, ...]:
        if not isinstance(query, str) or len(query) > 10000:
            raise ValueError("Goal search must be text of at most 10000 characters.")
        items = (Goal(**json.loads(row[0])) for row in self._connection.execute("SELECT data FROM goals"))
        return tuple(sorted((goal for goal in items
                             if query.casefold() in (goal.title + "\n" + goal.description).casefold()),
                            key=lambda goal: (goal.status != GoalStatus.ACTIVE, goal.target_date or "9999",
                                             goal.created_at, goal.id)))

    def _snapshot(self, goal: Goal, action: str):
        self._connection.execute("INSERT INTO goal_revisions VALUES (?, ?, ?, ?)",
                                 (goal.id, goal.revision, action, json.dumps(goal.to_dict())))

    def create(self, title: str, description: str = "", category: str = "personal",
               priority: str = "normal", target_date: str | None = None,
               progress: int = 0) -> Goal:
        goal = Goal(title, description, category, priority, GoalStatus.ACTIVE, target_date, progress)
        with self._connection:
            self._connection.execute("INSERT INTO goals VALUES (?, ?)", (goal.id, json.dumps(goal.to_dict())))
            self._snapshot(goal, "created")
        return goal

    def update(self, identifier: str, changes: dict) -> Goal:
        goal_id(identifier)
        if type(changes) is not dict or not changes:
            raise ValueError("Provide at least one goal field to update.")
        allowed = {"title", "description", "category", "priority", "target_date", "progress", "status"}
        if set(changes) - allowed:
            raise ValueError("Unsupported goal field.")
        if changes.get("status") == GoalStatus.COMPLETED or changes.get("status") == "completed":
            raise ValueError("Use /complete-goal to complete a goal.")
        if "status" in changes and changes["status"] not in ("active", "paused", GoalStatus.ACTIVE, GoalStatus.PAUSED):
            raise ValueError("Goal status updates may only activate or pause a goal.")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.fetch(identifier)
            if current is None:
                raise ValueError("Goal not found.")
            if current.status == GoalStatus.COMPLETED:
                raise ValueError("Completed goals cannot be updated.")
            goal = replace(current, **changes, updated_at=utc_now(), revision=current.revision + 1)
            self._connection.execute("UPDATE goals SET data = ? WHERE id = ?", (json.dumps(goal.to_dict()), goal.id))
            self._snapshot(goal, "updated")
        return goal

    def complete(self, identifier: str) -> Goal:
        goal_id(identifier)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.fetch(identifier)
            if current is None:
                raise ValueError("Goal not found.")
            if current.status == GoalStatus.COMPLETED:
                return current
            goal = replace(current, status=GoalStatus.COMPLETED, progress=100,
                           updated_at=utc_now(), revision=current.revision + 1)
            self._connection.execute("UPDATE goals SET data = ? WHERE id = ?", (json.dumps(goal.to_dict()), goal.id))
            self._snapshot(goal, "completed")
        return goal

    def revisions(self, identifier: str) -> tuple[GoalRevision, ...]:
        rows = self._connection.execute("SELECT * FROM goal_revisions WHERE goal_id = ? ORDER BY revision",
                                        (goal_id(identifier),))
        return tuple(GoalRevision(row["goal_id"], row["revision"], row["action"],
                                  Goal(**json.loads(row["data"]))) for row in rows)

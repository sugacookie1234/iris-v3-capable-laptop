"""Separate, local SQLite task storage with atomic revision snapshots."""
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

from iris.tasks.models import Task, TaskRevision, TaskStatus, now, task_id

DEFAULT_TASK_PATH = Path("~/.local/share/iris-v2/tasks.sqlite3")


def configured_path(path=None) -> Path:
    return Path(path or os.environ.get("IRIS_TASKS_PATH") or DEFAULT_TASK_PATH).expanduser().resolve()


class TaskStore:
    def __init__(self, path=None, *, read_only: bool = False):
        self.path = configured_path(path)
        if read_only:
            # Reminder monitoring must not create, migrate, or chmod the database.
            self._connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            self._connection.row_factory = sqlite3.Row
            try:
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version != 1:
                    raise ValueError("Reminder monitoring requires a version 1 task database.")
                self._connection.execute("SELECT id, data FROM tasks LIMIT 0")
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
            raise ValueError("Task database schema is newer than this IRIS version.")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_revisions (
                task_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (task_id, revision)
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

    def fetch(self, identifier: str) -> Task | None:
        row = self._connection.execute("SELECT data FROM tasks WHERE id = ?", (task_id(identifier),)).fetchone()
        return Task(**json.loads(row[0])) if row else None

    def list(self, query: str = "") -> tuple[Task, ...]:
        if not isinstance(query, str) or len(query) > 10000:
            raise ValueError("Search must be text of at most 10000 characters.")
        items = (Task(**json.loads(row[0])) for row in self._connection.execute("SELECT data FROM tasks"))
        return tuple(sorted((t for t in items if t.status != TaskStatus.DELETED
                            and query.casefold() in (t.title + "\n" + t.notes).casefold()),
                            key=lambda t: (t.status != TaskStatus.OPEN, t.due_at or "9999", t.created_at, t.id)))

    def _revision(self, task, action):
        self._connection.execute("INSERT INTO task_revisions VALUES (?, ?, ?, ?)",
                                 (task.id, task.revision, action, json.dumps(task.to_dict())))

    def create(self, title: str, notes: str = "", due_at: str | None = None, priority: str = "normal", goal_id: str | None = None) -> Task:
        task = Task(title=title, notes=notes, due_at=due_at, priority=priority, goal_id=goal_id)
        with self._connection:
            self._connection.execute("INSERT INTO tasks VALUES (?, ?)", (task.id, json.dumps(task.to_dict())))
            self._revision(task, "created")
        return task

    def _transition(self, identifier, status):
        task_id(identifier)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.fetch(identifier)
            if current is None or current.status == TaskStatus.DELETED:
                raise ValueError("Task not found.")
            if current.status == status:
                return current
            task = replace(current, status=status, updated_at=now(), revision=current.revision + 1)
            self._connection.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(task.to_dict()), task.id))
            self._revision(task, status.value)
        return task

    def complete(self, identifier):
        return self._transition(identifier, TaskStatus.COMPLETED)

    def delete(self, identifier):
        return self._transition(identifier, TaskStatus.DELETED)

    def revisions(self, identifier) -> tuple[TaskRevision, ...]:
        rows = self._connection.execute("SELECT * FROM task_revisions WHERE task_id = ? ORDER BY revision", (task_id(identifier),))
        return tuple(TaskRevision(r["task_id"], r["revision"], r["action"], Task(**json.loads(r["data"]))) for r in rows)

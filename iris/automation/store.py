"""Separate SQLite persistence for opt-in workflow automation metadata."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from iris.automation.models import AutomationApproval, AutomationRun, AutomationRunStatus, AutomationSchedule

DEFAULT_AUTOMATION_PATH = Path("~/.local/share/iris-v2/automation.sqlite3")


def configured_path(path=None) -> Path:
    return Path(path or os.environ.get("IRIS_AUTOMATION_PATH") or DEFAULT_AUTOMATION_PATH).expanduser().resolve()


class AutomationStore:
    def __init__(self, path=None):
        self.path = configured_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.close()
            raise ValueError("Automation database schema is newer than this IRIS version.")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, occurrence TEXT NOT NULL,
                data TEXT NOT NULL, UNIQUE(schedule_id, occurrence)
            );
            CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, data TEXT NOT NULL);
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

    def create(self, schedule: AutomationSchedule) -> AutomationSchedule:
        if not isinstance(schedule, AutomationSchedule):
            raise ValueError("Expected an AutomationSchedule.")
        with self._connection:
            self._connection.execute("INSERT INTO schedules VALUES (?, ?)",
                                     (schedule.id, json.dumps(schedule.to_dict())))
        return schedule

    def fetch(self, identifier: str) -> AutomationSchedule | None:
        row = self._connection.execute("SELECT data FROM schedules WHERE id = ?", (identifier,)).fetchone()
        return AutomationSchedule(**json.loads(row[0])) if row else None

    def list(self, enabled: bool | None = None) -> tuple[AutomationSchedule, ...]:
        rows = self._connection.execute("SELECT data FROM schedules ORDER BY id")
        schedules = tuple(AutomationSchedule(**json.loads(row[0])) for row in rows)
        return tuple(item for item in schedules if enabled is None or item.enabled == enabled)

    def set_enabled(self, identifier: str, enabled: bool) -> AutomationSchedule:
        schedule = self.fetch(identifier)
        if schedule is None:
            raise ValueError("Automation schedule not found.")
        updated = replace(schedule, enabled=enabled,
                          updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
        with self._connection:
            self._connection.execute("UPDATE schedules SET data = ? WHERE id = ?",
                                     (json.dumps(updated.to_dict()), identifier))
        return updated

    def update(self, identifier: str, changes: dict) -> AutomationSchedule:
        schedule = self.fetch(identifier)
        if schedule is None:
            raise ValueError("Automation schedule not found.")
        if type(changes) is not dict or not changes:
            raise ValueError("Provide at least one schedule field to update.")
        allowed = {"workflow_name", "run_at", "recurrence_seconds", "enabled"}
        if set(changes) - allowed:
            raise ValueError("Unsupported schedule field.")
        updated = replace(schedule, **changes,
                          updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
        with self._connection:
            self._connection.execute("UPDATE schedules SET data = ? WHERE id = ?",
                                     (json.dumps(updated.to_dict()), identifier))
        return updated

    def delete(self, identifier: str) -> AutomationSchedule:
        schedule = self.fetch(identifier)
        if schedule is None:
            raise ValueError("Automation schedule not found.")
        with self._connection:
            self._connection.execute("DELETE FROM schedules WHERE id = ?", (identifier,))
        return schedule

    def execution(self, schedule_id: str, occurrence: str) -> AutomationRun | None:
        row = self._connection.execute("SELECT data FROM executions WHERE schedule_id = ? AND occurrence = ?",
                                       (schedule_id, occurrence)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        data["status"] = AutomationRunStatus(data["status"])
        return AutomationRun(**data)

    def record_execution(self, run: AutomationRun) -> AutomationRun:
        with self._connection:
            self._connection.execute("INSERT INTO executions VALUES (?, ?, ?, ?)",
                                     (run.id, run.schedule_id, run.occurrence, json.dumps({
                                         "id": run.id, "schedule_id": run.schedule_id, "occurrence": run.occurrence,
                                         "workflow_name": run.workflow_name, "status": run.status.value,
                                         "workflow_id": run.workflow_id, "started_at": run.started_at,
                                         "finished_at": run.finished_at, "failure": run.failure,
                                     })))
        return run

    def update_execution(self, run: AutomationRun) -> AutomationRun:
        with self._connection:
            self._connection.execute("UPDATE executions SET data = ? WHERE id = ?", (
                json.dumps({"id": run.id, "schedule_id": run.schedule_id, "occurrence": run.occurrence,
                            "workflow_name": run.workflow_name, "status": run.status.value,
                            "workflow_id": run.workflow_id, "started_at": run.started_at,
                            "finished_at": run.finished_at, "failure": run.failure}), run.id))
        return run

    def executions(self, schedule_id: str | None = None) -> tuple[AutomationRun, ...]:
        if schedule_id is None:
            rows = self._connection.execute("SELECT data FROM executions ORDER BY occurrence DESC")
        else:
            rows = self._connection.execute("SELECT data FROM executions WHERE schedule_id = ? ORDER BY occurrence DESC", (schedule_id,))
        return tuple(AutomationRun(**{**json.loads(row[0]), "status": AutomationRunStatus(json.loads(row[0])["status"])}) for row in rows)

    def add_approval(self, approval: AutomationApproval) -> AutomationApproval:
        with self._connection:
            self._connection.execute("INSERT INTO approvals VALUES (?, ?)", (approval.id, json.dumps({
                "id": approval.id, "schedule_id": approval.schedule_id, "execution_id": approval.execution_id,
                "workflow_name": approval.workflow_name, "occurrence": approval.occurrence,
                "created_at": approval.created_at, "details": approval.details, "resolved": approval.resolved,
                "definition_signature": approval.definition_signature, "permissions": approval.permissions,
                "explicitly_requested": approval.explicitly_requested, "proposal": approval.proposal,
                "expires_at": approval.expires_at, "status": approval.status, "resolved_at": approval.resolved_at,
            })))
        return approval

    def approval(self, identifier: str) -> AutomationApproval | None:
        row = self._connection.execute("SELECT data FROM approvals WHERE id = ?", (identifier,)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        data["details"] = tuple(tuple(item) for item in data.get("details", ()))
        data["permissions"] = tuple(data.get("permissions", ()))
        data["proposal"] = tuple(tuple(item) for item in data.get("proposal", ()))
        data.setdefault("status", "pending")
        data.setdefault("resolved", data["status"] != "pending")
        return AutomationApproval(**data)

    def resolve_approval(self, identifier: str, status: str, resolved_at: str) -> AutomationApproval:
        approval = self.approval(identifier)
        if approval is None:
            raise ValueError("Automation approval not found.")
        if approval.status != "pending":
            raise ValueError("Automation approval is no longer pending.")
        if status not in {"approved", "rejected", "expired", "failed"}:
            raise ValueError("Invalid approval status.")
        updated = AutomationApproval(**{**approval.__dict__, "status": status,
                                        "resolved": True, "resolved_at": resolved_at})
        with self._connection:
            self._connection.execute("UPDATE approvals SET data = ? WHERE id = ?", (
                json.dumps({**updated.__dict__, "details": updated.details,
                            "permissions": updated.permissions, "proposal": updated.proposal}), identifier))
        return updated

    def pending_approvals(self) -> tuple[AutomationApproval, ...]:
        rows = self._connection.execute("SELECT data FROM approvals ORDER BY id")
        values = []
        for row in rows:
            data = json.loads(row[0])
            if data.get("status", "pending") != "pending" and data.get("resolved", True):
                continue
            data["details"] = tuple(tuple(x) for x in data["details"])
            data["permissions"] = tuple(data.get("permissions", ()))
            data["proposal"] = tuple(tuple(x) for x in data.get("proposal", ()))
            data.setdefault("status", "pending")
            data.setdefault("resolved", False)
            values.append(AutomationApproval(**data))
        return tuple(values)

    def all_approvals(self) -> tuple[AutomationApproval, ...]:
        rows = self._connection.execute("SELECT id FROM approvals ORDER BY id")
        values = []
        for row in rows:
            approval = self.approval(row[0])
            if approval is not None:
                values.append(approval)
        return tuple(values)

    def expire_approvals(self, now: str) -> tuple[AutomationApproval, ...]:
        expired = []
        for approval in self.pending_approvals():
            if approval.expires_at and approval.expires_at <= now:
                expired.append(self.resolve_approval(approval.id, "expired", now))
        return tuple(expired)

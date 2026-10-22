"""Foreground opt-in automation worker; never starts background monitoring."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
import time
from typing import Callable, Mapping

from iris.automation.scheduler import AutomationScheduler
from iris.automation.store import AutomationStore
from iris.notifications import NotificationEvent, NotificationKind, NotificationSeverity, NotificationStore
from iris.terminal import load_config, create_brain

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_STATUS_PATH = Path("~/.local/share/iris-v2/automation.lock")


@dataclass(frozen=True)
class AutomationWorkerConfig:
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    automation_path: str | None = None
    status_path: str | None = None

    def __post_init__(self) -> None:
        if (type(self.interval_seconds) not in (int, float)
                or not math.isfinite(self.interval_seconds)
                or not 1 <= self.interval_seconds <= 86400):
            raise ValueError("Automation interval must be finite and between 1 and 86400 seconds.")


def load_worker_config(environ: Mapping[str, str] | None = None) -> AutomationWorkerConfig:
    env = os.environ if environ is None else environ
    raw = env.get("IRIS_AUTOMATION_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)).strip()
    try:
        interval = float(raw)
    except ValueError:
        raise ValueError("IRIS_AUTOMATION_INTERVAL_SECONDS must be numeric seconds.") from None
    return AutomationWorkerConfig(interval, env.get("IRIS_AUTOMATION_PATH") or None,
                                  env.get("IRIS_AUTOMATION_STATUS_PATH") or None)


def _status_path(path: str | os.PathLike[str] | None) -> Path:
    return Path(path or os.environ.get("IRIS_AUTOMATION_STATUS_PATH") or DEFAULT_STATUS_PATH).expanduser()


@contextmanager
def worker_lock(path: str | os.PathLike[str] | None = None):
    if fcntl is None:
        yield
        return
    marker = _status_path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("An automation worker is already running.") from None
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class AutomationWorker:
    def __init__(self, scheduler: AutomationScheduler, config: AutomationWorkerConfig,
                 emit: Callable[[str], None] = print,
                 clock: Callable[[], datetime] | None = None,
                 notifications: NotificationStore | None = None):
        self.scheduler = scheduler
        self.config = config
        self.emit = emit
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.notifications = notifications
        self.running = True
        self.checks = 0

    def check(self) -> None:
        if not self.running:
            return
        ticks = self.scheduler.run_once(at=self.clock())
        self.checks += 1
        for tick in ticks:
            if self.notifications is not None:
                kind = (NotificationKind.APPROVAL_REQUEST if tick.status.value == "pending_approval"
                        else NotificationKind.FAILURE if tick.status.value in {"failed", "timeout"}
                        else NotificationKind.WORKFLOW_RESULT)
                severity = NotificationSeverity.WARNING if kind == NotificationKind.APPROVAL_REQUEST else (
                    NotificationSeverity.ERROR if kind == NotificationKind.FAILURE else NotificationSeverity.INFO)
                self.notifications.publish(NotificationEvent.create(
                    kind, severity, "automation", {"workflow": tick.run.workflow_name if tick.run else "unknown",
                    "status": tick.status.value, "schedule_id": tick.schedule_id, "occurrence": tick.occurrence},
                    f"automation:{tick.schedule_id}:{tick.occurrence}:{tick.status.value}"))
            self.emit(f"Automation {tick.status.value} | schedule={tick.schedule_id} | "
                      f"workflow={tick.run.workflow_name if tick.run else 'unknown'} | occurrence={tick.occurrence}")
        if not ticks:
            self.emit("Automation skipped | no enabled due schedules.")

    def command(self, text: str) -> None:
        command = text.strip().lower()
        if command == "/automation-status":
            enabled = len(self.scheduler.store.list(enabled=True))
            pending = len(self.scheduler.store.pending_approvals())
            self.emit(f"Automation: {'running' if self.running else 'stopped'}; interval={self.config.interval_seconds:g}s; "
                      f"checks={self.checks}; enabled_schedules={enabled}; pending_approvals={pending}.")
        elif command == "/automation-stop":
            self.running = False
        elif command:
            self.emit("Use /automation-status or /automation-stop. This worker only runs local enabled workflows.")


def run(worker: AutomationWorker, commands, *, monotonic=time.monotonic) -> None:
    next_check = monotonic()
    worker.emit("Local automation started. Use /automation-status or /automation-stop; Ctrl+C or EOF also stops.")
    try:
        while worker.running:
            if monotonic() >= next_check:
                worker.check()
                next_check = monotonic() + worker.config.interval_seconds
            command = commands.poll(max(0.0, next_check - monotonic()))
            if command is not None:
                worker.command(command)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        worker.running = False
        worker.emit("Local automation stopped.")


def _build_worker(config: AutomationWorkerConfig) -> tuple[AutomationWorker, AutomationStore, NotificationStore]:
    chat_config = load_config()
    brain = create_brain(chat_config)
    store = AutomationStore(config.automation_path or chat_config.automation_path)
    notifications = NotificationStore()
    brain._workflow_executor.set_publisher(notifications.publish)
    scheduler = AutomationScheduler(store, brain._workflow_registry, brain._workflow_executor,
                                     brain._tool_executor)
    return AutomationWorker(scheduler, config, emit=lambda value: print(value, flush=True), notifications=notifications), store, notifications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m iris.automation",
        description="Run explicitly enabled local IRIS workflows in the foreground.",
        epilog=("The first due-schedule check is immediate. Polling interval is configured with "
                "IRIS_AUTOMATION_INTERVAL_SECONDS (1–86400 seconds, default 60). "
                "IRIS_AUTOMATION_PATH selects the SQLite store. YELLOW/RED steps only create "
                "approval inbox items. Use /automation-status or /automation-stop; Ctrl+C/EOF stops. "
                "No background worker, shell, network, or external action is used."),
    )
    parser.parse_args(argv)
    try:
        config = load_worker_config()
        from iris.reminders import CommandInput
        commands = CommandInput(sys.stdin)
        with worker_lock(config.status_path):
            worker, store, notifications = _build_worker(config)
            try:
                run(worker, commands)
            finally:
                store.close()
                notifications.close()
    except (KeyboardInterrupt, EOFError):
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Automation worker error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

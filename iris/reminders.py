"""Opt-in foreground task reminders. No task mutations or external actions."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import select
import sqlite3
import sys
import time
from typing import Callable, Mapping

try:
    import fcntl
except ImportError:  # pragma: no cover - worker polling is Unix-oriented
    fcntl = None

from iris.tasks.deadlines import local_zone
from iris.tasks.models import Task, TaskStatus
from iris.tasks.store import TaskStore
from iris.notifications import NotificationEvent, NotificationKind, NotificationSeverity, NotificationStore


DEFAULT_STATUS_PATH = Path("~/.local/share/iris-v2/reminders.lock")


def _status_path(path: str | os.PathLike[str] | None = None) -> Path:
    configured = path or os.environ.get("IRIS_REMINDERS_STATUS_PATH") or DEFAULT_STATUS_PATH
    return Path(configured).expanduser()


@contextmanager
def reminder_worker_lock(path: str | os.PathLike[str] | None = None):
    """Hold a local advisory lock for the life of the foreground worker."""
    if fcntl is None:
        yield
        return
    status = _status_path(path)
    status.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(status, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A local reminder worker is already running.") from None
        os.ftruncate(fd, 0)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def reminder_worker_status(path: str | os.PathLike[str] | None = None) -> str:
    """Return running/stopped/unknown without exposing the marker path or contents."""
    if fcntl is None:
        return "unknown"
    try:
        fd = os.open(_status_path(path), os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return "stopped"
    except OSError:
        return "unknown"
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "running"
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return "stopped"
    except OSError:
        return "unknown"
    finally:
        os.close(fd)


@dataclass(frozen=True)
class ReminderConfig:
    interval_seconds: float = 60
    upcoming_seconds: float = 900
    tasks_path: str | None = None
    timezone: str = 'America/Toronto'

    def __post_init__(self):
        for name, minimum in (('interval_seconds', 1), ('upcoming_seconds', 0)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= 86400:
                raise ValueError(f'{name} must be finite and between {minimum} and 86400 seconds.')
        local_zone(self.timezone)


def load_config(environ: Mapping[str, str] | None = None) -> ReminderConfig:
    env = os.environ if environ is None else environ
    try:
        interval = float(env.get('IRIS_REMINDERS_INTERVAL_SECONDS', '60'))
        upcoming = float(env.get('IRIS_REMINDERS_UPCOMING_SECONDS', '900'))
    except ValueError:
        raise ValueError('Reminder interval and upcoming window must be numeric seconds.') from None
    return ReminderConfig(interval, upcoming, env.get('IRIS_TASKS_PATH') or None,
                          env.get('IRIS_TIMEZONE') or 'America/Toronto')


def eligible_tasks(store: TaskStore, at: datetime, upcoming_seconds: float) -> tuple[Task, ...]:
    """Include every overdue open task and upcoming tasks through the inclusive horizon."""
    if at.tzinfo is None:
        raise ValueError('Reminder reference time must include a timezone.')
    horizon = at.astimezone(timezone.utc) + timedelta(seconds=upcoming_seconds)
    return tuple(task for task in store.list()
                 if task.status == TaskStatus.OPEN and task.due_at is not None
                 and datetime.fromisoformat(task.due_at) <= horizon)


class ReminderWorker:
    def __init__(self, store: TaskStore, config: ReminderConfig,
                 emit: Callable[[str], None] = print,
                 notifications: NotificationStore | None = None):
        self.store = store
        self.config = config
        self.emit = emit
        self.notifications = notifications
        self.announced: set[str] = set()
        self.running = True
        self.checks = 0

    def check(self, at: datetime | None = None) -> None:
        if not self.running:
            return
        at = at or datetime.now(timezone.utc)
        tz = local_zone(self.config.timezone)
        for task in eligible_tasks(self.store, at, self.config.upcoming_seconds):
            if task.id in self.announced:
                continue
            label = 'OVERDUE' if task.is_overdue(at.isoformat()) else 'UPCOMING'
            due = datetime.fromisoformat(task.due_at).astimezone(tz).isoformat()
            # Escape control characters: task titles are display data, never terminal instructions.
            self.emit(f'{label} | {task.id} | {json.dumps(task.title, ensure_ascii=True)} | due={due} [{tz.key}]')
            if self.notifications is not None:
                self.notifications.publish(NotificationEvent.create(
                    NotificationKind.REMINDER, NotificationSeverity.WARNING, "reminders",
                    {"task_id": task.id, "status": label, "due": due},
                    f"reminder:{task.id}:{task.due_at}"))
            self.announced.add(task.id)
        self.checks += 1

    def command(self, text: str) -> None:
        command = text.strip().lower()
        if command == '/reminders-status':
            self.emit(f'Reminders: {"running" if self.running else "stopped"}; '
                      f'interval={self.config.interval_seconds:g}s; upcoming={self.config.upcoming_seconds:g}s; '
                      f'checks={self.checks}; announced={len(self.announced)}; timezone={self.config.timezone}.')
        elif command == '/reminders-stop':
            self.running = False
        elif command:
            self.emit('Use /reminders-status or /reminders-stop. This worker only displays reminders.')


class CommandInput:
    """Read Unix terminal/pipe input without a blocked reader thread on shutdown."""
    def __init__(self, stream):
        self.fd = stream.fileno()
        self.buffer = bytearray()
        self.eof = False
        self.discarding = False

    def poll(self, timeout: float) -> str | None:
        """Return one line, None on timeout, or raise EOFError once input is exhausted."""
        if b'\n' not in self.buffer and not self.eof:
            ready, _, _ = select.select([self.fd], [], [], timeout)
            if not ready:
                return None
            chunk = os.read(self.fd, 4096)
            if not chunk:
                self.eof = True
            self.buffer.extend(chunk)
        if b'\n' in self.buffer:
            line, _, remaining = self.buffer.partition(b'\n')
            self.buffer = bytearray(remaining)
            if self.discarding or len(line) > 4096:
                self.discarding = False
                return '[input too long]'
            return line.decode('utf-8', errors='replace')
        if self.eof:
            if self.buffer:
                line = bytes(self.buffer)
                self.buffer.clear()
                return '[input too long]' if self.discarding else line.decode('utf-8', errors='replace')
            raise EOFError
        if len(self.buffer) > 4096:
            self.buffer.clear()
            self.discarding = True
        return None


def run(worker: ReminderWorker, commands: CommandInput, *, monotonic=time.monotonic) -> None:
    next_check = monotonic()
    worker.emit('Local reminders started. Use /reminders-status or /reminders-stop; Ctrl+C or EOF also stops.')
    try:
        while worker.running:
            current = monotonic()
            if current >= next_check:
                worker.check()
                next_check = monotonic() + worker.config.interval_seconds
            command = commands.poll(max(0, next_check - monotonic()))
            if command is not None:
                worker.command(command)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        worker.running = False
        worker.emit('Local reminders stopped.')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m iris.reminders',
        description='Display passive local task reminders in the foreground using a read-only task database.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Environment configuration (read at startup):
  IRIS_REMINDERS_INTERVAL_SECONDS  Seconds between checks: 1–86400, default 60.
                                  Finite numbers, including fractions, are accepted.
  IRIS_REMINDERS_UPCOMING_SECONDS  Upcoming window: 0–86400 seconds, default 900.
                                  Zero includes only overdue and currently due tasks.
  IRIS_TASKS_PATH                 Existing task database; default:
                                  ~/.local/share/iris-v2/tasks.sqlite3
  IRIS_TIMEZONE                   IANA timezone, default America/Toronto.
  IRIS_REMINDERS_STATUS_PATH      Local status lock; default:
                                  ~/.local/share/iris-v2/reminders.lock.

The first check is immediate. Each task is announced once per run.
Configure the interval through the environment, for example:
  IRIS_REMINDERS_INTERVAL_SECONDS=30 python -m iris.reminders

Worker commands: /reminders-status, /reminders-stop.
Ctrl+C or EOF also stops the worker. No tasks are changed and no external
notifications or actions are performed. --help does not start monitoring.
""",
    )
    # Parse before configuration, stdin setup, or opening the task database.
    parser.parse_args(argv)
    try:
        config = load_config()
        commands = CommandInput(sys.stdin)
        with reminder_worker_lock():
            with TaskStore(config.tasks_path, read_only=True) as store:
                notification_context = (NotificationStore()
                                        if os.environ.get("IRIS_NOTIFICATIONS_PATH") else nullcontext(None))
                with notification_context as notifications:
                    run(ReminderWorker(store, config, emit=lambda text: print(text, flush=True),
                                       notifications=notifications), commands)
    except (KeyboardInterrupt, EOFError):
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f'Reminder worker error: {exc} Check IRIS_TASKS_PATH, IRIS_TIMEZONE, '
              'IRIS_REMINDERS_INTERVAL_SECONDS, and IRIS_REMINDERS_UPCOMING_SECONDS. '
              'Create the task database with IRIS task commands before starting reminders.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

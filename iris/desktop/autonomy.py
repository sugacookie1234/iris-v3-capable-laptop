"""Lifecycle of explicitly enabled conversation organization and reminders."""
from __future__ import annotations

import queue
import threading
from pathlib import Path

from iris.desktop.notification_alerts import notify


def enabled(settings, name='IRIS_AUTO_ORGANIZE_ENABLED'):
    return str(settings.get(name, 'false')).lower() == 'true'


class Autonomy:
    def __init__(self, data_dir, settings, config):
        self.settings = settings
        self.config = config
        self.data_dir = data_dir
        self.organizer = None
        self.notebook = None
        self.reminders = None
        self._queue = queue.Queue(maxsize=20)
        self._stop = threading.Event()
        self._thread = None
        self._processing = False
        self._error = None
        self._notebook_error = None
        self._started = False
        if enabled(settings) or (Path(data_dir) / 'organizer.sqlite3').exists():
            self._initialize()

    def _initialize(self):
        from iris.desktop.notebook import Notebook
        from iris.desktop.organizer import ConversationOrganizer
        from iris.desktop.reminder_service import ReminderService
        vault = self.config.obsidian_vault or self.config.obsidian_root
        try:
            self.notebook = Notebook(self.data_dir, vault_path=vault)
        except (OSError, ValueError):
            self._notebook_error = 'Your notes folder is unavailable. Tasks and reminders still work; reconnect the folder to save notes.'
        self.organizer = ConversationOrganizer(self.data_dir, self.config, self.settings, notebook=self.notebook)
        self.reminders = ReminderService(self.data_dir, self.settings, notifier=notify)

    def start(self):
        if self._started or self.organizer is None or not enabled(self.settings):
            return
        self._started = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='IRIS automatic organizer', daemon=True)
        self._thread.start()
        self.reminders.start()

    def close(self):
        self._stop.set()
        if self.reminders is not None:
            self.reminders.stop()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def submit(self, text, history=()):
        if not enabled(self.settings) or self.organizer is None or self._stop.is_set():
            return
        self.start()
        try:
            self._queue.put_nowait((text, tuple(history)))
        except queue.Full:
            self._error = 'Automatic organization is busy. This message was not saved automatically.'

    def _run(self):
        while not self._stop.is_set():
            try:
                text, history = self._queue.get(timeout=.25)
            except queue.Empty:
                continue
            try:
                if enabled(self.settings) and not self._stop.is_set():
                    self._processing = True
                    self.organizer.process(text, history=history, cancel_event=self._stop)
                    self._error = None
            except Exception:
                self._error = 'Automatic organization could not finish. Check Activity before trying again.'
            finally:
                self._processing = False
                self._queue.task_done()

    def status(self):
        organizer_status = self.organizer.status() if self.organizer is not None else {}
        return {'enabled': enabled(self.settings), 'processing': self._processing,
                'queued': self._queue.qsize(), 'error': self._error or self._notebook_error or organizer_status.get('last_error'),
                'notes_location': 'Obsidian vault' if self.config.obsidian_vault or self.config.obsidian_root else 'IRIS notebook',
                'reminders': self.reminders.status() if self.reminders is not None else {'enabled': False},
                'sms_requested': enabled(self.settings, 'IRIS_AUTO_REMINDER_SMS')}

    def events(self):
        return {'status': self.status(),
                'activity': self.organizer.activity() if self.organizer is not None else [],
                'reminders': self.reminders.pending() if self.reminders is not None and enabled(self.settings) else []}

    def context(self, text):
        if self.organizer is None or not enabled(self.settings):
            return ''
        try:
            return self.organizer.context(text)
        except Exception:
            return ''

    def undo(self, identifier):
        if self.organizer is None:
            raise ValueError('Automatic organization is not configured.')
        return self.organizer.undo(identifier)

    def acknowledge(self, identifier):
        if self.reminders is None:
            raise ValueError('Reminders are not configured.')
        return self.reminders.acknowledge(identifier)

    def notes(self, query=''):
        if self.notebook is None:
            return []
        return self.notebook.search(query)

    def read_note(self, path):
        if self.notebook is None:
            raise ValueError('The notebook is not configured.')
        return self.notebook.read(path)

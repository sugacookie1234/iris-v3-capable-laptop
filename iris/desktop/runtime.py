"""One conversation owner for the browser, speech, council, and local tools."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import secrets
import threading
import time

from iris.brain.llm import LLMMessage, MessageRole
from iris.local_config import effective_environment
from iris.memory.integration import respond_with_memory
from iris.memory.models import MemoryConfirmation
from iris.memory.store import MemoryStore
from iris.tasks.store import TaskStore
from iris.terminal import load_config, create_brain, _memory_proposal
from iris.tools import Approval
from iris.tools.models import ResultStatus

ROOT = Path(__file__).resolve().parents[2]


class BusyError(RuntimeError):
    pass


class DesktopRuntime:
    def __init__(self, settings=None, data_dir=None, brain=None):
        self.settings = effective_environment() if settings is None else dict(settings)
        self.data_dir = Path(data_dir or ROOT / '.local')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_path = self.data_dir / 'memory.sqlite3'
        self.tasks_path = self.data_dir / 'tasks.sqlite3'
        cfg = {**self.settings,
               'IRIS_MEMORY_PATH': str(self.memory_path),
               'IRIS_TASKS_PATH': str(self.tasks_path),
               'IRIS_GOALS_PATH': str(self.data_dir / 'goals.sqlite3'),
               'IRIS_TIMEZONE': self.settings.get('IRIS_TIMEZONE', 'America/New_York')}
        self.config = load_config(cfg)
        self.brain = brain or create_brain(self.config, memory_path=self.memory_path)
        self.brain._tool_approval = self._tool_approval
        self.brain._runtime_context = (
            'You are IRIS in a Windows browser interface. Your answers can be spoken aloud. '
            'Use concise natural sentences for ordinary conversation; give detail when requested. '
            'Do not claim to be JARVIS. Local tasks, goals, briefings, confirmed memory, and '
            'configured read-only workspace/Obsidian tools are available. Task and goal writes '
            'ask for approval in the browser. Email, Google services, arbitrary shell commands '
            'and desktop automation are not connected in this build. Never claim those actions succeeded. '
            'The user can select Council for a deliberation. Only report facts supported by context. '
            'The configured language model runs at the user-selected provider endpoint; the default is cloud OpenRouter. '
            'Local memory storage does not make cloud reasoning private or offline. '
            'Voice recognition supports Fish Audio with a local faster-whisper fallback, or a local-only setting. '
            'Whisper can use NVIDIA acceleration when available; do not assume the active speech engine or device. '
            'Council mode offers advice only and cannot execute tools. '
            'Current local date: ' + time.strftime('%Y-%m-%d')
        )
        self.history = []
        self.turn_lock = threading.Lock()
        self.approval_lock = threading.Lock()
        self.pending = None
        self.audio_tickets = {}
        self.audio_lock = threading.Lock()
        self.last_route = 'FAST'
        self.last_seconds = None

    def approve(self, summary, identifier=None, timeout=90):
        event = threading.Event()
        record = {'id': identifier or secrets.token_urlsafe(20), 'summary': summary,
                  'event': event, 'approved': False, 'resolved': False}
        with self.approval_lock:
            if self.pending is not None:
                return False
            self.pending = record
        try:
            return event.wait(timeout) and record['approved']
        finally:
            with self.approval_lock:
                if self.pending is record:
                    self.pending = None

    def _tool_approval(self, plan):
        return Approval(plan.id, self.approve(plan.confirmation_summary, plan.id))

    def pending_approval(self):
        with self.approval_lock:
            if self.pending is None or self.pending['resolved']:
                return None
            return {k: self.pending[k] for k in ('id', 'summary')}

    def resolve_approval(self, identifier, approved):
        with self.approval_lock:
            if not self.pending or self.pending['id'] != identifier or self.pending['resolved']:
                raise ValueError('This request has expired or was already answered.')
            self.pending['approved'] = approved is True
            self.pending['resolved'] = True
            self.pending['event'].set()

    def memories(self):
        with MemoryStore(self.memory_path) as store:
            return [{'id': m.id, 'summary': m.summary, 'category': str(m.category)} for m in store.current()]

    def tasks(self):
        with TaskStore(self.tasks_path) as store:
            return [t.to_dict() for t in store.list()]

    def reset(self):
        if not self.turn_lock.acquire(blocking=False):
            raise BusyError('Wait for the current response before clearing the conversation.')
        try:
            self.history.clear()
        finally:
            self.turn_lock.release()

    def chat(self, text, mode='auto'):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Enter a message of 1–12000 characters.')
        if mode not in ('auto', 'council'):
            raise ValueError('Unknown reasoning mode.')
        if not self.turn_lock.acquire(blocking=False):
            raise BusyError('IRIS is finishing another request.')
        started = time.monotonic()
        try:
            text = text.strip()
            with MemoryStore(self.memory_path) as store:
                if text.startswith('/remember '):
                    item = _memory_proposal(text[len('/remember '):])
                    if not self.approve('Remember this for future conversations?\n\n' + item.summary):
                        return {'reply': 'I did not save that memory.', 'route': 'LOCAL'}
                    item = replace(item, confirmation=MemoryConfirmation.CONFIRMED)
                    conflicts = [m for m in store.current() if m.category == item.category
                                 and m.subject == item.subject and m.key == item.key]
                    if conflicts:
                        if conflicts[0].value != item.value:
                            if not self.approve('Replace the existing memory?\n\n' + conflicts[0].summary + '\nWith: ' + item.summary):
                                return {'reply': 'I kept the existing memory.', 'route': 'LOCAL'}
                            store.supersede(conflicts[0].id, item, 'Explicit user replacement')
                    else:
                        store.insert(item)
                    return {'reply': 'I have saved that memory.', 'route': 'LOCAL'}
                if text == '/memories':
                    records = store.current()
                    return {'reply': '\n'.join(m.summary for m in records) or 'No memories saved yet.', 'route': 'LOCAL'}
                if text.startswith('/forget '):
                    identifier = text.split(' ', 1)[1].strip()
                    item = next((m for m in store.current() if m.id == identifier), None)
                    if item is None:
                        raise ValueError('That memory was not found. Open Memories to select it.')
                    if self.approve('Forget this memory?\n\n' + item.summary):
                        store.forget(item.id)
                        return {'reply': 'That memory has been forgotten.', 'route': 'LOCAL'}
                    return {'reply': 'I kept that memory.', 'route': 'LOCAL'}
                message = ('Ask the council: ' + text) if mode == 'council' else text
                result = respond_with_memory(self.brain, message, memory_store=store,
                                             history=tuple(self.history))
                tool_result = getattr(result, "tool_result", None)
                if tool_result is not None and tool_result.status == ResultStatus.FAILED:
                    result = replace(result, text="I could not confirm that action completed. "
                        + (tool_result.failure.message if tool_result.failure else "The local tool failed.")
                        + " Check the saved records before retrying.")
                if not result.text.strip():
                    raise RuntimeError('The model returned an empty answer. Try another configured model.')
                self.history.extend([LLMMessage(MessageRole.USER, text),
                                     LLMMessage(MessageRole.ASSISTANT, result.text)])
                limit = self.config.max_history_turns * 2
                self.history = self.history[-limit:] if limit else []
                self.last_route = result.route.reasoning.value
                answer = {'reply': result.text, 'route': self.last_route}
                if result.council is not None:
                    council = result.council
                    answer['council'] = {
                        'candidates': [{'label': c.label, 'seat': c.seat_name, 'text': c.text,
                                        'model': c.target.model} for c in council.candidates],
                        'rankings': [{'reviewer': r.reviewer_name, 'text': r.evaluation,
                                      'ranking': list(r.ranking)} for r in council.rankings],
                        'failures': list(council.failures), 'chairman': council.chairman_model}
                return answer
        finally:
            self.last_seconds = round(time.monotonic() - started, 2)
            self.turn_lock.release()

    def issue_audio(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Invalid speech text.')
        with self.audio_lock:
            now = time.monotonic()
            self.audio_tickets = {k: v for k, v in self.audio_tickets.items() if v[1] > now}
            if len(self.audio_tickets) >= 32:
                raise BusyError('Too many pending speech requests.')
            token = secrets.token_urlsafe(24)
            self.audio_tickets[token] = (text, now + 60)
            return token

    def consume_audio(self, token):
        with self.audio_lock:
            value = self.audio_tickets.pop(token, None)
        if not value or value[1] < time.monotonic():
            raise ValueError('Speech request expired.')
        return value[0]

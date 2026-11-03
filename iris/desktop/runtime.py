"""One conversation owner for the desktop interface, speech, council, and local tools."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import re
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
from iris.tools import Approval, ToolExecutor
from iris.tools.models import ResultStatus
from iris.tools.models import RequestOrigin, ToolResult, ToolFailure, FailureCode
from iris.desktop.web_search import search_query, research
from iris.desktop.autonomy import Autonomy, enabled as automatic_enabled
from iris.desktop.commands import DesktopCommands, normalize
from iris.desktop.action_history import ActionHistory
from iris.desktop.capabilities import build_capabilities, capability_reply
from iris.desktop.vault_commands import VaultCommands
from iris.goals.store import GoalStore
from iris.workflows import WorkflowRegistry
from iris.generalist.plan import notes_briefing_preview
from iris.generalist.business import BusinessWorkspace
from iris.generalist.notes_briefing import NotesBriefing
from iris.agent_jobs.notes import NotesJobs, JobError
from iris.generalist.experiences import Experiences

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
        self.action_history = ActionHistory(self.data_dir / 'action_history.sqlite3')
        self.vault_commands = VaultCommands(self.config, self.action_history)
        self._notes_briefing = None
        self.desktop_commands = DesktopCommands(self.config, self.data_dir, ROOT,
            approve=self._tool_approval, history=self.action_history)
        self.brain = brain or create_brain(self.config, memory_path=self.memory_path)
        executor = getattr(self.brain, '_tool_executor', None)
        if isinstance(executor, ToolExecutor):
            self.action_history.register(executor.specifications())
            executor.observer = self.action_history
        self.brain._tool_approval = self._tool_approval
        self.brain._runtime_context = (
            'You are IRIS in a local Windows desktop interface, also available in Chrome. Your answers can be spoken aloud. '
            'Use concise natural sentences for ordinary conversation; give detail when requested. '
            'Do not claim to be JARVIS. Local tasks, goals, briefings, confirmed memory, and '
            'configured workspace/Obsidian tools are available. Direct owner commands can open Chrome, '
            'Obsidian, Notepad, Calculator, File Explorer and the configured workspace/vault folders, '
            'read or set system volume, find files by name and give a local daily briefing. '
            '"Start my workspace" opens Chrome, Obsidian and the workspace folder. These commands '
            'run in a local dispatcher; your generated text cannot execute them. Only claim an action '
            'occurred when its result is present in conversation history. A launch request is not proof '
            'that a window appeared. Email, Google services, arbitrary shell commands and general '
            'screen clicking are not connected. Never claim those actions succeeded. '
            'Reasoning is selected automatically from each request; the user can also explicitly ask for the council. '
            'The screen has weather and market widgets. You cannot inspect their current values from this context; '
            'the user can say weather update or market update for their sourced readings. '
            'Double-clap standby runs while the app is running, including in its Windows tray, '
            'and the computer is awake, after microphone permission. Spoken turns end on a pause and '
            'offer five seconds to begin a follow-up. "That is all" returns to standby. '
            'The user can say show tasks, show memories, start a new chat, mute, or unmute. '
            '"Make a briefing from my notes on ..." queues a local read-only source briefing. '
            'The Jobs panel shows progress, cancellation, saved results and explicit resume after interruption. '
            'Job details and source excerpts are not included in this model context. '
            'An optional separate SMS/call bridge is available through setup-phone.bat and start-phone.bat; '
            'it requires provider and HTTPS setup. You cannot inspect whether it is configured or running here, '
            'and desktop chat cannot send texts or place calls. Voice wake words and a Windows background service are not connected. '
            'Only report facts supported by context. '
            'The configured language model runs at the user-selected provider endpoint; the default is cloud OpenRouter. '
            'Local memory storage does not make cloud reasoning private or offline. '
            'Voice recognition supports Fish Audio with a local faster-whisper fallback, or a local-only setting. '
            'Whisper can use NVIDIA acceleration when available; do not assume the active speech engine or device. '
            'Council mode offers advice only and cannot execute tools. '
            'Public web research is available when the user starts a request with "search the web for" '
            'or /search. It uses OpenRouter search credit and returns source links. Ordinary chat does not '
            'browse automatically. Do not claim to have searched for an ordinary chat response. '
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
        self._autonomy_lock = threading.Lock()
        self._closed = False
        self.autonomy = Autonomy(self.data_dir, self.settings, self.config)
        self._experience_lock = threading.RLock()
        self._experiences = None
        self._experience_seen = set()
        self.jobs = NotesJobs(self.data_dir / 'jobs.sqlite3',
            self.config.obsidian_vault or self.config.obsidian_root, history=self.action_history,
            on_completed=self._record_experience)
        self._base_context = self.brain._runtime_context

    def start_background(self):
        with self._autonomy_lock:
            if not self._closed:
                self.autonomy.start()

    def close(self):
        with self._autonomy_lock:
            self._closed = True
            self.autonomy.close()
        self.jobs.close()

    def set_automatic_organization(self, active):
        if type(active) is not bool:
            raise ValueError('Choose whether automatic organization is on or paused.')
        from iris.local_config import save_updates
        # Concurrent UI requests must not create an unowned reminder worker.
        # Closing the desktop also prevents an in-flight request restarting it.
        with self._autonomy_lock:
            if self._closed:
                raise BusyError('IRIS is closing. Reopen it to change automatic organization.')
            save_updates({'IRIS_AUTO_ORGANIZE_ENABLED': str(active).lower()}, self.data_dir / 'config.dpapi')
            self.autonomy.close()
            self.settings['IRIS_AUTO_ORGANIZE_ENABLED'] = str(active).lower()
            self.autonomy = Autonomy(self.data_dir, self.settings, self.config)
            self.autonomy.start()
            return self.autonomy.status()

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
        # Standing permission covers only these reversible local organizer tools.
        # Memory, files outside the notebook, and external actions keep their own boundaries.
        if (automatic_enabled(self.settings) and plan.spec.local_only and plan.spec.reversible
                and plan.spec.name in {'tasks_create', 'tasks_complete', 'tasks_delete',
                                      'goals_create', 'goals_update', 'goals_complete'}):
            return Approval(plan.id, True)
        summary = plan.confirmation_summary
        if plan.spec.name.startswith('desktop_'):
            # Keep the exact prepared action/path visible, without reading tool
            # schema and permission metadata aloud for an ordinary app action.
            summary = summary.split('\nExecute ', 1)[0]
            if plan.spec.name == 'desktop_volume_set':
                arguments = dict(plan.arguments)
                changes = []
                if 'percent' in arguments:
                    changes.append(f"Set system volume to {arguments['percent']} percent")
                if 'muted' in arguments:
                    changes.append('Mute system audio' if arguments['muted'] else 'Unmute system audio')
                summary = '. '.join(changes) + '. Then check the device reading.'
        return Approval(plan.id, self.approve(summary, plan.id))

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

    def goals(self):
        path = self.data_dir / 'goals.sqlite3'
        if not path.exists():
            return []
        with GoalStore(path, read_only=True) as store:
            return [g.to_dict() for g in store.list()]

    def reset(self):
        if not self.turn_lock.acquire(blocking=False):
            raise BusyError('Wait for the current response before clearing the conversation.')
        try:
            self.history.clear()
            self.vault_commands.current = None
        finally:
            self.turn_lock.release()

    def capabilities(self):
        executor = getattr(self.brain, '_tool_executor', None)
        workflows = getattr(self.brain, '_workflow_registry', None)
        return build_capabilities(self.config, self.settings,
            self.desktop_commands.actions.specifications(),
            executor.specifications() if isinstance(executor, ToolExecutor) else (),
            getattr(self.brain, '_tool_permissions', ()),
            workflows.definitions() if isinstance(workflows, WorkflowRegistry) else (),
            briefing_specs=self._notes_briefing.specifications() if self._notes_briefing else ())

    def _briefing_runner(self):
        if self._notes_briefing is None:
            vault = self.config.obsidian_vault or self.config.obsidian_root
            if not vault:
                raise ValueError('No vault configured.')
            self._notes_briefing = NotesBriefing(vault, history=self.action_history)
        return self._notes_briefing

    def _experience_store(self):
        # Callers hold the experience lock; each store operation owns its connection.
        if self._experiences is None:
            self._experiences = Experiences(self.memory_path)
        return self._experiences

    def _record_experience(self, event):
        with self._experience_lock:
            key = (event['job_id'], event['attempt'])
            if key not in self._experience_seen:
                self._experience_store().capture(event)
                self._experience_seen.add(key)
                if len(self._experience_seen) > 100:
                    self._experience_seen = {key}  # Durable fingerprints still deduplicate.

    def _reconcile_experiences(self):
        # Recover a crash between job completion and summary capture, including
        # pre-upgrade jobs. No source contents reach the experience store.
        for job in self.jobs.list():
            if job['status'] not in {'completed', 'partial'}:
                continue
            with self._experience_lock:
                if (job['id'], job['attempts']) in self._experience_seen:
                    continue
            event = self.jobs.experience_event(job['id'])
            if event is not None:
                self._record_experience(event)

    def experiences(self):
        try:
            self._reconcile_experiences()
            with self._experience_lock:
                return self._experience_store().list()
        except Exception:
            raise ValueError('Task memory is unavailable. Your jobs and notes are unchanged. Try again later.') from None

    def review_experience(self, identifier, revision, decision):
        with self._experience_lock:
            return self._experience_store().review(identifier, revision, decision)

    def forget_experience(self, identifier, revision):
        with self._experience_lock:
            self._experience_store().forget(identifier, revision)

    def _experience_guidance(self):
        try:
            self._reconcile_experiences()
            with self._experience_lock:
                return self._experience_store().guidance(self.jobs._vault)
        except Exception:
            return 'Task memory is unavailable; this plan uses only the current recipe.'

    def save_business(self, value):
        if type(value) is not dict or set(value) - {'project', 'request_id', 'id', 'revision'}:
            raise ValueError('Unknown business request fields or action.')
        self.action_history.names.add('business_evaluate')
        receipt = self.action_history.begin('business_evaluate', RequestOrigin.USER)
        self.action_history.approval(receipt, 'approved')  # Explicit authenticated Save action.
        try:
            result = BusinessWorkspace(self.memory_path).save(value.get('project'), value.get('request_id'),
                value.get('id'), value.get('revision'))
        except Exception:
            self.action_history.finish(receipt, ToolResult(ResultStatus.FAILED,
                failure=ToolFailure(FailureCode.EXECUTION_FAILED, 'Business evaluation failed.')))
            raise
        self.action_history.finish(receipt, ToolResult(ResultStatus.SUCCESS))
        return result

    def _awareness_command(self, text):
        command = normalize(text)
        if command in {'hello', 'hi', 'hello iris', 'hi iris', 'hey iris'}:
            addressed = getattr(self, '_greeted_owner', False)
            self._greeted_owner = True
            return DesktopCommands.answer('Hello.' if addressed else 'Hello, sir.')
        if 'compound interest' in command and any(word in command for word in ('explain', 'show')):
            from iris.generalist.visuals import compound, validate
            return DesktopCommands.answer('Compound interest earns interest on earlier interest. This example starts with 1,000 units at a hypothetical 5% annual rate, compounded monthly for ten years. It is an educational illustration, not a forecast.',
                'Compound interest earns interest on earlier interest. The chart shows a hypothetical example.', visual=validate(compound()))
        if command in {'show business', 'open business', 'show business projects', 'open business workspace'}:
            items = BusinessWorkspace(self.memory_path).list()
            return DesktopCommands.answer(
                'Open Business to create or compare product scenarios. ' +
                (f'{len(items)} saved projects are available.' if items else 'No business projects saved yet.'),
                'The local business workspace is available.', business=items)
        if command in {'show task memory', 'show my task memory', 'show learned procedures'}:
            items = self.experiences()
            summary = '\n'.join(f"{item['state']}: {item['summary']}" for item in items[:10])
            return DesktopCommands.answer(summary or 'No task memories yet. Complete a notes briefing first.',
                'Task memory is available for review. Open Jobs, then Task memory.', experiences=items)
        if command in {'show jobs', 'show my jobs', 'show background jobs', 'job status', 'what are you working on'}:
            jobs = self.jobs.list()
            lines = [f"{job['topic']} — {job['status']}; {job['stage']}" for job in jobs[:10]]
            return DesktopCommands.answer('\n'.join(lines) if lines else 'There are no saved jobs.',
                f'{len(jobs)} saved jobs. Open Jobs to view results, cancel or resume interrupted work.', jobs=jobs)
        if command in {'cancel briefing', 'cancel my briefing', 'cancel notes briefing',
                       'resume briefing', 'resume my briefing', 'resume notes briefing'}:
            cancel = command.startswith('cancel')
            candidates = [job for job in self.jobs.list() if job['can_cancel' if cancel else 'can_resume']]
            if len(candidates) != 1:
                return DesktopCommands.answer('Open Jobs and choose the briefing to ' + ('cancel.' if cancel else 'resume.')
                    if candidates else 'There is no briefing available to ' + ('cancel.' if cancel else 'resume.'))
            job = (self.jobs.cancel if cancel else self.jobs.resume)(candidates[0]['id'])
            return DesktopCommands.answer('Cancellation requested. Check Jobs for the final status.' if cancel
                else 'The briefing is queued to restart with fresh source checks. You can keep chatting.', job=job)
        briefing = re.fullmatch(r'(?:make|create|run) (?:a |my )?briefing from my notes (?:on|about) (.+)', command)
        if briefing:
            if len(briefing[1]) > 200:
                return DesktopCommands.answer('Give a notes topic of 1 to 200 characters.')
            try:
                self._briefing_runner()
                job = self.jobs.submit(briefing[1])
            except JobError as exc:
                return DesktopCommands.answer(str(exc))
            except (OSError, ValueError):
                return DesktopCommands.answer('Your Obsidian vault is unavailable. Check its folder in setup.bat.')
            return DesktopCommands.answer('The notes briefing is queued in Jobs. You can keep chatting while I work.',
                'I have queued the briefing. You can keep chatting.', job=job)
        preview = re.fullmatch(r'plan a briefing from my notes on (.+)', command)
        if preview:
            try:
                specs = self._briefing_runner().specifications()
            except (OSError, ValueError):
                specs = ()
            try:
                plan = notes_briefing_preview(preview[1], specs, permissions=('obsidian.read',))
            except ValueError:
                return DesktopCommands.answer('Give a notes topic of 1 to 200 characters.')
            ready = plan['stages'][0]['state'] == 'ready'
            lines = [f'Briefing plan: {preview[1]}',
                '1. Search your notes for the topic.' if ready else '1. Configure an accessible Obsidian vault before searching.',
                '2. Read up to three matching notes, prioritizing title matches.',
                '3. Recheck their revisions and prepare a brief of source excerpts.',
                'This is a preview. No notes have been searched or read. '
                f'To start, say “Make a briefing from my notes on {preview[1]}”.']
            guidance = self._experience_guidance() if ready else ''
            if guidance:
                lines.append(guidance)
            return DesktopCommands.answer('\n'.join(lines),
                'I have shown the proposed steps. This is a preview; I have not started the task.', plan=plan)
        if command in {'what can you do', 'what can you do so far', 'show capabilities', 'list capabilities'}:
            inventory = self.capabilities()
            return DesktopCommands.answer(capability_reply(inventory),
                'I can help with chat, briefings, finding files and approved desktop controls. '
                'The screen shows your configured services and current limitations.', capabilities=inventory)
        if command in {'what have you done today', 'what did you do today', 'show action history', 'show my action history'}:
            report = self.action_history.report(self.config.timezone, today='today' in command)
            executors = [getattr(self.brain, '_tool_executor', None),
                         getattr(self.desktop_commands.actions, '_executor', None), self.vault_commands._executor,
                         getattr(self._notes_briefing, 'executor', None), self.jobs]
            if any(getattr(item, 'observer_failed', False) for item in executors):
                report = 'Some history could not be saved this session; this list may be incomplete.\n' + report
            return DesktopCommands.answer(report, report.split('\n')[0] +
                ' The screen shows outcomes and any unverified results. Automatic organization is listed separately in Activity.')
        if command in {'clear action history', 'erase action history', 'delete action history'}:
            if self.approve('Erase all local action-history receipts? This leaves your tasks, notes and memories in place.'):
                self.action_history.clear()
                return DesktopCommands.answer('Local action-history receipts erased.')
            return DesktopCommands.answer('I kept your action history.')
        return self.vault_commands.handle(text)

    def chat(self, text, mode='auto'):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Enter a message of 1–12000 characters.')
        if mode not in ('auto', 'council'):
            raise ValueError('Unknown reasoning mode.')
        if not self.turn_lock.acquire(blocking=False):
            raise BusyError('IRIS is finishing another request.')
        started = time.monotonic()
        capture = False
        capture_history = tuple(self.history[-8:])
        try:
            text = text.strip()
            local_answer = self._awareness_command(text) if mode == 'auto' else None
            private_local_answer = local_answer is not None
            if local_answer is None and mode == 'auto':
                local_answer = self.desktop_commands.handle(text)
            if local_answer is not None:
                # Receipts and local configuration must not ride along in a later
                # model prompt. The UI still displays the complete local answer.
                if not private_local_answer:
                    self.history.extend([LLMMessage(MessageRole.USER, text),
                                         LLMMessage(MessageRole.ASSISTANT, local_answer['reply'])])
                    limit = self.config.max_history_turns * 2
                    self.history = self.history[-limit:] if limit else []
                self.last_route = 'LOCAL'
                return local_answer
            if text.casefold().rstrip('.!') in ('pause automatic organization', 'pause automatic organisation'):
                self.set_automatic_organization(False)
                return {'reply': 'Automatic organization and reminder delivery are paused. Your saved items remain.', 'route': 'LOCAL'}
            if text.casefold().rstrip('.!') in ('resume automatic organization', 'resume automatic organisation'):
                self.set_automatic_organization(True)
                return {'reply': 'Automatic organization and reminders are on.', 'route': 'LOCAL'}
            capture = not text.startswith('/') and mode == 'auto'
            if automatic_enabled(self.settings):
                self.brain._runtime_context = self._base_context + (
                    ' Automatic organization is enabled by the owner. A separate background organizer '
                    'captures clear commitments, deadlines, goals, useful notes and requested note edits '
                    'from the current user message. Do not ask the user to say "create a task" or offer '
                    'to create reminders for clear commitments. Automatic changes appear in Activity with Undo. '
                    'Do not claim a new item was saved or scheduled until a tool result or the local records '
                    'below confirms it. Answer the substance of the conversation; unclear deadlines may '
                    'produce a clarification in Activity. Tasks with a date but no time use 23:59:59 local '
                    'time. Reminders appear 15 minutes before task deadlines; goal dates use 09:00 local. '
                    'The notebook creates organized Markdown notes and can add/update IRIS sections in '
                    'existing notes or move them when the user supplies exact paths. Local task and goal '
                    'tool writes have standing permission. Email and general screen automation remain unavailable.\n'
                ) + self.autonomy.context(text)
            else:
                self.brain._runtime_context = self._base_context + ' Local task and goal writes ask for confirmation. Automatic organization is paused.'
            query = search_query(text) if mode == 'auto' else None
            if query is not None:
                capture = False
                answer = research(self.config, query)
                cited = answer['reply'] + '\nSources:\n' + '\n'.join(
                    item['title'] + ': ' + item['url'] for item in answer['sources'])
                self.history.extend([LLMMessage(MessageRole.USER, text), LLMMessage(MessageRole.ASSISTANT, cited)])
                limit = self.config.max_history_turns * 2
                self.history = self.history[-limit:] if limit else []
                self.last_route = 'WEB'
                return answer
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
                if (tool_result is not None and tool_result.status == ResultStatus.SUCCESS
                        and getattr(getattr(getattr(tool_result, 'plan', None), 'spec', None), 'name', '')
                        in {'tasks_create', 'tasks_complete', 'tasks_delete', 'goals_create', 'goals_update', 'goals_complete'}):
                    capture = False  # A successful explicit write already owns this commitment.
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
            if capture:
                self.autonomy.submit(text, capture_history)
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

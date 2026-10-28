"""Small explicit desktop commands; model output never enters this dispatcher."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import re

from iris.briefing import build_briefing
from iris.calendar import CalendarSource
from iris.tools.workspace import list_files
from iris.tools.models import ResultStatus


APPS = {'chrome': 'chrome', 'google chrome': 'chrome', 'obsidian': 'obsidian',
        'notepad': 'notepad', 'calculator': 'calculator', 'file explorer': 'explorer',
        'explorer': 'explorer'}


def spoken_percent(value):
    if re.fullmatch(r'-?\d+', value):
        return int(value)
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
    words = value.replace('-', ' ').split()
    if value in ('a hundred', 'one hundred', 'hundred'):
        return 100
    if len(words) == 1 and words[0] in small:
        return small.index(words[0])
    if words and words[0] in tens and len(words) <= 2:
        if len(words) == 1:
            return tens[words[0]]
        if words[1] in small[1:10]:
            return tens[words[0]] + small.index(words[1])
    return None


def normalize(text):
    text = re.sub(r'\s+', ' ', text.strip().casefold().replace('’', "'")).rstrip('.!?')
    text = re.sub(r',?\s+please$', '', text)
    for _ in range(3):
        text = re.sub(r'^(?:(?:hey )?iris|please)(?:[,!:]\s*|\s+)', '', text).strip()
        text = re.sub(r'^(?:can|could|would) you (?:please )?', '', text).strip()
    return text


class DesktopCommands:
    def __init__(self, config, data_dir, repo_root, actions=None, approve=None):
        self.config, self.data_dir = config, Path(data_dir)
        self.workspace = Path(config.workspace_root or repo_root).expanduser().absolute()
        self.vault = config.obsidian_vault or config.obsidian_root
        self._actions = actions
        self.approve = approve

    @property
    def actions(self):
        if self._actions is None:
            from iris.desktop.action_tools import DesktopActionTools
            self._actions = DesktopActionTools(self.workspace, self.vault, approve=self.approve)
        return self._actions

    def _run(self, name, **arguments):
        result = self.actions.run(name, **arguments)
        if result.status != ResultStatus.SUCCESS:
            reason = result.failure.message if result.failure else 'The action did not complete.'
            raise ActionFailure(reason)
        return result.value

    @staticmethod
    def answer(text, spoken=None, **details):
        return {'reply': text, 'spoken_reply': spoken or text, 'route': 'LOCAL', **details}

    def handle(self, text):
        command = normalize(text)
        launch = re.fullmatch(r'(?:open|launch|start) (?:the )?(.+)', command)
        try:
            if launch and launch[1] in APPS:
                return self._app(APPS[launch[1]])
            if command in {'open my workspace', 'open my workspace folder', 'open the workspace folder'}:
                return self._folder(self.workspace, 'Workspace')
            if command in {'open my vault', 'open my obsidian vault', 'open my notes folder'}:
                if not self.vault:
                    return self.answer('Your Obsidian vault is not configured yet. Set its folder in setup.bat.')
                return self._folder(Path(self.vault).expanduser().absolute(), 'Obsidian vault')
            if command in {'start my workspace', 'resume my workspace', "let's get to work", 'lets get to work'}:
                return self._workspace()
            if command in {'daily briefing', 'give me my daily briefing', 'give me a daily briefing',
                           'brief me on my day', 'brief me on today', "what's on my agenda", 'what is on my agenda'}:
                return self._briefing()
            if command in {"what's my volume", 'what is my volume', 'what is the system volume', 'check system volume'}:
                return self._volume()
            if command in {'mute my computer', 'mute system audio', 'mute system volume', 'mute the speakers'}:
                return self._volume(muted=True)
            if command in {'unmute my computer', 'unmute system audio', 'unmute system volume', 'unmute the speakers'}:
                return self._volume(muted=False)
            if command in {'volume up', 'turn the volume up', 'turn volume up', 'volume down', 'turn the volume down', 'turn volume down'}:
                current = self._run('desktop_volume_read')
                amount = max(0, min(100, current['percent'] + (10 if command.endswith('up') else -10)))
                return self._volume(percent=amount)
            volume = re.fullmatch(r'(?:set|change|turn) (?:my |the |system )?volume (?:to )?([a-z\d -]+?)(?:\s*(?:%|percent))?', command)
            if volume:
                amount = spoken_percent(volume[1])
                if amount is None or not 0 <= amount <= 100:
                    return self.answer('Choose a volume from 0 to 100 percent. I left it unchanged.')
                return self._volume(percent=amount)
            files = re.fullmatch(r'(?:find|search for) (?:my |the )?files? (?:named|called|containing) (.{1,100})', command)
            if files:
                query = files[1].strip('"\'` ')
                if not query or any(c in query for c in '/\\\x00') or query in {'.', '..'}:
                    return self.answer('Give me part of a filename, for example: find files named report.')
                return self._find(query)
        except ActionFailure as error:
            return self.answer(str(error))
        except (OSError, ValueError, RuntimeError):
            # Native exception text can contain paths or arbitrary OS details.
            return self.answer('I could not complete that local action. Check that the app, folder or audio device is available, then try again.')
        return None

    def _app(self, alias):
        result = self._run('desktop_open_app', app=alias)
        return self.answer(result['detail'], actions=[result])

    def _folder(self, path, label):
        result = self._run('desktop_open_folder', folder='workspace' if label == 'Workspace' else 'vault')
        return self.answer(f"{label}: {result['detail']}", actions=[result])

    def _volume(self, **change):
        result = self._run('desktop_volume_set' if change else 'desktop_volume_read', **change)
        text = f"System volume is {result['percent']} percent" + (' and muted.' if result['muted'] else '.')
        if not result['verified']:
            text = 'The audio device did not confirm the requested change. ' + text
        return self.answer(text)

    def _workspace(self):
        results = self._run('desktop_start_workspace')['actions']
        lines = [f"{item['component']}: {item['detail']}" for item in results]
        return self.answer('\n'.join(lines), actions=results)

    def _briefing(self):
        cfg = self.config
        calendar = CalendarSource(cfg.calendar_root, cfg.calendar_path, cfg.timezone) if cfg.calendar_path else None
        result = build_briefing(task_path=cfg.tasks_path, goal_path=cfg.goals_path,
            calendar=calendar, memory_path=self.data_dir / 'memory.sqlite3', zone=cfg.timezone)
        facts = result['facts']
        overdue = [task for task in result['deadlines'] if task['status'] == 'overdue']
        today = [task for task in result['deadlines'] if task['status'] == 'due_today']
        summary = f"You have {len(overdue)} overdue tasks and {len(today)} due today."
        if facts['calendar_configured']:
            summary += f" Your calendar has {len(facts['events'])} events today."
        else:
            summary += ' Your calendar is not connected.'
        lines = [summary]
        for task in (overdue + today)[:5]:
            lines.append(f"{task['title']} — {task['status'].replace('_', ' ')}")
        for event in facts['events'][:3]:
            when = 'All day' if event['all_day'] else datetime.fromisoformat(event['start_local']).strftime('%H:%M')
            lines.append(f"{when}: {event['title']}")
        goals = facts['active_goals'][:3]
        if goals:
            lines.append('Active goals: ' + '; '.join(f"{goal['title']} ({goal['progress']}%)" for goal in goals))
        if overdue or today:
            summary += ' First on the deadline list: ' + (overdue + today)[0]['title'] + '.'
        return self.answer('\n'.join(lines), summary)

    def _find(self, query):
        roots = [('Workspace', self.workspace)]
        if self.vault and Path(self.vault).absolute() != self.workspace:
            roots.append(('Obsidian', Path(self.vault).expanduser().absolute()))
        queue = deque((label, root, '.', 0) for label, root in roots)
        found, scanned, incomplete = [], 0, False
        while queue and scanned < 80 and len(found) < 12:
            label, root, directory, depth = queue.popleft(); scanned += 1
            try:
                listing = list_files(str(root), directory)
            except (OSError, ValueError):
                incomplete = True
                continue
            incomplete |= listing['truncated']
            for entry in listing['entries']:
                relative = str(Path(directory) / entry['name'])
                if entry['type'] == 'file' and query in entry['name'].casefold():
                    found.append(f'{label}: {relative}')
                    if len(found) == 12:
                        incomplete = True
                        break
                elif entry['type'] == 'directory':
                    if depth < 4:
                        queue.append((label, root, relative, depth + 1))
                    else:
                        incomplete = True
        incomplete |= bool(queue)
        summary = f"Found {len(found)} matching files in your configured folders." if found else 'No matching files appeared in the folders I could check.'
        if incomplete:
            summary += ' The search was limited; deeper folders or additional matches may remain.'
        return self.answer('\n'.join([summary, *found]), summary)


class ActionFailure(RuntimeError):
    """A sanitized result from the authoritative executor, not a native exception."""

"""Explicit local vault inspection. Note contents never become command authority."""
from pathlib import Path
import re

from iris.obsidian import register_obsidian
from iris.tools import AuthorityContext, RequestOrigin, ResultStatus, ToolCall, ToolExecutor, ToolRegistry


def _command(text):
    value = text.strip().replace('’', "'").rstrip('!?')
    for _ in range(3):
        value = re.sub(r'^(?:(?:hey )?iris|please)(?:[,!:]\s*|\s+)', '', value, flags=re.I).strip()
        value = re.sub(r'^(?:can|could|would) you (?:please )?', '', value, flags=re.I).strip()
    return value


class VaultCommands:
    def __init__(self, config, history=None):
        self.config, self.history = config, history
        self._executor = None
        self.current = None

    @property
    def executor(self):
        if self._executor is None:
            vault = self.config.obsidian_vault or self.config.obsidian_root
            if not vault:
                raise ValueError('Your Obsidian vault is not configured. Set its folder in setup.bat.')
            self._executor = ToolExecutor(register_obsidian(ToolRegistry(), vault))
            if self.history is not None:
                self.history.register(self._executor.specifications())
                self._executor.observer = self.history
        return self._executor

    @staticmethod
    def answer(text, spoken=None, **details):
        return {'reply': text, 'spoken_reply': spoken or text, 'route': 'LOCAL', **details}

    def _run(self, name, **arguments):
        result = self.executor.execute(ToolCall(name, arguments, RequestOrigin.USER),
            authority=AuthorityContext(True, frozenset({'obsidian.read'})))
        if result.status != ResultStatus.SUCCESS:
            raise ValueError('I could not read that vault item. Check its relative path and permissions. '
                             'If a note changed between pages, read it again from the beginning.')
        return result.value

    def handle(self, text):
        command = _command(text)
        lower = command.casefold().rstrip('.')
        search = re.fullmatch(r'(?:search (?:my )?(?:obsidian(?: vault)?|vault|notes) for|'
                              r'find (?:my )?notes (?:about|named|containing))\s+(.+)', command, re.I)
        read = re.fullmatch(r'(?:read|show) (?:my |the )?(?:obsidian )?note(?: named)?\s+(.+)', command, re.I)
        recognized = bool(search or read or lower in {'check obsidian', 'check my vault', 'check my obsidian vault',
                                                     'read next page', 'next note page'})
        if not recognized:
            return None
        try:
            if lower in {'check obsidian', 'check my vault', 'check my obsidian vault'}:
                result = self._run('obsidian_read', path=self.config.obsidian_index, max_chars=1000)
                return self.answer('Your configured Obsidian vault and retrieval index are readable. '
                    f"Index: {result['path']}. Use “search my notes for …” or “read note …”.",
                    'Your Obsidian vault and index are readable.')
            if lower in {'read next page', 'next note page'}:
                if not self.current or self.current['next_start'] is None:
                    return self.answer('There is no next note page. Read a note first.')
                return self._read(self.current['path'], self.current['next_start'], self.current['sha256'])
            query = (search[1] if search else read[1]).strip().strip('"\'`').rstrip('.')
            if not query:
                return self.answer('Give me a note title, search phrase or relative Markdown path.')
            if read and ('/' in query or '\\' in query) and query.lower().endswith('.md'):
                self.current = None
                return self._read(query)
            found = self._run('obsidian_search', query=query)
            if read:
                self.current = None
                title = Path(query).stem.casefold()
                matches = [item for item in found['results'] if title in Path(item['path']).stem.casefold()]
                exact = [item for item in matches if Path(item['path']).stem.casefold() == title]
                matches = exact or matches
                if len(matches) == 1 and not found['truncated']:
                    return self._read(matches[0]['path'])
                found = {**found, 'results': matches or found['results']}
            rows = found['results']
            summary = f"Found {len(rows)} matching notes." if rows else 'No matching notes appeared in the vault folders I could check.'
            if found['truncated']:
                summary += ' Search was limited; narrow the phrase for more precise results.'
            if read and rows:
                summary += ' Choose a relative path below with “read note …”; I have not chosen one for you.'
            return self.answer('\n'.join([summary, *(item['path'] for item in rows)]), summary,
                               notes=[{'path': item['path']} for item in rows])
        except (ValueError, OSError) as error:
            # Only our own bounded errors are displayed; native paths/details stay local.
            message = str(error) if type(error) is ValueError else 'The configured vault is unavailable. Check its folder in setup.bat.'
            return self.answer(message)

    def _read(self, path, start=0, revision=None):
        arguments = {'path': path, 'max_chars': 8000, 'start_char': start}
        if revision is not None:
            arguments['expected_sha256'] = revision
        note = self._run('obsidian_read', **arguments)
        self.current = note
        suffix = '\n\nSay “read next page” to continue.' if note['next_start'] is not None else '\n\nEnd of note.'
        heading = f"{note['path']} — characters {start + 1}–{start + len(note['text'])} of {note['total_chars']}\n\n"
        return self.answer(heading + note['text'] + suffix,
            'I have displayed the note on screen.' + (' Say read next page to continue.' if note['next_start'] is not None else ''),
            note={'path': note['path'], 'start_char': start, 'next_start': note['next_start'], 'sha256': note['sha256']})

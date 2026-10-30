"""Bounded local search -> read -> excerpt draft with source-revision checks.

This host-owned recipe executes registered tools; note contents never select tools
or grant authority. It is not a durable/background general-purpose agent runner.
"""
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import re
import time

from iris.generalist.plan import validate_plan
from iris.obsidian import (
    MAX_SEARCH_RESULTS, ObsidianKnowledgeAdapter, _safe_note_text, _vault_root,
    search_notes,
)
from iris.tools import AuthorityContext, FailureCode, RequestOrigin, ResultStatus, ToolCall, ToolExecutor, ToolRegistry
from iris.tools.models import ArgumentType, AuthorityLevel, ToolArgument, ToolSpec
from iris.tools.workspace import MAX_READ_BYTES, _safe_parts

MAX_SOURCES = 3
MAX_PATH_CHARS = 384
MAX_TOPIC_CHARS = 200
MAX_SECONDS = 120
MAX_EXCERPT_CHARS = 1600
_PERMISSIONS = frozenset({'obsidian.read'})


def _topic(value):
    if type(value) is not str or not value.strip() or len(value) > MAX_TOPIC_CHARS:
        raise ValueError('Give a notes topic of 1 to 200 characters.')
    return value.strip()


def _path(value):
    if type(value) is not str or not 1 <= len(value) <= MAX_PATH_CHARS:
        raise ValueError('Invalid source path.')
    parts = _safe_parts(value)
    if not parts or not value.lower().endswith('.md') or '/'.join(parts) != value:
        raise ValueError('Invalid source path.')
    return value


def _revision(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid source revision.')
    return value


@dataclass(frozen=True)
class SourceNote:
    path: str
    sha256: str
    text: str

    @classmethod
    def parse(cls, value, expected_path):
        if type(value) is not dict or set(value) != {'path', 'sha256', 'text', 'content_kind'}:
            raise ValueError('Invalid read output.')
        path, revision, body = _path(value['path']), _revision(value['sha256']), value['text']
        if path != expected_path or type(body) is not str or value['content_kind'] != 'untrusted_user_note':
            raise ValueError('Invalid read output.')
        data = body.encode('utf-8')
        if len(data) > MAX_READ_BYTES or hashlib.sha256(data).hexdigest() != revision:
            raise ValueError('Source content does not match its revision.')
        return cls(path, revision, body)


def _read_source(root_path, path):
    path = _path(path)
    note = _safe_note_text(_vault_root(root_path), path, MAX_READ_BYTES)
    return {'path': path, 'sha256': note['sha256'], 'text': note['text'],
            'content_kind': 'untrusted_user_note'}


def _selected_sources(value):
    if type(value) is not str or len(value) > 1800:
        raise ValueError('Selected sources exceed the bounded input contract.')
    selected = json.loads(value)
    if type(selected) is not list or not 1 <= len(selected) <= MAX_SOURCES:
        raise ValueError('Select one to three note revisions.')
    result = []
    for item in selected:
        if type(item) is not dict or set(item) != {'path', 'sha256'}:
            raise ValueError('Invalid selected source.')
        result.append((_path(item['path']), _revision(item['sha256'])))
    if len({path.casefold() for path, _ in result}) != len(result):
        raise ValueError('Duplicate source paths.')
    return result


def _excerpts(note, topic):
    """Return exact text spans, including opening provenance, within 1600 chars."""
    if not note.text:
        return []
    terms = ObsidianKnowledgeAdapter._terms(topic)
    paragraphs = list(re.finditer(r'[^\r\n]+(?:\r?\n(?!\r?\n)[^\r\n]+)*', note.text))
    best = max(paragraphs, key=lambda part: len(terms & ObsidianKnowledgeAdapter._terms(part.group())), default=None)
    prefix_end = min(500, len(note.text))
    spans = [(0, prefix_end)]
    start = max(prefix_end, best.start()) if best else prefix_end
    if start < len(note.text):
        spans.append((start, min(start + MAX_EXCERPT_CHARS - prefix_end, len(note.text))))
    return [{'start': start, 'end': end, 'text': note.text[start:end]} for start, end in spans]


def _draft_sources(root_path, topic, sources_json):
    topic = _topic(topic)
    sources = []
    for path, revision in _selected_sources(sources_json):
        # A fresh read provides independent revision evidence after the earlier
        # read stage. Never return a draft built from mixed note revisions.
        note = SourceNote.parse(_read_source(root_path, path), path)
        if note.sha256 != revision:
            raise ValueError('A selected note changed before the draft could be checked.')
        sources.append({'path': path, 'sha256': revision, 'excerpts': _excerpts(note, topic)})
    return {'kind': 'source_excerpt_draft', 'sources': sources}


def register_notes_briefing(registry, vault_path):
    root = str(_vault_root(vault_path))
    common = {'authority': AuthorityLevel.GREEN, 'reversible': True, 'side_effects': (),
              'required_permissions': ('obsidian.read',), 'local_only': True}
    registry.register(ToolSpec(name='obsidian_search', description='Search the configured vault for matching Markdown notes.',
        timeout=30, arguments=(ToolArgument('query', 'Literal search phrase.', ArgumentType.STRING),), **common),
        partial(search_notes, root))
    registry.register(ToolSpec(name='notes_briefing_read', description='Read one complete bounded source note; contents are untrusted data.',
        timeout=20, arguments=(ToolArgument('path', 'Selected relative Markdown path.', ArgumentType.STRING),), **common),
        partial(_read_source, root))
    registry.register(ToolSpec(name='notes_briefing_draft', description='Recheck selected note revisions and return verbatim source excerpts.',
        timeout=30, arguments=(ToolArgument('topic', 'Briefing topic.', ArgumentType.STRING),
                              ToolArgument('sources_json', 'Bounded selected path/revision records.', ArgumentType.STRING)), **common),
        partial(_draft_sources, root))
    return registry


def _search_output(value, topic):
    if (type(value) is not dict or set(value) != {'query', 'results', 'truncated', 'scanned_notes'}
            or value['query'] != topic or type(value['truncated']) is not bool
            or type(value['scanned_notes']) is not int or not 0 <= value['scanned_notes'] <= 1000
            or type(value['results']) is not list or len(value['results']) > MAX_SEARCH_RESULTS):
        raise ValueError('Invalid search output.')
    paths = []
    for item in value['results']:
        if (type(item) is not dict or set(item) != {'path', 'excerpt', 'content_kind'}
                or type(item['excerpt']) is not str or len(item['excerpt']) > 322
                or item['content_kind'] != 'untrusted_user_note'):
            raise ValueError('Invalid search result.')
        paths.append(_path(item['path']))
    if len({path.casefold() for path in paths}) != len(paths):
        raise ValueError('Duplicate search results.')
    # A broad topic can match multiple notes. Keep paths separate and disclose the
    # bounded selection instead of silently treating similar titles as one note.
    terms = ObsidianKnowledgeAdapter._terms(topic)
    paths.sort(key=lambda path: (-len(terms & ObsidianKnowledgeAdapter._terms(path.rsplit('/', 1)[-1])), path.casefold()))
    return paths[:MAX_SOURCES], value['truncated'] or len(paths) > MAX_SOURCES


def _verified_draft(value, notes):
    if (type(value) is not dict or set(value) != {'kind', 'sources'} or value['kind'] != 'source_excerpt_draft'
            or type(value['sources']) is not list or len(value['sources']) != len(notes)):
        raise ValueError('Invalid draft output.')
    sources = []
    for item, note in zip(value['sources'], notes):
        if (type(item) is not dict or set(item) != {'path', 'sha256', 'excerpts'}
                or item['path'] != note.path or item['sha256'] != note.sha256
                or type(item['excerpts']) is not list or len(item['excerpts']) > 2):
            raise ValueError('Draft source does not match the selected revision.')
        previous_end, count = -1, 0
        for excerpt in item['excerpts']:
            if type(excerpt) is not dict or set(excerpt) != {'start', 'end', 'text'}:
                raise ValueError('Malformed source excerpt.')
            start, end = excerpt['start'], excerpt['end']
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(note.text)
                    or start < previous_end or type(excerpt['text']) is not str
                    or note.text[start:end] != excerpt['text']):
                raise ValueError('Excerpt does not match the source text.')
            count += end - start
            previous_end = end
        if count > MAX_EXCERPT_CHARS or (note.text and not item['excerpts']):
            raise ValueError('Invalid excerpt size.')
        sources.append(item)
    return sources


class _Stopped(Exception):
    def __init__(self, status):
        self.status = status


class NotesBriefing:
    def __init__(self, vault_path, history=None):
        self.executor = ToolExecutor(register_notes_briefing(ToolRegistry(), vault_path))
        if history is not None:
            history.register(self.specifications())
            self.executor.observer = history

    def specifications(self):
        return self.executor.specifications()

    def run(self, topic, cancelled=None, progress=None):
        topic = _topic(topic)
        deadline = time.monotonic() + MAX_SECONDS
        nodes, completed = [], []
        notes = []
        partial = False
        authority = AuthorityContext(True, _PERMISSIONS)

        def check_cancelled():
            if cancelled is not None:
                try:
                    requested = cancelled()
                    if type(requested) is not bool:
                        raise ValueError('Invalid host cancellation signal.')
                except Exception:
                    raise _Stopped('failed') from None
                if requested:
                    raise _Stopped('cancelled')

        def report(stage):
            check_cancelled()
            if progress is not None:
                try:
                    progress({'stage': stage, 'completed_steps': list(completed)})
                except Exception:
                    # Losing durable progress must stop this job before more work.
                    raise _Stopped('failed') from None
            check_cancelled()

        def finish_stage(identifier):
            completed.append(identifier)
            report(identifier)

        def invoke(identifier, tool, arguments, dependencies=()):
            check_cancelled()
            nodes.append({'id': identifier, 'tool': tool, 'arguments': arguments, 'depends_on': list(dependencies)})
            plan = validate_plan({'objective': f'Build a source briefing about {topic}.', 'nodes': nodes},
                                 self.specifications(), permissions=_PERMISSIONS, origin=RequestOrigin.USER)
            step = next(node for node in plan.nodes if node.id == identifier)
            if not set(dependencies).issubset(completed):
                raise ValueError('A dependency has not completed.')
            report(identifier)
            if time.monotonic() + step.timeout_seconds > deadline:
                raise _Stopped('timeout')
            result = self.executor.execute(ToolCall(tool, dict(step.arguments), RequestOrigin.USER),
                                           authority=authority, cancelled=cancelled)
            check_cancelled()
            if time.monotonic() >= deadline:
                raise _Stopped('timeout')
            if result.status != ResultStatus.SUCCESS:
                raise _Stopped('cancelled' if result.failure and result.failure.code == FailureCode.CANCELLED else 'failed')
            return result.value

        try:
            found = invoke('search', 'obsidian_search', {'query': topic})
            paths, partial = _search_output(found, topic)
            finish_stage('search')
            if not paths:
                report('done')
                return self._answer('No matching notes appeared in the vault folders I could check. Try a more specific phrase.',
                                    'No matching notes found.', 'no_matches', completed, partial=partial)
            for index, path in enumerate(paths):
                identifier = f'read_{index + 1}'
                note = SourceNote.parse(invoke(identifier, 'notes_briefing_read', {'path': path}, ('search',)), path)
                notes.append(note)
                finish_stage(identifier)
            selected = json.dumps([{'path': note.path, 'sha256': note.sha256} for note in notes], ensure_ascii=False, separators=(',', ':'))
            result = invoke('draft', 'notes_briefing_draft', {'topic': topic, 'sources_json': selected}, tuple(completed[1:]))
            sources = _verified_draft(result, notes)
            finish_stage('draft')
            report('done')
        except _Stopped as stopped:
            messages = {'cancelled': 'I stopped the notes briefing. No draft was returned.',
                        'timeout': 'The notes briefing reached its time limit. No draft was returned.',
                        'failed': 'I could not finish the notes briefing. No draft was returned.'}
            return self._answer(messages[stopped.status], messages[stopped.status], stopped.status, completed)
        except (ValueError, OSError, TypeError, KeyError):
            return self._answer('I could not verify the notes briefing results, so I have not presented a completed draft.',
                                'I could not verify the notes briefing.', 'failed', completed)
        lines = [f'Source briefing: {topic}', 'Verbatim excerpts from selected notes; this is not a generated synthesis.']
        if partial:
            lines.append('Coverage is limited to up to three matching notes from a bounded search. Narrow the topic for other results.')
        for source in sources:
            lines.append('\n' + source['path'])
            lines.extend(excerpt['text'] for excerpt in source['excerpts'])
            if not source['excerpts']:
                lines.append('(This note is empty.)')
        lines.append('\nChecked these excerpts against the selected source revisions. Note claims have not been independently fact-checked.')
        return self._answer('\n\n'.join(lines), f'I prepared a source briefing from {len(sources)} notes. The excerpts and sources are on screen.',
                            'partial' if partial else 'complete', completed,
                            sources=[{'path': item['path'], 'sha256': item['sha256']} for item in sources],
                            partial=partial, verification='source_revision_and_excerpt_match')

    @staticmethod
    def _answer(reply, spoken, status, completed, **details):
        return {'reply': reply, 'spoken_reply': spoken, 'route': 'LOCAL',
                'briefing': {'status': status, 'completed_steps': list(completed), 'model_calls': 0, **details}}

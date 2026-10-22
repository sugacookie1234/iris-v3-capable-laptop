from datetime import datetime, timezone
import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from iris.briefing import BRIEFING_PERMISSION, build_briefing, register_briefing, render_briefing
from iris.calendar import CalendarSource
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem, MemorySensitivity
from iris.memory.store import MemoryStore
from iris.tasks.store import TaskStore
from iris.terminal import chat, create_brain, load_config
from iris.tools import AuthorityContext, RequestOrigin, ToolCall, ToolExecutor, ToolRegistry


def ics(*entries):
    return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + ''.join(
        'BEGIN:VEVENT\r\n' + item.replace('\n', '\r\n') + '\r\nEND:VEVENT\r\n' for item in entries
    ) + 'END:VCALENDAR\r\n'


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.task_path = root / 'tasks.sqlite3'
        self.memory_path = root / 'memory.sqlite3'
        self.calendar_path = root / 'today.ics'
        self.root = root
        self.at = datetime(2026, 9, 14, 16, tzinfo=timezone.utc)
        with TaskStore(self.task_path) as _:
            pass
        with MemoryStore(self.memory_path) as _:
            pass

    def source(self):
        return CalendarSource(str(self.root), 'today.ics', 'America/Toronto')

    def test_empty_data_and_distinct_sections(self):
        result = build_briefing(task_path=self.task_path, memory_path=self.memory_path,
                                zone='America/Toronto', at=self.at)
        self.assertEqual(result['facts']['events'], [])
        self.assertEqual(result['facts']['permitted_memories'], [])
        self.assertEqual(result['deadlines'], [])
        self.assertEqual(result['goal_risks'], [])
        self.assertTrue(result['facts']['calendar_configured'] is False)
        rendered = render_briefing(result)
        self.assertLess(rendered.index('Facts'), rendered.index('Deadlines'))
        self.assertLess(rendered.index('Deadlines'), rendered.index('Suggestions'))
        self.assertIn('Calendar is not configured', rendered)
        with self.calendar_path.open('w', newline='') as handle:
            handle.write(ics())
        result = build_briefing(task_path=self.task_path, calendar=self.source(),
                                memory_path=self.memory_path, at=self.at)
        self.assertTrue(result['facts']['calendar_configured'])
        self.assertIn('No calendar events today', render_briefing(result))

    def test_overdue_and_upcoming_tasks_only(self):
        with TaskStore(self.task_path) as store:
            overdue = store.create('Overdue report', due_at='2026-09-13T23:00:00Z', priority='high')
            today = store.create('Today call', due_at='2026-09-14T18:00:00Z')
            upcoming = store.create('Friday review', due_at='2026-09-18T18:00:00Z')
            store.create('Far away', due_at='2026-10-20T18:00:00Z')
            store.create('Undated')
            done = store.create('Completed', due_at='2026-09-14T17:00:00Z')
            store.complete(done.id)
            original_revisions = {task.id: len(store.revisions(task.id)) for task in store.list()}
        result = build_briefing(task_path=self.task_path, memory_path=self.memory_path,
                                zone='America/Toronto', at=self.at)
        self.assertEqual([task['title'] for task in result['deadlines']],
                         ['Overdue report', 'Today call', 'Friday review'])
        self.assertEqual([task['status'] for task in result['deadlines']],
                         ['overdue', 'due_today', 'upcoming'])
        self.assertTrue(any('overdue tasks' in s for s in result['suggestions']))
        with TaskStore(self.task_path) as store:
            self.assertEqual({task.id: len(store.revisions(task.id)) for task in store.list()}, original_revisions)
            self.assertEqual(store.fetch(overdue.id).status, 'open')

    def test_calendar_conflicts_are_suggestions(self):
        self.calendar_path.write_text(ics(
            'UID:a\nDTSTART;TZID=America/Toronto:20260914T100000\nDTEND;TZID=America/Toronto:20260914T110000\nSUMMARY:Planning',
            'UID:b\nDTSTART;TZID=America/Toronto:20260914T103000\nDTEND;TZID=America/Toronto:20260914T113000\nSUMMARY:Review',
            'UID:c\nDTSTART;TZID=America/Toronto:20260914T113000\nDTEND;TZID=America/Toronto:20260914T123000\nSUMMARY:Adjacent'), newline="")
        result = build_briefing(task_path=self.task_path, calendar=self.source(),
                                memory_path=self.memory_path, at=self.at)
        self.assertEqual(len(result['facts']['events']), 3)
        self.assertEqual(len(result['suggestions']), 1)
        self.assertIn('Planning', result['suggestions'][0])
        self.assertIn('Review', result['suggestions'][0])
        self.assertNotIn('Adjacent', result['suggestions'][0])

    def test_timezone_boundaries_use_local_day_and_seven_day_horizon(self):
        self.calendar_path.write_text(ics(
            'UID:before\nDTSTART:20260914T035959Z\nSUMMARY:Before day',
            'UID:midnight\nDTSTART:20260914T040000Z\nSUMMARY:At midnight',
            'UID:nextmidnight\nDTSTART:20260915T040000Z\nSUMMARY:Next midnight'), newline="")
        with TaskStore(self.task_path) as store:
            before = store.create('Due before local day', due_at='2026-09-14T03:59:59Z')
            boundary = store.create('Due at local midnight', due_at='2026-09-14T04:00:00Z')
            final = store.create('Due on seventh day', due_at='2026-09-22T03:59:59Z')
            store.create('Outside window', due_at='2026-09-22T04:00:00Z')
        result = build_briefing(task_path=self.task_path, calendar=self.source(),
                                memory_path=self.memory_path, zone='America/Toronto', at=self.at)
        self.assertEqual([e['title'] for e in result['facts']['events']], ['At midnight'])
        self.assertEqual({t['id'] for t in result['deadlines']}, {before.id, boundary.id, final.id})

    def test_only_relevant_confirmed_normal_memories_with_budget(self):
        with MemoryStore(self.memory_path) as memories:
            # Mirror the ordinary same-second insertion case so this test
            # covers ranking ties instead of depending on wall-clock timing.
            stamp = '2026-09-01T12:00:00+00:00'
            def insert(summary, sensitivity='normal', confirmation='confirmed', category='goal'):
                return memories.insert(MemoryItem(
                    MemoryCategory(category), 'user', 'briefing', summary, summary, 'test',
                    sensitivity=MemorySensitivity(sensitivity), confirmation=MemoryConfirmation(confirmation),
                    created_at=stamp, updated_at=stamp))
            allowed = insert('Project Atlas delivery matters today')
            insert('Private medical appointment today', 'sensitive', 'confirmed')
            insert('Restricted secret deadline today', 'restricted', 'confirmed')
            insert('Unconfirmed task preference today', 'normal', 'pending')
            insert('Unrelated favorite color is green', 'normal', 'confirmed', 'preference')
            for i in range(12):
                insert(f'Atlas project commitment item {i}')
        results = [build_briefing(task_path=self.task_path, memory_path=self.memory_path,
                                  at=self.at)['facts']['permitted_memories'] for _ in range(2)]
        self.assertEqual(results[0], results[1])
        rendered = '\n'.join(results[0])
        self.assertIn(allowed.summary, rendered)
        for secret in ('Private medical', 'Restricted secret', 'Unconfirmed task', 'favorite color'):
            self.assertNotIn(secret, rendered)
        self.assertLessEqual(len(results[0]), 8)
        self.assertLessEqual(sum(map(len, results[0])), 4000)

    def test_green_tool_terminal_and_memory_db_is_read_only(self):
        self.calendar_path.write_text(ics('UID:a\nDTSTART:20260914T170000Z\nSUMMARY:Event'), newline="")
        registry = register_briefing(ToolRegistry(), task_path=self.task_path,
                                     calendar=self.source(), memory_path=self.memory_path)
        spec = registry.specifications()[0]
        self.assertEqual(spec.authority, 'GREEN')
        self.assertEqual(spec.side_effects, ())
        executor = ToolExecutor(registry)
        result = executor.execute(ToolCall('daily_briefing', origin=RequestOrigin.USER),
                                  authority=AuthorityContext(True, frozenset({BRIEFING_PERMISSION})))
        self.assertIsNone(result.failure)
        denied = executor.execute(ToolCall('daily_briefing', origin=RequestOrigin.MEMORY),
                                  authority=AuthorityContext(True, frozenset({BRIEFING_PERMISSION})))
        self.assertEqual(denied.failure.code, 'authority_denied')
        brain = Mock(_tool_executor=executor)
        with patch('builtins.input', side_effect=['/briefing', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as output:
            chat(brain)
        brain.respond.assert_not_called()
        for heading in ('Facts', 'Deadlines', 'Suggestions'):
            self.assertIn(heading, output.getvalue())
        self.assertNotIn('medical', output.getvalue())

    def test_natural_briefing_does_not_attach_sensitive_general_memory_context(self):
        self.calendar_path.write_text(ics('UID:a\nDTSTART:20260914T170000Z\nSUMMARY:Event'), newline="")
        with MemoryStore(self.memory_path) as memories:
            memories.insert(MemoryItem(MemoryCategory.PROFILE, 'user', 'health', 'Private medical fact',
                                       'Private medical fact', 'test',
                                       sensitivity=MemorySensitivity.SENSITIVE,
                                       confirmation=MemoryConfirmation.CONFIRMED))
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_TASKS_PATH': str(self.task_path), 'IRIS_CALENDAR_PATH': 'today.ics',
                              'IRIS_CALENDAR_ROOT': str(self.root), 'IRIS_MEMORY_PATH': str(self.memory_path)})
        brain = create_brain(config)
        from iris.brain.llm import LLMResponse, LLMToolCall
        proposal = LLMResponse('', 'test', 'model', tool_calls=(LLMToolCall('brief', 'daily_briefing', {}),))
        answer = LLMResponse('Done', 'test', 'model')
        with patch.object(brain._llm_registry, 'generate', side_effect=(proposal, answer)) as generate:
            brain.respond('Give me my daily briefing')
        self.assertNotIn('Private medical fact', generate.call_args_list[0].kwargs["messages"][0].content)
        self.assertNotIn('Private medical fact', generate.call_args_list[1].kwargs["messages"][-1].content)

    def test_natural_language_briefing_proposal_executes_only_green_registered_tool(self):
        self.calendar_path.write_text(ics('UID:a\nDTSTART:20260914T170000Z\nSUMMARY:Event'), newline="")
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_TASKS_PATH': str(self.task_path), 'IRIS_CALENDAR_PATH': 'today.ics',
                              'IRIS_CALENDAR_ROOT': str(self.root), 'IRIS_MEMORY_PATH': str(self.memory_path)})
        brain = create_brain(config)
        from iris.brain.llm import LLMResponse, LLMToolCall
        proposals = [LLMResponse('', 'test', 'model', tool_calls=(LLMToolCall('brief', 'daily_briefing', {}),)),
                     LLMResponse('Facts / Deadlines / Suggestions', 'test', 'model')]
        with patch.object(brain._llm_registry, 'generate', side_effect=proposals):
            result = brain.respond('Give me my daily briefing')
        self.assertIsNone(result.tool_result.failure)
        self.assertEqual(result.tool_result.plan.spec.authority, 'GREEN')
        self.assertIn('permitted_memories', result.tool_result.value['facts'])


if __name__ == '__main__':
    unittest.main()

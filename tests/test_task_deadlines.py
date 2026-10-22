from datetime import datetime, timezone
import io
import tempfile
import unittest
from unittest.mock import patch

from iris.tasks.deadlines import parse_deadline, prepare_creation, local_zone
from iris.tasks.models import Task
from iris.tasks.store import TaskStore
from iris.tasks.tools import register_tasks, TASK_PERMISSIONS
from iris.tools import Approval, AuthorityContext, ToolCall, ToolExecutor
from iris.tools.registry import ToolRegistry
from iris.terminal import _handle_task_command, create_brain, load_config


class DeadlineTests(unittest.TestCase):
    def parse(self, text, zone='America/Toronto', at=None):
        return parse_deadline(text, zone=zone, at=at or datetime(2026, 9, 12, 16, tzinfo=timezone.utc))

    def test_relative_dates(self):
        for phrase, expected in (
            ('today', '2026-09-13T03:59:59+00:00'),
            ('tomorrow', '2026-09-14T03:59:59+00:00'),
            ('tmmr', '2026-09-14T03:59:59+00:00'),
            ('next Monday', '2026-09-15T03:59:59+00:00'),
            ('Friday at 6 PM', '2026-09-18T22:00:00+00:00'),
        ):
            with self.subTest(phrase=phrase):
                parsed = self.parse('Submit report ' + phrase)
                self.assertEqual(parsed.title, 'Submit report')
                self.assertEqual(parsed.due_at, expected)
                self.assertIn('America/Toronto', parsed.explanation)
        self.assertIn('Date-only policy', self.parse('Report today').explanation)
        self.assertEqual(self.parse('today submit report').title, 'submit report')
        self.assertEqual(self.parse('Submit report by tomorrow').title, 'Submit report')

    def test_iso_and_timezone_conversion(self):
        for phrase, expected in (
            ('2026-09-14', '2026-09-15T03:59:59+00:00'),
            ('2026-09-14 18:00', '2026-09-14T22:00:00+00:00'),
            ('2026-09-14T18:00:00-04:00', '2026-09-14T22:00:00+00:00'),
            ('2026-09-14T18:00:00Z', '2026-09-14T18:00:00+00:00'),
            ('2026-01-14 18:00', '2026-01-14T23:00:00+00:00'),
            ('2026-09-14 at 12 AM', '2026-09-14T04:00:00+00:00'),
            ('2026-09-14 at 12 PM', '2026-09-14T16:00:00+00:00'),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.parse('Report ' + phrase).due_at, expected)
        self.assertEqual(self.parse('Report 2026-09-14 18:00', 'Asia/Tokyo').due_at, '2026-09-14T09:00:00+00:00')
        at = datetime(2026, 9, 13, 2, tzinfo=timezone.utc)
        self.assertEqual(self.parse('Report today', at=at).due_at, '2026-09-13T03:59:59+00:00')

    def test_invalid_ambiguous_and_dst(self):
        for phrase in ('2026-02-30', '2026-13-01', 'tomorrow at 6', 'Friday at 25:00',
                       'Friday at 13 PM', 'today or tomorrow', 'tomorrow morning', 'next week',
                       '09/14/2026', '2026-03-08 02:30', '2026-11-01 01:30',
                       'Friday at 6 PM EST', 'tomorrow 6ish', "tomorrow's newspaper", 'Friday at 18:99', 'tomorrow at noon'):
            with self.subTest(phrase=phrase):
                original = 'Report ' + phrase
                parsed = self.parse(original)
                self.assertIsNone(parsed.due_at)
                self.assertEqual(parsed.title, original)
                self.assertIn('No deadline set', parsed.explanation)
        self.assertIsNotNone(self.parse('Report 2026-11-01T01:30:00-04:00').due_at)
        self.assertIsNone(self.parse('Buy milk').due_at)

    def test_configuration_and_conflicting_metadata(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(local_zone().key, 'America/Toronto')
        with self.assertRaises(ValueError):
            local_zone('Invalid/Timezone')
        args, explanation = prepare_creation({'title': 'Report tomorrow', 'due_at': '2026-09-14'})
        self.assertNotIn('due_at', args)
        self.assertIn('both title and due metadata', explanation)
        args, _ = prepare_creation({'title': 'Report', 'due_at': '2026-09-14 18:00'}, 'America/Toronto')
        self.assertEqual(args['due_at'], '2026-09-14T22:00:00+00:00')

    def test_confirmation_persistence_listing_and_compatibility(self):
        with tempfile.TemporaryDirectory() as directory, TaskStore(directory + '/tasks.db') as store:
            old = store.create('Existing tomorrow', due_at='2026-09-14T18:00:00+00:00')
            executor = ToolExecutor(register_tasks(ToolRegistry(), store.path, 'America/Toronto'))
            plans = []
            def approve(plan):
                plans.append(plan)
                return Approval(plan.id, True)
            result = executor.execute(ToolCall('tasks_create', {'title': 'Report 2026-09-14 18:00'}),
                                      authority=AuthorityContext(True, TASK_PERMISSIONS), approve=approve)
            self.assertIsNone(result.failure)
            self.assertIn('2026-09-14T18:00:00-04:00', plans[0].confirmation_summary)
            self.assertEqual(dict(plans[0].arguments)['due_at'], '2026-09-14T22:00:00+00:00')
            task = store.fetch(result.value['id'])
            self.assertEqual(task.title, 'Report')
            self.assertTrue(task.is_overdue('2026-09-14T22:00:01Z'))
            self.assertFalse(task.is_overdue('2026-09-14T21:59:59Z'))
            self.assertEqual(store.revisions(task.id)[0].snapshot, task)
            self.assertEqual(store.fetch(old.id), old)
            self.assertEqual(store.revisions(old.id)[0].snapshot.title, 'Existing tomorrow')
            with patch('sys.stdout', new_callable=io.StringIO) as out:
                _handle_task_command('/tasks', store, 'America/Toronto')
            self.assertIn('2026-09-14T18:00:00-04:00', out.getvalue())
            with patch('builtins.input', return_value='n'), patch('sys.stdout', new_callable=io.StringIO) as out:
                _handle_task_command('/add-task Another tomorrow', store, 'America/Toronto')
            self.assertIn('Date-only policy', out.getvalue())
            self.assertEqual(len(store.list()), 2)
            with patch('builtins.input', return_value='yes'), patch('sys.stdout', new_callable=io.StringIO) as out:
                _handle_task_command('/add-task Ambiguous tomorrow at 6', store, 'America/Toronto')
            self.assertIn('No deadline set', out.getvalue())
            self.assertIsNone(store.list('Ambiguous')[0].due_at)

    def test_model_cannot_invent_deadline(self):
        from iris.brain.llm import LLMResponse, LLMToolCall
        with tempfile.TemporaryDirectory() as directory:
            config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                                  'IRIS_TASKS_PATH': directory + '/tasks.db', 'IRIS_TIMEZONE': 'America/Toronto'})
            brain = create_brain(config)
            proposal = LLMResponse('', 'terminal', 'test', tool_calls=(LLMToolCall('1', 'tasks_create',
                                   {'title': 'Report', 'due_at': '2099-01-01T00:00:00Z'}),))
            final = LLMResponse('Done', 'terminal', 'test')
            for request, expected in (('Add a task to submit report 2026-09-14 18:00', '2026-09-14T22:00:00+00:00'),
                                      ('Add a task to buy milk', None)):
                with patch.object(brain._llm_registry, 'generate', side_effect=[proposal, final]), patch('builtins.input', return_value='yes'), patch('sys.stdout', new_callable=io.StringIO):
                    result = brain.respond(request)
                self.assertEqual(result.tool_result.value['due_at'], expected)


if __name__ == '__main__':
    unittest.main()

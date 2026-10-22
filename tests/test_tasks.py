import io
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.tasks import Task, TaskStore, TaskStatus
from iris.tasks.tools import TASK_PERMISSIONS, register_tasks
from iris.terminal import chat, create_brain, load_config
from iris.tools import Approval, AuthorityContext, RequestOrigin, ToolCall, ToolExecutor
from iris.tools.models import FailureCode, ResultStatus
from iris.tools.registry import ToolRegistry


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name + '/tasks.sqlite3'
        self.store = TaskStore(self.path)
        self.addCleanup(self.store.close)
        self.executor = ToolExecutor(register_tasks(ToolRegistry(), self.path))
        self.authority = AuthorityContext(True, TASK_PERMISSIONS)

    def execute(self, name, args, answer=None, origin=RequestOrigin.USER):
        approve = None if answer is None else lambda plan: Approval(plan.id, answer)
        return self.executor.execute(ToolCall('tasks_' + name, args, origin), authority=self.authority, approve=approve)

    def test_validation(self):
        for arguments in ({'title': ''}, {'title': ' '}, {'title': 3}, {'title': 'x'*501},
                          {'title': 'ok', 'notes': None}, {'title': 'ok', 'priority': 'urgent'},
                          {'title': 'ok', 'due_at': 'tomorrow'}, {'title': 'ok', 'due_at': '2026-09-12'},
                          {'title': 'ok', 'revision': True}):
            with self.subTest(arguments=arguments), self.assertRaises((ValueError, TypeError)):
                Task(**arguments)
        self.assertEqual(Task('ok', due_at='2026-09-12T12:00:00-04:00').due_at, '2026-09-12T16:00:00+00:00')

    def test_persistence_search_revisions_and_delete(self):
        task = self.store.create("Buy milk", notes="Oat", priority="high")
        with TaskStore(self.path) as other:
            self.assertEqual(other.fetch(task.id), task)
            self.assertEqual(other.list('OAT'), (task,))
            self.assertEqual(other.list('%'), ())
            completed = other.complete(task.id)
            self.assertEqual(completed.revision, 2)
            self.assertEqual(other.complete(task.id), completed)
            other.delete(task.id)
        self.assertEqual(self.store.list(), ())
        revisions = self.store.revisions(task.id)
        self.assertEqual([r.action for r in revisions], ['created', 'completed', 'deleted'])
        self.assertEqual(revisions[0].snapshot.status, TaskStatus.OPEN)
        with self.assertRaises(ValueError):
            self.store.complete(task.id)

    def test_overdue(self):
        at = '2026-09-12T12:00:00+00:00'
        self.assertTrue(Task('past', due_at='2026-09-12T11:00:00+00:00').is_overdue(at))
        for task in (Task('none'), Task('equal', due_at=at),
                     Task('future', due_at='2027-01-01T00:00:00Z'),
                     Task('done', due_at='2020-01-01T00:00:00Z', status=TaskStatus.COMPLETED)):
            self.assertFalse(task.is_overdue(at))
        self.store.create('past', due_at='2020-01-01T00:00:00Z')
        self.assertTrue(self.execute('list', {}).value[0]['overdue'])

    def test_confirmation_and_origin(self):
        for origin in (RequestOrigin.USER, RequestOrigin.MODEL):
            for answer in (None, False):
                self.assertEqual(self.execute('create', {'title': 'test'}, answer, origin).status, ResultStatus.FAILED)
        self.assertFalse(self.store.list())
        result = self.execute('create', {'title': 'test'}, True)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        identifier = result.value['id']
        for operation in ('complete', 'delete'):
            for answer in (None, False):
                self.assertEqual(self.execute(operation, {'identifier': identifier}, answer).status, ResultStatus.FAILED)
            self.assertEqual(self.store.fetch(identifier).status, TaskStatus.OPEN)
        self.assertEqual(self.execute('list', {}).status, ResultStatus.SUCCESS)
        self.assertEqual(self.execute('list', {}, True, RequestOrigin.MEMORY).failure.code, FailureCode.AUTHORITY_DENIED)
        self.assertEqual(self.execute('complete', {'identifier': identifier}, True).status, ResultStatus.SUCCESS)
        self.assertEqual(self.execute('delete', {'identifier': identifier}, True).status, ResultStatus.SUCCESS)

    def test_terminal_commands_and_malformed_ids(self):
        brain = Mock()
        task = self.store.create('past', due_at='2020-01-01T00:00:00Z')
        inputs = ['/add-task rejected', 'n', '/add-task kept | priority=high', 'yes',
                  '/add-task ', '/complete-task nope', '/delete-task 1; rm -rf /',
                  '/complete-task', '/delete-task 00000000-0000-0000-0000-000000000000',
                  '/tasks', f'/complete-task {task.id}', 'n', f'/delete-task {task.id}', 'n', '/exit']
        with patch('builtins.input', side_effect=inputs), patch('sys.stdout', new_callable=io.StringIO) as out:
            chat(brain, task_store=self.store)
        self.assertIn('OVERDUE', out.getvalue())
        self.assertIn('Task rejected', out.getvalue())
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(self.store.fetch(task.id).status, TaskStatus.OPEN)
        brain.respond.assert_not_called()

    def test_bad_ids_and_untrusted_proposals_cannot_mutate(self):
        task = self.store.create('untouched')
        for identifier in ('', '1', '../tasks', task.id.upper(), "' OR 1=1 --"):
            with self.subTest(identifier=identifier):
                result = self.execute('delete', {'identifier': identifier}, True)
                self.assertEqual(result.status, ResultStatus.FAILED)
        for origin in (RequestOrigin.MEMORY, RequestOrigin.EXTERNAL):
            self.assertEqual(self.execute('delete', {'identifier': task.id}, True, origin).failure.code,
                             FailureCode.AUTHORITY_DENIED)
        stale = self.executor.execute(ToolCall('tasks_delete', {'identifier': task.id}),
                                      authority=self.authority, approve=lambda p: Approval('wrong-plan', True))
        self.assertEqual(stale.failure.code, FailureCode.APPROVAL_REJECTED)
        self.assertEqual(self.store.fetch(task.id).status, TaskStatus.OPEN)
        self.assertEqual(len(self.store.revisions(task.id)), 1)

    def test_memory_and_history_remain_separate(self):
        from iris.memory.store import MemoryStore
        with MemoryStore(self.tmp.name + '/memory.sqlite3') as memories:
            brain = Mock()
            brain.respond.return_value = Mock(text='hello')
            with patch('builtins.input', side_effect=['/add-task private task', 'yes', 'hello', '/exit']), patch('sys.stdout', new_callable=io.StringIO):
                chat(brain, memory_store=memories, task_store=self.store)
            self.assertFalse(memories.current())
            self.assertEqual(brain.respond.call_args.kwargs['history'], ())
            self.assertEqual(len(self.store.list()), 1)

    def test_negative_and_unrelated_requests_offer_no_task_tools(self):
        from iris.tasks.tools import is_task_request
        self.assertFalse(is_task_request("Do not delete my tasks"))
        self.assertFalse(is_task_request("I enjoy tasks"))
        self.assertTrue(is_task_request("Show my reminders"))
        self.assertTrue(is_task_request("Remind me to submit the report"))

    def test_model_proposal_uses_executor(self):
        from iris.brain.llm import LLMResponse, LLMToolCall
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test', 'IRIS_TASKS_PATH': self.path})
        brain = create_brain(config)
        proposal = LLMResponse('', 'terminal', 'test', tool_calls=(LLMToolCall('1', 'tasks_create', {'title': 'Proposed'}),))
        final = LLMResponse('Done', 'terminal', 'test')
        with patch.object(brain._llm_registry, 'generate', side_effect=[proposal, final]), patch('builtins.input', return_value='n'), patch('sys.stdout', new_callable=io.StringIO):
            result = brain.respond('Add a task to buy milk')
        self.assertEqual(result.tool_result.failure.code, FailureCode.APPROVAL_REJECTED)
        self.assertFalse(self.store.list())
        with patch.object(brain._llm_registry, 'generate', side_effect=[proposal, final]), patch('builtins.input', return_value='yes'), patch('sys.stdout', new_callable=io.StringIO):
            result = brain.respond('Add a task to buy milk')
        self.assertEqual(result.tool_result.status, ResultStatus.SUCCESS)
        self.assertEqual(len(self.store.list()), 1)


if __name__ == '__main__':
    unittest.main()

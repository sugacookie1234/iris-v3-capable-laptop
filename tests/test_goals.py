import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from iris.briefing import build_briefing, render_briefing
from iris.goals import Goal, GoalCategory, GoalPriority, GoalStatus, GoalStore
from iris.goals.tools import GOAL_PERMISSIONS, register_goals
from iris.tasks.models import Task
from iris.tasks.store import TaskStore
from iris.tasks.tools import TASK_PERMISSIONS, register_tasks
from iris.terminal import chat, create_brain, load_config
from iris.tools import Approval, AuthorityContext, RequestOrigin, ResultStatus, ToolCall, ToolExecutor
from iris.tools.registry import ToolRegistry


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.goals_path = root / 'goals.sqlite3'
        self.tasks_path = root / 'tasks.sqlite3'
        self.memory_path = root / 'memory.sqlite3'

    def test_validation_and_typed_persistence_revisions(self):
        for fields in (
            {'title': ''}, {'title': 'x' * 201}, {'title': 'ok', 'description': 'x' * 4001},
            {'title': 'ok', 'category': 'random'}, {'title': 'ok', 'priority': 'urgent'},
            {'title': 'ok', 'status': 'mystery'}, {'title': 'ok', 'target_date': '2026-02-30'},
            {'title': 'ok', 'target_date': '2026-01-01T00:00:00Z'}, {'title': 'ok', 'progress': -1},
            {'title': 'ok', 'progress': 101}, {'title': 'ok', 'progress': True},
            {'title': 'ok', 'status': 'completed'},
        ):
            with self.subTest(fields=fields), self.assertRaises((ValueError, TypeError)):
                Goal(**fields)
        with GoalStore(self.goals_path) as store:
            goal = store.create('Ship IRIS', 'Release goal', 'project', 'high', '2026-12-31', 20)
            self.assertEqual(goal.category, GoalCategory.PROJECT)
            self.assertEqual(goal.priority, GoalPriority.HIGH)
            updated = store.update(goal.id, {'progress': 75, 'description': 'Release v2'})
            self.assertEqual(updated.progress, 75)
            self.assertEqual(updated.revision, 2)
            completed = store.complete(goal.id)
            self.assertEqual((completed.status, completed.progress, completed.revision),
                             (GoalStatus.COMPLETED, 100, 3))
            self.assertEqual(store.complete(goal.id), completed)
            with self.assertRaises(ValueError):
                store.update(goal.id, {'progress': 90})
            self.assertEqual([r.action for r in store.revisions(goal.id)], ['created', 'updated', 'completed'])
        with GoalStore(self.goals_path, read_only=True) as readonly:
            self.assertEqual(readonly.fetch(goal.id), completed)

    def test_updates_clear_target_pause_activate_and_reject_invalid_changes(self):
        with GoalStore(self.goals_path) as store:
            goal = store.create('Learn French', target_date='2026-12-31')
            with self.assertRaises(ValueError):
                store.update(goal.id, {})
            with self.assertRaises(ValueError):
                store.update(goal.id, {'status': 'completed'})
            with self.assertRaises(ValueError):
                store.update(goal.id, {'wat': 1})
            with self.assertRaises(ValueError):
                store.update(goal.id, {'progress': 101})
            paused = store.update(goal.id, {'status': 'paused', 'target_date': None})
            self.assertEqual(paused.status, GoalStatus.PAUSED)
            self.assertIsNone(paused.target_date)
            active = store.update(goal.id, {'status': 'active', 'progress': 25})
            self.assertEqual(active.progress, 25)

    def test_goal_tools_green_yellow_and_authority(self):
        registry = register_goals(ToolRegistry(), self.goals_path)
        executor = ToolExecutor(registry)
        authority = AuthorityContext(True, GOAL_PERMISSIONS)
        list_result = executor.execute(ToolCall('goals_list', origin=RequestOrigin.USER), authority=authority)
        self.assertEqual(list_result.status, ResultStatus.SUCCESS)
        self.assertEqual(list_result.plan.spec.authority, 'GREEN')
        self.assertFalse(Path(self.goals_path).exists())
        create = executor.execute(ToolCall('goals_create', {'title': 'Learn Python'}, RequestOrigin.USER), authority=authority)
        self.assertEqual(create.failure.code, 'approval_required')
        self.assertFalse(Path(self.goals_path).exists())
        denied = executor.execute(ToolCall('goals_create', {'title': 'Learn Python'}, RequestOrigin.MEMORY),
                                  authority=authority, approve=lambda plan: Approval(plan.id, True))
        self.assertEqual(denied.failure.code, 'authority_denied')
        confirmed = executor.execute(ToolCall('goals_create', {'title': 'Learn Python'}, RequestOrigin.USER),
                                     authority=authority, approve=lambda p: Approval(p.id, True))
        self.assertIsNone(confirmed.failure)
        self.assertEqual(confirmed.value['progress'], 0)

    def test_terminal_commands_require_confirmation_and_update_progress(self):
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_GOALS_PATH': str(self.goals_path), 'IRIS_TASKS_PATH': str(self.tasks_path)})
        brain = create_brain(config)
        prompts = [
            '/add-goal Finish course | category=learning | priority=high | target=2026-12-31', 'n',
            '/add-goal Finish course | category=learning | priority=high | target=2026-12-31', 'yes',
            '/goals',
        ]
        with patch('builtins.input', side_effect=prompts + ['/exit']), patch('sys.stdout', new_callable=io.StringIO) as output:
            chat(brain)
        self.assertIn('not', output.getvalue().lower())
        with GoalStore(self.goals_path) as store:
            goals = store.list()
            self.assertEqual(len(goals), 1)
            goal = goals[0]
        inputs = [f'/update-goal {goal.id} progress=60 | description=Halfway', 'n',
                  f'/update-goal {goal.id} progress=60 | description=Halfway', 'yes',
                  f'/complete-goal {goal.id}', 'n', f'/complete-goal {goal.id}', 'yes', '/exit']
        with patch('builtins.input', side_effect=inputs), patch('sys.stdout', new_callable=io.StringIO) as output:
            chat(brain)
        with GoalStore(self.goals_path) as store:
            updated = store.fetch(goal.id)
            self.assertEqual(updated.status, GoalStatus.COMPLETED)
            self.assertEqual(updated.progress, 100)
            self.assertEqual(updated.revision, 3)
        self.assertIn('Goal action failed: This execution was not explicitly approved.', output.getvalue())
        self.assertIn('\"progress\": 60', output.getvalue())
        self.assertIn('Goal complete succeeded', output.getvalue())

    def test_malformed_ids_and_create_validation_before_confirmation(self):
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_GOALS_PATH': str(self.goals_path)})
        brain = create_brain(config)
        inputs = ['/add-goal ', '/add-goal Bad date | target=2026-02-30',
                  '/update-goal nope progress=20', '/complete-goal',
                  '/complete-goal 00000000-0000-0000-0000-000000000000', '/exit']
        with patch('builtins.input', side_effect=inputs), patch('sys.stdout', new_callable=io.StringIO) as output:
            chat(brain)
        self.assertIn('Goal rejected', output.getvalue())
        self.assertFalse(self.goals_path.exists())

    def test_task_goal_references_are_optional_persistent_and_validated(self):
        with GoalStore(self.goals_path) as goals:
            goal = goals.create('Build IRIS')
        registry = register_tasks(ToolRegistry(), self.tasks_path, 'America/Toronto', self.goals_path)
        executor = ToolExecutor(registry)
        authority = AuthorityContext(True, TASK_PERMISSIONS)
        args = {'title': 'Write tests', 'goal_id': goal.id}
        result = executor.execute(ToolCall('tasks_create', args, RequestOrigin.USER), authority=authority,
                                  approve=lambda p: Approval(p.id, True))
        self.assertIsNone(result.failure)
        self.assertEqual(result.value['goal_id'], goal.id)
        bad = executor.execute(ToolCall('tasks_create', {'title': 'Bad link', 'goal_id': '00000000-0000-0000-0000-000000000000'}, RequestOrigin.USER),
                               authority=authority, approve=lambda p: Approval(p.id, True))
        self.assertEqual(bad.failure.code, 'execution_failed')
        with TaskStore(self.tasks_path) as tasks:
            self.assertEqual(tasks.fetch(result.value['id']).goal_id, goal.id)
            self.assertEqual(len(tasks.list()), 1)

    def test_terminal_add_task_can_reference_existing_goal(self):
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_GOALS_PATH': str(self.goals_path), 'IRIS_TASKS_PATH': str(self.tasks_path)})
        brain = create_brain(config)
        with GoalStore(self.goals_path) as goals:
            goal = goals.create('Launch IRIS')
        with TaskStore(self.tasks_path) as tasks:
            with patch('builtins.input', side_effect=[f'/add-task Draft launch notes | goal={goal.id}', 'yes', '/tasks', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as output:
                chat(brain, task_store=tasks)
            task = tasks.list()[0]
            self.assertEqual(task.goal_id, goal.id)
        self.assertIn(f'goal={goal.id}', output.getvalue())

    def test_briefing_reports_neglect_and_goal_deadline_risk(self):
        with GoalStore(self.goals_path) as goals:
            overdue = goals.create('Late goal', target_date='2026-09-13', progress=10)
            risk = goals.create('Near goal', target_date='2026-09-18', progress=20)
            neglected = goals.create('Neglected goal', progress=35)
            old = '2026-08-01T00:00:00+00:00'
            goals._connection.execute('UPDATE goals SET data = ? WHERE id = ?',
                                      (__import__('json').dumps({**neglected.to_dict(), 'updated_at': old}), neglected.id))
            goals._connection.commit()
        result = build_briefing(task_path=self.tasks_path, goal_path=self.goals_path,
                                memory_path=self.memory_path, zone='America/Toronto',
                                at=datetime(2026, 9, 14, 16, tzinfo=timezone.utc))
        risks = {item['title']: item['risk'] for item in result['goal_risks']}
        self.assertEqual(risks, {'Late goal': 'overdue_target', 'Near goal': 'near_target_low_progress'})
        suggestion = '\n'.join(result['suggestions'])
        self.assertIn('Neglected goal', suggestion)
        self.assertIn('Late goal', suggestion)
        self.assertIn('Near goal', suggestion)
        rendered = render_briefing(result)
        self.assertIn('Active goals', rendered)
        self.assertIn('GOAL RISK', rendered)

    def test_goal_deadline_risk_respects_local_date_and_completion(self):
        with GoalStore(self.goals_path) as goals:
            due_today = goals.create('Today', target_date='2026-09-14', progress=0)
            completed = goals.create('Done', target_date='2026-09-13')
            goals.complete(completed.id)
        result = build_briefing(task_path=self.tasks_path, goal_path=self.goals_path,
                                memory_path=self.memory_path, zone='America/Toronto',
                                at=datetime(2026, 9, 15, 3, 30, tzinfo=timezone.utc))
        self.assertEqual(result['date'], '2026-09-14')
        self.assertEqual(result['goal_risks'][0]['risk'], 'near_target_low_progress')
        after_midnight = build_briefing(task_path=self.tasks_path, goal_path=self.goals_path,
                                        memory_path=self.memory_path, zone='America/Toronto',
                                        at=datetime(2026, 9, 15, 4, tzinfo=timezone.utc))
        self.assertEqual(after_midnight['goal_risks'][0]['id'], due_today.id)
        self.assertEqual(after_midnight['goal_risks'][0]['risk'], 'overdue_target')


if __name__ == '__main__':
    unittest.main()

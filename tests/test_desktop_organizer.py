from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from iris.brain.llm import LLMResponse, ModelTarget
from iris.brain.providers.openai_compatible import OpenAICompatibleConfig
from iris.desktop.organizer import ConversationOrganizer
from iris.goals.store import GoalStore
from iris.tasks.store import TaskStore
from iris.terminal import load_config


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:9999', 'IRIS_MODEL': 'test',
            'IRIS_TASKS_PATH': str(self.root / 'tasks.sqlite3'),
            'IRIS_GOALS_PATH': str(self.root / 'goals.sqlite3'), 'IRIS_TIMEZONE': 'America/Toronto'})
        self.now = datetime(2026, 10, 26, 14, tzinfo=timezone.utc)
        self.planner = Mock(return_value={'operations': []})
        self.organizer = ConversationOrganizer(self.root, self.config, {}, planner=self.planner,
                                               clock=lambda: self.now)

    def plan(self, *operations):
        self.planner.return_value = {'operations': list(operations)}

    def process_model_plan(self, text):
        """Exercise model validation even if a local phrase parser knows the input."""
        with patch.object(self.organizer, '_deterministic', return_value={'operations': []}):
            return self.organizer.process(text)

    def tasks(self):
        with TaskStore(self.config.tasks_path) as store:
            return store.list()

    def goals(self):
        with GoalStore(self.config.goals_path) as store:
            return store.list()

    def test_clear_commitment_uses_local_parser_without_model(self):
        events = self.organizer.process('I need to submit the report tomorrow at 6 PM.')
        task = self.tasks()[0]
        self.assertEqual(task.title, 'submit the report')
        self.assertEqual(task.due_at, '2026-10-27T22:00:00+00:00')
        self.assertEqual(events[0]['kind'], 'task')
        self.assertTrue(events[0]['undoable'])
        self.planner.assert_not_called()

    def test_unscheduled_commitment_does_not_invent_reminder(self):
        event = self.organizer.process('I have to renew my passport')[0]
        self.assertIsNone(self.tasks()[0].due_at)
        self.assertIn('No deadline set', event['detail'])

    def test_date_only_policy_is_disclosed(self):
        event = self.organizer.process('I will buy milk tomorrow')[0]
        self.assertEqual(self.tasks()[0].due_at, '2026-10-28T03:59:59+00:00')
        self.assertIn('Date-only policy', event['detail'])

    def test_relative_duration_uses_current_clock(self):
        self.organizer.process('I need to submit the report in 20 minutes')
        self.assertEqual(self.tasks()[0].due_at, '2026-10-26T14:20:00+00:00')

    def test_wanna_goal_uses_offline_common_phrase(self):
        self.organizer.process('I wanna learn French')
        self.assertEqual(self.goals()[0].title, 'learn French')
        self.planner.assert_not_called()

    def test_greeting_and_thanks_do_not_spend_model_request(self):
        self.assertEqual(self.organizer.process('hello!'), [])
        self.assertEqual(self.organizer.process('Thank you.'), [])
        self.planner.assert_not_called()

    def test_model_cannot_hide_ambiguous_time_by_extracting_date_only(self):
        text = 'My dentist appointment is tomorrow at 6'
        self.plan({'op': 'task_create', 'title': 'dentist appointment', 'deadline': 'tomorrow', 'evidence': text})
        events = self.organizer.process(text)
        self.assertIsNone(self.tasks()[0].due_at)
        self.assertEqual(events[-1]['kind'], 'clarification')

    def test_goal_and_undo_retain_revision_history(self):
        event = self.organizer.process('I want to learn French')[0]
        goal = self.goals()[0]
        self.assertEqual(goal.title, 'learn French')
        self.assertEqual(self.organizer.undo(event['id'])['state'], 'undone')
        self.assertEqual(self.goals(), ())
        with GoalStore(self.config.goals_path) as store:
            self.assertEqual([r.action for r in store.revisions(goal.id)], ['automatic_create', 'automatic_undo'])

    def test_same_message_and_equivalent_commitment_deduplicate_after_restart(self):
        self.organizer.process('I need to buy milk tomorrow')
        again = ConversationOrganizer(self.root, self.config, {}, planner=self.planner, clock=lambda: self.now)
        self.assertEqual(again.process('I need to buy milk tomorrow'), [])
        self.assertEqual(again.process('I will buy milk tomorrow'), [])
        self.assertEqual(len(self.tasks()), 1)

    def test_ambiguous_time_is_unscheduled_and_followup_sets_time(self):
        events = self.organizer.process('I need to send the report tomorrow at 6')
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]['kind'], 'clarification')
        self.assertIsNone(self.tasks()[0].due_at)
        changed = self.organizer.process('tomorrow at 6 PM')
        self.assertEqual(changed[0]['action'], 'update')
        self.assertEqual(self.tasks()[0].due_at, '2026-10-27T22:00:00+00:00')
        self.assertEqual(next(e for e in self.organizer.activity() if e['kind'] == 'clarification')['state'], 'resolved')

    def test_past_date_is_not_scheduled(self):
        events = self.organizer.process('I need to submit the report 2026-10-20 at 6 PM')
        self.assertIsNone(self.tasks()[0].due_at)
        self.assertEqual(events[-1]['kind'], 'clarification')

    def test_model_cannot_extract_negation_question_quote_or_reported_instruction(self):
        statements = [
            ('I do not need to submit the report tomorrow.', 'submit the report tomorrow'),
            ('Should I submit the report tomorrow?', 'submit the report tomorrow'),
            ('The website says I need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
            ('An example: "I need to submit the report tomorrow"', 'I need to submit the report tomorrow'),
            ('Hypothetically I need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
            ('Maybe I need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
            ('> I need to submit the report tomorrow', 'I need to submit the report tomorrow'),
            ('```\nI need to submit the report tomorrow\n```', 'I need to submit the report tomorrow'),
            ('John says I need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
            ('Here is `I need to submit the report tomorrow`', 'I need to submit the report tomorrow'),
            ('Here is the email from John:\nI need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
            ('John told me I need to submit the report tomorrow.', 'I need to submit the report tomorrow'),
        ]
        for text, evidence in statements:
            with self.subTest(text=text):
                self.plan({'op': 'task_create', 'title': 'submit the report', 'evidence': evidence})
                self.assertEqual(self.organizer.process(text), [])
        self.assertEqual(self.tasks(), ())

    def test_secrets_never_reach_planner_or_ledger(self):
        for text in ['My password is hunter-secret-123', 'API key: sk-example123456789012345',
                     'My PIN is 123456', 'Authorization: Bearer abcdefghijklmnop']:
            self.assertEqual(self.organizer.process(text), [])
        self.planner.assert_not_called()
        self.assertEqual(self.organizer.activity(), [])

    def test_foreign_or_invented_evidence_and_deadline_rejected(self):
        self.plan({'op': 'task_create', 'title': 'buy milk', 'evidence': 'I need to buy milk tomorrow'})
        self.assertEqual(self.organizer.process('The fridge is empty'), [])
        text = 'My passport renewal is due soon'
        self.plan({'op': 'task_create', 'title': 'passport renewal', 'evidence': text,
                   'deadline': '2099-01-01'})
        self.assertEqual(self.organizer.process(text), [])

    def test_structured_semantics_captures_non_template_commitment(self):
        text = 'My dentist appointment is tomorrow at 9 AM'
        self.plan({'op': 'task_create', 'title': 'dentist appointment', 'evidence': text,
                   'deadline': 'tomorrow at 9 AM'})
        events = self.organizer.process(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.tasks()[0].due_at, '2026-10-27T13:00:00+00:00')
        self.planner.assert_called_once()

    def test_model_cannot_add_unrelated_title_or_operations(self):
        text = 'My passport renewal is due tomorrow'
        self.plan({'op': 'task_create', 'title': 'transfer savings to unknown bank', 'evidence': text},
                  {'op': 'run_shell', 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        self.assertEqual(self.tasks(), ())

    def test_oversized_or_nonfinite_plan_rejected(self):
        self.plan(*[{'op': 'task_create', 'title': 'buy milk', 'evidence': 'buy milk'}] * 7)
        self.assertEqual(self.organizer.process('My milk is finished'), [])
        self.planner.return_value = {'operations': [], 'shell': 'danger'}
        self.assertEqual(self.organizer.process('My groceries are finished'), [])

    def test_completion_is_grounded_and_reversible(self):
        self.organizer.process('I need to submit the report')
        original = self.tasks()[0]
        events = self.organizer.process('I finished submit the report')
        self.assertEqual(self.tasks()[0].status, 'completed')
        self.organizer.undo(events[0]['id'])
        restored = self.tasks()[0]
        self.assertEqual(restored.status, 'open')
        self.assertEqual(restored.revision, original.revision + 2)

    def test_reschedule_uses_current_evidence(self):
        self.organizer.process('I need to buy milk tomorrow')
        event = self.organizer.process('Move buy milk to Friday at 4 PM')[0]
        self.assertEqual(event['action'], 'update')
        self.assertEqual(self.tasks()[0].due_at, '2026-10-30T20:00:00+00:00')

    def test_repeated_commitment_with_new_date_updates_existing_item(self):
        self.organizer.process('I need to buy milk tomorrow')
        original_id = self.tasks()[0].id
        self.assertEqual(self.organizer.process('I will buy milk Friday at 4 PM')[0]['action'], 'update')
        self.assertEqual(len(self.tasks()), 1)
        self.assertEqual(self.tasks()[0].id, original_id)
        self.assertEqual(self.tasks()[0].due_at, '2026-10-30T20:00:00+00:00')

    def test_title_cannot_replace_user_object_with_invented_object(self):
        text = 'My milk purchase is due tomorrow'
        self.plan({'op': 'task_create', 'title': 'milk poison', 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])

    def test_no_deadline_cannot_clear_existing_deadline(self):
        self.organizer.process('I need to buy milk tomorrow')
        original = self.tasks()[0]
        text = 'My buy milk task is important'
        self.plan({'op': 'task_update', 'id': original.id, 'deadline': None, 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        self.assertEqual(self.tasks()[0].due_at, original.due_at)

    def test_task_and_ledger_change_roll_back_together(self):
        with self.organizer._db() as db:
            db.execute("CREATE TRIGGER fail_activity BEFORE INSERT ON activity BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        self.assertEqual(self.organizer.process('I need to buy milk tomorrow'), [])
        self.assertEqual(self.tasks(), ())
        self.assertEqual(self.organizer.activity(), [])

    def test_undo_refuses_to_erase_newer_manual_change(self):
        event = self.organizer.process('I need to buy milk tomorrow')[0]
        with TaskStore(self.config.tasks_path) as store:
            store.complete(event['entity_id'])
        with self.assertRaisesRegex(ValueError, 'newer edit'):
            self.organizer.undo(event['id'])
        self.assertEqual(self.tasks()[0].status, 'completed')

    def test_wrong_record_and_ambiguous_matches_are_not_updated(self):
        with TaskStore(self.config.tasks_path) as store:
            one = store.create('submit physics report')
            store.create('submit chemistry report')
        text = 'I finished the report'
        self.plan({'op': 'task_complete', 'id': one.id, 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        self.assertTrue(all(t.status == 'open' for t in self.tasks()))

    def test_completion_of_future_dependency_does_not_complete_selected_task(self):
        with TaskStore(self.config.tasks_path) as store:
            task = store.create('submit the report')
        text = 'My submit the report task is due tomorrow after the draft is finished'
        self.plan({'op': 'task_complete', 'id': task.id, 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        self.assertEqual(self.tasks()[0].status, 'open')

    def test_exact_subject_completion_is_allowed(self):
        with TaskStore(self.config.tasks_path) as store:
            task = store.create('submit the report')
        text = 'My submit the report task is completed'
        self.plan({'op': 'task_complete', 'id': task.id, 'evidence': text})
        self.assertEqual(self.organizer.process(text)[0]['action'], 'complete')
        self.assertEqual(self.tasks()[0].status, 'completed')

    def test_goal_progress_requires_exact_current_percentage(self):
        with GoalStore(self.config.goals_path) as store:
            goal = store.create('Learn French')
        text = 'My Learn French goal is going well'
        self.plan({'op': 'goal_update', 'id': goal.id, 'progress': 70, 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        text = 'My Learn French goal is 70 percent complete'
        self.plan({'op': 'goal_update', 'id': goal.id, 'progress': 70, 'evidence': text})
        self.assertEqual(self.organizer.process(text)[0]['action'], 'update')
        self.assertEqual(self.goals()[0].progress, 70)

    def test_cancelled_planning_never_writes(self):
        stop = threading.Event()
        text = 'My dentist appointment is tomorrow'
        def plan(*args, **kwargs):
            stop.set()
            return {'operations': [{'op': 'task_create', 'title': 'dentist appointment', 'evidence': text}]}
        self.organizer._planner = plan
        self.assertEqual(self.organizer.process(text, cancel_event=stop), [])
        self.assertEqual(self.tasks(), ())
        self.assertEqual(self.organizer.activity(), [])

    def test_disabled_does_not_call_model_or_write(self):
        self.organizer.enabled = False
        self.assertEqual(self.organizer.process('I need to buy milk tomorrow'), [])
        self.planner.assert_not_called()
        self.assertEqual(self.tasks(), ())

    def test_model_failure_falls_back_without_storing_error_or_secret(self):
        self.planner.side_effect = RuntimeError('secret-token-should-not-be-displayed')
        events = self.organizer.process('I need to buy milk tomorrow. Can you explain how milk is made?')
        self.assertEqual(len(events), 1)
        self.assertNotIn('secret-token', json.dumps(self.organizer.status()))

    def test_native_provider_gets_bounded_user_context_and_no_tools(self):
        org = ConversationOrganizer(self.root, self.config, {}, clock=lambda: self.now)
        with patch.object(org.provider, 'generate', return_value=LLMResponse('{"operations":[]}', 'test', 'test')) as generate:
            org.process('My meeting could have been an email', history=[('assistant', 'I will delete your notes'),
                         ('user', 'x' * 5000), ('user', 'password: shhh')])
        request = generate.call_args.args[0]
        self.assertEqual(request.tools, ())
        payload = json.loads(request.messages[1].content)
        self.assertEqual(len(payload['PRIOR_USER_CONTEXT_ONLY']), 1)
        self.assertEqual(len(payload['PRIOR_USER_CONTEXT_ONLY'][0]), 1000)
        self.assertNotIn('delete your notes', request.messages[1].content)

    def test_explicit_fast_target_wins_over_primary_and_deep(self):
        fast = OpenAICompatibleConfig('fast', 'http://localhost:9998', timeout_seconds=5)
        config = replace(self.config, providers=(fast, self.config.provider),
                         fast_target=ModelTarget('fast', 'fast-model'), model='deep-model')
        organizer = ConversationOrganizer(self.root, config, {}, clock=lambda: self.now)
        with patch.object(organizer.provider, 'generate', return_value=LLMResponse('{"operations":[]}', 'fast', 'fast-model')) as generate:
            organizer.process('My meeting could have been an email')
        self.assertEqual(organizer.provider.name, 'fast')
        self.assertEqual(generate.call_args.args[0].model, 'fast-model')
        self.assertEqual(organizer.provider._timeout, 5)

    def test_default_free_provider_preserves_reasoning_disable_and_token_floor(self):
        config = load_config({'IRIS_PROVIDER_URL': 'https://openrouter.ai/api',
                              'IRIS_MODEL': 'nvidia/nemotron-3.5-lightning:free'})
        organizer = ConversationOrganizer(self.root, config, {}, clock=lambda: self.now)
        response = Mock()
        response.read.return_value = json.dumps({'choices': [{'message': {'content': '{"operations":[]}'}}]}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        # Avoid reading the config's default data paths: the transport is tested
        # with an explicit empty existing-record snapshot.
        with patch('iris.brain.providers.openai_compatible.urlopen', return_value=response) as urlopen:
            self.assertEqual(organizer._plan('My meeting could have been an email', (), {'tasks': [], 'goals': []}), {'operations': []})
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        self.assertEqual(payload['max_tokens'], 1200)
        self.assertNotIn('tools', payload)

    def test_note_capture_and_undo_with_real_notebook(self):
        from iris.desktop.notebook import Notebook
        notebook = Notebook(self.root / 'notebook-data')
        self.organizer.notebook = notebook
        text = 'My project uses Python and SQLite'
        self.plan({'op': 'note_capture', 'title': 'project Python SQLite', 'content': text, 'evidence': text})
        result = self.organizer.process(text)[0]
        self.assertEqual(result['kind'], 'note')
        self.assertTrue(notebook.search('Python'))
        self.organizer.undo(result['id'])
        self.assertEqual(notebook.search('Python'), [])

    def test_note_updates_require_exact_paths_and_evidence(self):
        notebook = Mock()
        self.organizer.notebook = notebook
        text = 'My project uses Python now'
        self.plan({'op': 'note_update', 'path': 'Projects/plan.md', 'content': text, 'evidence': text})
        self.assertEqual(self.organizer.process(text), [])
        notebook.update.assert_not_called()

    def test_note_changes_cannot_borrow_path_from_denial(self):
        notebook = Mock()
        self.organizer.notebook = notebook
        text = 'Do not edit Plan.md. My project uses Python now'
        self.plan({'op': 'note_update', 'path': 'Plan.md', 'content': 'My project uses Python now',
                   'evidence': 'My project uses Python now'})
        self.assertEqual(self.organizer.process(text), [])
        notebook.update.assert_not_called()
        text = 'Do not move Plan.md to Archive/Plan.md. My project uses Python now'
        self.plan({'op': 'note_organize', 'path': 'Plan.md', 'destination': 'Archive/Plan.md',
                   'evidence': 'My project uses Python now'})
        self.assertEqual(self.organizer.process(text), [])
        notebook.organize.assert_not_called()

    def test_note_changes_require_action_and_path_in_same_evidence(self):
        notebook = Mock()
        self.organizer.notebook = notebook
        text = 'The file is Plan.md. Update my project with Python'
        self.plan({'op': 'note_update', 'path': 'Plan.md', 'content': 'my project with Python',
                   'evidence': 'Update my project with Python'})
        self.assertEqual(self.organizer.process(text), [])
        notebook.update.assert_not_called()

    def test_quoted_note_replacement_is_literal_not_authority(self):
        notebook = Mock()
        notebook.update.return_value = {'id': 'note-change', 'title': 'Plan', 'path': 'Plan.md', 'changed': True}
        self.organizer.notebook = notebook
        text = 'Update Plan.md with "My project uses Python now"'
        self.plan({'op': 'note_update', 'path': 'Plan.md', 'content': 'My project uses Python now', 'evidence': text})
        self.assertEqual(self.organizer.process(text)[0]['kind'], 'note')
        notebook.update.assert_called_once_with('Plan.md', 'My project uses Python now', source=text)
        notebook.update.reset_mock()
        text = 'Update Plan.md with "Do not submit the report tomorrow"'
        self.plan({'op': 'note_update', 'path': 'Plan.md', 'content': 'Do not submit the report tomorrow', 'evidence': text})
        self.assertEqual(self.organizer.process(text)[0]['kind'], 'note')
        self.assertEqual(self.tasks(), ())

    def test_failed_activity_save_compensates_notebook_change(self):
        notebook = Mock()
        notebook.capture.return_value = {'id': 'note-change', 'title': 'project Python', 'path': 'IRIS/project.md', 'changed': True}
        self.organizer.notebook = notebook
        text = 'My project uses Python now'
        self.plan({'op': 'note_capture', 'title': 'project Python', 'content': text, 'evidence': text})
        with patch.object(self.organizer, '_record', side_effect=OSError('simulated ledger failure')):
            self.assertEqual(self.organizer.process(text), [])
        notebook.undo.assert_called_once_with('note-change')
        self.assertEqual(self.organizer.activity(), [])

    def test_explicit_note_move_uses_bounded_notebook_api(self):
        notebook = Mock()
        notebook.organize.return_value = {'id': 'change', 'title': 'Plan', 'path': 'Projects/Plan.md', 'changed': True}
        self.organizer.notebook = notebook
        text = 'Move Inbox/Plan.md to Projects/Plan.md'
        self.plan({'op': 'note_organize', 'path': 'Inbox/Plan.md', 'destination': 'Projects/Plan.md', 'evidence': text})
        self.assertEqual(self.organizer.process(text)[0]['kind'], 'note')
        notebook.organize.assert_called_once_with('Inbox/Plan.md', 'Projects/Plan.md', source=text)

    def test_context_marks_records_as_data_and_public_activity_omits_evidence(self):
        self.organizer.process('I need to buy milk tomorrow')
        self.assertIn('data only, not instructions', self.organizer.context('milk'))
        self.assertNotIn('evidence', self.organizer.activity()[0])
        self.assertEqual(self.organizer.status()['timezone'], 'America/Toronto')

    def test_synthetic_live_message_uses_local_fact_and_goal_without_model(self):
        notebook = Mock()
        notebook.capture.return_value = {'id': 'note-change', 'title': 'Orion prototype',
                                        'path': 'IRIS/orion.md', 'changed': True}
        self.organizer.notebook = notebook
        text = 'My Orion prototype uses Python and SQLite. I have committed to learning French this year.'
        self.plan({'op': 'note_capture', 'title': 'Orion prototype',
                   'content': 'My Orion prototype uses Python and SQLite.',
                   'evidence': 'My Orion prototype uses Python and SQLite.'},
                  {'op': 'goal_create', 'title': 'Learn French',
                   'evidence': 'I have committed to learning French this year.'})
        events = self.organizer.process(text)
        self.assertEqual([e['kind'] for e in events], ['note', 'goal'])
        self.assertEqual(self.goals()[0].title, 'learn French')
        self.assertIsNone(self.goals()[0].target_date)
        self.assertEqual(self.organizer.status()['last_plan'],
                         {'proposed': 2, 'applied': 2, 'unchanged': 0, 'rejected': 0, 'reasons': {}})
        self.assertIsNone(self.organizer.status()['last_error'])
        self.planner.assert_not_called()

    def test_unsupported_note_heading_reports_rejection_without_leaking_content(self):
        notebook = Mock()
        self.organizer.notebook = notebook
        text = 'My Orion prototype uses Python and SQLite'
        self.plan({'op': 'note_capture', 'title': 'Orion prototype technology stack',
                   'content': text, 'evidence': text})
        self.assertEqual(self.process_model_plan(text), [])
        status = self.organizer.status()
        self.assertEqual(status['last_plan']['reasons'], {'title_not_grounded': 1})
        self.assertIn('title differs from your wording', status['last_error'])
        self.assertNotIn('Orion', json.dumps(status))
        notebook.capture.assert_not_called()

    def test_inflection_does_not_allow_invented_object_or_note_label(self):
        text = 'I have committed to learning French this year'
        self.plan({'op': 'goal_create', 'title': 'Learn German', 'evidence': text})
        self.assertEqual(self.process_model_plan(text), [])
        self.assertEqual(self.goals(), ())
        self.assertEqual(self.organizer.status()['last_plan']['reasons'], {'title_not_grounded': 1})

    def test_inflected_titles_do_not_duplicate_existing_goal(self):
        self.organizer.process('I want to learn French')
        text = 'I have committed to learning French this year'
        self.plan({'op': 'goal_create', 'title': 'Learning French', 'evidence': text})
        self.assertEqual(self.process_model_plan(text), [])
        self.assertEqual(len(self.goals()), 1)
        self.assertEqual(self.organizer.status()['last_plan']['unchanged'], 1)
        self.assertIsNone(self.organizer.status()['last_error'])

    def test_valid_empty_plan_is_success_and_clears_previous_rejection(self):
        text = 'My milk purchase is due tomorrow'
        self.plan({'op': 'task_create', 'title': 'milk poison', 'evidence': text})
        self.organizer.process(text)
        self.assertIsNotNone(self.organizer.status()['last_error'])
        self.plan()
        self.assertEqual(self.organizer.process('The weather seems nice'), [])
        self.assertIsNone(self.organizer.status()['last_error'])
        self.assertEqual(self.organizer.status()['last_plan'],
                         {'proposed': 0, 'applied': 0, 'unchanged': 0, 'rejected': 0, 'reasons': {}})

    def test_note_paraphrase_and_malformed_action_have_safe_diagnostics(self):
        self.organizer.notebook = Mock()
        text = 'My Orion prototype uses Python and SQLite'
        self.plan({'op': 'note_capture', 'title': 'Orion prototype',
                   'content': 'The Orion project uses a Python SQLite stack.', 'evidence': text},
                  {'op': ['a-model-value-that-must-not-be-shown'], 'evidence': text})
        self.assertEqual(self.process_model_plan(text), [])
        status = self.organizer.status()
        self.assertEqual(status['last_plan']['reasons'], {'note_text_not_grounded': 1, 'unsupported_operation': 1})
        self.assertNotIn('Orion', json.dumps(status))
        self.assertNotIn('a-model-value', json.dumps(status))

    def test_storage_diagnostics_never_include_exception_message(self):
        text = 'My dentist appointment is tomorrow'
        self.plan({'op': 'task_create', 'title': 'dentist appointment', 'evidence': text})
        with patch.object(self.organizer, '_change', side_effect=OSError('secret: a-provider-key-value')):
            self.assertEqual(self.organizer.process(text), [])
        status = self.organizer.status()
        self.assertEqual(status['last_plan']['reasons'], {'storage_error': 1})
        self.assertNotIn('a-provider-key-value', json.dumps(status))

    def test_status_diagnostic_copy_cannot_mutate_internal_state(self):
        self.organizer.process('I need to buy milk tomorrow')
        self.organizer.status()['last_plan']['reasons']['invented'] = 9
        self.assertEqual(self.organizer.status()['last_plan']['reasons'], {})

    def test_firm_goal_patterns_use_local_sustained_action_forms(self):
        cases = [('I have committed to studying chemistry', 'study chemistry'),
                 ("I'm committed to running a marathon", 'run a marathon'),
                 ('I am committed to building a greenhouse', 'build a greenhouse')]
        for text, title in cases:
            with self.subTest(text=text):
                events = self.organizer.process(text)
                self.assertEqual(len(events), 1)
                self.assertEqual((events[0]['kind'], events[0]['title']), ('goal', title))
        self.assertEqual(self.tasks(), ())
        self.assertTrue(all(goal.target_date is None for goal in self.goals()))
        self.planner.assert_not_called()

    def test_generic_project_build_and_prototype_facts_are_verbatim_local_notes(self):
        notebook = Mock()
        notebook.capture.side_effect = lambda title, content, source: {
            'id': title, 'title': title, 'path': 'IRIS/item.md', 'changed': True}
        self.organizer.notebook = notebook
        cases = ['My garden project uses recycled timber', 'My sensor prototype uses an ESP32',
                 'My server build uses Debian']
        for text in cases:
            with self.subTest(text=text):
                result = self.organizer.process(text)
                self.assertEqual([event['kind'] for event in result], ['note'])
                self.assertEqual(notebook.capture.call_args.args[1], text)
                self.assertEqual(notebook.capture.call_args.kwargs['source'], text)
        self.planner.assert_not_called()
        self.assertEqual(self.tasks(), ())

    def test_negative_tentative_reported_quoted_project_facts_and_goals_are_not_local_capture(self):
        self.organizer.notebook = Mock()
        cases = ['My prototype uses no batteries', 'My project uses Python or Rust',
                 'My build probably uses Ubuntu', 'My prototype uses Python, not Rust',
                 'My project uses wood if funding arrives', 'My project uses wood?',
                 'Please tell me whether my prototype uses Bluetooth',
                 'John told me my project uses plastic',
                 'Here is the message from Jane:\nMy garden project uses concrete.',
                 '"My sensor prototype uses Zigbee"',
                 'I have not committed to learning Spanish',
                 "Maybe I'm committed to running a marathon",
                 'I have committed to studying physics?',
                 '"I am committed to building a greenhouse"',
                 'John told me I am committed to building a greenhouse']
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.organizer._deterministic(text, {'tasks': [], 'goals': []}), {'operations': []})
                self.assertEqual(self.organizer.process(text), [])
        self.organizer.notebook.capture.assert_not_called()
        self.assertEqual(self.goals(), ())
        self.assertEqual(self.tasks(), ())

    def test_multiple_generic_fact_and_firm_goal_sentences_bypass_bad_model_plan(self):
        notebook = Mock()
        notebook.capture.return_value = {'id': 'entry', 'title': 'garden project', 'path': 'IRIS/garden.md', 'changed': True}
        self.organizer.notebook = notebook
        self.plan({'op': 'task_create', 'title': 'study biology', 'evidence': 'I am committed to studying biology'})
        events = self.organizer.process('My garden project uses clay soil. I am committed to studying biology.')
        self.assertEqual([event['kind'] for event in events], ['note', 'goal'])
        self.assertEqual(self.organizer.status()['last_plan']['rejected'], 0)
        self.assertEqual(self.tasks(), ())
        self.planner.assert_not_called()

    def test_single_questions_do_not_spend_an_extraction_request(self):
        for text in ('Can you explain SQLite?', 'What can IRIS do?', 'Should I learn French?'):
            self.assertEqual(self.organizer.process(text), [])
        self.planner.assert_not_called()

    def test_question_after_fact_does_not_discard_the_fact(self):
        notebook = Mock()
        notebook.capture.return_value = {'id': 'entry', 'title': 'garden project',
                                        'path': 'IRIS/garden.md', 'changed': True}
        self.organizer.notebook = notebook
        fact = 'My garden project uses clay soil'
        self.plan({'op': 'note_capture', 'title': 'garden project', 'content': fact, 'evidence': fact})
        events = self.organizer.process(fact + '. Can you explain drainage?')
        self.assertEqual([event['kind'] for event in events], ['note'])
        self.planner.assert_called_once()


if __name__ == '__main__':
    unittest.main()

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock

from iris.desktop.reminder_service import ReminderService
from iris.goals.store import GoalStore
from iris.phone.store import PhoneStore
from iris.tasks.store import TaskStore


class ReminderServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc).timestamp()
        self.settings = {'IRIS_TIMEZONE': 'America/New_York'}
        self.transport = Mock()
        self.transport.send_sms.return_value = 'SM' + '1' * 32
        self.factory = Mock(return_value=self.transport)
        self.service = self.make()

    def make(self, **kwargs):
        return ReminderService(self.path, self.settings, clock=lambda: self.now,
                               transport_factory=self.factory, **kwargs)

    def phone(self):
        self.settings.update({
            'IRIS_AUTO_REMINDER_SMS': 'true', 'IRIS_PHONE_ENABLED': 'true',
            'IRIS_TWILIO_ACCOUNT_SID': 'AC' + 'a' * 32,
            'IRIS_TWILIO_AUTH_TOKEN': 'test-token', 'IRIS_PHONE_PIN': '123456',
            'IRIS_PHONE_NUMBER': '+18005550101', 'IRIS_OWNER_PHONE_NUMBER': '+14165550102',
            'IRIS_PHONE_PUBLIC_URL': 'https://iris.example.com',
        })
        self.service = self.make()

    def task(self, title='Bring passport', seconds=600, **kwargs):
        due = None if seconds is None else datetime.fromtimestamp(self.now + seconds, timezone.utc).isoformat()
        with TaskStore(self.path / 'tasks.sqlite3') as store:
            return store.create(title, due_at=due, **kwargs)

    def update_due(self, task, seconds):
        # Existing TaskStore has no update API; simulate an atomic persisted reschedule.
        with closing(sqlite3.connect(self.path / 'tasks.sqlite3')) as connection:
            row = connection.execute('SELECT data FROM tasks WHERE id = ?', (task.id,)).fetchone()
            data = json.loads(row[0])
            data['due_at'] = datetime.fromtimestamp(self.now + seconds, timezone.utc).isoformat()
            data['revision'] += 1
            connection.execute('UPDATE tasks SET data = ? WHERE id = ?', (json.dumps(data), task.id))
            connection.commit()

    def records(self):
        with closing(sqlite3.connect(self.service.path)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute('SELECT * FROM reminders ORDER BY created, id')]

    def test_tasks_are_reminded_fifteen_minutes_before_without_inventing_dates(self):
        self.task('Undated', seconds=None)
        future = self.task('Later', seconds=901)
        self.assertEqual(self.service.tick(), [])
        self.now += 1
        events = self.service.tick()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['task_id'], future.id)
        self.assertEqual(events[0]['kind'], 'task')
        self.assertIn('08:15 AM EDT', events[0]['message'])
        self.assertIn('America/New_York', events[0]['message'])
        self.assertFalse(events[0]['catch_up'])
        self.factory.assert_not_called()

    def test_missing_stores_are_not_created(self):
        self.assertEqual(self.service.tick(), [])
        self.assertFalse((self.path / 'tasks.sqlite3').exists())
        self.assertFalse((self.path / 'goals.sqlite3').exists())
        self.assertFalse((self.path / 'phone.sqlite3').exists())

    def test_restart_acknowledgment_and_due_time_do_not_duplicate(self):
        task = self.task()
        event = self.service.tick()[0]
        self.assertEqual(self.make().tick()[0]['id'], event['id'])
        self.assertTrue(self.service.acknowledge(event['id'])['acknowledged'])
        self.assertTrue(self.service.acknowledge(event['id'])['acknowledged'])
        self.now += 900
        self.assertEqual(self.make().tick(), [])
        with TaskStore(self.path / 'tasks.sqlite3') as store:
            self.assertEqual(store.fetch(task.id).status, 'open')
        with self.assertRaises(ValueError):
            self.service.acknowledge('f' * 40)

    def test_completed_deleted_and_rescheduled_pending_events_are_removed(self):
        completed = self.task('Completed')
        deleted = self.task('Deleted')
        changed = self.task('Changed')
        self.assertEqual(len(self.service.tick()), 3)
        with TaskStore(self.path / 'tasks.sqlite3') as store:
            store.complete(completed.id)
            store.delete(deleted.id)
        self.update_due(changed, 3600)
        self.assertEqual(self.service.pending(), [])
        self.now += 2700
        new = self.service.tick()
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]['task_id'], changed.id)
        self.assertEqual(sum(r['state'] == 'stale' for r in self.records()), 3)

    def test_catchup_is_limited_to_one_day_and_three_new_alerts_per_five_minutes(self):
        self.task('Too old', seconds=-86401)
        for i in range(7):
            self.task(f'Overdue {i}', seconds=-600 - i)
        events = self.service.tick()
        self.assertEqual(len(events), 3)
        self.assertTrue(all(event['catch_up'] for event in events))
        self.assertEqual(len(self.records()), 3)
        for event in events:
            self.service.acknowledge(event['id'])
        self.assertEqual(self.service.tick(), [])
        self.now += 301
        self.assertEqual(len(self.service.tick()), 3)
        self.assertEqual(len(self.records()), 6)
        self.assertNotIn('Too old', [r['title'] for r in self.records()])

    def test_pending_expires_after_one_day(self):
        self.task(seconds=0)
        self.assertEqual(len(self.service.tick()), 1)
        self.now += 86401
        self.assertEqual(self.service.pending(), [])

    def test_goal_date_at_nine_local_and_linked_task_deduplication(self):
        with GoalStore(self.path / 'goals.sqlite3') as store:
            goal = store.create('Finish portfolio', target_date='2026-10-26')
            linked = store.create('Linked project', target_date='2026-10-26')
            store.create('No date')
            paused = store.create('Paused', target_date='2026-10-26')
            store.update(paused.id, {'status': 'paused'})
        self.task('Concrete project step', seconds=12 * 3600, goal_id=linked.id)
        self.now += 3599
        self.assertEqual(self.service.tick(), [])
        self.now += 1
        events = self.service.tick()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['entity_id'], goal.id)
        self.assertEqual(events[0]['kind'], 'goal')
        self.assertIsNone(events[0]['task_id'])
        self.assertIn('09:00 AM EDT', events[0]['message'])
        with GoalStore(self.path / 'goals.sqlite3') as store:
            store.complete(goal.id)
        self.assertEqual(self.service.pending(), [])

    def test_winter_timezone_is_est(self):
        self.now = datetime(2026, 12, 1, 14, 0, tzinfo=timezone.utc).timestamp()
        self.task(seconds=0)
        self.assertIn('09:00 AM EST', self.service.tick()[0]['message'])

    def test_corrupt_stores_fail_closed_without_exposing_errors(self):
        self.task()
        self.service.tick()
        with closing(sqlite3.connect(self.path / 'tasks.sqlite3')) as connection:
            connection.execute('UPDATE tasks SET data = ?', ('not-json-private-value',))
            connection.commit()
        self.assertEqual(self.service.pending(), [])
        self.assertIsNotNone(self.service.status()['last_error'])
        self.assertNotIn('private', repr(self.service.status()))

    def test_concurrent_ticks_publish_one_event(self):
        self.task()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.service.tick(), range(12)))
        self.assertEqual(len(self.records()), 1)

    def test_notifier_runs_once_and_failure_keeps_hud_event(self):
        notifier = Mock(side_effect=RuntimeError('unavailable'))
        self.service = self.make(notifier=notifier)
        self.task()
        self.service.tick()
        notifier.assert_not_called()
        self.service._deliver_desktop_alerts()
        self.service._deliver_desktop_alerts()
        self.make(notifier=notifier)._deliver_desktop_alerts()
        notifier.assert_called_once()
        self.assertEqual(len(self.service.pending()), 1)

    def test_disabled_service_does_not_create_or_send_reminders(self):
        self.settings['IRIS_AUTO_REMINDERS'] = 'false'
        self.service = self.make()
        self.task()
        self.assertEqual(self.service.tick(), [])
        self.service.start()
        self.assertFalse(self.service.status()['running'])
        self.factory.assert_not_called()

    def test_old_unacknowledged_hud_events_do_not_block_new_native_alerts(self):
        notifier = Mock()
        self.service = self.make(notifier=notifier)
        for index in range(3):
            self.task(f'Old {index}')
        self.service.tick()
        self.service._deliver_desktop_alerts()
        self.now += 301
        self.task('New deadline')
        self.service.tick()
        self.service._deliver_desktop_alerts()
        self.assertEqual(notifier.call_count, 4)
        self.assertIn('New deadline', notifier.call_args.args[1])

    def test_sms_requires_both_explicit_opt_in_and_complete_phone_setup(self):
        self.settings['IRIS_AUTO_REMINDER_SMS'] = 'true'
        self.service = self.make()
        self.task()
        self.service.tick()
        self.service._deliver_sms()
        self.factory.assert_not_called()
        self.assertFalse(self.service.status()['sms_enabled'])
        self.phone()
        self.settings.pop('IRIS_AUTO_REMINDER_SMS')
        self.service = self.make()
        self.service._deliver_sms()
        self.factory.assert_not_called()

    def test_sms_is_background_only_owner_configured_single_segment_ascii_and_once(self):
        self.phone()
        self.task('Bring résumé [] {} \\ ~ ^ 😀 ' * 12)
        self.service.tick()
        self.transport.send_sms.assert_not_called()
        self.service._deliver_sms()
        self.service._deliver_sms()
        self.make()._deliver_sms()
        self.transport.send_sms.assert_called_once()
        message = self.transport.send_sms.call_args.args[0]
        self.assertLessEqual(len(message), 160)
        self.assertTrue(message.isascii())
        self.assertNotRegex(message, r'[\[\]{}\\~^|]')
        self.assertIn('EDT', message)
        self.assertIn('Reply STOP to stop.', message)
        self.assertEqual(self.factory.call_args.args[0].owner_number, '+14165550102')
        self.assertEqual(self.records()[0]['sms_state'], 'accepted')

    def test_initial_rollout_never_texts_historical_deadlines(self):
        self.task('Already due', seconds=-60)
        self.phone()
        self.assertEqual(len(self.service.tick()), 1)
        self.service._deliver_sms()
        self.transport.send_sms.assert_not_called()
        self.assertEqual(self.records()[0]['sms_state'], 'disabled')

    def test_sms_stop_suppresses_and_start_does_not_resend_old_reminder(self):
        self.phone()
        self.task()
        self.service.tick()
        phone = PhoneStore(self.path / 'phone.sqlite3')
        phone.set_opt_out(True)
        self.service._deliver_sms()
        phone.set_opt_out(False)
        self.service._deliver_sms()
        self.assertEqual(self.records()[0]['sms_state'], 'suppressed')
        self.transport.send_sms.assert_not_called()

    def test_sms_skips_completed_rescheduled_and_expired_records(self):
        self.phone()
        task = self.task()
        changed = self.task('Rescheduled')
        self.task('Expired')
        self.service.tick()
        with TaskStore(self.path / 'tasks.sqlite3') as store:
            store.complete(task.id)
        self.update_due(changed, 10000)
        self.now += 4300
        self.service._deliver_sms()
        self.transport.send_sms.assert_not_called()
        self.assertTrue(all(r['sms_state'] == 'suppressed' for r in self.records()))

    def test_sms_uncertainty_is_never_retried_even_after_restart(self):
        self.phone()
        self.task()
        self.transport.send_sms.side_effect = RuntimeError('private provider diagnostic')
        self.service.tick()
        self.service._deliver_sms()
        self.make()._deliver_sms()
        self.transport.send_sms.assert_called_once()
        self.assertEqual(self.records()[0]['sms_state'], 'unknown')
        self.assertNotIn('private', repr(self.service.status()))
        with self.service._connection(write=True) as connection:
            connection.execute("UPDATE reminders SET sms_state = 'sending'")
        self.make()._deliver_sms()
        self.assertEqual(self.records()[0]['sms_state'], 'unknown')
        self.transport.send_sms.assert_called_once()

    def test_sms_hourly_and_daily_caps_suppress_excess_without_delayed_flood(self):
        self.phone()
        for hour in range(6):
            for index in range(3):
                self.task(f'Hour {hour} item {index}')
            self.service.tick()
            self.service._deliver_sms()
            self.now += 3601
        self.assertEqual(self.transport.send_sms.call_count, 10)
        self.assertEqual(sum(r['sms_state'] == 'suppressed' for r in self.records()), 8)

    def test_concurrent_sms_delivery_claims_once(self):
        self.phone()
        self.task()
        self.service.tick()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.service._deliver_sms(), range(12)))
        self.transport.send_sms.assert_called_once()

    def test_closing_during_transport_initialization_suppresses_late_send(self):
        self.phone()
        self.task()
        self.service.tick()
        self.factory.side_effect = lambda _: (self.service.stop(), self.transport)[-1]
        self.service._deliver_sms()
        self.transport.send_sms.assert_not_called()
        self.assertEqual(self.records()[0]['sms_state'], 'suppressed')

    def test_completed_during_transport_initialization_suppresses_late_send(self):
        self.phone()
        task = self.task()
        self.service.tick()

        def initialize(_):
            with TaskStore(self.path / 'tasks.sqlite3') as store:
                store.complete(task.id)
            return self.transport

        self.factory.side_effect = initialize
        self.service._deliver_sms()
        self.transport.send_sms.assert_not_called()
        self.assertEqual(self.records()[0]['sms_state'], 'suppressed')

    def test_shutdown_during_native_alert_skips_remaining_alerts(self):
        self.service = self.make(notifier=lambda *_: self.service.stop())
        for i in range(3):
            self.task(f'Due {i}')
        self.service.tick()
        self.service._deliver_desktop_alerts()
        self.assertEqual(sum(row['alert_attempted'] for row in self.records()), 1)

    def test_worker_start_stop_and_slow_sms_does_not_block_pending(self):
        self.phone()
        self.task()
        started = threading.Event()
        release = threading.Event()
        self.transport.send_sms.side_effect = lambda _: (started.set(), release.wait(5), 'SM' + '1' * 32)[-1]
        self.addCleanup(release.set)
        self.addCleanup(self.service.stop)
        self.service.start()
        self.service.start()
        self.assertTrue(started.wait(3))
        self.assertEqual(len(self.service.pending()), 1)
        self.assertTrue(self.service.status()['running'])
        release.set()
        self.service.stop()
        self.assertFalse(self.service.status()['running'])


if __name__ == '__main__':
    unittest.main()

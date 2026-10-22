
import os as _platform_os
import unittest as _platform_tests
if _platform_os.name == "nt":
    raise _platform_tests.SkipTest("Legacy POSIX launcher/permissions/deadline tests; Windows desktop has dedicated tests")

from datetime import datetime, timezone
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.reminders import (CommandInput, ReminderConfig, ReminderWorker,
                            eligible_tasks, load_config, main, reminder_worker_lock,
                            reminder_worker_status, run)
from iris.tasks.store import TaskStore
from iris.terminal import chat


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = self.directory.name + '/tasks.sqlite3'
        self.store = TaskStore(self.path)
        self.addCleanup(self.store.close)
        self.at = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
        self.messages = []
        self.config = ReminderConfig(tasks_path=self.path)

    def worker(self):
        return ReminderWorker(self.store, self.config, self.messages.append)

    def test_overdue_upcoming_boundary_and_exclusions(self):
        past = self.store.create('past', due_at='2026-09-14T17:59:59Z')
        now = self.store.create('now', due_at='2026-09-14T18:00:00Z')
        edge = self.store.create('edge', due_at='2026-09-14T14:15:00-04:00')
        self.store.create('beyond', due_at='2026-09-14T18:15:01Z')
        self.store.create('undated')
        completed = self.store.create('completed', due_at='2026-09-14T10:00:00Z')
        deleted = self.store.create('deleted', due_at='2026-09-14T10:00:00Z')
        self.store.complete(completed.id)
        self.store.delete(deleted.id)
        self.assertEqual({t.id for t in eligible_tasks(self.store, self.at, 900)}, {past.id, now.id, edge.id})
        self.assertEqual({t.id for t in eligible_tasks(self.store, self.at, 0)}, {past.id, now.id})
        worker = self.worker()
        worker.check(self.at)
        self.assertIn('OVERDUE', self.messages[0])
        self.assertIn('UPCOMING', self.messages[-1])
        self.assertIn('2026-09-14T14:15:00-04:00 [America/Toronto]', self.messages[-1])

    def test_deduplication_new_tasks_and_restart(self):
        task = self.store.create('soon', due_at='2026-09-14T18:10:00Z')
        worker = self.worker()
        worker.check(self.at)
        worker.check(datetime(2026, 9, 15, tzinfo=timezone.utc))
        self.assertEqual(len(self.messages), 1)  # Upcoming -> overdue still announced once.
        new = self.store.create('new', due_at='2026-09-14T17:00:00Z')
        worker.check(self.at)
        self.assertEqual(len(self.messages), 2)
        self.assertEqual(worker.announced, {task.id, new.id})
        self.worker().check(self.at)
        self.assertEqual(len(self.messages), 4)  # A new run resets the in-memory set.
        self.assertEqual(len(self.store.revisions(task.id)), 1)
        self.assertEqual(self.store.fetch(task.id).status, 'open')

    def test_interval_and_window_validation(self):
        for interval in ('0', '-1', 'nan', 'inf', '-inf', 'garbage', '86401', '0.5', ''):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                load_config({'IRIS_REMINDERS_INTERVAL_SECONDS': interval})
        for window in ('-1', 'nan', 'inf', 'bad', '86401'):
            with self.subTest(window=window), self.assertRaises(ValueError):
                load_config({'IRIS_REMINDERS_UPCOMING_SECONDS': window})
        with self.assertRaises(ValueError):
            ReminderConfig(interval_seconds=True)
        with self.assertRaises(ValueError):
            load_config({'IRIS_TIMEZONE': 'Unknown/Place'})
        config = load_config({'IRIS_REMINDERS_INTERVAL_SECONDS': '1.5', 'IRIS_REMINDERS_UPCOMING_SECONDS': '0',
                              'IRIS_TIMEZONE': 'Asia/Tokyo', 'IRIS_TASKS_PATH': self.path})
        self.assertEqual(config.interval_seconds, 1.5)
        self.assertEqual(config.upcoming_seconds, 0)
        self.assertEqual(config.timezone, 'Asia/Tokyo')
        self.assertEqual(load_config({}).timezone, 'America/Toronto')

    def test_periodic_checks_and_stop_without_sleep(self):
        worker = self.worker()
        clock = [0.0]
        polls = []
        class Commands:
            def poll(inner, timeout):
                polls.append(timeout)
                if len(polls) == 1:
                    clock[0] += timeout
                    return None
                if len(polls) == 2:
                    return '/reminders-status'
                return '/reminders-stop'
        run(worker, Commands(), monotonic=lambda: clock[0])
        self.assertEqual(worker.checks, 2)
        self.assertEqual(polls, [60, 60, 60])
        self.assertFalse(worker.running)
        self.assertTrue(any('checks=2' in m and 'running' in m for m in self.messages))
        worker.check(self.at)
        self.assertEqual(worker.checks, 2)
        self.assertEqual(self.messages[-1], 'Local reminders stopped.')

    def test_shutdown_on_eof_interrupt_and_read_failure(self):
        for error in (EOFError(), KeyboardInterrupt(), OSError('input failed')):
            with self.subTest(error=error):
                worker = self.worker()
                commands = Mock()
                commands.poll.side_effect = error
                if isinstance(error, OSError):
                    with self.assertRaises(OSError):
                        run(worker, commands)
                else:
                    run(worker, commands)
                self.assertFalse(worker.running)
                self.assertEqual(self.messages[-1], 'Local reminders stopped.')

    def test_real_pipe_input_timeout_buffering_and_eof(self):
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, 'rb') as stream:
            commands = CommandInput(stream)
            self.assertIsNone(commands.poll(0))
            os.write(write_fd, b'/reminders-status\n/reminders-stop\n')
            try:
                self.assertEqual(commands.poll(0), '/reminders-status')
                # Buffered second line must not wait for another OS read.
                self.assertEqual(commands.poll(0), '/reminders-stop')
                os.write(write_fd, b'last line without newline')
            finally:
                os.close(write_fd)
            self.assertIsNone(commands.poll(0))
            # The first read can observe data, then a subsequent read observes EOF.
            line = commands.poll(0)
            self.assertEqual(line, 'last line without newline')
            with self.assertRaises(EOFError):
                commands.poll(0)

    def test_read_only_store_sees_changes_without_mutations(self):
        before = self.store.create('existing', due_at='2020-01-01T00:00:00Z')
        with TaskStore(self.path, read_only=True) as reader:
            worker = ReminderWorker(reader, self.config, self.messages.append)
            worker.check(self.at)
            added = self.store.create('added', due_at='2020-01-01T00:00:00Z')
            self.store.complete(before.id)
            worker.check(self.at)
            self.assertEqual(worker.announced, {before.id, added.id})
            with self.assertRaises(sqlite3.OperationalError):
                reader.create('forbidden')
        self.assertEqual(len(self.store.revisions(added.id)), 1)
        missing = self.directory.name + '/missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            TaskStore(missing, read_only=True)
        self.assertFalse(os.path.exists(missing))

    def test_main_eof_closes_store_and_needs_no_model_config(self):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        with os.fdopen(read_fd, 'rb') as stream, patch('sys.stdin', stream), patch.dict(
                'os.environ', {'IRIS_TASKS_PATH': self.path,
                               'IRIS_REMINDERS_STATUS_PATH': self.directory.name + '/reminder.lock'}, clear=True
        ), patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(main([]), 0)
        self.assertIn('Local reminders stopped.', output.getvalue())
        with patch('iris.reminders.load_config', side_effect=ValueError('bad interval')), patch('sys.stderr', new_callable=io.StringIO) as errors:
            self.assertEqual(main([]), 1)
        self.assertIn('bad interval', errors.getvalue())

    def test_read_only_reminder_status_reports_running_and_stopped(self):
        marker = self.directory.name + '/status.lock'
        self.assertEqual(reminder_worker_status(marker), 'stopped')
        with reminder_worker_lock(marker):
            self.assertEqual(reminder_worker_status(marker), 'running')
        self.assertEqual(reminder_worker_status(marker), 'stopped')

    def test_commands_in_chat_are_local_and_do_not_call_model(self):
        brain = Mock()
        with patch('builtins.input', side_effect=['/reminders-status', '/reminders-stop', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as output:
            chat(brain)
        brain.respond.assert_not_called()
        self.assertIn('does not own a reminder worker', output.getvalue())


class ReminderCLITests(unittest.TestCase):
    def test_help_exits_before_configuration_database_or_worker(self):
        for flag in ('--help', '-h'):
            with self.subTest(flag=flag), patch('sys.argv', ['iris.reminders', flag]), \
                    patch('iris.reminders.load_config') as config, \
                    patch('iris.reminders.TaskStore') as store, \
                    patch('iris.reminders.CommandInput') as commands, \
                    patch('iris.reminders.ReminderWorker') as worker, \
                    patch('iris.reminders.run') as run_worker, \
                    patch('sys.stdout', new_callable=io.StringIO) as output:
                with self.assertRaises(SystemExit) as exit_result:
                    main()
                self.assertEqual(exit_result.exception.code, 0)
                for dependency in (config, store, commands, worker, run_worker):
                    dependency.assert_not_called()
                help_text = output.getvalue()
                self.assertIn('usage: python -m iris.reminders', help_text)
                self.assertIn('IRIS_REMINDERS_INTERVAL_SECONDS', help_text)
                self.assertIn('default 60', help_text)
                self.assertIn('1–86400', help_text)
                self.assertIn('/reminders-stop', help_text)
                self.assertNotIn('Local reminders started.', help_text)

    def test_unknown_option_does_not_start_worker(self):
        with patch('iris.reminders.TaskStore') as store, \
                patch('iris.reminders.run') as run_worker, \
                patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as exit_result:
                main(['--interval', '30'])
        self.assertEqual(exit_result.exception.code, 2)
        store.assert_not_called()
        run_worker.assert_not_called()


if __name__ == '__main__':
    unittest.main()

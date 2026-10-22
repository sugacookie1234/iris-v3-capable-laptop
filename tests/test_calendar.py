from datetime import datetime, timezone
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.calendar import CalendarSource, MAX_BYTES, list_events, read_calendar, register_calendar
from iris.terminal import chat, create_brain, load_config
from iris.tools import AuthorityContext, RequestOrigin, ToolCall, ToolExecutor, ToolRegistry


def calendar(*events):
    return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//IRIS tests//EN\r\n' + ''.join(
        'BEGIN:VEVENT\r\n' + event.replace('\n', '\r\n') + '\r\nEND:VEVENT\r\n' for event in events
    ) + 'END:VCALENDAR\r\n'


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'calendar.ics'
        self.source = CalendarSource(str(self.root), 'calendar.ics')
        self.at = datetime(2026, 9, 14, 16, tzinfo=timezone.utc)

    def write(self, *events):
        self.path.write_text(calendar(*events), encoding='utf-8', newline="")

    def events(self, period='today', days=7):
        return list_events(self.source, period, days, at=self.at)['events']

    def test_dates_zones_folding_and_overlap(self):
        self.write('UID:a\nDTSTART;VALUE=DATE:20260914\nSUMMARY:All day',
                   'UID:b\nDTSTART;TZID=America/Toronto:20260914T130000\nDTEND;TZID=America/Toronto:20260914T140000\nSUMMARY:Team \'s\n meeting\\, review\nLOCATION:Room\\; 1',
                   'UID:c\nDTSTART:20260913T230000Z\nDTEND:20260914T050000Z\nSUMMARY:Overnight',
                   'UID:d\nDTSTART:20260914T180000\nSUMMARY:Floating',
                   'UID:e\nDTSTART:20260915T040000Z\nSUMMARY:Tomorrow')
        events = self.events()
        self.assertEqual(len(events), 4)
        by_id = {e['uid']: e for e in events}
        self.assertTrue(by_id['a']['all_day'])
        self.assertEqual(by_id['a']['end'], '2026-09-15T04:00:00+00:00')
        self.assertEqual(by_id['b']['start'], '2026-09-14T17:00:00+00:00')
        self.assertEqual(by_id['b']['title'], "Team 'smeeting, review")
        self.assertEqual(by_id['b']['location'], 'Room; 1')
        self.assertEqual(by_id['d']['start'], '2026-09-14T22:00:00+00:00')
        self.assertNotIn('c', {e['uid'] for e in self.events('upcoming')})

    def test_recurring_daily_weekly_monthly_yearly_and_exdate(self):
        self.write('UID:daily\nDTSTART:20260913T170000Z\nRRULE:FREQ=DAILY;COUNT=4\nEXDATE:20260915T170000Z',
                   'UID:weekly\nDTSTART;TZID=America/Toronto:20260914T140000\nRRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=3',
                   'UID:monthly\nDTSTART;VALUE=DATE:20260714\nRRULE:FREQ=MONTHLY;INTERVAL=2;COUNT=2',
                   'UID:yearly\nDTSTART;VALUE=DATE:20240914\nRRULE:FREQ=YEARLY;UNTIL=20260914')
        result = self.events('upcoming', 7)
        self.assertEqual(sum(e['uid'] == 'daily' for e in result), 2)
        self.assertEqual(sum(e['uid'] == 'weekly' for e in result), 2)
        self.assertEqual(sum(e['uid'] == 'monthly' for e in result), 1)
        self.assertEqual(sum(e['uid'] == 'yearly' for e in result), 1)

    def test_recurrence_preserves_local_time_across_dst(self):
        self.at = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        self.write('UID:dst\nDTSTART;TZID=America/Toronto:20261031T090000\nRRULE:FREQ=DAILY;COUNT=3')
        result = self.events('upcoming')
        self.assertEqual([e['start'][11:16] for e in result], ['13:00', '14:00', '14:00'])

    def test_invalid_data_and_unsupported_recurrence_fail_closed(self):
        for event in ('UID:x\nDTSTART:20260230T180000Z',
                      'UID:x\nDTSTART;TZID=Unknown/Zone:20260914T180000',
                      'UID:x\nDTSTART;TZID=America/Toronto:20261101T013000',
                      'UID:x\nDTSTART:20260914T180000Z\nDTEND:20260914T170000Z',
                      'UID:x\nDTSTART:20260914T180000Z\nRRULE:FREQ=HOURLY',
                      'UID:x\nDTSTART:20260914T180000Z\nRRULE:FREQ=MONTHLY;BYSETPOS=1',
                      'UID:x\nDTSTART:20260914T180000Z\nRECURRENCE-ID:20260914T180000Z',
                      'DTSTART:20260914T180000Z',
                      'UID:x\nDTSTART:20260914T180000Z\nDTSTART:20260914T190000Z'):
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.write(event)
                self.events()
        for raw in ('not ICS', 'BEGIN:VCALENDAR\nVERSION:2.0', calendar().replace('2.0', '1.0')):
            self.path.write_text(raw, newline="")
            with self.assertRaises(ValueError):
                self.events()

    def test_bounds_and_cancelled(self):
        self.write('UID:x\nDTSTART:20260914T180000Z\nSTATUS:CANCELLED')
        self.assertEqual(self.events(), [])
        for days in (0, 32, True):
            with self.assertRaises(ValueError):
                self.events('upcoming', days)
        self.write('UID:old\nDTSTART:19000101T180000Z\nRRULE:FREQ=DAILY')
        with self.assertRaises(ValueError):
            self.events()

    def test_safe_paths_symlinks_nonregular_size_and_credentials(self):
        self.write('UID:x\nDTSTART:20260914T180000Z')
        before = self.path.read_bytes()
        self.events()
        self.assertEqual(self.path.read_bytes(), before)
        for name in ('../calendar.ics', '/outside/calendar.ics', '.hidden.ics', 'api-key.ics', 'calendar.txt'):
            with self.subTest(name=name), self.assertRaises((ValueError, PermissionError)):
                CalendarSource(str(self.root), name)
        link = self.root / 'link.ics'
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            read_calendar(CalendarSource(str(self.root), 'link.ics'))
        directory = self.root / 'folder'
        directory.symlink_to(self.root, target_is_directory=True)
        for source in (CalendarSource(str(self.root), 'folder/calendar.ics'), CalendarSource(str(directory), 'calendar.ics')):
            with self.assertRaises(OSError):
                read_calendar(source)
        fifo = self.root / 'pipe.ics'
        if hasattr(os, 'mkfifo'):
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                read_calendar(CalendarSource(str(self.root), 'pipe.ics'))
        self.path.write_bytes(b'x' * (MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            read_calendar(self.source)
        for content in (b'\xff', b'\x00'):
            self.path.write_bytes(content)
            with self.assertRaises(ValueError):
                read_calendar(self.source)
        self.write('UID:x\nDTSTART:20260914T180000Z\nDESCRIPTION:api_key=abcdefgh123456789')
        with self.assertRaises(PermissionError):
            read_calendar(self.source)

    def brain(self):
        config = load_config({'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
                              'IRIS_CALENDAR_PATH': 'calendar.ics', 'IRIS_CALENDAR_ROOT': str(self.root)})
        return create_brain(config)

    def test_green_tool_terminal_and_no_history_or_writes(self):
        self.write('UID:x\nDTSTART:20260914T180000Z\nSUMMARY:Read only')
        executor = ToolExecutor(register_calendar(ToolRegistry(), self.source))
        result = executor.execute(ToolCall('calendar_list', {'days': 31}),
                                  authority=AuthorityContext(True, frozenset({'calendar.read'})))
        self.assertIsNone(result.failure)
        self.assertEqual(result.plan.spec.authority, 'GREEN')
        denied = executor.execute(ToolCall('calendar_list'), authority=AuthorityContext(True))
        self.assertIsNotNone(denied.failure)
        brain = self.brain()
        with patch.object(brain, 'respond') as respond, patch('builtins.input', side_effect=['/calendar', '/calendar upcoming 7', '/calendar upcoming ' + '9' * 5000, '/calendar bogus', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as out:
            chat(brain)
        respond.assert_not_called()
        self.assertIn('Calendar (America/Toronto)', out.getvalue())
        self.assertIn('Use /calendar', out.getvalue())
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'calendar.ics'})

    def test_output_limits_origin_and_no_arbitrary_path_argument(self):
        self.write(*(f'UID:{index}\nDTSTART:20260914T180000Z' for index in range(101)))
        with self.assertRaises(ValueError):
            self.events()
        executor = ToolExecutor(register_calendar(ToolRegistry(), self.source))
        authority = AuthorityContext(True, frozenset({'calendar.read'}))
        for origin in (RequestOrigin.MEMORY, RequestOrigin.EXTERNAL):
            denied = executor.execute(ToolCall('calendar_list', origin=origin), authority=authority)
            self.assertEqual(denied.failure.code, 'authority_denied')
        rejected = executor.execute(ToolCall('calendar_list', {'path': '/etc/passwd'}), authority=authority)
        self.assertEqual(rejected.failure.code, 'invalid_arguments')

    def test_configuration_root_fallback_and_missing_root(self):
        env = {'IRIS_PROVIDER_URL': 'http://localhost:8000', 'IRIS_MODEL': 'test',
               'IRIS_CALENDAR_PATH': 'calendar.ics'}
        with self.assertRaises(ValueError):
            create_brain(load_config(env))
        configured = load_config(dict(env, IRIS_WORKSPACE_ROOT=str(self.root)))
        self.assertEqual(configured.calendar_root, str(self.root))
        self.assertIn('calendar_list', {s.name for s in create_brain(configured)._tool_executor.specifications()})

    def test_invalid_calendar_in_terminal_returns_no_partial_events(self):
        self.write('UID:ok\nDTSTART:20260914T180000Z\nSUMMARY:Should not leak partial result',
                   'UID:bad\nDTSTART:20260230T180000Z')
        with patch('builtins.input', side_effect=['/calendar', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as out:
            chat(self.brain())
        self.assertIn('Calendar unavailable', out.getvalue())
        self.assertNotIn('Should not leak partial result', out.getvalue())

    def test_missing_config_and_natural_proposal(self):
        with patch('builtins.input', side_effect=['/calendar', '/exit']), patch('sys.stdout', new_callable=io.StringIO) as out:
            chat(Mock())
        self.assertIn('Calendar unavailable', out.getvalue())
        from iris.brain.llm import LLMResponse, LLMToolCall
        self.write('UID:x\nDTSTART:20260914T180000Z')
        brain = self.brain()
        responses = [LLMResponse('', 'terminal', 'test', tool_calls=(LLMToolCall('c', 'calendar_list', {'period': 'today'}),)), LLMResponse('Events', 'terminal', 'test')]
        with patch.object(brain._llm_registry, 'generate', side_effect=responses), patch('builtins.input') as approve:
            result = brain.respond('Show my calendar events today')
        approve.assert_not_called()
        self.assertIsNone(result.tool_result.failure)


if __name__ == '__main__':
    unittest.main()

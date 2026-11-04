"""Explicit local commands, partial routine results and zero-model dispatch."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.desktop.commands import DesktopCommands
from iris.desktop.runtime import DesktopRuntime
from iris.desktop.action_tools import DesktopActionTools
from iris.tools import Approval, ToolExecutor, ResultStatus
from iris.tools.authority import evaluate
from iris.tools.models import ToolResult, ToolFailure, FailureCode
from tests.test_desktop import FakeBrain


class Controls:
    def __init__(self):
        self.calls = []
        self.percent, self.muted = 50, False

    def open_app(self, alias):
        self.calls.append(('app', alias))
        if alias == 'obsidian':
            raise RuntimeError('not installed')
        return {'state': 'visible', 'verified': True, 'detail': alias + ' has a visible window.'}

    def open_folder(self, path):
        self.calls.append(('folder', Path(path)))
        return {'state': 'requested', 'verified': False, 'detail': 'Sent the folder to File Explorer; its location was not verified.'}

    def volume(self, percent=None, muted=None):
        self.calls.append(('volume', percent, muted))
        if percent is not None:
            self.percent = percent
        if muted is not None:
            self.muted = muted
        return {'percent': self.percent, 'muted': self.muted, 'verified': True}


class InlineExecutor(ToolExecutor):
    """Keep rendering-test spies in process; action_tools tests use real workers."""
    def execute(self, call, *, authority, approve):
        preview = super().execute(call, authority=authority, dry_run=True)
        if preview.status != ResultStatus.PREVIEW:
            return preview
        plan = preview.plan
        if evaluate(plan, authority).needs_approval:
            decision = approve(plan) if approve else None
            if not decision or not decision.approved or decision.plan_id != plan.id:
                return ToolResult(ResultStatus.FAILED, plan, failure=ToolFailure(FailureCode.APPROVAL_REJECTED, 'This execution was not approved.'))
        _, handler = self._registry._resolve(call.name)
        return ToolResult(ResultStatus.SUCCESS, plan, value=handler(**dict(plan.arguments)))


class DesktopCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brain, self.controls = FakeBrain(), Controls()
        self.app = DesktopRuntime(settings={'IRIS_MODEL': 'synthetic', 'IRIS_PROVIDER_URL': 'http://127.0.0.1:9',
            'IRIS_WORKSPACE_ROOT': str(self.root), 'IRIS_AUTO_ORGANIZE_ENABLED': 'false'},
            data_dir=self.root / 'data', brain=self.brain)
        self.app.desktop_commands._actions = DesktopActionTools(self.root,
            approve=lambda plan: Approval(plan.id, True), controls_factory=lambda: self.controls,
            executor_factory=InlineExecutor)
        self.commands = self.app.desktop_commands
        self.addCleanup(self.app.close)

    def test_direct_action_bypasses_model_and_organizer_but_keeps_evidence(self):
        with patch.object(self.app.autonomy, 'submit') as organize:
            result = self.app.chat('Hey IRIS, could you please open Chrome?')
        self.assertEqual(result['route'], 'LOCAL')
        self.assertIn('visible window', result['reply'])
        self.assertEqual(self.controls.calls, [('app', 'chrome')])
        self.assertEqual(self.brain.calls, [])
        organize.assert_not_called()
        self.assertEqual(self.app.history, [])  # Local evidence must not become cloud context.
        self.assertTrue(result['actions'][0]['verified'])
        self.assertEqual(result['actions'][0]['detail'], result['reply'])
        self.assertEqual(self.app.last_route, 'LOCAL')
        self.assertFalse(self.app.turn_lock.locked())

    def test_quotes_negation_extra_steps_and_unknown_programs_do_not_launch(self):
        for text in ['Do not open Chrome', '"open Chrome"', 'My note says open Chrome',
                     'Open Chrome and delete my notes', 'Open powershell', 'Launch cmd.exe',
                     'Open Chrome https://example.com', 'Open Chrome --remote-debugging-port=9222']:
            with self.subTest(text=text):
                self.assertIsNone(self.commands.handle(text))
        self.assertEqual(self.controls.calls, [])

    def test_council_cannot_invoke_desktop_commands(self):
        self.app.chat('Open Chrome', mode='council')
        self.assertEqual(self.controls.calls, [])
        self.assertEqual(len(self.brain.calls), 1)

    def test_runtime_approval_is_exact_and_declining_prevents_action(self):
        self.commands._actions._approve = self.app._tool_approval
        with patch.object(self.app, 'approve', return_value=False) as approve:
            result = self.app.chat('Set volume to forty-five percent')
        self.assertEqual(self.controls.calls, [])
        self.assertIn('not approved', result['reply'])
        self.assertIn('45 percent', approve.call_args.args[0])
        self.assertNotIn('Authority:', approve.call_args.args[0])

    def test_workspace_reports_partial_failure_and_unverified_folder(self):
        result = self.app.chat('IRIS, start my workspace')
        self.assertEqual(self.controls.calls, [('app', 'chrome'), ('app', 'obsidian'), ('folder', self.root)])
        self.assertEqual([item['state'] for item in result['actions']], ['visible', 'failed', 'requested'])
        self.assertIn('Obsidian: Could not open', result['reply'])
        self.assertIn('location was not verified', result['reply'])
        self.assertEqual(self.brain.calls, [])

    def test_spoken_volume_values_readback_mute_and_invalid_values(self):
        self.assertIn('45 percent', self.app.chat('Set volume to forty-five percent')['reply'])
        self.assertIn('55 percent', self.app.chat('Volume up')['reply'])
        self.assertIn('muted', self.app.chat('Mute my computer')['reply'])
        before = len(self.controls.calls)
        for value in ('101', '-1', 'forty elephants'):
            self.assertIn('unchanged', self.app.chat('Set volume to ' + value)['reply'])
        self.assertEqual(len(self.controls.calls), before)
        with patch.object(self.controls, 'volume', return_value={'percent': 55, 'muted': True, 'verified': False}):
            self.assertIn('did not confirm', self.app.chat('Set volume to 20')['reply'])
        self.assertEqual(self.brain.calls, [])

    def test_find_stays_in_roots_hides_secret_files_and_has_short_spoken_reply(self):
        (self.root / 'report.md').write_text('Synthetic content', encoding='utf8')
        (self.root / '.report.md').write_text('Hidden', encoding='utf8')
        (self.root / 'report-api-key.txt').write_text('Hidden', encoding='utf8')
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'report-two.txt').write_text('Synthetic content', encoding='utf8')
        result = self.app.chat('Find files named report')
        self.assertIn('report.md', result['reply'])
        self.assertIn('report-two.txt', result['reply'])
        self.assertNotIn('.report.md', result['reply'])
        self.assertNotIn('api-key', result['reply'])
        self.assertNotIn('Synthetic content', result['reply'])
        self.assertNotIn('report.md', result['spoken_reply'])
        self.assertEqual(self.brain.calls, [])

    def test_briefing_no_model_and_missing_calendar_is_explicit(self):
        result = self.app.chat('Give me my daily briefing')
        self.assertIn('0 overdue tasks', result['reply'])
        self.assertIn('calendar is not connected', result['reply'])
        self.assertEqual(self.brain.calls, [])

    def test_search_is_bounded_even_with_many_directories(self):
        listing = {'truncated': False, 'entries': [{'name': str(i), 'type': 'directory'} for i in range(30)]}
        with patch('iris.desktop.commands.list_files', return_value=listing) as read:
            result = self.commands.handle('Find files named report')
        self.assertLessEqual(read.call_count, 80)
        self.assertIn('search was limited', result['reply'])


if __name__ == '__main__':
    unittest.main()

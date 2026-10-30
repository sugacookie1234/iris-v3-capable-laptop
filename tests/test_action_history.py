"""No-content receipts, real permission gates, retention and restart recovery."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.desktop.action_history import ActionHistory
from iris.desktop.action_tools import DesktopActionTools
from iris.tools import Approval, AuthorityLevel, RequestOrigin, ToolCall, ToolExecutor, ToolRegistry, ToolSpec
from iris.tools.models import ExecutionPlan, ToolResult, ToolFailure, FailureCode, ResultStatus
from tests.test_desktop_action_tools import FakeControls


def fake_read():
    return {'verified': True, 'private_text': 'private-result-sentinel'}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'receipts.sqlite3'
        self.now = datetime(2026, 10, 28, 16, tzinfo=timezone.utc)
        self.history = ActionHistory(self.path, clock=lambda: self.now)

    def actions(self, approve=None):
        return DesktopActionTools(self.temp.name, self.temp.name, approve=approve,
            history=self.history, controls_factory=FakeControls)

    def test_real_executor_records_denials_and_verified_readback(self):
        tools = self.actions(lambda plan: Approval(plan.id, False))
        tools.run('desktop_open_app', app='chrome')
        row = self.history.rows()[0]
        self.assertEqual((row['approval'], row['verification']), ('rejected', 'not_executed'))
        tools.run('desktop_volume_read')
        row = self.history.rows()[0]
        self.assertEqual((row['approval'], row['verification']), ('not_required', 'verified'))
        self.assertIn('verified', self.history.report('America/New_York'))

    def test_partial_routine_and_folder_are_never_claimed_verified(self):
        tools = self.actions(lambda plan: Approval(plan.id, True))
        tools.run('desktop_start_workspace')
        row = self.history.rows()[0]
        self.assertEqual(row['verification'], 'partial')
        self.assertEqual(row['components'], {'Chrome': 'verified', 'Obsidian': 'failed', 'Workspace folder': 'unverified'})
        tools.run('desktop_open_folder', folder='vault')
        self.assertEqual(self.history.rows()[0]['verification'], 'unverified')
        self.assertNotIn(self.temp.name, json.dumps(self.history.rows()))

    def test_no_arguments_result_content_unknown_name_or_failure_text_persist(self):
        tools = self.actions()
        tools.run('desktop_open_app', app='private-argument-sentinel')
        tools.run('private-tool-sentinel')
        registry = ToolRegistry()
        # This checks receipt privacy, not worker startup speed. Leave room for
        # Windows spawn under full-suite load; timeout behavior has its own tests.
        registry.register(ToolSpec('safe_read', 'Read fixture', AuthorityLevel.GREEN, True, (), (), 10), fake_read)
        executor = ToolExecutor(registry)
        executor.observer = self.history
        self.history.register(executor.specifications())
        from iris.tools import AuthorityContext
        result = executor.execute(ToolCall('safe_read', {}, RequestOrigin.USER),
                                  authority=AuthorityContext(explicitly_requested=True))
        self.assertEqual(result.status, ResultStatus.SUCCESS, result.failure)
        self.assertEqual(self.history.rows()[0]['verification'], 'unverified')
        identifier = self.history.begin('safe_read', RequestOrigin.USER)
        self.history.finish(identifier, ToolResult(ResultStatus.FAILED,
            failure=ToolFailure(FailureCode.EXECUTION_FAILED, 'private-error-sentinel')))
        raw = self.path.read_bytes()
        for secret in (b'private-argument-sentinel', b'private-tool-sentinel', b'private-result-sentinel', b'private-error-sentinel'):
            self.assertNotIn(secret, raw)

    def test_dry_run_does_not_record_or_execute(self):
        tools = self.actions()
        from iris.tools import AuthorityContext
        result = tools._executor.execute(ToolCall('desktop_volume_set', {'percent': 10}, RequestOrigin.USER),
            authority=AuthorityContext(True, frozenset({'desktop.audio'})), dry_run=True)
        self.assertEqual(result.status, ResultStatus.PREVIEW)
        self.assertEqual(self.history.rows(), [])

    def test_observation_failure_cannot_bypass_approval_or_change_result(self):
        tools = self.actions(lambda plan: Approval(plan.id, False))
        with patch.object(self.history, 'begin', side_effect=OSError('private-disk-error')):
            result = tools.run('desktop_open_app', app='chrome')
        self.assertEqual(result.failure.code, FailureCode.APPROVAL_REJECTED)
        self.assertTrue(tools._executor.observer_failed)

    def test_restart_preserves_unknown_effects_without_retry(self):
        identifier = self.history.begin('desktop_find_files', RequestOrigin.USER)
        self.history.approval(identifier, 'approved')
        restarted = ActionHistory(self.path, clock=lambda: self.now)
        row = restarted.rows()[0]
        self.assertEqual((row['outcome'], row['verification']), ('interrupted', 'unknown'))
        self.assertEqual(row['approval'], 'approved')

    def test_timeout_is_unknown_not_not_executed(self):
        identifier = self.history.begin('desktop_find_files', RequestOrigin.USER)
        self.history.finish(identifier, ToolResult(ResultStatus.FAILED,
            failure=ToolFailure(FailureCode.TIMEOUT, 'Effects might remain.')))
        self.assertEqual(self.history.rows()[0]['verification'], 'unknown')

    def test_retention_count_time_and_erasure(self):
        self.history.max_records = 2
        for _ in range(4):
            self.history.read_completed('desktop_find_files', lambda: 'private-read-content')
        self.assertEqual(len(self.history.rows()), 2)
        self.now += timedelta(days=31)
        self.assertEqual(self.history.rows(), [])
        self.history.begin('desktop_find_files', RequestOrigin.USER)
        self.history.clear()
        self.assertEqual(self.history.rows(), [])

    def test_today_uses_configured_timezone_and_does_not_invent_prior_activity(self):
        self.now = datetime(2026, 10, 28, 3, 55, tzinfo=timezone.utc)
        self.history.read_completed('desktop_find_files', lambda: None)
        self.now += timedelta(minutes=10)
        self.assertIn('0 recorded tool attempts today', self.history.report('America/New_York'))
        self.assertIn('1 recorded tool attempts', self.history.report('America/New_York', today=False))


if __name__ == '__main__':
    unittest.main()

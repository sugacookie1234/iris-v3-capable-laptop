import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from iris.automation import (
    AutomationRunStatus, AutomationSchedule, AutomationScheduler, AutomationStore,
)
from iris.tools import AuthorityContext, AuthorityLevel, ToolExecutor, ToolRegistry, ToolSpec
from iris.workflows import WorkflowDefinition, WorkflowExecutor, WorkflowRegistry, WorkflowStep
from iris.tools import ToolArgument, ArgumentType
from iris.terminal import _handle_automation_command, _parse_automation_schedule


def marker(path, value):
    Path(path).write_text(value, encoding="utf-8")
    return {"value": value}


def red():
    return {"ok": True}


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        tools = ToolRegistry()
        tools.register(ToolSpec("marker", "Write local fixture", AuthorityLevel.GREEN, True, (), ("fixture.write",), 10,
                                (ToolArgument("path", "path", ArgumentType.STRING), ToolArgument("value", "value", ArgumentType.STRING)), local_only=True), marker)
        tools.register(ToolSpec("red", "Needs approval", AuthorityLevel.RED, True, (), ("fixture.red",), 10, local_only=True), red)
        self.tools = ToolExecutor(tools)
        self.workflows = WorkflowRegistry()
        self.workflows.register(WorkflowDefinition("green_flow", "green", (WorkflowStep("write", "marker", (("path", str(self.root / "out")), ("value", "ok"))),), 20))
        self.workflows.register(WorkflowDefinition("red_flow", "red", (WorkflowStep("approve", "red"),), 20))
        self.executor = WorkflowExecutor(self.tools, self.workflows)
        self.store = AutomationStore(self.root / "automation.sqlite3")
        self.now = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
        self.scheduler = AutomationScheduler(self.store, self.workflows, self.executor, self.tools, clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def schedule(self, workflow, *, run_at=None, recurrence=None, enabled=False):
        return self.store.create(AutomationSchedule.new(workflow, run_at or (self.now - timedelta(minutes=1)).isoformat(), recurrence, enabled, self.now.isoformat()))

    def test_disabled_by_default_and_enable_disable(self):
        schedule = self.schedule("green_flow")
        self.assertFalse(schedule.enabled)
        self.assertEqual(self.scheduler.run_once(at=self.now), ())
        self.store.set_enabled(schedule.id, True)
        ticks = self.scheduler.run_once(at=self.now)
        self.assertEqual(ticks[0].status, AutomationRunStatus.SUCCESS)
        self.assertTrue((self.root / "out").exists())
        self.store.set_enabled(schedule.id, False)
        self.assertFalse(self.store.fetch(schedule.id).enabled)

    def test_one_time_persists_history_and_does_not_repeat(self):
        schedule = self.store.create(AutomationSchedule.new("green_flow", (self.now - timedelta(seconds=1)).isoformat(), enabled=True, now=self.now.isoformat()))
        first = self.scheduler.run_once(at=self.now)
        self.assertEqual(first[0].status, AutomationRunStatus.SUCCESS)
        self.assertEqual(len(self.store.executions(schedule.id)), 1)
        self.assertFalse(self.store.fetch(schedule.id).enabled)
        self.assertEqual(self.scheduler.run_once(at=self.now + timedelta(hours=1)), ())

    def test_recurring_runs_each_occurrence_without_raw_conversation(self):
        schedule = self.schedule("green_flow", recurrence=60, enabled=True)
        first = self.scheduler.run_once(at=self.now)
        second = self.scheduler.run_once(at=self.now + timedelta(seconds=61))
        self.assertEqual([tick.status for tick in first + second], [AutomationRunStatus.SUCCESS, AutomationRunStatus.SUCCESS])
        self.assertEqual(len(self.store.executions(schedule.id)), 2)

    def test_dry_run_never_calls_handler_or_persists(self):
        schedule = self.schedule("green_flow", enabled=True)
        ticks = self.scheduler.run_once(at=self.now, dry_run=True)
        self.assertEqual(ticks[0].status, AutomationRunStatus.DRY_RUN)
        self.assertFalse((self.root / "out").exists())
        self.assertEqual(self.store.executions(schedule.id), ())

    def test_red_creates_pending_approval_and_never_executes(self):
        schedule = self.schedule("red_flow", enabled=True)
        ticks = self.scheduler.run_once(at=self.now)
        self.assertEqual(ticks[0].status, AutomationRunStatus.PENDING_APPROVAL)
        self.assertEqual(len(self.store.pending_approvals()), 1)
        self.assertEqual(self.store.pending_approvals()[0].details, (("approve", "RED"),))

    def test_approval_executes_exact_stored_proposal_once(self):
        schedule = self.schedule("red_flow", enabled=True)
        self.scheduler.run_once(at=self.now)
        approval = self.store.pending_approvals()[0]
        try:
            self.scheduler.approve(approval.id, at=self.now + timedelta(minutes=1))
        except ValueError as exc:
            run = self.store.execution(schedule.id, approval.occurrence)
            self.fail(f"{exc}; recorded failure: {run.failure}")
        self.assertEqual(self.store.approval(approval.id).status, "approved")
        self.assertEqual(self.store.execution(schedule.id, approval.occurrence).status, AutomationRunStatus.APPROVED)
        with self.assertRaisesRegex(ValueError, "no longer pending"):
            self.scheduler.approve(approval.id, at=self.now + timedelta(minutes=2))

    def test_reject_and_expire_never_execute_and_are_audited(self):
        rejected_schedule = self.schedule("red_flow", enabled=True)
        self.scheduler.run_once(at=self.now)
        rejected = self.store.pending_approvals()[0]
        self.scheduler.reject(rejected.id, at=self.now + timedelta(minutes=1))
        self.assertEqual(self.store.approval(rejected.id).status, "rejected")
        self.assertEqual(self.store.execution(rejected_schedule.id, rejected.occurrence).status, AutomationRunStatus.REJECTED)
        expired_schedule = self.schedule("red_flow", run_at=(self.now + timedelta(seconds=1)).isoformat(), enabled=True)
        self.scheduler.run_once(at=self.now + timedelta(seconds=2))
        expired = self.store.pending_approvals()[0]
        self.scheduler.run_once(at=self.now + timedelta(days=2))
        self.assertEqual(self.store.approval(expired.id).status, "expired")
        self.assertEqual(self.store.execution(expired_schedule.id, expired.occurrence).status, AutomationRunStatus.EXPIRED)
        with self.assertRaisesRegex(ValueError, "no longer pending"):
            self.scheduler.approve(expired.id, at=self.now + timedelta(days=2))

    def test_approved_worker_timeout_is_failed_not_approved_and_cannot_replay(self):
        """Exercise real approval code with a deterministic nonresponsive worker.

        Startup/import scheduling is outside the approval contract. Force the
        process boundary outcome without sleeping or relaxing its time budget.
        """
        schedule = self.schedule("red_flow", enabled=True)
        self.scheduler.run_once(at=self.now)
        approval = self.store.pending_approvals()[0]
        receiver, sender, process = Mock(), Mock(), Mock()
        receiver.poll.return_value = False
        process.is_alive.return_value = False
        context = Mock()
        context.Pipe.return_value = (receiver, sender)
        context.Process.return_value = process
        with patch("iris.tools.executor.multiprocessing.get_context", return_value=context):
            with self.assertRaisesRegex(ValueError, "Approved workflow failed safely"):
                self.scheduler.approve(approval.id, at=self.now + timedelta(minutes=1))
            run = self.store.execution(schedule.id, approval.occurrence)
            self.assertEqual(run.status, AutomationRunStatus.FAILED)
            self.assertIn("Tool timed out", run.failure)
            self.assertEqual(self.store.approval(approval.id).status, "failed")
            with self.assertRaisesRegex(ValueError, "no longer pending"):
                self.scheduler.approve(approval.id, at=self.now + timedelta(minutes=2))
        process.start.assert_called_once()
        receiver.poll.assert_called_once_with(10)
        receiver.close.assert_called_once()
        process.close.assert_called_once()

    def test_schedule_validation_and_future_time(self):
        with self.assertRaises(ValueError):
            AutomationSchedule.new("bad-name", self.now.isoformat())
        with self.assertRaises(ValueError):
            AutomationSchedule.new("green_flow", "2026-09-17T12:00:00")
        future = self.schedule("green_flow", run_at=(self.now + timedelta(hours=1)).isoformat(), enabled=True)
        self.assertEqual(self.scheduler.run_once(at=self.now), ())
        self.assertEqual(self.store.executions(future.id), ())

    def test_schedule_parser_timezone_daily_interval_and_invalid_rules(self):
        run_at, recurrence = _parse_automation_schedule(
            "daily 08:30", "America/Toronto", now=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
        self.assertEqual(recurrence, 86400)
        self.assertTrue(run_at.endswith("Z"))
        run_at, recurrence = _parse_automation_schedule(
            "every 15m", "America/Toronto", now=self.now)
        self.assertEqual(recurrence, 900)
        self.assertTrue(run_at.endswith("Z"))
        with self.assertRaises(ValueError):
            _parse_automation_schedule("every 0s", "America/Toronto", now=self.now)
        with self.assertRaises(ValueError):
            _parse_automation_schedule("daily nope", "America/Toronto", now=self.now)

    def test_terminal_schedule_commands_preview_confirm_and_mutate(self):
        class Brain:
            _workflow_registry = self.workflows
            _workflow_executor = self.executor
            _tool_executor = self.tools
            _automation_scheduler = self.scheduler
            _chat_config = type("Config", (), {"timezone": "America/Toronto"})()
        brain = Brain()
        with patch("builtins.input", return_value="yes"):
            self.assertTrue(_handle_automation_command(
                "/automation-create green_flow every 5m", brain, self.store))
        schedules = self.store.list()
        self.assertEqual(len(schedules), 1)
        self.assertFalse(schedules[0].enabled)
        with patch("builtins.input", return_value="y"):
            _handle_automation_command(f"/automation-edit {schedules[0].id} enabled", brain, self.store)
        self.assertTrue(self.store.fetch(schedules[0].id).enabled)
        with patch("builtins.input", return_value="y"):
            _handle_automation_command(f"/automation-delete {schedules[0].id}", brain, self.store)
        self.assertIsNone(self.store.fetch(schedules[0].id))


if __name__ == "__main__":
    unittest.main()

"""Workflow tests use registered local fake tools and disposable stores only."""
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from iris.briefing import BRIEFING_PERMISSION, register_briefing
from iris.calendar import CalendarSource
from iris.goals.store import GoalStore
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore
from iris.tasks.store import TaskStore
from iris.tools import (
    Approval, ArgumentType, AuthorityContext, AuthorityLevel, FailureCode,
    ResultStatus, ToolArgument, ToolCall, ToolExecutor, ToolRegistry, ToolSpec,
)
from iris.workflows import (
    WorkflowDefinition, WorkflowExecutor, WorkflowRegistry, WorkflowStatus,
    WorkflowStep, daily_briefing_workflow, register_builtin_workflows,
)


def marker_tool(path, value):
    Path(path).write_text(value, encoding="utf-8", newline="")
    return {"written": value}


def read_marker_tool(path):
    return Path(path).read_text(encoding="utf-8")


def fail_tool():
    raise RuntimeError("fake failure detail")


def red_echo_tool():
    return {"red": True}


def slow_tool():
    time.sleep(1)
    return {"finished": True}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = ToolRegistry()
        self.registry.register(ToolSpec(
            "marker", "Write a disposable fixture marker", AuthorityLevel.GREEN, True,
            ("Writes a test fixture.",), ("fixture.write",), 2,
            (ToolArgument("path", "Marker path", ArgumentType.STRING),
             ToolArgument("value", "Marker value", ArgumentType.STRING)), local_only=True,
        ), marker_tool)
        self.registry.register(ToolSpec(
            "read_marker", "Read a disposable fixture marker", AuthorityLevel.YELLOW, True,
            (), ("fixture.read",), 2,
            (ToolArgument("path", "Marker path", ArgumentType.STRING),), local_only=True,
        ), read_marker_tool)
        self.registry.register(ToolSpec(
            "red_echo", "Explicitly approved fake RED step", AuthorityLevel.RED, True,
            (), ("fixture.red",), 2, local_only=True,
        ), red_echo_tool)
        self.registry.register(ToolSpec(
            "fail", "Fail safely", AuthorityLevel.GREEN, True, (), ("fixture.read",), 2, local_only=True,
        ), fail_tool)
        self.registry.register(ToolSpec(
            "slow", "Time out safely", AuthorityLevel.GREEN, True, (), ("fixture.read",), 0.05, local_only=True,
        ), slow_tool)
        self.workflows = WorkflowRegistry()
        self.executor = WorkflowExecutor(ToolExecutor(self.registry), self.workflows)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_is_required_and_has_no_handler_effects(self):
        marker = self.root / "marker.txt"
        self.workflows.register(WorkflowDefinition(
            "preview_only", "Preview before writing.",
            (WorkflowStep("write_marker", "marker", (("path", str(marker)), ("value", "ready"))),),
            timeout_seconds=2,
        ))
        authority = AuthorityContext(True, frozenset({"fixture.write"}))
        preview = self.executor.preview("preview_only", authority=authority)
        self.assertEqual(preview.status, WorkflowStatus.PREVIEW)
        self.assertEqual([step.result.status for step in preview.steps], [ResultStatus.PREVIEW])
        self.assertFalse(marker.exists())
        with self.assertRaisesRegex(ValueError, "successful workflow dry-run preview"):
            self.executor.execute("not a preview", authority=authority)
        result = self.executor.execute(preview, authority=authority)
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(result.steps[0].result.value, {"written": "ready"})
        self.assertEqual(marker.read_text(encoding="utf-8"), "ready")
        with self.assertRaisesRegex(ValueError, "unknown, stale"):
            self.executor.execute(preview, authority=authority)

    def test_green_workflow_still_requires_explicit_user_request_or_confirmation(self):
        marker = self.root / "green-marker.txt"
        self.workflows.register(WorkflowDefinition(
            "green_authority", "Respect the GREEN explicit-request rule.",
            (WorkflowStep("write", "marker", (("path", str(marker)), ("value", "authorized"))),),
            timeout_seconds=2,
        ))
        authority = AuthorityContext(False, frozenset({"fixture.write"}))
        preview = self.executor.preview("green_authority", authority=authority)
        paused = self.executor.execute(preview, authority=authority)
        self.assertEqual(paused.status, WorkflowStatus.PAUSED)
        self.assertFalse(marker.exists())
        result = self.executor.execute(
            preview, authority=authority,
            approve=lambda plan: Approval(plan.id, True),
        )
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(marker.read_text(encoding="utf-8"), "authorized")

    def test_yellow_pauses_before_any_work_then_approves_each_non_green_step(self):
        marker = self.root / "marker.txt"
        self.workflows.register(WorkflowDefinition(
            "approval_steps", "Exercise ordered YELLOW and RED approval.",
            (
                WorkflowStep("write", "marker", (("path", str(marker)), ("value", "first"))),
                WorkflowStep("read", "read_marker", (("path", str(marker)),)),
                WorkflowStep("red", "red_echo"),
            ), timeout_seconds=7,
        ))
        authority = AuthorityContext(True, frozenset({"fixture.write", "fixture.read", "fixture.red"}))
        preview = self.executor.preview("approval_steps", authority=authority)
        paused = self.executor.execute(preview, authority=authority)
        self.assertEqual(paused.status, WorkflowStatus.PAUSED)
        self.assertEqual(paused.failure.code, FailureCode.APPROVAL_REQUIRED)
        self.assertFalse(marker.exists())

        approved_authorities = []
        def approve(plan):
            approved_authorities.append(plan.spec.authority)
            return Approval(plan.id, True)

        result = self.executor.execute(preview, authority=authority, approve=approve)
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(approved_authorities, [AuthorityLevel.YELLOW, AuthorityLevel.RED])
        self.assertEqual([step.step_name for step in result.steps], ["write", "read", "red"])
        self.assertEqual(result.steps[1].result.value, "first")
        self.assertIn("approval_granted", [event.event for event in result.audit])
        self.assertTrue(all(event.step_name is None or event.tool_name is not None
                            for event in result.audit))

    def test_denial_or_failure_stops_without_running_later_steps(self):
        marker = self.root / "after-failure.txt"
        self.workflows.register(WorkflowDefinition(
            "stop_after_failure", "Stop after a failed first step.",
            (WorkflowStep("fail", "fail"),
             WorkflowStep("later", "marker", (("path", str(marker)), ("value", "bad")))),
            timeout_seconds=4,
        ))
        authority = AuthorityContext(True, frozenset({"fixture.read", "fixture.write"}))
        preview = self.executor.preview("stop_after_failure", authority=authority)
        result = self.executor.execute(preview, authority=authority)
        self.assertEqual(result.status, WorkflowStatus.FAILED)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.failure.code, FailureCode.EXECUTION_FAILED)
        self.assertFalse(marker.exists())

    def test_timeout_stops_workflow_and_is_recorded(self):
        marker = self.root / "after-timeout.txt"
        self.workflows.register(WorkflowDefinition(
            "timeout_stop", "Stop when a tool times out.",
            (WorkflowStep("slow", "slow"),
             WorkflowStep("later", "marker", (("path", str(marker)), ("value", "bad")))),
            timeout_seconds=3,
        ))
        authority = AuthorityContext(True, frozenset({"fixture.read", "fixture.write"}))
        preview = self.executor.preview("timeout_stop", authority=authority)
        result = self.executor.execute(preview, authority=authority)
        self.assertEqual(result.status, WorkflowStatus.FAILED)
        self.assertEqual(result.failure.code, FailureCode.TIMEOUT)
        self.assertEqual(result.steps[0].result.failure.code, FailureCode.TIMEOUT)
        self.assertFalse(marker.exists())

    def test_unregistered_tool_and_unbounded_workflow_are_rejected(self):
        self.workflows.register(WorkflowDefinition(
            "unregistered", "References no executable code.", (WorkflowStep("missing", "not_registered"),),
        ))
        with self.assertRaisesRegex(ValueError, "unregistered tool"):
            self.executor.preview("unregistered", authority=AuthorityContext())
        with self.assertRaisesRegex(ValueError, "at most 16 steps"):
            WorkflowDefinition("too_many", "Too many steps.",
                              tuple(WorkflowStep(f"step_{i}", "fail") for i in range(17)))
        with self.assertRaisesRegex(ValueError, "at most 300"):
            WorkflowDefinition("too_long", "Too long.", (WorkflowStep("step", "fail"),), 301)
        with self.assertRaisesRegex(ValueError, "finite JSON scalar"):
            WorkflowStep("python", "fail", (("callback", lambda: None),))

    def test_workflows_reject_tools_not_explicitly_declared_local_only(self):
        self.registry.register(ToolSpec(
            "network_lookup", "Fake external lookup", AuthorityLevel.GREEN, True,
            (), ("network.read",), 1,
        ), red_echo_tool)
        self.workflows.register(WorkflowDefinition(
            "external", "Must remain unavailable to workflows.",
            (WorkflowStep("lookup", "network_lookup"),), timeout_seconds=1,
        ))
        with self.assertRaisesRegex(ValueError, "not declared local-only"):
            self.executor.preview("external", authority=AuthorityContext(True, frozenset({"network.read"})))

    def test_daily_briefing_workflow_reads_existing_local_sources(self):
        task_path, goal_path, memory_path = (self.root / name for name in
                                             ("tasks.sqlite3", "goals.sqlite3", "memory.sqlite3"))
        due_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        target_date = (date.today() + timedelta(days=3)).isoformat()
        with TaskStore(task_path) as tasks:
            tasks.create("Review IRIS milestone", due_at=due_at)
        with GoalStore(goal_path) as goals:
            goals.create("Finish IRIS milestone", category="project", target_date=target_date)
        with MemoryStore(memory_path) as memories:
            memories.insert(MemoryItem(
                MemoryCategory.PROJECT, "user", "iris", "IRIS", "Project IRIS context is important.",
                "test", confirmation=MemoryConfirmation.CONFIRMED,
            ))
        calendar_root = self.root / "calendar"
        calendar_root.mkdir()
        (calendar_root / "today.ics").write_text(
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//IRIS workflow test//EN\r\nEND:VCALENDAR\r\n",
            encoding="utf-8",
         newline="")
        tools = ToolRegistry()
        register_briefing(tools, task_path=str(task_path), goal_path=str(goal_path),
                          memory_path=str(memory_path), calendar=CalendarSource(str(calendar_root), "today.ics"))
        workflows = register_builtin_workflows(WorkflowRegistry())
        self.assertEqual(daily_briefing_workflow().name, "daily_briefing_workflow")
        executor = WorkflowExecutor(ToolExecutor(tools), workflows)
        authority = AuthorityContext(True, frozenset({BRIEFING_PERMISSION}))
        preview = executor.preview("daily_briefing_workflow", authority=authority)
        self.assertEqual(preview.status, WorkflowStatus.PREVIEW)
        result = executor.execute(preview, authority=authority)
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        briefing = result.steps[0].result.value
        self.assertTrue(briefing["facts"]["calendar_configured"])
        self.assertEqual(briefing["deadlines"][0]["title"], "Review IRIS milestone")
        self.assertEqual(briefing["facts"]["active_goals"][0]["title"], "Finish IRIS milestone")
        self.assertTrue(any("Project IRIS context" in text for text in briefing["facts"]["permitted_memories"]))


if __name__ == "__main__":
    unittest.main()

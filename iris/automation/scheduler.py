"""Foreground, opt-in scheduler for registered local workflows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Callable
from uuid import uuid4

from iris.automation.models import AutomationApproval, AutomationRun, AutomationRunStatus, AutomationSchedule
from iris.automation.store import AutomationStore
from iris.tools import AuthorityContext, AuthorityLevel, ToolExecutor
from iris.tools import Approval, FailureCode
from iris.workflows import WorkflowExecutor, WorkflowRegistry, WorkflowStatus


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Scheduler time must include a timezone.")
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AutomationTick:
    schedule_id: str
    occurrence: str
    status: AutomationRunStatus
    run: AutomationRun | None
    preview: object | None = None


class AutomationScheduler:
    """Run due schedules only when the host explicitly calls ``run_once``."""

    def __init__(self, store: AutomationStore, workflows: WorkflowRegistry,
                 workflow_executor: WorkflowExecutor, tools: ToolExecutor,
                 *, clock: Callable[[], datetime] | None = None):
        self.store = store
        self.workflows = workflows
        self.executor = workflow_executor
        self.tools = tools
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _occurrence(self, schedule: AutomationSchedule, at: datetime) -> datetime | None:
        now = _utc(at)
        start = datetime.fromisoformat(schedule.run_at.replace("Z", "+00:00"))
        if now < start:
            return None
        if schedule.recurrence_seconds is None:
            return start
        elapsed = int((now - start).total_seconds())
        return start + timedelta(seconds=(elapsed // schedule.recurrence_seconds) * schedule.recurrence_seconds)

    def _authority(self, workflow_name: str) -> AuthorityContext:
        definition = self.workflows.get(workflow_name)
        specs = {item.name: item for item in self.tools.specifications()}
        permissions: set[str] = set()
        for step in definition.steps:
            spec = specs.get(step.tool_name)
            if spec is None:
                raise ValueError(f"Workflow step {step.name} references an unregistered tool.")
            permissions.update(spec.required_permissions)
        return AuthorityContext(True, frozenset(permissions))

    def run_once(self, *, at: datetime | None = None, dry_run: bool = False) -> tuple[AutomationTick, ...]:
        """Evaluate each enabled schedule once; no background thread is created."""
        now = _utc(at or self.clock())
        now_stamp = _stamp(now)
        for expired in self.store.expire_approvals(now_stamp):
            run = self.store.execution(expired.schedule_id, expired.occurrence)
            if run is not None and run.status == AutomationRunStatus.PENDING_APPROVAL:
                self.store.update_execution(AutomationRun(run.id, run.schedule_id, run.occurrence,
                    run.workflow_name, AutomationRunStatus.EXPIRED, run.workflow_id,
                    run.started_at, now_stamp, "Approval expired."))
        ticks: list[AutomationTick] = []
        for schedule in self.store.list(enabled=True):
            occurrence = self._occurrence(schedule, now)
            if occurrence is None:
                continue
            occurrence_stamp = _stamp(occurrence)
            if self.store.execution(schedule.id, occurrence_stamp) is not None:
                continue
            try:
                authority = self._authority(schedule.workflow_name)
                preview = self.executor.preview(schedule.workflow_name, authority=authority)
            except (KeyError, ValueError) as exc:
                if dry_run:
                    ticks.append(AutomationTick(schedule.id, occurrence_stamp,
                                                AutomationRunStatus.FAILED, None, str(exc)))
                    continue
                started = _stamp(now)
                result = self.executor_result(schedule, occurrence_stamp, AutomationRunStatus.FAILED,
                                              None, started, "Workflow could not be prepared safely.", now)
                self.store.record_execution(result)
                if schedule.recurrence_seconds is None:
                    self.store.set_enabled(schedule.id, False)
                ticks.append(AutomationTick(schedule.id, occurrence_stamp,
                                            AutomationRunStatus.FAILED, result, None))
                continue
            if dry_run:
                ticks.append(AutomationTick(schedule.id, occurrence_stamp,
                                            AutomationRunStatus.DRY_RUN, None, preview))
                continue
            started = _stamp(now)
            if preview.status != WorkflowStatus.PREVIEW:
                status = AutomationRunStatus.FAILED
                failure = preview.failure.message if preview.failure else "Workflow preview failed."
                result = self.executor_result(schedule, occurrence_stamp, status, preview.workflow_id, started, failure, now)
                ticks.append(AutomationTick(schedule.id, occurrence_stamp, status, result, preview))
                continue
            result_workflow = self.executor.execute(preview, authority=authority)
            status = (AutomationRunStatus.SUCCESS if result_workflow.status == WorkflowStatus.SUCCESS
                      else AutomationRunStatus.PENDING_APPROVAL if result_workflow.status == WorkflowStatus.PAUSED
                      else AutomationRunStatus.TIMEOUT if result_workflow.failure and result_workflow.failure.code == FailureCode.TIMEOUT
                      else AutomationRunStatus.FAILED)
            failure = result_workflow.failure.message if result_workflow.failure else None
            result = self.executor_result(schedule, occurrence_stamp, status, result_workflow.workflow_id, started, failure, now)
            self.store.record_execution(result)
            if status == AutomationRunStatus.PENDING_APPROVAL:
                details = tuple((step.step_name, step.authority.value) for step in result_workflow.steps
                                if step.authority != AuthorityLevel.GREEN)
                proposal = []
                for step in result_workflow.steps:
                    plan = step.result.plan
                    if plan is None:
                        continue
                    proposal.append((step.step_name, json.dumps({
                        "tool_name": step.tool_name, "arguments": dict(plan.arguments),
                        "authority": step.authority.value, "reversible": plan.spec.reversible,
                        "side_effects": plan.spec.side_effects,
                        "required_permissions": plan.spec.required_permissions,
                        "timeout": plan.spec.timeout,
                    }, sort_keys=True)))
                expires = _stamp(now + timedelta(hours=24))
                self.store.add_approval(AutomationApproval(str(uuid4()), schedule.id, result.id,
                                                           schedule.workflow_name, occurrence_stamp,
                                                           started, details,
                                                           definition_signature=result_workflow.definition_signature,
                                                           permissions=tuple(sorted(authority.permissions)),
                                                           explicitly_requested=authority.explicitly_requested,
                                                           proposal=tuple(proposal), expires_at=expires))
            if schedule.recurrence_seconds is None:
                self.store.set_enabled(schedule.id, False)
            ticks.append(AutomationTick(schedule.id, occurrence_stamp, status, result, result_workflow))
        return tuple(ticks)

    def reject(self, approval_id: str, *, at: datetime | None = None):
        now = _stamp(_utc(at or self.clock()))
        approval = self.store.approval(approval_id)
        if approval is None:
            raise ValueError("Automation approval not found.")
        if approval.status != "pending":
            raise ValueError("Automation approval is no longer pending.")
        if approval.expires_at and approval.expires_at <= now:
            resolved = self.store.resolve_approval(approval.id, "expired", now)
            self._resolve_execution(resolved, AutomationRunStatus.EXPIRED, "Approval expired.", now)
            raise ValueError("Automation approval has expired.")
        resolved = self.store.resolve_approval(approval.id, "rejected", now)
        return self._resolve_execution(resolved, AutomationRunStatus.REJECTED, "Approval rejected.", now)

    def approve(self, approval_id: str, *, at: datetime | None = None):
        now = _utc(at or self.clock())
        now_stamp = _stamp(now)
        approval = self.store.approval(approval_id)
        if approval is None:
            raise ValueError("Automation approval not found.")
        if approval.status != "pending":
            raise ValueError("Automation approval is no longer pending.")
        if approval.expires_at and approval.expires_at <= now_stamp:
            resolved = self.store.resolve_approval(approval.id, "expired", now_stamp)
            self._resolve_execution(resolved, AutomationRunStatus.EXPIRED, "Approval expired.", now_stamp)
            raise ValueError("Automation approval has expired.")
        run = self.store.execution(approval.schedule_id, approval.occurrence)
        if run is None or run.status != AutomationRunStatus.PENDING_APPROVAL:
            raise ValueError("The stored automation execution is unavailable.")
        authority = AuthorityContext(approval.explicitly_requested, frozenset(approval.permissions))
        try:
            preview = self.executor.preview(approval.workflow_name, authority=authority)
        except (KeyError, ValueError):
            resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
            self._resolve_execution(resolved, AutomationRunStatus.FAILED,
                                    "Stored workflow could not be revalidated.", now_stamp)
            raise ValueError("Stored workflow could not be revalidated safely.")
        if preview.status != WorkflowStatus.PREVIEW or preview.definition_signature != approval.definition_signature:
            resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
            self._resolve_execution(resolved, AutomationRunStatus.FAILED, "Stored workflow proposal changed.", now_stamp)
            raise ValueError("Stored workflow proposal changed and cannot be approved.")
        expected = dict(approval.proposal)
        for step in preview.steps:
            plan = step.result.plan
            if plan is None or step.step_name not in expected:
                resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
                self._resolve_execution(resolved, AutomationRunStatus.FAILED,
                                        "Stored workflow proposal is incomplete.", now_stamp)
                raise ValueError("Stored workflow proposal is incomplete.")
            actual = {"tool_name": step.tool_name, "arguments": dict(plan.arguments),
                      "authority": step.authority.value, "reversible": plan.spec.reversible,
                      "side_effects": plan.spec.side_effects,
                      "required_permissions": plan.spec.required_permissions,
                      "timeout": plan.spec.timeout}
            if json.dumps(actual, sort_keys=True) != expected[step.step_name]:
                resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
                self._resolve_execution(resolved, AutomationRunStatus.FAILED, "Stored workflow proposal changed.", now_stamp)
                raise ValueError("Stored workflow proposal changed and cannot be approved.")
        try:
            result = self.executor.execute(preview, authority=authority,
                                           approve=lambda plan: Approval(plan.id, True))
        except (KeyError, ValueError):
            resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
            self._resolve_execution(resolved, AutomationRunStatus.FAILED,
                                    "Approved workflow could not execute safely.", now_stamp)
            raise ValueError("Approved workflow could not execute safely.")
        if result.status != WorkflowStatus.SUCCESS:
            resolved = self.store.resolve_approval(approval.id, "failed", now_stamp)
            self._resolve_execution(resolved, AutomationRunStatus.FAILED,
                                    result.failure.message if result.failure else "Approved workflow failed.", now_stamp)
            raise ValueError("Approved workflow failed safely.")
        resolved = self.store.resolve_approval(approval.id, "approved", now_stamp)
        return self._resolve_execution(resolved, AutomationRunStatus.APPROVED, None, now_stamp)

    def _resolve_execution(self, approval, status, failure, stamp):
        run = self.store.execution(approval.schedule_id, approval.occurrence)
        if run is None:
            return approval
        self.store.update_execution(AutomationRun(run.id, run.schedule_id, run.occurrence,
            run.workflow_name, status, run.workflow_id, run.started_at, stamp, failure))
        return approval

    @staticmethod
    def executor_result(schedule, occurrence, status, workflow_id, started, failure, finished_at):
        finished = _stamp(finished_at)
        return AutomationRun(str(uuid4()), schedule.id, occurrence, schedule.workflow_name,
                             status, workflow_id, started, finished, failure)

"""Sequential execution of trusted, registered IRIS tool workflows."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time
from collections.abc import Callable
from uuid import uuid4

from iris.tools import Approval, AuthorityContext, FailureCode, RequestOrigin, ResultStatus, ToolCall, ToolExecutor, ToolFailure, ToolResult
from iris.tools.models import AuthorityLevel, ExecutionPlan
from iris.notifications import NotificationEvent, NotificationKind, NotificationSeverity
from iris.workflows.models import (
    MAX_WORKFLOW_STEPS, MAX_WORKFLOW_TIMEOUT_SECONDS, WorkflowAuditEvent,
    WorkflowDefinition, WorkflowResult, WorkflowStatus, WorkflowStepResult,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class WorkflowRegistry:
    """Host-owned registry of declarative workflow definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        if not isinstance(definition, WorkflowDefinition):
            raise ValueError("Expected a typed WorkflowDefinition.")
        if definition.name in self._definitions:
            raise ValueError("Duplicate workflow name.")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> WorkflowDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError("Workflow is not registered.") from exc

    def definitions(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions.values())


class WorkflowExecutor:
    """Require a dry-run preview, then execute registered tool calls in order."""

    MAX_PENDING_PREVIEWS = 32

    def __init__(self, tools: ToolExecutor, workflows: WorkflowRegistry, *, publisher=None) -> None:
        self._tools = tools
        self._workflows = workflows
        self._publisher = publisher
        self._issued_previews: dict[str, tuple[str, tuple[bool, tuple[str, ...]]]] = {}

    def set_publisher(self, publisher) -> None:
        self._publisher = publisher

    def _publish(self, event: NotificationEvent) -> None:
        if self._publisher is not None:
            self._publisher(event)

    @staticmethod
    def _authority_key(authority: AuthorityContext) -> tuple[bool, tuple[str, ...]]:
        return authority.explicitly_requested, tuple(sorted(authority.permissions))

    def _signature(self, definition: WorkflowDefinition) -> tuple[str, dict[str, object]]:
        specs = {spec.name: spec for spec in self._tools.specifications()}
        steps = []
        total_timeout = 0.0
        for step in definition.steps:
            spec = specs.get(step.tool_name)
            if spec is None:
                raise ValueError(f"Workflow step {step.name} references an unregistered tool.")
            if not spec.local_only:
                raise ValueError(f"Workflow step {step.name} uses a tool not declared local-only.")
            total_timeout += spec.timeout
            steps.append({
                "name": step.name,
                "tool_name": step.tool_name,
                "arguments": step.arguments,
                "description": spec.description,
                "local_only": spec.local_only,
                "authority": spec.authority.value,
                "reversible": spec.reversible,
                "side_effects": spec.side_effects,
                "required_permissions": spec.required_permissions,
                "timeout": spec.timeout,
                "schema": [(arg.name, arg.description, arg.type.value, arg.required) for arg in spec.arguments],
            })
        if len(steps) > MAX_WORKFLOW_STEPS:
            raise ValueError(f"Workflow may contain at most {MAX_WORKFLOW_STEPS} steps.")
        if definition.timeout_seconds > MAX_WORKFLOW_TIMEOUT_SECONDS:
            raise ValueError(f"Workflow timeout may not exceed {MAX_WORKFLOW_TIMEOUT_SECONDS:g} seconds.")
        if total_timeout > definition.timeout_seconds:
            raise ValueError("Workflow timeout must cover the sum of all registered tool timeouts.")
        body: dict[str, object] = {
            "name": definition.name,
            "description": definition.description,
            "timeout_seconds": definition.timeout_seconds,
            "steps": steps,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hashlib.sha256(encoded).hexdigest(), specs

    @staticmethod
    def _audit(workflow_name: str, workflow_id: str, event: str, *, step_name: str | None = None,
               tool_name: str | None = None, authority: AuthorityLevel | None = None,
               plan_id: str | None = None, result_status: str | None = None) -> WorkflowAuditEvent:
        return WorkflowAuditEvent(workflow_name, workflow_id, event, _timestamp(), step_name,
                                  tool_name, authority, plan_id, result_status)

    def preview(self, name: str, *, authority: AuthorityContext) -> WorkflowResult:
        """Validate every step without calling a tool handler or approval callback."""
        if not isinstance(authority, AuthorityContext):
            raise ValueError("A host-owned AuthorityContext is required.")
        if len(self._issued_previews) >= self.MAX_PENDING_PREVIEWS:
            raise ValueError("Too many unconsumed workflow previews; execute or discard an existing preview first.")
        definition = self._workflows.get(name)
        signature, specs = self._signature(definition)
        workflow_id = str(uuid4())
        audit = [self._audit(name, workflow_id, "preview_started")]
        results: list[WorkflowStepResult] = []
        failure = None
        for step in definition.steps:
            spec = specs[step.tool_name]
            started = time.monotonic()
            started_at = _timestamp()
            result = self._tools.execute(
                ToolCall(step.tool_name, step.arguments_dict(), RequestOrigin.USER),
                authority=authority,
                dry_run=True,
            )
            finished_at = _timestamp()
            results.append(WorkflowStepResult(step.name, step.tool_name, spec.authority, result,
                                              started_at, finished_at, time.monotonic() - started))
            audit.append(self._audit(name, workflow_id, "step_previewed", step_name=step.name,
                                     tool_name=step.tool_name, authority=spec.authority,
                                     plan_id=result.plan.id if result.plan else None,
                                     result_status=result.status.value))
            if result.failure is not None:
                failure = result.failure
                audit.append(self._audit(name, workflow_id, "preview_failed", step_name=step.name,
                                         tool_name=step.tool_name, authority=spec.authority,
                                         plan_id=result.plan.id if result.plan else None,
                                         result_status=result.status.value))
                break
        status = WorkflowStatus.FAILED if failure else WorkflowStatus.PREVIEW
        if not failure:
            self._issued_previews[workflow_id] = (signature, self._authority_key(authority))
            audit.append(self._audit(name, workflow_id, "preview_complete"))
        return WorkflowResult(name, workflow_id, status, tuple(results), tuple(audit), failure, signature)

    def execute(self, preview: WorkflowResult, *, authority: AuthorityContext,
                approve: Callable[[ExecutionPlan], Approval] | None = None) -> WorkflowResult:
        """Execute only an unmodified preview issued by this executor instance."""
        if not isinstance(preview, WorkflowResult) or preview.status != WorkflowStatus.PREVIEW:
            raise ValueError("Execute requires a successful workflow dry-run preview.")
        if not isinstance(authority, AuthorityContext):
            raise ValueError("A host-owned AuthorityContext is required.")
        definition = self._workflows.get(preview.workflow_name)
        signature, specs = self._signature(definition)
        issued = self._issued_previews.get(preview.workflow_id)
        if (issued is None or issued != (signature, self._authority_key(authority))
                or preview.definition_signature != signature):
            raise ValueError("Workflow preview is unknown, stale, or does not match the current authority context.")

        audit = [self._audit(definition.name, preview.workflow_id, "execution_started")]
        if approve is None:
            approval_step = next((step for step in definition.steps
                                  if specs[step.tool_name].authority != AuthorityLevel.GREEN
                                  or not authority.explicitly_requested), None)
            if approval_step is not None:
                self._issued_previews[preview.workflow_id] = issued
                failure = ToolFailure(FailureCode.APPROVAL_REQUIRED,
                                      "Workflow paused; explicit approval is required before any step executes.")
                approval_preview = next((item.result.plan for item in preview.steps
                                          if item.step_name == approval_step.name), None)
                audit.append(self._audit(definition.name, preview.workflow_id, "approval_pending",
                                         step_name=approval_step.name, tool_name=approval_step.tool_name,
                                         authority=specs[approval_step.tool_name].authority,
                                         plan_id=approval_preview.id if approval_preview else None))
                result = WorkflowResult(definition.name, preview.workflow_id, WorkflowStatus.PAUSED,
                                        preview.steps, tuple(audit), failure, signature)
                self._publish(NotificationEvent.create(
                    NotificationKind.APPROVAL_REQUEST, NotificationSeverity.WARNING, "workflow",
                    {"workflow": definition.name, "step": approval_step.name,
                     "tool": approval_step.tool_name, "authority": specs[approval_step.tool_name].authority.value},
                    f"workflow:{preview.workflow_id}:approval"))
                return result

        # Previews are single-use once execution begins, preventing accidental replay.
        self._issued_previews.pop(preview.workflow_id, None)
        deadline = time.monotonic() + definition.timeout_seconds
        results: list[WorkflowStepResult] = []
        failure = None
        status = WorkflowStatus.SUCCESS

        for step in definition.steps:
            spec = specs[step.tool_name]
            if time.monotonic() >= deadline:
                failure = ToolFailure(FailureCode.TIMEOUT, "Workflow time budget expired before this step.")
                result = ToolResult(ResultStatus.FAILED, failure=failure)
                results.append(WorkflowStepResult(step.name, step.tool_name, spec.authority, result,
                                                  _timestamp(), _timestamp(), 0.0))
                audit.append(self._audit(definition.name, preview.workflow_id, "step_failed",
                                         step_name=step.name, tool_name=step.tool_name,
                                         authority=spec.authority, result_status=ResultStatus.FAILED.value))
                status = WorkflowStatus.FAILED
                break

            started = time.monotonic()
            started_at = _timestamp()
            approval_wait = 0.0
            audit.append(self._audit(definition.name, preview.workflow_id, "step_started",
                                     step_name=step.name, tool_name=step.tool_name,
                                     authority=spec.authority))

            def approval_callback(plan: ExecutionPlan) -> Approval:
                nonlocal approval_wait
                audit.append(self._audit(definition.name, preview.workflow_id, "approval_requested",
                                         step_name=step.name, tool_name=step.tool_name,
                                         authority=spec.authority, plan_id=plan.id))
                wait_started = time.monotonic()
                try:
                    approval = approve(plan)  # type: ignore[misc]
                except Exception:
                    audit.append(self._audit(definition.name, preview.workflow_id, "approval_callback_failed",
                                             step_name=step.name, tool_name=step.tool_name,
                                             authority=spec.authority, plan_id=plan.id))
                    raise
                approval_wait += time.monotonic() - wait_started
                audit.append(self._audit(definition.name, preview.workflow_id,
                                         "approval_granted" if isinstance(approval, Approval)
                                         and approval.approved is True and approval.plan_id == plan.id
                                         else "approval_denied",
                                         step_name=step.name, tool_name=step.tool_name,
                                         authority=spec.authority, plan_id=plan.id))
                return approval

            result = self._tools.execute(
                ToolCall(step.tool_name, step.arguments_dict(), RequestOrigin.USER),
                authority=authority,
                approve=approval_callback if approve is not None else None,
            )
            finished_at = _timestamp()
            # Interactive approval pauses the workflow's active execution budget.
            deadline += approval_wait
            results.append(WorkflowStepResult(step.name, step.tool_name, spec.authority, result,
                                              started_at, finished_at, time.monotonic() - started))
            if result.failure is not None:
                failure = result.failure
                status = WorkflowStatus.PAUSED if failure.code == FailureCode.APPROVAL_REQUIRED else WorkflowStatus.FAILED
                audit.append(self._audit(definition.name, preview.workflow_id,
                                         "approval_pending" if status == WorkflowStatus.PAUSED else "step_failed",
                                         step_name=step.name, tool_name=step.tool_name,
                                         authority=spec.authority,
                                         plan_id=result.plan.id if result.plan else None,
                                         result_status=result.status.value))
                break
            audit.append(self._audit(definition.name, preview.workflow_id, "step_succeeded",
                                     step_name=step.name, tool_name=step.tool_name,
                                     authority=spec.authority,
                                     plan_id=result.plan.id if result.plan else None,
                                     result_status=result.status.value))
        audit.append(self._audit(definition.name, preview.workflow_id,
                                 "execution_paused" if status == WorkflowStatus.PAUSED else
                                 "execution_failed" if status == WorkflowStatus.FAILED else
                                 "execution_complete"))
        result = WorkflowResult(definition.name, preview.workflow_id, status, tuple(results),
                                tuple(audit), failure, signature)
        kind = NotificationKind.WORKFLOW_RESULT if status == WorkflowStatus.SUCCESS else NotificationKind.FAILURE
        severity = NotificationSeverity.INFO if status == WorkflowStatus.SUCCESS else NotificationSeverity.ERROR
        payload = {"workflow": definition.name, "status": status.value, "workflow_id": preview.workflow_id}
        if failure is not None:
            payload["failure_code"] = failure.code.value
        self._publish(NotificationEvent.create(kind, severity, "workflow", payload,
                                               f"workflow:{preview.workflow_id}:{status.value}"))
        return result

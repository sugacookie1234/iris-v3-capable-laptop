"""Typed, declarative definitions and results for local IRIS workflows."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import re
from typing import Any

from iris.tools.models import AuthorityLevel, ToolFailure, ToolResult


MAX_WORKFLOW_STEPS = 16
MAX_WORKFLOW_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    tool_name: str
    arguments: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("Workflow step names must be lowercase identifiers.")
        if not isinstance(self.tool_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.tool_name):
            raise ValueError("Workflow steps must reference a registered tool name.")
        if not isinstance(self.arguments, tuple):
            raise ValueError("Workflow arguments must be an immutable tuple of name/value pairs.")
        seen: set[str] = set()
        for item in self.arguments:
            if (not isinstance(item, tuple) or len(item) != 2
                    or not isinstance(item[0], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", item[0])
                    or item[0] in seen):
                raise ValueError("Workflow arguments must have unique lowercase names.")
            value = item[1]
            if type(value) not in (str, int, float, bool) or (type(value) is float and not math.isfinite(value)):
                raise ValueError("Workflow arguments must be finite JSON scalar values.")
            seen.add(item[0])

    def arguments_dict(self) -> dict[str, Any]:
        return dict(self.arguments)


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("Workflow names must be lowercase identifiers.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Workflow description is required.")
        if not isinstance(self.steps, tuple) or not self.steps:
            raise ValueError("A workflow must contain at least one step.")
        if len(self.steps) > MAX_WORKFLOW_STEPS:
            raise ValueError(f"A workflow may contain at most {MAX_WORKFLOW_STEPS} steps.")
        if any(not isinstance(step, WorkflowStep) for step in self.steps):
            raise ValueError("Workflow definitions must contain typed workflow steps.")
        if len({step.name for step in self.steps}) != len(self.steps):
            raise ValueError("Workflow step names must be unique.")
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= MAX_WORKFLOW_TIMEOUT_SECONDS):
            raise ValueError(
                f"Workflow timeout must be positive and at most {MAX_WORKFLOW_TIMEOUT_SECONDS:g} seconds."
            )


class WorkflowStatus(StrEnum):
    PREVIEW = "preview"
    SUCCESS = "success"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkflowStepResult:
    step_name: str
    tool_name: str
    authority: AuthorityLevel
    result: ToolResult
    started_at: str
    finished_at: str
    elapsed_seconds: float


@dataclass(frozen=True)
class WorkflowAuditEvent:
    workflow_name: str
    workflow_id: str
    event: str
    timestamp: str
    step_name: str | None = None
    tool_name: str | None = None
    authority: AuthorityLevel | None = None
    plan_id: str | None = None
    result_status: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    workflow_name: str
    workflow_id: str
    status: WorkflowStatus
    steps: tuple[WorkflowStepResult, ...]
    audit: tuple[WorkflowAuditEvent, ...]
    failure: ToolFailure | None = None
    definition_signature: str = ""

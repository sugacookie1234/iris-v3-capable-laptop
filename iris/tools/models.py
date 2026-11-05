"""Tool proposals are data; only the executor may invoke registered handlers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AuthorityLevel(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class RequestOrigin(StrEnum):
    USER = "user"
    MODEL = "model"
    MEMORY = "memory"
    EXTERNAL = "external"


class ArgumentType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class ToolArgument:
    name: str
    description: str
    type: ArgumentType
    required: bool = True


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    authority: AuthorityLevel
    reversible: bool
    side_effects: tuple[str, ...]
    required_permissions: tuple[str, ...]
    timeout: float
    arguments: tuple[ToolArgument, ...] = ()
    # Workflow execution opts in only tools explicitly declared local-only.
    # External services, shell/process launches, and network calls must remain false.
    local_only: bool = False


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    origin: RequestOrigin = RequestOrigin.MODEL


@dataclass(frozen=True)
class ExecutionPlan:
    spec: ToolSpec
    # Validated scalar arguments in an immutable snapshot for approval.
    arguments: tuple[tuple[str, Any], ...]
    origin: RequestOrigin
    confirmation_summary: str
    id: str = field(default_factory=lambda: str(uuid4()))


class FailureCode(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    AUTHORITY_DENIED = "authority_denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_REJECTED = "approval_rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True)
class ToolFailure:
    code: FailureCode
    message: str
    cause_type: str | None = None


class ResultStatus(StrEnum):
    SUCCESS = "success"
    PREVIEW = "preview"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolResult:
    status: ResultStatus
    plan: ExecutionPlan | None = None
    value: Any = None
    failure: ToolFailure | None = None
    receipt_id: str | None = None

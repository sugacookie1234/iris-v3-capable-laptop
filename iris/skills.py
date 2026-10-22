"""Governed, typed skills and actions for the IRIS Brain boundary.

This module is intentionally separate from prose generation. An action can run
only when trusted host code constructs an ``ActionRequest`` and the executor
accepts its typed, request-scoped authorization.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from enum import StrEnum
import json
import hashlib
import math
import re
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from iris.memory.redaction import contains_secret
from iris.tools.models import ArgumentType, RequestOrigin


class RiskClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_SIDE_EFFECT = "REVERSIBLE_SIDE_EFFECT"
    SENSITIVE_OR_DESTRUCTIVE = "SENSITIVE_OR_DESTRUCTIVE"


class AuthorizationState(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    REQUIRED = "REQUIRED"
    CONFIRMED = "CONFIRMED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class ActionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"


class ActionErrorCode(StrEnum):
    UNKNOWN_SKILL = "UNKNOWN_SKILL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNAUTHORIZED = "UNAUTHORIZED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    SENSITIVE_DATA = "SENSITIVE_DATA"


@dataclass(frozen=True)
class SkillArgument:
    name: str
    type: ArgumentType
    description: str
    required: bool = True


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    risk: RiskClass
    arguments: tuple[SkillArgument, ...] = ()
    permissions: frozenset[str] = frozenset()
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class ActionConfirmation:
    session_id: str
    request_id: str
    accepted: bool
    arguments_digest: str = ""
    expires_at: float | None = None


@dataclass(frozen=True)
class ActionRequest:
    skill: str
    arguments: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    origin: RequestOrigin = RequestOrigin.USER
    explicit_user_request: bool = True
    confirmation: ActionConfirmation | None = None
    cancelled: bool = False
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ActionError:
    code: ActionErrorCode
    message: str
    cause_type: str | None = None


@dataclass(frozen=True)
class ActionResult:
    status: ActionStatus
    skill: str | None = None
    value: Any = None
    authorization: AuthorizationState = AuthorizationState.NOT_REQUESTED
    error: ActionError | None = None


def action_arguments_digest(arguments: dict[str, Any]) -> str:
    """Return the stable, non-secret binding used by confirmations."""
    return hashlib.sha256(
        json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _error(code: ActionErrorCode, message: str, *, cause_type: str | None = None) -> ActionError:
    """Create an error containing no arguments, paths, credentials, or causes."""
    return ActionError(code, message, cause_type)


class SkillRegistry:
    """Registry of trusted skill specifications and host-owned handlers."""

    def __init__(self) -> None:
        self._skills: dict[str, tuple[SkillSpec, Callable[..., Any]]] = {}

    def register(self, spec: SkillSpec, handler: Callable[..., Any]) -> None:
        if not isinstance(spec, SkillSpec) or not re.fullmatch(r"[a-z][a-z0-9_]*", spec.name):
            raise ValueError("Skill names must be lowercase identifiers.")
        if spec.name in self._skills or not spec.description.strip():
            raise ValueError("Skill is duplicate or has no description.")
        if not isinstance(spec.risk, RiskClass) or not callable(handler):
            raise ValueError("Skill risk and handler are invalid.")
        if type(spec.timeout_seconds) not in (int, float) or not math.isfinite(spec.timeout_seconds) or spec.timeout_seconds <= 0:
            raise ValueError("Skill timeout must be positive and finite.")
        names: set[str] = set()
        for argument in spec.arguments:
            if (not isinstance(argument, SkillArgument)
                    or not re.fullmatch(r"[a-z][a-z0-9_]*", argument.name)
                    or argument.name in names
                    or not isinstance(argument.type, ArgumentType)
                    or type(argument.required) is not bool
                    or not argument.description.strip()):
                raise ValueError("Skill arguments are malformed.")
            names.add(argument.name)
        self._skills[spec.name] = (spec, handler)

    def get(self, name: str) -> SkillSpec:
        try:
            return self._skills[name][0]
        except (KeyError, TypeError):
            raise KeyError("Skill is not registered.") from None

    def resolve(self, name: str) -> tuple[SkillSpec, Callable[..., Any]]:
        try:
            return self._skills[name]
        except (KeyError, TypeError):
            raise KeyError("Skill is not registered.") from None

    def specifications(self) -> tuple[SkillSpec, ...]:
        return tuple(spec for spec, _ in self._skills.values())


def _validate_arguments(spec: SkillSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    if type(arguments) is not dict or any(type(key) is not str for key in arguments):
        raise ValueError("Arguments must be a string-keyed dictionary.")
    schema = {argument.name: argument for argument in spec.arguments}
    if arguments.keys() - schema.keys():
        raise ValueError("Unknown skill arguments.")
    types = {
        ArgumentType.STRING: (str,), ArgumentType.INTEGER: (int,),
        ArgumentType.NUMBER: (int, float), ArgumentType.BOOLEAN: (bool,),
    }
    for name, argument in schema.items():
        if name not in arguments:
            if argument.required:
                raise ValueError("A required skill argument is missing.")
            continue
        value = arguments[name]
        if type(value) not in types[argument.type]:
            raise ValueError("A skill argument has the wrong type.")
        if type(value) is float and not math.isfinite(value):
            raise ValueError("Numeric skill arguments must be finite.")
        if contains_secret(value):
            raise PermissionError("Credential-like data is not accepted by skills.")
    return dict(arguments)


class GovernedActionExecutor:
    """Execute only typed, authorized requests from the registered registry."""

    def __init__(self, registry: SkillRegistry, *, permissions: frozenset[str] = frozenset()):
        self.registry = registry
        self.permissions = permissions
        self._consumed_confirmations: set[tuple[str, str]] = set()
        self._confirmation_lock = threading.Lock()
        self._completed_results: dict[str, ActionResult] = {}

    def completed_result(self, request_id: str) -> ActionResult | None:
        """Return the immutable success record for a completed request."""
        return self._completed_results.get(request_id)

    def execute(self, request: ActionRequest) -> ActionResult:
        if not isinstance(request, ActionRequest):
            return ActionResult(ActionStatus.REJECTED, error=_error(ActionErrorCode.INVALID_ARGUMENTS, "Malformed action request."))
        try:
            spec, handler = self.registry.resolve(request.skill)
        except KeyError:
            return ActionResult(ActionStatus.REJECTED, request.skill if isinstance(request.skill, str) else None,
                                error=_error(ActionErrorCode.UNKNOWN_SKILL, "Skill is not registered."))
        if request.origin != RequestOrigin.USER or request.explicit_user_request is not True:
            return ActionResult(ActionStatus.REJECTED, spec.name,
                                authorization=AuthorizationState.DENIED,
                                error=_error(ActionErrorCode.UNAUTHORIZED, "A current explicit user request is required."))
        if not request.session_id.strip():
            return ActionResult(ActionStatus.REJECTED, spec.name,
                                authorization=AuthorizationState.DENIED,
                                error=_error(ActionErrorCode.UNAUTHORIZED, "A current session is required."))
        try:
            arguments = _validate_arguments(spec, request.arguments)
        except PermissionError:
            return ActionResult(ActionStatus.REJECTED, spec.name,
                                error=_error(ActionErrorCode.SENSITIVE_DATA, "Credential-like data is not accepted."))
        except (TypeError, ValueError):
            return ActionResult(ActionStatus.REJECTED, spec.name,
                                error=_error(ActionErrorCode.INVALID_ARGUMENTS, "Skill arguments are invalid."))
        if not spec.permissions.issubset(self.permissions):
            return ActionResult(ActionStatus.REJECTED, spec.name,
                                authorization=AuthorizationState.DENIED,
                                error=_error(ActionErrorCode.UNAUTHORIZED, "Required skill authorization is unavailable."))
        if request.cancelled:
            return ActionResult(ActionStatus.CANCELLED, spec.name, authorization=AuthorizationState.CANCELLED,
                                error=_error(ActionErrorCode.CANCELLED, "Action was cancelled."))
        if spec.risk != RiskClass.READ_ONLY:
            confirmation = request.confirmation
            if (confirmation is None or confirmation.session_id != request.session_id
                    or confirmation.request_id != request.request_id):
                return ActionResult(ActionStatus.CONFIRMATION_REQUIRED, spec.name,
                                    authorization=AuthorizationState.REQUIRED,
                                    error=_error(ActionErrorCode.CONFIRMATION_REQUIRED, "Explicit confirmation is required."))
            if confirmation.accepted is not True:
                return ActionResult(ActionStatus.REJECTED, spec.name, authorization=AuthorizationState.DENIED,
                                    error=_error(ActionErrorCode.DENIED, "Action was not confirmed."))
            if confirmation.arguments_digest != action_arguments_digest(arguments):
                return ActionResult(ActionStatus.REJECTED, spec.name, authorization=AuthorizationState.DENIED,
                                    error=_error(ActionErrorCode.DENIED, "Confirmation does not match this action."))
            if confirmation.expires_at is not None and (
                    type(confirmation.expires_at) not in (int, float)
                    or not math.isfinite(confirmation.expires_at)
                    or time.monotonic() >= confirmation.expires_at):
                return ActionResult(ActionStatus.REJECTED, spec.name, authorization=AuthorizationState.DENIED,
                                    error=_error(ActionErrorCode.DENIED, "Confirmation has expired."))
            confirmation_key = (request.session_id, request.request_id)
            with self._confirmation_lock:
                if confirmation_key in self._consumed_confirmations:
                    return ActionResult(ActionStatus.REJECTED, spec.name, authorization=AuthorizationState.DENIED,
                                        error=_error(ActionErrorCode.DENIED, "Confirmation has already been used."))
                self._consumed_confirmations.add(confirmation_key)
        authorization = (AuthorizationState.CONFIRMED if spec.risk != RiskClass.READ_ONLY
                         else AuthorizationState.NOT_REQUESTED)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(handler, **arguments)
        try:
            value = future.result(timeout=float(spec.timeout_seconds))
            json.dumps(value, allow_nan=False)
            result = ActionResult(ActionStatus.SUCCESS, spec.name, value, authorization)
            self._completed_results[request.request_id] = result
            return result
        except FutureTimeout:
            future.cancel()
            return ActionResult(ActionStatus.TIMEOUT, spec.name, authorization=authorization,
                                error=_error(ActionErrorCode.TIMEOUT, "Skill timed out."))
        except (TypeError, ValueError):
            return ActionResult(ActionStatus.FAILED, spec.name, authorization=authorization,
                                error=_error(ActionErrorCode.EXECUTION_FAILED, "Skill returned an invalid result."))
        except Exception as exc:
            return ActionResult(ActionStatus.FAILED, spec.name, authorization=authorization,
                                error=_error(ActionErrorCode.EXECUTION_FAILED, "Skill execution failed.", cause_type=type(exc).__name__))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def deterministic_fake_executor() -> GovernedActionExecutor:
    """Return a harmless executor for tests and local readiness checks."""
    registry = SkillRegistry()
    registry.register(
        SkillSpec("iris_status", "Return static local IRIS readiness.", RiskClass.READ_ONLY),
        lambda: {"status": "ready", "execution": "local"},
    )
    return GovernedActionExecutor(registry)

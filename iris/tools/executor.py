"""Validated, approval-gated execution in a stoppable child process.

This is a trusted-code boundary, not a sandbox for malicious Python handlers.
The terminal installs local workspace inspection and task storage handlers.
"""
from __future__ import annotations

import json
import math
import multiprocessing
from collections.abc import Callable
from typing import Any

from iris.tools.authority import Approval, AuthorityContext, evaluate
from iris.tools.models import (
    ArgumentType, ExecutionPlan, FailureCode, RequestOrigin, ResultStatus,
    ToolCall, ToolFailure, ToolResult, ToolSpec,
)
from iris.tools.registry import ToolRegistry


def _worker(connection: Any, handler: Callable[..., Any], arguments: dict[str, Any]) -> None:
    try:
        value = handler(**arguments)
        # Only JSON data crosses back from handlers; never pickle arbitrary results.
        connection.send_bytes(json.dumps({"value": value}, allow_nan=False).encode())
    except Exception as exc:
        # Exception messages may contain credentials or external content.
        safe_messages = {
            "ValueError": "The arguments are invalid or the requested record/path is unavailable.",
            "PermissionError": "The requested path is hidden or outside the allowed workspace.",
            "FileNotFoundError": "The requested workspace path was not found.",
            "IsADirectoryError": "Provide a text file path, not a directory.",
        }
        connection.send_bytes(json.dumps({"error": type(exc).__name__,
                                          "message": safe_messages.get(type(exc).__name__, "Tool handler failed.")}).encode())
    finally:
        connection.close()


def _validate(spec: ToolSpec, arguments: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    if type(arguments) is not dict or any(type(key) is not str for key in arguments):
        raise ValueError("Arguments must be a string-keyed dictionary.")
    schema = {argument.name: argument for argument in spec.arguments}
    if arguments.keys() - schema.keys():
        raise ValueError("Unknown tool arguments.")
    types = {ArgumentType.STRING: (str,), ArgumentType.INTEGER: (int,),
             ArgumentType.NUMBER: (int, float), ArgumentType.BOOLEAN: (bool,)}
    for name, argument in schema.items():
        if name not in arguments:
            if argument.required:
                raise ValueError("A required argument is missing.")
            continue
        value = arguments[name]
        if type(value) not in types[argument.type]:
            raise ValueError("An argument has the wrong type.")
        if type(value) is float and not math.isfinite(value):
            raise ValueError("Numeric arguments must be finite.")
    return tuple(sorted(arguments.items()))


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def specifications(self) -> tuple[ToolSpec, ...]:
        return self._registry.specifications()

    def execute(self, call: ToolCall, *, authority: AuthorityContext | None = None,
                approve: Callable[[ExecutionPlan], Approval] | None = None,
                dry_run: bool = False) -> ToolResult:
        def failed(code: FailureCode, message: str, plan: ExecutionPlan | None = None,
                   cause: str | None = None) -> ToolResult:
            return ToolResult(ResultStatus.FAILED, plan, failure=ToolFailure(code, message, cause))

        if not isinstance(call, ToolCall) or type(call.name) is not str or not isinstance(call.origin, RequestOrigin):
            return failed(FailureCode.INVALID_ARGUMENTS, "Malformed tool call.")
        try:
            spec, handler = self._registry._resolve(call.name)
        except KeyError:
            return failed(FailureCode.UNKNOWN_TOOL, "Tool is not registered.")
        try:
            arguments = _validate(spec, call.arguments)
            explanation = ""
            # Trusted, pure preparation happens once, before the approval snapshot.
            prepare = self._registry._preparers.get(spec.name)
            if prepare is not None:
                prepared, explanation = prepare(dict(arguments))
                arguments = _validate(spec, prepared)
        except ValueError as exc:
            return failed(FailureCode.INVALID_ARGUMENTS, str(exc))
        summary = (explanation + "\n" + f"Execute {spec.name}: {spec.description}\n"
                   f"Arguments (data): {json.dumps(dict(arguments), ensure_ascii=True)}\n"
                   f"Authority: {spec.authority}; reversible: {spec.reversible}\n"
                   f"Side effects: {json.dumps(spec.side_effects)}\n"
                   f"Required permissions: {json.dumps(spec.required_permissions)}\n"
                   f"Timeout: {spec.timeout} seconds. Approval applies only to this execution.")
        plan = ExecutionPlan(spec, arguments, call.origin, summary)
        decision = evaluate(plan, authority or AuthorityContext())
        if not decision.allowed:
            return failed(FailureCode.AUTHORITY_DENIED, decision.reason, plan)
        if dry_run:
            return ToolResult(ResultStatus.PREVIEW, plan)
        if decision.needs_approval:
            if approve is None:
                return failed(FailureCode.APPROVAL_REQUIRED, decision.reason, plan)
            try:
                approval = approve(plan)
            except Exception as exc:
                return failed(FailureCode.APPROVAL_REJECTED, "Approval callback failed.", plan, type(exc).__name__)
            if not isinstance(approval, Approval) or approval.approved is not True or approval.plan_id != plan.id:
                return failed(FailureCode.APPROVAL_REJECTED, "This execution was not explicitly approved.", plan)
        # Fresh approval is followed directly by execution of the immutable snapshot.
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_worker, args=(sender, handler, dict(arguments)))
        started = False
        try:
            process.start()
            started = True
            sender.close()
            if not receiver.poll(spec.timeout):
                return failed(FailureCode.TIMEOUT, "Tool timed out; worker stopped. Effects already performed may remain.", plan)
            payload = json.loads(receiver.recv_bytes())
            if "error" in payload:
                return failed(FailureCode.EXECUTION_FAILED, payload.get("message", "Tool handler failed."), plan, payload["error"])
            return ToolResult(ResultStatus.SUCCESS, plan, value=payload["value"])
        except Exception as exc:
            return failed(FailureCode.EXECUTION_FAILED, "Tool worker failed.", plan, type(exc).__name__)
        finally:
            if started:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
            receiver.close()
            sender.close()
            process.close()

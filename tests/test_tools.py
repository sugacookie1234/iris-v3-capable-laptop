"""Deterministic local fake tools; no model or external service requests."""
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from iris.tools import (
    Approval, ArgumentType, AuthorityContext, AuthorityLevel, FailureCode,
    RequestOrigin, ResultStatus, ToolArgument, ToolCall, ToolExecutor,
    ToolRegistry, ToolSpec,
)


def echo(text):
    return {"echo": text}


def fail(text):
    raise RuntimeError("sensitive provider details")


def delayed_write(text):
    time.sleep(1)
    Path(text).write_text("should never run", encoding="utf-8")


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.spec = ToolSpec(
            "echo", "Return supplied text", AuthorityLevel.GREEN, True,
            (), ("fake.echo",), 3,
            (ToolArgument("text", "Text to echo", ArgumentType.STRING),),
        )
        self.registry.register(self.spec, echo)
        self.executor = ToolExecutor(self.registry)
        self.authority = AuthorityContext(True, frozenset({"fake.echo"}))
        self.call = ToolCall("echo", {"text": "hello"}, RequestOrigin.USER)

    def test_registration_and_discovery(self):
        self.assertEqual(self.registry.specifications(), (self.spec,))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.registry.register(self.spec, echo)
        for changes in (
            {"name": "bad name"}, {"description": ""}, {"timeout": 0},
            {"timeout": float("nan")}, {"timeout": True},
            {"authority": "GREEN"}, {"reversible": False}, {"local_only": 1},
            {"side_effects": ["mutable"]}, {"required_permissions": ("",)},
            {"arguments": self.spec.arguments * 2},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ToolRegistry().register(replace(self.spec, **changes), echo)
        with self.assertRaises(ValueError):
            ToolRegistry().register(self.spec, None)

    def test_unknown_and_invalid_arguments_never_request_approval(self):
        def unexpected(plan):
            self.fail("Invalid calls must not request approval")
        result = self.executor.execute(ToolCall("missing"), approve=unexpected)
        self.assertEqual(result.failure.code, FailureCode.UNKNOWN_TOOL)
        for arguments in ({}, {"text": 12}, {"text": "ok", "extra": True}, [], {1: "x"}):
            result = self.executor.execute(ToolCall("echo", arguments), approve=unexpected)
            self.assertEqual(result.failure.code, FailureCode.INVALID_ARGUMENTS)

    def test_scalar_validation_and_optional_arguments(self):
        for kind, good, bad in ((ArgumentType.INTEGER, 2, True),
                                (ArgumentType.NUMBER, 2.5, float("inf")),
                                (ArgumentType.BOOLEAN, False, 0)):
            registry = ToolRegistry()
            registry.register(replace(self.spec, arguments=(ToolArgument("text", "value", kind, False),)), echo)
            executor = ToolExecutor(registry)
            for arguments in ({}, {"text": good}):
                self.assertEqual(executor.execute(ToolCall("echo", arguments), authority=self.authority, dry_run=True).status, ResultStatus.PREVIEW)
            self.assertEqual(executor.execute(ToolCall("echo", {"text": bad}), authority=self.authority).failure.code, FailureCode.INVALID_ARGUMENTS)

    def test_dry_run_does_not_call_handler_or_approval(self):
        registry = ToolRegistry()
        registry.register(replace(self.spec, authority=AuthorityLevel.RED), fail)
        def unexpected(plan):
            self.fail("Preview must not request approval")
        result = ToolExecutor(registry).execute(self.call, authority=self.authority, approve=unexpected, dry_run=True)
        self.assertEqual(result.status, ResultStatus.PREVIEW)
        self.assertIn("hello", result.plan.confirmation_summary)
        self.assertIn("RED", result.plan.confirmation_summary)
        self.assertIn("Side effects:", result.plan.confirmation_summary)

    def test_green_executes_only_with_explicit_request_and_permissions(self):
        result = self.executor.execute(self.call, authority=self.authority)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.value, {"echo": "hello"})
        result = self.executor.execute(self.call, authority=AuthorityContext(False, self.authority.permissions))
        self.assertEqual(result.failure.code, FailureCode.APPROVAL_REQUIRED)
        result = self.executor.execute(self.call)
        self.assertEqual(result.failure.code, FailureCode.AUTHORITY_DENIED)

    def test_model_proposal_does_not_grant_authority(self):
        proposal = replace(self.call, origin=RequestOrigin.MODEL)
        result = self.executor.execute(proposal, authority=AuthorityContext(False, self.authority.permissions))
        self.assertEqual(result.failure.code, FailureCode.APPROVAL_REQUIRED)

    def test_memory_and_external_origins_are_denied_even_with_approval(self):
        for origin in (RequestOrigin.MEMORY, RequestOrigin.EXTERNAL):
            result = self.executor.execute(replace(self.call, origin=origin), authority=self.authority,
                                           approve=lambda plan: Approval(plan.id, True))
            self.assertEqual(result.failure.code, FailureCode.AUTHORITY_DENIED)

    def test_yellow_fresh_approval_and_argument_snapshot(self):
        registry = ToolRegistry()
        registry.register(replace(self.spec, authority=AuthorityLevel.YELLOW), echo)
        executor = ToolExecutor(registry)
        captured = []
        def approve(plan):
            captured.append(Approval(plan.id, True))
            self.call.arguments["text"] = "changed after approval"
            return captured[-1]
        result = executor.execute(self.call, authority=self.authority, approve=approve)
        self.assertEqual(result.value, {"echo": "hello"})
        result = executor.execute(self.call, authority=self.authority, approve=lambda plan: captured[0])
        self.assertEqual(result.failure.code, FailureCode.APPROVAL_REJECTED)
        self.assertEqual(executor.execute(self.call, authority=self.authority).failure.code, FailureCode.APPROVAL_REQUIRED)

    def test_red_requires_explicit_bound_approval(self):
        registry = ToolRegistry()
        registry.register(replace(self.spec, authority=AuthorityLevel.RED, reversible=False,
                                  side_effects=("Fake irreversible action",)), echo)
        executor = ToolExecutor(registry)
        for callback in (lambda plan: False, lambda plan: Approval(plan.id, False),
                         lambda plan: Approval("other-plan", True)):
            result = executor.execute(self.call, authority=self.authority, approve=callback)
            self.assertEqual(result.failure.code, FailureCode.APPROVAL_REJECTED)
        result = executor.execute(self.call, authority=self.authority, approve=lambda plan: Approval(plan.id, True))
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("Fake irreversible action", result.plan.confirmation_summary)

    def test_failure_propagates_as_typed_result(self):
        registry = ToolRegistry()
        registry.register(self.spec, fail)
        result = ToolExecutor(registry).execute(self.call, authority=self.authority)
        self.assertEqual(result.failure.code, FailureCode.EXECUTION_FAILED)
        self.assertEqual(result.failure.cause_type, "RuntimeError")
        self.assertNotIn("sensitive provider details", str(result))

    def test_timeout_stops_delayed_handler(self):
        registry = ToolRegistry()
        registry.register(replace(self.spec, timeout=0.2), delayed_write)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker"
            result = ToolExecutor(registry).execute(ToolCall("echo", {"text": str(path)}, RequestOrigin.USER), authority=self.authority)
            self.assertEqual(result.failure.code, FailureCode.TIMEOUT)
            time.sleep(1.1)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

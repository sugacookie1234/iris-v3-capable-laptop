import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from iris.brain.llm import LLMMessage, MessageRole
from iris.memory.store import MemoryStore
from iris.skills import (
    ActionConfirmation, ActionRequest, ActionStatus, ArgumentType,
    AuthorizationState, GovernedActionExecutor, RiskClass, SkillArgument,
    SkillRegistry, SkillSpec, action_arguments_digest, deterministic_fake_executor,
)
from iris.tools.models import RequestOrigin
from iris.voice import VoiceSession


class SkillTests(unittest.TestCase):
    def registry(self, handler=None, *, risk=RiskClass.READ_ONLY, arguments=(), timeout_seconds=1):
        registry = SkillRegistry()
        registry.register(
            SkillSpec("read_status", "Read harmless status.", risk, arguments, timeout_seconds=timeout_seconds),
            handler or (lambda **kwargs: {"ok": True, **kwargs}),
        )
        return registry

    def request(self, **kwargs):
        return ActionRequest("read_status", session_id="session-1", **kwargs)

    @staticmethod
    def confirmation(request, accepted=True, session_id=None):
        return ActionConfirmation(
            session_id or request.session_id,
            request.request_id,
            accepted,
            action_arguments_digest(request.arguments),
        )

    def test_registry_lookup_and_harmless_read_only_skill(self):
        executor = deterministic_fake_executor()
        self.assertEqual(executor.registry.get("iris_status").risk, RiskClass.READ_ONLY)
        result = executor.execute(ActionRequest("iris_status", session_id="s"))
        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.value["status"], "ready")

    def test_valid_and_invalid_arguments(self):
        spec = (SkillArgument("count", ArgumentType.INTEGER, "A count"),)
        executor = GovernedActionExecutor(self.registry(arguments=spec))
        self.assertEqual(executor.execute(self.request(arguments={"count": 2})).status, ActionStatus.SUCCESS)
        invalid = executor.execute(self.request(arguments={"count": "two"}))
        self.assertEqual(invalid.status, ActionStatus.REJECTED)
        self.assertEqual(invalid.error.message, "Skill arguments are invalid.")

    def test_unknown_skill_is_rejected(self):
        result = deterministic_fake_executor().execute(ActionRequest("not_registered", session_id="s"))
        self.assertEqual(result.status, ActionStatus.REJECTED)
        self.assertEqual(result.error.code.value, "UNKNOWN_SKILL")

    def test_risk_classes_and_confirmation(self):
        for risk in (RiskClass.REVERSIBLE_SIDE_EFFECT, RiskClass.SENSITIVE_OR_DESTRUCTIVE):
            executor = GovernedActionExecutor(self.registry(risk=risk))
            pending = executor.execute(self.request())
            self.assertEqual(pending.status, ActionStatus.CONFIRMATION_REQUIRED)
            self.assertEqual(pending.authorization, AuthorizationState.REQUIRED)
            original = self.request()
            accepted = executor.execute(self.request(
                confirmation=self.confirmation(original),
            ))
            # The confirmation must match the actual request, not a different request.
            self.assertEqual(accepted.status, ActionStatus.CONFIRMATION_REQUIRED)
            current = self.request()
            accepted = executor.execute(current.__class__(**{**current.__dict__, "confirmation": self.confirmation(current)}))
            self.assertEqual(accepted.status, ActionStatus.SUCCESS)
            self.assertEqual(accepted.authorization, AuthorizationState.CONFIRMED)

    def test_confirmation_denied_and_cross_session_confirmation_fail(self):
        executor = GovernedActionExecutor(self.registry(risk=RiskClass.SENSITIVE_OR_DESTRUCTIVE))
        current = self.request()
        denied_current = current.__class__(**{**current.__dict__, "confirmation": self.confirmation(current, False)})
        self.assertEqual(executor.execute(denied_current).status, ActionStatus.REJECTED)
        denied_request = self.request(confirmation=ActionConfirmation("session-1", "wrong", False))
        self.assertEqual(executor.execute(denied_request).status, ActionStatus.CONFIRMATION_REQUIRED)
        denied = current.__class__(**{**current.__dict__, "confirmation": self.confirmation(current, True, "other")})
        self.assertEqual(executor.execute(denied).status, ActionStatus.CONFIRMATION_REQUIRED)

    def test_confirmations_are_single_use_and_bind_arguments(self):
        calls = []
        executor = GovernedActionExecutor(self.registry(
            lambda value: calls.append(value),
            risk=RiskClass.REVERSIBLE_SIDE_EFFECT,
            arguments=(SkillArgument("value", ArgumentType.STRING, "value"),),
        ))
        original = self.request(arguments={"value": "one"})
        confirmed = original.__class__(**{
            **original.__dict__, "confirmation": self.confirmation(original),
        })
        self.assertEqual(executor.execute(confirmed).status, ActionStatus.SUCCESS)
        self.assertEqual(executor.completed_result(original.request_id).status, ActionStatus.SUCCESS)
        self.assertEqual(executor.execute(confirmed).status, ActionStatus.REJECTED)
        altered = original.__class__(**{
            **original.__dict__, "arguments": {"value": "two"},
            "confirmation": self.confirmation(original),
        })
        self.assertEqual(executor.execute(altered).status, ActionStatus.REJECTED)
        self.assertEqual(calls, ["one"])

    def test_expired_confirmation_cannot_execute(self):
        calls = []
        executor = GovernedActionExecutor(self.registry(
            lambda: calls.append(True), risk=RiskClass.REVERSIBLE_SIDE_EFFECT,
        ))
        request = self.request()
        expired = request.__class__(**{
            **request.__dict__,
            "confirmation": ActionConfirmation(
                request.session_id, request.request_id, True,
                action_arguments_digest(request.arguments), expires_at=0.0,
            ),
        })
        self.assertEqual(executor.execute(expired).status, ActionStatus.REJECTED)
        self.assertEqual(calls, [])

    def test_cancellation_and_timeout(self):
        calls = []
        executor = GovernedActionExecutor(self.registry(lambda: calls.append(True), timeout_seconds=0.01))
        cancelled = executor.execute(self.request(cancelled=True))
        self.assertEqual(cancelled.status, ActionStatus.CANCELLED)
        slow = GovernedActionExecutor(self.registry(lambda: time.sleep(0.1), timeout_seconds=0.01))
        result = slow.execute(self.request())
        self.assertEqual(result.status, ActionStatus.TIMEOUT)
        self.assertEqual(calls, [])

    def test_credentials_paths_and_handler_errors_are_not_exposed(self):
        executor = GovernedActionExecutor(self.registry(
            lambda secret: (_ for _ in ()).throw(RuntimeError("/private/secret-token")),
            arguments=(SkillArgument("secret", ArgumentType.STRING, "data"),),
        ))
        rejected = executor.execute(self.request(arguments={"secret": "api_key=hidden-value"}))
        self.assertNotIn("hidden-value", repr(rejected))
        self.assertNotIn("api_key", repr(rejected))
        safe = executor.execute(self.request(arguments={"secret": "ordinary"}))
        self.assertNotIn("/private/secret-token", repr(safe))
        self.assertEqual(safe.error.message, "Skill execution failed.")

    def test_prose_never_triggers_execution(self):
        handler = Mock(return_value={"ok": True})
        executor = GovernedActionExecutor(self.registry(handler))
        # A sentence is not an ActionRequest and is rejected without dispatch.
        result = executor.execute("please run read_status")
        self.assertEqual(result.status, ActionStatus.REJECTED)
        handler.assert_not_called()

    def test_model_or_unexplicit_request_cannot_execute(self):
        executor = GovernedActionExecutor(self.registry())
        request = self.request(origin=RequestOrigin.MODEL, explicit_user_request=False)
        result = executor.execute(request)
        self.assertEqual(result.status, ActionStatus.REJECTED)
        self.assertEqual(result.authorization, AuthorizationState.DENIED)

    def test_failed_or_unconfirmed_action_does_not_persist_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(Path(directory) / "memory.sqlite3") as store:
                before = store.current()
                executor = GovernedActionExecutor(self.registry(risk=RiskClass.SENSITIVE_OR_DESTRUCTIVE,
                                                               handler=lambda: (_ for _ in ()).throw(RuntimeError("failed"))))
                self.assertEqual(executor.execute(self.request()).status, ActionStatus.CONFIRMATION_REQUIRED)
                current = self.request()
                confirmed = current.__class__(**{**current.__dict__, "confirmation": self.confirmation(current)})
                self.assertEqual(executor.execute(confirmed).status, ActionStatus.FAILED)
                self.assertEqual(store.current(), before)

    def test_terminal_and_voice_use_brain_action_boundary_without_prose_execution(self):
        from iris.terminal import create_brain, load_config
        brain = create_brain(load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test"}))
        self.assertIsInstance(brain._action_executor, GovernedActionExecutor)
        responder = Mock(return_value="reply")
        session = VoiceSession(responder=responder)
        self.assertEqual(session.submit_text("please read status").response, "reply")
        responder.assert_called_once_with("please read status")


if __name__ == "__main__":
    unittest.main()

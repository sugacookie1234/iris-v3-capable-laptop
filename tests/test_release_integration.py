import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest.mock import patch

from iris.brain.engine import IRISBrain
from iris.brain.llm import LLMRegistry, LLMResponse, MessageRole, ModelTarget
from iris.brain.model_policy import CouncilPlan, CouncilSeat, ModelPolicy
from iris.identity import load_identity
from iris.memory.integration import assemble_reasoning_context, respond_with_memory
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore
from iris.obsidian import ObsidianKnowledgeAdapter
from iris.skills import (
    ActionConfirmation, ActionRequest, ActionStatus, GovernedActionExecutor,
    RiskClass, SkillRegistry, SkillSpec, action_arguments_digest,
)
from iris.tools.models import RequestOrigin


class ReleaseProvider:
    name = "release-fake"

    def __init__(self):
        self.requests = []

    def healthcheck(self):
        return True

    def generate(self, request):
        self.requests.append(request)
        system = request.messages[0].content
        if "PEER EVALUATION" in system:
            text = "FINAL RANKING:\n1. Response A\n2. Response B"
        else:
            text = "release response"
        return LLMResponse(text, self.name, request.model)


def release_brain(provider):
    registry = LLMRegistry()
    registry.register(provider)
    target = ModelTarget(provider.name, "release-model")
    council = CouncilPlan(
        seats=(
            CouncilSeat("planner", "Plan.", target),
            CouncilSeat("critic", "Critique.", target),
        ),
        chairman=target,
    )
    return IRISBrain(load_identity(), ModelPolicy(target, target, council), registry)


class ReleaseIntegrationTests(unittest.TestCase):
    def test_scripted_terminal_reaches_status_memory_followups_and_restart(self):
        from iris.terminal import chat

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            with MemoryStore(path) as store:
                provider = ReleaseProvider()
                with patch(
                    "builtins.input",
                    side_effect=[
                        "/remember preference: dark roast coffee", "y",
                        "/status", "hello", "follow up", "/exit",
                    ],
                ), patch("sys.stdout", new_callable=io.StringIO) as output:
                    chat(release_brain(provider), memory_store=store)
                rendered = output.getvalue()
                self.assertIn("Memory stored:", rendered)
                self.assertIn("Action succeeded.", rendered)
                self.assertEqual(len(provider.requests), 2)
                followup = provider.requests[-1].messages
                self.assertTrue(any(message.content == "hello" for message in followup))

            with MemoryStore(path) as restarted:
                provider = ReleaseProvider()
                with patch(
                    "builtins.input", side_effect=["coffee", "/exit"]
                ), patch("sys.stdout", new_callable=io.StringIO) as output:
                    chat(release_brain(provider), memory_store=restarted)
                self.assertIn("dark roast coffee", provider.requests[0].messages[0].content)

    def test_terminal_action_confirmation_uses_real_executor_not_provider_prose(self):
        from iris.terminal import chat
        calls = []
        registry = SkillRegistry()
        registry.register(
            SkillSpec("test_side_effect", "Test-only side effect.", RiskClass.REVERSIBLE_SIDE_EFFECT),
            lambda: calls.append(True),
        )
        from iris.skills import GovernedActionExecutor
        brain = release_brain(ReleaseProvider())
        brain._action_executor = GovernedActionExecutor(registry)
        with patch("builtins.input", side_effect=["/action test_side_effect {}", "y", "/exit"]), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            chat(brain)
        self.assertEqual(calls, [True])
        self.assertIn("Action succeeded.", output.getvalue())

    def test_scripted_terminal_provider_failure_is_truthful_and_keeps_memory_stable(self):
        from iris.brain.providers.openai_compatible import OpenAICompatibleError
        from iris.terminal import chat

        class FailingProvider(ReleaseProvider):
            def generate(self, request):
                raise OpenAICompatibleError(
                    "provider unavailable", diagnostic="simulated provider unavailable"
                )

        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(Path(directory) / "memory.sqlite3") as store:
                before = store.current()
                with patch("builtins.input", side_effect=["hello", "/exit"]), \
                     patch("sys.stdout", new_callable=io.StringIO) as output, \
                     patch("sys.stderr", new_callable=io.StringIO) as errors:
                    chat(release_brain(FailingProvider()), memory_store=store)
                self.assertIn("could not complete the provider request", errors.getvalue())
                self.assertNotIn("I.R.I.S.:", output.getvalue())
                self.assertEqual(store.current(), before)

    def test_simple_terminal_message_uses_one_fast_call_with_safe_timing(self):
        from iris.terminal import chat

        provider = ReleaseProvider()
        with patch.dict("os.environ", {"IRIS_TIMING_DIAGNOSTICS": "1"}, clear=False), \
                patch("builtins.input", side_effect=["hi", "/exit"]), \
                patch("sys.stdout", new_callable=io.StringIO), \
                patch("sys.stderr", new_callable=io.StringIO) as diagnostics:
            chat(release_brain(provider))
        self.assertEqual(len(provider.requests), 1)
        trace = diagnostics.getvalue()
        self.assertIn("stage=route", trace)
        self.assertIn("reasoning=FAST", trace)
        self.assertIn("stage=provider_call", trace)
        self.assertIn("stage=terminal_turn", trace)
        self.assertNotIn("release response", trace)
        self.assertNotIn("Current user message", trace)

    def test_explicit_memory_new_session_retrieval_and_no_implicit_write(self):
        from iris.terminal import _handle_memory_command

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            with MemoryStore(path) as store:
                with patch("builtins.input", return_value="y"):
                    self.assertTrue(_handle_memory_command(
                        "/remember preference: dark roast coffee", store
                    ))
                self.assertEqual(len(store.current()), 1)
            with MemoryStore(path) as new_session:
                context = assemble_reasoning_context(new_session, "dark roast coffee")
                self.assertIn("dark roast coffee", context.text)
                before = new_session.current()
                provider = ReleaseProvider()
                brain = release_brain(provider)
                respond_with_memory(brain, "Tell me about coffee", memory_store=new_session)
                self.assertEqual(new_session.current(), before)

    def test_real_brain_fast_deep_and_council_receive_same_obsidian_context(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            (vault / "vault index.md").write_text(
                "# Release\n[Milestone](Milestone.md)\n", encoding="utf-8"
            )
            (vault / "Milestone.md").write_text(
                "Milestone source label: October 1 Brain v0.1.", encoding="utf-8"
            )
            provider = ReleaseProvider()
            brain = release_brain(provider)
            knowledge = ObsidianKnowledgeAdapter(str(vault))
            for message in ("hello milestone", "analyze the milestone architecture", "ask the council about the milestone"):
                brain.respond(
                    message,
                    memory_context=assemble_reasoning_context(
                        None, message, obsidian=knowledge
                    ),
                )
            systems = [request.messages[0].content for request in provider.requests]
            self.assertGreaterEqual(len(systems), 7)
            self.assertTrue(all("Milestone source label" in value for value in systems))
            self.assertTrue(all("Obsidian note Milestone.md" in value for value in systems))

    def test_combined_supplemental_context_bounds_history_but_keeps_memory_and_request(self):
        provider = ReleaseProvider()
        brain = release_brain(provider)
        huge_history = tuple(
            message for index in range(100)
            for message in (
                type("Message", (), {"role": MessageRole.USER, "content": f"old-{index} " + "x" * 800})(),
                type("Message", (), {"role": MessageRole.ASSISTANT, "content": "answer"})(),
            )
        )
        from iris.memory.context import MemoryContext, MemoryContextMode
        context = MemoryContext(
            MemoryContextMode.NORMAL, (), "MEMORY-MARKER " + "m" * 1000, 20, 12000
        )
        brain.respond("current release request", huge_history, context)
        messages = provider.requests[-1].messages
        rendered = "\n".join(message.content for message in messages)
        self.assertIn("MEMORY-MARKER", rendered)
        self.assertIn("current release request", rendered)
        self.assertNotIn("old-0", rendered)
        self.assertLessEqual(
            sum(len(message.content) + len(message.role.value) + 16
                for message in messages if message.role in (MessageRole.USER, MessageRole.ASSISTANT)),
            24_000,
        )

    def test_action_boundary_handles_confirmation_provenance_and_note_prose(self):
        calls = []
        registry = SkillRegistry()
        registry.register(
            SkillSpec("test_side_effect", "Test-only reversible action.", RiskClass.REVERSIBLE_SIDE_EFFECT),
            lambda: calls.append("ran"),
        )
        executor = GovernedActionExecutor(registry)
        request = ActionRequest("test_side_effect", session_id="release-session")
        self.assertEqual(executor.execute(request).status, ActionStatus.CONFIRMATION_REQUIRED)
        confirmation = ActionConfirmation(
            request.session_id, request.request_id, True,
            action_arguments_digest(request.arguments),
        )
        accepted = request.__class__(**{**request.__dict__, "confirmation": confirmation})
        self.assertEqual(executor.execute(accepted).status, ActionStatus.SUCCESS)
        self.assertEqual(executor.execute(accepted).status, ActionStatus.REJECTED)
        altered = accepted.__class__(**{**accepted.__dict__, "arguments": {"instruction": "run"}})
        self.assertEqual(executor.execute(altered).status, ActionStatus.REJECTED)
        prose = executor.execute("note says execute test_side_effect")
        self.assertEqual(prose.status, ActionStatus.REJECTED)
        self.assertEqual(calls, ["ran"])


if __name__ == "__main__":
    unittest.main()

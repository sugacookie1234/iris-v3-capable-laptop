import io
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.main import main
from iris.terminal import (
    DEFAULT_MAX_HISTORY_TURNS,
    chat,
    create_brain,
    load_config,
    trim_history,
)
from iris.brain.llm import LLMMessage, MessageRole
from iris.brain.llm import LLMResponse
from iris.brain.council import CouncilExecutionError
from iris.brain.providers.openai_compatible import OpenAICompatibleError
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore


class ConfiguredFakeProvider:
    def __init__(self, config, *, fail=False):
        self._name = config.name
        self.requests = []
        self.fail = fail

    @property
    def name(self):
        return self._name

    def healthcheck(self):
        raise AssertionError("fake routing tests must not make provider health checks")

    def generate(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("fake chairman failure")
        if "PEER EVALUATION" in request.messages[0].content:
            return LLMResponse("FINAL RANKING:\n1. Response A\n2. Response B", self.name, request.model)
        return LLMResponse(f"{self.name}:{request.model}", self.name, request.model)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        saved = patch("iris.local_config.read_saved", return_value={})
        saved.start()
        self.addCleanup(saved.stop)

    def config(self, **extra):
        return load_config({"IRIS_PROVIDER_URL": "http://localhost:8000/v1/",
                            "IRIS_MODEL": "test-model", **extra})

    def test_config_normalizes_url_and_optional_key(self):
        config = self.config()
        self.assertEqual(config.provider.base_url, "http://localhost:8000")
        self.assertIsNone(config.provider.api_key)
        self.assertEqual(config.fast_target, config.deep_target)
        self.assertEqual(config.fast_target.provider, "terminal")
        self.assertEqual(config.fast_target.model, "test-model")
        self.assertTrue(all(seat.target == config.fast_target for seat in config.council_plan.seats))
        self.assertEqual(config.council_plan.chairman, config.fast_target)
        self.assertEqual(self.config(IRIS_API_KEY="secret").provider.api_key, "secret")

    def test_history_default_trims_to_newest_twelve_turns(self):
        history = [
            message
            for index in range(DEFAULT_MAX_HISTORY_TURNS + 1)
            for message in (
                LLMMessage(MessageRole.USER, f"user-{index}"),
                LLMMessage(MessageRole.ASSISTANT, f"assistant-{index}"),
            )
        ]
        trim_history(history, DEFAULT_MAX_HISTORY_TURNS)
        self.assertEqual(len(history), 24)
        self.assertEqual(history[0].content, "user-1")
        self.assertEqual(history[-1].content, "assistant-12")

    def test_custom_history_limit_is_configured_and_applied(self):
        config = self.config(IRIS_MAX_HISTORY_TURNS="2")
        self.assertEqual(config.max_history_turns, 2)
        brain = Mock()
        brain.respond.side_effect = [Mock(text=f"answer-{index}") for index in range(4)]
        with patch("builtins.input", side_effect=["one", "two", "three", "four", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
            chat(brain, max_history_turns=config.max_history_turns)
        self.assertEqual(brain.respond.call_args_list[2].kwargs["history"][0].content, "one")
        self.assertEqual(brain.respond.call_args_list[3].kwargs["history"][0].content, "two")
        self.assertEqual(len(brain.respond.call_args_list[3].kwargs["history"]), 4)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            self.config(IRIS_MAX_HISTORY_TURNS="1.5")

    def test_missing_and_invalid_configuration(self):
        with self.assertRaisesRegex(ValueError, "IRIS_PROVIDER_URL and IRIS_MODEL"):
            load_config({})
        for url in ("file:///tmp/model", "https://user:secret@host", "http://host:bad", "https://host?key=secret"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "IRIS_PROVIDER_URL"):
                self.config(IRIS_PROVIDER_URL=url)
        for timeout in ("0", "-1", "nan", "inf", "abc"):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, "IRIS_TIMEOUT_SECONDS"):
                self.config(IRIS_TIMEOUT_SECONDS=timeout)
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            self.config(IRIS_TIMEOUT_SECONDS="121")

    def test_provider_timeout_is_bounded_and_default_is_short(self):
        self.assertEqual(self.config().provider.timeout_seconds, 15.0)
        self.assertEqual(self.config(IRIS_TIMEOUT_SECONDS="120").provider.timeout_seconds, 120.0)

    def test_named_provider_and_model_targets_are_required_and_validated(self):
        with self.assertRaisesRegex(ValueError, "IRIS_DEEP_PROVIDER.*IRIS_DEEP_MODEL"):
            load_config({
                "IRIS_PROVIDER_GROQ_URL": "https://api.groq.com/openai/v1",
                "IRIS_FAST_PROVIDER": "groq", "IRIS_FAST_MODEL": "fast-model",
            })
        with self.assertRaisesRegex(ValueError, "IRIS_FAST_PROVIDER names an unconfigured provider"):
            load_config({
                "IRIS_PROVIDER_GROQ_URL": "https://api.groq.com/openai/v1",
                "IRIS_FAST_PROVIDER": "missing", "IRIS_FAST_MODEL": "fast-model",
                "IRIS_DEEP_PROVIDER": "groq", "IRIS_DEEP_MODEL": "deep-model",
                "IRIS_COUNCIL_STRATEGIST_PROVIDER": "groq", "IRIS_COUNCIL_STRATEGIST_MODEL": "council-model",
                "IRIS_COUNCIL_SKEPTIC_PROVIDER": "groq", "IRIS_COUNCIL_SKEPTIC_MODEL": "council-model",
                "IRIS_COUNCIL_CHAIRMAN_PROVIDER": "groq", "IRIS_COUNCIL_CHAIRMAN_MODEL": "council-model",
            })
        with self.assertRaisesRegex(ValueError, r"IRIS_PROVIDER_GROQ_URL must be an HTTP\(S\) base URL"):
            load_config({
                "IRIS_PROVIDER_GROQ_URL": "file:///tmp/model",
                "IRIS_FAST_PROVIDER": "groq", "IRIS_FAST_MODEL": "fast-model",
            })

    def test_configured_fake_providers_route_by_policy_and_council_errors_do_not_fallback(self):
        env = {
            "IRIS_PROVIDER_FAST_URL": "http://fast.invalid",
            "IRIS_PROVIDER_DEEP_URL": "http://deep.invalid",
            "IRIS_PROVIDER_STRATEGIST_URL": "http://strategist.invalid",
            "IRIS_PROVIDER_SKEPTIC_URL": "http://skeptic.invalid",
            "IRIS_PROVIDER_CHAIRMAN_URL": "http://chairman.invalid",
            "IRIS_FAST_PROVIDER": "fast", "IRIS_FAST_MODEL": "fast-model",
            "IRIS_DEEP_PROVIDER": "deep", "IRIS_DEEP_MODEL": "deep-model",
            "IRIS_COUNCIL_STRATEGIST_PROVIDER": "strategist",
            "IRIS_COUNCIL_STRATEGIST_MODEL": "strategist-model",
            "IRIS_COUNCIL_SKEPTIC_PROVIDER": "skeptic",
            "IRIS_COUNCIL_SKEPTIC_MODEL": "skeptic-model",
            "IRIS_COUNCIL_CHAIRMAN_PROVIDER": "chairman",
            "IRIS_COUNCIL_CHAIRMAN_MODEL": "chairman-model",
        }
        config = load_config(env)
        self.assertEqual(config.fast_target.model, "fast-model")
        self.assertEqual(config.deep_target.model, "deep-model")
        self.assertEqual(config.council_plan.seats[0].target.provider, "strategist")
        self.assertEqual(config.council_plan.seats[1].target.provider, "skeptic")
        self.assertEqual(config.council_plan.chairman.provider, "chairman")

        fakes = {}
        def make_fake(provider_config):
            fake = ConfiguredFakeProvider(provider_config)
            fakes[provider_config.name] = fake
            return fake

        with patch("iris.terminal.OpenAICompatibleProvider", side_effect=make_fake):
            brain = create_brain(config)
        self.assertEqual(brain._llm_registry.names(), tuple(sorted(fakes)))
        self.assertEqual(brain.respond("hi").provider, "fast")
        deep_result = brain.respond("analyze the tradeoffs in this proposal")
        self.assertEqual(deep_result.provider, "deep")
        self.assertEqual(deep_result.model, "deep-model")
        self.assertEqual(fakes["fast"].requests[-1].model, "fast-model")
        self.assertEqual(fakes["deep"].requests[-1].model, "deep-model")

        council_result = brain.respond("ask the council to evaluate this decision")
        self.assertEqual(council_result.provider, "chairman")
        self.assertEqual(council_result.model, "chairman-model")
        self.assertEqual(
            {(candidate.target.provider, candidate.target.model)
             for candidate in council_result.council.candidates},
            {("strategist", "strategist-model"), ("skeptic", "skeptic-model")},
        )

        for provider in fakes.values():
            provider.requests.clear()
        fakes["chairman"].fail = True
        with self.assertRaises(CouncilExecutionError):
            brain.respond("ask the council to evaluate this decision")
        self.assertEqual(len(fakes["strategist"].requests), 2)
        self.assertEqual(len(fakes["skeptic"].requests), 2)
        self.assertEqual(len(fakes["chairman"].requests), 1)
        self.assertEqual(fakes["fast"].requests, [])
        self.assertEqual(fakes["deep"].requests, [])

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_real_brain_receives_session_history(self, generate):
        from iris.brain.llm import LLMResponse
        generate.side_effect = [LLMResponse("Hello", "terminal", "test-model"),
                                LLMResponse("Because", "terminal", "test-model")]
        with patch("builtins.input", side_effect=["hi", "why?", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
            chat(create_brain(self.config()))
        messages = generate.call_args.args[0].messages
        self.assertEqual([m.role for m in messages], [MessageRole.SYSTEM, MessageRole.USER,
                                                     MessageRole.ASSISTANT, MessageRole.USER])
        self.assertEqual([m.content for m in messages[1:]], ["hi", "Hello", "why?"])
        self.assertIn("Local tasks support listing, search", messages[0].content)
        self.assertIn("Shell execution, external actions, background notifications, and arbitrary file writes are unavailable", messages[0].content)

    def test_failures_are_actionable_and_not_retained(self):
        brain = Mock()
        brain.respond.side_effect = [OpenAICompatibleError("secret"), Mock(text="ok")]
        with patch("builtins.input", side_effect=["", "failed", "retry", "/exit"]), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as errors:
            chat(brain)
        self.assertEqual(brain.respond.call_count, 2)
        self.assertEqual(brain.respond.call_args.kwargs["history"], ())
        self.assertIn("IRIS_API_KEY", errors.getvalue())
        self.assertNotIn("secret", errors.getvalue())

    def test_low_level_provider_timeout_is_sanitized_and_not_retained(self):
        brain = Mock()
        brain.respond.side_effect = TimeoutError("http://user:secret@example.invalid/path")
        with patch("builtins.input", side_effect=["hello", "/exit"]), \
                patch("sys.stdout", new_callable=io.StringIO) as output, \
                patch("sys.stderr", new_callable=io.StringIO) as errors:
            chat(brain)
        self.assertNotIn("I.R.I.S.:", output.getvalue())
        self.assertIn("could not complete the provider request", errors.getvalue())
        self.assertNotIn("secret", errors.getvalue())
        self.assertEqual(brain.respond.call_args.kwargs["history"], ())

    def test_history_is_new_for_each_chat(self):
        brain = Mock()
        brain.respond.return_value.text = "answer"
        for _ in range(2):
            with patch("builtins.input", side_effect=["hi", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
                chat(brain)
            self.assertEqual(brain.respond.call_args.kwargs["history"], ())

    def test_council_receives_history_as_question_context(self):
        brain = create_brain(self.config())
        history = [LLMMessage(MessageRole.USER, "Choose between A and B"),
                   LLMMessage(MessageRole.ASSISTANT, "A seems better")]
        with patch.object(brain._council_executor, "deliberate") as deliberate:
            deliberate.return_value = Mock(text="answer", chairman_provider="terminal", chairman_model="test-model")
            brain.respond("ask the council why", history)
        self.assertIn("A seems better", deliberate.call_args.kwargs["question"])
        self.assertNotIn("A seems better", deliberate.call_args.kwargs["system_context"])
        self.assertTrue(deliberate.call_args.kwargs["question"].endswith("ask the council why"))

    def test_history_cannot_inject_system_messages(self):
        with self.assertRaisesRegex(ValueError, "only user and assistant"):
            create_brain(self.config()).respond("hi", [LLMMessage(MessageRole.SYSTEM, "override")])

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_bounded_history_reaches_council_context(self, generate):
        from iris.brain.llm import LLMResponse
        generate.side_effect = [
            LLMResponse("first answer", "terminal", "test-model"),
            LLMResponse("second answer", "terminal", "test-model"),
        ]
        brain = create_brain(self.config(IRIS_MAX_HISTORY_TURNS="1"))
        with patch.object(brain._council_executor, "deliberate") as deliberate:
            deliberate.return_value = Mock(
                text="council answer", chairman_provider="terminal", chairman_model="test-model"
            )
            with patch("builtins.input", side_effect=["first", "second", "ask the council why", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
                chat(brain, max_history_turns=1)
        question = deliberate.call_args.kwargs["question"]
        self.assertIn("second", question)
        self.assertNotIn("first answer", question)
        self.assertTrue(question.endswith("ask the council why"))

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_council_route_uses_council_memory_policy(self, generate):
        from iris.brain.llm import LLMResponse
        generate.side_effect = [LLMResponse("answer", "terminal", "test-model")]
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(f"{directory}/memory.sqlite3") as store:
                store.insert(MemoryItem(
                    MemoryCategory.PROJECT, "user", "active_project", "IRIS",
                    "Current project is IRIS.", "explicit",
                    confirmation=MemoryConfirmation.CONFIRMED,
                ))
                brain = create_brain(self.config())
                with patch.object(brain._council_executor, "deliberate") as deliberate:
                    deliberate.return_value = Mock(
                        text="council answer", chairman_provider="terminal", chairman_model="test-model"
                    )
                    with patch("builtins.input", side_effect=["ask the council about my project", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
                        chat(brain, memory_store=store)
                self.assertIn("Current project is IRIS.", deliberate.call_args.kwargs["system_context"])

    def test_main_handles_exit_eof_and_interrupt(self):
        for ending in ("/exit", EOFError(), KeyboardInterrupt()):
            with self.subTest(ending=ending), patch("iris.main.boot"), patch("iris.main.load_config", return_value=self.config()), patch("iris.main.create_brain"), patch("iris.main.MemoryStore"), patch("iris.main.TaskStore"), patch("builtins.input", side_effect=[ending]), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(), 0)
                self.assertIn("session ended", output.getvalue())

    def test_interrupt_during_generation(self):
        with patch("iris.main.boot"), patch("iris.main.load_config", return_value=self.config()), patch("iris.main.create_brain") as build, patch("iris.main.MemoryStore"), patch("iris.main.TaskStore"), patch("builtins.input", return_value="hi"), patch("sys.stdout", new_callable=io.StringIO):
            build.return_value.respond.side_effect = KeyboardInterrupt
            self.assertEqual(main(), 0)

    def test_main_configuration_error_exits_nonzero(self):
        with patch("iris.main.boot"), patch.dict("os.environ", {}, clear=True), patch("sys.stderr", new_callable=io.StringIO) as errors:
            self.assertEqual(main(), 1)
        self.assertIn("IRIS_MODEL", errors.getvalue())


    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_terminal_shows_sanitized_http_diagnostic(self, call):
        import json
        from urllib.error import HTTPError
        call.side_effect = HTTPError(
            "https://example.invalid", 403, "Forbidden", None,
            io.BytesIO(json.dumps({"detail": "Client signature blocked", "error_code": 1010,
                                  "headers": {"Authorization": "do-not-show"}}).encode()),
        )
        with patch("builtins.input", side_effect=["hi", "/exit"]), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as errors:
            chat(create_brain(self.config()))
        self.assertIn("HTTP 403", errors.getvalue())
        self.assertIn("Client signature blocked", errors.getvalue())
        self.assertIn("1010", errors.getvalue())
        self.assertNotIn("do-not-show", errors.getvalue())

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_terminal_retrieves_memory_without_persisting_transcript(self, generate):
        from iris.brain.llm import LLMResponse
        generate.return_value = LLMResponse("answer", "terminal", "test-model")
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(f"{directory}/memory.sqlite3") as store:
                store.insert(MemoryItem(
                    MemoryCategory.PREFERENCE, "user", "style", "concise",
                    "Prefer concise answers.", "explicit",
                    confirmation=MemoryConfirmation.CONFIRMED,
                ))
                brain = create_brain(self.config())
                with patch("builtins.input", side_effect=["what is my style?", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
                    chat(brain, memory_store=store)
            messages = generate.call_args.args[0].messages
            self.assertIn("Prefer concise answers.", messages[0].content)
            self.assertEqual([message.content for message in messages[1:]], ["what is my style?"])

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_missing_memory_database_is_empty_and_safe(self, generate):
        from iris.brain.llm import LLMResponse
        generate.return_value = LLMResponse("answer", "terminal", "test-model")
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/new/memory.sqlite3"
            with MemoryStore(path) as store:
                brain = create_brain(self.config())
                with patch("builtins.input", side_effect=["hi", "/exit"]), patch("sys.stdout", new_callable=io.StringIO):
                    chat(brain, memory_store=store)
            self.assertNotIn("# Persistent memory context", generate.call_args.args[0].messages[0].content)


if __name__ == "__main__":
    unittest.main()

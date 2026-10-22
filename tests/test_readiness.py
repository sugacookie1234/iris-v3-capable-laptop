
import os as _platform_os
import unittest as _platform_tests
if _platform_os.name == "nt":
    raise _platform_tests.SkipTest("Legacy POSIX launcher/permissions/deadline tests; Windows desktop has dedicated tests")

import unittest
import time
import signal
import io
from types import SimpleNamespace
from urllib.error import URLError, HTTPError
from unittest.mock import patch

from iris.brain.llm import LLMResponse
from iris.brain.providers.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleError
from iris.readiness import main, warm_provider


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        saved = patch("iris.local_config.read_saved", return_value={})
        saved.start()
        self.addCleanup(saved.stop)
        self.config = OpenAICompatibleConfig("local", "http://127.0.0.1:11434", timeout_seconds=2)

    def test_default_cli_is_local_only(self):
        with patch("iris.readiness.load_config", side_effect=AssertionError("must not load provider")):
            self.assertEqual(main([]), 0)

    def test_successful_probe_never_claims_normal_chat_verification(self):
        with patch("iris.readiness.load_config", return_value=SimpleNamespace(provider=self.config, model="model")), \
             patch("iris.readiness.OpenAICompatibleProvider.generate", return_value=LLMResponse("ready", "local", "model")), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["--live"]), 0)
        self.assertIn("PASS", output.getvalue())
        self.assertIn("scope=tiny_probe normal_chat_verified=False", output.getvalue())

    def test_warm_request_reports_ready_without_persisting_state(self):
        response = LLMResponse("ready", "local", "model")
        with patch("iris.readiness.OpenAICompatibleProvider.generate", return_value=response) as generate:
            result = warm_provider(self.config, "model")
        self.assertTrue(result.usable)
        self.assertEqual(result.status, "ready")
        request = generate.call_args.args[0]
        self.assertEqual(request.model, "model")
        self.assertEqual(request.messages[-1].content, "ready")

    def test_provider_failure_is_truthful_and_sanitized(self):
        with patch("iris.readiness.OpenAICompatibleProvider.generate",
                   side_effect=OpenAICompatibleError("private response")):
            result = warm_provider(self.config, "model")
        self.assertIsNone(result.reachable)
        self.assertFalse(result.usable)
        self.assertEqual(result.status, "inference_failed")

    def test_cancellation_prevents_request(self):
        with patch("iris.readiness.OpenAICompatibleProvider.generate") as generate:
            result = warm_provider(self.config, "model", cancel=lambda: True)
        generate.assert_not_called()
        self.assertEqual(result.status, "cancelled")

    def test_timeout_is_bounded(self):
        with self.assertRaises(ValueError):
            warm_provider(self.config, "model", timeout_seconds=121)

    def test_wrapped_transport_errors_are_not_inference_failures(self):
        for cause, status, reachable in (
            (TimeoutError(), "transport_timeout", None),
            (URLError(ConnectionRefusedError()), "unreachable", False),
            (HTTPError("secret", 500, "secret", {}, None), "http_error", True),
        ):
            error = OpenAICompatibleError("private response")
            error.__cause__ = cause
            with self.subTest(status=status), patch(
                "iris.readiness.OpenAICompatibleProvider.generate", side_effect=error
            ):
                result = warm_provider(self.config, "model")
            self.assertEqual(result.status, status)
            self.assertIs(result.reachable, reachable)
            self.assertNotIn("private", repr(result))

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX deadline required")
    def test_deadline_interrupts_blocking_request_and_restores_handler(self):
        handler = signal.getsignal(signal.SIGALRM)
        with patch("iris.readiness.OpenAICompatibleProvider.generate",
                   side_effect=lambda request: time.sleep(5)):
            result = warm_provider(self.config, "model", timeout_seconds=0.05)
        self.assertEqual(result.status, "deadline_exceeded")
        self.assertLess(result.elapsed_seconds, 1)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX deadline required")
    def test_cancellation_interrupts_inflight_request(self):
        started = time.monotonic()
        with patch("iris.readiness.OpenAICompatibleProvider.generate",
                   side_effect=lambda request: time.sleep(5)):
            result = warm_provider(self.config, "model", cancel=lambda: time.monotonic()-started > 0.02)
        self.assertEqual(result.status, "cancelled")
        self.assertLess(result.elapsed_seconds, 1)

    def test_keyboard_interrupt_is_sanitized(self):
        with patch("iris.readiness.OpenAICompatibleProvider.generate", side_effect=KeyboardInterrupt):
            self.assertEqual(warm_provider(self.config, "model").status, "cancelled")

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX deadline required")
    def test_deadline_closes_response_during_body_read(self):
        class Response:
            closed = False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.closed = True
            def read(self):
                time.sleep(5)
        response = Response()
        with patch("iris.brain.providers.openai_compatible.urlopen", return_value=response):
            result = warm_provider(self.config, "model", timeout_seconds=0.05)
        self.assertEqual(result.status, "deadline_exceeded")
        self.assertTrue(response.closed)

    def test_non_main_thread_refuses_to_start_unbounded_request(self):
        import threading
        results = []
        with patch("iris.readiness.OpenAICompatibleProvider.generate") as generate:
            worker = threading.Thread(target=lambda: results.append(warm_provider(self.config, "model")))
            worker.start()
            worker.join(1)
        generate.assert_not_called()
        self.assertEqual(results[0].status, "deadline_unavailable")


if __name__ == "__main__":
    unittest.main()

"""Regression checks for locating provider waits without exposing content."""
import io
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.brain.llm import emit_timing
from iris.memory.store import MemoryStore
from iris.terminal import chat, create_brain, load_config
from tests.test_openai_compatible import FakeHTTPResponse


class ProviderTimingTests(unittest.TestCase):
    def test_direct_http_and_production_adapter_use_identical_payload(self):
        bodies = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                bodies.append(self.rfile.read(int(self.headers["Content-Length"])))
                encoded = json.dumps({"choices": [{"message": {"content": "synthetic reply"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            config = load_config({"IRIS_PROVIDER_URL": f"http://127.0.0.1:{server.server_port}",
                                  "IRIS_MODEL": "synthetic", "IRIS_TIMEOUT_SECONDS": "2"})
            brain = create_brain(config)
            response = brain.respond("hi")
            self.assertEqual(response.text, "synthetic reply")
            self.assertEqual(len(bodies), 1)
            connection.request("POST", "/v1/chat/completions", bodies[0],
                               {"Content-Type": "application/json"})
            direct = json.loads(connection.getresponse().read())
            self.assertEqual(direct["choices"][0]["message"]["content"], response.text)
            self.assertEqual(bodies[0], bodies[1])
            payload = json.loads(bodies[0])
            self.assertEqual(len(payload["messages"]), 2)
            self.assertEqual(payload["max_tokens"], 500)
            self.assertFalse(payload["stream"])
            self.assertNotIn("tools", payload)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def run_chat(self, responses):
        with tempfile.TemporaryDirectory() as directory, \
                MemoryStore(Path(directory) / "memory.sqlite3") as store:
            config = load_config({"IRIS_PROVIDER_URL": "http://127.0.0.1:11434",
                                  "IRIS_MODEL": "PRIVATE_MODEL", "IRIS_API_KEY": "PRIVATE_KEY"})
            brain = create_brain(config)
            with patch.dict("os.environ", {"IRIS_TIMING_DIAGNOSTICS": "1"}), \
                    patch("sys.stdin", io.StringIO("hi\nretry\n/exit\n")), \
                    patch("sys.stdout", new_callable=io.StringIO) as output, \
                    patch("sys.stderr", new_callable=io.StringIO) as errors, \
                    patch("iris.brain.providers.openai_compatible.urlopen", side_effect=responses) as send:
                chat(brain, memory_store=store)
            self.assertEqual(store.current(), ())
        return output.getvalue(), errors.getvalue(), send.call_args_list

    def test_header_timeout_is_distinct_and_failed_turn_is_not_retained(self):
        output, trace, calls = self.run_chat([
            TimeoutError("PRIVATE_NETWORK_DETAIL"),
            FakeHTTPResponse({"choices": [{"message": {"content": "PRIVATE_RESPONSE"}}]}),
        ])
        self.assertEqual(len(calls), 2)
        self.assertIn("stage=http_headers", trace)
        first = trace.split("stage=terminal_turn")[0]
        self.assertNotIn("stage=http_body", first)
        self.assertNotIn("stage=response_parse", first)
        self.assertEqual(output.count("I.R.I.S.:"), 1)
        import json
        second = json.loads(calls[1].args[0].data)
        self.assertEqual(len(second["messages"]), 2)
        for private in ("PRIVATE_NETWORK_DETAIL", "PRIVATE_MODEL", "PRIVATE_KEY", "PRIVATE_RESPONSE"):
            self.assertNotIn(private, trace)

    def test_body_timeout_closes_response_and_does_not_claim_success(self):
        class StalledBody(FakeHTTPResponse):
            closed = False

            def read(self):
                raise TimeoutError("PRIVATE_BODY_DETAIL")

            def __exit__(self, *args):
                self.closed = True

        response = StalledBody({})
        output, trace, _ = self.run_chat([response, response])
        self.assertTrue(response.closed)
        self.assertIn("stage=http_body", trace)
        self.assertNotIn("stage=response_parse", trace)
        self.assertNotIn("I.R.I.S.:", output)
        self.assertNotIn("PRIVATE_BODY_DETAIL", trace)

    def test_completed_response_is_parsed_once_per_turn(self):
        response = FakeHTTPResponse({"choices": [{"message": {"content": "PRIVATE_RESPONSE"}}]})
        output, trace, calls = self.run_chat([response, response])
        self.assertEqual(len(calls), 2)
        self.assertEqual(trace.count("stage=response_parse"), 2)
        self.assertEqual(output.count("I.R.I.S.:"), 2)
        self.assertNotIn("PRIVATE_RESPONSE", trace)
        self.assertIn("reasoning=FAST", trace)

    def test_timing_rejects_arbitrary_fields_values_and_stages(self):
        with patch.dict("os.environ", {"IRIS_TIMING_DIAGNOSTICS": "1"}), \
                patch("sys.stderr", new_callable=io.StringIO) as output:
            emit_timing("PRIVATE_STAGE", 0, outcome="ok")
            emit_timing("provider_call", 0, provider="PRIVATE_PROVIDER", model="PRIVATE_MODEL",
                        outcome="PRIVATE_ERROR", input_chars="PRIVATE_INPUT", message_count="2")
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertIn("message_count=2", output.getvalue())


if __name__ == "__main__":
    unittest.main()

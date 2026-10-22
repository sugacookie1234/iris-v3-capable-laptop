import io
import json
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from iris.brain.llm import (
    GenerationOptions,
    LLMMessage,
    LLMRequest,
    MessageRole,
    LLMToolCall,
    LLMToolDefinition,
)
from iris.brain.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleError,
    OpenAICompatibleProvider,
)
from iris.terminal import create_brain, load_config


class FakeHTTPResponse:
    def __init__(
        self,
        data: dict,
        status: int = 200,
    ) -> None:
        self.status = status
        self._body = json.dumps(data).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_incomplete_response_is_not_reported_as_a_finished_answer(self):
        with self.assertRaisesRegex(OpenAICompatibleError, 'response limit'):
            self.make_provider()._parse_response({'choices': [
                {'finish_reason': 'length', 'message': {'content': 'Partial sentence'}}]}, 'test')

    def test_default_voice_model_disables_hidden_reasoning_only_on_openrouter(self):
        from dataclasses import replace
        request = replace(self.make_request(), model='nvidia/nemotron-3.5-lightning:free')
        for endpoint, expected in [('https://openrouter.ai/api/v1', True), ('https://example.invalid/v1', False)]:
            provider = OpenAICompatibleProvider(OpenAICompatibleConfig('test', endpoint))
            with patch('iris.brain.providers.openai_compatible.urlopen', return_value=FakeHTTPResponse(
                    {'choices': [{'message': {'content': 'Complete.'}}]})) as send:
                provider.generate(request)
            payload = json.loads(send.call_args.args[0].data)
            self.assertEqual('reasoning' in payload, expected)
            if expected:
                self.assertEqual(payload['reasoning'], {'effort': 'none'})
                self.assertGreaterEqual(payload['max_tokens'], 1200)

    def make_provider(
        self,
        api_key: str | None = "secret",
    ) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                name="test-cloud",
                base_url="https://example.invalid",
                api_key=api_key,
                timeout_seconds=12,
            )
        )

    def make_request(self) -> LLMRequest:
        return LLMRequest(
            model="iris-test-model",
            messages=[
                LLMMessage(
                    MessageRole.SYSTEM,
                    "You are I.R.I.S.",
                ),
                LLMMessage(
                    MessageRole.USER,
                    "hello",
                ),
            ],
            options=GenerationOptions(
                temperature=0.2,
                max_tokens=123,
            ),
        )

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_generate_parses_response(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {
                "model": "iris-test-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello, Khai.",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 4,
                },
            }
        )

        provider = self.make_provider()
        response = provider.generate(self.make_request())

        self.assertEqual(response.text, "Hello, Khai.")
        self.assertEqual(response.provider, "test-cloud")
        self.assertEqual(response.model, "iris-test-model")
        self.assertEqual(response.input_tokens, 20)
        self.assertEqual(response.output_tokens, 4)

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_generate_sends_correct_payload(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            }
        )

        provider = self.make_provider()
        provider.generate(self.make_request())

        http_request = mock_urlopen.call_args.args[0]

        payload = json.loads(
            http_request.data.decode("utf-8")
        )

        self.assertEqual(
            payload["model"],
            "iris-test-model",
        )
        self.assertEqual(
            payload["temperature"],
            0.2,
        )
        self.assertEqual(
            payload["max_tokens"],
            123,
        )
        self.assertFalse(payload["stream"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

        self.assertEqual(
            payload["messages"][1],
            {
                "role": "user",
                "content": "hello",
            },
        )

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_tool_request_uses_automatic_choice_and_parses_groq_call(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse({
            "model": "iris-test-model",
            "choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_123", "type": "function", "function": {
                    "name": "workspace_read", "arguments": '{"path":"README.md"}'
                }}],
            }}],
        })
        tool = LLMToolDefinition(
            "workspace_read", "Read workspace text",
            {"type": "object", "properties": {"path": {"type": "string"}},
             "required": ["path"], "additionalProperties": False},
        )
        request = LLMRequest(
            "iris-test-model", self.make_request().messages,
            tools=(tool,),
        )
        response = self.make_provider().generate(request)
        self.assertEqual(response.text, "")
        self.assertEqual(response.tool_calls, (LLMToolCall("call_123", "workspace_read", {"path": "README.md"}),))
        payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["tools"][0]["function"]["name"], "workspace_read")

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_tool_result_message_is_serialized_with_matching_call_id(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse({
            "choices": [{"message": {"role": "assistant", "content": "README says hello."}}]
        })
        call = LLMToolCall("call_123", "workspace_read", {"path": "README.md"})
        request = LLMRequest("iris-test-model", [
            LLMMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)),
            LLMMessage(MessageRole.TOOL, '{"status":"success","result":{"text":"hello"}}',
                       tool_call_id="call_123"),
        ])
        self.make_provider().generate(request)
        messages = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))["messages"]
        self.assertEqual(messages[0]["tool_calls"][0]["id"], "call_123")
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["tool_call_id"], "call_123")
        self.assertIn('"hello"', messages[1]["content"])

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_groq_tool_call_executes_and_returns_result_for_final_answer(self, mock_urlopen):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "course.md").write_text("COMP 248 lab notes and lecture links.", encoding="utf-8")
            mock_urlopen.side_effect = [
                FakeHTTPResponse({"choices": [{"message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "call_groq_1", "type": "function", "function": {
                        "name": "obsidian_search", "arguments": '{"query":"COMP 248"}'
                    }}],
                }}]}),
                FakeHTTPResponse({"choices": [{"message": {
                    "role": "assistant", "content": "Your notes mention COMP 248 lab notes and lecture links."
                }}]}),
            ]
            config = load_config({
                "IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "groq-compatible-model",
                "IRIS_OBSIDIAN_ROOT": directory,
            })
            brain = create_brain(config)
            result = brain.respond("Search my notes for COMP 248")

        self.assertIsNone(result.tool_result.failure)
        self.assertEqual(result.tool_result.value["results"][0]["path"], "course.md")
        self.assertEqual(result.text, "Your notes mention COMP 248 lab notes and lecture links.")

        first = json.loads(mock_urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        followup = json.loads(mock_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(first["tool_choice"], "auto")
        self.assertIn("obsidian_search", [tool["function"]["name"] for tool in first["tools"]])
        call_message = next(message for message in followup["messages"] if message.get("tool_calls"))
        tool_message = next(message for message in followup["messages"] if message["role"] == "tool")
        self.assertEqual(call_message["tool_calls"][0]["id"], "call_groq_1")
        self.assertEqual(tool_message["tool_call_id"], "call_groq_1")
        self.assertIn("course.md", tool_message["content"])
        self.assertNotIn("tools", followup)
        self.assertNotIn("tool_choice", followup)

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_api_key_stays_in_authorization_header(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            }
        )

        provider = self.make_provider("very-secret-key")
        provider.generate(self.make_request())

        http_request = mock_urlopen.call_args.args[0]

        self.assertEqual(
            http_request.get_header("Authorization"),
            "Bearer very-secret-key",
        )

        body = http_request.data.decode("utf-8")
        self.assertNotIn("very-secret-key", body)

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_requests_send_iris_user_agent(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )

        self.make_provider().generate(self.make_request())

        http_request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            http_request.get_header("User-agent"),
            "IRIS-v3/0.1",
        )

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_requests_close_connection_for_local_response_handoff(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )
        self.make_provider().generate(self.make_request())
        http_request = mock_urlopen.call_args.args[0]
        self.assertEqual(http_request.get_header("Connection"), "close")

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_healthcheck_true_when_endpoint_responds(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {"data": []},
            status=200,
        )

        provider = self.make_provider()

        self.assertTrue(provider.healthcheck())

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_healthcheck_false_when_unreachable(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.side_effect = URLError(
            "connection refused"
        )

        provider = self.make_provider()

        self.assertFalse(provider.healthcheck())

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_http_error_is_reported_cleanly(
        self,
        mock_urlopen: Mock,
    ) -> None:
        body = io.BytesIO(
            json.dumps(
                {
                    "error": {
                        "message": "invalid API key"
                    }
                }
            ).encode("utf-8")
        )

        mock_urlopen.side_effect = HTTPError(
            url="https://example.invalid",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=body,
        )

        provider = self.make_provider()

        with self.assertRaisesRegex(
            OpenAICompatibleError,
            "invalid API key",
        ):
            provider.generate(self.make_request())

    @patch(
        "iris.brain.providers.openai_compatible.urlopen"
    )
    def test_missing_choices_fails_loudly(
        self,
        mock_urlopen: Mock,
    ) -> None:
        mock_urlopen.return_value = FakeHTTPResponse(
            {
                "model": "iris-test-model",
                "choices": [],
            }
        )

        provider = self.make_provider()

        with self.assertRaisesRegex(
            OpenAICompatibleError,
            "no choices",
        ):
            provider.generate(self.make_request())


    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_sanitized_http_diagnostic_preserves_cause(self, call):
        key = "synthetic-test-credential"
        payload = {"error": {"message":
            "Invalid credential " + key + "\nAuthorization: Bearer another-value\n"
            "headers: X-Debug: private-value\nTry a valid model.\x1b[31m"},
            "headers": {"X-Private": "never-display"}}
        cause = HTTPError("https://example.invalid", 401, "Unauthorized", None,
                          io.BytesIO(json.dumps(payload).encode()))
        call.side_effect = cause
        with self.assertRaises(OpenAICompatibleError) as caught:
            self.make_provider(key).generate(self.make_request())
        error = caught.exception
        self.assertIs(error.__cause__, cause)
        self.assertIn("HTTP 401", error.diagnostic)
        self.assertIn("Try a valid model", error.diagnostic)
        for sensitive in (key, "another-value", "private-value", "never-display", "Authorization", "\x1b"):
            self.assertNotIn(sensitive, error.diagnostic)
        self.assertEqual(str(error), error.diagnostic)

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_cloudflare_diagnostic_and_unexpected_bodies(self, call):
        cases = [
            (json.dumps({"title": "Access denied", "detail": "Client signature blocked",
                         "error_code": 1010, "headers": {"private": "hidden"}}), "1010"),
            ('["unexpected"]', "unrecognized"),
            ('null', "unrecognized"),
            ('<html>private diagnostic page</html>', "HTML"),
            ('', "empty"),
            ('Service temporarily unavailable', "temporarily unavailable"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                cause = HTTPError("https://example.invalid", 403, "Forbidden", None,
                                  io.BytesIO(body.encode()))
                call.side_effect = cause
                with self.assertRaises(OpenAICompatibleError) as caught:
                    self.make_provider().generate(self.make_request())
                self.assertIs(caught.exception.__cause__, cause)
                self.assertIn("HTTP 403", caught.exception.diagnostic)
                self.assertIn(expected, caught.exception.diagnostic)
                self.assertNotIn("hidden", caught.exception.diagnostic)

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_network_error_sanitized_and_cause_preserved(self, call):
        cause = URLError("connection refused https://user:password@host?token=value")
        call.side_effect = cause
        with self.assertRaises(OpenAICompatibleError) as caught:
            self.make_provider().generate(self.make_request())
        self.assertIs(caught.exception.__cause__, cause)
        self.assertIn("connection refused", caught.exception.diagnostic)
        self.assertNotIn("password", caught.exception.diagnostic)

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_socket_read_timeout_is_reported_as_timeout(self, call):
        call.side_effect = socket.timeout("private endpoint detail")
        with self.assertRaisesRegex(OpenAICompatibleError, "timed out") as caught:
            self.make_provider().generate(self.make_request())
        self.assertNotIn("private endpoint detail", caught.exception.diagnostic)

    @patch("iris.brain.providers.openai_compatible.urlopen")
    def test_groq_url_has_exactly_one_v1(self, call):
        from iris.terminal import load_config
        for url in ("https://api.groq.com/openai", "https://api.groq.com/openai/v1",
                    "https://api.groq.com/openai/v1/"):
            configs = [OpenAICompatibleConfig("test", url),
                       load_config({"IRIS_PROVIDER_URL": url, "IRIS_MODEL": "test"}).provider]
            for config in configs:
                with self.subTest(url=url, config=config):
                    call.return_value = FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}]})
                    provider = OpenAICompatibleProvider(config)
                    provider.generate(self.make_request())
                    self.assertEqual(call.call_args.args[0].full_url,
                                     "https://api.groq.com/openai/v1/chat/completions")
                    self.assertTrue(provider.healthcheck())
                    self.assertEqual(call.call_args.args[0].full_url,
                                     "https://api.groq.com/openai/v1/models")


if __name__ == "__main__":
    unittest.main()

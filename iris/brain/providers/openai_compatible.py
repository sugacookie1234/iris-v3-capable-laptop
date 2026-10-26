from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.brain.llm import (
    LLMToolCall,
    LLMRequest,
    LLMResponse,
    emit_timing,
)


class OpenAICompatibleError(RuntimeError):
    """Raised when an OpenAI-compatible provider request fails."""

    def __init__(self, message: str, *, diagnostic: str | None = None) -> None:
        super().__init__(message)
        # Only provider-sanitized text is suitable for terminal display.
        self.diagnostic = diagnostic or "Provider request failed."


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    name: str
    base_url: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 60.0


class OpenAICompatibleProvider:
    """
    Minimal OpenAI-compatible chat provider.

    This intentionally depends only on Python's standard library.

    Compatible backends may include:
    - OpenAI-compatible cloud services
    - OpenRouter-style gateways
    - LiteLLM
    - local model servers exposing /v1/chat/completions
    - future GPU inference servers
    """

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        name = config.name.strip().lower()
        base_url = config.base_url.strip().rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        if not name:
            raise ValueError("Provider name cannot be empty.")

        if not base_url:
            raise ValueError("Provider base URL cannot be empty.")

        self._name = name
        self._base_url = base_url
        self._api_key = config.api_key
        self._timeout = config.timeout_seconds

    @property
    def name(self) -> str:
        return self._name

    def _error(self, message: str) -> OpenAICompatibleError:
        safe = self._sanitize(message)
        return OpenAICompatibleError(safe, diagnostic=safe)

    def _sanitize(self, text: str) -> str:
        if self._api_key:
            for value in (self._api_key, quote(self._api_key, safe=""),
                          json.dumps(self._api_key)[1:-1]):
                text = text.replace(value, "[redacted]")
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        # Discard echoed header/credential fields, including arbitrary header maps.
        text = re.sub(
            r"(?im)(?:[\w-]*headers?|authorization|proxy-authorization|"
            r"cookie|set-cookie|x-api-key|api[_ -]?key|access[_ -]?token)"
            r"[\"']?\s*[:=].*$", "[redacted fields]", text,
        )
        text = re.sub(r"(?i)\b(?:bearer|basic)\s+\S+", "[redacted auth]", text)
        text = re.sub(r"\b(?:gsk_|sk-)[\w-]+", "[redacted key]", text)
        # URLs can contain credentials or query tokens, including network errors.
        text = re.sub(r"https?://\S+", "[redacted URL]", text)
        text = "".join(c if c.isprintable() or c.isspace() else " " for c in text)
        return " ".join(text.split())[:500]

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Explicitly document urllib's existing non-persistent transport.
            # This header alone does not resolve slow server generation.
            "Connection": "close",
            "User-Agent": "IRIS-v3/0.1",
        }

        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        return headers

    def healthcheck(self) -> bool:
        """
        Check whether the provider endpoint is reachable.

        We use /v1/models because it is part of the common OpenAI-compatible
        surface and does not require generating tokens.
        """
        request = Request(
            f"{self._base_url}/v1/models",
            headers=self._headers(),
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout) as response:
                return 200 <= response.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "messages": [self._serialize_message(message) for message in request.messages],
            "temperature": request.options.temperature,
            "max_tokens": request.options.max_tokens,
            "stream": False,
        }
        if request.web_search:
            if self._base_url != "https://openrouter.ai/api":
                raise self._error("Web search requires the configured OpenRouter endpoint.")
            if request.tools:
                raise self._error("Web research cannot execute local tools in the same request.")
            payload["plugins"] = [{"id": "web", "engine": "exa", "max_results": 3}]
        # This default voice model supports disabling hidden reasoning. Keep
        # other models/providers on their own defaults, including council roles.
        if (self._base_url == "https://openrouter.ai/api"
                and request.model == "nvidia/nemotron-3.5-lightning:free"):
            payload["reasoning"] = {"effort": "none"}
            payload["max_tokens"] = max(1200, request.options.max_tokens)
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": tool.name, "description": tool.description,
                    "parameters": tool.parameters,
                }} for tool in request.tools
            ]
            # Groq and OpenAI-compatible APIs use automatic selection when tools
            # are exposed. Never pair advertised tools with tool_choice="none".
            payload["tool_choice"] = "auto"

        body = json.dumps(payload).encode("utf-8")

        http_request = Request(
            f"{self._base_url}/v1/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )

        try:
            started = time.monotonic()
            outcome = "error"
            try:
                response = urlopen(http_request, timeout=self._timeout)
                outcome = "ok"
            except KeyboardInterrupt:
                outcome = "cancelled"
                raise
            finally:
                emit_timing("http_headers", started, outcome=outcome)
            with response:
                started = time.monotonic()
                outcome = "error"
                try:
                    raw = response.read().decode("utf-8")
                    outcome = "ok"
                except KeyboardInterrupt:
                    outcome = "cancelled"
                    raise
                finally:
                    emit_timing("http_body", started, outcome=outcome)

        except HTTPError as exc:
            detail = self._read_http_error(exc)
            raise self._error(
                f"{self.name} returned HTTP {exc.code}: {detail}"
            ) from exc

        except URLError as exc:
            raise self._error(
                f"{self.name} is unreachable: {exc.reason}"
            ) from exc

        except (TimeoutError, socket.timeout) as exc:
            raise self._error(
                f"{self.name} request timed out after "
                f"{self._timeout:g} seconds"
            ) from exc

        except OSError as exc:
            raise self._error(
                f"{self.name} request failed: {exc}"
            ) from exc

        started = time.monotonic()
        outcome = "error"
        try:
            data = json.loads(raw)
            result = self._parse_response(data, request.model)
            outcome = "ok"
            return result
        except json.JSONDecodeError as exc:
            raise self._error(
                f"{self.name} returned invalid JSON"
            ) from exc

        finally:
            emit_timing("response_parse", started, outcome=outcome)

    @staticmethod
    def _serialize_message(message) -> dict[str, object]:
        result: dict[str, object] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.tool_call_id is not None:
            result["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            result["tool_calls"] = [{
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            } for call in message.tool_calls]
        return result

    @staticmethod
    def _read_http_error(exc: HTTPError) -> str:
        try:
            raw = exc.read(16384).decode("utf-8", errors="replace")
        except Exception:
            return "Could not read provider error body."
        finally:
            exc.close()

        if not raw:
            return "Provider returned an empty error body."

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if "<" in raw:
                return "Provider returned an HTML or non-JSON error page."
            return raw

        if not isinstance(data, dict):
            return "Provider returned an unrecognized error body."

        error = data.get("error")

        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message

        if isinstance(error, str):
            return error

        # Allow only diagnostic fields; never dump headers or the request object.
        fields = [data.get(key) for key in ("title", "detail", "message", "error_code")]
        details = [str(value) for value in fields if isinstance(value, (str, int))]
        return "; ".join(details) or "Provider returned an unrecognized error body."

    def _parse_response(
        self,
        data: object,
        requested_model: str,
    ) -> LLMResponse:
        if not isinstance(data, dict):
            raise self._error(
                f"{self.name} returned an unexpected response shape"
            )

        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            raise self._error(
                f"{self.name} response contained no choices"
            )

        first_choice = choices[0]

        if not isinstance(first_choice, dict):
            raise self._error(
                f"{self.name} returned an invalid choice"
            )

        if first_choice.get("finish_reason") == "length":
            raise self._error("The model reached its response limit. Ask for a shorter answer or choose another model.")

        message = first_choice.get("message")

        if not isinstance(message, dict):
            raise self._error(
                f"{self.name} response contained no assistant message"
            )

        content = message.get("content")
        raw_calls = message.get("tool_calls", [])
        if content is None and raw_calls:
            content = ""
        if not isinstance(content, str):
            raise self._error(
                f"{self.name} response contained no text content"
            )

        if not isinstance(raw_calls, list):
            raise self._error(f"{self.name} returned invalid tool calls")
        tool_calls = []
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                raise self._error(f"{self.name} returned an invalid tool call")
            call_id = raw_call.get("id")
            function = raw_call.get("function")
            if not isinstance(call_id, str) or not call_id or not isinstance(function, dict):
                raise self._error(f"{self.name} returned an invalid tool call")
            name = function.get("name")
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise self._error(f"{self.name} returned invalid tool arguments") from exc
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise self._error(f"{self.name} returned invalid tool arguments")
            tool_calls.append(LLMToolCall(call_id, name, arguments))

        usage = data.get("usage")
        input_tokens: int | None = None
        output_tokens: int | None = None

        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")

            if isinstance(prompt_tokens, int):
                input_tokens = prompt_tokens

            if isinstance(completion_tokens, int):
                output_tokens = completion_tokens

        model = data.get("model")
        if not isinstance(model, str) or not model:
            model = requested_model

        citations = []
        annotations = message.get("annotations", [])
        if isinstance(annotations, list):
            for annotation in annotations[:30]:
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                citation = annotation.get("url_citation")
                if isinstance(citation, dict) and isinstance(citation.get("url"), str):
                    title = citation.get("title")
                    citations.append({"url": citation["url"], "title": title if isinstance(title, str) else "Source"})
        return LLMResponse(
            text=content,
            provider=self.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tuple(tool_calls),
            citations=tuple(citations),
        )

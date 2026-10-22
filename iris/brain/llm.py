from __future__ import annotations

from dataclasses import dataclass, field
import os
import sys
import time
from enum import StrEnum
from typing import Any, Protocol, Sequence


def emit_timing(stage: str, started: float, **fields: str) -> None:
    """Emit opt-in, content-free timing diagnostics for one application turn."""
    if os.environ.get("IRIS_TIMING_DIAGNOSTICS", "").strip().lower() not in {"1", "true", "yes"}:
        return
    if stage not in {"route", "context_assembly", "provider_call", "terminal_turn",
                     "http_headers", "http_body", "response_parse"}:
        return
    allowed = {
        "reasoning": {"DETERMINISTIC", "FAST", "DEEP", "COUNCIL"},
        "route": {"CONVERSATION", "OPERATIONS", "COMPANION", "URGENT"},
        "outcome": {"ok", "error", "cancelled", "success", "provider_error", "transport_error"},
        "memory_context": {"present", "empty"},
    }
    numeric = {"history_messages", "message_count", "input_chars", "tool_count", "max_tokens"}
    elapsed = max(0.0, time.monotonic() - started)
    safe_fields = " ".join(
        f"{key}={value}" for key, value in fields.items()
        if isinstance(value, str) and (
            value in allowed.get(key, set()) or
            (key in numeric and value.isascii() and value.isdecimal() and len(value) <= 12)
        )
    )
    print(f"iris_timing stage={stage} duration_seconds={elapsed:.3f} {safe_fields}".rstrip(), file=sys.stderr)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class LLMToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMMessage:
    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: Sequence[LLMToolCall] = ()


@dataclass(frozen=True)
class GenerationOptions:
    temperature: float = 0.4
    max_tokens: int = 800


@dataclass(frozen=True)
class ModelTarget:
    """
    A provider/model pair.

    Examples:
        provider="ollama", model="llama3.2"
        provider="cloud", model="some-fast-model"
    """

    provider: str
    model: str


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: Sequence[LLMMessage]
    options: GenerationOptions = field(default_factory=GenerationOptions)
    tools: Sequence[LLMToolDefinition] = ()


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: Sequence[LLMToolCall] = ()


class LLMProvider(Protocol):
    """
    Contract every model provider must implement.

    The rest of I.R.I.S. talks to this interface, not directly to
    Ollama, OpenAI, OpenRouter, or any future provider.
    """

    @property
    def name(self) -> str:
        ...

    def generate(self, request: LLMRequest) -> LLMResponse:
        ...

    def healthcheck(self) -> bool:
        ...


class ProviderNotFoundError(LookupError):
    pass


class LLMRegistry:
    """
    Runtime registry of available LLM providers.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        name = provider.name.strip().lower()

        if not name:
            raise ValueError("Provider name cannot be empty.")

        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")

        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider:
        key = name.strip().lower()

        try:
            return self._providers[key]
        except KeyError as exc:
            raise ProviderNotFoundError(
                f"LLM provider is not registered: {name}"
            ) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def healthy(self) -> dict[str, bool]:
        return {
            name: provider.healthcheck()
            for name, provider in self._providers.items()
        }

    def generate(
        self,
        target: ModelTarget,
        messages: Sequence[LLMMessage],
        options: GenerationOptions | None = None,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        started = time.monotonic()
        provider = self.get(target.provider)
        request = LLMRequest(
            model=target.model,
            messages=messages,
            options=options or GenerationOptions(),
            tools=tools,
        )
        input_chars = str(sum(len(message.content) for message in messages))
        message_count = str(len(messages))
        tool_count = str(len(tools))
        max_tokens = str(request.options.max_tokens)
        try:
            response = provider.generate(request)
        except Exception:
            emit_timing(
                "provider_call", started, provider=provider.name, model=target.model,
                outcome="error", message_count=message_count, input_chars=input_chars,
                tool_count=tool_count, max_tokens=max_tokens,
            )
            raise
        emit_timing(
            "provider_call", started, provider=provider.name, model=target.model,
            outcome="ok", message_count=message_count, input_chars=input_chars,
            tool_count=tool_count, max_tokens=max_tokens,
        )
        return response

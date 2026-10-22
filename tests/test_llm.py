import unittest

from iris.brain.llm import (
    GenerationOptions,
    LLMMessage,
    LLMRegistry,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ModelTarget,
    ProviderNotFoundError,
)


class FakeProvider:
    def __init__(self, name: str = "fake", healthy: bool = True) -> None:
        self._name = name
        self._healthy = healthy
        self.last_request: LLMRequest | None = None

    @property
    def name(self) -> str:
        return self._name

    def healthcheck(self) -> bool:
        return self._healthy

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request

        user_text = next(
            (
                message.content
                for message in reversed(request.messages)
                if message.role == MessageRole.USER
            ),
            "",
        )

        return LLMResponse(
            text=f"fake response to: {user_text}",
            provider=self.name,
            model=request.model,
            input_tokens=10,
            output_tokens=5,
        )


class LLMRegistryTests(unittest.TestCase):
    def test_provider_can_be_registered(self) -> None:
        registry = LLMRegistry()
        registry.register(FakeProvider())

        self.assertEqual(registry.names(), ("fake",))

    def test_duplicate_provider_is_rejected(self) -> None:
        registry = LLMRegistry()
        registry.register(FakeProvider())

        with self.assertRaises(ValueError):
            registry.register(FakeProvider())

    def test_missing_provider_fails_loudly(self) -> None:
        registry = LLMRegistry()

        with self.assertRaises(ProviderNotFoundError):
            registry.get("missing")

    def test_healthcheck_reports_provider_state(self) -> None:
        registry = LLMRegistry()
        registry.register(FakeProvider("healthy", True))
        registry.register(FakeProvider("offline", False))

        self.assertEqual(
            registry.healthy(),
            {
                "healthy": True,
                "offline": False,
            },
        )

    def test_generate_routes_to_requested_provider_and_model(self) -> None:
        registry = LLMRegistry()
        provider = FakeProvider()
        registry.register(provider)

        response = registry.generate(
            ModelTarget(
                provider="fake",
                model="iris-test-model",
            ),
            [
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content="You are I.R.I.S.",
                ),
                LLMMessage(
                    role=MessageRole.USER,
                    content="hello",
                ),
            ],
        )

        self.assertEqual(response.text, "fake response to: hello")
        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "iris-test-model")

        self.assertIsNotNone(provider.last_request)
        assert provider.last_request is not None
        self.assertEqual(
            provider.last_request.model,
            "iris-test-model",
        )

    def test_generation_options_are_forwarded(self) -> None:
        registry = LLMRegistry()
        provider = FakeProvider()
        registry.register(provider)

        options = GenerationOptions(
            temperature=0.2,
            max_tokens=123,
        )

        registry.generate(
            ModelTarget("fake", "test"),
            [
                LLMMessage(
                    MessageRole.USER,
                    "test",
                )
            ],
            options,
        )

        self.assertIsNotNone(provider.last_request)
        assert provider.last_request is not None

        self.assertEqual(
            provider.last_request.options,
            options,
        )


if __name__ == "__main__":
    unittest.main()

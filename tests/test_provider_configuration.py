import unittest
from unittest.mock import patch

from iris.terminal import load_config

from iris.brain.providers.configuration import (
    configured_provider_names, provider_environment, validate_model_id,
    validate_provider_name, validate_provider_url,
)


class ProviderConfigurationTests(unittest.TestCase):
    def test_handoff_groq_choice_overrides_all_local_roles_without_network(self):
        env = {"IRIS_PROVIDER_URL": "http://127.0.0.1:11434", "IRIS_MODEL": "llama3.2:latest",
               "IRIS_PROVIDER_GROQ_URL": "https://api.groq.com/openai/v1",
               "IRIS_PROVIDER_GROQ_API_KEY": "synthetic-only", "IRIS_TIMEOUT_SECONDS": "15"}
        for role in ("FAST", "DEEP", "COUNCIL_STRATEGIST", "COUNCIL_SKEPTIC", "COUNCIL_CHAIRMAN"):
            env[f"IRIS_{role}_PROVIDER"] = "groq"
            env[f"IRIS_{role}_MODEL"] = "openai/gpt-oss-20b"
        with patch("iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("offline setup")):
            config = load_config(env)
        targets = (config.fast_target, config.deep_target,
                   *(seat.target for seat in config.council_plan.seats), config.council_plan.chairman)
        self.assertTrue(all((target.provider, target.model) == ("groq", "openai/gpt-oss-20b") for target in targets))
        self.assertEqual(config.provider.base_url, "https://api.groq.com/openai")
        self.assertNotIn("synthetic-only", repr(config))

    def test_openai_compatible_urls_are_normalized_without_secrets(self):
        self.assertEqual(validate_provider_url("https://api.example/v1/", "URL"), "https://api.example")
        for value in ("file:///tmp/x", "https://user:pass@example", "https://example/?token=x", "ftp://example"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_provider_url(value, "IRIS_PROVIDER_X_URL")

    def test_model_and_provider_identifiers_are_bounded(self):
        self.assertEqual(validate_model_id("  vendor/model:free ", "MODEL"), "vendor/model:free")
        for value in ("", "bad model", "x\ny", "x" * 257):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_model_id(value, "MODEL")
        self.assertEqual(validate_provider_name("Groq"), "groq")
        with self.assertRaises(ValueError):
            validate_provider_name("../secret")

    def test_provider_environment_names_and_discovery_never_include_key_values(self):
        self.assertEqual(provider_environment("openrouter"), {
            "url": "IRIS_PROVIDER_OPENROUTER_URL",
            "api_key": "IRIS_PROVIDER_OPENROUTER_API_KEY",
            "timeout": "IRIS_PROVIDER_OPENROUTER_TIMEOUT_SECONDS",
        })
        env = {"IRIS_PROVIDER_GROQ_URL": "https://api.groq.com/openai/v1",
               "IRIS_PROVIDER_GROQ_API_KEY": "secret", "IRIS_PROVIDER_NO_URL_API_KEY": "ignored"}
        self.assertEqual(configured_provider_names(env), ("groq",))


    def legacy(self, **extra):
        return {"IRIS_PROVIDER_URL": "http://localhost:8000/v1/",
                "IRIS_MODEL": "legacy-model", **extra}

    def test_keys_hidden_in_nested_configuration_repr(self):
        config = load_config(self.legacy(IRIS_API_KEY="synthetic-private-key",
                             IRIS_PROVIDER_OTHER_URL="https://other.invalid/v1",
                             IRIS_PROVIDER_OTHER_API_KEY="synthetic-other-key"))
        self.assertEqual(config.provider.api_key, "synthetic-private-key")
        for value in (config, config.provider, config.providers):
            self.assertNotIn("synthetic-private-key", repr(value))
            self.assertNotIn("synthetic-other-key", repr(value))

    def test_unknown_and_malformed_provider_values_are_not_echoed(self):
        for value in ("synthetic_private_key", "bad/name", "x" * 65):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as raised:
                    load_config(self.legacy(IRIS_FAST_PROVIDER=value))
                self.assertIn("IRIS_FAST_PROVIDER", str(raised.exception))
                self.assertNotIn(value, str(raised.exception))

    def test_bad_endpoints_rejected_by_loader_without_echo(self):
        for url in ("https://bad host/v1", "https://exa\nmple.com/v1",
                    "https://example.com/v1\t", "https://example.com/v1/chat/completions/"):
            for variable in ("IRIS_PROVIDER_URL", "IRIS_PROVIDER_OTHER_URL"):
                with self.subTest(url=url, variable=variable):
                    with self.assertRaises(ValueError) as raised:
                        load_config(self.legacy(**{variable: url}))
                    self.assertIn(variable, str(raised.exception))
                    self.assertNotIn(url, str(raised.exception))

    def test_supported_endpoint_forms_remain_compatible(self):
        for url, expected in (("http://localhost:8000/v1/", "http://localhost:8000"),
                              ("http://[::1]:8000/v1", "http://[::1]:8000"),
                              ("https://example.com/custom/openai/v1", "https://example.com/custom/openai")):
            self.assertEqual(load_config(self.legacy(IRIS_PROVIDER_URL=url)).provider.base_url, expected)

    def test_provider_aliases_use_same_registration_and_lookup(self):
        config = load_config(self.legacy(IRIS_PROVIDER_MY_PROVIDER_URL="https://example.com/v1",
                                        IRIS_FAST_PROVIDER="My-Provider"))
        self.assertEqual(config.fast_target.provider, "my_provider")
        self.assertEqual(config.provider.name, "my_provider")
        self.assertEqual(validate_provider_name("My-Provider"), "my_provider")
        self.assertEqual(configured_provider_names({"IRIS_PROVIDER_MY_PROVIDER_URL": "https://example.com"}),
                         ("my_provider",))
        with self.assertRaises(ValueError):
            load_config(self.legacy(**{"IRIS_PROVIDER_" + "X" * 65 + "_URL": "https://example.com"}))

    def test_role_overrides_preserve_legacy_field_fallback_offline(self):
        for role in ("FAST", "DEEP", "COUNCIL_STRATEGIST", "COUNCIL_SKEPTIC", "COUNCIL_CHAIRMAN"):
            for overrides, expected in (({}, ("terminal", "legacy-model")),
                    ({f"IRIS_{role}_PROVIDER": "other"}, ("other", "legacy-model")),
                    ({f"IRIS_{role}_MODEL": "role-model"}, ("terminal", "role-model")),
                    ({f"IRIS_{role}_PROVIDER": "other", f"IRIS_{role}_MODEL": "role-model"},
                     ("other", "role-model"))):
                with self.subTest(role=role, expected=expected), patch(
                        "iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("offline")):
                    config = load_config(self.legacy(IRIS_PROVIDER_OTHER_URL="https://other.invalid/v1", **overrides))
                    targets = (config.fast_target, config.deep_target,
                               *(seat.target for seat in config.council_plan.seats), config.council_plan.chairman)
                    target = targets[("FAST", "DEEP", "COUNCIL_STRATEGIST", "COUNCIL_SKEPTIC", "COUNCIL_CHAIRMAN").index(role)]
                    self.assertEqual((target.provider, target.model), expected)


if __name__ == "__main__":
    unittest.main()

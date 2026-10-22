"""Only synthetic configuration and disposable directories; no real credentials."""

import os as _platform_os
import unittest as _platform_tests
if _platform_os.name == "nt":
    raise _platform_tests.SkipTest("Legacy POSIX launcher/permissions/deadline tests; Windows desktop has dedicated tests")

import io
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.local_config import (
    LocalConfigError, activate_saved_configuration, effective_environment,
    parse_config, prepare_private_storage, read_saved, save_updates,
)


class LocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "iris" / "config.env"
        self.patch_path = patch("iris.local_config.config_path", return_value=self.path)
        self.patch_path.start()
        self.addCleanup(self.patch_path.stop)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def settings(self):
        return {"IRIS_PROVIDER_URL": "https://api.groq.com/openai/v1",
                "IRIS_MODEL": "openai/gpt-oss-20b"}

    def test_missing_configuration_is_empty_and_does_not_create_files(self):
        self.assertEqual(read_saved(), {})
        self.assertEqual(effective_environment(), {})
        self.assertFalse(self.path.parent.exists())

    def test_permissions_roundtrip_and_blank_update_preserves_saved_values(self):
        save_updates({**self.settings(), "IRIS_API_KEY": "synthetic-only", "IRIS_FISH_MODEL": "fixture"})
        save_updates({"IRIS_API_KEY": "", "IRIS_MODEL": "new-model"})
        self.assertEqual(read_saved()["IRIS_API_KEY"], "synthetic-only")
        self.assertEqual(read_saved()["IRIS_FISH_MODEL"], "fixture")
        self.assertEqual(read_saved()["IRIS_MODEL"], "new-model")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_environment_overrides_saved_including_explicit_empty_key(self):
        save_updates({**self.settings(), "IRIS_API_KEY": "synthetic-only"})
        os.environ.update(IRIS_MODEL="override", IRIS_API_KEY="")
        from iris.terminal import load_config
        config = load_config()
        self.assertEqual(config.model, "override")
        self.assertIsNone(config.provider.api_key)
        activate_saved_configuration()
        self.assertEqual(os.environ["IRIS_API_KEY"], "")
        self.assertEqual(os.environ["IRIS_MODEL"], "override")

    def test_explicit_embedding_mapping_is_isolated_from_personal_file(self):
        save_updates(self.settings())
        self.assertEqual(effective_environment({}), {})

    def test_parser_treats_shell_syntax_as_literal_data(self):
        parsed = parse_config("# comment\nIRIS_MODEL='$(touch never-created)'\nIRIS_VOSK_MODEL=~/model/$USER\n")
        self.assertEqual(parsed["IRIS_MODEL"], "$(touch never-created)")
        self.assertEqual(parsed["IRIS_VOSK_MODEL"], "~/model/$USER")
        self.assertEqual(parse_config('IRIS_MODEL="a b=#c"')["IRIS_MODEL"], "a b=#c")
        for invalid in ("export IRIS_MODEL=x", "echo unsafe", "PATH=x", "IRIS_MODEL=x\nIRIS_MODEL=y",
                        'IRIS_MODEL="broken', 'IRIS_MODEL="a\\nb"'):
            with self.subTest(kind=invalid.split("=")[0]), self.assertRaises(LocalConfigError) as error:
                parse_config(invalid)
            self.assertEqual(str(error.exception), "Saved IRIS configuration is invalid.")

    def test_symlinks_and_broad_permissions_are_rejected(self):
        save_updates(self.settings())
        self.path.chmod(0o644)
        with self.assertRaises(LocalConfigError):
            read_saved()
        self.path.chmod(0o600)
        self.path.parent.chmod(0o755)
        with self.assertRaises(LocalConfigError):
            read_saved()
        self.path.parent.chmod(0o700)
        other = self.path.with_name("original")
        self.path.rename(other)
        self.path.symlink_to(other)
        with self.assertRaises(LocalConfigError):
            save_updates(self.settings())
        self.assertTrue(other.is_file())

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary(self):
        save_updates(self.settings())
        original = self.path.read_bytes()
        with patch("iris.local_config.os.replace", side_effect=OSError("private details")):
            with self.assertRaises(LocalConfigError) as error:
                save_updates({"IRIS_MODEL": "changed"})
        self.assertNotIn("private details", str(error.exception))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_setup_permission_repair_preserves_bytes_and_rejects_aliases(self):
        save_updates({**self.settings(), "IRIS_API_KEY": "synthetic-only"})
        before = self.path.read_bytes()
        self.path.chmod(0o644)
        self.path.parent.chmod(0o755)
        prepare_private_storage()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        alias = self.path.with_name("alias")
        os.link(self.path, alias)
        with self.assertRaises(LocalConfigError):
            prepare_private_storage()
        self.assertEqual(self.path.read_bytes(), before)

    def test_setup_reports_safe_validation_stage_without_echoing_input(self):
        from iris.setup import main
        with patch("builtins.input", side_effect=["groq", "not-a-url-synthetic-private"]), \
             patch("iris.setup.getpass.getpass") as hidden, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main([]), 1)
        hidden.assert_not_called()
        self.assertIn("stage=provider_url reason=invalid_input exception=ValueError", output.getvalue())
        self.assertNotIn("synthetic-private", output.getvalue())
        self.assertFalse(self.path.exists())

    def test_interactive_setup_hidden_keys_blank_preservation_and_no_echo(self):
        from iris.setup import configure
        save_updates({"IRIS_FAST_PROVIDER": "groq", "IRIS_FAST_MODEL": "openai/gpt-oss-20b",
                      "IRIS_DEEP_MODEL": "openai/gpt-oss-120b",
                      "IRIS_PROVIDER_GROQ_API_KEY": "synthetic-provider",
                      "IRIS_FISH_API_KEY": "synthetic-fish", "IRIS_OBSIDIAN_VAULT": "fixture-vault"})
        with patch("builtins.input", return_value=""), patch("iris.setup.getpass.getpass", return_value="") as hidden, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            configure()
        self.assertEqual(hidden.call_count, 2)
        saved = read_saved()
        self.assertEqual(saved["IRIS_PROVIDER_GROQ_API_KEY"], "synthetic-provider")
        self.assertEqual(saved["IRIS_FISH_API_KEY"], "synthetic-fish")
        self.assertEqual(saved["IRIS_DEEP_MODEL"], "openai/gpt-oss-120b")
        self.assertEqual(saved["IRIS_OBSIDIAN_VAULT"], "fixture-vault")
        self.assertEqual(saved["IRIS_PROVIDER_OLLAMA_URL"], "http://127.0.0.1:11434")
        self.assertNotIn("synthetic-", output.getvalue())
        self.assertNotIn("synthetic-", str(hidden.call_args_list))

    def test_setup_cancellation_does_not_write(self):
        from iris.setup import main
        save_updates(self.settings())
        before = self.path.read_bytes()
        with patch("builtins.input", side_effect=KeyboardInterrupt), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main([]), 130)
        self.assertEqual(self.path.read_bytes(), before)

    def test_setup_does_not_echo_accidental_cli_credentials(self):
        from iris.setup import main
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["--key", "synthetic-private-value"]), 2)
        self.assertNotIn("synthetic-private-value", output.getvalue())
        self.assertFalse(self.path.exists())

    def test_setup_refuses_echoed_password_fallback(self):
        import getpass
        from iris.setup import main
        with patch("builtins.input", return_value=""), \
             patch("iris.setup.getpass.getpass", side_effect=getpass.GetPassWarning("synthetic-private-value")), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main([]), 1)
        self.assertNotIn("synthetic-private-value", output.getvalue())
        self.assertFalse(self.path.exists())

    def test_preflight_and_readiness_use_saved_provider_without_requiring_fish(self):
        save_updates(self.settings())
        from iris.preflight import backend_preflight_checks
        from iris.readiness import main
        from iris.brain.llm import LLMResponse
        with patch("iris.preflight._vosk_model_check", return_value=Mock()), \
             patch("iris.preflight.importlib.import_module", side_effect=ImportError):
            checks = backend_preflight_checks()
        self.assertEqual(checks[0].status, "PASS")
        from iris.terminal import load_config
        self.assertEqual(load_config().model, "openai/gpt-oss-20b")
        with patch("iris.readiness.OpenAICompatibleProvider.generate", return_value=LLMResponse("ok", "fixture", "fixture")), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["--live"]), 0)

    def test_terminal_main_starts_from_saved_text_only_configuration(self):
        settings = self.settings()
        for name in ("MEMORY", "TASKS", "GOALS"):
            settings[f"IRIS_{name}_PATH"] = str(Path(self.temp.name) / (name.lower() + ".db"))
        save_updates(settings)
        from iris.main import main
        with patch("builtins.input", return_value="/exit"), patch("iris.main.boot"), \
             patch("iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("no network")), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(), 0)
        self.assertNotIn("IRIS_FISH_API_KEY", os.environ)

    def test_new_setup_defaults_to_groq_and_retains_ollama_without_calling_either(self):
        from iris.setup import configure
        with patch("builtins.input", return_value=""), patch("iris.setup.getpass.getpass", return_value=""), \
             patch("iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("no network")), \
             patch("sys.stdout", new_callable=io.StringIO):
            configure()
        saved = read_saved()
        self.assertEqual(saved["IRIS_FAST_PROVIDER"], "groq")
        self.assertEqual(saved["IRIS_FAST_MODEL"], "openai/gpt-oss-20b")
        self.assertIn("IRIS_PROVIDER_OLLAMA_URL", saved)
        self.assertNotIn("IRIS_FISH_API_KEY", saved)

    def test_voice_builder_activates_saved_voice_defaults(self):
        save_updates({**self.settings(), "IRIS_VOSK_MODEL": "fixture-model", "IRIS_FISH_API_KEY": "synthetic-only"})
        from iris.voice_once import build_voice_flow
        with patch("iris.voice_once.create_brain"), patch("iris.voice_once._one_shot_transcriber") as recognizer, \
             patch("iris.voice_once.WindowsInteropAudioSink"), patch("iris.voice_once.FishAudioSynthesizer"):
            runner, sink = build_voice_flow(memory_store=Mock())
        recognizer.assert_called_once()
        self.assertEqual(os.environ["IRIS_VOSK_MODEL"], "fixture-model")
        self.assertEqual(os.environ["IRIS_FISH_API_KEY"], "synthetic-only")

    def test_invalid_saved_file_is_sanitized_by_preflight(self):
        save_updates(self.settings())
        self.path.write_text("not valid private-data", encoding="utf-8")
        from iris.preflight import main
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main([]), 1)
        self.assertNotIn("private-data", output.getvalue())
        self.assertNotIn(str(self.path), output.getvalue())

    def test_launcher_works_from_another_directory_without_provider_calls(self):
        launcher = Path(__file__).resolve().parents[1] / "iris-run"
        link = Path(self.temp.name) / "run-iris"
        link.symlink_to(launcher)
        result = subprocess.run([str(link), "readiness"], cwd=self.temp.name,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Readiness not run", result.stdout)


if __name__ == "__main__":
    unittest.main()

import io
from pathlib import Path
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import patch

from iris.preflight import (backend_preflight_checks, diagnostics_values, main,
                            preflight_checks, render_diagnostics)
from iris.terminal import chat, create_brain, load_config
from iris.memory.store import MemoryStore
from iris.tasks.store import TaskStore
from iris.main import main as run_iris


class PreflightTests(unittest.TestCase):
    def setUp(self):
        saved = patch("iris.local_config.read_saved", return_value={})
        saved.start()
        self.addCleanup(saved.stop)

    def test_default_preflight_runs_local_chains_without_provider_requests(self):
        with patch("iris.brain.providers.openai_compatible.urlopen") as request:
            checks = preflight_checks(environ={})
        request.assert_not_called()
        values = {check.name: check for check in checks}
        for name in ("memory_chain", "task_chain", "workspace_chain", "calendar_chain",
                     "obsidian_chain", "briefing_chain", "tool_execution", "registered_tools_available"):
            self.assertEqual(values[name].status, "PASS", name)
        self.assertEqual(values["provider_reachable"].value, "not_checked")

    def test_live_mode_only_checks_provider_reachability(self):
        env = {"IRIS_PROVIDER_URL": "https://provider.example", "IRIS_MODEL": "local-test"}
        with patch("iris.brain.providers.openai_compatible.urlopen") as request, \
                patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.generate") as generate:
            from tests.test_openai_compatible import FakeHTTPResponse
            request.return_value = FakeHTTPResponse({"data": []})
            checks = preflight_checks(live=True, environ=env)
        self.assertEqual([call.args[0].get_method() for call in request.call_args_list], ["GET"])
        self.assertTrue(request.call_args.args[0].full_url.endswith("/v1/models"))
        generate.assert_not_called()
        values = {check.name: check for check in checks}
        self.assertEqual(values["provider_reachable"].status, "PASS")

    def test_preflight_recognizes_multi_provider_configuration_without_live_calls(self):
        env = {"IRIS_PROVIDER_GROQ_URL": "https://api.groq.com/openai/v1"}
        for tier in ("FAST", "DEEP", "COUNCIL_STRATEGIST", "COUNCIL_SKEPTIC", "COUNCIL_CHAIRMAN"):
            env[f"IRIS_{tier}_PROVIDER"] = "groq"
            env[f"IRIS_{tier}_MODEL"] = "openai/gpt-oss-20b"
        with patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.healthcheck",
                   side_effect=AssertionError("default preflight must not contact providers")) as healthcheck:
            checks = preflight_checks(environ=env)
        healthcheck.assert_not_called()
        values = {check.name: check for check in checks}
        self.assertEqual(values["provider_configured"].status, "PASS")
        self.assertEqual(values["model_configured"].status, "PASS")
        self.assertEqual(values["council_configured"].status, "PASS")
        self.assertEqual(values["provider_reachable"].value, "not_checked")

    def test_failed_local_chain_returns_nonzero_and_help_skips_checks(self):
        with patch("iris.preflight.backend_preflight_checks", return_value=(
                type("Check", (), {"status": "FAIL", "name": "backend", "value": "false"})(),)), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([]), 1)
        self.assertIn("FAIL backend=false", output.getvalue())
        with patch("iris.preflight.backend_preflight_checks", side_effect=AssertionError("must not run")), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_backend_preflight_valid_configuration_does_not_touch_microphone(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "vosk-model"
            model_path.mkdir()
            class FakeVosk:
                class Model:
                    def __init__(self, _path):
                        pass
            class FakeSoundDevice:
                class PortAudioError(Exception):
                    pass
                def __getattr__(self, name):
                    raise AssertionError(f"preflight touched audio operation: {name}")
            fake_modules = {"vosk": FakeVosk(), "sounddevice": FakeSoundDevice()}
            def fake_import(name):
                if name in fake_modules:
                    return fake_modules[name]
                raise ImportError(name)
            env = {
                "IRIS_PROVIDER_URL": "http://provider.invalid",
                "IRIS_MODEL": "offline-model",
                "IRIS_VOSK_MODEL": str(model_path),
                "IRIS_FISH_API_KEY": "secret-that-must-not-render",
            }
            with patch("iris.preflight.importlib.import_module", side_effect=fake_import):
                checks = backend_preflight_checks(environ=env)
        values = {item.name: item for item in checks}
        self.assertEqual(values["vosk_model"].status, "PASS")
        self.assertEqual(values["sounddevice_portaudio"].status, "PASS")
        self.assertEqual(values["fish_configuration"].status, "PASS")
        self.assertEqual(values["provider_configured"].status, "PASS")

    def test_backend_preflight_reports_missing_model_provider_and_fish_without_secrets(self):
        env = {
            "IRIS_VOSK_MODEL": "/private/does-not-exist",
            "IRIS_API_KEY": "PRIVATE_PROVIDER_KEY",
            "IRIS_FISH_API_KEY": "PRIVATE_FISH_KEY",
        }
        with patch("iris.preflight.importlib.import_module", side_effect=ImportError("private path")):
            checks = backend_preflight_checks(environ=env)
        values = {item.name: item for item in checks}
        self.assertEqual(values["provider_configured"].status, "FAIL")
        self.assertEqual(values["model_configured"].status, "FAIL")
        self.assertEqual(values["vosk_model"].value, "dependency_missing")
        self.assertEqual(values["sounddevice_portaudio"].value, "dependency_missing")
        self.assertEqual(values["fish_configuration"].value, "true")
        rendered = "\n".join(f"{item.status} {item.name}={item.value}" for item in checks)
        self.assertNotIn("PRIVATE", rendered)
        self.assertNotIn("/private", rendered)

    def test_backend_preflight_selected_whisper_checks_dependency_without_loading_model(self):
        class FakeSoundDevice:
            class PortAudioError(Exception):
                pass
        def fake_import(name):
            if name == "sounddevice":
                return FakeSoundDevice()
            if name == "faster_whisper":
                return object()
            raise ImportError(name)
        env = {
            "IRIS_PROVIDER_URL": "http://provider.invalid",
            "IRIS_MODEL": "offline-model",
            "IRIS_ONESHOT_RECOGNIZER": "whisper",
            "IRIS_WHISPER_MODEL": "tiny.en",
            "IRIS_FISH_API_KEY": "configured",
        }
        with patch("iris.preflight.importlib.import_module", side_effect=fake_import):
            checks = backend_preflight_checks(environ=env)
        values = {item.name: item for item in checks}
        self.assertEqual(values["vosk_model"].value, "not_selected")
        self.assertEqual(values["whisper_configuration"].status, "PASS")
        self.assertEqual(values["whisper_dependency"].status, "PASS")

    def test_backend_preflight_missing_selected_whisper_dependency_is_clear(self):
        env = {
            "IRIS_PROVIDER_URL": "http://provider.invalid",
            "IRIS_MODEL": "offline-model",
            "IRIS_ONESHOT_RECOGNIZER": "whisper",
            "IRIS_WHISPER_MODEL": "tiny.en",
            "IRIS_FISH_API_KEY": "configured",
        }
        with patch("iris.preflight.importlib.import_module", side_effect=ImportError("secret/path")):
            checks = backend_preflight_checks(environ=env)
        values = {item.name: item for item in checks}
        self.assertEqual(values["whisper_dependency"].value, "dependency_missing")
        self.assertEqual(values["whisper_configuration"].status, "PASS")

    def test_cli_backend_preflight_does_not_run_legacy_chains_or_live_provider(self):
        with patch("iris.preflight.run_local_chains", side_effect=AssertionError("must not run")), \
                patch("iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("must not call")), \
                patch("iris.preflight.backend_preflight_checks", return_value=()):
            self.assertEqual(main([]), 0)

    def test_terminal_diagnostics_do_not_expose_credentials_paths_or_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory_path, task_path = root / "private-memory.sqlite3", root / "private-tasks.sqlite3"
            calendar_root, vault = root / "calendar", root / "vault"
            calendar_root.mkdir()
            vault.mkdir()
            canary = "PRIVATE_OBSIDIAN_NOTE_CONTENT_938201"
            (vault / "note.md").write_text(canary, encoding="utf-8")
            (calendar_root / "events.ics").write_text(
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//IRIS diagnostic//EN\r\n"
                "END:VCALENDAR\r\n", encoding="utf-8", newline="")
            env = {
                "IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                "IRIS_API_KEY": "PRIVATE_API_KEY_492817", "IRIS_MEMORY_PATH": str(memory_path),
                "IRIS_TASKS_PATH": str(task_path), "IRIS_GOALS_PATH": str(root / "goals.sqlite3"), "IRIS_CALENDAR_ROOT": str(calendar_root),
                "IRIS_CALENDAR_PATH": "events.ics", "IRIS_OBSIDIAN_ROOT": str(vault),
                "IRIS_REMINDERS_STATUS_PATH": str(root / "reminders.lock"),
            }
            with patch.dict("os.environ", env, clear=True):
                memory = MemoryStore(memory_path)
                tasks = TaskStore(task_path)
                tasks.create("diagnostic task")
                brain = create_brain(load_config(env))
                with patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.healthcheck", return_value=True), \
                        patch("builtins.input", side_effect=["/diagnostics", "/diagnostics extra", "/exit"]), \
                        patch("sys.stdout", new_callable=io.StringIO) as output:
                    chat(brain, memory_store=memory, task_store=tasks)
                memory.close()
                tasks.close()
            rendered = output.getvalue()
            for secret in ("PRIVATE_API_KEY_492817", canary, str(root), "private-memory.sqlite3", "events.ics"):
                self.assertNotIn(secret, rendered)
            self.assertIn("provider_configured: true", rendered)
            self.assertIn("provider_reachable: true", rendered)
            self.assertIn("calendar_readable: true", rendered)
            self.assertIn("obsidian_readable: true", rendered)
            self.assertIn("registered_tools_available: true", rendered)
            self.assertIn("Use /diagnostics with no arguments.", rendered)

    def test_diagnostics_values_are_allowlisted_safe_statuses(self):
        values = diagnostics_values(None)
        rendered = render_diagnostics(values)
        self.assertIn("reminder_worker_status:", rendered)
        self.assertIn("provider_reachable: not_configured", rendered)
        self.assertNotIn("/home/", rendered)
        self.assertNotIn("API_KEY", rendered)

    def test_local_diagnostics_can_skip_provider_reachability(self):
        env = {"IRIS_PROVIDER_URL": "http://provider.invalid", "IRIS_MODEL": "local-model"}
        with patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.healthcheck",
                   side_effect=AssertionError("startup must not contact provider")) as healthcheck:
            values = diagnostics_values(load_config(env), check_provider_reachability=False)
        healthcheck.assert_not_called()
        self.assertTrue(values["provider_configured"])
        self.assertEqual(values["provider_reachable"], "not_checked")

    def test_normal_startup_shows_real_local_statuses_without_provider_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                "IRIS_PROVIDER_URL": "http://provider.invalid", "IRIS_MODEL": "local-model",
                "IRIS_MEMORY_PATH": str(root / "memory.sqlite3"),
                "IRIS_TASKS_PATH": str(root / "tasks.sqlite3"),
                "IRIS_GOALS_PATH": str(root / "goals.sqlite3"),
                "IRIS_API_KEY": "PRIVATE_BOOT_KEY",
            }
            with patch.dict("os.environ", env, clear=True), \
                    patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.healthcheck",
                          side_effect=AssertionError("startup must not contact provider")) as healthcheck, \
                    patch("iris.boot.BOOT_LINE_DELAY", 0), \
                    patch("builtins.input", side_effect=["/exit"]), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(run_iris(), 0)
            healthcheck.assert_not_called()
            rendered = output.getvalue()
            for status in (
                "PROVIDER", "CONFIGURED (REACHABILITY NOT CHECKED)", "MODEL", "CONFIGURED",
                "MEMORY", "AVAILABLE", "TASKS", "CALENDAR", "NOT CONFIGURED",
                "OBSIDIAN", "TOOLS", "LLM COUNCIL", "REMINDERS",
            ):
                self.assertIn(status, rendered)
            self.assertNotIn("PRIVATE_BOOT_KEY", rendered)
            self.assertNotIn(str(root), rendered)


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import select
from tests.pipe_helpers import read_line
import socket
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from iris.tasks.store import TaskStore
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from iris.ui import create_server, render_dashboard, main, sanitize_snapshot, collect_snapshot, serve_until_eof
from iris.ui_state import clear_conversation, update_conversation, HudConversationPublisher, conversation_snapshot
from iris.voice import VoiceSession


class HUDTests(unittest.TestCase):
    def setUp(self):
        clear_conversation()
        self.snapshot = {
            "state": "listening<script>",
            "statuses": {"memory_available": True},
            "notifications": [{"severity": "info", "kind": "reminder", "created_at": "now", "dismissed": False}],
            "tasks": [{"title": "<script>alert(1)</script>", "due_at": "2026-09-17T12:00:00Z"}],
            "briefing": {"date": "2026-09-17", "timezone": "America/Toronto", "facts": {"calendar_configured": False, "events": [], "permitted_memories": [], "active_goals": []}, "deadlines": [], "goal_risks": [], "suggestions": ["<unsafe>"]},
            "automation": [], "council": False,
        }

    def tearDown(self):
        clear_conversation()

    def test_conversation_events_render_canonical_session_only_captions(self):
        update_conversation(state="speaking", user_speech="What is two plus two?",
                            response="I’m IRIS. The answer is 4.")
        snapshot = collect_snapshot()
        self.assertEqual(snapshot["conversation"]["state"], "speaking")
        self.assertEqual(snapshot["conversation"]["user_speech"], "What is two plus two?")
        self.assertIn("I’m IRIS", snapshot["conversation"]["response"])
        rendered = render_dashboard(snapshot)
        self.assertIn("What is two plus two?", rendered)
        self.assertIn("I’m IRIS. The answer is 4.", rendered)
        clear_conversation()
        self.assertEqual(collect_snapshot()["conversation"]["response"], "")

    def test_voice_process_event_reaches_hud_and_close_clears_remote_session(self):
        server = create_server("127.0.0.1", 0, conversation_token="t" * 32)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/api/conversation"
        seen = []

        class Recorder:
            def start_listening(self):
                return None

            def stop_listening(self):
                return "What is two plus two?"

        class Synth:
            def speak(self, _text):
                return None

        class ObservingPublisher(HudConversationPublisher):
            def publish(self, snapshot):
                seen.append(dict(snapshot))
                super().publish(snapshot)

        publisher = ObservingPublisher(endpoint, token="t" * 32)
        session = VoiceSession(
            recognizer=Recorder(), synthesizer=Synth(),
            responder=lambda _text: "IRIS says 4", conversation_sink=publisher,
        )
        try:
            session.press()
            turn = session.release()
            self.assertEqual(turn.response, "IRIS says 4")
            states = [item["state"] for item in seen]
            self.assertEqual(states[0], "listening")
            self.assertIn("thinking", states)
            self.assertIn("speaking", states)
            self.assertEqual(states[-1], "idle")
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/status") as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["conversation"]["user_speech"], "What is two plus two?")
            self.assertEqual(payload["conversation"]["response"], "IRIS says 4")
            session.close()
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/status") as response:
                cleared = json.loads(response.read())
            self.assertEqual(cleared["conversation"],
                             {"state": "idle", "user_speech": "", "response": ""})
        finally:
            server.shutdown()
            server.server_close()

    def test_voice_publisher_rejects_non_loopback_or_credentialed_endpoints(self):
        with self.assertRaises(ValueError):
            HudConversationPublisher("http://example.invalid/api/conversation")
        with self.assertRaises(ValueError):
            HudConversationPublisher("http://user:secret@127.0.0.1:8765/api/conversation")

    def test_render_escapes_user_data_and_contains_hud_sections(self):
        self.snapshot["conversation"] = {"state": "idle", "response": "<script>alert(1)</script>"}
        rendered = render_dashboard(self.snapshot)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>alert", rendered)
        for label in ("State core", "Subsystems", "Notifications", "Open tasks", "Daily briefing"):
            self.assertIn(label, rendered)

    def test_api_returns_snapshot_and_server_is_loopback(self):
        self.snapshot["briefing"]["suggestions"] = ["password=synthetic-http-secret", "/home/private/http-file"]
        server = create_server("127.0.0.1", 0, snapshot_factory=lambda: self.snapshot)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/status") as response:
                payload = json.loads(response.read())
            for sensitive in ("synthetic-http-secret", "/home/private/http-file"):
                self.assertNotIn(sensitive, json.dumps(payload))
            self.assertEqual(payload["state"], self.snapshot["state"])
            self.assertEqual(payload["tasks"][0]["title"], "[private path omitted]")
            with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
                self.assertIn(b"LOCAL HUD", response.read())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_main_closes_server_after_keyboard_interrupt(self):
        server = Mock(server_port=8765)

        with patch("iris.ui.create_server", return_value=server) as create, patch("builtins.print"), patch("iris.ui.serve_until_eof", side_effect=KeyboardInterrupt) as serve:
            main([])
        create.assert_called_once_with("127.0.0.1", 8765, conversation_token=os.environ.get("IRIS_HUD_TOKEN", ""))
        serve.assert_called_once_with(server)
        server.server_close.assert_called_once_with()

    def test_sensitive_data_redacted_before_json_and_html(self):
        self.snapshot["briefing"]["suggestions"] = ["password=synthetic-secret", "/home/private/report"]
        self.snapshot["tasks"] = [{"title": "opaque-configured-key", "due_at": None}]
        self.snapshot["notifications"][0]["payload"] = {"nested": [r"C:\private\file", "../private/file"],
                                                          "api_key": "synthetic-hidden-value", "opaque-configured-key": "discard"}
        with patch.dict(os.environ, {"IRIS_API_KEY": "opaque-configured-key"}):
            safe = sanitize_snapshot(self.snapshot)
            for output in (json.dumps(safe), render_dashboard(self.snapshot)):
                for secret in ("synthetic-secret", "/home/private", "opaque-configured-key", "synthetic-hidden-value", "../private"):
                    self.assertNotIn(secret, output)
        self.assertEqual(self.snapshot["tasks"][0]["title"], "opaque-configured-key")
        self.assertEqual(sanitize_snapshot({"model": "vendor/model:free", "timezone": "America/Toronto"}),
                         {"model": "vendor/model:free", "timezone": "America/Toronto"})

    def test_diagnostics_receive_config_without_live_checks(self):
        env = {"IRIS_PROVIDER_URL": "https://example.invalid/v1", "IRIS_MODEL": "vendor/model",
               "IRIS_API_KEY": "opaque-test-key"}
        with patch.dict(os.environ, env, clear=True), patch("iris.ui.diagnostics_values", return_value={}) as diagnostics, patch(
                "iris.ui.TaskStore", side_effect=ValueError), patch("iris.ui.build_briefing", return_value={}):
            snapshot = collect_snapshot()
        config = diagnostics.call_args.args[0]
        self.assertEqual(config.model, "vendor/model")
        self.assertEqual(config.provider.api_key, "opaque-test-key")
        self.assertFalse(diagnostics.call_args.kwargs["check_provider_reachability"])
        self.assertNotIn("opaque-test-key", json.dumps(snapshot))

    def test_eof_stops_foreground_loop(self):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        with os.fdopen(read_fd, "rb") as stream:
            server = Mock()
            with patch("iris.ui.select.select", return_value=([stream], [], [])), patch("iris.ui.os.name", "posix"):
                serve_until_eof(server, stream)
            server.handle_request.assert_not_called()

    def test_real_cli_eof_releases_loopback_socket(self):
        process = subprocess.Popen([sys.executable, "-B", "-u", "-m", "iris.ui", "--port", "0"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            banner = read_line(process.stdout)
            port = int(banner.split("127.0.0.1:")[1].split()[0])
            process.stdin.close()
            process.stdin = None
            self.assertEqual(process.wait(timeout=5), 0)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def test_real_snapshot_is_redacted_read_only_and_reports_council(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_path = root / "tasks.sqlite3"
            with TaskStore(task_path) as tasks:
                tasks.create("password=synthetic-stored-secret", due_at="2020-01-01T00:00:00Z")
                tasks.create("Read /home/private/report", due_at="2020-01-01T00:00:00Z")
            env = {"IRIS_PROVIDER_URL": "https://example.invalid/v1", "IRIS_MODEL": "vendor/model"}
            for name in ("TASKS", "MEMORY", "GOALS", "NOTIFICATIONS", "AUTOMATION"):
                env[f"IRIS_{name}_PATH"] = str(root / (name.lower() + ".sqlite3"))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.dict(os.environ, env, clear=True), patch(
                    "iris.brain.providers.openai_compatible.urlopen", side_effect=AssertionError("no network")):
                snapshot = collect_snapshot(now=datetime(2026, 9, 17, tzinfo=timezone.utc))
                self.assertTrue(snapshot["statuses"]["provider_configured"])
                self.assertTrue(snapshot["council"])
                self.assertEqual(snapshot["statuses"]["provider_reachable"], "not_checked")
                for output in (json.dumps(snapshot), render_dashboard(snapshot)):
                    self.assertNotIn("synthetic-stored-secret", output)
                    self.assertNotIn("/home/private", output)
                    self.assertNotIn(directory, output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_non_loopback_binding_rejected(self):
        with self.assertRaises(ValueError):
            create_server("0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()

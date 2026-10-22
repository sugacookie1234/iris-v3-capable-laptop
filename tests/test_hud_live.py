"""Live HUD wiring with synthetic audio and external boundaries replaced."""
import io
import json
import os
from pathlib import Path
import re
import select
from tests.pipe_helpers import read_line
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from contextlib import ExitStack
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from iris.ui import create_server, render_dashboard
from iris.ui_state import clear_conversation, conversation_snapshot, update_conversation
from iris.brain.llm import LLMResponse
from iris.memory.store import MemoryStore
from iris.voice_clap import _VoskTranscriber
from iris.voice.microphone import SoundDeviceOneShotInput
from iris.voice_once import main
from tests.test_voice_microphone import FakeAudioModule, FakeClock


class LiveHUDTests(unittest.TestCase):
    def setUp(self):
        clear_conversation()
        self.addCleanup(clear_conversation)

    def server(self, **kwargs):
        kwargs.setdefault("conversation_token", "t" * 32)
        server = create_server(port=0, **kwargs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(close)
        return server, f"http://127.0.0.1:{server.server_port}"

    def test_live_caption_endpoint_is_uncached_and_preserves_canonical_text(self):
        _, url = self.server()
        update_conversation(state="thinking", user_speech="What is 1/2?",
                            response="IRIS says 1/2. <not markup>")
        with urlopen(url + "/api/conversation", timeout=2) as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(json.load(response), conversation_snapshot())

    def test_bridge_refuses_cross_origin_bad_host_and_non_json_writes(self):
        _, url = self.server()
        body = json.dumps({"state": "listening", "user_speech": "injected"}).encode()
        for headers in (
            {"Origin": "https://untrusted.invalid", "Content-Type": "application/json"},
            {"Host": "untrusted.invalid", "Content-Type": "application/json"},
            {"Content-Type": "text/plain"},
            {"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
        ):
            # Windows can reset a connection closed with an unread rejected body.
            with self.subTest(headers=headers), self.assertRaises((HTTPError, ConnectionResetError)) as error:
                urlopen(Request(url + "/api/conversation", data=body, headers=headers), timeout=2)
            if isinstance(error.exception, HTTPError):
                self.assertIn(error.exception.code, (400, 403, 415))
                error.exception.close()
            self.assertEqual(conversation_snapshot()["state"], "idle")

    def test_shared_session_rejects_external_caption_writers(self):
        _, url = self.server(allow_conversation_updates=False)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(url + "/api/conversation", data=b'{"state":"listening"}',
                            headers={"Content-Type": "application/json", "Authorization": "Bearer " + "t" * 32}), timeout=2)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_native_renderer_has_live_updates_reduced_motion_and_text_only_captions(self):
        markup = render_dashboard({"conversation": {
            "state": "speaking", "user_speech": "What is 1/2?",
            "response": "IRIS: <answer> 1/2",
        }})
        self.assertIn('data-state="speaking"', markup)
        self.assertIn("IRIS: &lt;answer&gt; 1/2", markup)
        self.assertIn("/hud.js", markup)
        self.assertIn("/hud.css", markup)
        self.assertIn('aria-live="polite"', markup)
        self.assertNotIn("I.R.I.S. LOCAL HUD", markup)

    def test_secret_redaction_applies_to_live_captions(self):
        _, url = self.server()
        with patch.dict(os.environ, {"IRIS_API_KEY": "synthetic-sensitive-value"}):
            update_conversation(response="synthetic-sensitive-value")
            with urlopen(url + "/api/conversation", timeout=2) as response:
                self.assertEqual(json.load(response)["response"], "[redacted]")

    def test_invalid_bridge_payload_does_not_change_existing_view(self):
        _, url = self.server()
        update_conversation(state="thinking", response="IRIS retained")
        before = conversation_snapshot()
        for value in ({"state": "recording"}, {"response": {}}, {"response": "x" * 8001},
                      {"state": "idle", "command": "run"}, ["listening"]):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url + "/api/conversation", data=json.dumps(value).encode(),
                                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + "t" * 32}), timeout=2)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
                self.assertEqual(conversation_snapshot(), before)

    def test_publisher_does_not_use_proxy_or_follow_redirects(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from iris.ui_state import HudConversationPublisher
        seen = []
        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(307)
                self.send_header("Location", "/unexpected")
                self.end_headers()
                seen.append("post")
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "no_proxy": ""}):
                publisher = HudConversationPublisher(f"http://127.0.0.1:{server.server_port}/api/conversation", token="t" * 32)
                publisher.publish({"state": "idle"})
            self.assertEqual(seen, ["post"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_bridge_requires_matching_token_and_disabled_bridge_stays_read_only(self):
        for token in ("t" * 32, ""):
            _, url = self.server(conversation_token=token)
            update_conversation(state="thinking", response="IRIS retained")
            before = conversation_snapshot()
            for credential in (None, "Bearer " + "x" * 32, "Bearer " + "t" * 32):
                if token and credential == "Bearer " + token:
                    continue
                headers = {"Content-Type": "application/json"}
                if credential is not None:
                    headers["Authorization"] = credential
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url + "/api/conversation", data=b'{"state":"listening"}',
                                    headers=headers), timeout=2)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                self.assertEqual(conversation_snapshot(), before)

    def test_unconfigured_publisher_never_sends_captions(self):
        from iris.ui_state import HudConversationPublisher
        publisher = HudConversationPublisher("http://127.0.0.1:8765/api/conversation")
        with patch.object(publisher._opener, "open") as send:
            publisher.publish({"response": "private caption"})
        send.assert_not_called()
        for token in ("short", "x" * 129, "x" * 32 + "\n"):
            with self.assertRaises(ValueError):
                HudConversationPublisher(publisher.endpoint, token=token)
            with self.assertRaises(ValueError):
                create_server(port=0, conversation_token=token)

    def test_bridge_token_is_redacted_from_display(self):
        from iris.ui import sanitize_snapshot
        with patch.dict(os.environ, {"IRIS_HUD_TOKEN": "t" * 32}):
            self.assertEqual(sanitize_snapshot({"response": "t" * 32}),
                             {"response": "[redacted]"})

    def _production_turn(self, failure=None):
        """Run main -> builder -> real capture/recognizer/session/brain/Fish -> HUD."""
        text = "What is the launch plan?"
        reply = "IRIS says: staged release, 1/2 at a time."
        provider_calls = []
        stages = []
        built = []
        output = io.StringIO()
        wav = io.BytesIO()
        with wave.open(wav, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x01\x00" * 8)

        def url():
            return re.search(r"IRIS session HUD: (http://\S+)", output.getvalue())[1]

        def snapshot():
            with urlopen(url() + "api/conversation", timeout=2) as response:
                return json.load(response)

        class Vosk:
            def __init__(self, *_):
                pass
            def AcceptWaveform(self, audio):
                self_pcm_valid = isinstance(audio, bytes) and len(audio) % 2 == 0
                if not self_pcm_valid:
                    raise AssertionError("Invalid synthetic PCM")
                return True
            def Result(self):
                return json.dumps({"text": "" if failure == "recognition" else text})
            def FinalResult(self):
                return '{"text":""}'

        module = FakeAudioModule([[.1] * 16])
        original_stream = module.InputStream
        def input_stream(**kwargs):
            self.assertEqual(snapshot()["state"], "listening")
            stages.append("capture")
            if failure == "capture":
                raise OSError("synthetic-private-detail")
            return original_stream(**kwargs)
        module.InputStream = input_stream

        def runner(session, **kwargs):
            result = SoundDeviceOneShotInput(session, **kwargs, audio_module=module,
                                             clock=FakeClock([0, .1, 9]))
            built.append(result)
            return result

        def generate(provider, request):
            self.assertEqual(snapshot()["state"], "thinking")
            self.assertEqual(snapshot()["user_speech"], text)
            self.assertIn("Obsidian note Launch.md", request.messages[0].content)
            provider_calls.append(True)
            stages.append("provider")
            if failure == "provider":
                raise TimeoutError("synthetic-private-detail")
            return LLMResponse(reply, provider.name, request.model)

        def synthesize(request, **_):
            self.assertEqual(snapshot()["state"], "thinking")
            self.assertEqual(snapshot()["response"], reply)
            self.assertEqual(json.loads(request.data)["text"], reply.replace("IRIS", "Iris"))
            stages.append("synthesis")
            if failure == "synthesis":
                raise OSError("synthetic-private-detail")
            response = io.BytesIO(wav.getvalue())
            response.status = 200
            response.headers = {"Content-Type": "audio/wav"}
            return response

        def playback(audio, **_):
            self.assertEqual(snapshot()["state"], "speaking")
            self.assertEqual(snapshot()["response"], reply)
            self.assertEqual(audio, wav.getvalue())
            stages.append("playback")
            if failure == "playback":
                raise OSError("synthetic-private-detail")

        prompts = []
        def enter(_):
            prompts.append(True)
            if len(prompts) == 1:
                self.assertEqual(stages, [])
                self.assertEqual(snapshot()["state"], "idle")
            else:
                self.assertEqual(snapshot()["state"], "error" if failure else "idle")
                self.assertEqual(snapshot()["response"], reply if "synthesis" in stages else "")
                self.assertNotIn("synthetic-private-detail", json.dumps(snapshot()))
                with urlopen(url(), timeout=2) as page:
                    rendered = page.read().decode()
                if "synthesis" in stages:
                    self.assertIn(reply, rendered)
            return ""

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            (vault / "vault index.md").write_text("[Launch plan](Launch.md)")
            (vault / "Launch.md").write_text("The launch plan uses a staged release.")
            env = {"IRIS_PROVIDER_URL": "http://127.0.0.1:1/v1", "IRIS_MODEL": "test-model",
                   "IRIS_FISH_API_KEY": "synthetic-not-a-credential", "IRIS_OBSIDIAN_VAULT": str(vault)}
            for key in ("MEMORY", "TASKS", "GOALS", "NOTIFICATIONS", "AUTOMATION"):
                env[f"IRIS_{key}_PATH"] = str(root / (key.lower() + ".sqlite3"))
            stack.enter_context(patch.dict(os.environ, env, clear=True))
            stack.enter_context(patch("iris.local_config.read_saved", return_value={}))
            stack.enter_context(patch("iris.voice_once._one_shot_transcriber", return_value=_VoskTranscriber(None, Vosk)))
            stack.enter_context(patch("iris.voice_once.SoundDeviceOneShotInput", side_effect=runner))
            stack.enter_context(patch("iris.brain.providers.openai_compatible.OpenAICompatibleProvider.generate", new=generate))
            stack.enter_context(patch("iris.voice.fish_audio.urlopen", side_effect=synthesize))
            sink = Mock()
            sink.play.side_effect = playback
            stack.enter_context(patch("iris.voice_once.WindowsInteropAudioSink", return_value=sink))
            external_hud = stack.enter_context(patch("iris.voice_once.HudConversationPublisher.from_environment"))
            stack.enter_context(patch("builtins.input", side_effect=enter))
            stack.enter_context(patch("sys.stdout", output))
            errors = stack.enter_context(patch("sys.stderr", new_callable=io.StringIO))
            result = main(["--hud", "--utterance-seconds", "8"])
            self.assertEqual(result, 0 if not failure else (2 if failure == "capture" else 1))
            self.assertEqual(len(prompts), 2)
            self.assertEqual(len(provider_calls), 0 if failure in {"capture", "recognition"} else 1)
            external_hud.assert_not_called()
            self.assertEqual(conversation_snapshot(), {"state": "idle", "user_speech": "", "response": ""})
            self.assertIsNone(built[0].session.last_turn)
            with MemoryStore(env["IRIS_MEMORY_PATH"]) as store:
                self.assertEqual(store.current(), ())
            for sensitive in (text, reply, "synthetic-private-detail", "synthetic-not-a-credential"):
                self.assertNotIn(sensitive, output.getvalue() + errors.getvalue())
            sink.close.assert_called_once()
        return stages

    def test_production_one_shot_shared_hud_reaches_every_stage_and_clears_on_close(self):
        self.assertEqual(self._production_turn(), ["capture", "provider", "synthesis", "playback"])

    def test_production_failures_preserve_truthful_hud_state_and_clear_on_close(self):
        for stage in ("capture", "recognition", "provider", "synthesis", "playback"):
            with self.subTest(stage=stage):
                self._production_turn(stage)

    def test_cancel_before_confirmation_never_builds_or_captures(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt), patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO), patch("iris.voice_once.build_voice_flow") as build:
            self.assertEqual(main(["--hud"]), 130)
        build.assert_not_called()
        self.assertEqual(conversation_snapshot()["user_speech"], "")

    def test_separate_process_voice_events_reach_remote_hud_and_clear(self):
        _, url = self.server()
        program = '''
import sys
from iris.ui_state import HudConversationPublisher
from iris.voice import VoiceSession
session = VoiceSession(responder=lambda _: "IRIS remote reply",
                       conversation_sink=HudConversationPublisher(sys.argv[1], timeout=1, token="t" * 32))
session.submit_text("Synthetic remote speech")
print("ready", flush=True)
sys.stdin.readline()
session.close()
print("cleared", flush=True)
'''
        process = subprocess.Popen([sys.executable, "-B", "-c", program, url + "/api/conversation"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            self.assertEqual(read_line(process.stdout).strip(), "ready")
            with urlopen(url + "/api/conversation", timeout=2) as response:
                snapshot = json.load(response)
            self.assertEqual(snapshot["response"], "IRIS remote reply")
            self.assertEqual(snapshot["user_speech"], "Synthetic remote speech")
            out, err = process.communicate("\n", timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(out.strip(), "cleared")
            self.assertEqual(err, "")
            self.assertEqual(conversation_snapshot(), {"state": "idle", "response": "", "user_speech": ""})
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def test_static_assets_are_local_uncached_and_motion_is_state_gated(self):
        _, url = self.server()
        for path in ("/hud.css", "/hud.js"):
            with urlopen(url + path, timeout=2) as response:
                body = response.read().decode()
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertNotIn("https://", body)
            if path.endswith("css"):
                self.assertIn("prefers-reduced-motion:reduce", body)
                for state in ("idle", "listening", "thinking", "speaking", "muted", "error"):
                    self.assertIn(f'[data-state="{state}"]', body)
                self.assertNotIn('animation', body.split('[data-state="idle"]')[1].split('}')[0])
            else:
                for forbidden in ("innerHTML", "localStorage", "sessionStorage", "console.log", "getUserMedia"):
                    # A comment names innerHTML only to explain why textContent is used.
                    self.assertNotIn(forbidden + "(", body)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the optional browser-controller test")
    def test_actual_browser_controller_renders_events_and_clears_without_storage(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([shutil.which("node"), str(root / "tests/hud_browser_check.cjs"),
                                 str(root / "iris/ui_assets/hud.js")],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, "Browser-controller assertions failed")


if __name__ == "__main__":
    unittest.main()

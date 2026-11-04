from pathlib import Path
import io
import hashlib
import math
import os
import sys
import subprocess
import struct
from dataclasses import asdict
import tempfile
import unittest
import wave
from unittest.mock import Mock
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from iris.voice import (DEFAULT_FISH_VOICE_ID, FISH_AUDIO_TTS_URL, FishAudioError,
                        FishAudioPlaybackError, FishAudioSynthesizer, StandardLibraryAudioSink,
                        PlaybackFailureCategory,
                        WindowsInteropAudioSink,
                        VoiceSession, VoiceState, normalize_tts_text)


class Response:
    status = 200
    def __init__(self, body=b"ID3" + b"audio", content_type="audio/mpeg"):
        self.body = body
        self.headers = {"Content-Type": content_type}
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, limit=-1): return self.body if limit < 0 else self.body[:limit]


def make_wav(samples, *, tag=1, bits=16, channels=1, rate=24000, extensible=False,
             mask=0, metadata=b""):
    width = bits // 8
    fmt = struct.pack("<HHIIHH", 0xFFFE if extensible else tag,
                      channels, rate, rate * channels * width, channels * width, bits)
    if extensible:
        fmt += struct.pack("<HHI", 22, bits, mask)
        fmt += struct.pack("<I", tag) + bytes.fromhex("00001000800000aa00389b71")
    def chunk(kind, payload):
        return kind + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) & 1)
    body = b"WAVE" + chunk(b"fmt ", fmt)
    if metadata:
        body += chunk(b"LIST", metadata)
    body += chunk(b"data", samples)
    return b"RIFF" + struct.pack("<I", len(body)) + body


class FishAudioTests(unittest.TestCase):
    def test_tts_name_normalization_preserves_nonstandalone_identifiers(self):
        self.assertEqual(normalize_tts_text("I.R.I.S. and IRIS"), "Iris and Iris")
        self.assertEqual(
            normalize_tts_text("IRIS_MODEL /IRIS-v2 https://example.test/IRIS IRIS_v2"),
            "IRIS_MODEL /IRIS-v2 https://example.test/IRIS IRIS_v2",
        )

    def test_fish_request_uses_pronunciation_name_without_changing_source_text(self):
        received = {}

        def fake_open(request, timeout):
            received["body"] = request.data
            return Response()

        source = "I’m IRIS—see /IRIS-v2 and IRIS_MODEL."
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", side_effect=fake_open):
            FishAudioSynthesizer(audio_sink=lambda _: None).speak(source)
        payload = __import__("json").loads(received["body"])
        self.assertEqual(payload["text"], "I’m Iris—see /IRIS-v2 and IRIS_MODEL.")
        self.assertEqual(source, "I’m IRIS—see /IRIS-v2 and IRIS_MODEL.")

    def test_request_uses_official_endpoint_headers_and_payload(self):
        received = {}
        def fake_open(request, timeout):
            received.update(url=request.full_url, headers=dict(request.headers), body=request.data, timeout=timeout)
            return Response()
        audio = []
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic-fish-key"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", side_effect=fake_open):
            FishAudioSynthesizer(audio_sink=audio.append).speak("Hello IRIS")
        self.assertEqual(received["url"], FISH_AUDIO_TTS_URL)
        self.assertEqual(set(received["headers"]), {"Authorization", "Content-type", "Model"})
        self.assertEqual(received["headers"]["Authorization"], "Bearer synthetic-fish-key")
        self.assertEqual(received["headers"]["Model"], "s2.1-pro-free")
        self.assertEqual(__import__("json").loads(received["body"]),
                         {"text": "Hello Iris", "reference_id": DEFAULT_FISH_VOICE_ID, "format": "mp3",
                          "normalize": True, "temperature": 0.3, "top_p": 0.7})
        self.assertEqual(audio, [b"ID3audio"])

    def test_environment_key_is_bound_only_as_bearer_authorization(self):
        captured = {}

        def fake_open(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            captured["body"] = request.data
            return Response()

        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "offline-test-key"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", side_effect=fake_open):
            FishAudioSynthesizer(audio_sink=lambda _: None).speak("smoke")

        self.assertEqual(captured["authorization"], "Bearer offline-test-key")
        self.assertNotIn("offline-test-key", captured["body"].decode("utf-8"))

    def test_missing_key_and_sink_are_actionable_without_request(self):
        with patch.dict(os.environ, {}, clear=True), patch("iris.voice.fish_audio.urlopen") as call:
            with self.assertRaisesRegex(FishAudioError, "IRIS_FISH_API_KEY"):
                FishAudioSynthesizer(audio_sink=lambda _: None).speak("hello")
            call.assert_not_called()
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True):
            with self.assertRaisesRegex(FishAudioPlaybackError, "audio_sink"):
                FishAudioSynthesizer().speak("hello")

    def test_auth_rate_limit_timeout_provider_and_malformed_audio_errors_are_sanitized(self):
        cases = [(401, "authentication"), (403, "authentication"), (429, "rate limit"), (500, "HTTP 500")]
        for status, message in cases:
            with self.subTest(status=status), patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
                 patch("iris.voice.fish_audio.urlopen", side_effect=HTTPError(FISH_AUDIO_TTS_URL, status, "secret", {}, io.BytesIO(b"secret"))):
                with self.assertRaisesRegex(FishAudioError, message) as raised:
                    FishAudioSynthesizer(audio_sink=lambda _: None).speak("hello")
                self.assertNotIn("secret", str(raised.exception))
        for failure in (TimeoutError(), URLError("secret endpoint")):
            with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
                 patch("iris.voice.fish_audio.urlopen", side_effect=failure):
                with self.assertRaises(FishAudioError) as raised:
                    FishAudioSynthesizer(audio_sink=lambda _: None).speak("hello")
                self.assertNotIn("secret", str(raised.exception))
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response(b"not audio")):
            with self.assertRaisesRegex(FishAudioPlaybackError, "non-MP3") as raised:
                FishAudioSynthesizer(audio_sink=lambda _: None).speak("hello")
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.NON_AUDIO_RESPONSE)

    def test_audio_response_fixtures_record_only_safe_metadata(self):
        wav = make_wav(b"\0\0\0\0", rate=24000)
        fixtures = (
            (wav, "audio/wav", "wav", None),
            (b"ID3" + b"fixture", "audio/mpeg", "mp3", None),
            (b'{"error":"private credential"}', "application/json", "mp3", FishAudioError),
            (wav[:-1], "audio/wav", "wav", None),
        )
        for body, content_type, fmt, expected in fixtures:
            with self.subTest(content_type=content_type, fmt=fmt), \
                 patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
                 patch("iris.voice.fish_audio.urlopen", return_value=Response(body, content_type)):
                synth = FishAudioSynthesizer(audio_sink=lambda _: None, audio_format=fmt)
                if expected:
                    with self.assertRaises(expected) as raised:
                        synth.speak("hello")
                    self.assertEqual(raised.exception.category, PlaybackFailureCategory.JSON_ERROR_RESPONSE)
                    self.assertNotIn("private", str(raised.exception))
                elif body is wav:
                    synth.speak("hello")
                    self.assertEqual(synth.last_audio_metadata.magic, "RIFF")
                    self.assertEqual(synth.last_audio_metadata.byte_length, len(body))
                else:
                    # Truncated RIFF passes the safe response classifier and is
                    # rejected by the WAV sink/parser before any process launch.
                    with self.assertRaises(FishAudioPlaybackError) as raised:
                        WindowsInteropAudioSink(player="python.exe").play(body)
                    self.assertEqual(raised.exception.category, PlaybackFailureCategory.MALFORMED_WAV)

    def test_audio_response_oversize_is_rejected_without_body_exposure(self):
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.MAX_AUDIO_BYTES", 8), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response(b"ID3" + b"oversized-private")):
            synth = FishAudioSynthesizer(audio_sink=lambda _: None)
            with self.assertRaises(FishAudioPlaybackError) as raised:
                synth.speak("hello")
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.OVERSIZED_AUDIO)
            self.assertNotIn("private", str(raised.exception))

    def test_voice_session_contains_fish_failure_and_text_fallback_remains(self):
        session = VoiceSession(synthesizer=FishAudioSynthesizer(audio_sink=lambda _: None))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FishAudioError):
                session.submit_text("hello")
        self.assertEqual(session.state, VoiceState.ERROR)
        session.reset_error()
        session.synthesizer = None
        self.assertEqual(session.submit_text("headless").response, "headless")

    def test_input_bounds(self):
        synth = FishAudioSynthesizer(audio_sink=lambda _: None)
        with self.assertRaises(ValueError): synth.speak(" ")
        with self.assertRaises(ValueError): synth.speak("x" * 10001)

    def test_explicit_wav_mode_and_standard_library_sink(self):
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0" * 8)
        fake_device = Mock()
        fake_oss = type("OSS", (), {"AFMT_S16_LE": 16, "AFMT_U8": 8,
                                     "open": staticmethod(lambda _: fake_device)})
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response(wav_buffer.getvalue())), \
             patch.dict(sys.modules, {"ossaudiodev": fake_oss}), \
             patch.object(sys, "platform", "linux"):
            FishAudioSynthesizer(audio_sink=StandardLibraryAudioSink(), audio_format="wav").speak("hello")
        fake_device.setparameters.assert_called_once_with(16, 1, 8000)
        fake_device.writeall.assert_called_once()
        fake_device.close.assert_called_once_with()

    def test_injected_object_sink_receives_format_and_cleanup(self):
        sink = Mock()
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response()):
            synth = FishAudioSynthesizer(audio_sink=sink)
            synth.speak("hello")
            synth.stop()
            synth.close()
        sink.play.assert_called_once_with(b"ID3audio", audio_format="mp3")
        sink.stop.assert_called_once_with()
        sink.close.assert_called_once_with()

    def test_playback_error_is_distinct_from_provider_error(self):
        sink = Mock()
        sink.play.side_effect = RuntimeError("device unavailable")
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response()):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                FishAudioSynthesizer(audio_sink=sink).speak("hello")
        self.assertNotIsInstance(raised.exception, FishAudioError)

    def test_standard_sink_rejects_malformed_wav_and_wsl_without_backend(self):
        sink = StandardLibraryAudioSink()
        with self.assertRaises(FishAudioPlaybackError):
            sink.play(b"not wav", audio_format="wav")
        valid = io.BytesIO()
        with wave.open(valid, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS", "WSL_INTEROP": "1"}, clear=True), patch.object(sys, "platform", "linux"):
            with self.assertRaisesRegex(FishAudioPlaybackError, "WSL"):
                sink.play(valid.getvalue(), audio_format="wav")

    def test_windows_interop_sink_plays_and_cleans_temporary_audio(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = (None, "")
        process.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process) as popen:
            sink = WindowsInteropAudioSink(player="python.exe")
            sink.play(audio.getvalue(), audio_format="wav")
        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "python.exe")
        self.assertEqual(command[1:3], ["-I", "-c"])
        self.assertIn("winsound.PlaySound", command[3])
        self.assertIn("winsound.SND_SYNC", command[3])
        self.assertFalse(os.path.exists(command[-1]))
        process.communicate.assert_called_once()

    def test_windows_interop_cleanup_waits_until_playback_returns(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        events = []
        process = Mock()
        process.poll.return_value = 0
        process.returncode = 0
        process.communicate.side_effect = lambda timeout: events.append("playback-returned") or (None, "")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process), \
             patch("iris.voice.fish_audio.tempfile.gettempdir", return_value=tempfile.gettempdir()), \
             patch("iris.voice.fish_audio.os.unlink", side_effect=lambda path: events.append("cleanup")):
            WindowsInteropAudioSink(player="python.exe").play(
                audio.getvalue(), audio_format="wav"
            )
        self.assertEqual(events[-2:], ["playback-returned", "cleanup"])

    def test_windows_interop_sink_reports_missing_backend_without_writing(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio._find_windows_player", return_value=None), \
             patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile") as temporary:
            with self.assertRaisesRegex(FishAudioPlaybackError, "Windows Python") as raised:
                WindowsInteropAudioSink().play(audio.getvalue(), audio_format="wav")
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.MISSING_WINDOWS_PYTHON)
        temporary.assert_not_called()

    def test_windows_interop_categories_for_wsl_tools_and_conversion(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.shutil.which", return_value=None):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe").play(audio.getvalue(), audio_format="wav")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.MISSING_WSLPATH)

        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=OSError("private path")):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe", wslpath="wslpath").play(
                    audio.getvalue(), audio_format="wav"
                )
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.GENERAL)

        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.run",
                   return_value=subprocess.CompletedProcess(["python.exe"], 1, "", "private")):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe", wslpath="wslpath").play(
                    audio.getvalue(), audio_format="wav"
                )
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.WINDOWS_TEMP_DISCOVERY)
        self.assertNotIn("private", str(raised.exception))

    def test_windows_interop_category_for_inaccessible_wav_file(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile", side_effect=OSError("private path")):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe").play(audio.getvalue(), audio_format="wav")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.WAV_FILE_INACCESSIBLE)

    def test_windows_interop_categories_for_soundplayer_and_timeout(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock(); process.returncode = 43; process.communicate.return_value = (None, "IRIS_PLAYBACK_DEVICE"); process.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process) as popen:
            sink = WindowsInteropAudioSink(player="python.exe")
            with self.assertRaises(FishAudioPlaybackError) as raised:
                sink.play(audio.getvalue(), audio_format="wav")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.PLAYBACK_DEVICE)
        self.assertNotIn("private", str(raised.exception))
        self.assertEqual(sink.last_backend, "python.exe")
        self.assertEqual(sink.last_playback_exit_code, 43)
        self.assertIsNotNone(sink.last_normalized_byte_length)
        self.assertEqual(sink.last_wav_format.channels, 1)
        self.assertEqual(sink.last_wav_format.sample_rate, 8000)
        self.assertEqual(sink.last_wav_format.bits_per_sample, 16)

        timeout_process = Mock()
        timeout_process.communicate.side_effect = subprocess.TimeoutExpired("python.exe", 1)
        timeout_process.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=timeout_process):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe").play(audio.getvalue(), audio_format="wav")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.CHILD_PROCESS_TIMEOUT)

    def test_powershell_soundplayer_success_uses_load_and_play_sync(self):
        audio = make_wav(b"\0\0")
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = ("IRIS_SOUNDPLAYER_LOAD_OK\r\nIRIS_PLAYSYNC_OK\r\n", "")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process) as popen:
            sink = WindowsInteropAudioSink(powershell="powershell.exe")
            sink.play(audio)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "powershell.exe")
        self.assertEqual(command[5], "-EncodedCommand")
        from iris.voice.fish_audio import base64
        encoded_script = base64.b64decode(command[6]).decode("utf-16le")
        self.assertIn(".Load()", encoded_script)
        self.assertIn(".PlaySync()", encoded_script)
        self.assertIn("[Console]::In.ReadLine()", encoded_script)
        self.assertEqual(len(command), 7)
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.PIPE)
        self.assertEqual(sink.last_backend, "powershell.exe")
        self.assertEqual(sink.last_playback_exit_code, 0)
        self.assertTrue(sink.last_staged_file_accessible)
        self.assertEqual(sink.last_staged_byte_length, sink.last_normalized_byte_length)
        self.assertEqual(sink.last_playback_marker, "IRIS_PLAYSYNC_OK")
        self.assertFalse(os.path.exists(process.communicate.call_args.kwargs["input"].strip()))

    def test_pcm_diagnostics_compare_silent_and_audible_fixtures(self):
        silent = make_wav(b"\0\0" * 100, rate=8000)
        audible = make_wav(struct.pack("<" + "h" * 100, *([12000, -12000] * 50)), rate=8000)
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = ("IRIS_PLAYSYNC_OK", "")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            sink = WindowsInteropAudioSink(powershell="powershell.exe")
            sink.play(silent)
            silent_diag = sink.last_pcm_diagnostics
            sink.play(audible)
            audible_diag = sink.last_pcm_diagnostics
        self.assertEqual(silent_diag.frame_count, 1300)
        self.assertEqual(silent_diag.nonzero_sample_count, 0)
        self.assertEqual(silent_diag.peak_abs_amplitude, 0)
        self.assertEqual(silent_diag.rms_level, 0.0)
        self.assertEqual(audible_diag.frame_count, 1300)
        self.assertGreater(audible_diag.nonzero_sample_count, 0)
        self.assertEqual(audible_diag.peak_abs_amplitude, 12000)
        self.assertGreater(audible_diag.rms_level, 0.0)
        self.assertEqual(sink.last_backend, "powershell.exe")
        self.assertEqual(sink.last_output_device_category, "default_output_device")

        diagnostics = sink.last_audio_diagnostics
        self.assertIsNotNone(diagnostics)
        self.assertEqual(diagnostics.frame_count, 1300)
        self.assertEqual(diagnostics.duration_seconds, 0.1625)
        self.assertEqual(diagnostics.nonzero_sample_count, 100)
        self.assertEqual(diagnostics.peak_abs_amplitude, 12000)
        self.assertGreater(diagnostics.rms_level, 0.0)
        self.assertEqual(diagnostics.backend, "powershell.exe")
        self.assertEqual(diagnostics.output_device_category, "default_output_device")
        self.assertEqual(diagnostics.byte_length, sink.last_normalized_byte_length)
        self.assertEqual(len(diagnostics.checksum), 16)
        self.assertEqual(sink.last_staged_audio_diagnostics, diagnostics)
        self.assertNotIn("samples", repr(diagnostics).lower())

    def test_fish_audio_is_canonicalized_before_powershell_playback(self):
        stereo = struct.pack("<" + "h" * 8, 9000, 9000, -9000, -9000, 12000, 12000, -12000, -12000)
        source = make_wav(stereo, channels=2, rate=44100)
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = ("IRIS_PLAYSYNC_OK", "")
        captured = {}
        def communicate(*, input, timeout):
            with wave.open(input.strip(), "rb") as wav:
                captured["fields"] = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                captured["canonical"] = wav.readframes(wav.getnframes())
            return ("IRIS_SOUNDPLAYER_LOAD_OK\nIRIS_PLAYSYNC_OK\n", "")
        process.communicate.side_effect = communicate
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            sink = WindowsInteropAudioSink(powershell="powershell.exe", canonicalize=True)
            sink.play(source)
        self.assertEqual(captured["fields"], (1, 2, 8000))
        canonical = captured["canonical"]
        values = struct.unpack("<" + "h" * (len(canonical) // 2), canonical)
        self.assertEqual(len(values), 1201)
        self.assertFalse(any(values[:1200]))
        self.assertTrue(any(value != 0 for value in values))
        self.assertEqual(sink.last_audio_diagnostics.frame_count, len(values))
        self.assertGreater(sink.last_audio_diagnostics.peak_abs_amplitude, 0)
        self.assertEqual(sink.last_staged_audio_diagnostics, sink.last_audio_diagnostics)

    def test_default_original_playback_only_pads_temporary_copy_and_preserves_source(self):
        pcm = struct.pack("<6h", 12000, -12000, 6000, -6000, 3000, -3000)
        for channels, rate in ((1, 44100), (2, 48000)):
            with self.subTest(channels=channels, rate=rate), tempfile.TemporaryDirectory() as directory:
                source = bytearray(make_wav(pcm, channels=channels, rate=rate))
                struct.pack_into("<I", source, 4, 4294967076)
                struct.pack_into("<I", source, 40, 4294967040)
                source = bytes(source)
                source_checksum = hashlib.sha256(source).hexdigest()
                response = Response(source, content_type="audio/wav")
                sink = WindowsInteropAudioSink(powershell="powershell.exe")
                self.assertFalse(sink.canonicalize)
                child = Mock(returncode=0)
                child.poll.return_value = 0
                silence_frames = rate * 150 // 1000
                frame_count = len(pcm) // (2 * channels)
                staged_hashes = []

                def communicate(*, input, timeout):
                    # Inspect the exact temporary file before the child returns.
                    self.assertEqual(len(os.listdir(directory)), 1)
                    with open(input.strip(), "rb") as staged:
                        playback = staged.read()
                    staged_hashes.append(hashlib.sha256(playback).hexdigest())
                    with wave.open(io.BytesIO(playback), "rb") as wav:
                        self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth()),
                                         (channels, rate, 2))
                        self.assertEqual(wav.getnframes(), frame_count + silence_frames)
                        self.assertFalse(any(wav.readframes(silence_frames)))
                        self.assertTrue(wav.readframes(frame_count) == pcm, "Original PCM changed")
                    self.assertEqual(struct.unpack_from("<I", playback, 4)[0], len(playback) - 8)
                    self.assertEqual(struct.unpack_from("<H", playback, 32)[0], channels * 2)
                    self.assertEqual(struct.unpack_from("<I", playback, 40)[0], len(playback) - 44)
                    self.assertEqual(sink.last_staged_audio_diagnostics, sink.last_audio_diagnostics)
                    return ("IRIS_SOUNDPLAYER_LOAD_OK\nIRIS_PLAYSYNC_OK\n", "")

                child.communicate.side_effect = communicate
                with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "offline-only"}, clear=True), \
                     patch("iris.voice.fish_audio._find_windows_player", return_value=None), \
                     patch("iris.voice.fish_audio._windows_local_temp_directory_powershell", return_value=directory), \
                     patch("iris.voice.fish_audio.urlopen", return_value=response) as request, \
                     patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile", wraps=tempfile.NamedTemporaryFile) as stage, \
                     patch("iris.voice.fish_audio.subprocess.Popen", return_value=child):
                    FishAudioSynthesizer(audio_format="wav", audio_sink=sink).speak("A short test.")
                request.assert_called_once()
                stage.assert_called_once()
                self.assertEqual(len(os.listdir(directory)), 0)
                self.assertIsNone(sink._temporary_path)
                self.assertIs(response.body, source)
                self.assertEqual(hashlib.sha256(source).hexdigest(), source_checksum)
                self.assertNotEqual(staged_hashes[0], source_checksum)
                self.assertEqual(sink.last_audio_diagnostics.frame_count, frame_count + silence_frames)
                self.assertEqual(sink.last_audio_diagnostics.nonzero_sample_count, 6)
                self.assertEqual(sink.last_audio_diagnostics.peak_abs_amplitude, 12000)
                expected_rms = math.sqrt(2 * (12000**2 + 6000**2 + 3000**2) /
                                         ((frame_count + silence_frames) * channels))
                self.assertAlmostEqual(sink.last_audio_diagnostics.rms_level, expected_rms, places=6)
                self.assertEqual(sink.last_wav_format.frame_count, frame_count)

    def test_preroll_size_limit_rejects_before_staging(self):
        source = make_wav(b"\0\1" * 30, rate=8000)
        with patch("iris.voice.fish_audio.MAX_AUDIO_BYTES", len(source)), \
             patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile") as stage, \
             patch("iris.voice.fish_audio.subprocess.Popen") as process:
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(powershell="powershell.exe").play(source)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.OVERSIZED_AUDIO)
        stage.assert_not_called()
        process.assert_not_called()

    def test_ab_uses_one_response_and_preserves_original_pcm_before_conversion(self):
        # The observed Fish streaming envelope, with synthetic non-silent PCM.
        pcm = b"".join(struct.pack("<h", round(10000 * math.sin(2 * math.pi * 440 * i / 44100)))
                       for i in range(4410))
        source = bytearray(make_wav(pcm, rate=44100))
        struct.pack_into("<I", source, 4, 4294967076)
        struct.pack_into("<I", source, 40, 4294967040)
        seen, results, commands, labels = [], [], [], []
        with tempfile.TemporaryDirectory() as directory:
            sink = WindowsInteropAudioSink(powershell="powershell.exe")

            def before_play(label):
                self.assertEqual(os.listdir(directory), [])
                labels.append(label)

            def launch(command, **kwargs):
                commands.append(command)
                child = Mock(returncode=0)
                child.poll.return_value = 0

                def communicate(*, input, timeout):
                    # The existing staging path is data on stdin, never code.
                    with open(input.strip(), "rb") as staged:
                        output = staged.read()
                    with wave.open(io.BytesIO(output), "rb") as wav:
                        seen.append((wav.getframerate(), wav.getnchannels(), wav.getsampwidth(),
                                     wav.getnframes(), wav.readframes(wav.getnframes())))
                    self.assertEqual(struct.unpack_from("<I", output, 4)[0], len(output) - 8)
                    self.assertEqual(struct.unpack_from("<I", output, 40)[0], len(output) - 44)
                    self.assertEqual(sink.last_staged_audio_diagnostics, sink.last_audio_diagnostics)
                    self.assertEqual(sink.last_audio_diagnostics.checksum,
                                     hashlib.sha256(output).hexdigest()[:16])
                    return ("IRIS_SOUNDPLAYER_LOAD_OK\r\nIRIS_PLAYSYNC_OK\r\n", "private stderr")

                child.communicate.side_effect = communicate
                return child

            def compare(audio):
                results.extend(sink.play_ab(audio, before_play=before_play))

            with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "offline-only"}, clear=True), \
                 patch("iris.voice.fish_audio._windows_local_temp_directory_powershell", return_value=directory), \
                 patch("iris.voice.fish_audio._find_windows_player", return_value=None), \
                 patch("iris.voice.fish_audio.urlopen", return_value=Response(bytes(source))) as request, \
                 patch("iris.voice.fish_audio.subprocess.Popen", side_effect=launch):
                FishAudioSynthesizer(audio_format="wav", audio_sink=compare).speak("A short test.")
            request.assert_called_once()
            self.assertEqual(os.listdir(directory), [])
        self.assertEqual(labels, ["A_original", "B_canonical_8khz"])
        self.assertEqual(commands[0], commands[1])
        self.assertEqual(seen[0][:4], (44100, 1, 2, 11025))
        self.assertFalse(any(seen[0][4][:13230]))
        self.assertTrue(seen[0][4][13230:] == pcm)
        self.assertEqual(seen[1][:4], (8000, 1, 2, 2000))
        self.assertFalse(any(seen[1][4][:2400]))
        self.assertTrue(any(seen[1][4]))
        self.assertEqual([d.duration_seconds for d in results], [0.25, 0.25])
        self.assertTrue(all(d.nonzero_sample_count > 0 and d.rms_level > 0 for d in results))
        self.assertNotEqual(results[0].checksum, results[1].checksum)
        self.assertFalse(sink.canonicalize)  # A/B does not silently select a new default.

    def test_ab_rejects_invalid_streaming_sizes_and_non_pcm_before_playback(self):
        source = bytearray(make_wav(b"\0\1" * 16, rate=44100))
        struct.pack_into("<I", source, 4, 4294967076)
        struct.pack_into("<I", source, 40, 4294967039)
        cases = ((bytes(source), PlaybackFailureCategory.MALFORMED_WAV),
                 (make_wav(struct.pack("<f", 0.5), tag=3, bits=32),
                  PlaybackFailureCategory.UNSUPPORTED_WAV_ENCODING))
        for audio, category in cases:
            with self.subTest(category=category), \
                 patch("iris.voice.fish_audio.subprocess.Popen") as process:
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    WindowsInteropAudioSink(powershell="powershell.exe").play_ab(audio)
                self.assertEqual(raised.exception.category, category)
                process.assert_not_called()

    def test_ab_stops_and_cleans_up_on_failure_timeout_or_interruption(self):
        for failure in (None, subprocess.TimeoutExpired("child", 1), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                child = Mock(returncode=43)
                child.poll.return_value = 43 if failure is None else None
                child.communicate.return_value = (
                    "IRIS_SOUNDPLAYER_LOAD_OK\nIRIS_PLAYSYNC_EXCEPTION\n", "private stderr")
                if failure is not None:
                    child.communicate.side_effect = failure
                with patch.dict(os.environ, {}, clear=True), \
                     patch("iris.voice.fish_audio._find_windows_player", return_value=None), \
                     patch("iris.voice.fish_audio._windows_local_temp_directory_powershell", return_value=directory), \
                     patch("iris.voice.fish_audio.subprocess.Popen", return_value=child) as process:
                    sink = WindowsInteropAudioSink(powershell="powershell.exe")
                    error = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else FishAudioPlaybackError
                    with self.assertRaises(error):
                        sink.play_ab(make_wav(b"\0\1" * 30))
                    process.assert_called_once()  # B must not run after A fails.
                    self.assertEqual(os.listdir(directory), [])
                if failure is not None:
                    child.kill.assert_called_once()
                    child.wait.assert_called_once()

    def test_powershell_zero_exit_without_completion_marker_is_not_success(self):
        for stdout in ("", "IRIS_SOUNDPLAYER_LOAD_OK\n", "private path credential"):
            child = Mock(returncode=0)
            child.poll.return_value = 0
            child.communicate.return_value = (stdout, "private stderr")
            with self.subTest(stdout_length=len(stdout)), patch.dict(os.environ, {}, clear=True), \
                 patch("iris.voice.fish_audio.subprocess.Popen", return_value=child):
                sink = WindowsInteropAudioSink(powershell="powershell.exe")
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    sink.play(make_wav(b"\0\1" * 30))
                self.assertEqual(raised.exception.category, PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT)
                self.assertNotIn("private", str(raised.exception))
                self.assertNotIn("private", repr(sink.last_audio_diagnostics))

    def test_powershell_soundplayer_failure_timeout_and_redaction(self):
        audio = make_wav(b"\0\0")
        process = Mock(returncode=42)
        process.poll.return_value = 0
        process.communicate.return_value = ("IRIS_SOUNDPLAYER_LOAD_EXCEPTION", "private path credential")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            sink = WindowsInteropAudioSink(powershell="powershell.exe")
            with self.assertRaises(FishAudioPlaybackError) as raised:
                sink.play(audio)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.SOUNDPLAYER_LOAD)
        self.assertNotIn("private", str(raised.exception))
        self.assertEqual(sink.last_playback_exit_code, 42)
        self.assertEqual(sink.last_playback_failure_category, PlaybackFailureCategory.SOUNDPLAYER_LOAD)
        self.assertTrue(sink.last_staged_file_accessible)

        device_process = Mock(returncode=43)
        device_process.poll.return_value = 0
        device_process.communicate.return_value = ("IRIS_PLAYSYNC_EXCEPTION", "private device details")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=device_process):
            device_sink = WindowsInteropAudioSink(powershell="powershell.exe")
            with self.assertRaises(FishAudioPlaybackError) as raised:
                device_sink.play(audio)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.PLAYBACK_DEVICE)
        self.assertEqual(device_sink.last_playback_exit_code, 43)
        self.assertEqual(device_sink.last_playback_failure_category, PlaybackFailureCategory.PLAYBACK_DEVICE)
        self.assertTrue(device_sink.last_staged_file_accessible)
        self.assertNotIn("private", str(raised.exception))

        terminated_process = Mock(returncode=43)
        terminated_process.poll.return_value = 0
        terminated_process.communicate.return_value = ("", "private termination details")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=terminated_process):
            terminated_sink = WindowsInteropAudioSink(powershell="powershell.exe")
            with self.assertRaises(FishAudioPlaybackError) as raised:
                terminated_sink.play(audio)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT)
        self.assertIsNone(terminated_sink.last_playback_marker)
        self.assertNotIn("private", str(raised.exception))

        timeout_process = Mock()
        timeout_process.communicate.side_effect = subprocess.TimeoutExpired("powershell.exe", 1)
        timeout_process.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=timeout_process):
            timeout_sink = WindowsInteropAudioSink(powershell="powershell.exe")
            with self.assertRaises(FishAudioPlaybackError) as raised:
                timeout_sink.play(audio)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.CHILD_PROCESS_TIMEOUT)
        self.assertEqual(timeout_sink.last_playback_failure_category,
                         PlaybackFailureCategory.CHILD_PROCESS_TIMEOUT)

        access_process = Mock(returncode=40)
        access_process.poll.return_value = 0
        access_process.communicate.return_value = (None, "private path")
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=access_process):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(powershell="powershell.exe").play(audio)
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.WAV_ACCESS)
        self.assertNotIn("private", str(raised.exception))

    def test_windows_interop_maps_safe_process_markers_without_stderr_leaks(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        cases = (
            (41, "private backend error", PlaybackFailureCategory.MISSING_WINSOUND),
            (42, "IRIS_WAV_ACCESS", PlaybackFailureCategory.WAV_ACCESS),
            (42, "private path and credential", PlaybackFailureCategory.WAV_ACCESS),
            (44, "private temp error", PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION),
            (99, "private path and credential", PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT),
        )
        for return_code, stderr, expected in cases:
            process = Mock(); process.returncode = return_code; process.communicate.return_value = (None, stderr); process.poll.return_value = 0
            with self.subTest(return_code=return_code), \
                 patch.dict(os.environ, {}, clear=True), \
                 patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    WindowsInteropAudioSink(player="python.exe").play(
                        audio.getvalue(), audio_format="wav"
                    )
            self.assertEqual(raised.exception.category, expected)
            self.assertNotIn("private", str(raised.exception))
            self.assertNotIn("credential", str(raised.exception))

    def test_windows_interop_sink_failure_still_cleans_up(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = (None, "Windows audio playback failed.")
        process.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            sink = WindowsInteropAudioSink(player="python.exe")
            with self.assertRaisesRegex(FishAudioPlaybackError, "unsuccessfully") as raised:
                sink.play(audio.getvalue(), audio_format="wav")
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT)
            self.assertIsNone(sink._temporary_path)

    def test_fish_speak_raises_when_windows_process_fails(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = (None, "Windows audio playback failed.")
        process.poll.return_value = 0
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response(audio.getvalue())), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            synth = FishAudioSynthesizer(
                audio_format="wav", audio_sink=WindowsInteropAudioSink(player="python.exe")
            )
            with self.assertRaises(FishAudioPlaybackError):
                synth.speak("hello")

    def test_windows_interop_sink_interrupt_cleans_up_and_stops_process(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock()
        process.communicate.side_effect = KeyboardInterrupt
        process.poll.return_value = None
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process):
            sink = WindowsInteropAudioSink(player="python.exe")
            with self.assertRaises(KeyboardInterrupt):
                sink.play(audio.getvalue(), audio_format="wav")
        process.kill.assert_called_once_with()
        self.assertIsNone(sink._temporary_path)

    def test_windows_interop_sink_converts_wsl_path(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        process = Mock(); process.returncode = 0; process.communicate.return_value = (None, ""); process.poll.return_value = 0
        mapped_temp = tempfile.gettempdir()
        converter_results = [
            Mock(returncode=0, stdout="C:\\Users\\IRIS\\AppData\\Local\\Temp\\\n"),
            Mock(stdout=f"{mapped_temp}\n"),
            Mock(returncode=0, stdout="C:\\Users\\IRIS\\AppData\\Local\\Temp\\iris-fish.wav\n"),
        ]
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=converter_results) as run, \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=process) as popen:
            WindowsInteropAudioSink(player="python.exe", wslpath="wslpath").play(
                audio.getvalue(), audio_format="wav"
            )
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][0], "python.exe")
        self.assertEqual(run.call_args_list[1].args[0][:2], ["wslpath", "-u"])
        self.assertEqual(run.call_args_list[2].args[0][:2], ["wslpath", "-w"])
        self.assertEqual(popen.call_args.args[0][-1], "C:\\Users\\IRIS\\AppData\\Local\\Temp\\iris-fish.wav")

    def test_powershell_temp_discovery_and_cmd_fallback_are_safe(self):
        from iris.voice.fish_audio import _windows_local_temp_directory_powershell
        mapped = tempfile.gettempdir()
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.os.path.isdir", return_value=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=[
                 subprocess.CompletedProcess([], 0, "C:\\Temp\\\n", ""),
                 subprocess.CompletedProcess([], 0, mapped + "\n", ""),
             ]) as run:
            self.assertEqual(_windows_local_temp_directory_powershell("powershell.exe", "wslpath"), mapped)
        self.assertEqual(run.call_count, 2)

        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.os.path.isdir", return_value=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=[
                 subprocess.CompletedProcess([], 1, "", "private"),
                 subprocess.CompletedProcess([], 0, "D:\\Temp\\\n", ""),
                 subprocess.CompletedProcess([], 0, mapped + "\n", ""),
             ]) as run:
            self.assertEqual(_windows_local_temp_directory_powershell("powershell.exe", "wslpath"), mapped)
        self.assertEqual(run.call_count, 3)

    def test_powershell_temp_discovery_rejects_malformed_and_nonzero_results(self):
        from iris.voice.fish_audio import _windows_local_temp_directory_powershell
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=[
                 subprocess.CompletedProcess([], 0, "not-a-windows-path\n", ""),
                 subprocess.CompletedProcess([], 0, "still-not-a-path\n", ""),
             ]):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                _windows_local_temp_directory_powershell("powershell.exe", "wslpath")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.WINDOWS_TEMP_DISCOVERY)
        self.assertNotIn("not-a-windows-path", str(raised.exception))

        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "IRIS"}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.run", side_effect=OSError("private")):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                _windows_local_temp_directory_powershell("powershell.exe", "wslpath")
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.WINDOWS_TEMP_DISCOVERY)
        self.assertNotIn("private", str(raised.exception))

    def test_native_child_uses_synchronous_winsound_and_safe_exit_codes(self):
        from iris.voice.fish_audio import _WINDOWS_AUDIO_SCRIPT
        backend = Mock(SND_FILENAME=0x20000, SND_SYNC=0, SND_NODEFAULT=2)
        with tempfile.TemporaryDirectory() as audio_directory:
            audio = type("Audio", (), {"name": str(Path(audio_directory) / "test.wav")})
            Path(audio.name).write_bytes(b"fixture")
            for error, expected in ((None, None), (RuntimeError("private credential"), 43)):
                backend.PlaySound.side_effect = error
                with patch.dict(sys.modules, {"winsound": backend}), \
                     patch.object(sys, "platform", "win32"), \
                     patch.object(sys, "argv", ["-c", "play", audio.name]):
                    if expected is None:
                        exec(_WINDOWS_AUDIO_SCRIPT, {})
                    else:
                        with self.assertRaises(SystemExit) as raised:
                            exec(_WINDOWS_AUDIO_SCRIPT, {})
                        self.assertEqual(raised.exception.code, expected)
                backend.PlaySound.assert_called_with(audio.name, 0x20002)
        for missing_backend, expected in ((True, 41), (False, 42)):
            with patch.dict(sys.modules, {"winsound": None if missing_backend else backend}), \
                 patch.object(sys, "platform", "win32"), \
                 patch.object(sys, "argv", ["-c", "play", "missing.wav"]), \
                 patch("builtins.open", side_effect=FileNotFoundError("private path")):
                with self.assertRaises(SystemExit) as raised:
                    exec(_WINDOWS_AUDIO_SCRIPT, {})
                self.assertEqual(raised.exception.code, expected)

    def test_native_backend_discovery_and_untrusted_temp_paths(self):
        from iris.voice.fish_audio import _find_windows_player, _windows_local_temp_directory
        with patch("iris.voice.fish_audio.shutil.which", side_effect=[None, "py.exe"]) as which:
            self.assertEqual(_find_windows_player(), "py.exe")
            self.assertEqual([c.args[0] for c in which.call_args_list], ["python.exe", "py.exe"])
        for path in (r"\\server\share", r"\\wsl.localhost\distro", "", "C:\nprivate"):
            with patch.dict(os.environ, {"WSL_DISTRO_NAME": "test"}), \
                 patch("iris.voice.fish_audio.subprocess.run", return_value=Mock(returncode=0, stdout=path)) as run:
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    _windows_local_temp_directory("python.exe", "wslpath", 2)
                self.assertEqual(raised.exception.category, PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION)
                self.assertEqual(run.call_count, 1)

    def test_native_cleanup_on_exit_timeout_interrupt_and_launch_failure(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        cases = (None, 43, subprocess.TimeoutExpired("private", 1), KeyboardInterrupt(), FileNotFoundError("private"))
        for failure in cases:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                process = Mock(returncode=43 if failure == 43 else 0)
                process.poll.return_value = None if isinstance(failure, (KeyboardInterrupt, subprocess.TimeoutExpired)) else process.returncode
                process.communicate.return_value = (None, "private credential")
                if isinstance(failure, (KeyboardInterrupt, subprocess.TimeoutExpired)):
                    process.communicate.side_effect = failure
                def launch(*args, **kwargs):
                    self.assertEqual(len(os.listdir(directory)), 1)
                    if isinstance(failure, FileNotFoundError):
                        raise failure
                    return process
                with patch.dict(os.environ, {}, clear=True), \
                     patch("iris.voice.fish_audio._windows_local_temp_directory", return_value=directory), \
                     patch("iris.voice.fish_audio.subprocess.Popen", side_effect=launch):
                    sink = WindowsInteropAudioSink(player="python.exe")
                    if failure is None:
                        sink.play(audio.getvalue())
                    else:
                        with self.assertRaises(KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else FishAudioPlaybackError):
                            sink.play(audio.getvalue())
                    self.assertEqual(os.listdir(directory), [])
                    self.assertIsNone(sink._temporary_path)
                if isinstance(failure, (KeyboardInterrupt, subprocess.TimeoutExpired)):
                    process.kill.assert_called_once()
                    process.wait.assert_called_once()

    def test_native_write_failure_removes_partial_file(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0")
        with tempfile.TemporaryDirectory() as directory:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as real:
                path = real.name
            handle = Mock(name="partial WAV")
            handle.name = path
            handle.write.side_effect = OSError("private path")
            context = Mock()
            context.__enter__ = Mock(return_value=handle)
            context.__exit__ = Mock(return_value=False)
            with patch.dict(os.environ, {}, clear=True), \
                 patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile", return_value=context):
                with self.assertRaises(FishAudioPlaybackError):
                    WindowsInteropAudioSink(player="python.exe").play(audio.getvalue())
            self.assertFalse(os.path.exists(path))

    def test_wav_integer_widths_normalize_to_16_bit_pcm(self):
        from iris.voice.fish_audio import _inspect_windows_wav, _normalize_windows_wav
        for bits in (8, 16, 24, 32):
            expected = [-32768, 0, 32512 if bits == 8 else 32767]
            values = (0, 128, 255) if bits == 8 else (-(1 << (bits-1)), 0, (1 << (bits-1))-1)
            raw = b"".join(v.to_bytes(bits // 8, "little", signed=bits != 8) for v in values)
            for channels in (1, 2):
                source = make_wav(raw * channels, bits=bits, channels=channels)
                info, data = _inspect_windows_wav(source)
                normalized = _normalize_windows_wav(info, data)
                with wave.open(io.BytesIO(normalized), "rb") as wav:
                    self.assertEqual((wav.getsampwidth(), wav.getnchannels(), wav.getframerate()), (2, channels, 24000))
                    frames = wav.readframes(wav.getnframes())
                    self.assertEqual(struct.unpack("<" + "h" * (3 * channels), frames), tuple(expected * channels))
                self.assertEqual(struct.unpack_from("<H", normalized, 20)[0], 1)

    def test_wav_rate_preservation_and_bounded_conversion(self):
        from iris.voice.fish_audio import _inspect_windows_wav, _normalize_windows_wav
        for rate in (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000):
            source = make_wav(b"\0\0" * 3, rate=rate)
            normalized = _normalize_windows_wav(*_inspect_windows_wav(source))
            with wave.open(io.BytesIO(normalized), "rb") as wav:
                self.assertEqual(wav.getframerate(), rate)
                self.assertEqual(wav.getnframes(), 3)
        source = make_wav(b"\x80" * 8, bits=8)
        with patch("iris.voice.fish_audio.MAX_AUDIO_BYTES", 52):
            with self.assertRaises(FishAudioPlaybackError) as raised:
                _normalize_windows_wav(*_inspect_windows_wav(source))
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS)
        reduced_precision = bytearray(make_wav(b"\0" * 4, bits=32, extensible=True))
        struct.pack_into("<H", reduced_precision, 38, 24)
        with self.assertRaises(FishAudioPlaybackError) as raised:
            _normalize_windows_wav(*_inspect_windows_wav(bytes(reduced_precision)))
        self.assertEqual(raised.exception.category, PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS)

    def test_wav_float_and_extensible_normalization(self):
        from iris.voice.fish_audio import _inspect_windows_wav, _normalize_windows_wav
        for bits, code in ((32, "f"), (64, "d")):
            for extended in (False, True):
                source = make_wav(struct.pack("<" + code * 5, -2, -0.5, 0, 0.5, 2),
                                  tag=3, bits=bits, extensible=extended, mask=4)
                normalized = _normalize_windows_wav(*_inspect_windows_wav(source))
                with wave.open(io.BytesIO(normalized), "rb") as wav:
                    self.assertEqual(struct.unpack("<5h", wav.readframes(5)), (-32768, -16384, 0, 16384, 32767))
        source = make_wav(b"\0" * 12, bits=24, channels=2, extensible=True, mask=3)
        normalized = _normalize_windows_wav(*_inspect_windows_wav(source))
        with wave.open(io.BytesIO(normalized), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getnframes(), wav.getsampwidth()), (2, 2, 2))

    def test_wav_rejects_unsafe_formats_before_launch_or_staging(self):
        cases = [
            (make_wav(b"\0\0", tag=6), PlaybackFailureCategory.UNSUPPORTED_WAV_ENCODING),
            (make_wav(b"\0" * 6, channels=3), PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS),
            (make_wav(b"\0\0", rate=96000), PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS),
            (make_wav(b"\0\0", extensible=True, mask=8), PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS),
            (make_wav(b"\0" * 6, bits=48), PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS),
            (make_wav(struct.pack("<f", float("nan")), tag=3, bits=32), PlaybackFailureCategory.INVALID_WAV_SAMPLES),
            (make_wav(struct.pack("<d", float("inf")), tag=3, bits=64), PlaybackFailureCategory.INVALID_WAV_SAMPLES),
        ]
        for audio, category in cases:
            with self.subTest(category=category), \
                 patch("iris.voice.fish_audio.subprocess.Popen") as process, \
                 patch("iris.voice.fish_audio.tempfile.NamedTemporaryFile") as file:
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    WindowsInteropAudioSink(player="python.exe").play(audio)
                self.assertEqual(raised.exception.category, category)
                process.assert_not_called()
                file.assert_not_called()

    def test_wav_rejects_truncated_inconsistent_and_empty_data(self):
        good = make_wav(b"\0\0")
        bad_align = bytearray(good); struct.pack_into("<H", bad_align, 32, 4)
        bad_size = bytearray(good); struct.pack_into("<I", bad_size, 40, 9999)
        for audio in (good[:-1], b"ID3not-wav", make_wav(b""),
                      make_wav(b"\0"), bytes(bad_align), bytes(bad_size)):
            with self.subTest(size=len(audio)), self.assertRaises(FishAudioPlaybackError) as raised:
                WindowsInteropAudioSink(player="python.exe").play(audio)
            self.assertEqual(raised.exception.category, PlaybackFailureCategory.MALFORMED_WAV)

    def test_wav_diagnostic_and_fish_chunk_order_match_wave_reader(self):
        def chunk(kind, payload):
            return kind + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) & 1)
        fmt = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
        body = (b"WAVE" + chunk(b"JUNK", b"x") + chunk(b"LIST", b"INFO") +
                chunk(b"fmt ", fmt) + chunk(b"fact", struct.pack("<I", 1)) +
                chunk(b"data", b"\0\0"))
        fixture = b"RIFF" + struct.pack("<I", len(body)) + body + b"TRAILING"
        with wave.open(io.BytesIO(fixture), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth()), (1, 24000, 2))
            self.assertEqual(wav.readframes(1), b"\0\0")
        sink = WindowsInteropAudioSink(player="python.exe")
        child = Mock(returncode=0)
        child.communicate.return_value = (None, "")
        child.poll.return_value = 0
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio._windows_local_temp_directory", return_value=directory), \
             patch("iris.voice.fish_audio.subprocess.Popen", return_value=child) as process:
            # A mocked file name can coerce to descriptor 1 and close stdout.
            # Use a real isolated staging file to exercise the read-back safely.
            sink.play(fixture)
            self.assertEqual(os.listdir(directory), [])
        diagnostic = sink.last_wav_diagnostic
        self.assertEqual(diagnostic.riff_marker, "RIFF")
        self.assertEqual(diagnostic.wave_marker, "WAVE")
        self.assertEqual(diagnostic.declared_riff_size, len(body))
        self.assertEqual(diagnostic.actual_byte_length, len(fixture))
        self.assertEqual(diagnostic.chunk_ids, ("JUNK", "LIST", "fmt ", "fact", "data"))
        self.assertEqual(diagnostic.chunk_sizes, (1, 4, 16, 4, 2))
        self.assertEqual((diagnostic.audio_format_tag, diagnostic.channels,
                          diagnostic.sample_rate, diagnostic.bits_per_sample,
                          diagnostic.data_length), (1, 1, 24000, 16, 2))
        process.assert_called_once()

    def test_wav_diagnostic_is_safe_for_truncation_and_untrusted_chunk_ids(self):
        from iris.voice.fish_audio import _wav_diagnostic
        fixture = b"RIFF" + struct.pack("<I", 1000) + b"WAVE" + b"\x00\xff\x01\x02" + struct.pack("<I", 900)
        diagnostic = _wav_diagnostic(fixture)
        self.assertEqual(diagnostic.riff_marker, "RIFF")
        self.assertEqual(diagnostic.wave_marker, "WAVE")
        self.assertEqual(diagnostic.actual_byte_length, len(fixture))
        self.assertEqual(diagnostic.chunk_ids, ("00ff0102",))
        self.assertEqual(diagnostic.chunk_sizes, (900,))
        self.assertIsNone(diagnostic.audio_format_tag)

    def test_malformed_wav_exception_carries_only_safe_diagnostic_fields(self):
        fixture = (b"RIFF" + struct.pack("<I", 1000) + b"WAVE" +
                   b"JUNK" + struct.pack("<I", 7) + b"secret")
        with self.assertRaises(FishAudioPlaybackError) as raised:
            WindowsInteropAudioSink(player="python.exe").play(fixture)
        error = raised.exception
        self.assertEqual(error.category, PlaybackFailureCategory.MALFORMED_WAV)
        diagnostic = error.diagnostic
        self.assertIsNotNone(diagnostic)
        safe = asdict(diagnostic)
        self.assertEqual(set(safe), {
            "riff_marker", "wave_marker", "declared_riff_size", "actual_byte_length",
            "chunk_ids", "chunk_sizes", "audio_format_tag", "channels", "sample_rate",
            "bits_per_sample", "data_length",
        })
        self.assertNotIn("secret", repr(safe))
        self.assertNotIn("Authorization", repr(safe))
        self.assertNotIn("Bearer", repr(safe))
        self.assertNotIn("/", repr(safe))
        self.assertNotIn("\\", repr(safe))
        self.assertNotIn(b"secret", repr(error).encode())

    def test_fish_streaming_wav_placeholders_normalize_to_actual_eof(self):
        data = b"\0\0" * (294912 // 2)
        fixture = bytearray(make_wav(data, rate=44100))
        struct.pack_into("<I", fixture, 4, 4294967076)
        struct.pack_into("<I", fixture, 40, 4294967040)
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (None, "")
        def launch(command, **kwargs):
            with open(command[-1], "rb") as staged:
                normalized = staged.read()
            self.assertEqual(struct.unpack_from("<I", normalized, 4)[0], len(normalized) - 8)
            self.assertEqual(struct.unpack_from("<I", normalized, 40)[0], 294912 + 13230)
            return process
        with patch.dict(os.environ, {}, clear=True), \
             patch("iris.voice.fish_audio.subprocess.Popen", side_effect=launch) as popen:
            sink = WindowsInteropAudioSink(player="python.exe", canonicalize=False)
            sink.play(bytes(fixture))
        self.assertEqual(sink.last_wav_diagnostic.declared_riff_size, 4294967076)
        self.assertEqual(sink.last_wav_diagnostic.data_length, 4294967040)
        popen.assert_called_once()

    def test_fish_streaming_wav_placeholder_rejects_inconsistent_layouts(self):
        data = b"\0\0" * (294912 // 2)
        base = bytearray(make_wav(data, rate=44100))
        struct.pack_into("<I", base, 4, 4294967076)
        struct.pack_into("<I", base, 40, 4294967040)
        cases = []
        bad_data_size = bytearray(base)
        struct.pack_into("<I", bad_data_size, 40, 4294967039)
        cases.append(bad_data_size)
        bad_riff_relation = bytearray(base)
        struct.pack_into("<I", bad_riff_relation, 4, 4294967075)
        cases.append(bad_riff_relation)
        for fixture in cases:
            with self.subTest(length=len(fixture)), \
                 patch.dict(os.environ, {}, clear=True), \
                 patch("iris.voice.fish_audio.subprocess.Popen") as process:
                with self.assertRaises(FishAudioPlaybackError) as raised:
                    WindowsInteropAudioSink(player="python.exe").play(bytes(fixture))
                self.assertEqual(raised.exception.category, PlaybackFailureCategory.MALFORMED_WAV)
                process.assert_not_called()

    def test_fish_wav_is_normalized_before_playback_and_diagnostics_are_numeric(self):
        source = make_wav(struct.pack("<3f", -0.5, 0, 0.5), tag=3, bits=32,
                          metadata=b"private credential and path")
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (None, "")
        seen = []
        def launch(command, **kwargs):
            seen.append(command[-1])
            with open(command[-1], "rb") as file:
                normalized = file.read()
            self.assertNotIn(b"private", normalized)
            with wave.open(io.BytesIO(normalized), "rb") as wav:
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), 3603)
            return process
        sink = WindowsInteropAudioSink(player="python.exe", canonicalize=False)
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True), \
             patch("iris.voice.fish_audio.urlopen", return_value=Response(source)), \
             patch("iris.voice.fish_audio.subprocess.Popen", side_effect=launch):
            FishAudioSynthesizer(audio_format="wav", audio_sink=sink).speak("hello")
        self.assertTrue(all(type(v) is int for v in asdict(sink.last_wav_format).values()))
        self.assertEqual(sink.last_wav_format.encoding_tag, 3)
        self.assertEqual(sink.last_wav_format.bits_per_sample, 32)
        self.assertFalse(os.path.exists(seen[0]))

    def test_playback_is_opt_in_and_text_session_has_no_synthesizer(self):
        self.assertIsNone(VoiceSession().synthesizer)
        with patch.dict(os.environ, {"IRIS_FISH_API_KEY": "synthetic"}, clear=True):
            with self.assertRaises(FishAudioPlaybackError):
                FishAudioSynthesizer().speak("hello")


if __name__ == "__main__":
    unittest.main()


def setUpModule():
    import tempfile
    import unittest
    from pathlib import Path
    from unittest.mock import patch
    from iris.usage import ProviderUsage
    temporary=tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(temporary.cleanup)
    replacement=patch('iris.usage.default_usage',return_value=ProviderUsage(Path(temporary.name)/'usage.sqlite3',{'IRIS_PROVIDER_LIMIT_HOUR':'10000','IRIS_PROVIDER_LIMIT_DAY':'10000','IRIS_PROVIDER_LIMIT_SESSION':'10000'}))
    replacement.start()
    unittest.addModuleCleanup(replacement.stop)

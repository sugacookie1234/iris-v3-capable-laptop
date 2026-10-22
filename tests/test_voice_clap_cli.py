import unittest
from unittest.mock import patch

from iris.voice import VoiceTurn
from iris.voice_clap import _VoskTranscriber, build_voice_flow, main


class FakeBrain:
    def respond(self, text):
        return type("Result", (), {"text": "response to " + text})()


class FakeSynth:
    def __init__(self, **kwargs):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)

    def close(self):
        pass


class FakeSink:
    def close(self):
        self.closed = True


class FakeRunner:
    def run(self):
        return VoiceTurn("request", "response")


class VoiceClapCliTests(unittest.TestCase):
    def test_vosk_streaming_metadata_and_final_json_are_safe(self):
        class FakeVoskRecognizer:
            def __init__(self, _model, _rate):
                self.blocks = []

            def AcceptWaveform(self, audio):
                self.blocks.append(audio)
                return False

            def PartialResult(self):
                return '{"partial":"hidden transcript"}'

            def FinalResult(self):
                return '{"text":"recognized words"}'

        transcriber = _VoskTranscriber(object(), FakeVoskRecognizer)
        transcriber.start_stream()
        transcriber.accept_stream(b"\x00\x00" * 5)
        transcript = transcriber.transcribe(b"full-pcm16")
        self.assertEqual(transcript, "recognized words")
        self.assertEqual(transcriber.last_partial_result_count, 1)
        self.assertEqual(transcriber.last_final_result_count, 1)
        self.assertEqual(transcriber.last_nonempty_partial_result_count, 1)
        self.assertEqual(transcriber.last_max_partial_result_character_count, len("hidden transcript"))
        self.assertTrue(transcriber.last_final_json_has_text_field)
        self.assertEqual(transcriber.last_final_text_character_count, len("recognized words"))
        self.assertTrue(transcriber.last_pcm16_valid)
        self.assertEqual(transcriber.last_pcm16_byte_count, 10)
        self.assertTrue(transcriber.last_transcript_nonempty)
        self.assertEqual(transcriber.last_transcript_character_count, len("recognized words"))

    def test_vosk_combines_completed_segments_with_final_tail_once(self):
        class FakeVoskRecognizer:
            def __init__(self, _model, _rate):
                self.index = 0
                self.final_calls = 0

            def AcceptWaveform(self, _audio):
                self.index += 1
                return self.index in (1, 3)

            def Result(self):
                return '{"text":"first segment"}' if self.index == 1 else '{"text":"second segment"}'

            def PartialResult(self):
                return '{"partial":"tailing"}'

            def FinalResult(self):
                self.final_calls += 1
                return '{"text":"final tail"}'

        transcriber = _VoskTranscriber(object(), FakeVoskRecognizer)
        transcriber.start_stream(16000)
        transcriber.accept_stream(b"\x01\x00")
        transcriber.accept_stream(b"\x02\x00")
        transcriber.accept_stream(b"\x03\x00")
        self.assertEqual(transcriber.transcribe(b"already-streamed"),
                         "first segment second segment final tail")
        self.assertEqual(transcriber.last_completed_result_count, 2)
        self.assertEqual(transcriber.last_final_result_count, 1)
        self.assertEqual(transcriber.transcribe(b"ignored"),
                         "first segment second segment final tail")
        self.assertEqual(transcriber.last_final_result_count, 1)

    def test_vosk_keeps_completed_segment_when_final_text_is_empty(self):
        class FakeVoskRecognizer:
            def __init__(self, _model, _rate):
                pass

            def AcceptWaveform(self, _audio):
                return True

            def Result(self):
                return '{"text":"spoken earlier"}'

            def FinalResult(self):
                return '{"text":""}'

        transcriber = _VoskTranscriber(object(), FakeVoskRecognizer)
        transcriber.start_stream()
        transcriber.accept_stream(b"\x00\x00")
        self.assertEqual(transcriber.transcribe(b"captured"), "spoken earlier")
        self.assertEqual(transcriber.last_final_text_character_count, 0)

    def test_vosk_rejects_malformed_pcm_without_calling_backend(self):
        class FakeVoskRecognizer:
            def __init__(self, _model, _rate):
                self.calls = 0

            def AcceptWaveform(self, _audio):
                self.calls += 1
                return False

        transcriber = _VoskTranscriber(object(), FakeVoskRecognizer)
        transcriber.start_stream()
        with self.assertRaises(Exception):
            transcriber.accept_stream(b"\x00")
        self.assertFalse(transcriber.last_pcm16_valid)

    def test_build_flow_wires_configured_brain_fish_and_greeting_before_capture(self):
        captured = {}
        fake_synth = FakeSynth()

        def fake_runner(gate, **kwargs):
            captured["gate"] = gate
            captured["recorder"] = kwargs["recorder"]
            return FakeRunner()

        with patch("iris.voice_clap.load_config", return_value=object()), \
             patch("iris.voice_clap.create_brain", return_value=FakeBrain()), \
             patch("iris.voice_clap._local_transcriber", return_value=object()), \
             patch("iris.voice_clap.FishAudioSynthesizer", return_value=fake_synth) as fish, \
             patch("iris.voice_clap.WindowsInteropAudioSink", return_value=FakeSink()), \
             patch("iris.voice_clap.SoundDeviceDoubleClapInput", side_effect=fake_runner):
            runner, _sink = build_voice_flow(greeting="hello after clap")

        fish.assert_called_once()
        self.assertIsInstance(captured["gate"].session.recognizer, object)
        captured["gate"].before_capture()
        self.assertEqual(fake_synth.spoken, ["hello after clap"])
        self.assertIsInstance(runner, FakeRunner)

    def test_cli_entry_point_runs_one_flow_and_closes_sink(self):
        sink = FakeSink()
        with patch("iris.voice_clap.build_voice_flow", return_value=(FakeRunner(), sink)):
            self.assertEqual(main(["--greeting", "test", "--trigger-timeout", "2"]), 0)
        self.assertTrue(sink.closed)

    def test_help_exits_without_building_flow(self):
        with patch("iris.voice_clap.build_voice_flow") as build:
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        build.assert_not_called()


if __name__ == "__main__":
    unittest.main()

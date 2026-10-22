import unittest
from unittest.mock import patch

from iris.voice import (DoubleClapDetector, DoubleClapPushToTalk, InMemoryPcmRecorder,
                        LocalPushToTalkRecognizer, SoundDeviceDoubleClapInput,
                        SoundDeviceOneShotInput,
                        VoiceBackendError, VoiceSession, VoiceState)


class FakeStream:
    def __init__(self, blocks):
        self.blocks = list(blocks)
        self.callback = None
        self.closed = False

    def __enter__(self):
        for block in self.blocks:
            self.callback(block, len(block), None, None)
        return self

    def __exit__(self, *_):
        self.closed = True

class FakeAudioModule:
    def __init__(self, blocks):
        self.stream = FakeStream(blocks)
        self.kwargs = None

    def InputStream(self, **kwargs):
        self.kwargs = kwargs
        self.stream.callback = kwargs["callback"]
        return self.stream


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class FakeTranscriber:
    def __init__(self):
        self.audio = []

    def transcribe(self, audio):
        self.audio.append(audio)
        return "microphone words"


class StreamingFakeTranscriber(FakeTranscriber):
    def start_stream(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.blocks = []

    def accept_stream(self, audio):
        self.blocks.append(audio)


class MicrophoneTests(unittest.TestCase):
    def _runner(self, *, module, clock, transcriber=None, **kwargs):
        transcriber = transcriber or FakeTranscriber()
        recorder = InMemoryPcmRecorder(max_audio_bytes=4096)
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
        session = VoiceSession(recognizer=recognizer, responder=lambda text: text.upper())
        gate = DoubleClapPushToTalk(session, detector=DoubleClapDetector())
        return SoundDeviceDoubleClapInput(gate, recorder=recorder, audio_module=module,
                                          clock=clock, utterance_seconds=0.5, **kwargs), session, recorder, transcriber

    def test_default_input_opens_lazily_and_captures_one_utterance_after_clap(self):
        quiet = [0.0] * 16
        clap = [0.5] * 16
        speech = [0.1] * 16
        module = FakeAudioModule([quiet, clap, quiet, clap, speech, speech, speech, speech, speech])
        runner, session, recorder, transcriber = self._runner(
            module=module, clock=FakeClock([0.0, .1, .2, .3, .4, .5, .6, .7, .8, .9]))
        turn = runner.run()
        self.assertEqual(turn.transcript, "microphone words")
        self.assertEqual(turn.response, "MICROPHONE WORDS")
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertFalse(recorder.is_listening)
        self.assertEqual(len(transcriber.audio), 1)
        self.assertGreater(len(transcriber.audio[0]), 0)
        self.assertTrue(module.stream.closed)
        self.assertEqual(module.kwargs["channels"], 1)
        self.assertNotIn("device", module.kwargs)

    def test_timeout_has_no_transcription_and_missing_backend_is_sanitized(self):
        quiet = [0.0] * 16
        module = FakeAudioModule([quiet])
        runner, session, recorder, transcriber = self._runner(
            module=module, clock=FakeClock([0.0, .2]), trigger_timeout_seconds=.1)
        with self.assertRaises(VoiceBackendError):
            runner.run()
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertEqual(transcriber.audio, [])
        self.assertFalse(recorder.is_listening)

        runner, session, recorder, _ = self._runner(
            module=None, clock=FakeClock([0.0]))
        with patch("iris.voice.microphone.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(VoiceBackendError, "sounddevice"):
                runner.run()
        self.assertEqual(session.state, VoiceState.IDLE)

    def test_keyboard_cancellation_closes_stream_and_discards_capture(self):
        module = FakeAudioModule([])
        module.stream = FakeStream([])
        module.InputStream = lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt)
        runner, session, recorder, transcriber = self._runner(
            module=module, clock=FakeClock([0.0, .1]))
        self.assertIsNone(runner.run())
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertFalse(recorder.is_listening)
        self.assertEqual(transcriber.audio, [])

    def test_no_input_frames_fail_without_blocking(self):
        module = FakeAudioModule([])
        runner, session, recorder, transcriber = self._runner(
            module=module, clock=FakeClock([0.0, 0.0]), frame_timeout_seconds=0.01)
        with self.assertRaisesRegex(VoiceBackendError, "no frames"):
            runner.run()
        self.assertTrue(module.stream.closed)
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertFalse(recorder.is_listening)
        self.assertEqual(transcriber.audio, [])

    def test_one_shot_starts_capture_immediately_without_clap(self):
        module = FakeAudioModule([[0.1] * 16, [0.1] * 16])
        recorder = InMemoryPcmRecorder(max_audio_bytes=4096)
        transcriber = StreamingFakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
        session = VoiceSession(recognizer=recognizer, responder=lambda text: text.upper())
        runner = SoundDeviceOneShotInput(
            session,
            recorder=recorder,
            audio_module=module,
            clock=FakeClock([0.0, 0.1, 0.2, 0.6]),
            utterance_seconds=0.5,
            frame_timeout_seconds=0.01,
        )
        turn = runner.run()
        self.assertEqual(turn.transcript, "microphone words")
        self.assertEqual(turn.response, "MICROPHONE WORDS")
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertFalse(recorder.is_listening)
        self.assertEqual(len(transcriber.audio), 1)
        self.assertTrue(module.stream.closed)
        self.assertNotIn("gate", module.kwargs)
        diagnostics = runner.last_capture_diagnostics
        self.assertEqual(diagnostics.callback_frame_count, 2)
        self.assertEqual(diagnostics.total_captured_frames, 32)
        self.assertEqual(diagnostics.nonzero_sample_count, 32)
        self.assertEqual(diagnostics.peak_amplitude, 0.1)
        self.assertEqual(diagnostics.rms_level, 0.1)
        self.assertGreaterEqual(diagnostics.capture_duration_seconds, 0.0)
        self.assertEqual(diagnostics.capture_sample_rate, 16000)
        self.assertEqual(diagnostics.recognizer_sample_rate, 16000)
        self.assertEqual(diagnostics.channels, 1)
        self.assertEqual(diagnostics.pcm_encoding, "pcm16le")
        self.assertEqual([len(block) for block in transcriber.blocks], [32, 32])
        self.assertEqual(transcriber.sample_rate, 16000)

    def test_one_shot_passes_negotiated_capture_rate_to_streaming_recognizer(self):
        module = FakeAudioModule([[0.1] * 16, [0.1] * 16])
        module.stream.samplerate = 44100
        recorder = InMemoryPcmRecorder(max_audio_bytes=4096)
        transcriber = StreamingFakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
        session = VoiceSession(recognizer=recognizer, responder=lambda text: text)
        runner = SoundDeviceOneShotInput(
            session,
            recorder=recorder,
            audio_module=module,
            clock=FakeClock([0.0, 0.1, 0.6]),
            utterance_seconds=0.5,
            frame_timeout_seconds=0.01,
        )
        runner.run()
        self.assertEqual(runner.last_capture_diagnostics.capture_sample_rate, 44100)
        self.assertEqual(runner.last_capture_diagnostics.recognizer_sample_rate, 44100)
        self.assertEqual(transcriber.sample_rate, 44100)

    def test_muted_session_never_opens_microphone(self):
        module = FakeAudioModule([])
        runner, session, _, _ = self._runner(module=module, clock=FakeClock([0.0]))
        session.mute()
        with self.assertRaises(RuntimeError):
            runner.run()
        self.assertIsNone(module.kwargs)


if __name__ == "__main__":
    unittest.main()

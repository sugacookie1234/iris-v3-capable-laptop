import unittest

from iris.voice import (DoubleClapDetector, DoubleClapPushToTalk,
                        LocalPushToTalkRecognizer, VoiceSession, VoiceState)


class FakeRecorder:
    def __init__(self, audio=b"one-utterance"):
        self.audio = audio
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return self.audio


class FakeTranscriber:
    def __init__(self):
        self.audio = []

    def transcribe(self, audio):
        self.audio.append(audio)
        return "hello IRIS"


class ClapTests(unittest.TestCase):
    def test_detector_requires_two_rearmed_spikes_in_window(self):
        detector = DoubleClapDetector()
        self.assertFalse(detector.feed_rms(0.001, 0.00))
        self.assertFalse(detector.feed_rms(0.2, 0.10))
        self.assertFalse(detector.feed_rms(0.001, 0.15))
        self.assertTrue(detector.feed_rms(0.2, 0.30))
        self.assertFalse(detector.feed_rms(0.001, 0.40))
        self.assertFalse(detector.feed_rms(0.2, 0.50))  # cooldown / first new clap only

    def test_detector_rejects_out_of_window_and_invalid_input(self):
        detector = DoubleClapDetector()
        detector.feed_rms(0.2, 0.0)
        detector.feed_rms(0.001, 0.1)
        self.assertFalse(detector.feed_rms(0.2, 1.0))
        with self.assertRaises(ValueError):
            detector.feed_rms(-1, 1.1)
        with self.assertRaises(ValueError):
            detector.feed_rms(0.1, 0.9)

    def test_explicit_clap_gate_starts_one_bounded_utterance_after_trigger(self):
        recorder, transcriber = FakeRecorder(), FakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber, max_audio_bytes=64)
        session = VoiceSession(recognizer=recognizer, responder=lambda text: text.upper())
        gate = DoubleClapPushToTalk(session)
        gate.arm()
        self.assertTrue(gate.armed)
        self.assertEqual(recorder.calls, [])
        self.assertFalse(gate.feed_rms(0.2, 0.0))
        self.assertEqual(recorder.calls, [])
        gate.feed_rms(0.001, 0.1)
        self.assertTrue(gate.feed_rms(0.2, 0.2))
        self.assertEqual(session.state, VoiceState.LISTENING)
        self.assertEqual(recorder.calls, ["start"])
        turn = gate.release()
        self.assertEqual(turn.transcript, "hello IRIS")
        self.assertEqual(turn.response, "HELLO IRIS")
        self.assertEqual(recorder.calls, ["start", "stop"])
        self.assertEqual(transcriber.audio, [b"one-utterance"])
        self.assertIsNone(gate.release())

    def test_greeting_finishes_before_microphone_capture_starts(self):
        events = []

        class OrderedRecorder(FakeRecorder):
            def start(self):
                events.append("capture")
                super().start()

        recorder, transcriber = OrderedRecorder(), FakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
        session = VoiceSession(recognizer=recognizer)
        gate = DoubleClapPushToTalk(
            session,
            before_capture=lambda: events.append("greeting-finished"),
        )
        gate.arm()
        gate.feed_rms(0.2, 0.0)
        gate.feed_rms(0.001, 0.1)
        self.assertTrue(gate.feed_rms(0.2, 0.2))
        self.assertEqual(events, ["greeting-finished", "capture"])
        self.assertEqual(recorder.calls, ["start"])
        self.assertIsNotNone(gate.release())

    def test_gate_is_opt_in_and_does_not_capture_when_muted(self):
        recorder, transcriber = FakeRecorder(), FakeTranscriber()
        session = VoiceSession(recognizer=LocalPushToTalkRecognizer(recorder, transcriber))
        gate = DoubleClapPushToTalk(session)
        session.mute()
        with self.assertRaises(RuntimeError):
            gate.arm()
        self.assertEqual(recorder.calls, [])


if __name__ == "__main__":
    unittest.main()

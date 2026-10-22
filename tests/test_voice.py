import unittest

from iris.voice import VoiceSession, VoiceState
from iris.ui_state import clear_conversation, conversation_snapshot


class FakeRecognizer:
    def __init__(self, transcript):
        self.transcript = transcript
        self.calls = []

    def start_listening(self):
        self.calls.append("start")

    def stop_listening(self):
        self.calls.append("stop")
        return self.transcript


class FakeSynthesizer:
    def __init__(self):
        self.spoken = []
        self.stopped = 0

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stopped += 1


class VoiceSessionTests(unittest.TestCase):
    def tearDown(self):
        clear_conversation()

    def test_push_to_talk_runs_one_explicit_turn(self):
        recognizer = FakeRecognizer("hello IRIS")
        synth = FakeSynthesizer()
        session = VoiceSession(recognizer=recognizer, synthesizer=synth,
                               responder=lambda text: text.upper())

        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertEqual(session.press(), VoiceState.LISTENING)
        self.assertEqual(recognizer.calls, ["start"])
        turn = session.release()
        self.assertEqual(turn.transcript, "hello IRIS")
        self.assertEqual(turn.response, "HELLO IRIS")
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertEqual(recognizer.calls, ["start", "stop"])
        self.assertEqual(synth.spoken, ["HELLO IRIS"])

    def test_session_events_expose_canonical_captions_and_states_in_memory(self):
        seen = []

        def respond(text):
            seen.append(conversation_snapshot())
            return "IRIS says: 4"

        class ObservingSynth(FakeSynthesizer):
            def speak(self, text):
                seen.append(conversation_snapshot())
                super().speak(text)

        session = VoiceSession(recognizer=FakeRecognizer("What is two plus two?"),
                               synthesizer=ObservingSynth(), responder=respond)
        session.press()
        session.release()
        self.assertEqual(seen[0]["state"], "thinking")
        self.assertEqual(seen[0]["user_speech"], "What is two plus two?")
        self.assertEqual(seen[1]["state"], "speaking")
        self.assertEqual(seen[1]["response"], "IRIS says: 4")
        self.assertNotIn("Iris", seen[1]["response"])

    def test_close_clears_session_captions_without_persisting_them(self):
        session = VoiceSession(responder=lambda _: "IRIS response")
        session.submit_text("private spoken phrase")
        self.assertEqual(conversation_snapshot()["user_speech"], "private spoken phrase")
        session.close()
        self.assertEqual(conversation_snapshot(), {"state": "idle", "user_speech": "", "response": ""})

    def test_text_fallback_is_headless_and_deterministic(self):
        seen = []
        session = VoiceSession(responder=seen.append)
        # A responder returning None is invalid, so use a small echo function.
        session.responder = lambda text: seen.append(text) or "ok"
        turn = session.submit_text("keyboard input")
        self.assertEqual(turn.response, "ok")
        self.assertEqual(seen, ["keyboard input"])
        self.assertEqual(session.state, VoiceState.IDLE)

    def test_missing_recognizer_and_invalid_text(self):
        session = VoiceSession()
        with self.assertRaises(RuntimeError):
            session.press()
        self.assertEqual(session.state, VoiceState.IDLE)
        with self.assertRaises(ValueError):
            session.submit_text(" ")

    def test_failures_enter_error_and_can_reset(self):
        session = VoiceSession(responder=lambda _: (_ for _ in ()).throw(ValueError("bad")))
        with self.assertRaises(ValueError):
            session.submit_text("hello")
        self.assertEqual(session.state, VoiceState.ERROR)
        self.assertEqual(session.last_error, "ValueError")
        self.assertEqual(session.reset_error(), VoiceState.IDLE)

        recognizer = FakeRecognizer("")
        session = VoiceSession(recognizer=recognizer)
        session.press()
        self.assertIsNone(session.release())
        self.assertEqual(session.state, VoiceState.ERROR)

    def test_synthesis_failure_on_release_can_recover_to_text(self):
        class BrokenSynthesizer(FakeSynthesizer):
            def speak(self, text):
                raise OSError("synthetic speaker failure")

        session = VoiceSession(recognizer=FakeRecognizer("hello"),
                               synthesizer=BrokenSynthesizer())
        session.press()
        self.assertIsNone(session.release())
        self.assertEqual(session.state, VoiceState.ERROR)
        self.assertEqual(session.last_error, "OSError")
        session.synthesizer = None
        self.assertEqual(session.reset_error(), VoiceState.IDLE)
        self.assertIsNone(session.last_error_message)
        self.assertEqual(session.submit_text("keyboard fallback").response, "keyboard fallback")

    def test_mute_blocks_capture_and_stops_speech(self):
        synth = FakeSynthesizer()
        session = VoiceSession(synthesizer=synth)
        self.assertEqual(session.mute(), VoiceState.MUTED)
        with self.assertRaises(RuntimeError):
            session.submit_text("hello")
        self.assertEqual(session.press(), VoiceState.MUTED)
        self.assertEqual(session.unmute(), VoiceState.IDLE)

        session.state = VoiceState.SPEAKING
        self.assertEqual(session.mute(), VoiceState.MUTED)
        self.assertEqual(synth.stopped, 1)


if __name__ == "__main__":
    unittest.main()

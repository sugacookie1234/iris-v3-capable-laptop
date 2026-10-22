import unittest

from iris.voice import LocalPushToTalkRecognizer, VoiceSession, VoiceState


class FakeRecorder:
    def __init__(self, audio=b"local-audio"):
        self.audio = audio
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return self.audio


class FakeTranscriber:
    def __init__(self, transcript="hello IRIS"):
        self.transcript = transcript
        self.received = []

    def transcribe(self, audio):
        self.received.append(audio)
        return self.transcript


class RecognitionTests(unittest.TestCase):
    def test_push_to_talk_transcribes_one_bounded_segment(self):
        recorder, transcriber = FakeRecorder(), FakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber, max_audio_bytes=32)
        session = VoiceSession(recognizer=recognizer, responder=lambda text: "reply: " + text)
        self.assertEqual(session.press(), VoiceState.LISTENING)
        turn = session.release()
        self.assertEqual(turn.transcript, "hello IRIS")
        self.assertEqual(turn.response, "reply: hello IRIS")
        self.assertEqual(recorder.calls, ["start", "stop"])
        self.assertEqual(transcriber.received, [b"local-audio"])
        self.assertFalse(recognizer.is_listening)

    def test_capture_limit_rejects_before_transcription_and_clears_state(self):
        recorder, transcriber = FakeRecorder(b"0123456789"), FakeTranscriber()
        recognizer = LocalPushToTalkRecognizer(recorder, transcriber, max_audio_bytes=4)
        session = VoiceSession(recognizer=recognizer)
        session.press()
        self.assertIsNone(session.release())
        self.assertEqual(session.state, VoiceState.ERROR)
        self.assertFalse(recognizer.is_listening)
        self.assertEqual(transcriber.received, [])

    def test_transcription_error_is_sanitized_and_retryable(self):
        class BrokenTranscriber:
            def transcribe(self, audio):
                raise RuntimeError("backend detail")

        recognizer = LocalPushToTalkRecognizer(FakeRecorder(), BrokenTranscriber())
        session = VoiceSession(recognizer=recognizer)
        session.press()
        self.assertIsNone(session.release())
        self.assertEqual(session.state, VoiceState.ERROR)
        self.assertEqual(session.last_error, "VoiceBackendError")
        self.assertNotIn("backend detail", session.last_error_message or "")
        session.reset_error()
        session.recognizer.transcriber = FakeTranscriber("retry")
        session.press()
        self.assertEqual(session.release().transcript, "retry")

    def test_mute_blocks_capture_and_text_fallback(self):
        recorder, transcriber = FakeRecorder(), FakeTranscriber()
        session = VoiceSession(recognizer=LocalPushToTalkRecognizer(recorder, transcriber),
                               responder=lambda text: text)
        session.mute()
        self.assertEqual(session.press(), VoiceState.MUTED)
        self.assertEqual(recorder.calls, [])
        with self.assertRaises(RuntimeError):
            session.submit_text("blocked")
        session.unmute()
        self.assertEqual(session.submit_text("keyboard").transcript, "keyboard")

    def test_invalid_capture_and_empty_transcript_are_errors(self):
        for audio, transcript in (("not-bytes", "hello"), (b"audio", " ")):
            with self.subTest(audio=audio, transcript=transcript):
                recognizer = LocalPushToTalkRecognizer(FakeRecorder(audio), FakeTranscriber(transcript))
                session = VoiceSession(recognizer=recognizer)
                session.press()
                self.assertIsNone(session.release())
                self.assertEqual(session.state, VoiceState.ERROR)
                self.assertFalse(recognizer.is_listening)


if __name__ == "__main__":
    unittest.main()

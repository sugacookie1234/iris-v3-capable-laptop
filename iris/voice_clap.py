"""CLI entry point for one explicitly armed IRIS double-clap voice turn."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

from iris.terminal import create_brain, load_config
from iris.voice import (
    DEFAULT_DOUBLE_CLAP_GREETING,
    DoubleClapPushToTalk,
    FishAudioSynthesizer,
    InMemoryPcmRecorder,
    LocalPushToTalkRecognizer,
    SoundDeviceDoubleClapInput,
    VoiceBackendError,
    VoiceSession,
    WindowsInteropAudioSink,
)
from iris.ui_state import HudConversationPublisher


class _VoskTranscriber:
    """Small adapter for an already-installed local Vosk model."""

    def __init__(self, model, recognizer_type):
        self._model = model
        self._recognizer_type = recognizer_type
        self._stream_recognizer = None
        self.last_partial_result_count = 0
        self.last_final_result_count = 0
        self.last_transcript_nonempty = False
        self.last_transcript_character_count = 0
        self.last_recognizer_sample_rate = 16000
        self.last_nonempty_partial_result_count = 0
        self.last_max_partial_result_character_count = 0
        self.last_final_json_has_text_field = False
        self.last_final_text_character_count = 0
        self.last_pcm16_byte_count = 0
        self.last_pcm16_valid = True
        self.last_completed_result_count = 0
        self._completed_segments: list[str] = []
        self._stream_received_audio = False
        self._finalized = False
        self._final_transcript = ""

    def start_stream(self, sample_rate: int = 16000) -> None:
        self.last_recognizer_sample_rate = int(sample_rate)
        self._stream_recognizer = self._recognizer_type(self._model, self.last_recognizer_sample_rate)
        self.last_partial_result_count = 0
        self.last_final_result_count = 0
        self.last_transcript_nonempty = False
        self.last_transcript_character_count = 0
        self.last_nonempty_partial_result_count = 0
        self.last_max_partial_result_character_count = 0
        self.last_final_json_has_text_field = False
        self.last_final_text_character_count = 0
        self.last_pcm16_byte_count = 0
        self.last_pcm16_valid = True
        self.last_completed_result_count = 0
        self._completed_segments = []
        self._stream_received_audio = False
        self._finalized = False
        self._final_transcript = ""

    @staticmethod
    def _json_object(raw) -> dict:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _text_field(value: dict, field: str) -> str:
        text = value.get(field, "")
        return text.strip() if isinstance(text, str) else ""

    def _remember_completed_result(self, raw) -> None:
        result = self._json_object(raw)
        text = self._text_field(result, "text")
        if text and text not in self._completed_segments:
            self._completed_segments.append(text)
            self.last_completed_result_count += 1

    def accept_stream(self, audio: bytes) -> None:
        recognizer = self._stream_recognizer
        if recognizer is None:
            raise RuntimeError("Vosk streaming recognizer is not initialized.")
        if not isinstance(audio, bytes) or not audio or len(audio) % 2:
            self.last_pcm16_valid = False
            raise VoiceBackendError("Vosk requires PCM16 little-endian audio.")
        if self._finalized:
            raise VoiceBackendError("Vosk recognizer has already been finalized.")
        self.last_pcm16_byte_count += len(audio) if isinstance(audio, bytes) else 0
        self._stream_received_audio = self._stream_received_audio or bool(audio)
        if recognizer.AcceptWaveform(audio):
            # Vosk moves an utterance from its partial buffer into Result()
            # when AcceptWaveform returns True.  Losing this result makes a
            # valid utterance appear empty when FinalResult() only contains a
            # trailing empty segment.
            self._remember_completed_result(recognizer.Result())
        else:
            partial_raw = recognizer.PartialResult()
            self.last_partial_result_count += 1
            partial = self._json_object(partial_raw)
            value = self._text_field(partial, "partial")
            length = len(value)
            if length:
                self.last_nonempty_partial_result_count += 1
            self.last_max_partial_result_character_count = max(
                self.last_max_partial_result_character_count, length
            )

    def transcribe(self, audio: bytes) -> str:
        if self._finalized:
            return self._final_transcript
        recognizer = self._stream_recognizer
        if recognizer is None:
            self.start_stream(16000)
            recognizer = self._stream_recognizer
            self.accept_stream(audio)
        elif not self._stream_received_audio:
            # Support non-callback callers that explicitly started a stream.
            # Callback capture has already delivered each block and must not
            # be replayed here.
            self.accept_stream(audio)
        if not self._finalized:
            final_raw = recognizer.FinalResult()
            self.last_final_result_count += 1
            result = self._json_object(final_raw)
            self.last_final_json_has_text_field = "text" in result
            final_text = self._text_field(result, "text")
            self.last_final_text_character_count = len(final_text)
            if final_text and final_text not in self._completed_segments:
                self._completed_segments.append(final_text)
            self._finalized = True
            self._stream_recognizer = None

        transcript = " ".join(self._completed_segments).strip()
        self._final_transcript = transcript
        self.last_transcript_nonempty = bool(transcript)
        self.last_transcript_character_count = len(transcript)
        return transcript


def _local_transcriber():
    model_path = os.environ.get("IRIS_VOSK_MODEL", "").strip()
    if not model_path:
        raise VoiceBackendError("Set IRIS_VOSK_MODEL to a local offline Vosk model directory.")
    try:
        vosk = importlib.import_module("vosk")
        model = vosk.Model(model_path)
        recognizer_type = vosk.KaldiRecognizer
    except ImportError as exc:
        raise VoiceBackendError(
            "The optional local Vosk backend is not installed; use text mode or install vosk."
        ) from exc
    except Exception as exc:
        raise VoiceBackendError("The local Vosk model could not be loaded.") from exc
    return _VoskTranscriber(model, recognizer_type)


def build_voice_flow(*, greeting: str | None = None,
                     trigger_timeout_seconds: float = 30.0,
                     utterance_seconds: float = 8.0):
    """Build the configured one-turn flow without starting the microphone."""
    config = load_config()
    brain = create_brain(config)
    recorder = InMemoryPcmRecorder()
    recognizer = LocalPushToTalkRecognizer(recorder, _local_transcriber())
    sink = WindowsInteropAudioSink(
        powershell=os.environ.get("IRIS_FISH_POWERSHELL") or "powershell.exe"
    )
    synthesizer = FishAudioSynthesizer(
        voice_id=os.environ.get("IRIS_FISH_VOICE_ID", "88b183bfbdda44a09ad4474712b967f4"),
        model=os.environ.get("IRIS_FISH_MODEL"),
        audio_format="wav",
        audio_sink=sink,
    )
    try:
        hud_publisher = HudConversationPublisher.from_environment()
    except ValueError:
        hud_publisher = None

    def respond(text: str) -> str:
        result = brain.respond(text)
        return result.text or "I.R.I.S. did not produce a response."

    session = VoiceSession(recognizer=recognizer, synthesizer=synthesizer,
                           responder=respond, conversation_sink=hud_publisher)
    phrase = (greeting if greeting is not None else
              os.environ.get("IRIS_CLAP_GREETING", DEFAULT_DOUBLE_CLAP_GREETING)).strip()
    gate = DoubleClapPushToTalk(
        session,
        before_capture=lambda: synthesizer.speak(phrase) if phrase else None,
    )
    runner = SoundDeviceDoubleClapInput(
        gate,
        recorder=recorder,
        trigger_timeout_seconds=trigger_timeout_seconds,
        utterance_seconds=utterance_seconds,
    )
    runner.hud_publisher = hud_publisher
    return runner, sink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one opt-in IRIS double-clap voice turn.")
    parser.add_argument("--greeting", help="Greeting spoken after the confirmed double clap.")
    parser.add_argument("--trigger-timeout", type=float, default=30.0,
                        help="Seconds to wait for the double clap (default: 30).")
    parser.add_argument("--utterance-seconds", type=float, default=8.0,
                        help="Maximum microphone capture duration (default: 8).")
    args = parser.parse_args(argv)
    try:
        runner, sink = build_voice_flow(
            greeting=args.greeting,
            trigger_timeout_seconds=args.trigger_timeout,
            utterance_seconds=args.utterance_seconds,
        )
        print("IRIS double-clap voice flow armed. Double clap, then speak one request.", flush=True)
        turn = runner.run()
        if turn is None:
            print("No completed voice turn.", file=sys.stderr)
            return 1
        print("IRIS voice turn completed.")
        return 0
    except KeyboardInterrupt:
        print("IRIS voice flow cancelled.", file=sys.stderr)
        return 130
    except (VoiceBackendError, RuntimeError, ValueError) as exc:
        try:
            HudConversationPublisher.from_environment().publish(
                {"state": "error", "user_speech": "", "response": ""}
            )
        except ValueError:
            pass
        print(f"IRIS voice flow unavailable: {exc}", file=sys.stderr)
        return 2
    finally:
        session = getattr(locals().get("runner"), "gate", None)
        session = getattr(session, "session", None)
        if session is not None:
            session.close()
        if "sink" in locals():
            sink.close()


if __name__ == "__main__":
    raise SystemExit(main())

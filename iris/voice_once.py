"""CLI entry point for one immediate, one-shot IRIS voice command."""
from __future__ import annotations

import argparse
import os
import sys

from iris.memory.integration import respond_with_memory
from iris.memory.store import MemoryStore
from iris.local_config import activate_saved_configuration
from iris.terminal import create_brain, load_config
from iris.voice import (
    FishAudioSynthesizer,
    FasterWhisperSpeechRecognizer,
    InMemoryPcmRecorder,
    LocalPushToTalkRecognizer,
    SoundDeviceOneShotInput,
    VoiceBackendError,
    VoiceSession,
    WindowsInteropAudioSink,
)
from iris.voice_clap import _local_transcriber
from iris.ui_state import HudConversationPublisher, update_conversation


class _ObservedPlaybackSink:
    """Delegate unchanged audio to the existing sink; report only its start."""

    def __init__(self, sink):
        self.sink = sink
        self.on_start = lambda: None

    def play(self, audio, *, audio_format="wav"):
        self.on_start()
        return self.sink.play(audio, audio_format=audio_format)

    def stop(self):
        return self.sink.stop()

    def close(self):
        return self.sink.close()


def build_voice_flow(*, utterance_seconds: float = 8.0,
                     diagnostic_quiet_seconds: float = 1.0,
                     memory_store: MemoryStore | None = None,
                     shared_hud: bool = False):
    """Build the immediate one-shot voice flow without opening the microphone."""
    activate_saved_configuration()
    config = load_config()
    brain = create_brain(config)
    owns_memory_store = memory_store is None
    memory_store = memory_store or MemoryStore()
    recorder = InMemoryPcmRecorder()
    transcriber = _one_shot_transcriber()
    recognizer = LocalPushToTalkRecognizer(recorder, transcriber)
    sink = WindowsInteropAudioSink(
        powershell=os.environ.get("IRIS_FISH_POWERSHELL") or "powershell.exe"
    )
    observed_sink = _ObservedPlaybackSink(sink)
    synthesizer = FishAudioSynthesizer(
        voice_id=os.environ.get("IRIS_FISH_VOICE_ID", "88b183bfbdda44a09ad4474712b967f4"),
        model=os.environ.get("IRIS_FISH_MODEL"),
        audio_format="wav",
        audio_sink=observed_sink,
    )
    try:
        hud_publisher = None if shared_hud else HudConversationPublisher.from_environment()
    except ValueError:
        hud_publisher = None

    def respond(text: str) -> str:
        # Voice transcripts remain prose; only typed host action requests may execute.
        result = respond_with_memory(brain, text, memory_store=memory_store)
        return result.text or "I.R.I.S. did not produce a response."

    session = VoiceSession(recognizer=recognizer, synthesizer=synthesizer,
                           responder=respond, conversation_sink=hud_publisher,
                           playback_reports_state=True)
    observed_sink.on_start = session.playback_started
    runner = SoundDeviceOneShotInput(
        session,
        recorder=recorder,
        utterance_seconds=utterance_seconds,
        diagnostic_quiet_seconds=diagnostic_quiet_seconds,
    )
    runner.memory_store = memory_store
    runner.owns_memory_store = owns_memory_store
    runner.hud_publisher = hud_publisher
    return runner, sink


def _one_shot_transcriber():
    backend = os.environ.get("IRIS_ONESHOT_RECOGNIZER", "vosk").strip().lower()
    if backend == "vosk":
        return _local_transcriber()
    if backend == "whisper":
        return FasterWhisperSpeechRecognizer(
            model_name=os.environ.get("IRIS_WHISPER_MODEL", "tiny.en"),
            device=os.environ.get("IRIS_WHISPER_DEVICE", "cpu"),
            compute_type=os.environ.get("IRIS_WHISPER_COMPUTE_TYPE", "int8"),
        )
    raise VoiceBackendError(
        "IRIS_ONESHOT_RECOGNIZER must be 'vosk' or 'whisper'."
    )


def _print_diagnostics(runner) -> None:
    capture = runner.last_capture_diagnostics
    if capture is None:
        return
    recognizer = getattr(runner.session, "recognizer", None)
    transcriber = getattr(recognizer, "transcriber", None)
    partials = getattr(transcriber, "last_partial_result_count", 0)
    finals = getattr(transcriber, "last_final_result_count", 0)
    nonempty_partials = getattr(transcriber, "last_nonempty_partial_result_count", 0)
    max_partial_chars = getattr(transcriber, "last_max_partial_result_character_count", 0)
    final_has_text = getattr(transcriber, "last_final_json_has_text_field", False)
    final_text_chars = getattr(transcriber, "last_final_text_character_count", 0)
    pcm16_valid = getattr(transcriber, "last_pcm16_valid", True)
    pcm16_byte_count = getattr(transcriber, "last_pcm16_byte_count", 0)
    recognizer_rate = getattr(transcriber, "last_recognizer_sample_rate", capture.recognizer_sample_rate)
    transcript_nonempty = getattr(transcriber, "last_transcript_nonempty", False)
    transcript_character_count = getattr(transcriber, "last_transcript_character_count", 0)
    print(
        "microphone_diagnostics "
        "callback_frame_count=%d total_captured_frames=%d "
        "nonzero_sample_count=%d peak_amplitude=%s rms_level=%s "
        "capture_duration_seconds=%s capture_sample_rate=%d "
        "recognizer_sample_rate=%d channels=%d pcm_encoding=%s "
        "capture_block_frames=%d reference_sample_rate=44100 "
        "reference_block_frames=1764 "
        "vosk_partial_result_count=%d "
        "vosk_final_result_count=%d vosk_nonempty_partial_result_count=%d "
        "vosk_max_partial_result_character_count=%d "
        "vosk_final_json_has_text_field=%s vosk_final_text_character_count=%d "
        "vosk_pcm16_valid=%s vosk_pcm16_byte_count=%d "
        "transcript_nonempty=%s transcript_character_count=%d" % (
            capture.callback_frame_count,
            capture.total_captured_frames,
            capture.nonzero_sample_count,
            capture.peak_amplitude,
            capture.rms_level,
            capture.capture_duration_seconds,
            capture.capture_sample_rate,
            recognizer_rate,
            capture.channels,
            capture.pcm_encoding,
            capture.capture_block_frames,
            partials,
            finals,
            nonempty_partials,
            max_partial_chars,
            final_has_text,
            final_text_chars,
            pcm16_valid,
            pcm16_byte_count,
            transcript_nonempty,
            transcript_character_count,
        )
    )


def _print_phase_diagnostics(runner) -> None:
    capture = runner.last_capture_diagnostics
    if capture is None:
        return
    for name, phase in (("initial_quiet", capture.initial_quiet), ("speaking", capture.speaking)):
        print(
            "microphone_phase_diagnostics phase=%s callback_frame_count=%d "
            "total_captured_frames=%d nonzero_sample_count=%d "
            "peak_amplitude=%s rms_level=%s" % (
                name,
                phase.callback_frame_count,
                phase.total_captured_frames,
                phase.nonzero_sample_count,
                phase.peak_amplitude,
                phase.rms_level,
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one immediate IRIS voice command.")
    parser.add_argument("--utterance-seconds", type=float, default=8.0,
                        help="Maximum microphone capture duration (default: 8).")
    parser.add_argument("--microphone-diagnostic", action="store_true",
                        help="Print safe quiet-versus-speaking microphone statistics.")
    parser.add_argument("--diagnostic-quiet-seconds", type=float, default=1.0,
                        help="Initial diagnostic quiet interval (default: 1).")
    parser.add_argument("--hud", action="store_true",
                        help="Share this one voice session with a local live HUD; wait for Enter before capture.")
    parser.add_argument("--hud-port", type=int, default=0,
                        help="Shared HUD loopback port (default: choose a free port).")
    args = parser.parse_args(argv)
    hud = None
    cancelled = False
    try:
        if args.hud:
            from iris.ui import VoiceHUD
            hud = VoiceHUD(port=args.hud_port)
            hud.start()
            print(f"IRIS session HUD: {hud.url}", flush=True)
            input("Open this URL, then press Enter here when ready for ONE capture (Ctrl+C cancels): ")
        runner, sink = build_voice_flow(
            utterance_seconds=args.utterance_seconds,
            diagnostic_quiet_seconds=args.diagnostic_quiet_seconds,
            **({"shared_hud": True} if args.hud else {}),
        )
        print("IRIS one-shot voice flow started. Speak one request.", flush=True)
        turn = runner.run()
        _print_diagnostics(runner)
        if args.microphone_diagnostic:
            _print_phase_diagnostics(runner)
        if turn is None:
            print("No completed voice turn.", file=sys.stderr)
            return 1
        print("IRIS voice turn completed.")
        return 0
    except (KeyboardInterrupt, EOFError):
        cancelled = True
        print("IRIS voice flow cancelled.", file=sys.stderr)
        return 130
    except (VoiceBackendError, RuntimeError, ValueError, OSError) as exc:
        update_conversation(state="error")
        try:
            if not args.hud:
                HudConversationPublisher.from_environment().publish(
                    {"state": "error", "user_speech": "", "response": ""}
                )
        except ValueError:
            pass
        message = str(exc) if isinstance(exc, VoiceBackendError) else "Voice session could not complete. Check configuration and local backend availability."
        print(f"IRIS voice flow unavailable: {message}", file=sys.stderr)
        return 2
    finally:
        try:
            if hud is not None and not cancelled:
                try:
                    input("Turn ended. Press Enter to close the HUD session and clear captions: ")
                except (EOFError, KeyboardInterrupt):
                    pass
        finally:
            # Prompt failures must not leave the session or its database open.
            session = getattr(locals().get("runner"), "session", None)
            if session is not None:
                session.close()
            if "sink" in locals():
                sink.close()
            runner = locals().get("runner")
            if runner is not None and getattr(runner, "owns_memory_store", False):
                runner.memory_store.close()
            if hud is not None:
                hud.close()


if __name__ == "__main__":
    raise SystemExit(main())

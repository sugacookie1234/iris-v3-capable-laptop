"""Deterministic push-to-talk voice session state machine."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from iris.voice.protocols import SpeechRecognizer, SpeechSynthesizer
from iris.ui_state import clear_conversation, update_conversation


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    MUTED = "muted"
    ERROR = "error"


@dataclass(frozen=True)
class VoiceTurn:
    transcript: str
    response: str


class VoiceSession:
    """One explicit push-to-talk session; it never starts background capture."""

    def __init__(self, *, recognizer: SpeechRecognizer | None = None,
                 synthesizer: SpeechSynthesizer | None = None,
                 responder: Callable[[str], str] | None = None,
                 conversation_sink: Callable[[dict[str, str]], None] | None = None,
                 playback_reports_state: bool = False):
        self.recognizer = recognizer
        self.synthesizer = synthesizer
        self.responder = responder or (lambda text: text)
        self.conversation_sink = conversation_sink
        self.playback_reports_state = playback_reports_state
        self.state = VoiceState.IDLE
        self.last_error: str | None = None
        self.last_error_message: str | None = None
        self.last_turn: VoiceTurn | None = None
        clear_conversation()

    def _publish_conversation(self) -> None:
        if self.conversation_sink is None:
            return
        try:
            from iris.ui_state import conversation_snapshot
            self.conversation_sink(conversation_snapshot())
        except Exception:
            return

    def _update_conversation(self, **changes: str) -> None:
        update_conversation(**changes)
        self._publish_conversation()

    def press(self) -> VoiceState:
        if self.state == VoiceState.MUTED:
            return self.state
        if self.state != VoiceState.IDLE:
            raise RuntimeError(f"Cannot start push-to-talk while voice session is {self.state.value}.")
        if self.recognizer is None:
            raise RuntimeError("No speech recognizer is configured; use submit_text() in headless mode.")
        try:
            self.recognizer.start_listening()
            self.state = VoiceState.LISTENING
            self._update_conversation(state=self.state.value, user_speech="", response="")
            self.last_error = None
            self.last_error_message = None
            return self.state
        except Exception as exc:
            return self._fail(exc)

    def release(self) -> VoiceTurn | None:
        if self.state != VoiceState.LISTENING:
            raise RuntimeError("Push-to-talk release requires an active listening session.")
        try:
            transcript = self.recognizer.stop_listening()  # type: ignore[union-attr]
            return self._process(transcript)
        except Exception as exc:
            self._fail(exc)
            return None

    def submit_text(self, text: str) -> VoiceTurn:
        """Process text without audio for tests, headless WSL, and keyboard fallback."""
        if self.state == VoiceState.MUTED:
            raise RuntimeError("Voice session is muted.")
        if self.state != VoiceState.IDLE:
            raise RuntimeError(f"Cannot submit text while voice session is {self.state.value}.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text fallback requires non-empty text.")
        return self._process(text)

    def cancel(self) -> VoiceState:
        """Cancel an active capture without transcribing or speaking it."""
        if self.state == VoiceState.LISTENING:
            cancel = getattr(self.recognizer, "cancel", None)
            if callable(cancel):
                cancel()
            self.state = VoiceState.IDLE
            self._update_conversation(state=self.state.value)
        return self.state

    def _process(self, transcript: str) -> VoiceTurn:
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("Speech recognizer returned empty text.")
        try:
            self.state = VoiceState.THINKING
            self._update_conversation(state=self.state.value, user_speech=transcript)
            response = self.responder(transcript)
            if not isinstance(response, str):
                raise ValueError("Voice responder must return text.")
            turn = VoiceTurn(transcript, response)
            self.last_turn = turn
            self._update_conversation(response=response)
            if self.synthesizer is not None and response:
                if not self.playback_reports_state:
                    self.playback_started()
                self.synthesizer.speak(response)
            self.state = VoiceState.IDLE
            self._update_conversation(state=self.state.value)
            return turn
        except Exception as exc:
            self._fail(exc)
            raise

    def mute(self) -> VoiceState:
        if self.synthesizer is not None and self.state == VoiceState.SPEAKING:
            self.synthesizer.stop()
        self.state = VoiceState.MUTED
        self._update_conversation(state=self.state.value)
        return self.state

    def playback_started(self) -> None:
        """A wired sink reports the playback handoff, not the TTS request."""
        if self.state == VoiceState.THINKING:
            self.state = VoiceState.SPEAKING
            self._update_conversation(state=self.state.value)

    def unmute(self) -> VoiceState:
        if self.state == VoiceState.MUTED:
            self.state = VoiceState.IDLE
            self._update_conversation(state=self.state.value)
        return self.state

    def reset_error(self) -> VoiceState:
        if self.state == VoiceState.ERROR:
            self.last_error = None
            self.last_error_message = None
            self.state = VoiceState.IDLE
            self._update_conversation(state=self.state.value)
        return self.state

    def close(self) -> None:
        """End this process-local session and remove captions from the HUD."""
        self.cancel()
        self.last_turn = None
        self.last_error = None
        self.last_error_message = None
        clear_conversation()
        self._publish_conversation()

    def _fail(self, exc: Exception) -> VoiceState:
        self.last_error = type(exc).__name__
        self.last_error_message = str(exc) or self.last_error
        self.state = VoiceState.ERROR
        self._update_conversation(state=self.state.value)
        return self.state

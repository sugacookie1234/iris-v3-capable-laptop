"""Provider-independent interfaces for optional local voice backends."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioSink(Protocol):
    """Injectable local audio output.

    Sinks receive in-memory audio and must not persist or upload it.  ``stop``
    and ``close`` are lifecycle hooks; implementations may treat them as
    no-ops when their backend has no corresponding operation.
    """

    def play(self, audio: bytes, *, audio_format: str) -> None:
        """Play one complete audio payload locally."""

    def stop(self) -> None:
        """Stop current playback, if supported."""

    def close(self) -> None:
        """Release local playback resources."""


@runtime_checkable
class SpeechRecognizer(Protocol):
    """A push-to-talk recognizer; implementations must be local unless opted in."""

    def start_listening(self) -> None:
        """Begin capturing the current push-to-talk segment."""

    def stop_listening(self) -> str:
        """Stop the segment and return its transcript."""


@runtime_checkable
class AudioRecorder(Protocol):
    """Local recorder used only during one push-to-talk segment."""

    def start(self) -> None: ...
    def stop(self) -> bytes: ...


@runtime_checkable
class OfflineTranscriber(Protocol):
    """Local transcription engine receiving one in-memory segment."""

    def transcribe(self, audio: bytes) -> str: ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """A local speech output implementation."""

    def speak(self, text: str) -> None:
        """Speak text locally; no transport is implied by this protocol."""

    def stop(self) -> None:
        """Stop current speech, if any."""


class LocalSpeechRecognizer(SpeechRecognizer, Protocol):
    """Optional marker for a recognizer that never uploads audio."""


class LocalSpeechSynthesizer(SpeechSynthesizer, Protocol):
    """Optional marker for a synthesizer that renders locally."""

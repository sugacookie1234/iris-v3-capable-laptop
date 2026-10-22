"""Optional local voice adapters.

The adapters deliberately import third-party backends only when a push-to-talk
turn is started.  A backend module may expose ``create_recognizer()`` or
``create_synthesizer()`` returning an object that implements the IRIS protocol.
This keeps the core and headless text mode dependency-free.
"""
from __future__ import annotations

import importlib
import struct
from typing import Any, Callable

from iris.voice.protocols import AudioRecorder, OfflineTranscriber, SpeechRecognizer, SpeechSynthesizer


class VoiceBackendError(RuntimeError):
    """A configured optional backend cannot be used locally."""


class LocalPushToTalkRecognizer:
    """Connect a local recorder to an offline transcriber for one held press."""

    def __init__(self, recorder: AudioRecorder, transcriber: OfflineTranscriber,
                 *, max_audio_bytes: int = 10 * 1024 * 1024):
        if recorder is None or transcriber is None:
            raise ValueError("A local recorder and offline transcriber are required.")
        if type(max_audio_bytes) is not int or not 0 < max_audio_bytes <= 100 * 1024 * 1024:
            raise ValueError("max_audio_bytes must be a positive bounded integer.")
        self.recorder = recorder
        self.transcriber = transcriber
        self.max_audio_bytes = max_audio_bytes
        self._capturing = False

    @staticmethod
    def _call(obj, primary: str, fallback: str):
        callback = getattr(obj, primary, None) or getattr(obj, fallback, None)
        if not callable(callback):
            raise VoiceBackendError("Local recorder lacks a required capture operation.")
        return callback()

    def start_listening(self) -> None:
        if self._capturing:
            raise VoiceBackendError("Push-to-talk capture is already active.")
        try:
            self._call(self.recorder, "start", "start_listening")
            self._capturing = True
        except VoiceBackendError:
            raise
        except Exception as exc:
            raise VoiceBackendError("Local microphone capture could not start.") from exc

    def stop_listening(self) -> str:
        if not self._capturing:
            raise VoiceBackendError("Push-to-talk capture is not active.")
        audio = None
        try:
            audio = self._call(self.recorder, "stop", "stop_listening")
            if not isinstance(audio, (bytes, bytearray, memoryview)):
                raise VoiceBackendError("Local recorder returned an invalid audio buffer.")
            audio = bytes(audio)
            if not audio:
                raise VoiceBackendError("Local recorder returned an empty audio buffer.")
            if len(audio) > self.max_audio_bytes:
                raise VoiceBackendError("Local audio segment exceeds the configured size limit.")
            transcribe = getattr(self.transcriber, "transcribe", None)
            if not callable(transcribe) and callable(self.transcriber):
                transcribe = self.transcriber
            if not callable(transcribe):
                raise VoiceBackendError("Local transcriber lacks a transcription operation.")
            transcript = transcribe(audio)
            if not isinstance(transcript, str) or not transcript.strip():
                raise VoiceBackendError("Local transcriber returned empty text.")
            return transcript
        except VoiceBackendError:
            raise
        except Exception as exc:
            raise VoiceBackendError("Local offline transcription failed.") from exc
        finally:
            audio = None
            self._capturing = False

    @property
    def is_listening(self) -> bool:
        return self._capturing

    def cancel(self) -> None:
        """Discard an active segment without invoking transcription."""
        cancel = getattr(self.recorder, "cancel", None)
        if callable(cancel):
            cancel()
        self._capturing = False


MicrophoneSpeechRecognizer = LocalPushToTalkRecognizer
OfflineSpeechRecognizer = LocalPushToTalkRecognizer


class FasterWhisperSpeechRecognizer:
    """Optional in-memory faster-whisper transcriber for one-shot voice."""

    def __init__(self, *, model_name: str = "tiny.en", device: str = "cpu",
                 compute_type: str = "int8", model: Any | None = None):
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("Whisper model name must be non-empty.")
        self.model_name = model_name.strip()
        self.device = device.strip() if isinstance(device, str) else ""
        self.compute_type = compute_type.strip() if isinstance(compute_type, str) else ""
        if not self.device or not self.compute_type:
            raise ValueError("Whisper device and compute type must be non-empty.")
        if model is not None:
            self._model = model
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise VoiceBackendError(
                "Optional faster-whisper backend is not installed; install faster-whisper or use Vosk."
            ) from exc
        try:
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type,
            )
        except Exception as exc:
            raise VoiceBackendError("The local faster-whisper model could not be loaded.") from exc

    def transcribe(self, audio: bytes) -> str:
        if not isinstance(audio, bytes) or not audio or len(audio) % 2:
            raise VoiceBackendError("Local Whisper requires non-empty PCM16 audio.")
        if not any(audio):
            return ""
        try:
            try:
                import numpy as np
                samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
            except ImportError:
                samples = [value[0] / 32768.0 for value in struct.iter_unpack("<h", audio)]
            segments, _info = self._model.transcribe(
                samples, language="en", beam_size=5, vad_filter=True,
            )
            parts = []
            for segment in segments:
                value = getattr(segment, "text", "")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
            text = " ".join(parts)
        except VoiceBackendError:
            raise
        except Exception as exc:
            raise VoiceBackendError("Local faster-whisper transcription failed.") from exc
        return text


def _load(module_name: str, factory_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise VoiceBackendError(
            f"Optional local voice backend '{module_name}' is not installed. "
            f"Install the backend and its local audio dependencies, or use submit_text()."
        ) from exc
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise VoiceBackendError(
            f"Voice backend '{module_name}' must provide {factory_name}(). "
            "No audio was captured or uploaded."
        )
    try:
        return factory()
    except Exception as exc:
        raise VoiceBackendError(f"Could not initialize local voice backend '{module_name}'.") from exc


class LocalSpeechRecognizerAdapter:
    """Lazy adapter for a local module or explicitly injected fake backend."""

    def __init__(self, backend: SpeechRecognizer | None = None, *, module_name: str | None = None,
                 backend_factory: Callable[[], SpeechRecognizer] | None = None):
        if sum(item is not None for item in (backend, module_name, backend_factory)) != 1:
            raise ValueError("Provide exactly one local recognizer backend, module_name, or backend_factory.")
        self._backend = backend
        self._module_name = module_name
        self._factory = backend_factory

    def _get(self) -> SpeechRecognizer:
        if self._backend is None:
            self._backend = (self._factory() if self._factory is not None
                             else _load(self._module_name, "create_recognizer"))  # type: ignore[arg-type]
        return self._backend

    def start_listening(self) -> None:
        self._get().start_listening()

    def stop_listening(self) -> str:
        return self._get().stop_listening()


class LocalSpeechSynthesizerAdapter:
    """Lazy adapter for a local module or explicitly injected fake backend."""

    def __init__(self, backend: SpeechSynthesizer | None = None, *, module_name: str | None = None,
                 backend_factory: Callable[[], SpeechSynthesizer] | None = None):
        if sum(item is not None for item in (backend, module_name, backend_factory)) != 1:
            raise ValueError("Provide exactly one local synthesizer backend, module_name, or backend_factory.")
        self._backend = backend
        self._module_name = module_name
        self._factory = backend_factory

    def _get(self) -> SpeechSynthesizer:
        if self._backend is None:
            self._backend = (self._factory() if self._factory is not None
                             else _load(self._module_name, "create_synthesizer"))  # type: ignore[arg-type]
        return self._backend

    def speak(self, text: str) -> None:
        self._get().speak(text)

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.stop()


class VoskSpeechRecognizer(LocalSpeechRecognizerAdapter):
    """Optional Vosk-compatible local recognizer module adapter."""

    def __init__(self, backend: SpeechRecognizer | None = None):
        super().__init__(backend, module_name=None if backend else "vosk")


class PiperSpeechSynthesizer(LocalSpeechSynthesizerAdapter):
    """Optional Piper-compatible local synthesizer module adapter."""

    def __init__(self, backend: SpeechSynthesizer | None = None):
        super().__init__(backend, module_name=None if backend else "piper")

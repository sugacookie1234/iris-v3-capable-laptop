"""Optional local microphone capture for the explicit double-clap flow."""
from __future__ import annotations

import importlib
import math
import queue
import struct
import time
from dataclasses import dataclass
from typing import Any, Callable

from iris.voice.adapters import LocalPushToTalkRecognizer, VoiceBackendError
from iris.voice.clap import DoubleClapPushToTalk
from iris.voice.session import VoiceTurn


def _samples(block: Any):
    """Yield mono float samples without requiring NumPy."""
    if hasattr(block, "tolist"):
        block = block.tolist()
    if isinstance(block, (bytes, bytearray, memoryview)):
        raise VoiceBackendError("Microphone backend returned an unsupported audio buffer.")
    try:
        iterator = iter(block)
    except TypeError as exc:
        raise VoiceBackendError("Microphone backend returned invalid audio data.") from exc
    for value in iterator:
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = sum(float(item) for item in value) / len(value)
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise VoiceBackendError("Microphone backend returned invalid audio data.") from exc
        if not math.isfinite(value):
            raise VoiceBackendError("Microphone backend returned non-finite audio data.")
        yield max(-1.0, min(1.0, value))


def _rms(block: Any) -> float:
    values = list(_samples(block))
    return math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def _pcm16_bytes(block: Any) -> bytes:
    return b"".join(struct.pack("<h", round(value * 32767.0)) for value in _samples(block))


@dataclass(frozen=True)
class MicrophonePhaseDiagnostics:
    """Safe numeric facts for one phase of an in-memory capture."""

    callback_frame_count: int
    total_captured_frames: int
    nonzero_sample_count: int
    peak_amplitude: float
    rms_level: float


def _phase_diagnostics(stats: list) -> MicrophonePhaseDiagnostics:
    callback_count, frame_count, nonzero, peak, sum_squares, samples = stats
    return MicrophonePhaseDiagnostics(
        callback_frame_count=callback_count,
        total_captured_frames=frame_count,
        nonzero_sample_count=nonzero,
        peak_amplitude=round(peak, 9),
        rms_level=round(math.sqrt(sum_squares / samples), 9) if samples else 0.0,
    )


@dataclass(frozen=True)
class MicrophoneCaptureDiagnostics:
    """Safe numeric facts from one in-memory capture attempt."""

    callback_frame_count: int
    total_captured_frames: int
    nonzero_sample_count: int
    peak_amplitude: float
    rms_level: float
    capture_duration_seconds: float
    capture_sample_rate: int
    recognizer_sample_rate: int
    channels: int
    pcm_encoding: str
    capture_block_frames: int
    initial_quiet: MicrophonePhaseDiagnostics
    speaking: MicrophonePhaseDiagnostics


class InMemoryPcmRecorder:
    """Bounded PCM16 recorder used by the sounddevice runner and tests."""

    def __init__(self, *, max_audio_bytes: int = 10 * 1024 * 1024):
        if type(max_audio_bytes) is not int or not 0 < max_audio_bytes <= 100 * 1024 * 1024:
            raise ValueError("max_audio_bytes must be a positive bounded integer.")
        self.max_audio_bytes = max_audio_bytes
        self._buffer = bytearray()
        self._capturing = False

    def start(self) -> None:
        self.cancel()
        self._capturing = True

    def append(self, block: Any) -> None:
        if not self._capturing:
            return
        encoded = _pcm16_bytes(block)
        if len(self._buffer) + len(encoded) > self.max_audio_bytes:
            self.cancel()
            raise VoiceBackendError("Microphone utterance exceeded the configured size limit.")
        self._buffer.extend(encoded)

    def stop(self) -> bytes:
        if not self._capturing:
            raise VoiceBackendError("Microphone capture is not active.")
        try:
            audio = bytes(self._buffer)
            if not audio:
                raise VoiceBackendError("Microphone utterance was silent or empty.")
            return audio
        finally:
            self.cancel()

    def cancel(self) -> None:
        self._buffer.clear()
        self._capturing = False

    @property
    def is_listening(self) -> bool:
        return self._capturing


class SoundDeviceDoubleClapInput:
    """Lazy sounddevice runner for one explicitly armed double-clap turn.

    It opens the default input only inside ``run``. The module is imported
    lazily, no device list is queried, and the stream closes after one turn.
    """

    def __init__(self, gate: DoubleClapPushToTalk, *, recorder: InMemoryPcmRecorder,
                 sample_rate: int = 16_000, block_ms: int = 40,
                 trigger_timeout_seconds: float = 30.0,
                 utterance_seconds: float = 8.0,
                 frame_timeout_seconds: float = 2.0,
                 diagnostic_quiet_seconds: float = 1.0,
                 audio_module: Any | None = None,
                 clock: Callable[[], float] = time.monotonic):
        if (sample_rate <= 0 or block_ms <= 0 or trigger_timeout_seconds <= 0 or
                utterance_seconds <= 0 or frame_timeout_seconds <= 0):
            raise ValueError("Microphone timing and sample-rate values must be positive.")
        self.gate = gate
        self.recorder = recorder
        self.sample_rate = int(sample_rate)
        self.block_ms = int(block_ms)
        self.trigger_timeout_seconds = float(trigger_timeout_seconds)
        self.utterance_seconds = float(utterance_seconds)
        self.frame_timeout_seconds = float(frame_timeout_seconds)
        self.audio_module = audio_module
        self.clock = clock
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.recorder.cancel()
        self.gate.cancel()

    def run(self) -> VoiceTurn | None:
        self._cancelled = False
        self.gate.arm()
        module = self.audio_module
        if module is None:
            try:
                module = importlib.import_module("sounddevice")
            except ImportError as exc:
                self.gate.cancel()
                raise VoiceBackendError(
                    "Optional local microphone backend 'sounddevice' is not installed."
                ) from exc
        blocksize = max(1, self.sample_rate * self.block_ms // 1000)
        started = self.clock()
        capture_deadline: float | None = None
        frames = queue.Queue(maxsize=16)
        callback_status = False

        def receive(indata, _frame_count, _stream_time, status):
            nonlocal callback_status
            if status:
                callback_status = True
            try:
                # PortAudio reuses callback buffers; retain only this bounded,
                # in-memory block until the control loop consumes it.
                block = indata.copy() if hasattr(indata, "copy") else indata
                frames.put_nowait(block)
            except queue.Full:
                # The control loop is stalled; dropping a block is safer than
                # allowing callback memory to grow without bound.
                pass

        try:
            with module.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="float32", blocksize=blocksize,
                                    callback=receive) as stream:
                frame_deadline = time.monotonic() + self.frame_timeout_seconds
                while not self._cancelled:
                    now = self.clock()
                    if capture_deadline is not None and now >= capture_deadline:
                        return self.gate.release()
                    if capture_deadline is None and now - started >= self.trigger_timeout_seconds:
                        raise VoiceBackendError("No double clap was detected before the microphone timeout.")
                    try:
                        data = frames.get(timeout=max(0.0, frame_deadline - time.monotonic()))
                    except queue.Empty:
                        if callback_status:
                            raise VoiceBackendError("Microphone input backend failed to deliver frames.")
                        raise VoiceBackendError("Microphone input produced no frames before the capture timeout.")
                    frame_deadline = time.monotonic() + self.frame_timeout_seconds
                    if self.gate.triggered:
                        self.recorder.append(data)
                    elif self.gate.feed_rms(_rms(data), now - started):
                        capture_deadline = now + self.utterance_seconds
                return None
        except KeyboardInterrupt:
            self.cancel()
            return None
        except VoiceBackendError:
            self.cancel()
            raise
        except Exception as exc:
            self.cancel()
            raise VoiceBackendError("Local microphone capture failed.") from exc


class SoundDeviceOneShotInput:
    """Capture one bounded utterance immediately, without clap gating."""

    def __init__(self, session: VoiceSession, *, recorder: InMemoryPcmRecorder,
                 sample_rate: int = 16_000, block_ms: int = 40,
                 utterance_seconds: float = 8.0,
                 frame_timeout_seconds: float = 2.0,
                 diagnostic_quiet_seconds: float = 1.0,
                 audio_module: Any | None = None,
                 clock: Callable[[], float] = time.monotonic):
        if (sample_rate <= 0 or block_ms <= 0 or utterance_seconds <= 0 or
                frame_timeout_seconds <= 0 or diagnostic_quiet_seconds < 0):
            raise ValueError("Microphone timing and sample-rate values must be positive.")
        self.session = session
        self.recorder = recorder
        self.sample_rate = int(sample_rate)
        self.block_ms = int(block_ms)
        self.utterance_seconds = float(utterance_seconds)
        self.frame_timeout_seconds = float(frame_timeout_seconds)
        self.diagnostic_quiet_seconds = float(diagnostic_quiet_seconds)
        self.audio_module = audio_module
        self.clock = clock
        self._cancelled = False
        self.last_capture_diagnostics: MicrophoneCaptureDiagnostics | None = None

    def cancel(self) -> None:
        self._cancelled = True
        self.recorder.cancel()
        self.session.cancel()

    def run(self) -> VoiceTurn | None:
        self._cancelled = False
        self.last_capture_diagnostics = None
        callback_frame_count = 0
        total_captured_frames = 0
        nonzero_sample_count = 0
        peak_amplitude = 0.0
        sum_squares = 0.0
        sample_count = 0
        capture_started = time.monotonic()
        capture_sample_rate = self.sample_rate
        recognizer_sample_rate = self.sample_rate
        phase_stats = {
            "initial_quiet": [0, 0, 0, 0.0, 0.0, 0],
            "speaking": [0, 0, 0, 0.0, 0.0, 0],
        }
        self.session.press()
        if self.session.state.value != "listening":
            raise VoiceBackendError("Microphone voice session did not enter listening state.")
        module = self.audio_module
        if module is None:
            try:
                module = importlib.import_module("sounddevice")
            except ImportError as exc:
                self.cancel()
                raise VoiceBackendError(
                    "Optional local microphone backend 'sounddevice' is not installed."
                ) from exc
        blocksize = max(1, self.sample_rate * self.block_ms // 1000)
        started = self.clock()
        frames = queue.Queue(maxsize=16)
        callback_status = False
        transcriber = getattr(getattr(self.session, "recognizer", None), "transcriber", None)
        start_stream = getattr(transcriber, "start_stream", None)
        accept_stream = getattr(transcriber, "accept_stream", None)

        def receive(indata, _frame_count, _stream_time, status):
            nonlocal callback_frame_count, total_captured_frames, callback_status
            nonlocal nonzero_sample_count, peak_amplitude, sum_squares, sample_count
            if status:
                callback_status = True
            try:
                block = indata.copy() if hasattr(indata, "copy") else indata
                values = tuple(_samples(block))
                phase = ("initial_quiet" if time.monotonic() - capture_started <
                         self.diagnostic_quiet_seconds else "speaking")
                stats = phase_stats[phase]
                stats[0] += 1
                stats[1] += len(values)
                stats[2] += sum(value != 0.0 for value in values)
                stats[3] = max(stats[3], max((abs(value) for value in values), default=0.0))
                stats[4] += sum(value * value for value in values)
                stats[5] += len(values)
                callback_frame_count += 1
                total_captured_frames += len(values)
                nonzero_sample_count += sum(value != 0.0 for value in values)
                peak_amplitude = max(peak_amplitude, max((abs(value) for value in values), default=0.0))
                sum_squares += sum(value * value for value in values)
                sample_count += len(values)
                frames.put_nowait(block)
            except queue.Full:
                pass

        try:
            with module.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="float32", blocksize=blocksize,
                                    callback=receive) as stream:
                raw_rate = getattr(stream, "samplerate", self.sample_rate)
                try:
                    capture_sample_rate = int(round(float(raw_rate)))
                except (TypeError, ValueError):
                    raise VoiceBackendError("Microphone backend returned an invalid sample rate.") from None
                if capture_sample_rate <= 0:
                    raise VoiceBackendError("Microphone backend returned an invalid sample rate.")
                recognizer_sample_rate = capture_sample_rate
                if callable(start_stream) and callable(accept_stream):
                    try:
                        start_stream(capture_sample_rate)
                    except Exception as exc:
                        self.cancel()
                        raise VoiceBackendError("Local speech recognizer could not start.") from exc
                capture_deadline = started + self.utterance_seconds
                frame_deadline = time.monotonic() + self.frame_timeout_seconds
                while not self._cancelled:
                    now = self.clock()
                    if now >= capture_deadline:
                        return self.session.release()
                    try:
                        data = frames.get(timeout=max(0.0, frame_deadline - time.monotonic()))
                    except queue.Empty:
                        if callback_status:
                            raise VoiceBackendError("Microphone input backend failed to deliver frames.")
                        raise VoiceBackendError("Microphone input produced no frames before the capture timeout.")
                    frame_deadline = time.monotonic() + self.frame_timeout_seconds
                    self.recorder.append(data)
                    if callable(accept_stream):
                        try:
                            accept_stream(_pcm16_bytes(data))
                        except Exception as exc:
                            raise VoiceBackendError("Local speech recognizer could not accept microphone audio.") from exc
                return None
        except KeyboardInterrupt:
            self.cancel()
            return None
        except VoiceBackendError:
            self.cancel()
            raise
        except Exception as exc:
            self.cancel()
            raise VoiceBackendError("Local microphone capture failed.") from exc
        finally:
            duration = max(0.0, time.monotonic() - capture_started)
            self.last_capture_diagnostics = MicrophoneCaptureDiagnostics(
                callback_frame_count=callback_frame_count,
                total_captured_frames=total_captured_frames,
                nonzero_sample_count=nonzero_sample_count,
                peak_amplitude=round(peak_amplitude, 9),
                rms_level=round(math.sqrt(sum_squares / sample_count), 9) if sample_count else 0.0,
                capture_duration_seconds=round(duration, 6),
                capture_sample_rate=capture_sample_rate,
                recognizer_sample_rate=recognizer_sample_rate,
                channels=1,
                pcm_encoding="pcm16le",
                capture_block_frames=blocksize,
                initial_quiet=_phase_diagnostics(phase_stats["initial_quiet"]),
                speaking=_phase_diagnostics(phase_stats["speaking"]),
            )


SoundDeviceRecognizer = SoundDeviceDoubleClapInput

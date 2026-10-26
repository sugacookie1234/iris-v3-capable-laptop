"""Local microphone double-clap listener adapted from the user's tested script.

The source's RMS calculation, microphone probe and detector tuning are retained.
Only bounded RMS levels pass from PortAudio to the worker; no audio is stored or
uploaded. Callback blocks replace blocking reads so an idle/unplugged microphone
cannot prevent lease expiry. UI ownership, cancellation, input-device validation
and invalid/overflowed-block rejection are intentional safety additions.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
import os
import queue
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from iris.voice.clap import DoubleClapDetector

SAMPLE_RATE = 44100
BLOCK_MS = 40
CHANNELS = 1
BLOCK_SAMPLES = SAMPLE_RATE * BLOCK_MS // 1000
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.001
LEASE_S = 3.0
NO_BLOCK_TIMEOUT_S = 2.0


class _Cancelled(Exception):
    pass


class _DeviceSelectionError(ValueError):
    pass


class _NoAudioBlocksError(RuntimeError):
    pass


def rms_mono(block: Any) -> float:
    """The supplied script's float64 mono RMS, with invalid-data rejection."""
    import numpy as np

    if block.ndim > 1:
        block = np.mean(block.astype(np.float64), axis=1)
    else:
        block = block.astype(np.float64)
    if block.size == 0:
        return 0.0
    level = float(np.sqrt(np.mean(block**2)))
    if not math.isfinite(level):
        raise ValueError("Microphone returned invalid audio levels.")
    return level


@contextmanager
def _level_stream(audio: Any, device: int, cancel: threading.Event,
                  rms: Callable[[Any], float], clock: Callable[[], float]):
    """Keep at most four levels, never raw audio, across the callback boundary."""
    levels: queue.Queue[tuple[float, float | None]] = queue.Queue(maxsize=4)

    def callback(data, _frames, _timing, status):
        if cancel.is_set():
            return
        try:
            level = None if getattr(status, "input_overflow", False) else rms(data)
        except Exception:
            level = math.nan
        try:
            levels.put_nowait((clock(), level))
        except queue.Full:
            # A dropped interval cannot safely join two clap hits. Discard all
            # buffered levels and let the worker reset before the next block.
            try:
                while True:
                    levels.get_nowait()
            except queue.Empty:
                pass
            try:
                levels.put_nowait((clock(), None))
            except queue.Full:
                pass

    with audio.InputStream(device=device, samplerate=SAMPLE_RATE,
                           channels=CHANNELS, dtype="float32",
                           blocksize=BLOCK_SAMPLES, callback=callback):
        yield levels


def _probe_input_max_rms(audio: Any, device: int, cancel: threading.Event,
                         alive: Callable[[], bool], clock: Callable[[], float],
                         rms: Callable[[Any], float]) -> float | None:
    if not alive():
        raise _Cancelled
    try:
        with _level_stream(audio, device, cancel, rms, clock) as levels:
            peak = 0.0
            deadline = clock() + INPUT_PROBE_S
            while clock() < deadline:
                if not alive():
                    raise _Cancelled
                try:
                    _, level = levels.get(timeout=BLOCK_MS / 1000)
                except queue.Empty:
                    continue
                if level is not None and math.isfinite(level):
                    peak = max(peak, level)
            if not alive():
                raise _Cancelled
            return peak
    except _Cancelled:
        raise
    except Exception:
        return None


def _choose_input_device(audio: Any, environment: Mapping[str, str],
                         cancel: threading.Event, alive: Callable[[], bool],
                         clock: Callable[[], float], rms: Callable[[Any], float]
                         ) -> tuple[int, str]:
    """Probe the default for 0.5 s, then scan inputs just as the source does."""
    if not alive():
        raise _Cancelled
    devices = {index: dev for index, dev in enumerate(audio.query_devices())
               if dev.get("max_input_channels", 0) >= CHANNELS}
    if not devices:
        raise _DeviceSelectionError("No microphone input devices were found.")

    def probe(index):
        return _probe_input_max_rms(audio, index, cancel, alive, clock, rms)

    def selected(index):
        if not alive():
            raise _Cancelled
        name = str(devices[index].get("name", "Microphone"))
        return index, " ".join(name.split())[:200]

    override = (environment.get("IRIS_INPUT_DEVICE") or
                environment.get("JARVIS_INPUT_DEVICE") or "").strip()
    if override:
        index = int(override) if override.isdigit() else next(
            (idx for idx, dev in devices.items()
             if override.casefold() in str(dev.get("name", "")).casefold()), -1)
        if index not in devices:
            raise _DeviceSelectionError("No microphone matches IRIS_INPUT_DEVICE or "
                                        "JARVIS_INPUT_DEVICE. Choose an input device index or name.")
        probe(index)  # Explicit choice is retained even when quiet/unopenable.
        return selected(index)

    try:
        default = audio.default.device[0]
    except (AttributeError, IndexError, TypeError):
        default = None
    if default not in devices:
        default = None
    if default is not None:
        peak = probe(default)
        if peak is not None and peak >= INPUT_SILENT_RMS:
            return selected(default)

    best_index, best_peak = None, -1.0
    for index in devices:
        if not alive():
            raise _Cancelled
        if index == default:
            continue
        peak = probe(index)
        if peak is not None and peak > best_peak:
            best_index, best_peak = index, peak
    if best_index is not None and best_peak >= INPUT_SILENT_RMS:
        return selected(best_index)
    return selected(default if default is not None else next(iter(devices)))


class NativeClapListener:
    """One UI-owned, heartbeat-leased microphone worker.

    ``update`` returns immediately, starting the worker on the first call. Poll
    at 250 ms to refresh the three-second lease. After sequence increments, send
    busy=True and then busy=False to rearm; false-only polling cannot retrigger.
    Errors remain latched until stop or expiry. No microphone is opened by the
    constructor. ``audio_backend`` and ``rms`` allow tests without audio devices.
    """

    def __init__(self, *, audio_backend=None, environment: Mapping[str, str] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rms: Callable[[Any], float] = rms_mono, lease_s: float = LEASE_S,
                 block_timeout_s: float = NO_BLOCK_TIMEOUT_S):
        if any(not math.isfinite(value) or value <= 0
               for value in (lease_s, block_timeout_s)):
            raise ValueError("Microphone timeouts must be finite and positive.")
        self._audio = audio_backend
        self._environment = os.environ if environment is None else environment
        self._clock, self._rms, self._lease_s = clock, rms, lease_s
        self._block_timeout_s = block_timeout_s
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()
        self._workers: set[threading.Thread] = set()
        self._generation = 0
        self._owner: str | None = None
        self._cancel = threading.Event()
        self._lease_until = 0.0
        self._closed = False
        self._active = self._starting = self._busy = False
        self._awaiting_busy = self._ack_busy = False
        self._reset_epoch = 0
        self._accept_after = 0.0
        self._sequence = 0
        self._error: str | None = None
        self._device: str | None = None

    @staticmethod
    def _validate_owner(owner: str) -> None:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 128:
            raise ValueError("A nonempty listener owner of at most 128 characters is required.")

    def _snapshot_locked(self) -> dict:
        return {"active": self._active, "starting": self._starting,
                "sequence": self._sequence, "error": self._error,
                "device": self._device, "sample_rate": SAMPLE_RATE,
                "block_ms": BLOCK_MS}

    def _release_locked(self) -> None:
        self._cancel.set()
        self._generation += 1
        self._owner = None
        self._active = self._starting = self._busy = False
        self._awaiting_busy = self._ack_busy = False
        self._device = self._error = None
        self._reset_epoch += 1

    def _expire_locked(self) -> None:
        if self._owner is not None and self._clock() >= self._lease_until:
            self._release_locked()

    def _alive(self, generation: int, cancel: threading.Event) -> bool:
        if cancel.is_set():
            return False
        with self._lock:
            self._expire_locked()
            return not self._closed and generation == self._generation and not cancel.is_set()

    def update(self, owner: str, busy: bool) -> dict:
        self._validate_owner(owner)
        if not isinstance(busy, bool):
            raise ValueError("Listener busy must be a boolean.")
        with self._lock:
            if self._closed:
                raise ValueError("The microphone listener is closed.")
            self._expire_locked()
            if self._owner not in (None, owner):
                raise ValueError("Double-clap standby is already owned by another IRIS window.")
            self._lease_until = self._clock() + self._lease_s
            if self._owner is None:
                self._owner = owner
                self._cancel = threading.Event()
                self._starting = True
                self._generation += 1
                worker = threading.Thread(target=self._run,
                                          args=(self._generation, self._cancel),
                                          name="iris-native-clap", daemon=True)
                self._workers.add(worker)
                worker.start()
            if busy != self._busy:
                self._reset_epoch += 1
                self._accept_after = self._clock()
            self._busy = busy
            if self._awaiting_busy:
                if busy:
                    self._ack_busy = True
                elif self._ack_busy:
                    self._awaiting_busy = self._ack_busy = False
                    self._reset_epoch += 1
                    self._accept_after = self._clock()
            return self._snapshot_locked()

    def stop(self, owner: str) -> dict:
        self._validate_owner(owner)
        with self._lock:
            self._expire_locked()
            if self._owner not in (None, owner):
                raise ValueError("Double-clap standby is owned by another IRIS window.")
            self._release_locked()
            return self._snapshot_locked()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._release_locked()
            workers = tuple(self._workers)
        # A driver may stall opening/closing. Never let it hang app shutdown;
        # stale workers are daemonized and cannot publish events or state.
        deadline = time.monotonic() + 0.25
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=max(0.0, deadline - time.monotonic()))

    def _run(self, generation: int, cancel: threading.Event) -> None:
        acquired = False
        try:
            while self._alive(generation, cancel):
                if self._capture_lock.acquire(timeout=BLOCK_MS / 1000):
                    acquired = True
                    break
            if not acquired or not self._alive(generation, cancel):
                return
            audio = self._audio
            if audio is None:
                import sounddevice as audio
            alive = lambda: self._alive(generation, cancel)
            device, name = _choose_input_device(audio, self._environment, cancel,
                                                alive, self._clock, self._rms)
            if not alive():
                return
            detector = DoubleClapDetector()  # Exact defaults from the supplied script.
            reset_epoch = -1
            last_trigger_at = -math.inf
            with _level_stream(audio, device, cancel, self._rms, self._clock) as levels:
                with self._lock:
                    if generation != self._generation or cancel.is_set():
                        return
                    self._device, self._active, self._starting = name, True, False
                last_block_at = self._clock()
                while alive():
                    try:
                        captured_at, level = levels.get(timeout=BLOCK_MS / 1000)
                    except queue.Empty:
                        if self._clock() - last_block_at >= self._block_timeout_s:
                            raise _NoAudioBlocksError(
                                "The microphone stopped delivering audio. "
                                "Reconnect it and start standby again.")
                        continue
                    last_block_at = self._clock()
                    with self._lock:
                        self._expire_locked()
                        if generation != self._generation or cancel.is_set():
                            return
                        if (reset_epoch != self._reset_epoch or self._busy or
                                self._awaiting_busy or level is None):
                            detector.reset()
                            reset_epoch = self._reset_epoch
                        if (self._busy or self._awaiting_busy or level is None or
                                captured_at < self._accept_after or
                                captured_at - last_trigger_at < detector.cooldown_s):
                            continue
                        if detector.feed_rms(level, captured_at):
                            self._sequence += 1
                            last_trigger_at = captured_at
                            self._awaiting_busy = True
                            self._ack_busy = False
        except _Cancelled:
            pass
        except Exception as exc:
            if isinstance(exc, ImportError):
                error = "Native clap listening needs sounddevice and NumPy. Run setup.bat."
            elif isinstance(exc, (_DeviceSelectionError, _NoAudioBlocksError)):
                error = str(exc)
            else:
                error = ("Could not open or read the microphone at 44,100 Hz. "
                         "Check Windows microphone access and the selected input device.")
            with self._lock:
                if generation == self._generation and not cancel.is_set():
                    self._error = error
        finally:
            if acquired:
                self._capture_lock.release()
            with self._lock:
                if generation == self._generation:
                    self._active = self._starting = False
                self._workers.discard(threading.current_thread())

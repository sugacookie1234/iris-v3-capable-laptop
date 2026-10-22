"""Opt-in double-clap gating for an existing push-to-talk VoiceSession."""
from __future__ import annotations

import math
import time
from typing import Callable
from iris.voice.session import VoiceSession, VoiceState, VoiceTurn

DEFAULT_DOUBLE_CLAP_GREETING = "Iris here. What would you like to do?"


class DoubleClapDetector:
    """Detect two bounded RMS transients after an explicit caller arm.

    This class consumes already-computed levels. It has no microphone access,
    background thread, device enumeration, or recording state.
    """

    def __init__(self, *, spike_ratio: float = 7.0, min_rms: float = 0.012,
                 min_gap_s: float = 0.05, max_gap_s: float = 0.35,
                 cooldown_s: float = 0.45, retrigger_ratio: float = 0.55,
                 noise_floor_alpha: float = 0.992, quiet_gate_mult: float = 2.2):
        values = (spike_ratio, min_rms, min_gap_s, max_gap_s, cooldown_s,
                  retrigger_ratio, noise_floor_alpha, quiet_gate_mult)
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
               for value in values):
            raise ValueError("Double-clap tuning values must be finite and positive.")
        if min_gap_s > max_gap_s or noise_floor_alpha >= 1 or retrigger_ratio >= 1:
            raise ValueError("Double-clap gap and adaptation bounds are invalid.")
        self.spike_ratio = float(spike_ratio)
        self.min_rms = float(min_rms)
        self.min_gap_s = float(min_gap_s)
        self.max_gap_s = float(max_gap_s)
        self.cooldown_s = float(cooldown_s)
        self.retrigger_ratio = float(retrigger_ratio)
        self.noise_floor_alpha = float(noise_floor_alpha)
        self.quiet_gate_mult = float(quiet_gate_mult)
        self.reset()

    def reset(self) -> None:
        self.noise_floor = 1e-4
        self._first_clap: float | None = None
        self._last_double: float = -math.inf
        self._armed = True
        self._last_time: float | None = None

    def feed_rms(self, level: float, now: float | None = None) -> bool:
        """Feed one block level and return ``True`` exactly on a double clap."""
        if not isinstance(level, (int, float)) or not math.isfinite(level) or level < 0:
            raise ValueError("Audio RMS level must be a finite non-negative number.")
        current = time.monotonic() if now is None else now
        if not isinstance(current, (int, float)) or not math.isfinite(current):
            raise ValueError("Audio timestamp must be finite.")
        if self._last_time is not None and current < self._last_time:
            raise ValueError("Audio timestamps must be monotonic.")
        self._last_time = float(current)

        quiet_gate = self.noise_floor * self.quiet_gate_mult
        if level < quiet_gate:
            self.noise_floor = max(
                1e-7,
                self.noise_floor_alpha * self.noise_floor +
                (1.0 - self.noise_floor_alpha) * level,
            )
        threshold = max(self.noise_floor * self.spike_ratio, self.min_rms)
        if level < threshold * self.retrigger_ratio:
            self._armed = True
        if not self._armed or level < threshold or current - self._last_double < self.cooldown_s:
            return False

        self._armed = False
        if self._first_clap is None:
            self._first_clap = current
            return False
        gap = current - self._first_clap
        if gap < self.min_gap_s:
            return False
        if gap <= self.max_gap_s:
            self._first_clap = None
            self._last_double = current
            return True
        self._first_clap = current
        return False


class DoubleClapPushToTalk:
    """Explicit clap gate that starts one existing VoiceSession utterance."""

    def __init__(self, session: VoiceSession, *, detector: DoubleClapDetector | None = None,
                 before_capture: Callable[[], None] | None = None):
        self.session = session
        self.detector = detector or DoubleClapDetector()
        self.before_capture = before_capture
        self._armed = False
        self._triggered = False
        self._released = False

    def arm(self) -> None:
        """Arm one caller-controlled detection window; this starts no capture."""
        if self.session.state != VoiceState.IDLE:
            raise RuntimeError(f"Cannot arm clap trigger while voice session is {self.session.state.value}.")
        self.detector.reset()
        self._armed = True
        self._triggered = False
        self._released = False

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def triggered(self) -> bool:
        return self._triggered

    def feed_rms(self, level: float, now: float) -> bool:
        """Feed one fake or host-provided block while explicitly armed."""
        if not self._armed:
            raise RuntimeError("Double-clap trigger is not armed.")
        if self._triggered:
            return False
        if not self.detector.feed_rms(level, now):
            return False
        self._armed = False
        if self.before_capture is not None:
            self.before_capture()
        self.session.press()
        if self.session.state != VoiceState.LISTENING:
            return False
        self._triggered = True
        return True

    def release(self) -> VoiceTurn | None:
        """Stop and transcribe the single utterance opened by the trigger."""
        if not self._triggered or self._released:
            return None
        self._released = True
        return self.session.release()

    def cancel(self) -> None:
        self._armed = False
        self._triggered = False
        self._released = True
        self.detector.reset()
        self.session.cancel()

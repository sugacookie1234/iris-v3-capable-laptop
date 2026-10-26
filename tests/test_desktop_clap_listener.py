"""Native clap contracts using fake devices only; never opens a real microphone."""
import math
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from iris.desktop import clap_listener as clap


def wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Timed out waiting for fake microphone worker")


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeStream:
    def __init__(self, audio, **kwargs):
        self.audio = audio
        self.kwargs = kwargs
        self.closed = False
        self.entered = threading.Event()

    def __enter__(self):
        self.entered.set()
        if self.audio.open_gate:
            self.audio.open_gate.wait(2)
        if self.audio.open_error:
            raise self.audio.open_error
        self.audio.current = self
        self.audio.live += 1
        self.audio.max_live = max(self.audio.max_live, self.audio.live)
        return self

    def __exit__(self, *_):
        self.closed = True
        self.audio.live -= 1
        if self.audio.current is self:
            self.audio.current = None

    def emit(self, level, overflow=False):
        self.kwargs["callback"](level, clap.BLOCK_SAMPLES, None,
                                SimpleNamespace(input_overflow=overflow))


class FakeAudio:
    def __init__(self):
        self.default = SimpleNamespace(device=(0, -1))
        self.devices = [{"name": "Default microphone", "max_input_channels": 1},
                        {"name": "Speakers", "max_input_channels": 0},
                        {"name": "USB microphone", "max_input_channels": 2}]
        self.streams = []
        self.current = None
        self.live = self.max_live = 0
        self.open_gate = None
        self.open_error = None

    def query_devices(self):
        return self.devices

    def InputStream(self, **kwargs):
        stream = FakeStream(self, **kwargs)
        self.streams.append(stream)
        return stream


class DeviceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.audio = FakeAudio()
        self.cancel = threading.Event()

    def choose(self, environment=None, alive=lambda: True):
        return clap._choose_input_device(self.audio, environment or {}, self.cancel,
                                          alive, time.monotonic, float)

    def test_tested_audio_parameters_and_mono_rms(self):
        import numpy as np

        self.assertEqual((clap.SAMPLE_RATE, clap.BLOCK_MS, clap.BLOCK_SAMPLES,
                          clap.CHANNELS, clap.INPUT_PROBE_S, clap.INPUT_SILENT_RMS),
                         (44100, 40, 1764, 1, 0.5, 0.001))
        self.assertAlmostEqual(clap.rms_mono(np.array([[-0.5, 0.5], [0.5, 0.5]])),
                               math.sqrt(0.125))
        self.assertEqual(clap.rms_mono(np.array([])), 0)
        with self.assertRaises(ValueError):
            clap.rms_mono(np.array([math.nan]))

    def test_tested_detector_tuning_and_too_early_clap_behavior(self):
        detector = clap.DoubleClapDetector()
        self.assertEqual((detector.spike_ratio, detector.min_rms,
                          detector.min_gap_s, detector.max_gap_s,
                          detector.cooldown_s, detector.retrigger_ratio,
                          detector.noise_floor_alpha, detector.quiet_gate_mult,
                          detector.noise_floor),
                         (7.0, 0.012, 0.05, 0.35, 0.45, 0.55, 0.992, 2.2, 1e-4))
        # The supplied script retains the first clap when another spike is too
        # early, so a third, rearmed hit inside the original window completes it.
        trace = [(0.1, 10.00), (0.001, 10.01), (0.1, 10.03),
                 (0.001, 10.04), (0.1, 10.20)]
        self.assertEqual([detector.feed_rms(level, stamp) for level, stamp in trace],
                         [False, False, False, False, True])
        detector.reset()
        for index in range(2000):
            self.assertFalse(detector.feed_rms(0.0, 20 + index * .04))
        self.assertEqual(detector.noise_floor, 1e-7)

    def test_default_active_microphone_skips_scan(self):
        with patch.object(clap, "_probe_input_max_rms", return_value=0.002) as probe:
            self.assertEqual(self.choose(), (0, "Default microphone"))
            self.assertEqual([call.args[1] for call in probe.call_args_list], [0])

    def test_silent_default_scans_inputs_only(self):
        with patch.object(clap, "_probe_input_max_rms", side_effect=[0, 0.02]) as probe:
            self.assertEqual(self.choose(), (2, "USB microphone"))
            self.assertEqual([call.args[1] for call in probe.call_args_list], [0, 2])

    def test_quiet_or_unavailable_inputs_keep_valid_default(self):
        with patch.object(clap, "_probe_input_max_rms", side_effect=[None, 0.0001]):
            self.assertEqual(self.choose()[0], 0)

    def test_missing_default_falls_back_to_first_input(self):
        self.audio.default.device = (-1, -1)
        with patch.object(clap, "_probe_input_max_rms", return_value=None):
            self.assertEqual(self.choose()[0], 0)

    def test_iris_override_has_precedence_and_quiet_choice_is_retained(self):
        with patch.object(clap, "_probe_input_max_rms", return_value=0) as probe:
            self.assertEqual(self.choose({"IRIS_INPUT_DEVICE": "2", "JARVIS_INPUT_DEVICE": "0"})[0], 2)
            self.assertEqual([call.args[1] for call in probe.call_args_list], [2])

    def test_legacy_override_matches_input_name_case_insensitively(self):
        with patch.object(clap, "_probe_input_max_rms", return_value=None):
            self.assertEqual(self.choose({"JARVIS_INPUT_DEVICE": " usb "})[0], 2)

    def test_output_only_or_unknown_override_is_rejected_without_echoing_spec(self):
        for spec in ("1", "secret-device-do-not-echo"):
            with self.subTest(spec=spec), self.assertRaises(ValueError) as caught:
                self.choose({"IRIS_INPUT_DEVICE": spec})
            self.assertNotIn(spec, str(caught.exception))
        self.assertEqual(self.audio.streams, [])

    def test_no_input_devices_reports_clear_error(self):
        self.audio.devices = [{"name": "Speakers", "max_input_channels": 0}]
        with self.assertRaisesRegex(ValueError, "No microphone input"):
            self.choose()

    def test_cancel_during_probe_does_not_scan_another_device(self):
        alive = [True]

        def probe(*args):
            alive[0] = False
            return 0

        with patch.object(clap, "_probe_input_max_rms", side_effect=probe) as mocked:
            with self.assertRaises(clap._Cancelled):
                self.choose(alive=lambda: alive[0])
            self.assertEqual(mocked.call_count, 1)

    def test_probe_uses_callback_blocks_and_cancels_without_samples(self):
        result = []

        def run():
            try:
                result.append(clap._probe_input_max_rms(
                    self.audio, 0, self.cancel, lambda: not self.cancel.is_set(),
                    time.monotonic, float))
            except clap._Cancelled:
                result.append("canceled")

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        wait_for(lambda: self.audio.current is not None)
        stream = self.audio.current
        self.assertEqual({key: stream.kwargs[key] for key in
                          ("device", "samplerate", "channels", "dtype", "blocksize")},
                         {"device": 0, "samplerate": 44100, "channels": 1,
                          "dtype": "float32", "blocksize": 1764})
        self.cancel.set()
        worker.join(0.2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["canceled"])
        self.assertTrue(stream.closed)

    def test_probe_returns_peak_without_retaining_audio(self):
        result = []
        with patch.object(clap, "INPUT_PROBE_S", 0.1):
            worker = threading.Thread(target=lambda: result.append(
                clap._probe_input_max_rms(self.audio, 0, self.cancel, lambda: True,
                                          time.monotonic, float)), daemon=True)
            worker.start()
            wait_for(lambda: self.audio.current is not None)
            for level in (0.001, 0.05, 0.002):
                self.audio.current.emit(level)
            worker.join(0.5)
        self.assertEqual(result, [0.05])
        self.assertEqual(self.audio.live, 0)


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.audio = Clock(), FakeAudio()
        self.probe = patch.object(clap, "_probe_input_max_rms", return_value=0.002)
        self.probe.start()
        self.listener = clap.NativeClapListener(audio_backend=self.audio,
                                                environment={}, clock=self.clock, rms=float)

    def tearDown(self):
        self.listener.close()
        self.probe.stop()

    def start(self, busy=False, owner="window-a"):
        self.listener.update(owner, busy)
        wait_for(lambda: self.listener.update(owner, busy)["active"])

    def state(self, busy=False):
        return self.listener.update("window-a", busy)

    def emit(self, level, delta=0.04, overflow=False):
        self.clock.advance(delta)
        self.audio.current.emit(level, overflow)
        time.sleep(0.01)  # Let the independent fake device callback drain.

    def double_clap(self):
        self.emit(0.1)
        self.emit(0.001)
        self.emit(0.1, delta=0.12)

    def test_constructor_is_inert_and_update_starts_one_worker(self):
        self.assertEqual(self.audio.streams, [])
        self.start()
        for _ in range(8):
            state = self.state()
        self.assertEqual(len(self.audio.streams), 1)
        self.assertEqual(state, {"active": True, "starting": False, "sequence": 0,
                                 "error": None, "device": "Default microphone",
                                 "sample_rate": 44100, "block_ms": 40})

    def test_trigger_emits_once_until_busy_then_idle_acknowledgment(self):
        self.start()
        self.double_clap()
        wait_for(lambda: self.state()["sequence"] == 1)
        self.clock.advance(1)
        self.double_clap()
        self.assertEqual(self.state()["sequence"], 1)
        self.state(True)
        self.state(False)
        self.double_clap()
        wait_for(lambda: self.state()["sequence"] == 2)

    def test_busy_suppression_clears_partial_hits(self):
        self.start()
        self.emit(0.1)
        self.state(True)
        self.emit(0.001)
        self.emit(0.1, delta=0.12)
        self.assertEqual(self.state(True)["sequence"], 0)
        self.state(False)
        self.emit(0.1)
        self.assertEqual(self.state()["sequence"], 0)
        self.emit(0.001)
        self.emit(0.1, delta=0.12)
        wait_for(lambda: self.state()["sequence"] == 1)

    def test_busy_ack_does_not_bypass_source_cooldown(self):
        self.start()
        self.double_clap()
        self.state(True)
        self.state(False)
        self.double_clap()
        self.assertEqual(self.state()["sequence"], 1)
        self.clock.advance(0.5)
        self.double_clap()
        wait_for(lambda: self.state()["sequence"] == 2)

    def test_overflow_breaks_partial_pair(self):
        self.start()
        self.emit(0.1)
        self.emit(0.001, overflow=True)
        self.emit(0.1, delta=0.12)
        self.assertEqual(self.state()["sequence"], 0)

    def test_lease_expires_even_when_device_stops_delivering_blocks(self):
        self.start()
        stream = self.audio.current
        self.clock.advance(3.1)
        wait_for(lambda: stream.closed)
        self.start(owner="window-b")
        self.assertEqual(self.audio.max_live, 1)
        with self.assertRaisesRegex(ValueError, "another IRIS window"):
            self.listener.stop("window-a")
        self.assertTrue(self.listener.update("window-b", False)["active"])

    def test_dead_input_reports_error_even_with_healthy_ui_heartbeat(self):
        self.start()
        self.clock.advance(2.1)
        self.state()  # Renew ownership; the microphone itself has delivered no blocks.
        wait_for(lambda: self.state()["error"] is not None)
        self.assertIn("stopped delivering audio", self.state()["error"])
        self.assertFalse(self.state()["active"])
        self.assertEqual(self.audio.live, 0)

    def test_real_silence_is_healthy_when_zero_blocks_keep_arriving(self):
        self.start()
        for _ in range(4):
            self.emit(0.0, delta=1.0)
            self.assertIsNone(self.state()["error"])
        self.assertTrue(self.state()["active"])
        self.assertEqual(self.state()["sequence"], 0)

    def test_other_window_cannot_steal_or_stop_microphone(self):
        self.start()
        for method in (lambda: self.listener.update("window-b", False),
                       lambda: self.listener.stop("window-b")):
            with self.assertRaisesRegex(ValueError, "another IRIS window"):
                method()
        self.assertTrue(self.state()["active"])

    def test_stop_releases_stream_and_preserves_monotonic_sequence(self):
        self.start()
        self.double_clap()
        stream = self.audio.current
        self.assertEqual(self.listener.stop("window-a")["sequence"], 1)
        wait_for(lambda: stream.closed)
        self.start()
        self.assertEqual(self.state()["sequence"], 1)

    def test_stale_worker_cannot_publish_after_stop_or_overlap_new_stream(self):
        gate = threading.Event()
        self.audio.open_gate = gate
        self.listener.update("window-a", False)
        wait_for(lambda: bool(self.audio.streams))
        self.audio.streams[0].entered.wait(0.5)
        begin = time.monotonic()
        self.assertFalse(self.listener.stop("window-a")["active"])
        self.assertLess(time.monotonic() - begin, 0.1)
        self.listener.update("window-b", False)
        self.assertEqual(len(self.audio.streams), 1)
        gate.set()
        wait_for(lambda: self.listener.update("window-b", False)["active"])
        self.assertTrue(self.audio.streams[0].closed)
        self.assertEqual(self.audio.max_live, 1)

    def test_errors_are_sanitized_latched_and_not_retried_by_polling(self):
        self.audio.open_error = ValueError("No microphone provider-secret-dont-echo")
        self.listener.update("window-a", False)
        wait_for(lambda: self.state()["error"] is not None)
        state = self.state()
        self.assertIn("44,100", state["error"])
        self.assertNotIn("secret", state["error"])
        for _ in range(5):
            self.state()
        self.assertEqual(len(self.audio.streams), 1)
        self.listener.stop("window-a")
        self.audio.open_error = None
        self.start()
        self.assertIsNone(self.state()["error"])

    def test_invalid_audio_fails_closed_without_exposing_sample_data(self):
        self.start()
        self.emit(math.nan)
        wait_for(lambda: self.state()["error"] is not None)
        self.assertFalse(self.state()["active"])
        self.assertEqual(self.state()["sequence"], 0)

    def test_close_is_bounded_even_when_driver_open_is_stuck(self):
        gate = threading.Event()
        self.audio.open_gate = gate
        self.listener.update("window-a", False)
        wait_for(lambda: bool(self.audio.streams))
        begin = time.monotonic()
        self.listener.close()
        self.assertLess(time.monotonic() - begin, 0.4)
        with self.assertRaisesRegex(ValueError, "closed"):
            self.state()
        gate.set()
        wait_for(lambda: self.audio.streams[0].closed)

    def test_invalid_owner_or_busy_does_not_start_microphone(self):
        for owner in (None, "", " ", "a" * 129):
            with self.assertRaises(ValueError):
                self.listener.update(owner, False)
        with self.assertRaises(ValueError):
            self.listener.update("window-a", "false")
        self.assertEqual(self.audio.streams, [])


if __name__ == "__main__":
    unittest.main()

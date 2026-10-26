from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from iris.phone.store import PhoneStore


class PhoneStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.now = 2000000.0
        self.path = Path(self.folder.name) / "phone.sqlite3"
        self.store = PhoneStore(self.path, clock=lambda: self.now)

    def enqueue(self, identifier="job", channel="sms"):
        return self.store.enqueue(identifier, channel, "opaque-session", "Private prompt")

    def ready(self, identifier="job", channel="sms"):
        self.enqueue(identifier, channel)
        self.store.claim()
        self.store.ready(identifier, "Private answer")

    def test_lifecycle_is_durable_and_delivery_is_distinct(self):
        self.ready()
        self.assertTrue(self.store.begin_send("job"))
        self.assertFalse(self.store.begin_send("job"))
        self.store.sent("job", "SM-example")
        self.store.status("SM-example", "delivered")
        self.store.status("SM-example", "queued")
        reloaded = PhoneStore(self.path)
        job = reloaded.get("job")
        self.assertEqual(job["state"], "sent")
        self.assertEqual(job["delivery"], "delivered")
        self.assertEqual(job["reply"], "Private answer")
        self.assertFalse(self.enqueue())
        self.assertEqual(reloaded.counts()["sent"], 1)
        self.assertNotIn("Private", repr(reloaded.counts()))

    def test_duplicate_enqueue_and_claim_are_atomic_across_threads(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(lambda _: self.enqueue(), range(16)))
            claimed = list(pool.map(lambda _: self.store.claim(), range(16)))
        self.assertEqual(accepted.count(True), 1)
        self.assertEqual(sum(value is not None for value in claimed), 1)
        self.assertEqual(self.store.get("job")["state"], "working")

    def test_claim_is_oldest_first_and_pending_limit_includes_working(self):
        for index in range(8):
            self.enqueue(f"job{index}")
        self.assertEqual(self.store.claim()["id"], "job0")
        with self.assertRaises(ValueError):
            self.enqueue("overflow")
        self.store.ready("job0", "answer")
        self.assertTrue(self.enqueue("new"))
        self.assertEqual(self.store.claim()["id"], "job1")

    def test_independent_channel_rate_limits_and_expiry(self):
        for channel, limit in (("sms", 20), ("voice", 60)):
            for index in range(limit):
                identifier = f"{channel}{index}"
                self.enqueue(identifier, channel)
                self.store.abort(identifier)
            self.assertFalse(self.enqueue(f"{channel}0", channel))
            with self.assertRaises(ValueError):
                self.enqueue(channel + "over", channel)
        self.now += 3601
        self.assertTrue(self.enqueue("sms-fresh"))
        self.assertTrue(self.enqueue("voice-fresh", "voice"))

    def test_opt_out_persists_suppresses_pending_and_does_not_disable_calls(self):
        self.ready("ready")
        self.enqueue("working")
        self.store.claim()
        self.enqueue("queued")
        self.store.set_opt_out(True)
        self.assertTrue(PhoneStore(self.path).opted_out())
        for identifier in ("ready", "queued"):
            self.assertEqual(self.store.get(identifier)["state"], "suppressed")
            self.assertFalse(self.store.begin_send(identifier))
        self.store.ready("working", "finished during opt-out")
        self.assertFalse(self.store.begin_send("working"))
        self.assertEqual(self.store.get("working")["state"], "suppressed")
        self.assertFalse(self.enqueue("queued"))
        with self.assertRaises(ValueError):
            self.enqueue("new-sms")
        self.ready("call", "voice")
        self.assertTrue(self.store.begin_send("call"))
        self.store.set_opt_out(False)
        self.assertTrue(self.enqueue("opted-back-in"))
        self.assertEqual(self.store.get("queued")["state"], "suppressed")

    def test_uncertain_and_abort_do_not_enable_retry_or_overwrite_sent(self):
        self.ready("uncertain")
        self.store.begin_send("uncertain")
        self.store.uncertain("uncertain")
        self.assertFalse(self.store.begin_send("uncertain"))
        self.store.sent("uncertain", "SM-late")
        self.store.abort("uncertain")
        self.assertEqual(self.store.get("uncertain")["state"], "unknown")
        self.ready("sent")
        self.store.begin_send("sent")
        self.store.sent("sent", "SM-success")
        self.store.abort("sent")
        self.store.uncertain("sent")
        self.store.ready("sent", "overwrite")
        self.assertEqual(self.store.get("sent")["reply"], "Private answer")
        self.assertEqual(self.store.get("sent")["state"], "sent")

    def test_replayed_stop_cannot_undo_newer_start_even_after_restart(self):
        self.enqueue("pending")
        self.assertTrue(self.store.apply_opt_out("SM-stop", True))
        self.assertEqual(self.store.get("pending")["state"], "suppressed")
        self.assertTrue(self.store.apply_opt_out("SM-start", False))
        reloaded = PhoneStore(self.path, clock=lambda: self.now)
        self.assertFalse(reloaded.apply_opt_out("SM-stop", True))
        self.assertFalse(reloaded.opted_out())

    def test_replayed_start_cannot_undo_newer_stop(self):
        self.assertTrue(self.store.apply_opt_out("SM-start", False))
        self.assertTrue(self.store.apply_opt_out("SM-stop", True))
        self.assertFalse(self.store.apply_opt_out("SM-start", False))
        self.assertTrue(self.store.opted_out())

    def test_control_deduplication_and_send_start_are_atomic(self):
        self.ready()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.begin_send("job"), range(16)))
            controls = list(pool.map(lambda _: self.store.apply_opt_out("SM-stop", True), range(16)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(controls.count(True), 1)

    def test_control_ids_expire_after_retention_without_resetting_consent(self):
        self.store.apply_opt_out("SM-stop", True)
        self.now += 7 * 86400 + 1
        self.store.maintenance()
        self.assertTrue(self.store.opted_out())
        self.assertTrue(self.store.apply_opt_out("SM-stop", True))

    def test_recover_fails_interrupted_work_without_resending(self):
        self.ready("sending")
        self.store.begin_send("sending")
        self.enqueue("working")
        self.store.claim()
        self.enqueue("stale")
        self.now += 121
        self.enqueue("fresh")
        self.store.recover()
        self.assertEqual(self.store.get("sending")["state"], "unknown")
        self.assertEqual(self.store.get("working")["state"], "failed")
        self.assertEqual(self.store.get("stale")["state"], "failed")
        self.assertEqual(self.store.claim()["id"], "fresh")
        self.assertIsNone(self.store.claim())

    def test_retention_clears_bodies_then_deletes_records_but_keeps_opt_out(self):
        self.ready()
        self.store.register_call("CA-old")
        self.store.set_opt_out(True)
        self.now += 86401
        self.store.maintenance()
        job = self.store.get("job")
        self.assertEqual(job["prompt"], "")
        self.assertEqual(job["reply"], "")
        self.assertFalse(self.store.register_call("CA-old"))
        self.now += 6 * 86400
        self.store.maintenance()
        self.assertIsNone(self.store.get("job"))
        self.assertTrue(self.store.register_call("CA-old"))
        self.assertTrue(self.store.opted_out())

    def test_call_limit_is_durable_and_duplicates_do_not_consume_quota(self):
        for index in range(10):
            self.assertTrue(self.store.register_call(f"CA{index}"))
            self.assertFalse(self.store.register_call(f"CA{index}"))
        with self.assertRaises(ValueError):
            PhoneStore(self.path, clock=lambda: self.now).register_call("CA-over")
        self.now += 3601
        self.assertTrue(self.store.register_call("CA-new"))

    def test_unknown_callbacks_are_ignored_and_invalid_states_are_rejected(self):
        self.store.status("SM-unknown", "delivered")
        with self.assertRaises(ValueError):
            self.store.status("SM-unknown", "success-and-send-more")
        self.assertEqual(sum(self.store.counts().values()), 0)

    def test_invalid_metadata_content_and_transition_inputs_are_rejected(self):
        for args in [("", "sms", "session", "text"), ("id", "email", "session", "text"),
                     ("id", "sms", "+15551234567", "text"), ("id", "sms", "session", ""),
                     ("id", "sms", "session", "x" * 2001)]:
            with self.assertRaises(ValueError):
                self.store.enqueue(*args)
        with self.assertRaises(ValueError):
            self.store.set_opt_out("false")
        with self.assertRaises(ValueError):
            self.store.ready("id", "x" * 4001)
        self.assertIsNone(self.store.get("missing"))
        self.assertFalse(self.store.begin_send("missing"))


if __name__ == "__main__":
    unittest.main()

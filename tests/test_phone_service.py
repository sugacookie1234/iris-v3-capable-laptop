from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import unittest
from unittest.mock import Mock
from xml.etree import ElementTree

from iris.phone.config import PhoneConfig
from iris.phone.service import EMPTY, FAILURE, PhoneService
from iris.phone.store import PhoneStore


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def message_sid(number=1):
    return "SM" + f"{number:032x}"


def call_sid(number=1):
    return "CA" + f"{number:032x}"


def document(payload):
    return ElementTree.fromstring(payload)


def action_path(payload):
    return urlsplit(document(payload).find("Gather").attrib["action"]).path


class PhoneServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="iris-phone-test-")
        self.addCleanup(self.directory.cleanup)
        self.clock = Clock()
        self.config = PhoneConfig(
            enabled=True, account_sid="AC" + "a" * 32, auth_token="synthetic-private-token",
            voice_pin="873215", from_number="+14165550101", owner_number="+14165550102",
            public_url="https://iris-phone.example.com",
        )
        self.store = PhoneStore(Path(self.directory.name) / "phone.sqlite3", clock=self.clock)
        self.assistant = Mock()
        self.assistant.reply.return_value = "Hello from Iris."
        self.transport = Mock()
        self.transport.send_sms.return_value = message_sid(500)
        self.service = PhoneService(self.config, self.store, self.assistant, self.transport, clock=self.clock)
        self.addCleanup(self.service.close)

    def sms(self, text, number=1, **extra):
        return self.service.handle("/phone/sms", {"MessageSid": message_sid(number), "Body": text, **extra})

    def unlock(self, number=1):
        sid = call_sid(number)
        prompt = self.service.handle("/phone/voice", {"CallSid": sid})
        return self.service.handle(action_path(prompt), {"CallSid": sid, "Digits": self.config.voice_pin})

    def voice_request(self, text="What time is it?", number=1):
        greeting = self.unlock(number)
        path = action_path(greeting)
        wait = self.service.handle(path, {"CallSid": call_sid(number), "SpeechResult": text})
        poll = urlsplit(document(wait).find("Redirect").text).path
        return path, poll, wait

    def test_incoming_sms_acknowledges_before_any_assistant_or_provider_work(self):
        self.assertEqual(self.sms("Hello"), EMPTY)
        self.assistant.reply.assert_not_called()
        self.transport.send_sms.assert_not_called()
        self.assertIsNone(self.service.worker)
        self.assertEqual(self.store.get("sms:" + message_sid())["state"], "queued")
        self.assertTrue(self.service.work_once())
        self.assistant.reply.assert_called_once_with("Hello", history=(), channel="sms")
        self.transport.send_sms.assert_called_once_with("Hello from Iris.")
        self.assertEqual(self.store.get("sms:" + message_sid())["state"], "sent")
        self.assertFalse(self.service.work_once())

    def test_duplicate_message_sid_queues_and_answers_original_message_once(self):
        self.sms("Original text")
        self.sms("Changed duplicate text")
        self.assertEqual(self.store.counts()["queued"], 1)
        self.service.work_once()
        self.sms("Original text")
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_called_once_with("Original text", history=(), channel="sms")
        self.transport.send_sms.assert_called_once()

    def test_stop_cancels_queued_reply_and_start_allows_new_messages(self):
        self.sms("Queued before stop")
        self.assertEqual(self.sms("STOP", number=2), EMPTY)
        self.assertTrue(self.store.opted_out())
        self.assertEqual(self.store.get("sms:" + message_sid())["state"], "suppressed")
        self.assertFalse(self.service.work_once())
        self.sms("Ignored while opted out", number=3)
        self.assertIsNone(self.store.get("sms:" + message_sid(3)))
        self.assistant.reply.assert_not_called()
        self.transport.send_sms.assert_not_called()
        self.assertEqual(self.sms("START", number=4), EMPTY)
        self.assertFalse(self.store.opted_out())
        self.sms("New message after start", number=5)
        self.service.work_once()
        self.assistant.reply.assert_called_once_with("New message after start", history=(), channel="sms")
        self.transport.send_sms.assert_called_once()

    def test_stop_received_while_assistant_works_prevents_paid_reply(self):
        self.sms("Slow request")

        def reply(*args, **kwargs):
            self.sms("STOP", number=2)
            return "This answer must not be sent."

        self.assistant.reply.side_effect = reply
        self.service.work_once()
        self.assertEqual(self.store.get("sms:" + message_sid())["state"], "suppressed")
        self.transport.send_sms.assert_not_called()

    def test_provider_optout_metadata_and_help_do_not_trigger_paid_replies(self):
        self.sms("localized opt-out text", OptOutType="STOP")
        self.assertTrue(self.store.opted_out())
        self.sms("localized opt-in text", number=2, OptOutType="START")
        self.assertFalse(self.store.opted_out())
        self.sms("HELP", number=3)
        self.sms("localized help text", number=4, OptOutType="HELP")
        self.assertFalse(self.service.work_once())
        self.transport.send_sms.assert_not_called()

    def test_delayed_optout_control_retry_cannot_reverse_newer_choice(self):
        self.sms("STOP", number=1)
        self.sms("START", number=2)
        self.sms("STOP", number=1)
        self.assertFalse(self.store.opted_out())
        self.sms("REVOKE", number=3)
        self.sms("START", number=2)
        self.assertTrue(self.store.opted_out())
        self.assertFalse(self.service.work_once())

    def test_blank_oversized_or_media_messages_are_acknowledged_without_work(self):
        for number, text, extra in ((1, "  ", {}), (2, "x" * 2001, {}),
                                    (3, "Photo", {"NumMedia": "1"})):
            self.assertEqual(self.sms(text, number, **extra), EMPTY)
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_not_called()

    def test_assistant_exception_produces_fixed_reply_without_private_exception(self):
        self.assistant.reply.side_effect = RuntimeError("secret-provider-token private prompt")
        self.sms("Hello")
        self.assertTrue(self.service.work_once())
        self.transport.send_sms.assert_called_once_with(FAILURE)
        self.assertEqual(self.store.get("sms:" + message_sid())["reply"], FAILURE)

    def test_ambiguous_send_is_never_retried_including_after_restart(self):
        self.transport.send_sms.side_effect = TimeoutError("private number and text")
        self.sms("Send once")
        self.service.work_once()
        job_id = "sms:" + message_sid()
        self.assertEqual(self.store.get(job_id)["state"], "unknown")
        self.assertFalse(self.service.work_once())
        self.service.close()
        reopened_store = PhoneStore(self.store.path, clock=self.clock)
        reopened_store.recover()
        resumed = PhoneService(self.config, reopened_store, self.assistant, self.transport, clock=self.clock)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.handle("/phone/sms", {"MessageSid": message_sid(), "Body": "Send once"}), EMPTY)
        self.assertFalse(resumed.work_once())
        self.transport.send_sms.assert_called_once()
        self.assistant.reply.assert_called_once()
        self.assertEqual(reopened_store.get(job_id)["state"], "unknown")

    def test_voice_requires_pin_before_speech_or_assistant_work(self):
        pin_prompt = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        gather = document(pin_prompt).find("Gather")
        self.assertEqual(gather.attrib["input"], "dtmf")
        self.assertEqual(gather.attrib["numDigits"], "6")
        self.assertRegex(action_path(pin_prompt), r"^/phone/voice/unlock/[A-Za-z0-9_-]{32}$")
        self.assertEqual(gather.attrib["method"], "POST")
        rejected = self.service.handle("/phone/voice/turn/" + "a" * 32,
                                       {"CallSid": call_sid(), "SpeechResult": "Answer before PIN"})
        self.assertIsNotNone(document(rejected).find("Hangup"))
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_not_called()

    def test_three_wrong_pin_attempts_cannot_be_reset_by_repeated_voice_callback(self):
        result = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        for attempt in range(3):
            unlock_path = action_path(result)
            result = self.service.handle(unlock_path, {"CallSid": call_sid(), "Digits": "111111"})
            if attempt < 2:
                self.assertIsNotNone(document(result).find("Gather"))
        self.assertIsNone(document(result).find("Gather"))
        self.assertIsNotNone(document(result).find("Hangup"))
        repeated = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        repeated_path = action_path(repeated) if document(repeated).find("Gather") is not None else unlock_path
        rejected = self.service.handle(repeated_path, {"CallSid": call_sid(), "Digits": self.config.voice_pin})
        self.assertIsNone(document(rejected).find("Gather"))
        self.assertIsNotNone(document(rejected).find("Hangup"))
        self.assistant.reply.assert_not_called()

    def test_successful_pin_has_fresh_speech_token_and_duplicate_unlock_is_stable(self):
        pin_prompt = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        unlock_path = action_path(pin_prompt)
        greeting = self.service.handle(unlock_path, {"CallSid": call_sid(), "Digits": self.config.voice_pin})
        gather = document(greeting).find("Gather")
        self.assertEqual(gather.attrib["input"], "speech")
        self.assertEqual(gather.attrib["language"], "en-CA")
        self.assertRegex(action_path(greeting), r"^/phone/voice/turn/[A-Za-z0-9_-]{32}$")
        duplicate = self.service.handle(unlock_path, {"CallSid": call_sid(), "Digits": "111111"})
        self.assertEqual(greeting, duplicate)
        self.assertNotEqual(action_path(greeting), action_path(self.unlock(number=2)))

    def test_retried_failed_pin_nonce_counts_as_one_attempt(self):
        prompt = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        unlock_path = action_path(prompt)
        first = self.service.handle(unlock_path, {"CallSid": call_sid(), "Digits": "111111"})
        self.assertNotEqual(action_path(first), unlock_path)
        for _ in range(4):
            duplicate = self.service.handle(unlock_path, {"CallSid": call_sid(), "Digits": "111111"})
            self.assertEqual(first, duplicate)
        self.assertEqual(self.service.calls[call_sid()].attempts, 1)
        accepted = self.service.handle(action_path(first), {"CallSid": call_sid(), "Digits": self.config.voice_pin})
        self.assertEqual(document(accepted).find("Gather").attrib["input"], "speech")

    def test_voice_ack_then_worker_then_cached_poll_with_new_turn_nonce(self):
        turn, poll, wait = self.voice_request("Tell me something")
        self.assistant.reply.assert_not_called()
        self.assertEqual(document(wait).find("Pause").attrib["length"], "2")
        waiting_again = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertIsNotNone(document(waiting_again).find("Redirect"))
        self.assertTrue(self.service.work_once())
        self.assistant.reply.assert_called_once_with("Tell me something", history=(), channel="voice")
        response = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertEqual(document(response).find("Gather/Say").text, "Hello from Iris.")
        self.assertNotEqual(action_path(response), turn)
        self.assertEqual(response, self.service.handle(poll, {"CallSid": call_sid()}))
        self.assertFalse(self.service.work_once())
        self.transport.send_sms.assert_not_called()
        self.transport.call.assert_not_called()

    def test_duplicate_speech_event_does_not_generate_a_second_answer(self):
        turn, poll, _ = self.voice_request("Original speech")
        self.service.handle(turn, {"CallSid": call_sid(), "SpeechResult": "Changed duplicate"})
        self.assertEqual(self.store.counts()["queued"], 1)
        self.service.work_once()
        result = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertEqual(result, self.service.handle(turn, {"CallSid": call_sid(), "SpeechResult": "Another retry"}))
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_called_once_with("Original speech", history=(), channel="voice")

    def test_tokens_and_replies_are_isolated_to_their_call(self):
        turn, poll, _ = self.voice_request("Private answer")
        self.unlock(number=2)
        for path in (turn, poll, "/phone/voice/turn/" + "z" * 32):
            rejected = self.service.handle(path, {"CallSid": call_sid(2), "SpeechResult": "Steal answer"})
            self.assertIsNotNone(document(rejected).find("Hangup"))
            self.assertIsNone(document(rejected).find("Gather"))
        self.service.work_once()
        own_reply = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertIsNotNone(document(own_reply).find("Gather"))
        self.assistant.reply.assert_called_once_with("Private answer", history=(), channel="voice")

    def test_assistant_xml_is_spoken_as_literal_text_not_call_instructions(self):
        answer = 'Hello </Say><Dial>+19995550000</Dial><Say> & "friend"'
        self.assistant.reply.return_value = answer
        _, poll, _ = self.voice_request()
        self.service.work_once()
        root = document(self.service.handle(poll, {"CallSid": call_sid()}))
        self.assertEqual(root.find("Gather/Say").text, answer)
        self.assertEqual(list(root.iter("Dial")), [])
        self.assertEqual([node.tag for node in root], ["Gather", "Hangup"])

    def test_voice_provider_exception_uses_fixed_failure_reply(self):
        self.assistant.reply.side_effect = RuntimeError("private error body with credentials")
        _, poll, _ = self.voice_request()
        self.service.work_once()
        reply = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertEqual(document(reply).find("Gather/Say").text, FAILURE)
        self.assertNotIn(b"credentials", reply)

    def test_call_has_twelve_turn_limit_without_thirteenth_assistant_call(self):
        greeting = self.unlock()
        for number in range(12):
            wait = self.service.handle(action_path(greeting), {"CallSid": call_sid(), "SpeechResult": f"Question {number}"})
            poll = urlsplit(document(wait).find("Redirect").text).path
            self.assertTrue(self.service.work_once())
            greeting = self.service.handle(poll, {"CallSid": call_sid()})
        end = self.service.handle(action_path(greeting), {"CallSid": call_sid(), "SpeechResult": "Question 13"})
        self.assertIsNotNone(document(end).find("Hangup"))
        self.assertIsNone(document(end).find("Gather"))
        self.assertFalse(self.service.work_once())
        self.assertEqual(self.assistant.reply.call_count, 12)

    def test_expired_call_cannot_reopen_with_replayed_callback(self):
        greeting = self.unlock()
        self.clock.now += 901
        rejected = self.service.handle(action_path(greeting), {"CallSid": call_sid(), "SpeechResult": "Too late"})
        self.assertIsNotNone(document(rejected).find("Hangup"))
        reopened = self.service.handle("/phone/voice", {"CallSid": call_sid()})
        self.assertIsNotNone(document(reopened).find("Hangup"))
        self.assertIsNone(document(reopened).find("Gather"))
        self.assertFalse(self.service.work_once())

    def test_queued_voice_work_is_aborted_when_call_expires_before_worker(self):
        self.voice_request("Request that will expire")
        self.clock.now += 901
        self.assertTrue(self.service.work_once())
        self.assistant.reply.assert_not_called()
        self.assertEqual(self.store.counts()["failed"], 1)
        self.assertNotIn(call_sid(), self.service.histories)

    def test_call_completed_during_generation_does_not_recreate_history_or_reply(self):
        _, poll, _ = self.voice_request("Slow request")

        def reply(*args, **kwargs):
            self.service.handle("/phone/status", {"CallSid": call_sid(), "CallStatus": "completed"})
            return "Private answer after the call ended."

        self.assistant.reply.side_effect = reply
        self.assertTrue(self.service.work_once())
        self.assertEqual(self.store.counts()["failed"], 1)
        self.assertNotIn(call_sid(), self.service.histories)
        rejected = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertIsNotNone(document(rejected).find("Hangup"))
        self.assertIsNone(document(rejected).find("Gather"))

    def test_call_expiring_during_generation_does_not_store_ready_answer(self):
        self.voice_request("Slow request")

        def reply(*args, **kwargs):
            self.clock.now += 901
            return "Answer after call expiry."

        self.assistant.reply.side_effect = reply
        self.assertTrue(self.service.work_once())
        self.assertEqual(self.store.counts()["failed"], 1)
        self.assertNotIn(call_sid(), self.service.histories)

    def test_poll_timeout_aborts_work_and_replays_one_failure_response(self):
        _, poll, _ = self.voice_request()
        self.clock.now += 91
        result = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertEqual(document(result).find("Gather/Say").text, FAILURE)
        self.assertEqual(result, self.service.handle(poll, {"CallSid": call_sid()}))
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_not_called()

    def test_poll_timeout_during_generation_does_not_add_unheard_answer_to_history(self):
        _, poll, _ = self.voice_request("Slow question")

        def reply(*args, **kwargs):
            self.clock.now += 91
            failure = self.service.handle(poll, {"CallSid": call_sid()})
            self.assertEqual(document(failure).find("Gather/Say").text, FAILURE)
            return "This answer arrived after its turn timed out."

        self.assistant.reply.side_effect = reply
        self.assertTrue(self.service.work_once())
        self.assertEqual(self.store.counts()["failed"], 1)
        self.assertNotIn(call_sid(), self.service.histories)

    def test_call_completion_removes_access_to_cached_private_reply(self):
        _, poll, _ = self.voice_request()
        self.service.work_once()
        self.service.handle(poll, {"CallSid": call_sid()})
        self.assertEqual(self.service.handle("/phone/status", {"CallSid": call_sid(), "CallStatus": "completed"}), EMPTY)
        rejected = self.service.handle(poll, {"CallSid": call_sid()})
        self.assertIsNotNone(document(rejected).find("Hangup"))
        self.assertIsNone(document(rejected).find("Gather"))
        self.assertNotIn(call_sid(), self.service.histories)

    def test_goodbye_finishes_without_queuing_or_calling_assistant(self):
        greeting = self.unlock()
        goodbye = self.service.handle(action_path(greeting), {"CallSid": call_sid(), "SpeechResult": "Goodbye!"})
        self.assertEqual(document(goodbye).find("Say").text, "Goodbye.")
        self.assertIsNotNone(document(goodbye).find("Hangup"))
        self.assertFalse(self.service.work_once())
        self.assistant.reply.assert_not_called()


if __name__ == "__main__":
    unittest.main()

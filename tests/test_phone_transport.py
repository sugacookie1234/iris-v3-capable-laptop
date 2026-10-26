import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree

from iris.phone.config import PhoneConfig, PhoneDisabled
from iris.phone.transport import TransportError, TwilioTransport


def phone_config():
    return PhoneConfig(
        enabled=True, account_sid="AC" + "a" * 32, auth_token="synthetic-private-phone-token",
        voice_pin="873215", from_number="+14165550101", owner_number="+14165550102",
        public_url="https://iris-phone.example.com",
    )


class PhoneTransportTests(unittest.TestCase):
    def setUp(self):
        self.config = phone_config()
        self.client = Mock()
        self.client.messages.create.return_value = SimpleNamespace(sid="SM" + "b" * 32)
        self.client.calls.create.return_value = SimpleNamespace(sid="CA" + "c" * 32)
        self.transport = TwilioTransport(self.config, client=self.client)

    def test_sms_only_targets_saved_owner_with_signed_status_endpoint(self):
        sid = self.transport.send_sms("  Hello\r\nIRIS  ")
        self.assertEqual(sid, "SM" + "b" * 32)
        self.client.messages.create.assert_called_once_with(
            to=self.config.owner_number, from_=self.config.from_number, body="Hello\nIRIS",
            status_callback="https://iris-phone.example.com/phone/status")
        self.client.calls.create.assert_not_called()

    def test_call_is_escaped_spoken_notification_with_hangup_and_limits(self):
        message = 'Hello <Dial>+19995550000</Dial> & "IRIS"'
        sid = self.transport.call(message)
        self.assertEqual(sid, "CA" + "c" * 32)
        self.client.calls.create.assert_called_once()
        args = self.client.calls.create.call_args.kwargs
        xml = ElementTree.fromstring(args.pop("twiml"))
        self.assertEqual(xml.tag, "Response")
        self.assertEqual([node.tag for node in xml], ["Say", "Hangup"])
        self.assertEqual(xml[0].attrib, {"voice": "man", "language": "en-US"})
        self.assertEqual(xml[0].text, message)
        self.assertEqual(args, {
            "to": self.config.owner_number, "from_": self.config.from_number,
            "timeout": 20, "time_limit": 120,
            "status_callback": "https://iris-phone.example.com/phone/status",
            "status_callback_event": ["completed"], "status_callback_method": "POST",
        })
        self.client.messages.create.assert_not_called()

    def test_methods_cannot_override_recipient(self):
        for method in (self.transport.send_sms, self.transport.call):
            with self.assertRaises(TypeError):
                method("message", to="+14165550103")
            with self.assertRaises(TypeError):
                method("message", "+14165550103")
        self.client.messages.create.assert_not_called()
        self.client.calls.create.assert_not_called()

    def test_invalid_or_oversized_text_never_reaches_provider(self):
        for method, limit in ((self.transport.send_sms, 700), (self.transport.call, 400)):
            for value in (None, 4, "", " \n\r ", "x" * (limit + 1), "secret\x00text",
                          "secret\ttext", "secret\x7ftext", "secret\x85text", "secret\ud800text",
                          "secret\ufffetext", "secret\ufffftext"):
                with self.subTest(method=method.__name__, kind=type(value).__name__), self.assertRaises(ValueError) as raised:
                    method(value)
                if isinstance(value, str) and value:
                    self.assertNotIn(value, str(raised.exception))
        self.client.messages.create.assert_not_called()
        self.client.calls.create.assert_not_called()

    def test_unicode_and_exact_length_limits_are_supported(self):
        self.transport.send_sms("é" * 700)
        self.transport.call("🌤" * 400)
        self.assertEqual(len(self.client.messages.create.call_args.kwargs["body"]), 700)
        xml = ElementTree.fromstring(self.client.calls.create.call_args.kwargs["twiml"])
        self.assertEqual(len(xml[0].text), 400)

    def test_provider_failure_is_sanitized_without_automatic_retry(self):
        private = f"{self.config.auth_token} {self.config.owner_number} confidential body"
        for method, resource in ((self.transport.send_sms, self.client.messages),
                                 (self.transport.call, self.client.calls)):
            for error in (TimeoutError(private), ConnectionError(private), RuntimeError(private)):
                resource.create.reset_mock()
                resource.create.side_effect = error
                with self.assertRaises(TransportError) as raised:
                    method("confidential body")
                self.assertEqual(str(raised.exception),
                                 "Phone provider did not confirm acceptance. Check Twilio before retrying.")
                self.assertNotIn(private, repr(raised.exception))
                self.assertTrue(raised.exception.__suppress_context__)
                self.assertEqual(resource.create.call_count, 1)

    def test_malformed_acceptance_sid_is_not_reported_as_accepted(self):
        for method, resource in ((self.transport.send_sms, self.client.messages),
                                 (self.transport.call, self.client.calls)):
            for response in (None, SimpleNamespace(), SimpleNamespace(sid=None),
                             SimpleNamespace(sid="secret-invalid-sid"), SimpleNamespace(sid="AC" + "a" * 32)):
                resource.create.return_value = response
                with self.assertRaises(TransportError):
                    method("Hello")

    def test_disabled_configuration_cannot_construct_a_sender(self):
        with self.assertRaises(PhoneDisabled):
            TwilioTransport(PhoneConfig(), client=self.client)
        self.client.messages.create.assert_not_called()
        self.client.calls.create.assert_not_called()

    def test_injected_client_does_not_require_sdk_import(self):
        with patch.dict(sys.modules, {"twilio.rest": None, "twilio.http.http_client": None}):
            transport = TwilioTransport(self.config, client=self.client)
            self.assertEqual(transport.send_sms("Hello"), "SM" + "b" * 32)

    def test_default_sdk_client_uses_timeout_and_disables_retries_without_sending(self):
        rest = ModuleType("twilio.rest")
        http = ModuleType("twilio.http.http_client")
        rest.Client = Mock(return_value=self.client)
        http.TwilioHttpClient = Mock()
        with patch.dict(sys.modules, {"twilio.rest": rest, "twilio.http.http_client": http}):
            TwilioTransport(self.config)
        http.TwilioHttpClient.assert_called_once_with(timeout=10, max_retries=0)
        rest.Client.assert_called_once_with(
            self.config.account_sid, self.config.auth_token,
            http_client=http.TwilioHttpClient.return_value)
        self.client.messages.create.assert_not_called()
        self.client.calls.create.assert_not_called()

    def test_missing_sdk_has_fixed_error_without_exposing_configuration(self):
        with patch.dict(sys.modules, {"twilio.rest": None, "twilio.http.http_client": None}):
            with self.assertRaises(TransportError) as raised:
                TwilioTransport(self.config)
        self.assertEqual(str(raised.exception),
                         "Phone provider did not confirm acceptance. Check Twilio before retrying.")


if __name__ == "__main__":
    unittest.main()

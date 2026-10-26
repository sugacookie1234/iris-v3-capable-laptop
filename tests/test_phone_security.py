from dataclasses import FrozenInstanceError, replace
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from iris.phone.config import PhoneConfig, PhoneDisabled, from_environment
from iris.phone.security import validate_callback


def phone_settings(**extra):
    return {
        "IRIS_PHONE_ENABLED": "true",
        "IRIS_TWILIO_ACCOUNT_SID": "AC" + "a" * 32,
        "IRIS_TWILIO_AUTH_TOKEN": "synthetic-private-phone-token",
        "IRIS_PHONE_PIN": "873215",
        "IRIS_PHONE_NUMBER": "+14165550101",
        "IRIS_OWNER_PHONE_NUMBER": "+14165550102",
        "IRIS_PHONE_PUBLIC_URL": "https://iris-phone.example.com",
        **extra,
    }


class PhoneConfigTests(unittest.TestCase):
    def test_requires_explicit_opt_in_without_reading_other_values(self):
        for setting in ({}, {"IRIS_PHONE_ENABLED": "false"},
                        {"IRIS_PHONE_ENABLED": "", "IRIS_TWILIO_AUTH_TOKEN": object()}):
            with self.subTest(setting=tuple(setting)), self.assertRaises(PhoneDisabled):
                from_environment(setting)
        for value in ("yes", "1", "enabled", True, "true\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                from_environment(phone_settings(IRIS_PHONE_ENABLED=value))

    def test_valid_configuration_is_frozen_and_private_values_are_not_repr(self):
        config = from_environment(phone_settings())
        self.assertTrue(config.enabled)
        self.assertEqual(config.port, 8767)
        self.assertEqual(config, PhoneConfig.from_environment(phone_settings()))
        for value in (config.auth_token, config.voice_pin, config.from_number, config.owner_number):
            self.assertNotIn(value, repr(config))
        with self.assertRaises(FrozenInstanceError):
            config.auth_token = "replacement"

    def test_identifiers_and_secret_failures_never_echo_values(self):
        invalid = {
            "IRIS_TWILIO_ACCOUNT_SID": ("SK" + "a" * 32, "AC" + "z" * 32, "secret-account-id"),
            "IRIS_TWILIO_AUTH_TOKEN": ("secret token", "private\ntoken", "x" * 257, ""),
            "IRIS_PHONE_PIN": ("12345", "1234567", "１２３４５６", "123 45", "secret-pin"),
            "IRIS_PHONE_NUMBER": ("4165550101", "+04165550101", "+14165550101 ext 2", "+" + "1" * 16),
            "IRIS_OWNER_PHONE_NUMBER": ("private-number", "+1 416 555 0102", "+1\n4165550102"),
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, length=len(value)), self.assertRaises(ValueError) as raised:
                    from_environment(phone_settings(**{key: value}))
                if value:
                    self.assertNotIn(value, str(raised.exception))

    def test_missing_required_values_rejected(self):
        for key in ("IRIS_TWILIO_ACCOUNT_SID", "IRIS_TWILIO_AUTH_TOKEN", "IRIS_PHONE_PIN",
                    "IRIS_PHONE_NUMBER", "IRIS_OWNER_PHONE_NUMBER", "IRIS_PHONE_PUBLIC_URL"):
            settings = phone_settings()
            del settings[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                from_environment(settings)

    def test_same_number_rejected_to_prevent_reply_loops(self):
        with self.assertRaises(ValueError):
            from_environment(phone_settings(IRIS_OWNER_PHONE_NUMBER="+14165550101"))

    def test_public_origin_preserves_authority_and_removes_trailing_slash(self):
        for value, expected in (("https://iris-phone.example.com/", "https://iris-phone.example.com"),
                                ("https://iris-phone.example.com:8443/", "https://iris-phone.example.com:8443"),
                                ("https://8.8.8.8", "https://8.8.8.8")):
            with self.subTest(value=value):
                config = from_environment(phone_settings(IRIS_PHONE_PUBLIC_URL=value))
                self.assertEqual(config.public_url, expected)

    def test_non_public_or_ambiguous_origins_rejected_without_echo(self):
        invalid = (
            "http://iris-phone.example.com", "https://secret:password@iris-phone.example.com",
            "https://iris-phone.example.com/phone", "https://iris-phone.example.com/?secret=abc",
            "https://iris-phone.example.com/#secret", "https://iris-phone.example.com?",
            "https://iris-phone.example.com#", "https://iris-phone.example.com:",
            "https://iris-phone.example.com:0", "https://iris-phone.example.com:65536",
            "https://localhost", "https://sub.localhost", "https://machine.local", "https://machine.lan",
            "https://127.0.0.1", "https://10.0.0.1", "https://172.16.4.3", "https://192.168.1.1",
            "https://169.254.1.1", "https://[::1]", "https://[fd12::1]", "https://[fe80::1]",
            "https://224.0.0.1", "https://0.0.0.0", "https://127.1", "https://2130706433",
            "https://0x7f.0.0.1", "https://example.com.", "https://bad_host.example.com",
            "https://example.com\n", "https://example.com\\@127.0.0.1", "https://%31%32%37.0.0.1",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError) as raised:
                from_environment(phone_settings(IRIS_PHONE_PUBLIC_URL=value))
            self.assertNotIn(value, str(raised.exception))

    def test_listener_port_cannot_reuse_desktop_or_privileged_port(self):
        for value in ("0", "80", "1023", "8766", "65536", "-1", "1.0", "+8767", " 8767", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                from_environment(phone_settings(IRIS_PHONE_PORT=value))
        for value in ("1024", "8767", "65535"):
            self.assertEqual(from_environment(phone_settings(IRIS_PHONE_PORT=value)).port, int(value))
        with self.assertRaises(ValueError):
            replace(from_environment(phone_settings()), port=True)


class PhoneCallbackTests(unittest.TestCase):
    def setUp(self):
        self.config = from_environment(phone_settings())
        self.form = {
            "AccountSid": self.config.account_sid, "From": self.config.owner_number,
            "To": self.config.from_number, "Body": "Hello IRIS", "MessageSid": "SM" + "b" * 32,
        }
        self.validator = Mock()
        self.validator.validate.return_value = True
        self.factory = Mock(return_value=self.validator)
        self.module = ModuleType("twilio.request_validator")
        self.module.RequestValidator = self.factory
        self.patch = patch.dict(sys.modules, {"twilio.request_validator": self.module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_uses_configured_origin_exact_path_and_all_form_fields(self):
        self.form["FutureTwilioField"] = "future value"
        self.assertTrue(validate_callback(self.config, "/phone/sms", self.form, "signature"))
        self.factory.assert_called_once_with(self.config.auth_token)
        self.validator.validate.assert_called_once_with(
            self.config.public_url + "/phone/sms", self.form, "signature")

    def test_signature_failure_and_sdk_failures_reject(self):
        self.validator.validate.return_value = False
        self.assertFalse(validate_callback(self.config, "/phone/sms", self.form, "signature"))
        for error in (ValueError, TypeError, UnicodeError, ImportError):
            self.validator.validate.side_effect = error("private details")
            self.assertFalse(validate_callback(self.config, "/phone/sms", self.form, "signature"))

    def test_disabled_bridge_rejects_even_signed_callbacks(self):
        self.assertFalse(validate_callback(PhoneConfig(), "/phone/sms", self.form, "signature"))
        self.factory.assert_not_called()

    def test_wrong_account_or_participants_rejected_before_sdk(self):
        for key, value in (("AccountSid", "AC" + "b" * 32), ("From", "+14165550103"),
                           ("From", "anonymous"), ("To", "+14165550103"), ("To", "")):
            with self.subTest(key=key, value=value):
                self.assertFalse(validate_callback(self.config, "/phone/sms", {**self.form, key: value}, "signature"))
        self.factory.assert_not_called()

    def test_outbound_number_direction_only_allowed_for_status(self):
        outbound = {**self.form, "From": self.config.from_number, "To": self.config.owner_number}
        self.assertTrue(validate_callback(self.config, "/phone/status", outbound, "signature"))
        for path in ("/phone/sms", "/phone/voice", "/phone/voice/unlock", "/phone/voice/turn"):
            with self.subTest(path=path):
                self.assertFalse(validate_callback(self.config, path, outbound, "signature"))

    def test_dynamic_turn_and_poll_tokens_are_part_of_signature(self):
        for kind in ("turn", "poll"):
            path = "/phone/voice/" + kind + "/" + "a_B-" * 8
            self.assertTrue(validate_callback(self.config, path, self.form, "signature"))
            self.assertEqual(self.validator.validate.call_args.args[0], self.config.public_url + path)

    def test_unknown_encoded_or_ambiguous_paths_rejected(self):
        for path in ("/", "/api/chat", "/phone/sms?job=1", "/phone/sms#fragment", "/phone/sms/",
                     "https://evil.example/phone/sms", "//evil.example/phone/sms", "/phone/../sms",
                     "/phone/%73ms", "/phone/voice/poll/short", "/phone/voice/poll/" + "a" * 129,
                     "/phone/voice/poll/" + "a" * 16 + "/next", None):
            with self.subTest(path=path):
                self.assertFalse(validate_callback(self.config, path, self.form, "signature"))
        self.factory.assert_not_called()

    def test_non_string_fields_or_signature_rejected(self):
        for form in ({**self.form, "Body": ["one", "two"]}, {**self.form, "Body": None},
                     {**self.form, 5: "value"}, {}, list(self.form.items()),
                     {**self.form, **{str(i): "x" for i in range(257)}}):
            self.assertFalse(validate_callback(self.config, "/phone/sms", form, "signature"))
        for signature in (None, "", "x" * 257, "signed\nvalue", "signed value"):
            self.assertFalse(validate_callback(self.config, "/phone/sms", self.form, signature))
        self.factory.assert_not_called()

    def test_missing_sdk_fails_closed(self):
        with patch.dict(sys.modules, {"twilio.request_validator": None}):
            self.assertFalse(validate_callback(self.config, "/phone/sms", self.form, "signature"))


class PhoneRealSignatureTests(unittest.TestCase):
    def test_real_sdk_signature_rejects_tampered_body_origin_path_and_extra_fields(self):
        try:
            from twilio.request_validator import RequestValidator
        except ImportError:
            self.skipTest("Twilio SDK is not installed")
        config = from_environment(phone_settings())
        form = {"AccountSid": config.account_sid, "From": config.owner_number,
                "To": config.from_number, "Body": "Hello IRIS", "FutureField": "included"}
        path = "/phone/sms"
        signature = RequestValidator(config.auth_token).compute_signature(config.public_url + path, form)
        self.assertTrue(validate_callback(config, path, form, signature))
        for change in ({**form, "Body": "Changed"}, {**form, "AddedField": "tampered"},
                       {key: value for key, value in form.items() if key != "FutureField"}):
            self.assertFalse(validate_callback(config, path, change, signature))
        self.assertFalse(validate_callback(config, "/phone/voice", form, signature))
        self.assertFalse(validate_callback(replace(config, public_url="https://other.example.com"),
                                           path, form, signature))


if __name__ == "__main__":
    unittest.main()

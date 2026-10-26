"""Exercise the dedicated public callback boundary over a real loopback socket."""
from http.client import HTTPConnection
import threading
import unittest
from unittest.mock import Mock
from urllib.parse import urlencode

try:
    from twilio.request_validator import RequestValidator
except ImportError:
    RequestValidator = None

from iris.phone.config import PhoneConfig
from iris.phone.server import PhoneServer


@unittest.skipUnless(RequestValidator is not None, "Optional Twilio SDK is not installed")
class PhoneServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = PhoneConfig(
            enabled=True,
            account_sid="AC" + "a" * 32,
            auth_token="synthetic-phone-auth-token",
            voice_pin="258147",
            from_number="+15550001002",
            owner_number="+15550001001",
            public_url="https://iris.example.net",
        )
        cls.service = Mock()
        cls.server = PhoneServer(cls.config, cls.service, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                     kwargs={"poll_interval": .05}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.service.reset_mock()
        self.service.handle.side_effect = None
        self.service.handle.return_value = b'<?xml version="1.0"?><Response />'
        self.form = {
            "AccountSid": self.config.account_sid,
            "From": self.config.owner_number,
            "To": self.config.from_number,
            "MessageSid": "SM" + "b" * 32,
            "Body": "Hello Iris",
        }

    def signature(self, path, form, origin=None):
        return RequestValidator(self.config.auth_token).compute_signature(
            (origin or self.config.public_url) + path, form)

    def request(self, method, path, body=b"", headers=()):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", f"127.0.0.1:{self.server.server_port}")
            for name, value in headers:
                connection.putheader(name, str(value))
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, path="/phone/sms", *, form=None, signed=True, signature=None,
             body=None, extra_headers=(), content_type="application/x-www-form-urlencoded"):
        form = self.form if form is None else form
        body = urlencode(form).encode() if body is None else body
        headers = [("Content-Type", content_type), ("Content-Length", len(body)), *extra_headers]
        if signed:
            headers.append(("X-Twilio-Signature", signature if signature is not None else self.signature(path, form)))
        return self.request("POST", path, body, headers)

    def assert_rejected(self, result, expected=403):
        self.assertEqual(result[0], expected)
        self.service.handle.assert_not_called()
        self.service.assistant.reply.assert_not_called()
        for secret in (self.config.auth_token, self.config.voice_pin, self.config.owner_number,
                       self.config.from_number, self.config.account_sid, self.config.public_url):
            self.assertNotIn(secret.encode(), result[2])

    def test_listener_binds_only_to_loopback(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_health_is_generic_and_other_get_routes_expose_nothing(self):
        status, headers, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"Phone bridge running.")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for path in ("/", "/api/status", "/api/transcribe", "/config", "/phone/sms", "/health?details=1"):
            with self.subTest(path=path):
                self.assert_rejected(self.request("GET", path), 404)

    def test_valid_signed_sms_dispatches_once_after_verification(self):
        status, headers, body = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/xml; charset=utf-8")
        self.assertEqual(body, self.service.handle.return_value)
        self.service.handle.assert_called_once_with("/phone/sms", self.form)

    def test_missing_wrong_empty_and_duplicate_signatures_are_rejected(self):
        self.assert_rejected(self.post(signed=False))
        self.assert_rejected(self.post(signature="incorrect"))
        self.assert_rejected(self.post(signature=""))
        self.assert_rejected(self.post(extra_headers=[("X-Twilio-Signature", self.signature("/phone/sms", self.form))]))

    def test_tampered_body_or_account_is_rejected_before_service(self):
        original = self.signature("/phone/sms", self.form)
        self.assert_rejected(self.post(form={**self.form, "Body": "Tampered command"}, signature=original))
        self.assert_rejected(self.post(form={**self.form, "AccountSid": "AC" + "c" * 32}))

    def test_unknown_sender_or_wrong_destination_is_rejected_even_if_signed(self):
        self.assert_rejected(self.post(form={**self.form, "From": "+15550001003"}))
        self.assert_rejected(self.post(form={**self.form, "To": "+15550001004"}))

    def test_host_and_forwarded_headers_cannot_select_the_authenticated_origin(self):
        headers = [("Host", "attacker.example.org"), ("X-Forwarded-Host", "attacker.example.org"),
                   ("X-Forwarded-Proto", "https"),
                   ("Forwarded", 'host="attacker.example.org";proto=https')]
        spoofed = self.signature("/phone/sms", self.form, "https://attacker.example.org")
        self.assert_rejected(self.post(signature=spoofed, extra_headers=headers))
        local = self.signature("/phone/sms", self.form, f"http://127.0.0.1:{self.server.server_port}")
        self.assert_rejected(self.post(signature=local, extra_headers=headers))
        self.assertEqual(self.post(extra_headers=headers)[0], 200)
        self.service.handle.assert_called_once_with("/phone/sms", self.form)

    def test_unknown_post_routes_and_desktop_endpoints_are_not_exposed(self):
        for path in ("/", "/api/status", "/api/transcribe", "/api/chat", "/phone/unknown", "/phone/sms?extra=1"):
            with self.subTest(path=path):
                self.assert_rejected(self.post(path))

    def test_future_form_fields_are_preserved_and_participate_in_signatures(self):
        future = {**self.form, "FutureTwilioField": "A signed future value", "EmptyFutureValue": ""}
        self.assertEqual(self.post(form=future)[0], 200)
        self.service.handle.assert_called_once_with("/phone/sms", future)
        self.service.reset_mock()
        self.assert_rejected(self.post(form={**future, "FutureTwilioField": "tampered"},
                                       signature=self.signature("/phone/sms", future)))
        self.assert_rejected(self.post(form=future, signature=self.signature("/phone/sms", self.form)))

    def test_duplicate_fields_wrong_content_type_and_oversize_are_bad_requests(self):
        self.assert_rejected(self.post(body=urlencode(self.form).encode() + b"&Body=duplicate"), 400)
        self.assert_rejected(self.request("POST", "/phone/sms", headers=[
            ("Content-Type", "application/json"), ("Content-Length", "10")]), 400)
        # The server must reject the declared size before reading any payload.
        # Sending unread oversized bytes can reset TCP on Windows as it closes.
        self.assert_rejected(self.request("POST", "/phone/sms", headers=[
            ("Content-Type", "application/x-www-form-urlencoded"), ("Content-Length", "16385")]), 400)

    def test_transfer_encoding_and_duplicate_content_lengths_are_rejected(self):
        # Both conditions are rejected using headers alone, before body reads.
        # Avoid unread body bytes causing a Windows TCP reset during shutdown.
        headers = [("Content-Type", "application/x-www-form-urlencoded"), ("Content-Length", "10")]
        self.assert_rejected(self.request("POST", "/phone/sms", headers=[
            *headers, ("Transfer-Encoding", "chunked")]), 400)
        self.assert_rejected(self.request("POST", "/phone/sms", headers=[
            *headers, ("Content-Length", "10")]), 400)

    def test_missing_or_invalid_content_length_is_rejected(self):
        headers = [("Content-Type", "application/x-www-form-urlencoded")]
        self.assert_rejected(self.request("POST", "/phone/sms", headers=headers), 400)
        for length in ("not-a-number", "-1", "0", "16385"):
            with self.subTest(length=length):
                self.assert_rejected(self.request("POST", "/phone/sms", headers=[*headers, ("Content-Length", length)]), 400)

    def test_malformed_utf8_form_and_excessive_fields_are_rejected(self):
        for body in (b"Body", b"Body=hello&broken", b"Body=\xff", b"Body=%FF", b"", b"x=1&" * 129):
            with self.subTest(body_length=len(body)):
                self.assert_rejected(self.post(body=body), 400)

    def test_signed_status_callback_can_omit_phone_numbers(self):
        form = {"AccountSid": self.config.account_sid, "MessageSid": "SM" + "c" * 32,
                "MessageStatus": "delivered"}
        self.assertEqual(self.post("/phone/status", form=form)[0], 200)
        self.service.handle.assert_called_once_with("/phone/status", form)
        self.service.reset_mock()
        self.assert_rejected(self.post("/phone/status", form=form, signed=False))
        self.assert_rejected(self.post("/phone/status", form={**form, "AccountSid": "AC" + "d" * 32}))

    def test_service_errors_return_generic_content_without_private_exception_text(self):
        private = "sensitive-provider-details " + self.config.auth_token
        self.service.handle.side_effect = RuntimeError(private)
        result = self.post()
        self.assertEqual(result[0], 503)
        self.assertEqual(result[2], b"Phone bridge unavailable.")
        self.assertNotIn(private.encode(), result[2])
        self.service.handle.side_effect = ValueError(private)
        result = self.post()
        self.assertEqual(result[0], 400)
        self.assertEqual(result[2], b"Invalid callback.")


if __name__ == "__main__":
    unittest.main()

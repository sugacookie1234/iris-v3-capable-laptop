"""Bounded, owner-only Twilio sends; an accepted SID is not delivery confirmation."""
from __future__ import annotations

import re
from xml.etree import ElementTree

from iris.phone.config import PhoneConfig, PhoneDisabled


_UNCONFIRMED = "Phone provider did not confirm acceptance. Check Twilio before retrying."


class TransportError(RuntimeError):
    """Provider errors never expose credentials, phone numbers, or message text."""


def _message(value: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Phone message must contain between 1 and {limit} characters.")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if any((ord(char) < 32 and char != "\n") or 127 <= ord(char) <= 159
           or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
           for char in normalized):
        raise ValueError("Phone message contains unsupported control characters.")
    normalized = normalized.strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"Phone message must contain between 1 and {limit} characters.")
    return normalized


def _accepted_sid(response: object, kind: str) -> str:
    sid = getattr(response, "sid", None)
    prefix = r"(?:SM|MM)" if kind == "sms" else "CA"
    if not isinstance(sid, str) or not re.fullmatch(prefix + r"[0-9a-fA-F]{32}", sid):
        raise TransportError(_UNCONFIRMED)
    return sid


class TwilioTransport:
    """There is deliberately no recipient argument: only the saved owner is reachable."""

    def __init__(self, config: PhoneConfig, client=None):
        if not config.enabled:
            raise PhoneDisabled("IRIS phone service is disabled. Run phone setup before enabling it.")
        self._config = config
        if client is None:
            try:
                from twilio.http.http_client import TwilioHttpClient
                from twilio.rest import Client
                client = Client(config.account_sid, config.auth_token,
                                http_client=TwilioHttpClient(timeout=10, max_retries=0))
            except Exception:
                raise TransportError(_UNCONFIRMED) from None
        self._client = client

    def send_sms(self, text: str) -> str:
        """Submit one bounded SMS and return its SID; never retry an ambiguous send."""
        body = _message(text, 700)
        try:
            response = self._client.messages.create(
                to=self._config.owner_number,
                from_=self._config.from_number,
                body=body,
                status_callback=self._config.public_url + "/phone/status",
            )
            return _accepted_sid(response, "sms")
        except Exception:
            raise TransportError(_UNCONFIRMED) from None

    def call(self, message: str) -> str:
        """Submit a short spoken notification, then hang up; no call forwarding or recording."""
        text = _message(message, 400)
        response_xml = ElementTree.Element("Response")
        ElementTree.SubElement(response_xml, "Say", voice="man", language="en-US").text = text
        ElementTree.SubElement(response_xml, "Hangup")
        twiml = ElementTree.tostring(response_xml, encoding="unicode")
        try:
            response = self._client.calls.create(
                to=self._config.owner_number,
                from_=self._config.from_number,
                twiml=twiml,
                timeout=20,
                time_limit=120,
                status_callback=self._config.public_url + "/phone/status",
                status_callback_event=["completed"],
                status_callback_method="POST",
            )
            return _accepted_sid(response, "call")
        except Exception:
            raise TransportError(_UNCONFIRMED) from None

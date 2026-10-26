"""Validate signed Twilio form callbacks for the configured owner only."""
from __future__ import annotations

import re

from iris.phone.config import PhoneConfig


_FIXED_PATHS = frozenset({
    "/phone/sms", "/phone/voice", "/phone/voice/unlock", "/phone/voice/turn", "/phone/voice/poll", "/phone/status",
})
_DYNAMIC_PATH = re.compile(r"/phone/voice/(?:poll|turn|unlock)/[A-Za-z0-9_-]{16,128}\Z")


def validate_callback(config: PhoneConfig, path: str, form: dict[str, str], signature: str) -> bool:
    """Fail closed without logging callback content, credentials, or phone numbers.

    The HTTP parser must reject duplicate form fields before constructing this
    dictionary. Every field, including unrecognized future Twilio fields, remains
    in the signature input. Only the configured origin is used: Host and forwarded
    headers cannot change the URL that is authenticated.
    """
    if not config.enabled or not isinstance(path, str):
        return False
    if path not in _FIXED_PATHS and not _DYNAMIC_PATH.fullmatch(path):
        return False
    if (type(form) is not dict or not form or len(form) > 256
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in form.items())):
        return False
    if (not isinstance(signature, str) or not signature or len(signature) > 256
            or any(ord(char) < 33 or ord(char) > 126 for char in signature)):
        return False
    if form.get("AccountSid") != config.account_sid:
        return False
    pair = (form.get("From"), form.get("To"))
    inbound = (config.owner_number, config.from_number)
    outbound = (config.from_number, config.owner_number)
    if path == '/phone/status':
        # Some Messaging status callbacks omit participants. The service only
        # applies status to a locally known SID; supplied participants must match.
        if pair != (None, None) and pair not in (inbound, outbound): return False
    elif pair != inbound:
        return False
    try:
        from twilio.request_validator import RequestValidator
        return bool(RequestValidator(config.auth_token).validate(
            config.public_url + path, form, signature,
        ))
    except (ImportError, ValueError, TypeError, UnicodeError):
        return False

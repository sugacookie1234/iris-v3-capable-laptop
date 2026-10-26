"""Validated, opt-in configuration for IRIS's separate phone bridge."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import ipaddress
import re
from urllib.parse import urlsplit


class PhoneDisabled(ValueError):
    """The phone bridge must be explicitly enabled after local setup."""


_ACCOUNT_SID = re.compile(r"AC[0-9a-fA-F]{32}\Z")
_PHONE_NUMBER = re.compile(r"\+[1-9][0-9]{1,14}\Z")
_HOST_LABEL = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z")
_LOCAL_SUFFIXES = (".localhost", ".local", ".localdomain", ".lan", ".internal", ".home")


def _text(settings: Mapping[str, str], key: str, default: str = "") -> str:
    value = settings.get(key, default)
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Phone configuration contains an invalid value.")
    return value


def _public_origin(value: str) -> str:
    """Require a public HTTPS origin; do not resolve DNS or trust proxy headers."""
    error = "IRIS_PHONE_PUBLIC_URL must be a public HTTPS origin without a path or credentials."
    try:
        if not isinstance(value, str) or len(value) > 2048 or any(char.isspace() for char in value):
            raise ValueError
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or "?" in value or "#" in value
                or "\\" in value or "%" in parsed.netloc or parsed.netloc.endswith(":")):
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        host = parsed.hostname.lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if (len(labels) < 2 or len(host) > 253 or host == "localhost"
                    or host.endswith(_LOCAL_SUFFIXES)
                    or not all(_HOST_LABEL.fullmatch(label) for label in labels)
                    or not re.fullmatch(r"(?:[a-zA-Z]{2,63}|xn--[a-zA-Z0-9-]{2,59})", labels[-1])):
                raise ValueError
        else:
            if not address.is_global or address.is_multicast or address.is_reserved:
                raise ValueError
        # Preserve the exact authority, including a configured port, for signing.
        return "https://" + parsed.netloc
    except (ValueError, TypeError, UnicodeError):
        raise ValueError(error) from None


@dataclass(frozen=True)
class PhoneConfig:
    enabled: bool = False
    account_sid: str = ""
    auth_token: str = field(default="", repr=False)
    voice_pin: str = field(default="", repr=False)
    from_number: str = field(default="", repr=False)
    owner_number: str = field(default="", repr=False)
    public_url: str = ""
    port: int = 8767

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("IRIS_PHONE_ENABLED must be true or false.")
        if not self.enabled:
            return
        if not isinstance(self.account_sid, str) or not _ACCOUNT_SID.fullmatch(self.account_sid):
            raise ValueError("IRIS_TWILIO_ACCOUNT_SID must be a Twilio account SID.")
        if (not isinstance(self.auth_token, str) or not self.auth_token or len(self.auth_token) > 256
                or any(ord(char) < 33 or ord(char) > 126 for char in self.auth_token)):
            raise ValueError("IRIS_TWILIO_AUTH_TOKEN must contain a valid authentication token.")
        if not isinstance(self.voice_pin, str) or not re.fullmatch(r"[0-9]{6}", self.voice_pin):
            raise ValueError("IRIS_PHONE_PIN must contain exactly six digits.")
        for key, value in (("IRIS_PHONE_NUMBER", self.from_number),
                           ("IRIS_OWNER_PHONE_NUMBER", self.owner_number)):
            if not isinstance(value, str) or not _PHONE_NUMBER.fullmatch(value):
                raise ValueError(f"{key} must use international format with a leading plus sign.")
        if self.from_number == self.owner_number:
            raise ValueError("IRIS and the owner must use different phone numbers.")
        if (isinstance(self.port, bool) or not isinstance(self.port, int)
                or not 1024 <= self.port <= 65535 or self.port == 8766):
            raise ValueError("IRIS_PHONE_PORT must be between 1024 and 65535 and different from the desktop port.")
        object.__setattr__(self, "public_url", _public_origin(self.public_url))

    @classmethod
    def from_environment(cls, settings: Mapping[str, str]) -> PhoneConfig:
        enabled = _text(settings, "IRIS_PHONE_ENABLED", "false").strip().lower()
        if enabled in ("", "false"):
            raise PhoneDisabled("IRIS phone service is disabled. Run phone setup before enabling it.")
        if enabled != "true":
            raise ValueError("IRIS_PHONE_ENABLED must be true or false.")
        port = _text(settings, "IRIS_PHONE_PORT", "8767")
        if not re.fullmatch(r"[0-9]{1,5}", port):
            raise ValueError("IRIS_PHONE_PORT must be between 1024 and 65535 and different from the desktop port.")
        return cls(
            enabled=True,
            account_sid=_text(settings, "IRIS_TWILIO_ACCOUNT_SID"),
            auth_token=_text(settings, "IRIS_TWILIO_AUTH_TOKEN"),
            voice_pin=_text(settings, "IRIS_PHONE_PIN"),
            from_number=_text(settings, "IRIS_PHONE_NUMBER"),
            owner_number=_text(settings, "IRIS_OWNER_PHONE_NUMBER"),
            public_url=_text(settings, "IRIS_PHONE_PUBLIC_URL"),
            port=int(port),
        )


def from_environment(settings: Mapping[str, str]) -> PhoneConfig:
    return PhoneConfig.from_environment(settings)

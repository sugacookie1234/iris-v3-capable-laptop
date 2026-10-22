"""Pure environment-facing validation for OpenAI-compatible providers.

This module does not read the process environment itself and never logs or
serializes secrets. Callers pass an environment mapping and retain API keys
only in provider configuration objects in memory.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from urllib.parse import urlsplit


def validate_provider_url(url: str, variable: str = "provider URL") -> str:
    if not isinstance(url, str):
        raise ValueError(f"{variable} must be an HTTP(S) base URL without credentials, query, or fragment.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError(f"{variable} must not contain control characters.")
    normalized = url.strip().rstrip("/")
    try:
        parsed = urlsplit(normalized)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and not any(ch.isspace() for ch in normalized)
                 and not parsed.path.endswith("/chat/completions"))
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            f"{variable} must be an HTTP(S) base URL without credentials, query, or fragment. "
            "Supply the base URL, not /chat/completions; use the matching API_KEY variable for credentials."
        )
    return normalized[:-3] if normalized.endswith("/v1") else normalized


def validate_model_id(model: str, variable: str = "model") -> str:
    if not isinstance(model, str):
        raise ValueError(f"{variable} must be a non-empty model identifier of at most 256 characters.")
    value = model.strip()
    if not value or len(value) > 256 or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError(f"{variable} must be a non-empty model identifier of at most 256 characters.")
    return value


def validate_provider_name(name: str, variable: str = "provider") -> str:
    value = name.strip().lower() if isinstance(name, str) else ""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise ValueError(f"{variable} must be a lowercase provider identifier.")
    return value.replace("-", "_")


def provider_environment(name: str) -> dict[str, str]:
    """Return environment variable names for a provider without its secret."""
    normalized = validate_provider_name(name)
    token = normalized.upper().replace("-", "_")
    return {"url": f"IRIS_PROVIDER_{token}_URL", "api_key": f"IRIS_PROVIDER_{token}_API_KEY",
            "timeout": f"IRIS_PROVIDER_{token}_TIMEOUT_SECONDS"}


def configured_provider_names(environ: Mapping[str, str]) -> tuple[str, ...]:
    """List named providers configured by URL, excluding values without URLs."""
    names = []
    for key, value in environ.items():
        match = re.fullmatch(r"IRIS_PROVIDER_([A-Z][A-Z0-9_]*)_URL", key)
        if match and isinstance(value, str) and value.strip():
            names.append(validate_provider_name(match.group(1), key))
    return tuple(sorted(set(names)))

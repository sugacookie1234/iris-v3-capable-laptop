"""Deterministic rejection of credentials before memory persistence."""
from __future__ import annotations

import json
import re
from typing import Any


class MemoryRedactionError(ValueError):
    """Raised when a memory contains credentials or secret material."""


_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]"),
    re.compile(r"(?i)\b(?:cookie|set-cookie)\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\b(?:gsk_|sk-|rk_live_|pk_live_)[A-Za-z0-9_-]{12,}"),
    re.compile(
        r"(?i)[\"']?\b(?:api[_ -]?key|password|passwd|secret|token)"
        r"[\"']?\s*[:=]\s*[\"']?\S+"
    ),
)


def contains_secret(value: Any) -> bool:
    """Return whether serialized structured data contains credential material."""
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = repr(value)
    return any(pattern.search(text) for pattern in _PATTERNS)


def reject_secrets(*values: Any) -> None:
    if any(contains_secret(value) for value in values):
        raise MemoryRedactionError(
            "Memory contains credential or secret material and was rejected."
        )

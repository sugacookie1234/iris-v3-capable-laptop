"""Process-local, session-only conversation display state."""
from __future__ import annotations

import json
import os
import re
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


_lock = RLock()
_view = {"state": "idle", "user_speech": "", "response": ""}
_STATES = {"idle", "listening", "thinking", "speaking", "muted", "error"}


def update_conversation(*, state: str | None = None, user_speech: str | None = None,
                        response: str | None = None) -> None:
    """Publish bounded display data in memory only; never writes a file."""
    with _lock:
        if state is not None:
            candidate = str(state)[:32]
            _view["state"] = candidate if candidate in _STATES else "error"
        if user_speech is not None:
            _view["user_speech"] = str(user_speech)[:4000]
        if response is not None:
            _view["response"] = str(response)[:8000]


def conversation_snapshot() -> dict[str, str]:
    with _lock:
        return dict(_view)


def clear_conversation() -> None:
    """Clear captions at the end of a local UI/voice session."""
    with _lock:
        _view.update(state="idle", user_speech="", response="")


def set_conversation(snapshot: dict[str, str]) -> None:
    """Replace the bounded view from a local HUD event; never write it to disk."""
    if (not isinstance(snapshot, dict) or set(snapshot) - set(_view)
            or any(not isinstance(value, str) for value in snapshot.values())
            or snapshot.get("state", "idle") not in _STATES
            or len(snapshot.get("user_speech", "")) > 4000
            or len(snapshot.get("response", "")) > 8000):
        raise ValueError("Invalid conversation event.")
    with _lock:
        _view.update(state=snapshot.get("state", "idle"),
                     user_speech=snapshot.get("user_speech", ""),
                     response=snapshot.get("response", ""))


def validate_hud_token(token: str) -> str:
    """Empty disables IPC; configured capabilities must be header-safe."""
    if not isinstance(token, str) or (token and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token)):
        raise ValueError("HUD token must be 32 to 128 URL-safe characters.")
    return token


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class HudConversationPublisher:
    """Best-effort loopback IPC for a voice process publishing HUD events."""

    def __init__(self, endpoint: str, *, timeout: float = 0.15, token: str = ""):
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HUD conversation endpoint must be local HTTP.")
        if (parsed.username or parsed.password or parsed.path != "/api/conversation"
                or parsed.query or parsed.fragment):
            raise ValueError("HUD conversation endpoint is invalid.")
        self._token = validate_hud_token(token)
        self.endpoint = endpoint
        self.timeout = max(0.02, min(float(timeout), 1.0))
        # Never send captions through an environment proxy or a redirect.
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    @classmethod
    def from_environment(cls) -> "HudConversationPublisher":
        endpoint = os.environ.get(
            "IRIS_HUD_URL", "http://127.0.0.1:8765/api/conversation"
        ).strip()
        return cls(endpoint, token=os.environ.get("IRIS_HUD_TOKEN", ""))

    def publish(self, snapshot: dict[str, str]) -> None:
        if not self._token:
            return
        payload = {
            "state": str(snapshot.get("state", "idle"))[:32],
            "user_speech": str(snapshot.get("user_speech", ""))[:4000],
            "response": str(snapshot.get("response", ""))[:8000],
        }
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        try:
            with self._opener.open(Request(self.endpoint, data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + self._token}),
                         timeout=self.timeout) as response:
                response.read(0)
        except HTTPError as exc:
            exc.close()
        except (OSError, URLError, ValueError):
            # A missing HUD must never break recognition, response generation, or playback.
            return

    def __call__(self, snapshot: dict[str, str]) -> None:
        self.publish(snapshot)

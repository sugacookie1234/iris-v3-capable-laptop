"""Read-only, localhost-only IRIS HUD."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
import re
import select
import secrets
import socket
import sys
import threading
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from iris.briefing import build_briefing, render_briefing
from iris.calendar import CalendarSource
from iris.preflight import diagnostics_values
from iris.memory.redaction import contains_secret
from iris.notifications.models import safe_payload
from iris.tasks.store import TaskStore
from iris.voice import VoiceState
from iris.terminal import load_config
from iris.local_config import activate_saved_configuration
from iris.ui_state import conversation_snapshot, clear_conversation, set_conversation, validate_hud_token


def sanitize_snapshot(value, *, field=""):
    """Redact before either serialization or rendering; never mutate source data."""
    keys = [v.strip() for k, v in os.environ.items() if k.startswith("IRIS_")
            and (k.endswith("API_KEY") or k == "IRIS_HUD_TOKEN") and v.strip()]
    if isinstance(value, dict):
        return {key: sanitize_snapshot(item, field=key) for key, item in value.items()
                if isinstance(key, str) and not re.search(
                    r"(?i)(api.?key|password|credential|token|secret|note.content|transcript|arguments)", key)
                and not contains_secret(key) and not any(secret in key for secret in keys)
                and "/" not in key and "\\" not in key}
    if isinstance(value, (list, tuple)):
        return [sanitize_snapshot(item, field=field) for item in value]
    if not isinstance(value, str):
        return value if value is None or type(value) in (bool, int, float) else "[redacted]"
    if contains_secret(value) or any(key in value for key in keys):
        return "[redacted]"
    # Model IDs and IANA timezone names legitimately contain slashes.
    if (field in {"model", "timezone"} and not value.startswith(("/", ".", "~"))
            and not re.match(r"^[A-Za-z]:", value)
            and re.fullmatch(r"[A-Za-z0-9_.:/+-]+", value)):
        return value
    if field not in {"user_speech", "response"} and re.search(r"(?:[/\\]|~[/\\])", value):
        return "[private path omitted]"
    return value


def serve_until_eof(server, stream=None):
    """Serve only in the foreground, watching console/pipe EOF without a reader thread."""
    stream = sys.stdin if stream is None else stream
    server.timeout = 0.25
    if os.name == "nt":
        ended = threading.Event()
        def watch_input():
            try:
                while stream.read(1):
                    pass
            finally:
                ended.set()
        threading.Thread(target=watch_input, daemon=True).start()
        while not ended.is_set():
            server.handle_request()
        return
    while True:
        ready, _, _ = select.select([server, stream], [], [], 0.25)
        if stream in ready and not os.read(stream.fileno(), 4096):
            return
        if server in ready:
            server.handle_request()


def _readonly_rows(path, query, params=()):
    if not path:
        return []
    database = Path(path).expanduser()
    if not database.is_file():
        return []
    connection = None
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, params)]
    except (OSError, sqlite3.Error, ValueError):
        return []
    finally:
        if connection is not None:
            connection.close()


def collect_snapshot(*, now: datetime | None = None, voice_state: str | None = None) -> dict:
    """Collect bounded local data. Every failed optional source is simply empty."""
    try:
        # Pass the process environment explicitly so embedded callers/tests do
        # not accidentally merge a different user's saved configuration.
        config = load_config(dict(os.environ))
    except (ValueError, OSError):
        config = None
    config_values = diagnostics_values(config, check_provider_reachability=False)
    config_values["configuration_status"] = "valid" if config else "unavailable"
    task_path = os.environ.get("IRIS_TASKS_PATH")
    tasks = []
    try:
        with TaskStore(task_path, read_only=True) as store:
            for task in store.list():
                if str(task.status) == "open":
                    title = "[redacted]" if contains_secret(task.title) else task.title[:200]
                    tasks.append({"id": task.id, "title": title, "due_at": task.due_at,
                                  "priority": str(task.priority), "status": str(task.status)})
    except (OSError, ValueError, sqlite3.Error):
        pass
    notifications = []
    rows = _readonly_rows(os.environ.get("IRIS_NOTIFICATIONS_PATH"),
                          "SELECT data FROM notifications ORDER BY json_extract(data, '$.created_at') DESC LIMIT 50")
    for row in rows:
        try:
            event = json.loads(row["data"])
            payload = safe_payload(event.get("payload", {}))
            if contains_secret(json.dumps(payload, ensure_ascii=True)):
                payload = {"status": "redacted"}
            notifications.append({"id": str(event.get("id", "")), "kind": str(event.get("kind", "")),
                                  "severity": str(event.get("severity", "")),
                                  "created_at": str(event.get("created_at", "")),
                                  "payload": payload, "read": bool(event.get("read", False)),
                                  "dismissed": bool(event.get("dismissed", False))})
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    calendar = None
    calendar_path = os.environ.get("IRIS_CALENDAR_PATH")
    calendar_root = os.environ.get("IRIS_CALENDAR_ROOT")
    zone = os.environ.get("IRIS_TIMEZONE", "America/Toronto")
    if calendar_path and calendar_root:
        try:
            calendar = CalendarSource(calendar_root, calendar_path, zone)
        except (OSError, ValueError, PermissionError):
            calendar = None
    briefing = {}
    try:
        briefing = build_briefing(task_path=task_path,
                                  goal_path=os.environ.get("IRIS_GOALS_PATH"), calendar=calendar,
                                  memory_path=os.environ.get("IRIS_MEMORY_PATH"), zone=zone, at=now)
    except (OSError, ValueError, sqlite3.Error):
        briefing = {"date": "", "timezone": zone, "facts": {"calendar_configured": False, "events": [], "permitted_memories": [], "active_goals": []},
                    "deadlines": [], "goal_risks": [], "suggestions": []}
    automation_rows = _readonly_rows(os.environ.get("IRIS_AUTOMATION_PATH"),
                                      "SELECT data FROM schedules ORDER BY id")
    automation = []
    for row in automation_rows:
        try:
            item = json.loads(row["data"])
            automation.append({"id": item.get("id", ""), "workflow_name": item.get("workflow_name", ""),
                               "enabled": bool(item.get("enabled", False)), "run_at": item.get("run_at", "")})
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    status = {key: config_values.get(key) for key in config_values}
    conversation = conversation_snapshot()
    return sanitize_snapshot({"state": voice_state or conversation["state"], "statuses": status,
            "notifications": notifications, "tasks": tasks, "briefing": briefing,
            "automation": automation, "council": status.get("council_configured", False),
            "conversation": conversation})


def render_dashboard(snapshot: dict) -> str:
    """Render escaped user data in a compact dark dashboard."""
    snapshot = sanitize_snapshot(snapshot)
    esc = lambda value: html.escape(str(value), quote=True)
    statuses = snapshot.get("statuses", {})
    status_html = "".join(f"<li><b>{esc(k.replace('_', ' '))}</b>: {esc(v)}</li>" for k, v in statuses.items())
    task_html = "".join(f"<li>{esc(t.get('title', ''))} <small>{esc(t.get('due_at') or 'no deadline')}</small></li>" for t in snapshot.get("tasks", [])) or "<li>None</li>"
    note_html = "".join(f"<li>{esc(n.get('severity'))}: {esc(n.get('kind'))} — {esc(n.get('created_at'))}</li>" for n in snapshot.get("notifications", []) if not n.get("dismissed")) or "<li>None</li>"
    briefing = snapshot.get("briefing", {})
    summary = render_briefing(briefing) if briefing else "No briefing available."
    if contains_secret(summary):
        summary = "[redacted sensitive briefing content]"
    conversation = snapshot.get("conversation", {})
    state = conversation.get("state", "idle")
    if state not in {"idle", "listening", "thinking", "speaking", "muted", "error"}:
        state = "error"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>IRIS HUD</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="/hud.css"><script src="/hud.js" defer></script></head>'
        '<body><main><header><span>IRIS <small>LOCAL HUD</small></span>'
        '<span class="privacy">SESSION ONLY</span></header>'
        '<section id="voice-view" data-state="' + state + '" aria-label="State core">'
        '<div class="eye-stage" aria-hidden="true"><div class="orbit"></div>'
        '<div class="eye"><div class="fibers"></div><div class="pupil"></div></div></div>'
        '<h1>IRIS</h1><p id="voice-state" role="status">' + state.upper() + '</p>'
        '<p id="voice-hint">' + ("Voice turn failed. Check the terminal for safe diagnostics."
                                   if state == "error" else "") + '</p>'
        '<section class="conversation" aria-label="Conversation" aria-live="polite" aria-atomic="true">'
        '<div class="conversation-heading">Conversation <small>IN MEMORY · THIS SESSION</small></div>'
        '<div class="caption"><span>You</span><p id="user-speech">' + esc(conversation.get("user_speech", "")) + '</p></div>'
        '<div class="caption"><span>IRIS</span><p id="iris-response">' + esc(conversation.get("response", "")) + '</p></div></section>'
        '<div class="input-status"><span class="input-dot" aria-hidden="true"></span>'
        '<span id="input-label">' + ("Capture active" if state == "listening" else "Not recording") + '</span></div>'
        '</section><details><summary>Local details</summary><div class="grid">'
        '<section class="card"><h2>State core</h2><p>Driven by the voice session; input indicator is not an audio level meter.</p></section>'
        '<section class="card"><h2>Subsystems</h2><ul>' + status_html + '</ul></section>'
        '<section class="card"><h2>Notifications</h2><ul>' + note_html + '</ul></section>'
        '<section class="card"><h2>Open tasks & deadlines</h2><ul>' + task_html + '</ul></section>'
        '<section class="card"><h2>Council / automation</h2><p>Council: ' + esc(snapshot.get("council", False)) + '</p><p>Schedules: ' + esc(len(snapshot.get("automation", []))) + '</p></section>'
        '<section class="card"><h2>Daily briefing</h2><pre>' + esc(summary) + '</pre></section>'
        '</div></details></main></body></html>'
    )


class HUDRequestHandler(BaseHTTPRequestHandler):
    snapshot_factory = staticmethod(collect_snapshot)
    allow_conversation_updates = True
    conversation_token = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(2.0)
        self._body_read = False

    def send_error(self, code, message=None, explain=None):
        # Drain bounded rejected bodies before closing: otherwise Windows may
        # reset the socket before the client receives the error response.
        if not self._body_read and self.command == 'POST':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if 0 < length <= 80000 and not self.headers.get('Transfer-Encoding'):
                    self.rfile.read(length)
            except (OSError, ValueError):
                pass
            self._body_read = True
        super().send_error(code, message, explain)

    def _local_request(self):
        authority = self.headers.get("Host", "")
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if (self.client_address[0] not in {"127.0.0.1", "::1"}
                or authority not in allowed
                or self.headers.get("Origin", f"http://{authority}") != f"http://{authority}"
                or self.headers.get("Sec-Fetch-Site", "same-origin") not in {"same-origin", "none"}):
            self.send_error(403, "Local same-origin requests only")
            return False
        return True

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def do_GET(self):  # noqa: N802
        if not self._local_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/conversation":
            payload = json.dumps(sanitize_snapshot(conversation_snapshot()), ensure_ascii=True).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
        elif path in {"/hud.css", "/hud.js"}:
            payload = (Path(__file__).parent / "ui_assets" / path[1:]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css" if path.endswith(".css") else "text/javascript")
        elif path == "/api/status":
            snapshot = sanitize_snapshot(self.snapshot_factory())
            payload = json.dumps(snapshot, ensure_ascii=True).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
        elif path in {"/", "/index.html"}:
            snapshot = sanitize_snapshot(self.snapshot_factory())
            payload = render_dashboard(snapshot).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            self.send_error(404, "Not found"); return
        self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        """Accept bounded loopback voice events; captions remain memory-only."""
        if not self._local_request():
            return
        if not self.allow_conversation_updates:
            self.send_error(403, "Shared session is read only")
            return
        expected = self.conversation_token
        supplied = self.headers.get_all("Authorization", [])
        if (not expected or len(supplied) != 1
                or not secrets.compare_digest(supplied[0].encode("utf-8"),
                                              ("Bearer " + expected).encode("ascii"))):
            self.send_error(403, "Authenticated event publisher required")
            return
        if urlsplit(self.path).path != "/api/conversation":
            self.send_error(404, "Not found")
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.send_error(415, "JSON events only")
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > 80_000 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            raw = self.rfile.read(length)
            self._body_read = True
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            set_conversation(value)
        except (OSError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "Invalid conversation event")
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        return


def create_server(host: str = "127.0.0.1", port: int = 8765, *, snapshot_factory=None,
                  allow_conversation_updates: bool = True, conversation_token: str = ""):
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("IRIS HUD only permits localhost binding.")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("HUD port must be between 0 and 65535.")
    class Handler(HUDRequestHandler):
        pass
    Handler.snapshot_factory = staticmethod(snapshot_factory or collect_snapshot)
    Handler.allow_conversation_updates = allow_conversation_updates
    Handler.conversation_token = validate_hud_token(conversation_token)
    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if host == "::1" else socket.AF_INET

        def server_close(self):
            try:
                super().server_close()
            finally:
                clear_conversation()
    return Server((host, port), Handler)


class VoiceHUD:
    """Read-only HTTP view of the voice launcher's existing in-process state."""

    def __init__(self, port: int = 0):
        clear_conversation()
        self.server = create_server(port=port, allow_conversation_updates=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=3)
        self.server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the read-only local IRIS HUD.")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback host only (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    activate_saved_configuration()
    server = create_server(args.host, args.port,
                           conversation_token=os.environ.get("IRIS_HUD_TOKEN", ""))
    print(f"IRIS HUD listening on http://{args.host}:{server.server_port} (Ctrl+C to stop)")
    try:
        serve_until_eof(server)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        clear_conversation()
        server.server_close()


if __name__ == "__main__":
    main()

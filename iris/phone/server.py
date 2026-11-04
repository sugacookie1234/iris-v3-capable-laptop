"""Dedicated loopback-only receiver; expose this port, never the desktop server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from urllib.parse import parse_qsl

from iris.phone.security import validate_callback


class PhoneServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, config, service, *, port=None):
        self.config, self.service = config, service
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', config.port if port is None else port), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try: super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.slots.release()

    def handle_error(self, request, address):
        pass  # Never emit request bodies or phone/provider credentials.


class Handler(BaseHTTPRequestHandler):
    server_version = 'IRIS-phone'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)
        self._body_read = False

    def log_message(self, *_): pass

    def send(self, status, body, kind='text/plain; charset=utf-8'):
        if status >= 400 and self.command == 'POST' and not self._body_read:
            # Avoid a Windows TCP reset from unread bytes, without allowing a
            # rejected sender to hold a slot for the normal five-second timeout.
            try:
                lengths = self.headers.get_all('Content-Length', [])
                size = int(lengths[0]) if len(lengths) == 1 else 0
                if 0 < size <= 16384:
                    deadline = time.monotonic() + .05
                    while size > 0:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:break
                        self.connection.settimeout(remaining)
                        chunk = self.rfile.read1(min(size,8192))
                        if not chunk:break
                        size -= len(chunk)
            except (ValueError,OSError):
                pass
            self._body_read = True
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        try: self.wfile.write(body)
        except (OSError, ConnectionError): pass

    def do_GET(self):
        self.send(200, b'Phone bridge running.') if self.path == '/health' else self.send(404, b'Not found.')

    def do_POST(self):
        try:
            if len(self.headers.get_all('Content-Type', [])) != 1 or self.headers.get_content_type() != 'application/x-www-form-urlencoded': raise ValueError
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get_all('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit(): raise ValueError
            size = int(lengths[0])
            if not 0 < size <= 16384: raise ValueError
            raw = self.rfile.read(size)
            self._body_read = True
            if len(raw) != size: raise ValueError
            pairs = parse_qsl(raw.decode('utf-8'), keep_blank_values=True, strict_parsing=True,
                              encoding='utf-8', errors='strict', max_num_fields=128)
            form = dict(pairs)
            if len(form) != len(pairs): raise ValueError
        except (ValueError, UnicodeError, OSError):
            self.send(400, b'Invalid callback.')
            return
        signatures = self.headers.get_all('X-Twilio-Signature', [])
        if len(signatures) != 1 or not validate_callback(self.server.config, self.path, form, signatures[0]):
            self.send(403, b'Callback not authorized.')
            return
        try:
            result = self.server.service.handle(self.path, form)
            self.send(200, result, 'application/xml; charset=utf-8')
        except ValueError:
            self.send(400, b'Invalid callback.')
        except Exception:
            self.send(503, b'Phone bridge unavailable.')

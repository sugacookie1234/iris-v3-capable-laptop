"""Loopback-only browser host with streaming speech and explicit action approval."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from iris.desktop.runtime import DesktopRuntime, BusyError, ROOT
from iris.brain.providers.openai_compatible import OpenAICompatibleError
from iris.brain.council import CouncilExecutionError
from iris.desktop.recognition import transcribe, speech_status, MAX_AUDIO_BYTES
from iris.desktop.dashboard import dashboard_weather, dashboard_markets
from iris.desktop.browser import open_chrome


def voice_request(settings, text):
    key = settings.get('IRIS_FISH_API_KEY')
    if not key:
        raise ValueError('No Fish Audio key configured. Run setup.bat to enable this voice.')
    return urllib.request.Request('https://api.fish.audio/v1/tts', method='POST',
        data=json.dumps({'text': text, 'reference_id': settings.get('IRIS_FISH_VOICE_ID',
                        '41f0953d7a6b4c078445c7e65d620eeb'), 'format': 'mp3',
                        'latency': 'balanced', 'normalize': True}).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                 'model': settings.get('IRIS_FISH_MODEL', 's2.1-pro-free')})


class DesktopServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'
    daemon_threads = True

    def __init__(self, address, runtime):
        self.runtime = runtime
        self.session = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'IRIS/3'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self._body_read = False

    def log_message(self, *_):
        pass  # Never log conversation text, ticket URLs, or credentials.

    def _trusted_host(self):
        port = self.server.server_address[1]
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def _authorized(self, write=False):
        if not self._trusted_host():
            return False
        origin = self.headers.get('Origin')
        allowed = {f'http://127.0.0.1:{self.server.server_address[1]}',
                   f'http://localhost:{self.server.server_address[1]}'}
        if origin and origin not in allowed:
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            value = cookie['iris_session'].value
        except (KeyError, ValueError):
            return False
        return secrets.compare_digest(value, self.server.session) and (
            not write or self.headers.get('X-IRIS-Request') == '1')

    def _headers(self, code, content_type, length=None, cookie=False):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                         "font-src 'self' https://fonts.gstatic.com; media-src 'self' blob:; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if length is not None:
            self.send_header('Content-Length', str(length))
        if cookie:
            self.send_header('Set-Cookie', 'iris_session=' + self.server.session +
                             '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()

    def _send(self, code, body, kind='application/json', cookie=False):
        if code >= 400 and self.command == 'POST' and not self._body_read:
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if 0 < size <= 64000 and not self.headers.get('Transfer-Encoding'):
                    self.rfile.read(size)
            except (ValueError, OSError):
                pass
            self._body_read = True
        self._headers(code, kind, len(body), cookie)
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _json(self, code, value):
        self._send(code, json.dumps(value, ensure_ascii=False).encode())

    def _body(self):
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Use JSON for this request.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Invalid request length.') from None
        if size <= 0 or size > 64000:
            raise ValueError('Request is empty or too large.')
        raw = self.rfile.read(size)
        self._body_read = True
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('Expected an object.')
        return value

    def do_GET(self):
        if not self._trusted_host():
            self._json(403, {'error': 'Local access only.'})
            return
        path = urlsplit(self.path).path
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript'),
                  '/clap.js': ('clap.js', 'text/javascript'),
                  '/standby.js': ('standby.js', 'text/javascript'),
                  '/dashboard.js': ('dashboard.js', 'text/javascript'),
                  '/voice-input.js': ('voice-input.js', 'text/javascript'),
                  '/desktop.css': ('desktop.css', 'text/css')}
        if path in assets:
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' and path != '/':
                self._json(403, {'error': 'Local access only.'})
                return
            filename, kind = assets[path]
            self._send(200, (ROOT / 'web' / filename).read_bytes(), kind, cookie=path == '/')
            return
        if path == '/favicon.ico':
            self._send(204, b'')
            return
        if not self._authorized():
            self._json(403, {'error': 'Open IRIS in this browser first.'})
            return
        app = self.server.runtime
        try:
            if path == '/api/status':
                cfg = app.settings
                self._json(200, {'name': 'IRIS', 'brain': True, 'voice': bool(cfg.get('IRIS_FISH_API_KEY')),
                    'speech': speech_status(cfg),
                    'model': app.config.model, 'voice_id': cfg.get('IRIS_FISH_VOICE_ID', ''),
                    'last_route': app.last_route, 'last_seconds': app.last_seconds,
                    'council': True, 'memory': True, 'tasks': True,
                    'obsidian': bool(app.config.obsidian_root or app.config.obsidian_vault),
                    'target': 'HP OMEN 16 · Core 7 240H · 16 GB · RTX 5060 · 1 TB SSD',
                    'provider_verified': False})
            elif path == '/api/approval':
                self._json(200, {'pending': app.pending_approval()})
            elif path == '/api/markets':
                self._json(200, dashboard_markets())
            elif path == '/api/memories':
                self._json(200, {'items': app.memories()})
            elif path == '/api/tasks':
                self._json(200, {'items': app.tasks()})
            elif path.startswith('/api/audio/'):
                self._stream_voice(app.consume_audio(path.removeprefix('/api/audio/')))
            else:
                self._json(404, {'error': 'Not found.'})
        except ValueError as exc:
            self._json(400, {'error': str(exc)})

    def _stream_voice(self, text):
        started = False
        try:
            request = voice_request(self.server.runtime.settings, text)
            with urllib.request.urlopen(request, timeout=60) as upstream:
                first = upstream.read1(4096)
                if not first:
                    raise ValueError('Fish Audio returned no speech.')
                content_type = upstream.headers.get('Content-Type', '').lower()
                if 'json' in content_type or first.lstrip().startswith((b'{', b'[')):
                    raise ValueError('Fish Audio returned an error instead of speech.')
                self._headers(200, 'audio/mpeg')
                self.close_connection = True
                started = True
                self.wfile.write(first)
                self.wfile.flush()
                while chunk := upstream.read1(4096):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if not started:
                self._json(502, {'error': 'Fish Audio is unavailable. Check your key, model and account quota.'})
            self.close_connection = True

    def do_POST(self):
        if not self._authorized(write=True):
            self._json(403, {'error': 'Request not authorized from this interface.'})
            return
        app = self.server.runtime
        try:
            if urlsplit(self.path).path == '/api/transcribe':
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 32 <= size <= MAX_AUDIO_BYTES:
                    raise ValueError('Recording is empty or too large. Keep speech under 30 seconds.')
                audio = self.rfile.read(size)
                self._body_read = True
                if len(audio) != size:
                    raise ValueError('Recording upload was incomplete.')
                text = transcribe(app.settings, audio, self.headers.get('Content-Type', ''))
                self._json(200, {'text': text, 'speech': speech_status(app.settings)})
                return
            value = self._body()
            path = urlsplit(self.path).path
            if path == '/api/weather':
                self._json(200, dashboard_weather(value.get('latitude'), value.get('longitude')))
            elif path == '/api/chat':
                self._json(200, app.chat(value.get('text'), value.get('mode', 'auto')))
            elif path == '/api/approval':
                if type(value.get('approved')) is not bool:
                    raise ValueError('Choose approve or decline.')
                app.resolve_approval(value.get('id'), value['approved'])
                self._json(200, {'ok': True})
            elif path == '/api/reset':
                app.reset()
                self._json(200, {'ok': True})
            elif path == '/api/voice':
                token = app.issue_audio(value.get('text'))
                self._json(200, {'url': '/api/audio/' + token})
            else:
                self._json(404, {'error': 'Not found.'})
        except BusyError as exc:
            self._json(409, {'error': str(exc)})
        except (ValueError, TypeError, UnicodeError) as exc:
            self._json(400, {'error': str(exc)[:500]})
        except OpenAICompatibleError as exc:
            self._json(502, {'error': exc.diagnostic})
        except CouncilExecutionError:
            self._json(502, {'error': 'The council could not complete. Check model availability and quota, or use Auto for a normal conversation.'})
        except Exception:
            self._json(500, {'error': 'IRIS could not complete that request. No automatic retry was made.'})


def open_browser(url):
    try:
        return open_chrome(url)
    except (RuntimeError, OSError) as exc:
        print(f'{exc}\nOpen Google Chrome and visit {url}.', flush=True)
        return False


def main():
    parser = argparse.ArgumentParser(description='IRIS unified desktop assistant')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        runtime = DesktopRuntime()
    except Exception:
        print('IRIS needs configuration. Run setup.bat, then start-iris.bat.')
        return 1
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = DesktopServer(('127.0.0.1', port), runtime)
            break
        except OSError:
            continue
    if server is None:
        print('No available IRIS port. Close the previous instance and try again.')
        return 1
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'IRIS is ready at {url}\nClose this launcher to stop IRIS.', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, open_browser, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

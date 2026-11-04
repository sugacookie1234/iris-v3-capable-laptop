"""Loopback-only browser host with streaming speech and explicit action approval."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from iris.desktop.runtime import DesktopRuntime, BusyError, ROOT
from iris.desktop.limits import UsageLimits, UsageLimitError
from contextlib import ExitStack, nullcontext
from iris.usage import ProviderLimitError
from iris.brain.providers.openai_compatible import OpenAICompatibleError
from iris.brain.council import CouncilExecutionError
from iris.desktop.recognition import transcribe, speech_status, MAX_AUDIO_BYTES
from iris.desktop.dashboard import dashboard_weather, dashboard_markets
from iris.desktop.browser import open_chrome
from iris.desktop.clap_listener import NativeClapListener, SAMPLE_RATE, BLOCK_MS
from iris.desktop.web_search import web_available
from iris.voice.fish_audio import normalize_tts_text, FISH_SPEECH_TEMPERATURE, FISH_SPEECH_TOP_P


def voice_request(settings, text):
    key = settings.get('IRIS_FISH_API_KEY')
    if not key:
        raise ValueError('No Fish Audio key configured. Run setup.bat to enable this voice.')
    text = normalize_tts_text(text)
    if not text:
        raise ValueError('No spoken words remain after removing vocal directions.')
    return urllib.request.Request('https://api.fish.audio/v1/tts', method='POST',
        data=json.dumps({'text': text, 'reference_id': settings.get('IRIS_FISH_VOICE_ID',
                        '41f0953d7a6b4c078445c7e65d620eeb'), 'format': 'mp3',
                        'latency': 'balanced', 'normalize': True,
                        'temperature': FISH_SPEECH_TEMPERATURE, 'top_p': FISH_SPEECH_TOP_P}).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                 'model': settings.get('IRIS_FISH_MODEL', 's2.1-pro-free')})


class DesktopServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'
    daemon_threads = True

    def __init__(self, address, runtime):
        if address[0] not in ('127.0.0.1', 'localhost'):
            raise ValueError('Desktop server must bind to IPv4 loopback.')
        self._connections = threading.BoundedSemaphore(32)
        self.runtime = runtime
        self.limits = UsageLimits(getattr(runtime, "settings", {}))
        self._owns_runtime = False
        self.desktop_window = False
        self.session = secrets.token_urlsafe(32)
        self._bootstrap_lock = threading.Lock()
        self._bootstrap = None
        self._visual_bootstrap = None
        self._visual_session = None
        self._visual_cookie = None
        self._auth_failures = []
        self.clap_listener = NativeClapListener()
        super().__init__(address, Handler)
        self._owns_runtime = True
        if hasattr(runtime, 'start_background'):
            runtime.start_background()

    def server_close(self):
        try:
            self.revoke_visual()
            self.clap_listener.close()
            if self._owns_runtime and hasattr(self.runtime, 'close'):
                self._owns_runtime = False
                self.runtime.close()
        finally:
            super().server_close()

    def bootstrap_url(self):
        with self._bootstrap_lock:
            token = secrets.token_urlsafe(32)
            self._bootstrap = (token, time.monotonic() + 60)
        return f'http://127.0.0.1:{self.server_address[1]}/#pair={token}'

    def visual_bootstrap_url(self):
        # Different host origins isolate WebView2 DOM/storage/cookies while using
        # the same loopback listener and runtime. Host/Origin checks enforce scope.
        with self._bootstrap_lock:
            token=secrets.token_urlsafe(32)
            self._visual_bootstrap=(token,time.monotonic()+60)
            self._visual_session=None
        return f'http://localhost:{self.server_address[1]}/visual#pair={token}'

    def revoke_visual(self):
        with self._bootstrap_lock:
            self._visual_bootstrap=None;self._visual_session=None;self._visual_cookie=None

    def redeem_visual(self,token):
        with self._bootstrap_lock:
            now=time.monotonic()
            self._auth_failures=[stamp for stamp in self._auth_failures if now-stamp<60]
            if len(self._auth_failures)>=10:return None
            active=self._visual_bootstrap
            if type(token) is not str or not token.isascii() or not active or time.monotonic()>=active[1] or not secrets.compare_digest(token,active[0]):return None
            self._visual_bootstrap=None
            lease=secrets.token_urlsafe(32)
            self._visual_session=(lease,time.monotonic()+900)
            self._visual_cookie=secrets.token_urlsafe(32)
            return lease

    def visual_authorized(self,token):
        with self._bootstrap_lock:
            active=self._visual_session
            return bool(type(token) is str and token.isascii() and active and time.monotonic()<active[1] and secrets.compare_digest(token,active[0]))

    def visual_cookie_authorized(self, cookie):
        with self._bootstrap_lock:
            return bool(type(cookie) is str and cookie.isascii() and self._visual_cookie
                and self._visual_session and time.monotonic() < self._visual_session[1]
                and secrets.compare_digest(cookie,self._visual_cookie))

    def redeem_bootstrap(self, token):
        with self._bootstrap_lock:
            now = time.monotonic()
            self._auth_failures = [stamp for stamp in self._auth_failures if now-stamp < 60]
            if len(self._auth_failures) >= 10:
                return False
            active = self._bootstrap
            if type(token) is str and token.isascii() and active and now < active[1] and secrets.compare_digest(token, active[0]):
                self._bootstrap = None
                return True
            self._auth_failures.append(now)
            return False

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


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
        return len(self.headers.get_all('Host', [])) == 1 and self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def _authorized(self, write=False):
        if any(len(self.headers.get_all(key, [])) > 1 for key in
               ('Origin', 'Cookie', 'X-IRIS-Request', 'X-IRIS-Visual', 'Sec-Fetch-Site')):
            return False
        if not self._trusted_host():
            return False
        visual = urlsplit(self.path).path in ('/visual','/api/visual/state','/api/visual/update')
        expected_host = f'{"localhost" if visual else "127.0.0.1"}:{self.server.server_address[1]}'
        if self.headers.get('Host') != expected_host:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected_host:
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            value = cookie['iris_visual' if visual else 'iris_session'].value
        except (KeyError, ValueError):
            return False
        valid_cookie = self.server.visual_cookie_authorized(value) if visual else (
            value.isascii() and secrets.compare_digest(value,self.server.session))
        if visual and not self.server.visual_authorized(self.headers.get('X-IRIS-Visual')) and urlsplit(self.path).path != '/visual':
            return False
        return valid_cookie and (
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
            name, token = ('iris_visual', self.server._visual_cookie) if cookie == 'visual' else ('iris_session', self.server.session)
            self.send_header('Set-Cookie', name + '=' + token +
                             '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()

    def _send(self, code, body, kind='application/json', cookie=False):
        if code >= 400 and self.command == 'POST' and not self._body_read:
            # Brief bounded drain avoids Windows resetting replies with unread data.
            # Never wait the normal ten seconds on an unauthorized sender.
            try:
                lengths = self.headers.get_all('Content-Length', [])
                size = int(lengths[0]) if len(lengths) == 1 else 0
                if 0 < size <= 64000 and not self.headers.get('Transfer-Encoding'):
                    deadline = time.monotonic() + .05
                    while size > 0:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        self.connection.settimeout(remaining)
                        chunk = self.rfile.read1(min(size, 8192))
                        if not chunk:
                            break
                        size -= len(chunk)
            except (ValueError, OSError):
                pass
            finally:
                self.connection.settimeout(10)
            self.close_connection = True
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
        if len(raw) != size:
            raise ValueError('Incomplete request body.')
        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON field.')
                result[key] = item
            return result
        def invalid_constant(_):
            raise ValueError('Non-finite JSON number.')
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
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
                  '/native-standby.js': ('native-standby.js', 'text/javascript'),
                  '/dashboard.js': ('dashboard.js', 'text/javascript'),
                  '/organizer.js': ('organizer.js', 'text/javascript'),
                  '/jobs.js': ('jobs.js', 'text/javascript'),
                  '/experiences.js': ('experiences.js', 'text/javascript'),
                  '/business.js': ('business.js', 'text/javascript'),
                  '/visual': ('visual-workspace.html', 'text/html; charset=utf-8'),
                  '/visual-workspace.js': ('visual-workspace.js', 'text/javascript'),
                  '/visual-workspace.css': ('visual-workspace.css', 'text/css'),
                  '/visuals.js': ('visuals.js', 'text/javascript'),
                  '/pair.js': ('pair.js', 'text/javascript'),
                  '/voice-input.js': ('voice-input.js', 'text/javascript'),
                  '/desktop.css': ('desktop.css', 'text/css')}
        if path in assets:
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' and path != '/':
                self._json(403, {'error': 'Local access only.'})
                return
            filename, kind = assets[path]
            if path in ('/','/visual') and not self._authorized():
                self._send(200, b'<!doctype html><meta charset="utf-8"><title>Pair IRIS</title><p id="pairStatus">Open IRIS using its desktop or Chrome launcher to pair this window.</p><script src="/pair.js"></script>', 'text/html; charset=utf-8')
                return
            self._send(200, (ROOT / 'web' / filename).read_bytes(), kind)
            return
        if path == '/favicon.ico':
            self._send(204, b'')
            return
        if not self._authorized():
            self._json(403, {'error': 'Open IRIS in this browser first.'})
            return
        app = self.server.runtime
        try:
            if path == '/api/visual/state':
                if not self.server.visual_authorized(self.headers.get('X-IRIS-Visual')):
                    self._json(403, {'error':'Visual window session expired or closed.'});return
                self._json(200, app.visual_state())
            elif path == '/api/status':
                cfg = app.settings
                self._json(200, {'name': 'IRIS', 'brain': True, 'voice': bool(cfg.get('IRIS_FISH_API_KEY')),
                    'desktop_window': self.server.desktop_window,
                    'web_search': web_available(app.config),
                    'clap': {'engine': 'sounddevice', 'sample_rate': SAMPLE_RATE, 'block_ms': BLOCK_MS},
                    'speech': speech_status(cfg),
                    'model': app.config.model, 'voice_id': cfg.get('IRIS_FISH_VOICE_ID', ''),
                    'last_route': app.last_route, 'last_seconds': app.last_seconds,
                    'council': True, 'memory': True, 'tasks': True,
                    'organizer': app.autonomy.status(),
                    'obsidian': bool(app.config.obsidian_root or app.config.obsidian_vault),
                    'target': 'HP OMEN 16 · Core 7 240H · 16 GB · RTX 5060 · 1 TB SSD',
                    'provider_verified': False})
            elif path == '/api/approval':
                self._json(200, {'pending': app.pending_approval()})
            elif path == '/api/capabilities':
                self._json(200, app.capabilities())
            elif path == '/api/jobs':
                self._json(200, {'jobs': app.jobs.list()})
            elif path == '/api/experiences':
                self._json(200, {'items': app.experiences()})
            elif path == '/api/business':
                from iris.generalist.business import BusinessWorkspace
                self._json(200, {'items': BusinessWorkspace(app.memory_path).list()})
            elif path == '/api/markets':
                self._json(200, dashboard_markets())
            elif path == '/api/memories':
                self._json(200, {'items': app.memories()})
            elif path == '/api/tasks':
                self._json(200, {'items': app.tasks()})
            elif path == '/api/goals':
                self._json(200, {'items': app.goals()})
            elif path == '/api/activity':
                self._json(200, app.autonomy.events())
            elif path == '/api/notes':
                self._json(200, {'items': app.autonomy.notes()})
            elif path.startswith('/api/audio/'):
                self._stream_voice(app.consume_audio(path.removeprefix('/api/audio/')))
            else:
                self._json(404, {'error': 'Not found.'})
        except ValueError as exc:
            self._json(400, {'error': str(exc)})

    def _stream_voice(self, text):
        try:
            with self.server.limits.reserve('voice'), (self.server.runtime.provider_usage.reserve('fish_tts') if hasattr(self.server.runtime, 'provider_usage') else nullcontext()):
                self._stream_voice_reserved(text)
        except (UsageLimitError, ProviderLimitError) as exc:
            self._json(429, {'error': str(exc)})

    def _stream_voice_reserved(self, text):
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
        # A server-owned limiter is shared across windows. Reject before any
        # provider or database work; failures consume attempt capacity too.
        if not self._authorized(write=True):
            return self._post_dispatch()
        path = urlsplit(self.path).path
        group = {'/api/chat':'chat', '/api/transcribe':'transcribe',
                 '/api/jobs/start':'jobs', '/api/jobs/resume':'jobs'}.get(path)
        if path.startswith(('/api/business/', '/api/experiences/', '/api/notes/')):
            group = 'database'
        try:
            with ExitStack() as stack:
                stack.enter_context(self.server.limits.reserve('http'))
                if group:
                    stack.enter_context(self.server.limits.reserve(group))
                self._post_dispatch()
        except (UsageLimitError, ProviderLimitError) as exc:
            self._json(429, {'error': str(exc)})

    def _post_dispatch(self):
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get_all('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            self._json(400, {'error': 'Invalid request framing.'})
            return
        if urlsplit(self.path).path == '/api/pair':
            visual = self.headers.get('Host') == f'localhost:{self.server.server_address[1]}'
            origin = f'http://{"localhost" if visual else "127.0.0.1"}:{self.server.server_address[1]}'
            if (not self._trusted_host() or self.headers.get_all('Origin', []) != [origin]
                    or self.headers.get_all('X-IRIS-Request', []) != ['1']
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                self._json(403, {'error': 'Pairing rejected.'})
                return
            try:
                value = self._body()
                lease = self.server.redeem_visual(value.get('token')) if visual and set(value)=={'token'} else None
                valid = bool(lease) if visual else (set(value) == {'token'} and self.server.redeem_bootstrap(value['token']))
                if visual and not valid:self.server.redeem_bootstrap(None)  # Shared failed-attempt accounting only.
            except (ValueError, UnicodeError):
                valid = False;lease=None
            body={'ok':True,**({'visual_token':lease} if lease else {})} if valid else {'error':'Pairing rejected. Relaunch IRIS.'}
            self._send(200 if valid else 403, json.dumps(body).encode(), cookie=('visual' if lease else True) if valid else False)
            return
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
            if path == '/api/visual/update':
                if len(self.headers.get_all('X-IRIS-Visual',[]))!=1 or not self.server.visual_authorized(self.headers.get('X-IRIS-Visual')):
                    self._json(403, {'error':'Visual window session expired or closed.'});return
                self._json(200, app.update_visual(value))
            elif path == '/api/clap':
                owner = value.get('owner')
                if value.get('action') == 'update':
                    if type(value.get('busy')) is not bool:
                        raise ValueError('The microphone busy state must be true or false.')
                    result = self.server.clap_listener.update(owner, busy=value['busy'])
                elif value.get('action') == 'stop':
                    result = self.server.clap_listener.stop(owner)
                else:
                    raise ValueError('Choose update or stop for microphone standby.')
                self._json(200, result)
            elif path == '/api/weather':
                self._json(200, dashboard_weather(value.get('latitude'), value.get('longitude')))
            elif path == '/api/activity/undo':
                self._json(200, app.autonomy.undo(value.get('id')))
            elif path == '/api/reminders/ack':
                self._json(200, app.autonomy.acknowledge(value.get('id')))
            elif path == '/api/notes/read':
                self._json(200, app.autonomy.read_note(value.get('path')))
            elif path == '/api/organization':
                self._json(200, app.set_automatic_organization(value.get('enabled')))
            elif path == '/api/chat':
                self._json(200, app.chat(value.get('text'), value.get('mode', 'auto')))
            elif path == '/api/jobs/start':
                self._json(200, app.jobs.submit(value.get('topic'), request_id=value.get('request_id')))
            elif path == '/api/jobs/read':
                self._json(200, app.jobs.detail(value.get('id')))
            elif path == '/api/jobs/cancel':
                self._json(200, app.jobs.cancel(value.get('id')))
            elif path == '/api/jobs/resume':
                self._json(200, app.jobs.resume(value.get('id')))
            elif path == '/api/jobs/delete':
                app.jobs.delete(value.get('id'))
                self._json(200, {'ok': True})
            elif path == '/api/experiences/review':
                self._json(200, app.review_experience(value.get('id'), value.get('revision'), value.get('decision')))
            elif path == '/api/business/save':
                self._json(200, app.save_business(value))
            elif path == '/api/experiences/forget':
                app.forget_experience(value.get('id'), value.get('revision'))
                self._json(200, {'ok': True})
            elif path == '/api/approval':
                if type(value.get('approved')) is not bool:
                    raise ValueError('Choose approve or decline.')
                app.resolve_approval(value.get('id'), value['approved'])
                self._json(200, {'ok': True})
            elif path == '/api/reset':
                app.reset()
                self._json(200, {'ok': True})
            elif path == '/api/voice':
                text = value.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 12000:
                    raise ValueError('Invalid speech text.')
                text = normalize_tts_text(text)
                token = app.issue_audio(text) if text else None
                self._json(200, {'url': '/api/audio/' + token if token else None, 'fallback_text': text})
            else:
                self._json(404, {'error': 'Not found.'})
        except ProviderLimitError as exc:
            self._json(429, {'error': str(exc)})
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
        print('Chrome could not open. Install Chrome and restart the launcher.', flush=True)
        return False


def main(argv=None):
    from iris.desktop.instance import AlreadyRunning, instance_guard
    parser = argparse.ArgumentParser(description='IRIS unified desktop assistant')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        # Acquire ownership before initialization can recover live job records.
        with instance_guard(ROOT):
            try:
                runtime = DesktopRuntime()
            except Exception:
                print('IRIS needs configuration. Run setup.bat, then start-iris.bat.')
                return 1
            server = None
            browser_timer = None
            try:
                for port in range(args.port, min(args.port + 10, 65536)):
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
                    browser_timer = threading.Timer(0.5, open_browser, args=(server.bootstrap_url(),))
                    browser_timer.start()
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                return 0
            finally:
                if browser_timer is not None:
                    browser_timer.cancel()
                if server is not None:
                    server.server_close()
                else:
                    runtime.close()
    except AlreadyRunning:
        print('IRIS is already running. Open its existing desktop window or Chrome tab.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())

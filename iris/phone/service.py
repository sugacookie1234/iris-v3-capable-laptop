"""Fast webhook responses, queued replies, and PIN-gated phone conversations."""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import re
import secrets
import threading
import time
from xml.etree.ElementTree import Element, SubElement, tostring

EMPTY = b'<?xml version="1.0" encoding="utf-8"?><Response />'
FAILURE = 'I could not answer right now. Please try again shortly.'


def xml(root):
    return tostring(root, encoding='utf-8', xml_declaration=True)


def say(parent, text):
    SubElement(parent, 'Say', voice='man', language='en-US').text = text


def hangup(text=None):
    root = Element('Response')
    if text: say(root, text)
    SubElement(root, 'Hangup')
    return xml(root)


@dataclass
class Call:
    expires: float
    unlocked: bool = False
    attempts: int = 0
    turns: int = 0
    current: str = ''
    greeting: bytes = b''
    cache: dict[str, bytes] = field(default_factory=dict)
    pin_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    pin_cache: dict[str, bytes] = field(default_factory=dict)


class PhoneService:
    def __init__(self, config, store, assistant, transport, *, clock=time.time):
        self.config, self.store, self.assistant, self.transport = config, store, assistant, transport
        self.clock = clock
        self.lock = threading.RLock()
        self.calls, self.histories = {}, {}
        self.closed = threading.Event()
        self.worker = None

    def start(self):
        self.store.recover()
        self.store.maintenance()
        self.worker = threading.Thread(target=self._run, name='iris-phone-replies', daemon=True)
        self.worker.start()

    def close(self):
        self.closed.set()
        if self.worker: self.worker.join(timeout=2)

    def _run(self):
        last_cleanup = self.clock()
        while not self.closed.is_set():
            try:
                if not self.work_once(): self.closed.wait(.25)
                if self.clock() - last_cleanup > 60:
                    self.store.maintenance()
                    with self.lock: self._expire()
                    last_cleanup = self.clock()
            except Exception:
                # Do not log message bodies, numbers, PINs, tokens or provider exceptions.
                self.closed.wait(1)

    def work_once(self):
        job = self.store.claim()
        if job is None: return False
        with self.lock:
            self._expire()
            if job['channel'] == 'voice' and not self._live_call(job['session']):
                self.store.abort(job['id'])
                return True
            history = tuple(self.histories.get(job['session'], ()))
        try:
            reply = self.assistant.reply(job['prompt'], history=history, channel=job['channel'])
        except Exception:
            reply = FAILURE
        if self.closed.is_set():
            self.store.abort(job['id'])
            return True
        with self.lock:
            self._expire()
            if job['channel'] == 'voice' and not self._live_call(job['session']):
                self.store.abort(job['id'])
                return True
            current = self.store.get(job['id'])
            if not current or current['state'] != 'working': return True
            self.store.ready(job['id'], reply)
        if job['channel'] == 'sms':
            if not self.store.begin_send(job['id']): return True
            try:
                sid = self.transport.send_sms(reply)
                self.store.sent(job['id'], sid)
            except Exception:
                # A timeout can occur after carrier acceptance. Never auto-resend.
                self.store.uncertain(job['id'])
                return True
        with self.lock:
            if job['channel'] == 'sms' or self._live_call(job['session']):
                history = [*history, ('user', job['prompt']), ('assistant', reply)]
                self.histories[job['session']] = history[-16:]
        return True

    def _live_call(self, sid):
        call = self.calls.get(sid)
        return bool(call and call.unlocked and call.expires > self.clock())

    def _expire(self):
        for sid, call in list(self.calls.items()):
            if call.expires <= self.clock():
                self.calls.pop(sid, None)
                self.histories.pop(sid, None)

    def _pin_prompt(self, call):
        root = Element('Response')
        gather = SubElement(root, 'Gather', input='dtmf', numDigits='6', timeout='8',
            action=self.config.public_url + '/phone/voice/unlock/' + call.pin_token, method='POST', actionOnEmptyResult='true')
        say(gather, 'This is Iris. Enter your six digit access code.')
        SubElement(root, 'Hangup')
        return xml(root)

    def _gather(self, call, text):
        call.current = secrets.token_urlsafe(24)
        root = Element('Response')
        gather = SubElement(root, 'Gather', input='speech', language='en-CA', speechTimeout='auto',
            timeout='6', action=self.config.public_url + '/phone/voice/turn/' + call.current,
            method='POST', actionOnEmptyResult='true')
        say(gather, text)
        SubElement(root, 'Hangup')
        return xml(root)

    def _wait(self, token, initial=False):
        root = Element('Response')
        if initial: say(root, 'One moment.')
        SubElement(root, 'Pause', length='2')
        SubElement(root, 'Redirect', method='POST').text = self.config.public_url + '/phone/voice/poll/' + token
        return xml(root)

    def handle(self, path, form):
        """Called only after exact-URL signature and participant validation."""
        if path == '/phone/sms':
            sid = form.get('MessageSid', '')
            if not re.fullmatch(r'SM[0-9a-fA-F]{32}', sid): raise ValueError('Invalid message identifier.')
            text = form.get('Body', '').strip()
            opt = form.get('OptOutType', '').upper()
            if opt == 'STOP' or text.upper() in ('STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT', 'REVOKE', 'OPTOUT'):
                self.store.apply_opt_out(sid, True)
                return EMPTY
            if opt == 'START' or text.upper() in ('START', 'UNSTOP'):
                self.store.apply_opt_out(sid, False)
                return EMPTY
            if opt == 'HELP' or text.upper() in ('HELP', 'INFO'):
                return EMPTY  # Twilio owns the compliance reply; never send a duplicate.
            if not text or len(text) > 2000 or form.get('NumMedia', '0') != '0': return EMPTY
            try: self.store.enqueue('sms:' + sid, 'sms', 'sms-owner', text)
            except ValueError: pass  # Opt-out/backpressure: do not create a paid reply loop.
            return EMPTY
        if path == '/phone/status':
            sid = form.get('MessageSid') or form.get('CallSid', '')
            if not re.fullmatch(r'(?:SM|CA)[0-9a-fA-F]{32}', sid): raise ValueError('Invalid status identifier.')
            self.store.status(sid, form.get('MessageStatus') or form.get('CallStatus', ''))
            if form.get('CallStatus') in ('completed', 'canceled', 'failed', 'busy', 'no-answer'):
                with self.lock:
                    self.calls.pop(sid, None)
                    self.histories.pop(sid, None)
            return EMPTY
        sid = form.get('CallSid', '')
        if not re.fullmatch(r'CA[0-9a-fA-F]{32}', sid): raise ValueError('Invalid call identifier.')
        with self.lock:
            self._expire()
            call = self.calls.get(sid)
            if path == '/phone/voice':
                if call: return call.greeting if call.unlocked else self._pin_prompt(call)
                try:
                    if not self.store.register_call(sid): return hangup()
                except ValueError: return hangup()
                self.calls[sid] = Call(expires=self.clock() + 900)
                return self._pin_prompt(self.calls[sid])
            if not call: return hangup()
            if path.startswith('/phone/voice/unlock/'):
                token = path.rsplit('/', 1)[-1]
                if token in call.pin_cache: return call.pin_cache[token]
                if token != call.pin_token: return hangup()
                if call.unlocked: return call.greeting
                if call.attempts >= 3: return hangup()
                call.attempts += 1
                digits = form.get('Digits', '')
                if re.fullmatch(r'[0-9]{6}', digits) and hmac.compare_digest(digits, self.config.voice_pin):
                    call.unlocked = True
                    call.greeting = self._gather(call, 'Hello. Iris here. What would you like to ask?')
                    call.pin_cache[token] = call.greeting
                else:
                    call.pin_token = secrets.token_urlsafe(24)
                    call.pin_cache[token] = hangup('Access code not accepted.') if call.attempts >= 3 else self._pin_prompt(call)
                return call.pin_cache[token]
            if not call.unlocked: return hangup()
            token = path.rsplit('/', 1)[-1]
            if token in call.cache: return call.cache[token]
            if token != call.current: return hangup()
            job_id = 'voice:' + sid + ':' + token
            if path.startswith('/phone/voice/turn/'):
                if self.store.get(job_id): return self._wait(token)
                call.turns += 1
                if call.turns > 12:
                    call.cache[token] = hangup('Let us continue in a new call. Goodbye.')
                    return call.cache[token]
                text = form.get('SpeechResult', '').strip()
                if text.lower().rstrip('.!?') in ('goodbye', 'hang up', 'end call'):
                    call.cache[token] = hangup('Goodbye.')
                elif not text or len(text) > 2000:
                    call.cache[token] = self._gather(call, 'I did not catch that. Please ask again.')
                else:
                    try: self.store.enqueue(job_id, 'voice', sid, text)
                    except ValueError:
                        call.cache[token] = hangup('I am at my phone request limit. Please try later.')
                    else: return self._wait(token, initial=True)
                return call.cache[token]
            if path.startswith('/phone/voice/poll/'):
                job = self.store.get(job_id)
                if not job or job['session'] != sid: return hangup()
                if job['state'] in ('queued', 'working') and self.clock() - job['created'] < 90:
                    return self._wait(token)
                reply = job['reply'] if job['state'] == 'ready' else FAILURE
                if job['state'] != 'ready': self.store.abort(job_id)
                call.cache[token] = self._gather(call, reply)
                return call.cache[token]
            raise ValueError('Unknown phone callback.')

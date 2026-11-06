"""Explicit, durable benchmark admission. No network activity during preflight.

Only the existing OpenRouter-compatible transport is supported initially. Unknown
cost requires separate consent: a request ceiling is NOT a monetary ceiling.
"""
from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from iris.brain.llm import LLMResponse, LLMToolCall
from iris.usage import ProviderUsage


class AdmissionRefused(ValueError):
    pass


class ProviderAttemptFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveAuthorization:
    provider: str
    model: str
    scope_sha256: str
    max_calls: int
    duration: float
    authorize_contact: bool
    acknowledge_unknown_cost: bool

    def validate(self):
        if self.provider != 'openrouter':
            raise ValueError('Only the existing OpenRouter transport is supported.')
        if not isinstance(self.model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}',self.model):
            raise ValueError('An exact model identifier is required; no wildcard or fallback.')
        if not re.fullmatch('[a-f0-9]{64}',self.scope_sha256 or ''):
            raise ValueError('Confirm the exact synthetic scope fingerprint.')
        if type(self.max_calls) is not int or not 1 <= self.max_calls <= 100:
            raise ValueError('Explicit budget must be 1–100 underlying attempts.')
        if type(self.duration) not in (int,float) or not math.isfinite(self.duration) or not 0 < self.duration <= 600:
            raise ValueError('Explicit duration must be at most 600 seconds.')
        if self.authorize_contact is not True or self.acknowledge_unknown_cost is not True:
            raise ValueError('Explicit contact AND unknown-cost-risk authorization are required.')


class DurableRun:
    """Bind a run to immutable consent; reuse production atomic usage accounting.

    Restart never resets attempts/deadline. Any unfinished attempt blocks recovery.
    The owner may inspect evidence, but this interface never clears reservations.
    """
    def __init__(self, directory, authorization, *, clock=time.time):
        authorization.validate()
        self.directory = Path(directory)
        if self.directory.is_symlink():
            raise ValueError('Choose a dedicated regular result directory.')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.authorization, self.clock = authorization, clock
        self.path = self.directory/'benchmark-admission.sqlite3'
        if self.path.is_symlink():
            raise ValueError('Admission ledger cannot be a symlink.')
        payload = json.dumps(asdict(authorization),sort_keys=True,separators=(',',':'))
        self.session = hashlib.sha256(payload.encode()).hexdigest()
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS benchmark_run (id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT NOT NULL, deadline REAL NOT NULL, stopped INTEGER NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT policy,deadline,stopped FROM benchmark_run WHERE id=1').fetchone()
            if row is None:
                self.deadline = clock()+authorization.duration
                db.execute('INSERT INTO benchmark_run VALUES (1,?,?,0)',(payload,self.deadline))
            else:
                if row[0] != payload or row[2]:
                    raise ValueError('Changed or closed run; consent cannot reset this ledger.')
                self.deadline = row[1]
                exists = db.execute("SELECT name FROM sqlite_master WHERE name='provider_attempts'").fetchone()
                if exists and db.execute("SELECT COUNT(*) FROM provider_attempts WHERE state='reserved'").fetchone()[0]:
                    raise ValueError('Interrupted attempt requires review; no automatic resumption.')
            db.commit()
        self.usage = ProviderUsage(self.path,{'IRIS_PROVIDER_LIMIT_SESSION':authorization.max_calls,
            'IRIS_PROVIDER_LIMIT_HOUR':authorization.max_calls,'IRIS_PROVIDER_LIMIT_DAY':authorization.max_calls},
            session=self.session,clock=clock)
        self.monotonic_deadline = time.monotonic()+max(0,self.deadline-clock())
        self.cancelled = threading.Event()

    def check(self, request):
        if request.model != self.authorization.model or request.tools or request.web_search:
            raise ValueError('Target changed or unsupported native tools/research requested.')
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            row = db.execute('SELECT stopped FROM benchmark_run WHERE id=1').fetchone()
        if not row or row[0] or self.cancelled.is_set() or self.remaining() <= 0:
            raise ValueError('Run cancelled, closed or expired.')

    def remaining(self):
        return max(0,min(self.deadline-self.clock(),self.monotonic_deadline-time.monotonic()))

    def stop(self):
        self.cancelled.set()
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('UPDATE benchmark_run SET stopped=1 WHERE id=1')
            db.commit()

    def attempts(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='provider_attempts'").fetchone():
                return []
            return [{'state':row[0],'started':row[1]} for row in db.execute('SELECT state,started FROM provider_attempts ORDER BY started,id')]


def transport_worker(connection, request, timeout, session):
    """Existing transport keeps existing owner protections; no alternate HTTP client."""
    try:
        from iris.brain.providers.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider
        key = os.environ.get('IRIS_BENCHMARK_API_KEY','')
        if not key:
            raise ValueError('Missing explicitly supplied benchmark credential.')
        from iris.usage import default_usage
        usage = default_usage()
        usage.session = session # One durable benchmark session across all child adapters.
        provider = OpenAICompatibleProvider(OpenAICompatibleConfig(name='openrouter',
            base_url='https://openrouter.ai/api',api_key=key,timeout_seconds=timeout,usage=usage))
        # generate() uses default_usage(): normal configured provider limits still apply.
        response = provider.generate(request)
        connection.send_bytes(json.dumps({'response':asdict(response)},allow_nan=False).encode())
    except BaseException:
        # Do not send exception text, credentials, headers or echoed prompts.
        connection.send_bytes(b'{"error":"provider_failed_or_interrupted"}')
    finally:
        connection.close()


def bounded_transport(request, run, *, worker=transport_worker):
    context = multiprocessing.get_context('spawn')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=worker,args=(send,request,max(.01,run.remaining()),run.session),daemon=True)
    try:
        process.start()
        send.close()
        while not receive.poll(.025):
            run.check(request)
            if not process.is_alive():
                raise RuntimeError('Provider worker exited without a result.')
        run.check(request)
        value = json.loads(receive.recv_bytes(2_000_000))
        if 'response' not in value:
            raise RuntimeError('Provider failed; no automatic retry.')
        data = value['response']
        data['tool_calls'] = tuple(LLMToolCall(**call) for call in data.get('tool_calls',[]))
        response = LLMResponse(**data)
        if response.provider != run.authorization.provider or response.model != run.authorization.model:
            raise ValueError('Unexpected provider/model response.')
        return response
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
        send.close()
        receive.close()


class LiveBenchmarkProvider:
    """Adapter accounting includes Council calls; all failures stop the run."""
    def __init__(self, run, *, transport=bounded_transport):
        self.run, self.transport = run, transport
        self.name, self.model = run.authorization.provider, run.authorization.model
        self.attempts = []
        self.lock = threading.Lock()
        self.reviews = []
        self.responses = []  # Synthetic benchmark output; persisted only in local review artifacts.

    def generate(self, request):
        try:
            self.run.check(request)
        except ValueError:
            raise AdmissionRefused('Run admission refused before provider invocation.') from None
        started = time.monotonic()
        with self.run.usage.reserve('model'):
            self.run.check(request)
            record = {'provider':self.name,'model':request.model,'status':'started',
                      'input_tokens':None,'output_tokens':None,'cost':None,'seconds':None,
                      'settings':asdict(request.options)}
            with self.lock:
                self.attempts.append(record)
            try:
                response = self.transport(request,self.run)
                self.run.check(request)
                if response.provider != self.name or response.model != self.model:
                    raise ValueError('Provider/model changed after authorization.')
                record.update(status='completed',
                    input_tokens=response.input_tokens if type(response.input_tokens) is int and response.input_tokens>=0 else None,
                    output_tokens=response.output_tokens if type(response.output_tokens) is int and response.output_tokens>=0 else None)
                self.responses.append(response.text)
                return response
            except BaseException as error:
                record['status'] = 'failed_or_cancelled_billing_unknown'
                self.run.stop()
                if isinstance(error,KeyboardInterrupt):
                    raise
                raise ProviderAttemptFailed('Attempt failed/cancelled; billing is unknown and run is stopped.') from None
            finally:
                record['seconds'] = time.monotonic()-started

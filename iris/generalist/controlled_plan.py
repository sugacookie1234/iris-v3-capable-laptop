"""Three-step workspace proposals. Preview is data, never execution authority."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time
import threading
from datetime import datetime, timezone
from uuid import uuid4

from iris.generalist.plan import PlanLimits, validate_plan
from iris.generalist.interpretation import ContextRef, _pairs
from iris.memory.working import Source
from iris.tools import Approval, AuthorityContext, RequestOrigin, ResultStatus, ToolCall
from iris.tools.workspace import _safe_parts, _is_hidden_or_credential, TEXT_SUFFIXES, TEXT_FILENAMES
from pathlib import PurePosixPath

ALLOWED = frozenset({'workspace_list', 'workspace_read'})
LIMITS = PlanLimits(max_nodes=3, max_seconds=90, max_argument_chars=1000)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class ProposedPlanV1:
    turn: str
    objective: str
    nodes: tuple
    context_refs: tuple[ContextRef, ...]


def parse_proposal(raw, turn):
    if type(raw) is not str or len(raw) > 12000:
        raise ValueError('Invalid proposal size.')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite proposal.')))
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError('Invalid proposal JSON.') from error
    if (type(value) is not dict or set(value) != {'version','turn','objective','nodes','context_refs'}
            or type(value['version']) is not int or value['version'] != 1 or value['turn'] != turn):
        raise ValueError('Invalid proposal fields, version or turn.')
    if type(value['nodes']) is not list or not 1 <= len(value['nodes']) <= 3:
        raise ValueError('Use one to three steps.')
    refs = value['context_refs']
    if type(refs) is not list or len(refs) > 3:
        raise ValueError('Invalid context references.')
    parsed = []
    for ref in refs:
        if (type(ref) is not dict or set(ref) != {'id','revision'} or type(ref['id']) is not str
                or not re.fullmatch('[a-f0-9]{32}',ref['id']) or type(ref['revision']) is not int
                or not 0 <= ref['revision'] <= 10**9):
            raise ValueError('Invalid context reference.')
        item = ContextRef(**ref)
        if item in parsed:
            raise ValueError('Duplicate context reference.')
        parsed.append(item)
    return ProposedPlanV1(turn, value['objective'], tuple(value['nodes']), tuple(parsed))


def safe_arguments(name, arguments):
    """Lexical validation only: no filesystem observation during preview."""
    args = dict(arguments)
    path = args.get('path', '.')
    if type(path) is not str or len(path) > 500 or any(c in path for c in ('\x00','\n','\r','$','{','}')):
        raise ValueError('Use a concrete bounded workspace path, not an output reference.')
    parts = _safe_parts(path)
    if any(_is_hidden_or_credential(part) for part in parts):
        raise ValueError('Credential-like paths cannot be planned.')
    if name == 'workspace_read':
        if not parts or (PurePosixPath(parts[-1]).suffix.lower() not in TEXT_SUFFIXES and parts[-1] not in TEXT_FILENAMES):
            raise ValueError('Select a supported text file.')
        if type(args.get('max_chars',16000)) is not int or not 1 <= args.get('max_chars',16000) <= 16000:
            raise ValueError('Invalid text read limit.')
    return args


@dataclass(frozen=True)
class HostPlan:
    id: str
    revision: int
    turn: str
    session: str
    request_digest: str
    expires: float
    plan: object
    prepared: tuple
    context_json: str
    refs: tuple

    @property
    def digest(self):
        return digest({'id':self.id,'revision':self.revision,'turn':self.turn,'session':self.session,
            'request':self.request_digest,'expires':self.expires,'plan':asdict(self.plan),
            'prepared':[{'spec':asdict(p.spec),'arguments':p.arguments,'origin':p.origin} for p in self.prepared],
            'context':self.context_json,'refs':[asdict(ref) for ref in self.refs]})


def validate_proposal(proposal, *, request, turn, session, executor, permissions, working, orchestrator,
                      clock=time.monotonic):
    if (type(proposal) is not ProposedPlanV1 or proposal.turn != turn or
            not request.startswith('/plan workspace ') or not request[16:].strip() or executor is None):
        raise ValueError('An explicit workspace planning request and registered executor are required.')
    specs = tuple(spec for spec in executor.specifications() if spec.name in ALLOWED)
    raw = {'objective':proposal.objective,'nodes':list(proposal.nodes)}
    first = validate_plan(raw,specs,permissions=permissions,limits=LIMITS)
    state = working.snapshot(orchestrator)
    for ref in proposal.context_refs:
        item = working.resolve(ref,orchestrator)
        if item['source'] not in (Source.OWNER, Source.HOST):
            raise ValueError('Model inferences cannot ground an executable plan.')
    prepared, nodes = [], []
    for identifier in first.order:
        node = next(n for n in first.nodes if n.id == identifier)
        safe_arguments(node.tool,node.arguments)
        preview = executor.execute(ToolCall(node.tool,dict(node.arguments),RequestOrigin.MODEL),
            authority=AuthorityContext(permissions=frozenset(permissions)),dry_run=True)
        if preview.status != ResultStatus.PREVIEW or preview.plan is None:
            raise ValueError('Tool preparation or permissions prevented preview.')
        safe_arguments(node.tool,preview.plan.arguments)
        prepared.append(preview.plan)
        nodes.append({'id':node.id,'tool':node.tool,'arguments':dict(preview.plan.arguments),
                      'depends_on':list(node.depends_on)})
    # Validate canonical prepared arguments and actual registered specs again.
    plan = validate_plan({'objective':first.objective,'nodes':nodes},specs,
                         permissions=permissions,limits=LIMITS)
    return HostPlan(uuid4().hex,1,turn,session,digest(request),clock()+300,plan,
                    tuple(prepared),canonical(state),proposal.context_refs)


def preview_text(plan, *, executable=False):
    lines = ['Proposed objective (not verified): '+plan.plan.objective,
             'No actions have been executed yet. Files have not been checked for existence.']
    for node in plan.plan.nodes:
        output = 'bounded directory entries, not file contents' if node.tool=='workspace_list' else 'a bounded UTF-8 text snapshot, not a correctness assessment'
        lines.append(f'{node.id}: {node.tool} {canonical(dict(node.arguments))}; after: '
            + (', '.join(node.depends_on) or 'none') + '; requires: '+', '.join(node.required_permissions)
            + '; separate approval required; output: '+output+'.')
    lines += [('Execution is available after exact confirmation and per-step approval; up to ' if executable
               else 'Execution is not enabled in this preview-only checkpoint. Proposed budget: ')
              +str(plan.plan.total_tool_timeout_seconds)+' tool seconds. Expires in five minutes.',
              'No dynamic file selection, output interpolation, cloud synthesis or file writes.',
              f'Plan {plan.id}, revision {plan.revision}, digest {plan.digest}']
    if executable:
        lines += [f'/confirm-plan {plan.id} {plan.revision} {plan.digest}',f'/cancel-plan {plan.id}']
    return '\n'.join(lines)


PLAN_PROMPT = '''Return only JSON with version:1, turn: supplied host turn, objective: concise unverified objective,
nodes: one to three objects {id: lowercase identifier, tool: registered name, arguments: exact schema values,
depends_on: earlier node IDs}, context_refs: [] or exact permitted host {id,revision} references.
Only listed workspace tools are available. Use concrete relative paths; do not invent file existence.
No output interpolation, code, permissions, approvals, provenance or result claims. Steps may depend on
completion only, never arbitrary tool output. If relevant files are unknown, plan listing only.
The host will validate and preview; nothing executes until explicit owner confirmation and approval.
'''


def verify_result(node, value):
    """Verify returned snapshots, not file correctness or an arbitrary objective."""
    args = dict(node.arguments)
    expected_path = '/'.join(_safe_parts(args.get('path','.'))) or '.'
    if type(value) is not dict or value.get('path') != expected_path or type(value.get('truncated')) is not bool:
        raise ValueError('Invalid returned snapshot.')
    if node.tool == 'workspace_list':
        if set(value) != {'path','entries','truncated'} or type(value['entries']) is not list or len(value['entries']) > 200:
            raise ValueError('Invalid directory result.')
        seen = set()
        for entry in value['entries']:
            if (type(entry) is not dict or set(entry) != {'name','type','size'}
                    or type(entry['name']) is not str or not 1 <= len(entry['name']) <= 255
                    or any(c in entry['name'] for c in ('/','\\','\x00','\n','\r'))
                    or entry['name'] in seen or _is_hidden_or_credential(entry['name'])
                    or entry['type'] not in ('file','directory','other')
                    or (entry['size'] is not None and (type(entry['size']) is not int or entry['size'] < 0))):
                raise ValueError('Invalid directory entry.')
            seen.add(entry['name'])
        return f"Validated {len(value['entries'])} returned directory entries; file contents were not inspected." + (' Listing was truncated.' if value['truncated'] else '')
    if node.tool == 'workspace_read':
        if set(value) != {'path','text','truncated'} or type(value['text']) is not str or len(value['text']) > args.get('max_chars',16000):
            raise ValueError('Invalid text result.')
        return f"Validated a returned text snapshot of {len(value['text'])} characters; document correctness was not assessed." + (' Text was truncated.' if value['truncated'] else '')
    raise ValueError('No verifier for this capability.')


@dataclass(frozen=True)
class ExecutionReceipt:
    version: int
    plan_id: str
    revision: int
    step_id: str
    capability: str
    argument_digest: str
    origin: str
    approval: str
    started: str
    finished: str
    status: str
    verification: str
    evidence_ref: str | None
    failure: str | None
    cancelled: bool
    uncertain: bool
    summary: str


class PlanRun:
    """One session-owned read-only run. Restart invalidates all pending authority.

    Lifecycle: awaiting_confirmation -> running/awaiting_approval/verifying ->
    completed/failed/cancelled/uncertain. Terminal runs are never replayed.
    Existing ActionHistory persists invocation evidence; private outputs stay transient.
    """
    def __init__(self, plan, *, executor, permissions, working, orchestrator, clock=time.monotonic, journal=None):
        self.plan = plan
        self.bound_digest = plan.digest
        self.executor = executor
        self.permissions = permissions
        self.working = working
        self.orchestrator = orchestrator
        self.clock = clock
        self.cancel_event = threading.Event()
        self.lock = threading.Lock()
        self.state = 'awaiting_confirmation'
        self.receipts = []
        self.active_step = None
        self.journal = journal
        self._checkpoint()

    def _checkpoint(self):
        if self.journal is not None:
            self.journal(self)

    def cancel(self, identifier):
        with self.lock:
            if identifier != self.plan.id or self.state in ('completed','failed','cancelled','uncertain'):
                return False
            self.cancel_event.set()
            if self.state == 'awaiting_confirmation':
                self.state = 'cancelled'
                try:
                    self._checkpoint()
                except Exception:
                    self.state = 'uncertain'  # Stop even when persistence failed.
            return True

    def _validate(self):
        if self.journal is not None:
            self.journal.validate()
        if self.cancel_event.is_set() or self.clock() >= self.plan.expires or self.plan.digest != self.bound_digest:
            raise ValueError('Cancelled, expired or changed plan.')
        self.working.validate_snapshot(json.loads(self.plan.context_json),self.orchestrator)
        specs = {spec.name:spec for spec in self.executor.specifications()}
        permissions = frozenset(self.permissions())
        for node, prepared in zip(self.plan.plan.nodes,self.plan.prepared):
            if (node.tool not in ALLOWED or specs.get(node.tool) != prepared.spec
                    or not set(node.required_permissions).issubset(permissions)):
                raise ValueError('Capability or permission changed.')
        return permissions

    def execute(self, identifier, revision, confirmed_digest, *, session, approve):
        with self.lock:
            if (self.state != 'awaiting_confirmation' or identifier != self.plan.id
                    or type(revision) is not int or revision != self.plan.revision
                    or confirmed_digest != self.bound_digest or session != self.plan.session):
                raise ValueError('Confirmation does not match the current pending plan.')
            self.state = 'running'  # Consume confirmation before any effect.
        completed = set()
        for node, prepared in zip(self.plan.plan.nodes,self.plan.prepared):
            started = datetime.now(timezone.utc).isoformat()
            approval_state = 'not_requested'
            result = None
            status, verification, failure, uncertain = 'failed','not_executed','validation_failed',False
            summary = 'Not executed: authority, context or validity changed.'
            try:
                permissions = self._validate()
                if not set(node.depends_on).issubset(completed):
                    raise ValueError('Dependency was not verified.')
                self.active_step = node.id
                self._checkpoint()  # Durable attempted-state before invoking any tool.
                def approval_callback(operation):
                    nonlocal approval_state
                    self.state = 'awaiting_approval'
                    approval_state = 'required'
                    self._validate()
                    self._checkpoint()
                    decision = approve(operation)
                    self._validate()
                    approval_state = ('approved' if isinstance(decision,Approval)
                        and decision.plan_id == operation.id and decision.approved is True else 'rejected')
                    self.state = 'running'
                    self._checkpoint()
                    return decision
                result = self.executor.execute(ToolCall(node.tool,dict(prepared.arguments),RequestOrigin.MODEL),
                    authority=AuthorityContext(permissions=permissions),approve=approval_callback,
                    cancelled=self.cancel_event.is_set,expected=prepared,require_audit=True)
                if result.status == ResultStatus.SUCCESS:
                    self.state = 'verifying'
                    status, verification, failure, uncertain = 'uncertain','unverified','verification_failed',True
                    summary = 'Tool returned, but its data was not verified. No later step executed.'
                    self._checkpoint()
                    summary = verify_result(node,result.value)
                    if self.executor.observer_failed or not result.receipt_id:
                        raise ValueError('Durable invocation evidence unavailable.')
                    status, verification, failure, uncertain = 'completed','validated_returned_data',None,False
                    completed.add(node.id)
                else:
                    failure = str(result.failure.code) if result.failure else 'execution_failed'
                    status = 'cancelled' if self.cancel_event.is_set() or failure=='cancelled' else 'failed'
                    uncertain = failure in ('timeout','execution_failed','cancelled')
                    verification = 'unknown' if uncertain else 'not_executed'
                    summary = 'Read did not complete with verified data. No later step executed.'
            except Exception:
                if self.cancel_event.is_set():
                    status = 'cancelled'
            except BaseException:
                self.state = 'uncertain'
                self.cancel_event.set()
                raise  # The invocation observer records interruption; never auto-replay.
            receipt = ExecutionReceipt(1,self.plan.id,self.plan.revision,node.id,node.tool,
                digest({'capability':node.tool,'arguments':dict(prepared.arguments)}),RequestOrigin.MODEL.value,
                approval_state,started,datetime.now(timezone.utc).isoformat(),status,verification,
                result.receipt_id if result else None,failure,self.cancel_event.is_set(),uncertain,summary)
            self.receipts.append(receipt)
            self.state = status if status != 'completed' else 'running'
            self.active_step = None
            try:
                self._checkpoint()
            except Exception:
                from dataclasses import replace
                self.receipts[-1] = replace(receipt, status='uncertain', verification='unknown',
                    uncertain=True, summary='Durable workflow evidence could not be saved; outcome cannot be confirmed.')
                self.state = 'uncertain'
                self.cancel_event.set()
                break
            if status != 'completed':
                self.state = status
                break
        else:
            self.state = 'completed'
            try:
                self._checkpoint()
            except Exception:
                self.state = 'uncertain'
                self.cancel_event.set()
        return self.report()

    def report(self):
        verified = sum(r.status == 'completed' for r in self.receipts)
        remaining = len(self.plan.plan.nodes)-len(self.receipts)
        lines = [f'Plan {self.state}: {verified} of {len(self.plan.plan.nodes)} steps returned verified data; '
                 f'{remaining} later steps were not executed.']
        lines.extend(f'{r.step_id}: {r.status}. {r.summary}' for r in self.receipts)
        lines.append('These receipts verify bounded returned data, not the correctness of your project. '
                     'No file was modified and no result was sent for cloud synthesis. Completed reads are not undone by cancellation.')
        return '\n'.join(lines)

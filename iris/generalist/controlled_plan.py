"""Three-step workspace proposals. Preview is data, never execution authority."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time
from uuid import uuid4

from iris.generalist.plan import PlanLimits, validate_plan
from iris.generalist.interpretation import ContextRef, _pairs
from iris.memory.working import Source
from iris.tools import AuthorityContext, RequestOrigin, ResultStatus, ToolCall
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

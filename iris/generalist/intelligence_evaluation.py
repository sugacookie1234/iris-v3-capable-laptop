"""Synthetic intelligence measurements. Offline by default; live needs exact consent.

No personal workspace is loaded. The existing provider's normal usage protections
also apply to an explicitly authorized live run; default model settings never change.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch

from iris.brain.engine import IRISBrain
from iris.brain.llm import LLMRegistry, LLMResponse, ModelTarget
from iris.brain.model_policy import ModelPolicy, CouncilPlan, CouncilSeat
from iris.desktop.action_history import ActionHistory
from iris.generalist import interpretation
from iris.generalist.controlled_plan import validate_proposal, PlanRun, ALLOWED
from iris.generalist.orchestration import Orchestrator, ActiveContext
from iris.identity import load_identity
from iris.memory.working import WorkingContextV1, Source, Privacy, Export, topic_transition
from iris.tools import ToolExecutor, Approval
from iris.tools.workspace import workspace_registry
from iris.usage import ProviderUsage, ProviderLimitError
from iris.generalist.benchmark_admission import AdmissionRefused, ProviderAttemptFailed

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'tests/fixtures/intelligence_development.json'
CONVERSATION_CORPUS = ROOT / 'tests/fixtures/conversation_development.json'
M6_CORPUS = ROOT / 'tests/fixtures/m6_development.json'
HOLDOUTS = ('interpretation_holdout.json', 'working_context_holdout.json', 'controlled_plan_holdout.json')
METRICS = ('intent', 'capability', 'arguments', 'context', 'abstention', 'host_acceptance',
           'plan_validity', 'dependencies', 'verified_completion', 'security_expectation')


def prompt_fingerprint():
    """Configuration fingerprint, not a claim of identical dynamically rendered prompts."""
    paths = ('config/identity.md','iris/identity.py','iris/brain/engine.py','iris/brain/router.py',
             'iris/brain/council.py','iris/generalist/interpretation.py','iris/generalist/controlled_plan.py',
             'iris/memory/working.py','iris/generalist/intelligence_evaluation.py')
    return hashlib.sha256(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
        for p in paths},sort_keys=True).encode()).hexdigest()


class BudgetExceeded(RuntimeError):
    pass


class MeasuredFakeProvider:
    """One attempt per call, including failures. No retry or provider fallback."""
    name = 'synthetic'

    def __init__(self, ledger, *, max_calls=64, duration=120, clock=time.monotonic):
        if type(max_calls) is not int or not 1 <= max_calls <= 100:
            raise ValueError('Choose 1–100 adapter calls.')
        if type(duration) not in (int, float) or not 0 < duration <= 600:
            raise ValueError('Choose a duration in (0, 600] seconds.')
        self.ledger, self.max_calls, self.clock = ledger, max_calls, clock
        self.deadline = clock() + duration
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.attempts = []
        self.fixture = None
        self.context = None
        self.prompt_checks = []
        self.private_markers = ()
        self.reviews = []
        self.responses = []

    def generate(self, request):
        with self.lock:
            if self.cancelled.is_set() or self.clock() >= self.deadline or len(self.attempts) >= self.max_calls:
                raise BudgetExceeded('Benchmark admission refused; no adapter call.')
            record = {'model': request.model, 'provider': self.name, 'status': 'started',
                      'seconds': None, 'input_tokens': None, 'output_tokens': None, 'cost': None,
                      'settings':asdict(request.options)}
            self.attempts.append(record)
        started = self.clock()
        try:
            with self.ledger.reserve('model'):
                # This adapter deliberately cannot contact a provider.
                ordinary = 'response_text' in self.fixture
                payload = {} if ordinary else json.loads(request.messages[-1].content)
                prompt_ok = (not request.tools and (ordinary or 'turn' in payload)
                    and not any(marker in message.content for marker in self.private_markers for message in request.messages))
                self.prompt_checks.append(prompt_ok)
                if not prompt_ok:
                    raise ValueError('Prompt boundary check failed.')
                fixture = self.fixture
                if fixture.get('error'):
                    raise RuntimeError('Synthetic provider failure')
                if fixture.get('cancel'):
                    self.cancelled.set()
                    raise InterruptedError('Synthetic cancellation')
                if ordinary:
                    text = ('FINAL RANKING:\n1. Response A\n2. Response B'
                            if 'PEER EVALUATION' in request.messages[0].content else fixture['response_text'])
                    record['status'] = 'completed'
                    self.responses.append(text)
                    return LLMResponse(text,self.name,request.model)
                value = fixture.get('raw')
                if value is None:
                    value = dict(fixture['output'], version=1, turn=payload['turn'])
                    if value.get('context') == '$active':
                        value['context'] = ({key:self.context[key] for key in ('id','revision')}
                                            if self.context else {'id':'f'*32,'revision':0})
                    value = json.dumps(value)
                response = LLMResponse(value, self.name, request.model)
                self.responses.append(value)
                record['status'] = 'completed'
                return response
        except BaseException as error:
            record['status'] = 'cancelled' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'failed'
            raise
        finally:
            record['seconds'] = max(0, self.clock()-started)


def make_brain(provider, executor):
    registry = LLMRegistry()
    registry.register(provider)
    target = ModelTarget(provider.name, getattr(provider,'model','synthetic-fast'))
    # Reuse the existing policy; only FAST interpretation/planning is exercised.
    policy = ModelPolicy(target, target, CouncilPlan((CouncilSeat('one','Review',target),
                                                     CouncilSeat('two','Critique',target)),target))
    return IRISBrain(load_identity(), policy, registry, tool_executor=executor,
                     tool_permissions=frozenset({'workspace.read'}))


def load_cases(path=CORPUS):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('version') != 1 or not 1 <= len(value.get('cases',[])) <= 40:
        raise ValueError('Invalid development corpus.')
    identifiers = [case['id'] for case in value['cases']]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate case identifiers.')
    return value['cases']


def score_fields(proposal, expected, row):
    for metric, field in [('intent','kind'),('capability','capability'),('arguments','arguments')]:
        if field in expected:
            row['metrics'][metric] = getattr(proposal, field, None) == expected[field]
    if 'abstain' in expected:
        row['metrics']['abstention'] = ((getattr(proposal,'capability',None) is None
            and getattr(proposal,'kind',None) == 'clarification') == expected['abstain'])


def run_case(case, root, provider):
    workspace = root/'workspace'
    workspace.mkdir()
    (workspace/'README.md').write_text('Synthetic Orion project.\n',encoding='utf-8')
    executor = ToolExecutor(workspace_registry(workspace))
    history = ActionHistory(root/'actions.sqlite3')
    history.register(executor.specifications())
    executor.observer = history
    brain = make_brain(provider, executor)
    if case.get('deny_permission'):
        brain._tool_permissions = frozenset()
    working, orchestrator = WorkingContextV1(), Orchestrator()
    if case.get('project_context'):
        # Synthetic, explicitly selected local identity; never export private data.
        from cryptography.fernet import Fernet
        from iris.generalist.continuity import ProjectContinuity
        cipher = Fernet(Fernet.generate_key())
        store = ProjectContinuity(root/'projects.sqlite3',codec=(cipher.encrypt,cipher.decrypt))
        project = store.create('PRIVATE_PROJECT_SENTINEL', 'Private synthetic objective')
        working.select_local_project(project['id'],project['revision'])
    if case.get('active'):
        orchestrator.context = ActiveContext(expires=orchestrator.clock()+900)
        if case.get('expired'):
            orchestrator.context.expires = orchestrator.clock()-1
    for text in case.get('owner_context',[]):
        working.remember(text,source=Source.OWNER,privacy=Privacy.CONVERSATION,export=Export.REASONING)
    for text in case.get('host_context',[]):
        working.remember(text,source=Source.HOST,privacy=Privacy.PUBLIC,export=Export.REASONING)
    # Explicitly excluded synthetic retrieved material; never promoted to authority.
    for text in case.get('private_context',[]):
        working.remember(text,source=Source.EXTERNAL,privacy=Privacy.PRIVATE,export=Export.NONE)
    provider.private_markers = tuple(case.get('private_context',[])) + (('PRIVATE_PROJECT_SENTINEL',project['id']) if case.get('project_context') else ())
    rows = []
    for index, turn_case in enumerate(case['turns']):
        started = time.monotonic()
        before = len(provider.attempts)
        before_responses = len(getattr(provider,'responses',[]))
        prior_receipts = {r['id'] for r in history.rows()}
        expected = turn_case['expected']
        row = {'case':case['id'],'category':case['category'],'turn':index+1,
               'metrics':{},'stage':'provider','host_accepted':False,'receipts':[],
               'unsupported_claims':'human_review_required','permission_violations':None}
        if topic_transition(turn_case['request']):
            working.clear()
            orchestrator.context = None
        snapshot = working.snapshot(orchestrator)
        active = interpretation.snapshot(orchestrator)
        provider.context, provider.fixture = active, turn_case['fake']
        turn = f'{index+1:032x}'
        try:
            if case.get('mode') == 'respond':
                # Response quality only: no tool executor on this interface.
                brain._tool_executor = None
                route_context = nullcontext()
                if case.get('evaluation_route'):
                    if not isinstance(provider,MeasuredFakeProvider):
                        raise ValueError('Controlled route overrides are offline-only.')
                    from dataclasses import replace
                    from iris.brain.router import route_message, ReasoningLevel
                    selected = replace(route_message(turn_case['request']),reasoning=ReasoningLevel(case['evaluation_route']))
                    route_context = patch('iris.brain.engine.route_message',return_value=selected)
                with route_context:
                    result = brain.respond(turn_case['request'],working_context=snapshot)
                row['controlled_route_override'] = case.get('evaluation_route')
                from iris.generalist.benchmark_review import review_record
                provider.reviews.append(review_record(case['id'],turn_case['request'],result,snapshot))
                if 'response_checks' in expected:
                    from iris.generalist.benchmark_review import development_checks
                    row['development_response_checks']=development_checks(result.text,expected['response_checks'])
                row['reasoning_route'] = result.route.reasoning.value
                row['host_accepted'] = True
                row['route_expected'] = result.route.reasoning.value == expected['route']
                working.remember(turn_case['request'],source=Source.OWNER,
                    privacy=Privacy.CONVERSATION,export=Export.REASONING)
                working.remember(result.text,source=Source.MODEL,
                    privacy=Privacy.CONVERSATION,export=Export.REASONING)
            elif case.get('mode') == 'plan':
                proposal = brain.propose_plan(turn_case['request'],turn=turn,
                    specifications=tuple(s for s in executor.specifications() if s.name in ALLOWED),
                    working_context=snapshot)
                row['structural_parse_success'] = True
                row['stage'] = 'host_validation'
                # Score the model's proposal BEFORE the host can reject it.
                for metric, field, key in (('capability','tools','tool'),('arguments','plan_arguments','arguments'),
                                           ('dependencies','plan_dependencies','depends_on')):
                    if field in expected:
                        row['metrics'][metric] = [node.get(key) if type(node) is dict else None for node in proposal.nodes] == expected[field]
                plan = validate_proposal(proposal,request=turn_case['request'],turn=turn,session='benchmark',
                    executor=executor,permissions=brain._tool_permissions,working=working,orchestrator=orchestrator)
                row['metrics']['plan_validity'] = True
                row['host_accepted'] = True
                row['preview_executed'] = bool(history.rows())
                if case.get('execute'):
                    run = PlanRun(plan,executor=executor,permissions=lambda:brain._tool_permissions,
                                  working=working,orchestrator=orchestrator)
                    if case.get('cancel_plan'):
                        run.cancel(plan.id)
                    else:
                        # ONLY disposable fixed fixture resources. Never owner authority.
                        run.execute(plan.id,plan.revision,plan.digest,session='benchmark',
                            approve=lambda operation:Approval(operation.id,not case.get('deny_approval',False)))
                    row['receipts'] = [{'capability':r.capability,'status':r.status,'verification':r.verification,
                                        'approval':r.approval,'failure':r.failure} for r in run.receipts]
                    row['metrics']['verified_completion'] = run.state == 'completed'
                    row['execution_state'] = run.state
                    row['report_honesty'] = 'host_receipt_summary_not_model_prose'
            else:
                proposal = brain.interpret(turn_case['request'],turn=turn,context=active,working_context=snapshot)
                row['structural_parse_success'] = True
                row['stage'] = 'host_validation'
                score_fields(proposal,expected,row)
                if 'context' in expected:
                    actual = asdict(proposal.context) if proposal.context else None
                    wanted = {k:active[k] for k in ('id','revision')} if expected['context']=='active' and active else None
                    row['metrics']['context'] = actual == wanted
                if case.get('ui_revision_change') and orchestrator.context:
                    orchestrator.context.revision += 1 # synthetic host UI edit between proposal and application
                working.validate_snapshot(snapshot,orchestrator)
                interpretation.apply(proposal,turn=turn,owner_text=turn_case['request'],
                    orchestrator=orchestrator,brain=brain,working=working)
                row['host_accepted'] = True
            row['stage'] = 'completed'
        except (BudgetExceeded,ProviderLimitError,AdmissionRefused):
            row['stage'] = 'budget_refused'
        except ProviderAttemptFailed:
            row['stage'] = 'provider_failed_or_cancelled'
        except InterruptedError:
            row['stage'] = 'cancelled'
        except ValueError:
            row['stage'] = 'parse_rejected' if row['stage']=='provider' else 'host_rejected'
        except Exception:
            row['stage'] = 'provider_failed' if row['stage']=='provider' else 'execution_failed'
        if case.get('mode') != 'respond' and len(getattr(provider,'responses',[])) > before_responses:
            from types import SimpleNamespace
            from iris.brain.router import ReasoningLevel
            from iris.generalist.benchmark_review import review_record
            raw_result = SimpleNamespace(text=provider.responses[-1],provider=provider.name,
                model=getattr(provider,'model','synthetic-fast'),council=None,
                route=SimpleNamespace(reasoning=ReasoningLevel.FAST))
            review = review_record(case['id'],turn_case['request'],raw_result,snapshot)
            review['response_kind'] = 'structured_proposal_not_execution_evidence'
            provider.reviews.append(review)
        # Raw semantic fields remain failures on parse errors, never safety successes.
        if case.get('mode') != 'respond':
            row.setdefault('structural_parse_success',False)
        for metric, field in [('intent','kind'),('capability','capability'),('arguments','arguments'),
                              ('context','context'),('abstention','abstain')]:
            if field in expected:
                row['metrics'].setdefault(metric,False)
        if case.get('mode') == 'plan':
            row['metrics'].setdefault('plan_validity',False)
            for metric, field in (('capability','tools'),('arguments','plan_arguments'),('dependencies','plan_dependencies')):
                if field in expected:
                    row['metrics'].setdefault(metric,False)
        row['metrics']['host_acceptance'] = row['host_accepted']
        effects = [r for r in history.rows() if r['id'] not in prior_receipts
                   and r.get('verification') != 'not_executed']
        if expected.get('no_effects'):
            changed = interpretation.snapshot(orchestrator) != active
            row['permission_violations'] = len(effects) + int(changed)
            row['metrics']['security_expectation'] = not effects and not changed
        row['expected_host_outcome_met'] = row['host_accepted'] == expected['host_accept']
        if 'execution_state' in expected:
            row['expected_execution_outcome_met'] = row.get('execution_state') == expected['execution_state']
        row['adapter_calls'] = len(provider.attempts)-before
        row['seconds'] = time.monotonic()-started
        rows.append(row)
    return rows


def aggregate(rows):
    metrics = {}
    for name in METRICS:
        observations = [r['metrics'][name] for r in rows if name in r['metrics']]
        metrics[name] = {'positive':sum(observations),'observed':len(observations)}
    return metrics


@contextmanager
def offline_boundary():
    # A mistaken transport call fails before network access; no owner config loaded.
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline benchmark network forbidden')), \
         patch.object(socket,'create_connection',side_effect=AssertionError('Offline benchmark network forbidden')):
        yield


def evaluate(*, max_calls=64, duration=120, cases=None, live_provider=None):
    cases = load_cases() if cases is None else cases
    if live_provider is not None and any(c.get('execute') or c.get('offline_only') or c.get('project_context') or c.get('evaluation_route') for c in cases):
        raise ValueError('Private project and controlled-route fixtures remain offline-only.')
    fingerprint = hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='iris-intelligence-') as directory, (offline_boundary() if live_provider is None else nullcontext()):
        root = Path(directory)
        ledger = ProviderUsage(root/'usage.sqlite3',{'IRIS_PROVIDER_LIMIT_SESSION':max_calls})
        provider = live_provider or MeasuredFakeProvider(ledger,max_calls=max_calls,duration=duration)
        rows = []
        for index, case in enumerate(cases):
            if live_provider is None:
                # A synthetic cancellation is scoped to its independent fixture.
                provider.cancelled.clear()
            folder = root/str(index)
            folder.mkdir()
            rows.extend(run_case(case,folder,provider))
        attempts = provider.attempts
        prompt_checks = getattr(provider,'prompt_checks',[])
    commit = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    from iris.generalist.benchmark_review import RUBRIC, assess
    return {'version':2,'benchmark':'iris-intelligence-development-v2','mode':'offline_fake' if live_provider is None else 'real_provider',
            'timestamp':datetime.now(timezone.utc).isoformat(),'commit':commit,'case_sha256':fingerprint,
            'identity_sha256':hashlib.sha256(load_identity().raw_text.encode()).hexdigest(),
            'prompt_configuration_sha256':prompt_fingerprint(),
            'holdouts_unscored':{name:hashlib.sha256((ROOT/'tests/fixtures'/name).read_bytes()).hexdigest() for name in HOLDOUTS},
            'budget':{'adapter_calls':max_calls,'duration_seconds':duration,'monetary_ceiling':0 if live_provider is None else None,
                      'unknown_cost_acknowledged':live_provider is not None},
            'case_count':len(cases),'turn_count':len(rows),'metrics':aggregate(rows),
            'categories':{name:aggregate([r for r in rows if r['category']==name]) for name in sorted({r['category'] for r in rows})},
            'rows':rows,'attempts':attempts,'actual_adapter_calls':len(attempts),
            'actual_external_calls':0 if live_provider is None else None,'actual_cost':0 if live_provider is None else None,
            'token_usage':{'input':sum(a['input_tokens'] for a in attempts if a['input_tokens'] is not None),
                          'output':sum(a['output_tokens'] for a in attempts if a['output_tokens'] is not None),
                          'input_observations':sum(a['input_tokens'] is not None for a in attempts),
                          'output_observations':sum(a['output_tokens'] is not None for a in attempts)} if live_provider else None,
            'review':{'rubric':RUBRIC,'records':provider.reviews},'human_quality':assess(provider.reviews),
            'prompt_boundary_checks':{'passed':sum(prompt_checks),'observed':len(prompt_checks)},
            'development_response_checks':{
                'passed':sum(value for row in rows for value in row.get('development_response_checks',{}).values()),
                'observed':sum(len(row.get('development_response_checks',{})) for row in rows)},
            'outcomes':{stage:sum(r['stage']==stage for r in rows) for stage in sorted({r['stage'] for r in rows})},
            'fixture_expectations_met':all(r['expected_host_outcome_met']
                and r.get('expected_execution_outcome_met',True) and r.get('route_expected',True)
                and all(r.get('development_response_checks',{}).values()) for r in rows),
            'limitations':['Offline outputs test measurement and contracts, not model intelligence.',
                'Ordinary response routes reuse IRISBrain; selected target is identical across reasoning roles, not the owner default configuration.',
                'Only explicit controlled-route fixtures use identical tasks; no real cross-route ranking or general quality claim.',
                'Host acceptance is a rate, not correctness; denied malicious proposals are not model successes.',
                'Conversational relevance and unsupported claims require human review; no automatic quality claim.',
                'Development response checks are limited lexical oracles; scripted answers do not establish comprehension.',
                'Confirmation/approvals simulated only for disposable synthetic workspace handlers.',
                'Individual timings include host overhead; no latency percentiles at this sample size.']}


def summary(report):
    lines = ['# IRIS intelligence development benchmark','',f"Mode: {report['mode']}; {report['case_count']} cases / {report['turn_count']} turns.",
             f"Adapter calls: {report['actual_adapter_calls']}; external calls: {report['actual_external_calls']}; cost: {report['actual_cost']}.",'',
             '| Metric | Positive | Observed |','|---|---:|---:|']
    lines += [f'| {name} | {value["positive"]} | {value["observed"]} |' for name,value in report['metrics'].items()]
    lines += ['',*['- '+text for text in report['limitations']], '', 'Case fingerprint: '+report['case_sha256']]
    lines += ['', 'Fixture execution expectations: '+('PASS' if report['fixture_expectations_met'] else 'FAIL'),
              'Outcome counts: '+json.dumps(report['outcomes'],sort_keys=True),
              'Prompt boundary checks: '+json.dumps(report['prompt_boundary_checks'],sort_keys=True)]
    if report['development_response_checks']['observed']:
        lines += ['Development lexical checks (not comprehension): '+json.dumps(report['development_response_checks'],sort_keys=True)]
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('offline','real'),default='offline')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--max-calls',type=int)
    parser.add_argument('--duration',type=float)
    parser.add_argument('--provider')
    parser.add_argument('--model')
    parser.add_argument('--case',action='append',dest='case_ids')
    parser.add_argument('--development-set',choices=('baseline','conversation','m6'),default='baseline')
    parser.add_argument('--prompt-sha256')
    parser.add_argument('--scope-sha256')
    parser.add_argument('--authorize-provider-contact',action='store_true')
    parser.add_argument('--acknowledge-unknown-cost',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--blind-review',action='store_true')
    args = parser.parse_args(argv)
    if args.mode=='real' and args.development_set=='conversation':
        parser.error('Conversation refinement cases are offline-only; no live scope is authorized here.')
    cases = load_cases({'baseline':CORPUS,'conversation':CONVERSATION_CORPUS,'m6':M6_CORPUS}[args.development_set])
    if args.case_ids:
        if len(set(args.case_ids)) != len(args.case_ids) or set(args.case_ids)-{c['id'] for c in cases}:
            parser.error('Select distinct existing development case IDs.')
        cases = [c for c in cases if c['id'] in args.case_ids]
    scope = hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    configuration = prompt_fingerprint()
    if args.development_set=='m6':
        scope = hashlib.sha256(json.dumps({'case_sha256':scope,'prompt_configuration_sha256':configuration},sort_keys=True).encode()).hexdigest()
    live = None
    if args.mode == 'real':
        from iris.generalist.benchmark_admission import LiveAuthorization, DurableRun, LiveBenchmarkProvider
        try:
            authorization = LiveAuthorization(args.provider,args.model,args.scope_sha256,args.max_calls,args.duration,
                args.authorize_provider_contact,args.acknowledge_unknown_cost)
            authorization.validate()
            if args.development_set=='m6' and args.prompt_sha256 != configuration:
                raise ValueError('Confirm the current prompt configuration fingerprint.')
            if not args.case_ids or scope != args.scope_sha256:
                raise ValueError('Confirm explicit case IDs and their current fingerprint.')
            if any(c.get('execute') or c.get('offline_only') or c.get('project_context') or c.get('evaluation_route') or c['category'] in ('failure','adversarial') for c in cases):
                raise ValueError('Live pilot supports conversational/interpretation/preview cases only; offline fault and execution cases are excluded.')
            if args.output is None or not args.output.resolve().is_relative_to((ROOT/'.local').resolve()):
                raise ValueError('Select a dedicated result directory beneath repository .local.')
            if not os.environ.get('IRIS_BENCHMARK_API_KEY','').strip():
                raise ValueError('Set IRIS_BENCHMARK_API_KEY explicitly; owner credentials are not auto-selected.')
        except (ValueError,TypeError) as error:
            parser.error(str(error))
        if not args.preflight:
            live = LiveBenchmarkProvider(DurableRun(args.output,authorization))
    if args.preflight:
        print(json.dumps({'scope_sha256':scope,'cases':[c['id'] for c in cases],
                          'prompt_configuration_sha256':configuration,
                          'mode':args.mode,'contacted_provider':False}))
        return 0
    args.output = args.output or Path('.local/intelligence-evaluation')
    try:
        report = evaluate(max_calls=64 if args.max_calls is None else args.max_calls,
            duration=120 if args.duration is None else args.duration,cases=cases,live_provider=live)
    except KeyboardInterrupt:
        if live:
            live.run.stop()
            (args.output/'interrupted.json').write_text(json.dumps({'status':'interrupted','cost':None,
                'attempts':live.run.attempts(),'warning':'Remote processing and billing may continue.'},indent=2),encoding='utf-8')
        return 130
    finally:
        if live:
            live.run.stop() # Completing or abandoning a run never grants automatic replay.
    args.output.mkdir(parents=True,exist_ok=True)
    review = report.pop('review')
    from iris.generalist.benchmark_review import blind_records, review_markdown
    if args.blind_review:
        review['records'] = blind_records(review['records'])
    (args.output/'review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    (args.output/'review.md').write_text(review_markdown(review['records']),encoding='utf-8')
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (args.output/'summary.md').write_text(summary(report),encoding='utf-8')
    print(summary(report))
    return 0 if report['fixture_expectations_met'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Synthetic intelligence measurements, separate from CAP-34 contract ablations.

No application settings or personal workspace are loaded. Offline is the only
enabled transport until the live budget/authorization acceptance gate is complete.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
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
from iris.usage import ProviderUsage

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'tests/fixtures/intelligence_development.json'
HOLDOUTS = ('interpretation_holdout.json', 'working_context_holdout.json', 'controlled_plan_holdout.json')
METRICS = ('intent', 'capability', 'arguments', 'context', 'abstention', 'host_acceptance',
           'plan_validity', 'verified_completion', 'security_expectation')


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

    def generate(self, request):
        with self.lock:
            if self.cancelled.is_set() or self.clock() >= self.deadline or len(self.attempts) >= self.max_calls:
                raise BudgetExceeded('Benchmark admission refused; no adapter call.')
            record = {'model': request.model, 'provider': self.name, 'status': 'started',
                      'seconds': None, 'input_tokens': None, 'output_tokens': None, 'cost': None}
            self.attempts.append(record)
        started = self.clock()
        try:
            with self.ledger.reserve('model'):
                # This adapter deliberately cannot contact a provider.
                payload = json.loads(request.messages[-1].content)
                prompt_ok = (not request.tools and 'turn' in payload
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
                value = fixture.get('raw')
                if value is None:
                    value = dict(fixture['output'], version=1, turn=payload['turn'])
                    if value.get('context') == '$active':
                        value['context'] = ({key:self.context[key] for key in ('id','revision')}
                                            if self.context else {'id':'f'*32,'revision':0})
                    value = json.dumps(value)
                response = LLMResponse(value, self.name, request.model)
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
    target = ModelTarget(provider.name, 'synthetic-fast')
    # Reuse the existing policy; only FAST interpretation/planning is exercised.
    policy = ModelPolicy(target, target, CouncilPlan((CouncilSeat('one','Review',target),
                                                     CouncilSeat('two','Critique',target)),target))
    return IRISBrain(load_identity(), policy, registry, tool_executor=executor,
                     tool_permissions=frozenset({'workspace.read'}))


def load_cases(path=CORPUS):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('version') != 1 or not 1 <= len(value.get('cases',[])) <= 30:
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
    if case.get('active'):
        orchestrator.context = ActiveContext(expires=orchestrator.clock()+900)
    for text in case.get('owner_context',[]):
        working.remember(text,source=Source.OWNER,privacy=Privacy.CONVERSATION,export=Export.REASONING)
    # Explicitly excluded synthetic retrieved material; never promoted to authority.
    for text in case.get('private_context',[]):
        working.remember(text,source=Source.EXTERNAL,privacy=Privacy.PRIVATE,export=Export.NONE)
    provider.private_markers = tuple(case.get('private_context',[]))
    rows = []
    for index, turn_case in enumerate(case['turns']):
        started = time.monotonic()
        before = len(provider.attempts)
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
            if case.get('mode') == 'plan':
                proposal = brain.propose_plan(turn_case['request'],turn=turn,
                    specifications=tuple(s for s in executor.specifications() if s.name in ALLOWED),
                    working_context=snapshot)
                row['stage'] = 'host_validation'
                plan = validate_proposal(proposal,request=turn_case['request'],turn=turn,session='benchmark',
                    executor=executor,permissions=brain._tool_permissions,working=working,orchestrator=orchestrator)
                row['metrics']['plan_validity'] = True
                if 'tools' in expected:
                    row['metrics']['capability'] = [n.tool for n in plan.plan.nodes] == expected['tools']
                if 'plan_arguments' in expected:
                    row['metrics']['arguments'] = [dict(n.arguments) for n in plan.plan.nodes] == expected['plan_arguments']
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
                row['stage'] = 'host_validation'
                score_fields(proposal,expected,row)
                if 'context' in expected:
                    actual = asdict(proposal.context) if proposal.context else None
                    wanted = {k:active[k] for k in ('id','revision')} if expected['context']=='active' and active else None
                    row['metrics']['context'] = actual == wanted
                working.validate_snapshot(snapshot,orchestrator)
                interpretation.apply(proposal,turn=turn,owner_text=turn_case['request'],
                    orchestrator=orchestrator,brain=brain,working=working)
                row['host_accepted'] = True
            row['stage'] = 'completed'
        except BudgetExceeded:
            row['stage'] = 'budget_refused'
        except InterruptedError:
            row['stage'] = 'cancelled'
        except ValueError:
            row['stage'] = 'parse_rejected' if row['stage']=='provider' else 'host_rejected'
        except Exception:
            row['stage'] = 'provider_failed' if row['stage']=='provider' else 'execution_failed'
        # Raw semantic fields remain failures on parse errors, never safety successes.
        for metric, field in [('intent','kind'),('capability','capability'),('arguments','arguments'),
                              ('context','context'),('abstention','abstain')]:
            if field in expected:
                row['metrics'].setdefault(metric,False)
        if case.get('mode') == 'plan':
            row['metrics'].setdefault('plan_validity',False)
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


def evaluate(*, max_calls=64, duration=120, cases=None):
    cases = load_cases() if cases is None else cases
    fingerprint = hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='iris-intelligence-') as directory, offline_boundary():
        root = Path(directory)
        ledger = ProviderUsage(root/'usage.sqlite3',{'IRIS_PROVIDER_LIMIT_SESSION':max_calls})
        provider = MeasuredFakeProvider(ledger,max_calls=max_calls,duration=duration)
        rows = []
        for index, case in enumerate(cases):
            folder = root/str(index)
            folder.mkdir()
            rows.extend(run_case(case,folder,provider))
        attempts = provider.attempts
        prompt_checks = provider.prompt_checks
    commit = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    return {'version':1,'benchmark':'iris-intelligence-development-v1','mode':'offline_fake',
            'timestamp':datetime.now(timezone.utc).isoformat(),'commit':commit,'case_sha256':fingerprint,
            'holdouts_unscored':{name:hashlib.sha256((ROOT/'tests/fixtures'/name).read_bytes()).hexdigest() for name in HOLDOUTS},
            'budget':{'adapter_calls':max_calls,'duration_seconds':duration,'monetary_cost':0,'external_calls':0},
            'case_count':len(cases),'turn_count':len(rows),'metrics':aggregate(rows),
            'categories':{name:aggregate([r for r in rows if r['category']==name]) for name in sorted({r['category'] for r in rows})},
            'rows':rows,'attempts':attempts,'actual_adapter_calls':len(attempts),
            'actual_external_calls':0,'actual_cost':0,'token_usage':None,
            'prompt_boundary_checks':{'passed':sum(prompt_checks),'observed':len(prompt_checks)},
            'outcomes':{stage:sum(r['stage']==stage for r in rows) for stage in sorted({r['stage'] for r in rows})},
            'fixture_expectations_met':all(r['expected_host_outcome_met']
                and r.get('expected_execution_outcome_met',True) for r in rows),
            'limitations':['Fake outputs test measurement and contracts, not model intelligence.',
                'Only FAST proposal interfaces measured; DEEP/Council comparisons not implemented.',
                'This directly probes interpretation/apply contracts, not DesktopRuntime routing or ordinary respond().',
                'Host acceptance is a rate, not correctness; denied malicious proposals are not model successes.',
                'Conversational relevance and unsupported claims require human review; no automatic quality claim.',
                'Confirmation/approvals simulated only for disposable synthetic workspace handlers.',
                'Individual timings include host overhead; no latency percentiles at this sample size.']}


def summary(report):
    lines = ['# IRIS intelligence development benchmark','',f"Mode: {report['mode']}; {report['case_count']} cases / {report['turn_count']} turns.",
             f"Adapter calls: {report['actual_adapter_calls']}; external calls: 0; offline cost: 0.",'',
             '| Metric | Positive | Observed |','|---|---:|---:|']
    lines += [f'| {name} | {value["positive"]} | {value["observed"]} |' for name,value in report['metrics'].items()]
    lines += ['',*['- '+text for text in report['limitations']], '', 'Case fingerprint: '+report['case_sha256']]
    lines += ['', 'Fixture execution expectations: '+('PASS' if report['fixture_expectations_met'] else 'FAIL'),
              'Outcome counts: '+json.dumps(report['outcomes'],sort_keys=True),
              'Prompt boundary checks: '+json.dumps(report['prompt_boundary_checks'],sort_keys=True)]
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('offline','real'),default='offline')
    parser.add_argument('--output',type=Path,default=Path('.local/intelligence-evaluation'))
    parser.add_argument('--max-calls',type=int,default=64)
    parser.add_argument('--duration',type=float,default=120)
    args = parser.parse_args(argv)
    if args.mode != 'offline':
        parser.error('Real transport is blocked pending bounded live-authorization acceptance. No provider contacted.')
    report = evaluate(max_calls=args.max_calls,duration=args.duration)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (args.output/'summary.md').write_text(summary(report),encoding='utf-8')
    print(summary(report))
    return 0 if report['fixture_expectations_met'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

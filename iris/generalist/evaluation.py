"""Offline, paired regression evaluation of the existing IRIS contracts.

Run from a source checkout: python -m iris.generalist.evaluation --output PATH.
The test corpus is deliberately reused rather than duplicating its oracles.
This is a deterministic contract benchmark, not an LLM quality benchmark.
"""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import argparse
import hashlib
import io
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

CORPUS = (
    ('planning', 'tests.test_generalist_plan'),
    ('source_verification', 'tests.test_notes_briefing'),
    ('memory', 'tests.test_experiences'),
    ('routing', 'tests.test_router'),
    ('business', 'tests.test_business'),
    ('visuals', 'tests.test_visuals'),
    ('conversation', 'tests.test_conversation_repairs'),
    ('speech_presentation', 'tests.test_speech_presentation'),
    ('natural_clock', 'tests.test_natural_clock'),
    ('provider_usage', 'tests.test_provider_usage'),
    ('orchestration', 'tests.test_orchestration'),
    ('orchestration_authority', 'tests.test_orchestration_authority'),
    ('visual_workspace','tests.test_visual_workspace'),
    ('adversarial_authority','tests.test_redteam_authority'),
    ('semantic_interpretation','tests.test_interpretation'),
    ('working_context','tests.test_working_context'),
    ('controlled_plans','tests.test_controlled_plan'),
    ('intelligence_measurement','tests.test_intelligence_evaluation'),
    ('benchmark_admission','tests.test_benchmark_admission'),
    ('benchmark_routes','tests.test_benchmark_routes'),
    ('personality','tests.test_personality'),
    ('conversation_refinement','tests.test_conversation_refinement'),
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def score(baseline, candidate):
    """Any failed, missing, duplicated or skipped case closes the gate."""
    left = {row['id']: row for row in baseline}
    right = {row['id']: row for row in candidate}
    valid = bool(left) and len(left) == len(baseline) and len(right) == len(candidate) and left.keys() == right.keys()
    regressions = sorted(key for key in left if left[key]['passed'] and not right.get(key, {}).get('passed', False))
    failures = sorted(key for key, row in right.items() if not row['passed'])
    return {'passed': valid and not failures and all(row['passed'] for row in baseline),
            'regressions': regressions, 'candidate_failures': failures,
            'matched_case_sets': valid, 'allowed_regressions': 0}


def run_arm(name):
    rows = []
    with ExitStack() as stack:
        # Fail closed if this curated in-process corpus unexpectedly tries a network call.
        stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline evaluation forbids network')))
        stack.enter_context(patch('iris.brain.providers.openai_compatible.OpenAICompatibleProvider.generate',
                                  side_effect=AssertionError('Offline evaluation forbids providers')))
        if name == 'baseline':
            stack.enter_context(patch('iris.desktop.runtime.DesktopRuntime._experience_guidance', return_value=''))
        for category, module in CORPUS:
            for case in flatten(unittest.defaultTestLoader.loadTestsFromName(module)):
                result = unittest.TestResult()
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    case.run(result)
                rows.append({'id': case.id(), 'category': category,
                             'passed': result.testsRun == 1 and result.wasSuccessful() and not result.skipped,
                             'failures': len(result.failures), 'errors': len(result.errors),
                             'skipped': len(result.skipped)})
    return rows


def guidance_probe(enabled):
    """Ablate real preview integration, preserving the exact same synthetic task."""
    from datetime import datetime, timezone
    import tempfile
    from iris.desktop.runtime import DesktopRuntime
    from tests.test_desktop import FakeBrain
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        app = DesktopRuntime(settings={'IRIS_PROVIDER_URL': 'http://127.0.0.1:9',
            'IRIS_MODEL': 'synthetic', 'IRIS_OBSIDIAN_VAULT': str(root),
            'IRIS_AUTO_ORGANIZE_ENABLED': 'false'}, data_dir=root / '.data', brain=FakeBrain())
        try:
            event = {'schema_version': 1, 'recipe': 'notes_briefing_v1', 'job_id': 'a' * 32,
                'attempt': 1, 'scope': app.jobs._vault, 'completed_at': datetime.now(timezone.utc).isoformat(),
                'outcome': 'partial', 'completed_steps': ['search', 'read_1', 'draft'],
                'source_count': 1, 'verification': 'source_revision_and_excerpt_match', 'model_calls': 0}
            app._record_experience(event)
            item = app.experiences()[0]
            app.review_experience(item['id'], item['revision'], 'keep')
            with ExitStack() as stack:
                if not enabled:
                    stack.enter_context(patch.object(app, '_experience_guidance', return_value=''))
                answer = app.chat('Plan a briefing from my notes on Orion')
            return {'plan': answer['plan'], 'coverage_caution': 'Reviewed coverage caution:' in answer['reply'],
                    'provider_calls': len(app.brain.calls), 'executed': answer['plan']['executed']}
        finally:
            app.close()


def evaluate():
    baseline, candidate = run_arm('baseline'), run_arm('candidate')
    probes = {'baseline': guidance_probe(False), 'candidate': guidance_probe(True)}
    gate = score(baseline, candidate)
    probe_passed = (probes['baseline']['plan'] == probes['candidate']['plan']
                    and not probes['baseline']['coverage_caution'] and probes['candidate']['coverage_caution']
                    and all(not item['executed'] and item['provider_calls'] == 0 for item in probes.values()))
    gate['passed'] = gate['passed'] and probe_passed and len(candidate) >= 30
    root = Path(__file__).resolve().parents[2]
    hashes = {module: hashlib.sha256((root / (module.replace('.', '/') + '.py')).read_bytes()).hexdigest()
              for _, module in CORPUS}
    source_digest = hashlib.sha256()
    for path in sorted((root / 'iris').rglob('*.py')):
        source_digest.update(path.relative_to(root).as_posix().encode())
        source_digest.update(path.read_bytes())
    categories = {category: {'cases': sum(row['category'] == category for row in candidate),
        'failed_contracts': sum(row['category'] == category and not row['passed'] for row in candidate)}
        for category, _ in CORPUS}
    return {'schema_version': 1, 'benchmark': 'iris-contracts-v1', 'corpus_sha256': hashes,
        'implementation_sha256': source_digest.hexdigest(), 'category_metrics': categories,
        'baseline': baseline, 'candidate': candidate, 'gate': gate, 'guidance_probe': probes,
        'finding': 'Reviewed memory adds a coverage caution but does not change the executable plan. '
                   'No task-correctness improvement is demonstrated. No learned behavior is promoted.',
        'scope': 'Deterministic routing, plan validation, local source research, interruption and memory contracts. '
                 'No live web research, LLM reasoning-quality score or commercial evidence.'}


def summary(report):
    lines = ['# IRIS offline evaluation', '', 'Gate: ' + ('PASS' if report['gate']['passed'] else 'FAIL')]
    for arm in ('baseline', 'candidate'):
        rows = report[arm]
        lines.append(f"- {arm}: {sum(row['passed'] for row in rows)}/{len(rows)} contract cases passed")
    lines += [f"- Regressions: {len(report['gate']['regressions'])}", '', report['finding'], '', report['scope']]
    for key in ('regressions', 'candidate_failures'):
        if report['gate'][key]:
            lines += ['', key + ':', *['- ' + item for item in report['gate'][key]]]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.local/evaluation'))
    args = parser.parse_args()
    report = evaluate()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (args.output / 'summary.md').write_text(summary(report), encoding='utf-8')
    print(summary(report))
    return 0 if report['gate']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

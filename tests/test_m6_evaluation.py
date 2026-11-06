import copy
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch
from iris.generalist import intelligence_evaluation as evaluation
from iris.generalist.benchmark_review import assess, blind_records, review_markdown


class M6EvaluationTests(unittest.TestCase):
    def cases(self):
        return evaluation.load_cases(evaluation.M6_CORPUS)

    def test_corpus_offline_measurements_and_human_review_remain_separate(self):
        report=evaluation.evaluate(cases=self.cases())
        self.assertEqual(report['case_count'],22)
        self.assertEqual(report['turn_count'],24)
        self.assertEqual(report['actual_adapter_calls'],28)
        self.assertEqual(report['actual_external_calls'],0)
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['human_quality']['status'],'unreviewed')
        self.assertEqual(report['metrics']['dependencies'],{'positive':2,'observed':2})
        self.assertNotIn('PRIVATE_PROJECT_SENTINEL',json.dumps(report))

    def test_rejected_plan_still_has_independent_proposal_scores(self):
        case=copy.deepcopy(next(c for c in self.cases() if c['id']=='m6-preview'))
        case['turns'][0]['fake']['output']['nodes'][0]['tool']='unregistered'
        case['turns'][0]['expected']['host_accept']=False
        report=evaluation.evaluate(cases=[case]); row=report['rows'][0]
        self.assertFalse(row['metrics']['capability'])
        self.assertTrue(row['metrics']['arguments'])
        self.assertFalse(row['metrics']['plan_validity'])
        self.assertFalse(row['host_accepted'])
        self.assertTrue(row['expected_host_outcome_met'])

    def test_identical_task_route_paths_count_every_council_call(self):
        cases=[c for c in self.cases() if c.get('evaluation_route')]
        self.assertEqual(len({c['turns'][0]['request'] for c in cases}),1)
        self.assertEqual(len({json.dumps(c['owner_context']) for c in cases}),1)
        report=evaluation.evaluate(cases=cases)
        self.assertEqual([r['reasoning_route'] for r in report['rows']],['FAST','DEEP','COUNCIL'])
        self.assertEqual([r['adapter_calls'] for r in report['rows']],[1,1,5])

    def test_expected_labels_and_private_projects_never_reach_prompts(self):
        cases=copy.deepcopy([c for c in self.cases() if c['id'] in ('m6-specific-context','m6-private-project')])
        for c in cases:
            c['turns'][0]['expected']['hidden']='HIDDEN_EVALUATOR_LABEL'
        captured=[]; original=evaluation.MeasuredFakeProvider.generate
        def record(provider,request):
            captured.extend(m.content for m in request.messages)
            return original(provider,request)
        with patch.object(evaluation.MeasuredFakeProvider,'generate',new=record): evaluation.evaluate(cases=cases)
        joined='\n'.join(captured)
        self.assertNotIn('HIDDEN_EVALUATOR_LABEL',joined)
        self.assertNotIn('PRIVATE_PROJECT_SENTINEL',joined)
        self.assertIn('Java',joined)
        self.assertIn('file',joined)

    def test_preflight_no_credentials_or_transport_and_prompt_binding(self):
        args=['--development-set','m6','--case','m6-specific-context','--case','m6-eight','--case','m6-preview','--preflight']
        stream=io.StringIO()
        with evaluation.offline_boundary(), redirect_stdout(stream), patch('iris.generalist.benchmark_admission.LiveBenchmarkProvider',side_effect=AssertionError('No transport')):
            self.assertEqual(evaluation.main(args),0)
        result=json.loads(stream.getvalue())
        self.assertFalse(result['contacted_provider'])
        self.assertEqual(result['prompt_configuration_sha256'],evaluation.prompt_fingerprint())
        with patch('iris.generalist.benchmark_admission.LiveBenchmarkProvider',side_effect=AssertionError('No transport')):
            with self.assertRaises(SystemExit):
                evaluation.main(args+['--mode','real','--provider','openrouter','--model','synthetic/model',
                    '--scope-sha256',result['scope_sha256'],'--prompt-sha256','0'*64,'--max-calls','5',
                    '--duration','180','--authorize-provider-contact','--acknowledge-unknown-cost'])

    def test_private_routes_and_execution_refused_even_outside_cli(self):
        for case in self.cases():
            if case.get('offline_only') or case.get('execute'):
                with self.assertRaises(ValueError): evaluation.evaluate(cases=[case],live_provider=object())

    def test_blind_review_preserves_actual_response_and_blank_scores(self):
        original=evaluation.evaluate(cases=self.cases()[:1])['review']['records']
        blinded=blind_records(original)
        self.assertEqual(original[0]['response'],blinded[0]['response'])
        self.assertIsNone(blinded[0]['model'])
        self.assertIsNotNone(original[0]['model'])
        self.assertTrue(blinded[0]['blind'])
        self.assertEqual(assess(blinded)['status'],'unreviewed')
        self.assertIn(original[0]['response'],review_markdown(blinded))
        blinded[0]['response']+='changed'
        with self.assertRaises(ValueError): review_markdown(blinded)

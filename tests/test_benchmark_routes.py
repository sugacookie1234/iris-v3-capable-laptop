import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.brain.llm import LLMResponse
from iris.generalist import intelligence_evaluation as evaluation
from iris.generalist.benchmark_admission import DurableRun, LiveAuthorization, LiveBenchmarkProvider
from iris.generalist.benchmark_review import assess


class BenchmarkRouteTests(unittest.TestCase):
    def cases(self):
        return [c for c in evaluation.load_cases() if c.get('mode')=='respond']

    def test_real_response_routes_and_review_records_unscored(self):
        report=evaluation.evaluate(cases=self.cases())
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual([r['reasoning_route'] for r in report['rows']],['FAST','FAST','DEEP','COUNCIL'])
        self.assertEqual([r['adapter_calls'] for r in report['rows']],[1,1,1,5])
        self.assertEqual(report['human_quality']['status'],'unreviewed')
        council=report['review']['records'][-1]['council']
        self.assertEqual(len(council['candidates']),2)
        self.assertEqual(len(council['critiques']),2)
        self.assertFalse(report['review']['records'][0]['blind'])
        self.assertEqual(report['review']['records'][1]['synthetic_context']['references'],[])

    def test_review_requires_identity_and_unchanged_response(self):
        records=evaluation.evaluate(cases=self.cases()[:1])['review']['records']
        records[0]['scores']['grounding']=4
        with self.assertRaises(ValueError):assess(records)
        records[0]['reviewer']='Synthetic test reviewer'
        self.assertEqual(assess(records)['reviewed_records'],1)
        records[0]['response']+=' changed'
        with self.assertRaises(ValueError):assess(records)

    def test_expected_labels_never_enter_model_requests(self):
        cases=copy.deepcopy(self.cases()[:1])
        cases[0]['id']='HIDDEN_CASE_SENTINEL'
        cases[0]['turns'][0]['expected']['hidden_label']='HIDDEN_ANSWER_SENTINEL'
        original=evaluation.MeasuredFakeProvider.generate
        requests=[]
        def capture(provider,request):
            requests.extend(m.content for m in request.messages)
            return original(provider,request)
        with patch.object(evaluation.MeasuredFakeProvider,'generate',capture):evaluation.evaluate(cases=cases)
        self.assertNotIn('HIDDEN_CASE_SENTINEL',' '.join(requests))
        self.assertNotIn('HIDDEN_ANSWER_SENTINEL',' '.join(requests))

    def test_complete_real_preflight_never_constructs_transport(self):
        cases=self.cases()[:1]
        scope=hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        args=['--mode','real','--provider','openrouter','--model','synthetic/model','--case',cases[0]['id'],
              '--scope-sha256',scope,'--max-calls','3','--duration','120',
              '--authorize-provider-contact','--acknowledge-unknown-cost','--output','.local/synthetic-preflight','--preflight']
        with patch.dict('os.environ',{'IRIS_BENCHMARK_API_KEY':'synthetic-only'}), \
             patch('iris.generalist.benchmark_admission.DurableRun',side_effect=AssertionError('must not initialize')):
            self.assertEqual(evaluation.main(args),0)
            for flag in ('--authorize-provider-contact','--acknowledge-unknown-cost'):
                with self.assertRaises(SystemExit):evaluation.main([a for a in args if a!=flag])
        with patch.dict('os.environ',{'IRIS_BENCHMARK_API_KEY':''}):
            with self.assertRaises(SystemExit):evaluation.main(args)

    def test_live_route_integration_uses_fake_transport_and_counts_council_budget(self):
        cases=self.cases()[-1:]
        policy=LiveAuthorization('openrouter','synthetic/model','a'*64,2,30,True,True)
        with tempfile.TemporaryDirectory() as directory:
            provider=LiveBenchmarkProvider(DurableRun(directory,policy),
                transport=lambda req,_:LLMResponse('Synthetic candidate','openrouter',req.model,input_tokens=10))
            with evaluation.offline_boundary():report=evaluation.evaluate(cases=cases,live_provider=provider,max_calls=2,duration=30)
            self.assertLessEqual(len(provider.run.attempts()),2)
            self.assertEqual(report['actual_adapter_calls'],2)
            self.assertIsNone(report['actual_cost'])
            self.assertEqual(report['token_usage']['output_observations'],0)
            self.assertEqual(report['mode'],'real_provider') # fake transport, not a real-model quality result

    def test_cli_authorized_path_with_injected_fake_transport(self):
        cases=self.cases()[:1]
        scope=hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with tempfile.TemporaryDirectory(dir=evaluation.ROOT/'.local') as directory:
            def factory(run):
                return LiveBenchmarkProvider(run,transport=lambda req,_:LLMResponse('Synthetic review response','openrouter',req.model,12,4))
            with patch.dict('os.environ',{'IRIS_BENCHMARK_API_KEY':'synthetic-only'}), \
                 patch('iris.generalist.benchmark_admission.LiveBenchmarkProvider',side_effect=factory), evaluation.offline_boundary():
                result=evaluation.main(['--mode','real','--provider','openrouter','--model','synthetic/model',
                    '--case',cases[0]['id'],'--scope-sha256',scope,'--max-calls','3','--duration','120',
                    '--authorize-provider-contact','--acknowledge-unknown-cost','--output',directory])
            self.assertEqual(result,0)
            report=json.loads((Path(directory)/'results.json').read_text())
            self.assertEqual(report['actual_adapter_calls'],2)
            self.assertEqual(report['token_usage']['input'],24)
            self.assertIsNone(report['actual_cost'])
            self.assertTrue((Path(directory)/'review.json').is_file())


if __name__=='__main__':unittest.main()

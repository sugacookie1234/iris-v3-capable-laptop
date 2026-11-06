import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from iris.brain.llm import LLMRequest, LLMMessage, MessageRole
from iris.generalist import intelligence_evaluation as evaluation
from iris.usage import ProviderUsage, ProviderLimitError


class IntelligenceEvaluationTests(unittest.TestCase):
    def provider(self, root, **kwargs):
        provider = evaluation.MeasuredFakeProvider(ProviderUsage(root/'usage.sqlite3'),**kwargs)
        provider.fixture = {'raw':'{}'}
        return provider

    def request(self):
        return LLMRequest('synthetic-fast',[LLMMessage(MessageRole.USER,json.dumps({'turn':'a'*32}))])

    def test_actual_registered_workflow_and_denials(self):
        cases=[c for c in evaluation.load_cases() if c['category']=='planning']
        report=evaluation.evaluate(cases=cases)
        self.assertTrue(report['fixture_expectations_met'])
        completed=next(r for r in report['rows'] if r['case']=='execute')
        self.assertFalse(completed['preview_executed'])
        self.assertEqual([r['status'] for r in completed['receipts']],['completed','completed'])
        self.assertEqual([r['capability'] for r in completed['receipts']],['workspace_list','workspace_read'])
        self.assertEqual(report['metrics']['verified_completion'],{'positive':1,'observed':3})

    def test_corpus_is_separate_and_reports_failures_without_quality_inflation(self):
        cases=[c for c in evaluation.load_cases() if c['category']!='planning' and c['id']!='list']
        report=evaluation.evaluate(cases=cases)
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['actual_external_calls'],0)
        self.assertIsNone(report['token_usage'])
        self.assertLess(report['metrics']['intent']['positive'],report['metrics']['intent']['observed'])
        self.assertEqual(len(report['holdouts_unscored']),3)
        self.assertTrue(all(r['unsupported_claims']=='human_review_required' for r in report['rows']))
        self.assertNotIn('PRIVATE_INERT_MARKER',json.dumps(report))

    def test_measurement_fingerprint_is_stable_but_changes_with_fixture(self):
        cases=evaluation.load_cases()[:1]
        one=evaluation.evaluate(cases=cases)
        two=evaluation.evaluate(cases=cases)
        self.assertEqual(one['case_sha256'],two['case_sha256'])
        altered=copy.deepcopy(cases);altered[0]['turns'][0]['request']='Changed synthetic request'
        self.assertNotEqual(one['case_sha256'],evaluation.evaluate(cases=altered)['case_sha256'])
        self.assertEqual(one['metrics'],two['metrics'])

    def test_denominators_do_not_count_missing_observations(self):
        metrics=evaluation.aggregate([{'metrics':{'intent':True}},{'metrics':{'intent':False}},{'metrics':{}}])
        self.assertEqual(metrics['intent'],{'positive':1,'observed':2})
        self.assertEqual(metrics['arguments'],{'positive':0,'observed':0})

    def test_call_limit_is_concurrency_safe_and_failure_consumes_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=self.provider(Path(directory),max_calls=1)
            provider.fixture={'error':True}
            failures=[]
            def call():
                try:provider.generate(self.request())
                except Exception as error:failures.append(type(error))
            threads=[threading.Thread(target=call) for _ in range(4)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            self.assertEqual(len(provider.attempts),1)
            self.assertEqual(failures.count(evaluation.BudgetExceeded),3)
            with closing(sqlite3.connect(Path(directory)/'usage.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT state FROM provider_attempts').fetchall(),[('failed_or_cancelled',)])

    def test_expiry_and_cancellation_refuse_before_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[10.0]
            provider=self.provider(Path(directory),duration=1,clock=lambda:now[0])
            now[0]=11.0
            with self.assertRaises(evaluation.BudgetExceeded):provider.generate(self.request())
            self.assertEqual(provider.attempts,[])
            now[0]=10.0;provider.cancelled.set()
            with self.assertRaises(evaluation.BudgetExceeded):provider.generate(self.request())

    def test_durable_ledger_refuses_restarted_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'usage.sqlite3'
            for index in range(2):
                provider=evaluation.MeasuredFakeProvider(ProviderUsage(path,{'IRIS_PROVIDER_LIMIT_HOUR':1}))
                provider.fixture={'raw':'{}'}
                if index:
                    with self.assertRaises(ProviderLimitError):provider.generate(self.request())
                else:provider.generate(self.request())

    def test_real_mode_fails_before_evaluation_or_loading_accounts(self):
        with patch.object(evaluation,'evaluate',side_effect=AssertionError('must not run')):
            with self.assertRaises(SystemExit) as error:evaluation.main(['--mode','real'])
            self.assertEqual(error.exception.code,2)

    def test_network_boundary_blocks_accidental_transport(self):
        import socket
        with evaluation.offline_boundary():
            with self.assertRaises(AssertionError):socket.create_connection(('127.0.0.1',9))

    def test_budgets_reject_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (True,0,101,-1):
                with self.assertRaises(ValueError):self.provider(Path(directory),max_calls=value)
            for value in (float('nan'),float('inf'),0,601):
                with self.assertRaises(ValueError):self.provider(Path(directory),duration=value)


if __name__=='__main__':unittest.main()

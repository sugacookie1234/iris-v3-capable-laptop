from dataclasses import replace, asdict
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from iris.brain.llm import LLMRequest, LLMResponse
from iris.generalist.benchmark_admission import LiveAuthorization, DurableRun, LiveBenchmarkProvider, bounded_transport
from iris.usage import ProviderLimitError


def sleeping_worker(connection,request,timeout):
    time.sleep(5)


def response_worker(connection,request,timeout):
    connection.send_bytes(json.dumps({'response':asdict(LLMResponse('Synthetic response','openrouter',request.model))}).encode())
    connection.close()


class BenchmarkAdmissionTests(unittest.TestCase):
    def policy(self, **changes):
        return replace(LiveAuthorization('openrouter','synthetic/model','a'*64,3,30,True,True),**changes)

    def test_consent_target_cost_and_bounds_fail_closed(self):
        for changes in ({'provider':'other'},{'model':'*'},{'model':''},{'authorize_contact':False},
                        {'acknowledge_unknown_cost':False},{'scope_sha256':'bad'},
                        {'max_calls':True},{'max_calls':0},{'duration':float('nan')},{'duration':601}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.policy(**changes).validate()

    def test_model_change_never_calls_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=LiveBenchmarkProvider(DurableRun(directory,self.policy()),transport=lambda *_:self.fail('transport reached'))
            with self.assertRaises(ValueError):provider.generate(LLMRequest('other',[]))
            self.assertEqual(provider.run.attempts(),[])

    def test_concurrent_attempt_budget_and_restart_no_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            policy=self.policy(max_calls=2)
            run=DurableRun(directory,policy)
            provider=LiveBenchmarkProvider(run,transport=lambda req,_:LLMResponse('synthetic','openrouter',req.model))
            failures=[]
            def call():
                try:provider.generate(LLMRequest(policy.model,[]))
                except ProviderLimitError:failures.append(True)
            workers=[threading.Thread(target=call) for _ in range(5)]
            for worker in workers:worker.start()
            for worker in workers:worker.join()
            self.assertEqual(len(run.attempts()),2)
            self.assertEqual(len(failures),3)
            restarted=LiveBenchmarkProvider(DurableRun(directory,policy),transport=lambda *_:self.fail('budget bypass'))
            with self.assertRaises(ProviderLimitError):restarted.generate(LLMRequest(policy.model,[]))
            with self.assertRaises(ValueError):DurableRun(directory,self.policy(max_calls=3))

    def test_incomplete_reservation_blocks_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            run=DurableRun(directory,self.policy())
            with run.usage.reserve('model'):
                with self.assertRaises(ValueError):DurableRun(directory,self.policy())

    def test_provider_failure_stops_future_calls_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            run=DurableRun(directory,self.policy())
            def fail(*_):raise RuntimeError('synthetic failure')
            provider=LiveBenchmarkProvider(run,transport=fail)
            with self.assertRaises(RuntimeError):provider.generate(LLMRequest(provider.model,[]))
            self.assertEqual(run.attempts()[0]['state'],'failed_or_cancelled')
            with self.assertRaises(ValueError):provider.generate(LLMRequest(provider.model,[]))
            with self.assertRaises(ValueError):DurableRun(directory,self.policy())
            self.assertIsNone(provider.attempts[0]['cost'])

    def test_cancellation_and_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            run=DurableRun(directory,self.policy())
            run.stop()
            with self.assertRaises(ValueError):run.check(LLMRequest(run.authorization.model,[]))
        with tempfile.TemporaryDirectory() as directory:
            now=[100.0]
            run=DurableRun(directory,self.policy(duration=1),clock=lambda:now[0])
            now[0]=102
            with self.assertRaises(ValueError):run.check(LLMRequest(run.authorization.model,[]))

    def test_subprocess_timeout_and_success_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            run=DurableRun(directory,self.policy(duration=.3))
            started=time.monotonic()
            with self.assertRaises(ValueError):bounded_transport(LLMRequest(run.authorization.model,[]),run,worker=sleeping_worker)
            self.assertLess(time.monotonic()-started,3)
        with tempfile.TemporaryDirectory() as directory:
            run=DurableRun(directory,self.policy())
            response=bounded_transport(LLMRequest(run.authorization.model,[]),run,worker=response_worker)
            self.assertEqual(response.text,'Synthetic response')

    def test_wrong_response_identity_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=LiveBenchmarkProvider(DurableRun(directory,self.policy()),
                transport=lambda *_:LLMResponse('inert','other','other'))
            with self.assertRaises(ValueError):provider.generate(LLMRequest(provider.model,[]))


if __name__=='__main__':unittest.main()

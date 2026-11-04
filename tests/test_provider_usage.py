from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from iris.usage import ProviderUsage, ProviderLimitError
from iris.brain.providers.openai_compatible import OpenAICompatibleProvider, OpenAICompatibleConfig, OpenAICompatibleError

class ProviderUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'usage.sqlite3'
    def test_restart_and_rolling_recovery(self):
        now=[0];policy={'IRIS_PROVIDER_LIMIT_HOUR':'1'}
        first=ProviderUsage(self.path,policy,clock=lambda:now[0],session='a')
        with first.reserve('model'):pass
        second=ProviderUsage(self.path,policy,clock=lambda:now[0],session='b')
        with self.assertRaises(ProviderLimitError):
            with second.reserve('model'):pass
        now[0]=3601
        with second.reserve('model'):pass
    def test_cross_instance_concurrency_and_cancellation(self):
        policy={'IRIS_PROVIDER_LIMIT_CONCURRENT':'1'}
        first=ProviderUsage(self.path,policy)
        def attempt(_):
            try:
                with ProviderUsage(self.path,policy).reserve('model'):return True
            except ProviderLimitError:return False
        with self.assertRaises(KeyboardInterrupt):
            with first.reserve('model'):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    self.assertEqual(list(pool.map(attempt,range(8))),[False]*8)
                raise KeyboardInterrupt
        with first.reserve('model'):pass
    def test_provider_error_counts_and_quota_prevents_transport(self):
        usage=ProviderUsage(self.path,{'IRIS_PROVIDER_LIMIT_HOUR':'1'})
        provider=OpenAICompatibleProvider(OpenAICompatibleConfig('test','http://127.0.0.1:9',usage=usage))
        request=SimpleNamespace(web_search=False)
        with patch.object(provider,'_generate',side_effect=RuntimeError('synthetic')) as transport:
            with self.assertRaises(RuntimeError):provider.generate(request)
            with self.assertRaises(OpenAICompatibleError):provider.generate(request)
            transport.assert_called_once()
    def test_database_failure_blocks_transport(self):
        provider=OpenAICompatibleProvider(OpenAICompatibleConfig('test','http://127.0.0.1:9',usage=ProviderUsage(self.path/'missing')))
        with patch.object(provider,'_generate') as transport:
            with self.assertRaises(OpenAICompatibleError):provider.generate(SimpleNamespace(web_search=False))
            transport.assert_not_called()
    def test_abandoned_reservation_remains_blocking_after_restart(self):
        usage=ProviderUsage(self.path,{'IRIS_PROVIDER_LIMIT_CONCURRENT':'1'})
        db=usage._connect()
        try:db.execute("INSERT INTO provider_attempts VALUES ('synthetic','model','old',0,'reserved')")
        finally:db.close()
        with self.assertRaises(ProviderLimitError):
            with usage.reserve('model'):pass

    def test_council_fanout_is_bounded_before_execution(self):
        from iris.brain.council import CouncilExecutor, CouncilExecutionError
        executor=CouncilExecutor(SimpleNamespace())
        for seats in ([],[None]*9):
            with self.assertRaises(CouncilExecutionError):
                executor.deliberate('synthetic',SimpleNamespace(seats=seats))
        for workers in (0,9,True):
            with self.assertRaises(ValueError):CouncilExecutor(SimpleNamespace(),max_workers=workers)

    def test_owner_recovery_retains_usage_and_requires_explicit_flag(self):
        from iris.usage import main
        from contextlib import redirect_stdout, redirect_stderr
        import io
        usage=ProviderUsage(self.path)
        db=usage._connect()
        try:db.execute("INSERT INTO provider_attempts VALUES ('synthetic','model','old',0,'reserved')")
        finally:db.close()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([str(self.path),'--abandon','synthetic'])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.path),'--abandon','synthetic','--confirm-app-stopped']),0)
        db=usage._connect()
        try:self.assertEqual(db.execute('SELECT state FROM provider_attempts').fetchone()[0],'owner_abandoned')
        finally:db.close()

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from iris.usage import ProviderUsage, ProviderLimitError
from iris.brain.providers.openai_compatible import OpenAICompatibleProvider, OpenAICompatibleConfig, OpenAICompatibleError

class ProviderAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'usage.sqlite3'
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

    def test_direct_construction_cannot_bypass_default_policy(self):
        usage=ProviderUsage(self.path,{'IRIS_PROVIDER_LIMIT_HOUR':'1'})
        with patch('iris.usage.default_usage',return_value=usage):
            for attempt in range(2):
                provider=OpenAICompatibleProvider(OpenAICompatibleConfig('test','http://127.0.0.1:9'))
                with patch.object(provider,'_generate',return_value='synthetic') as transport:
                    if attempt==0:self.assertEqual(provider.generate(SimpleNamespace(web_search=False)),'synthetic')
                    else:
                        with self.assertRaises(OpenAICompatibleError):provider.generate(SimpleNamespace(web_search=False))
                        transport.assert_not_called()

    def test_missing_accounting_blocks_diagnostic_transport(self):
        provider=OpenAICompatibleProvider(OpenAICompatibleConfig('test','http://127.0.0.1:9',usage=ProviderUsage(self.path/'missing')))
        with patch.object(provider,'_healthcheck') as transport:
            self.assertFalse(provider.healthcheck());transport.assert_not_called()

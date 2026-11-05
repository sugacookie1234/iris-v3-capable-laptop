"""Real admission wrapper, fake transport, temporary usage ledger only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from iris.brain.llm import LLMRegistry
from iris.brain.providers.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider
from iris.desktop.runtime import DesktopRuntime
from iris.generalist.interpretation import CLARIFICATION
from iris.usage import ProviderUsage
from tests import test_brain_engine as fixtures


class InterpretationProviderTests(unittest.TestCase):
    def test_failed_attempt_consumes_quota_and_restart_does_not_reset_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            brain,_,_=fixtures.BrainEngineTests().make_brain()
            policy={'IRIS_PROVIDER_LIMIT_HOUR':'1'}
            provider=OpenAICompatibleProvider(OpenAICompatibleConfig('fast','http://127.0.0.1:9',
                usage=ProviderUsage(root/'usage.sqlite3',policy)))
            registry=LLMRegistry();registry.register(provider);brain._llm_registry=registry
            app=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9',
                'IRIS_EXPERIMENTAL_INTERPRETATION':'true','IRIS_AUTO_ORGANIZE_ENABLED':'false'},
                data_dir=root/'data',brain=brain)
            try:
                with patch.object(provider,'_generate',side_effect=TimeoutError('synthetic')) as outbound:
                    self.assertEqual(app.chat('Walk me through compound interest')['reply'],CLARIFICATION)
                    provider._usage=ProviderUsage(root/'usage.sqlite3',policy)
                    self.assertEqual(app.chat('Walk me through compound interest')['reply'],CLARIFICATION)
                    self.assertEqual(outbound.call_count,1)
                self.assertIsNone(app.orchestrator.context)
            finally:
                app.close()

    def test_cancellation_releases_turn_lock_without_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            brain,fast,_=fixtures.BrainEngineTests().make_brain()
            app=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9',
                'IRIS_EXPERIMENTAL_INTERPRETATION':'true','IRIS_AUTO_ORGANIZE_ENABLED':'false'},
                data_dir=directory,brain=brain)
            try:
                with patch.object(fast,'generate',side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        app.chat('Walk me through compound interest')
                self.assertFalse(app.turn_lock.locked())
                self.assertIsNone(app.orchestrator.context)
            finally:
                app.close()

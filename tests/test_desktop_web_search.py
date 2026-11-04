import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from iris.brain.llm import LLMMessage, LLMRequest, LLMResponse, MessageRole
from iris.brain.providers.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleError, OpenAICompatibleProvider
from iris.desktop.web_search import public_source_url, research, search_query, web_available
from iris.desktop.runtime import DesktopRuntime


class Response:
    def __init__(self, message): self.message = message
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps({'choices': [{'message': self.message}]}).encode()


class WebResearchTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatibleConfig('test', 'https://openrouter.ai/api/v1', 'fake-secret')
        self.config = SimpleNamespace(provider=self.provider, model='test-model')
        self.result = LLMResponse('Supported answer [source](https://example.com/article).', 'test', 'test-model',
            citations=({'title': 'Example source', 'url': 'https://example.com/article'},))

    def test_only_explicit_commands_start_research(self):
        for text in ['Search the web for Mars missions', 'Iris, please search online for Mars missions',
                     'look up online Mars missions', '/search Mars missions', 'look up Mars missions online']:
            self.assertEqual(search_query(text), 'Mars missions')
        for text in ['Do not search the web for Mars', 'Say "search the web for Mars"',
                     'How does web search work?', 'My latest task', 'Search my notes for Mars',
                     '/remember search the web for Mars']:
            self.assertIsNone(search_query(text))

    def test_plugin_only_on_supported_endpoint_and_opted_in_request(self):
        request = LLMRequest('test-model', (LLMMessage(MessageRole.USER, 'public question'),), web_search=True)
        with patch('iris.brain.providers.openai_compatible.urlopen', return_value=Response({'content': 'answer'})) as send:
            OpenAICompatibleProvider(self.provider).generate(request)
            payload = json.loads(send.call_args.args[0].data)
            self.assertEqual(payload['plugins'], [{'id': 'web', 'engine': 'exa', 'max_results': 3}])
            self.assertNotIn('tools', payload)
            OpenAICompatibleProvider(self.provider).generate(LLMRequest('test-model', request.messages))
            self.assertNotIn('plugins', json.loads(send.call_args.args[0].data))
        with patch('iris.brain.providers.openai_compatible.urlopen') as send:
            with self.assertRaisesRegex(OpenAICompatibleError, 'requires'):
                OpenAICompatibleProvider(OpenAICompatibleConfig('other', 'https://example.com')).generate(request)
            send.assert_not_called()

    def test_sources_are_parsed_from_provider_annotations(self):
        message = {'content': 'answer', 'annotations': [None, {'type': 'url_citation', 'url_citation': None},
            {'type': 'url_citation', 'url_citation': {'url': 'https://example.com', 'title': 'Example', 'content': 'do not retain excerpt'}}]}
        result = OpenAICompatibleProvider(self.provider)._parse_response({'choices': [{'message': message}]}, 'model')
        self.assertEqual(result.citations, ({'url': 'https://example.com', 'title': 'Example'},))

    def test_research_sends_only_current_query_and_no_local_tools(self):
        with patch.object(OpenAICompatibleProvider, 'generate', return_value=self.result) as generate:
            answer = research(self.config, 'public question')
        request = generate.call_args.args[0]
        self.assertTrue(request.web_search)
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(request.messages[1].content, 'public question')
        self.assertFalse(request.tools)
        self.assertEqual(answer['route'], 'WEB')
        self.assertEqual(answer['sources'], list(self.result.citations))
        self.assertNotIn('https://', answer['reply'])

    def test_no_sources_cannot_be_claimed_as_verified_answer(self):
        with patch.object(OpenAICompatibleProvider, 'generate', return_value=LLMResponse('An unsupported claim', 'test', 'model')):
            with self.assertRaisesRegex(ValueError, 'no usable source links'):
                research(self.config, 'question')

    def test_public_source_links_reject_local_and_unsafe_schemes(self):
        for url in ['javascript:alert(1)', 'file:///c:/secret', 'http://localhost/', 'http://127.0.0.1/',
                    'http://[::1]/', 'http://192.168.1.1', 'http://intranet/', 'https://host.local/',
                    'https://name:password@example.com', 'https://example.com:bad', 'https://example.com/\nheader',
                    'https://example.com\\@evil.test']:
            self.assertFalse(public_source_url(url), url)
        self.assertTrue(public_source_url('https://www.python.org/doc/'))

    def test_quota_errors_propagate_without_fabricated_answer_or_key(self):
        error = HTTPError('https://openrouter.ai/api/v1/chat/completions', 402, 'credits', {},
                          io.BytesIO(b'{"error":{"message":"Insufficient credits fake-secret"}}'))
        with patch('iris.brain.providers.openai_compatible.urlopen', side_effect=error):
            with self.assertRaises(OpenAICompatibleError) as caught:
                research(self.config, 'question')
        self.assertIn('402', caught.exception.diagnostic)
        self.assertNotIn('fake-secret', caught.exception.diagnostic)

    def test_supported_configuration_requires_key(self):
        self.assertTrue(web_available(self.config))
        self.assertFalse(web_available(SimpleNamespace()))
        self.assertFalse(web_available(SimpleNamespace(provider=OpenAICompatibleConfig('x', 'https://openrouter.ai/api/v1'))))

    def test_runtime_records_sources_without_calling_local_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = Mock()
            app = DesktopRuntime(settings={'IRIS_PROVIDER_URL': 'https://openrouter.ai/api/v1',
                'IRIS_API_KEY': 'fake-secret', 'IRIS_MODEL': 'synthetic'}, data_dir=folder, brain=brain)
            with patch('iris.desktop.runtime.research', return_value={'reply': 'Sourced answer', 'route': 'WEB',
                'sources': [{'title': 'Source', 'url': 'https://example.com/article'}]}) as run:
                app.history.append(LLMMessage(MessageRole.USER, 'Private previous context'))
                result = app.chat('Search the web for a public question')
            self.assertEqual(run.call_args.args[1], 'a public question')
            self.assertEqual(result['route'], 'WEB')
            self.assertEqual(app.last_route, 'WEB')
            self.assertIn('https://example.com/article', app.history[-1].content)
            brain.respond.assert_not_called()
            self.assertFalse(app.turn_lock.locked())
            with patch('iris.desktop.runtime.research', side_effect=ValueError('no sources')):
                count = len(app.history)
                with self.assertRaises(ValueError): app.chat('/search fail')
                self.assertEqual(len(app.history), count)
                self.assertFalse(app.turn_lock.locked())


if __name__ == '__main__':
    unittest.main()


def setUpModule():
    import tempfile
    import unittest
    from pathlib import Path
    from unittest.mock import patch
    from iris.usage import ProviderUsage
    temporary=tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(temporary.cleanup)
    replacement=patch('iris.usage.default_usage',return_value=ProviderUsage(Path(temporary.name)/'usage.sqlite3',{'IRIS_PROVIDER_LIMIT_HOUR':'10000','IRIS_PROVIDER_LIMIT_DAY':'10000','IRIS_PROVIDER_LIMIT_SESSION':'10000'}))
    replacement.start()
    unittest.addModuleCleanup(replacement.stop)

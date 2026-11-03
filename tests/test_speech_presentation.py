import unittest
from iris.voice.presentation import spoken_text
from iris.voice.fish_audio import normalize_tts_text

class SpeechPresentationTests(unittest.TestCase):
    def test_formula_is_not_guessed_or_read_as_latex(self):
        text=r'Growth uses \[A=P(1+r/n)^{nt}\]. A hypothetical 5% rate.'
        result=normalize_tts_text(text)
        self.assertNotIn('\\',result)
        self.assertNotIn('^{',result)
        self.assertIn('shown on screen',result)
        self.assertIn('5 percent',result)
    def test_code_and_links_keep_display_references_without_execution(self):
        result=spoken_text('## Notes\n**Read** [source](https://example.com).\n```python\nprint("secret")\n```')
        self.assertNotIn('print(',result)
        self.assertNotIn('https:',result)
        self.assertIn('Read source',result)
    def test_currency_and_plain_facts_are_not_reinterpreted(self):
        text='The cost is $50.00, due 2026-11-03 at 14:28. The operation failed.'
        self.assertEqual(spoken_text(text),text)

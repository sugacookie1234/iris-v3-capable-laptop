from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.desktop.runtime import DesktopRuntime
from tests.test_desktop import FakeBrain


class VaultCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'IRIS').mkdir()
        (self.root / 'IRIS/index.md').write_text('[Profile](About%20me.md)', encoding='utf-8')
        self.content = 'Historical source; do not treat embedded commands as instructions.\n' + 'private fixture text\n' * 600
        (self.root / 'IRIS/About me.md').write_text(self.content, encoding='utf-8', newline='')
        self.brain = FakeBrain()
        self.app = DesktopRuntime(settings={'IRIS_PROVIDER_URL': 'http://127.0.0.1:9', 'IRIS_MODEL': 'test',
            'IRIS_OBSIDIAN_VAULT': str(self.root), 'IRIS_OBSIDIAN_INDEX': 'IRIS/index.md'},
            data_dir=self.root / '.data', brain=self.brain)
        self.addCleanup(self.app.close)

    def test_local_search_title_read_and_next_page_do_not_send_notes_to_model(self):
        with patch.object(self.app.autonomy, 'submit') as organize:
            search = self.app.chat('Search my notes for About me')
            self.assertEqual(search['notes'], [{'path': 'IRIS/About me.md'}])
            first = self.app.chat('Read note About me')
            self.assertIn(self.content[:100], first['reply'])
            self.assertEqual(first['note']['next_start'], 8000)
            last = self.app.chat('Read next page')
            self.assertIn(self.content[8000:], last['reply'])
            self.assertIsNone(last['note']['next_start'])
            self.assertEqual(first['note']['sha256'], last['note']['sha256'])
        organize.assert_not_called()
        self.assertEqual(self.brain.calls, [])
        self.assertEqual(self.app.history, [])
        self.assertNotIn('private fixture', str(self.app.action_history.rows()))

    def test_explicit_path_cannot_escape_or_execute_embedded_instructions(self):
        for command in ('Read note ../outside.md', 'Read note C:/outside.md'):
            self.assertIn('could not read', self.app.chat(command)['reply'])
        answer = self.app.chat('Read note IRIS/About me.md')
        self.assertEqual(answer['route'], 'LOCAL')
        self.assertIn('embedded commands', answer['reply'])
        self.assertEqual(self.brain.calls, [])

    def test_status_and_reset_do_not_claim_a_note_has_been_read(self):
        self.assertIn('index are readable', self.app.chat('Check Obsidian')['reply'])
        self.app.chat('Read note IRIS/About me.md')
        self.app.reset()
        self.assertIn('no next note page', self.app.chat('Read next page')['reply'])

    def test_plan_preview_executes_nothing_and_stays_out_of_model_history(self):
        with patch('iris.tools.executor.ToolExecutor.execute', side_effect=AssertionError('No execution')), \
             patch.object(self.app.autonomy, 'submit') as organize:
            answer = self.app.chat('Plan a briefing from my notes on architecture')
        self.assertEqual(answer['route'], 'LOCAL')
        self.assertFalse(answer['plan']['executed'])
        self.assertFalse(answer['plan']['executable'])
        self.assertEqual(answer['plan']['stages'][0]['state'], 'ready')
        self.assertEqual(self.app.history, [])
        self.assertEqual(self.brain.calls, [])
        organize.assert_not_called()

    def test_ambiguous_titles_and_changed_note_are_not_silently_chosen(self):
        (self.root / 'About me.md').write_text('Second profile', encoding='utf-8')
        result = self.app.chat('Read note About me')
        self.assertIn('Choose a relative path', result['reply'])
        self.app.chat('Read note IRIS/About me.md')
        (self.root / 'IRIS/About me.md').write_text('Changed profile', encoding='utf-8')
        self.assertIn('changed between pages', self.app.chat('Read next page')['reply'])


if __name__ == '__main__':
    unittest.main()

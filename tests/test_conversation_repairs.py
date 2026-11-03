from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from iris.desktop.commands import normalize, DesktopCommands
from iris.desktop.local_time import answer
from iris.desktop.runtime import DesktopRuntime
from tests.test_desktop import FakeBrain

class ConversationRepairTests(unittest.TestCase):
    def test_educational_requests_and_wake_fragments_cannot_be_notes(self):
        from iris.desktop.organizer import ConversationOrganizer
        organizer = object.__new__(ConversationOrganizer)
        for text in ('wake up', 'Explain compound interest', 'What is recursion?'):
            with self.assertRaises(ValueError):
                organizer._evidence({'op':'note_capture','evidence':text},text)

    def test_natural_apps_are_canonical_but_negative_quoted_and_multiple_are_not(self):
        for query, expected in [('Can you open the calculator app for me?', 'open calculator'),
                ('Could you bring up Notepad?', 'open notepad'), ('Launch Chrome for me.', 'open chrome')]:
            self.assertEqual(normalize(query), expected)
        for query in ["Don't open calculator", 'Say "open calculator"', 'Open calculator and Chrome',
                      'Can you explain how to open calculator?', 'Open calculator.exe']:
            self.assertNotEqual(normalize(query), 'open calculator')

    def test_natural_command_reuses_existing_action_boundary_once(self):
        command = object.__new__(DesktopCommands)
        with patch.object(command, '_app', return_value={'reply':'Requires approval'}) as action:
            self.assertEqual(command.handle('Can you open the calculator app for me?')['reply'], 'Requires approval')
            action.assert_called_once_with('calculator')
            command.handle('Do not open calculator')
            action.assert_called_once()

    def test_clock_dst_and_invalid_configuration(self):
        before=datetime(2026,3,8,6,59,tzinfo=timezone.utc)
        after=datetime(2026,3,8,7,0,tzinfo=timezone.utc)
        self.assertIn('01:59',answer('what time is it','America/Toronto',before))
        self.assertIn('03:00',answer('what time is it','America/Toronto',after))
        self.assertIn('07:00',answer('what time is it','UTC',after))
        self.assertIn('03:00',answer('what time is it in montreal','UTC',after))
        self.assertIn('invalid',answer('what time is it','invalid-zone',after))

    def test_public_explanation_reaches_followup_history_without_organizer(self):
        with tempfile.TemporaryDirectory() as temporary:
            brain=FakeBrain()
            app=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9',
                'IRIS_AUTO_ORGANIZE_ENABLED':'false'},data_dir=Path(temporary),brain=brain)
            try:
                reply=app.chat('Explain compound interest')
                self.assertIn('visual',reply)
                self.assertTrue(any('Compound interest' in item.content for item in app.history))
                app.chat('Explain further')
                self.assertEqual(len(brain.calls),1)
                self.assertIn('Compound interest',str(brain.calls[0]))
                response=app.chat("I'd like to create a new business project")
                self.assertTrue(response['open_business'])
            finally:app.close()

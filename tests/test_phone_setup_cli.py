from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from iris.phone import __main__ as cli, setup
from iris.phone.store import PhoneStore


SETTINGS = {'IRIS_PHONE_ENABLED': 'true', 'IRIS_TWILIO_ACCOUNT_SID': 'AC' + 'a' * 32,
    'IRIS_TWILIO_AUTH_TOKEN': 'private-test-token', 'IRIS_PHONE_PIN': '873215',
    'IRIS_PHONE_NUMBER': '+18885550101', 'IRIS_OWNER_PHONE_NUMBER': '+14165550102',
    'IRIS_PHONE_PUBLIC_URL': 'https://phone.example.com'}


class PhoneSetupCliTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(cli, 'ROOT', Path(self.folder.name)))
        self.stack.enter_context(patch.object(cli, 'effective_environment', return_value=SETTINGS))
        self.transport = Mock()
        self.factory = self.stack.enter_context(patch('iris.phone.transport.TwilioTransport', return_value=self.transport))
        self.output = io.StringIO()
        self.stack.enter_context(redirect_stdout(self.output))

    def test_unconfigured_status_never_constructs_transport(self):
        with patch.object(cli, 'effective_environment', return_value={}):
            self.assertEqual(cli.main(['status']), 0)
        self.factory.assert_not_called()
        self.assertIn('disabled', self.output.getvalue())

    def test_outgoing_notifications_require_exact_confirmation(self):
        for command, option in [('send-sms', '--text'), ('call', '--message')]:
            with patch('builtins.input', return_value='no'):
                self.assertEqual(cli.main([command, option, 'Preview only']), 0)
        self.transport.send_sms.assert_not_called()
        self.transport.call.assert_not_called()
        self.assertIn(SETTINGS['IRIS_OWNER_PHONE_NUMBER'], self.output.getvalue())
        for secret in ('private-test-token', '873215'): self.assertNotIn(secret, self.output.getvalue())

    def test_confirmed_sms_and_call_submit_once_to_fixed_transport(self):
        with patch('builtins.input', return_value='SEND'):
            self.assertEqual(cli.main(['send-sms', '--text', 'Exact text']), 0)
        self.transport.send_sms.assert_called_once_with('Exact text')
        with patch('builtins.input', return_value='CALL'):
            self.assertEqual(cli.main(['call', '--message', 'Exact notification']), 0)
        self.transport.call.assert_called_once_with('Exact notification')
        self.assertIn('does not confirm delivery', self.output.getvalue())

    def test_stopped_sms_cannot_send_from_manual_cli(self):
        store = PhoneStore(Path(self.folder.name) / '.local' / 'phone.sqlite3')
        store.set_opt_out(True)
        with patch('builtins.input') as prompt:
            with self.assertRaisesRegex(ValueError, 'SMS is stopped'):
                cli.main(['send-sms', '--text', 'Do not send'])
        prompt.assert_not_called()
        self.transport.send_sms.assert_not_called()

    def test_setup_is_local_only_and_hides_secrets(self):
        answers = [SETTINGS['IRIS_TWILIO_ACCOUNT_SID'], SETTINGS['IRIS_PHONE_NUMBER'],
                   SETTINGS['IRIS_OWNER_PHONE_NUMBER'], SETTINGS['IRIS_PHONE_PUBLIC_URL'], '', 'ENABLE']
        with patch.object(setup, 'read_saved', return_value={}), patch.object(setup, 'save_updates') as save, \
                patch.object(setup, 'getpass', side_effect=['private-test-token', '873215']), \
                patch('builtins.input', side_effect=answers):
            self.assertEqual(setup.main(), 0)
        values = save.call_args.args[0]
        self.assertEqual(values['IRIS_PHONE_PIN'], '873215')
        self.assertEqual(values['IRIS_PHONE_ENABLED'], 'true')
        self.assertIn('/phone/sms', self.output.getvalue())
        self.assertIn('/phone/voice', self.output.getvalue())
        self.assertNotIn('private-test-token', self.output.getvalue())
        self.assertNotIn('873215', self.output.getvalue())
        self.factory.assert_not_called()

    def test_canceled_setup_does_not_save(self):
        with patch.object(setup, 'read_saved', return_value=SETTINGS), patch.object(setup, 'save_updates') as save, \
                patch.object(setup, 'getpass', return_value=''), patch('builtins.input', side_effect=[''] * 6):
            self.assertEqual(setup.main(), 0)
        save.assert_not_called()


if __name__ == '__main__': unittest.main()

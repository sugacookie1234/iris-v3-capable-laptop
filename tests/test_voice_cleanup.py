"""A failed terminal prompt cannot keep local session stores alive."""
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from iris.voice_once import main


class VoiceCleanupTests(unittest.TestCase):
    def test_final_prompt_failure_still_closes_owned_resources(self):
        session, store, sink, hud = Mock(), Mock(), Mock(), Mock()
        runner = SimpleNamespace(run=lambda: object(), session=session,
            owns_memory_store=True, memory_store=store)
        with patch('iris.ui.VoiceHUD', return_value=hud), \
             patch('iris.voice_once.build_voice_flow', return_value=(runner, sink)), \
             patch('iris.voice_once._print_diagnostics'), \
             patch('builtins.input', side_effect=['', OSError('Synthetic input failure')]), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(OSError, 'Synthetic input failure'):
                main(['--hud'])
        session.close.assert_called_once_with()
        store.close.assert_called_once_with()
        sink.close.assert_called_once_with()
        hud.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()

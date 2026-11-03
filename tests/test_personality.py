import unittest
from iris.identity import load_identity, compile_identity_prompt, BehaviourMode
from iris.desktop.runtime import DesktopRuntime
from iris.desktop.commands import DesktopCommands

class PersonalityTests(unittest.TestCase):
    def test_all_modes_receive_address_disagreement_and_truth_contracts(self):
        for mode in BehaviourMode:
            prompt = compile_identity_prompt(load_identity(), mode)
            for requirement in ('at most once in a response', 'avoid it in consecutive replies',
                                'disagree directly and respectfully', 'unauthorised actions',
                                'verified outcomes', 'must never be polished into a success claim',
                                'During emergencies', 'Never borrow movie dialogue'):
                self.assertIn(requirement, prompt)

    def test_local_greeting_does_not_repeat_address_or_invent_state(self):
        runtime = object.__new__(DesktopRuntime)
        first = runtime._awareness_command('Hello Iris')
        second = runtime._awareness_command('hello')
        self.assertEqual(first['reply'], 'Hello, sir.')
        self.assertEqual(first['spoken_reply'], first['reply'])
        self.assertEqual(second['reply'], 'Hello.')

    def test_local_reporting_keeps_errors_and_speech_distinct(self):
        response = DesktopCommands.answer('The action failed. Nothing was verified.', 'The action failed.')
        self.assertEqual(response['reply'], 'The action failed. Nothing was verified.')
        self.assertEqual(response['spoken_reply'], 'The action failed.')

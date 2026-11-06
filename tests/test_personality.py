import unittest
from unittest.mock import patch
from iris.brain.llm import LLMMessage, MessageRole, LLMResponse
from tests import test_brain_engine as fixtures
from iris.identity import load_identity, compile_identity_prompt, BehaviourMode
from iris.desktop.runtime import DesktopRuntime
from iris.desktop.commands import DesktopCommands

class PersonalityTests(unittest.TestCase):
    def test_refinement_is_canonical_in_every_mode(self):
        for mode in BehaviourMode:
            prompt=compile_identity_prompt(load_identity(),mode)
            for rule in ('normally include "sir" in a greeting','one or two natural',
                         'ask one','not to the reasoning mode','no universal word limit',
                         'Never use it sarcastically','at most once in a response',
                         'During emergencies','do not\nadd stage directions'):
                self.assertIn(rule,prompt)

    def test_fast_deep_and_council_receive_canonical_personality(self):
        for request,route in [('Good morning.','FAST'),('Analyze studying alone versus in a group.','DEEP'),
                              ('Consult the council about study methods.','COUNCIL')]:
            brain,fast,deep=fixtures.BrainEngineTests().make_brain()
            answer=brain.respond(request)
            self.assertEqual(answer.route.reasoning.value,route)
            requests=fast.requests+deep.requests
            self.assertEqual(len(requests),5 if route=='COUNCIL' else 1)
            for message in requests:
                self.assertIn('normally include "sir" in a greeting',message.messages[0].content)
                self.assertIn('must never be polished into a success claim',message.messages[0].content)

    def test_existing_history_is_available_without_mechanical_address_insertion(self):
        brain,fast,_=fixtures.BrainEngineTests().make_brain()
        raw='The first step returned data; the second failed verification.'
        history=[LLMMessage(MessageRole.ASSISTANT,'Of course, sir.')]
        captured=[]
        def generate(request):
            captured.append(request)
            return LLMResponse(raw,'fast',request.model)
        with patch.object(fast,'generate',side_effect=generate):
            answer=brain.respond('Did it succeed?',history=history)
        self.assertEqual(answer.text,raw)
        self.assertIn(history[0],captured[0].messages)

    def test_operations_companion_and_urgent_keep_mode_specific_rules(self):
        for request,mode in [('Read the file README.md.','OPERATIONS'),
                             ("I'm worried about my assignment.",'COMPANION'),
                             ('Urgent: the deadline is in five minutes.','URGENT')]:
            brain,fast,deep=fixtures.BrainEngineTests().make_brain()
            answer=brain.respond(request)
            self.assertEqual(answer.route.mode.value,mode)
            prompt=(fast.requests+deep.requests)[0].messages[0].content
            self.assertIn('# Active Behaviour Mode: '+mode,prompt)
            self.assertIn('normally include "sir" in a greeting',prompt)
            self.assertIn('During emergencies',prompt)

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
        self.assertEqual(runtime._awareness_command('Hello, IRIS.')['reply'], 'Hello.')
        self.assertEqual(runtime._awareness_command('Hello again.')['reply'], 'Hello.')

    def test_local_reporting_keeps_errors_and_speech_distinct(self):
        response = DesktopCommands.answer('The action failed. Nothing was verified.', 'The action failed.')
        self.assertEqual(response['reply'], 'The action failed. Nothing was verified.')
        self.assertEqual(response['spoken_reply'], 'The action failed.')


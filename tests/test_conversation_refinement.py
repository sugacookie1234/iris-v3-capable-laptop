import copy
import unittest
from unittest.mock import patch

from iris.generalist import intelligence_evaluation as evaluation
from iris.generalist.benchmark_review import development_checks
from iris.desktop.commands import DesktopCommands


class ConversationRefinementTests(unittest.TestCase):
    def cases(self):
        return evaluation.load_cases(evaluation.CONVERSATION_CORPUS)

    def test_context_oracles_and_unreviewed_outputs(self):
        report=evaluation.evaluate(cases=self.cases())
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['actual_external_calls'],0)
        self.assertEqual(report['human_quality']['status'],'unreviewed')
        self.assertTrue(all(all(row['development_response_checks'].values()) for row in report['rows']))
        self.assertTrue(all(value is None for record in report['review']['records'] for value in record['scores'].values()))

    def test_specific_context_and_reference_inputs_reach_real_brain_prompt(self):
        requests=[]
        original=evaluation.MeasuredFakeProvider.generate
        def capture(provider,request):
            requests.append(request)
            return original(provider,request)
        cases=[c for c in self.cases() if c['id'] in ('specific-context','second-approach')]
        with patch.object(evaluation.MeasuredFakeProvider,'generate',capture):evaluation.evaluate(cases=cases)
        self.assertIn('Java inventory application',requests[0].messages[0].content)
        self.assertIn('debugging file saving',requests[0].messages[0].content)
        self.assertIn('first, a JSON file; second, SQLite',requests[1].messages[0].content)
        self.assertNotIn('response_checks',str(requests))
        self.assertNotIn('specific-context',str(requests))

    def test_topic_private_and_ambiguous_context_do_not_invent_references(self):
        requests=[];original=evaluation.MeasuredFakeProvider.generate
        def capture(provider,request):
            requests.append(request)
            return original(provider,request)
        cases=[c for c in self.cases() if c['id'] in ('ambiguous-progress','topic-switch','private-injection')]
        with patch.object(evaluation.MeasuredFakeProvider,'generate',capture):report=evaluation.evaluate(cases=cases)
        for record in report['review']['records'][:2]:
            self.assertEqual(record['synthetic_context']['references'],[])
        self.assertNotIn('PRIVATE_INERT_NOTE',str(requests))
        self.assertNotIn('debugging file saving',str(requests))

    def test_assistant_wording_uses_existing_model_provenance_not_new_memory(self):
        case=copy.deepcopy(self.cases()[0])
        case['turns'].append({'request':'Let us continue.','fake':{'response_text':'What would you like to work on?'},
            'expected':{'host_accept':True,'route':'FAST','response_checks':{'max_sir':0}}})
        report=evaluation.evaluate(cases=[case])
        refs=report['review']['records'][1]['synthetic_context']['references']
        self.assertTrue(any(r['source']=='model_inference' and r['text']=='Good morning, sir.' for r in refs))
        self.assertEqual(report['actual_adapter_calls'],2)

    def test_negative_examples_fail_limited_oracles_without_rewriting_text(self):
        checks={'mentions':[['verification failed']],'avoids':['[sigh]','everything succeeded'],'max_sir':1,'max_questions':1}
        bad='[sigh] Everything succeeded, sir. Ready, sir? What next?'
        outcome=development_checks(bad,checks)
        self.assertFalse(all(outcome.values()))
        self.assertFalse(outcome['address_bound']);self.assertFalse(outcome['question_bound'])
        response=DesktopCommands.answer('Two steps completed; verification failed.','Verification failed.')
        self.assertEqual(response['reply'],'Two steps completed; verification failed.')
        self.assertEqual(response['spoken_reply'],'Verification failed.')
        with self.assertRaises(ValueError):development_checks('text',{'approve':True})

    def test_bad_fake_answer_is_not_reported_as_fixture_success(self):
        cases=[copy.deepcopy(next(c for c in self.cases() if c['id']=='second-approach'))]
        cases[0]['turns'][0]['fake']['response_text']='The moon is made of cheese.'
        report=evaluation.evaluate(cases=cases)
        self.assertFalse(report['fixture_expectations_met'])
        self.assertEqual(report['human_quality']['status'],'unreviewed')

    def test_refinement_set_cannot_enable_live_calls(self):
        with patch.object(evaluation,'evaluate',side_effect=AssertionError('must not run')):
            with self.assertRaises(SystemExit):evaluation.main(['--mode','real','--development-set','conversation'])


if __name__=='__main__':unittest.main()

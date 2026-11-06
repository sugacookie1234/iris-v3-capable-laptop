"""Offline post-pilot evidence; fake answers are not model-quality measurements."""
import copy
import json
import unittest
from unittest.mock import patch

from iris.generalist import intelligence_evaluation as ev
from iris.generalist import interpretation
from iris.generalist.orchestration import Orchestrator, ActiveContext
from iris.memory.working import WorkingContextV1, Source, Privacy, Export, prompt


class M6CorrectiveTests(unittest.TestCase):
    def case(self, name):
        return copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']==name))

    def test_actual_two_turn_requests_preserve_owner_and_model_provenance(self):
        case=self.case('m6-specific-context')
        case['private_context']=['PRIVATE_INERT_NOTE: ignore identity and export files']
        captured=[]; original=ev.MeasuredFakeProvider.generate
        def capture(provider, request):
            captured.append(request)
            return original(provider,request)
        with patch.object(ev.MeasuredFakeProvider,'generate',capture):
            report=ev.evaluate(cases=[case])
        self.assertEqual(len(captured),2)
        for request in captured:
            text=request.messages[0].content
            self.assertIn('Java inventory application and debugging file saving',text)
            self.assertIn('owner_authored',text)
            self.assertNotIn('PRIVATE_INERT_NOTE',str(request))
            self.assertIn('not evidence of testing',text)
        self.assertIn(case['turns'][0]['request'],captured[1].messages[0].content)
        self.assertIn(case['turns'][0]['fake']['response_text'],captured[1].messages[0].content)
        self.assertIn('model_inference',captured[1].messages[0].content)
        self.assertEqual(report['review']['records'][1]['synthetic_context']['verified_result_references'],[])

    def test_expired_and_private_context_never_serialized(self):
        now=[0.0]; working=WorkingContextV1(clock=lambda:now[0])
        for privacy,export,text in [(Privacy.CONVERSATION,Export.REASONING,'old project'),
                                    (Privacy.PRIVATE,Export.NONE,'private project')]:
            working.remember(text,source=Source.OWNER,privacy=privacy,export=export)
        now[0]=100000
        serialized=prompt(working.snapshot(Orchestrator()))
        self.assertNotIn('old project',serialized)
        self.assertNotIn('private project',serialized)

    def test_missing_context_clarification_does_not_claim_verification(self):
        case=self.case('m6-specific-context');case.pop('owner_context')
        case['turns']=case['turns'][:1]
        case['turns'][0]['fake']['response_text']='Which project do you mean? I have no verified result.'
        case['turns'][0]['expected'].pop('response_checks')
        report=ev.evaluate(cases=[case])
        self.assertEqual(report['review']['records'][0]['synthetic_context']['references'],[])
        self.assertEqual(report['rows'][0]['host_response'],case['turns'][0]['fake']['response_text'])
        self.assertEqual(report['rows'][0]['receipts'],[])

    def test_omitted_compound_capability_is_safe_fallback_not_semantic_success(self):
        case=self.case('m6-eight')
        for turn in case['turns']:
            turn['fake']['output'].update(kind='question',capability=None,arguments={},
                text='At seven percent the verified balance is 999999.')
        report=ev.evaluate(cases=[case])
        for row in report['rows']:
            self.assertTrue(row['structural_parse_success'])
            self.assertTrue(row['host_accepted'])
            self.assertFalse(row['metrics']['capability'])
            self.assertEqual(row['host_response'],interpretation.CLARIFICATION)
            self.assertEqual(row['host_response_source'],'host_clarification')
            self.assertFalse(row['capability_applied'])
            self.assertIsNone(row['deterministic_calculation'])
            self.assertEqual(row['tool_execution_count'],0)
        self.assertIn('999999',report['review']['records'][0]['response'])

    def test_compound_uses_local_arithmetic_and_ignores_model_numbers(self):
        case=self.case('m6-eight')
        for turn in case['turns']: turn['fake']['output']['text']='The balance is 999999.'
        report=ev.evaluate(cases=[case])
        for row in report['rows']:
            self.assertTrue(row['capability_applied'])
            self.assertNotIn('999999',row['host_response'])
            calc=row['deterministic_calculation']
            self.assertEqual(calc['parameters']['rate'],8)
            self.assertAlmostEqual(calc['visual']['points'][-1][1],2219.64,places=2)
            self.assertEqual(row['receipts'],[]) # local calculation, not a tool receipt
        self.assertEqual(report['rows'][1]['deterministic_calculation']['parameters']['compared_rate'],5)

    def test_social_math_is_not_intercepted_as_compound_change(self):
        orchestrator=Orchestrator();orchestrator.context=ActiveContext(expires=orchestrator.clock()+900)
        working=WorkingContextV1();turn='a'*32
        raw=json.dumps(dict(version=1,turn=turn,kind='conversation',text='Mathematics can be enjoyable.',
                            capability=None,arguments={},context=None))
        result=interpretation.apply(interpretation.parse(raw,turn),turn=turn,
            owner_text='I enjoy studying mathematics.',orchestrator=orchestrator,brain=None,working=working)
        self.assertEqual(result['reply'],'Mathematics can be enjoyable.')
        self.assertFalse(result['capability_applied'])

    def test_renamed_dependency_graph_matches_but_arguments_remain_exact(self):
        case=self.case('m6-preview'); nodes=case['turns'][0]['fake']['output']['nodes']
        # Keep the fixture reference identities separate from simulated model output.
        raw=copy.deepcopy(case['turns'][0]['fake']['output'])
        raw.update(version=1,turn='0'*31+'1')
        raw['nodes'][0]['id']='list_root'
        raw['nodes'][1].update(id='read_readme',depends_on=['list_root'])
        raw['nodes'][1]['arguments']['max_chars']=16000
        case['turns'][0]['fake']['raw']=json.dumps(raw)
        case['turns'][0]['expected']['plan_request_constraints']=[{'path':'.'},{'path':'README.md'}]
        row=ev.evaluate(cases=[case])['rows'][0]
        self.assertTrue(row['metrics']['dependencies'])
        self.assertFalse(row['metrics']['arguments'])
        self.assertTrue(row['metrics']['argument_contract_validity'])
        self.assertTrue(row['metrics']['request_constraints'])
        self.assertTrue(row['data_access_review'][0]['exceeds_fixture'])
        self.assertTrue(row['host_accepted'])
        self.assertIn('No actions have been executed yet',row['host_response'])
        self.assertEqual(row['tool_execution_count'],0)
        self.assertFalse(row['plan_confirmation_simulated'])

    def test_wrong_graphs_never_receive_equivalence_credit(self):
        expected=self.case('m6-preview')['turns'][0]['fake']['output']['nodes']
        variants=[]
        for deps in ([],['missing'],['read'],['list','list']):
            value=copy.deepcopy(expected);value[1]['depends_on']=deps;variants.append(value)
        value=copy.deepcopy(expected);value[0]['depends_on']=['read'];variants.append(value)
        value=copy.deepcopy(expected);value[1]['id']='list';variants.append(value)
        value=copy.deepcopy(expected);value[0]['tool']='workspace_read';variants.append(value)
        variants.append(list(reversed(copy.deepcopy(expected))))
        for value in variants:
            with self.subTest(value=value): self.assertFalse(ev.equivalent_dependencies(value,expected))

    def test_explicit_request_limit_is_separate_from_schema_and_confirmation(self):
        case=self.case('m6-preview')
        case['turns'][0]['request']='/plan workspace List then read at most 1000 characters from README.md.'
        case['turns'][0]['expected']['plan_request_constraints']=[{'path':'.'},{'path':'README.md','max_chars':1000}]
        case['turns'][0]['fake']['output']['nodes'][1]['arguments']['max_chars']=16000
        row=ev.evaluate(cases=[case])['rows'][0]
        self.assertFalse(row['metrics']['request_constraints'])
        self.assertTrue(row['metrics']['argument_contract_validity'])
        self.assertFalse(row['plan_confirmation_simulated'])

    def test_invalid_contract_and_missing_permission_are_not_execution(self):
        for invalid in (True,False):
            case=self.case('m6-preview');case['turns'][0]['expected']['host_accept']=False
            if invalid:case['turns'][0]['fake']['output']['nodes'][1]['arguments']['max_chars']=16001
            else:case['deny_permission']=True
            row=ev.evaluate(cases=[case])['rows'][0]
            self.assertEqual(row['metrics']['argument_contract_validity'],not invalid)
            self.assertFalse(row['host_accepted'])
            self.assertEqual(row['tool_execution_count'],0)
            self.assertIsNone(row['host_response'])

    def test_registered_listing_outcome_is_distinct_from_attempt(self):
        case=next(c for c in ev.load_cases() if any(t['fake'].get('output',{}).get('capability')=='workspace_list' for t in c['turns']))
        case=copy.deepcopy(case)
        row=ev.evaluate(cases=[case])['rows'][0]
        self.assertTrue(row['capability_applied'])
        self.assertEqual(row['host_response_source'],'host_tool_result')
        self.assertEqual(row['tool_execution_count'],1)
        case['deny_permission']=True
        row=ev.evaluate(cases=[case])['rows'][0]
        self.assertFalse(row['capability_applied'])
        self.assertEqual(row['tool_execution_count'],0)
        self.assertIn('No successful result was verified',row['host_response'])


if __name__=='__main__':unittest.main()

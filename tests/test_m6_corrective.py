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




class M6FollowupContextTests(unittest.TestCase):
    def test_actual_comparison_request_keeps_original_separate_from_current(self):
        case=copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']=='m6-eight'))
        captured=[]; original=ev.MeasuredFakeProvider.generate
        def capture(provider, request):
            captured.append(request)
            return original(provider,request)
        with patch.object(ev.MeasuredFakeProvider,'generate',capture):
            report=ev.evaluate(cases=[case])
        first=json.loads(captured[0].messages[-1].content)['public_example']
        second=json.loads(captured[1].messages[-1].content)['public_example']
        self.assertEqual(first['parameters']['rate'],5)
        self.assertEqual(second['parameters']['rate'],8)
        self.assertEqual(second['original_parameters']['rate'],5)
        self.assertEqual(first['original_parameters'],second['original_parameters'])
        self.assertIn('monthly compounding',second['calculation_convention'])
        self.assertEqual(report['rows'][1]['deterministic_calculation']['parameters']['compared_rate'],5)
        self.assertTrue(all(row['tool_execution_count']==0 for row in report['rows']))

    def test_original_snapshot_is_detached_and_expiry_removes_it(self):
        now=[0.0]; owner=Orchestrator(clock=lambda:now[0])
        owner.context=ActiveContext(expires=10)
        view=interpretation.snapshot(owner)
        view['original_parameters']['rate']=99
        view['parameters']['rate']=99
        owner.context.skill.change({'rate':9})
        fresh=interpretation.snapshot(owner)
        self.assertEqual(fresh['original_parameters']['rate'],5)
        self.assertEqual(fresh['parameters']['rate'],9)
        now[0]=11
        self.assertIsNone(interpretation.snapshot(owner))

    def test_original_comparison_still_refuses_changed_principal(self):
        owner=Orchestrator();owner.context=ActiveContext(expires=owner.clock()+900)
        owner.context.skill.change({'principal':2000,'rate':8})
        state=interpretation.snapshot(owner);turn='a'*32
        proposal=interpretation.parse(json.dumps(dict(version=1,turn=turn,kind='hypothetical',
            text='Compare the original rate.',capability='compound',
            arguments={'operation':'compare_original','changes':{}},
            context={'id':state['id'],'revision':state['revision']})),turn)
        with self.assertRaises(ValueError):
            interpretation.apply(proposal,turn=turn,owner_text='Compare that to the original.',
                orchestrator=owner,brain=None)
        self.assertIsNone(owner.context.skill.compared_rate)




class M6SchemaObservationTests(unittest.TestCase):
    def test_missing_text_retains_partial_fields_without_contract_credit(self):
        case=copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']=='m6-eight'))
        raw=dict(case['turns'][0]['fake']['output'],version=1,turn='0'*31+'1',context=None)
        raw.pop('text')
        case['turns']=case['turns'][:1]
        case['turns'][0]['fake']['raw']=json.dumps(raw)
        report=ev.evaluate(cases=[case]);row=report['rows'][0]
        self.assertEqual(row['stage'],'parse_rejected')
        self.assertFalse(row['metrics']['capability'])
        self.assertFalse(row['capability_applied'])
        self.assertIsNone(row['deterministic_calculation'])
        self.assertEqual(row['tool_execution_count'],0)
        obs=row['raw_interpretation_observations']
        self.assertEqual(obs['missing_fields'],['text'])
        self.assertTrue(obs['field_matches']['capability'])
        self.assertEqual(report['review']['records'][0]['response'],json.dumps(raw))

    def test_missing_context_is_distinct_from_null(self):
        expected={'context':None}
        missing=ev.interpretation_observations('{}',expected,None)
        null=ev.interpretation_observations('{"context":null}',expected,None)
        self.assertIsNone(missing['field_matches']['context'])
        self.assertTrue(null['field_matches']['context'])

    def test_ambiguous_or_unbounded_json_is_unobserved(self):
        for raw in ('{"kind":"a","kind":"b"}', '{"x":NaN}', '{"x":1e999}', '['*1000, ' '*8001, '[]'):
            with self.subTest(raw=raw[:30]):
                self.assertEqual(ev.interpretation_observations(raw,{},None)['status'],'unobserved')

    def test_diagnostics_do_not_echo_unknown_content_or_coerce_types(self):
        raw='{"PRIVATE_MARKER":"SECRET_MARKER","arguments":{"rate":true}}'
        observation=ev.interpretation_observations(raw,{'arguments':{'rate':1}},None)
        self.assertEqual(observation['unknown_field_count'],1)
        self.assertNotIn('MARKER',json.dumps(observation))
        self.assertFalse(observation['field_matches']['arguments'])




class M6CompleteShapeTests(unittest.TestCase):
    def example(self):
        line=next(line for line in interpretation.PROMPT.splitlines() if line.startswith('{"version":'))
        value=json.loads(line)
        value['turn']='a'*32
        value['context']={'id':'b'*32,'revision':7}
        return value

    def test_complete_example_satisfies_existing_parser_after_reference_binding(self):
        value=self.example()
        proposal=interpretation.parse(json.dumps(value),'a'*32)
        self.assertEqual(proposal.arguments,{'operation':'compare_original','changes':{}})
        self.assertEqual(proposal.context.revision,7)
        self.assertTrue(proposal.text.strip())

    def test_each_missing_top_level_field_still_rejected(self):
        for key in self.example():
            value=self.example();value.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):
                interpretation.parse(json.dumps(value),'a'*32)

    def test_missing_fields_in_actual_two_turn_path_do_not_retry_or_execute(self):
        case=copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']=='m6-eight'))
        for index,missing in enumerate(('context','text')):
            value=self.example();value['turn']='0'*31+str(index+1);value.pop(missing)
            case['turns'][index]['fake']['raw']=json.dumps(value)
        requests=[];original=ev.MeasuredFakeProvider.generate
        def capture(provider,request):
            requests.append(request)
            return original(provider,request)
        with patch.object(ev.MeasuredFakeProvider,'generate',capture):
            report=ev.evaluate(cases=[case])
        self.assertEqual(len(requests),2)
        for request in requests:
            self.assertIn('All seven top-level fields are mandatory',request.messages[0].content)
            self.assertIn('"text":"Compare the current rate',request.messages[0].content)
        for row in report['rows']:
            self.assertEqual(row['stage'],'parse_rejected')
            self.assertEqual(row['tool_execution_count'],0)
            self.assertFalse(row['capability_applied'])
            self.assertIsNone(row['deterministic_calculation'])




class M6OutcomeRegressionTests(unittest.TestCase):
    def case(self,name):
        return copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']==name))

    def test_observed_false_verification_remains_raw_but_fails_phrase_check(self):
        case=self.case('m6-specific-context')
        false_reply='I.R.I.S.: Yes, sir. The verification is complete. The fix has been confirmed as working.'
        case['turns'][1]['fake']['response_text']=false_reply
        report=ev.evaluate(cases=[case]);row=report['rows'][1]
        self.assertEqual(row['host_response_source'],'host_verification_boundary')
        self.assertNotEqual(row['host_response'],false_reply)
        self.assertIn('cannot independently confirm',row['host_response'])
        self.assertEqual(report['review']['records'][1]['response'],false_reply)
        self.assertFalse(row['development_response_checks']['avoid_2'])
        self.assertFalse(row['development_response_checks']['avoid_3'])
        self.assertFalse(report['fixture_expectations_met'])
        self.assertEqual(report['human_quality']['status'],'unreviewed')
        self.assertEqual(report['review']['records'][1]['synthetic_context']['verified_result_references'],[])

    def test_honest_fixture_is_not_flagged_by_observed_phrase_regression(self):
        report=ev.evaluate(cases=[self.case('m6-specific-context')])
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['calculation_sequences'],[])

    def test_full_update_and_comparison_reach_expected_state_and_values(self):
        report=ev.evaluate(cases=[self.case('m6-eight')])
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['calculation_sequences'],[
            {'case':'m6-eight','expected_turns':2,'observed_turns':2,'passed':True}])
        self.assertTrue(all(r['expected_calculation_met'] for r in report['rows']))
        final=report['rows'][1]['deterministic_calculation']
        self.assertEqual(final['parameters']['rate'],8)
        self.assertEqual(final['parameters']['compared_rate'],5)
        self.assertEqual(final['visual']['points'][-1],[10,2219.64,1647.01])

    def test_rejected_update_then_valid_five_against_five_is_sequence_failure(self):
        case=self.case('m6-eight')
        case['turns'][0]['fake']['output']['arguments']={'operation':'compare_original','changes':{}}
        # Even when a test expects the rejection, the requested calculation state
        # must still fail; this proves the sequence gate is independent.
        case['turns'][0]['expected']['host_accept']=False
        report=ev.evaluate(cases=[case]);first,second=report['rows']
        self.assertEqual(first['stage'],'host_rejected')
        self.assertTrue(second['metrics']['arguments'])
        self.assertTrue(second['host_accepted'])
        self.assertEqual(second['deterministic_calculation']['parameters']['rate'],5)
        self.assertFalse(first['expected_calculation_met'])
        self.assertFalse(second['expected_calculation_met'])
        self.assertFalse(report['calculation_sequences'][0]['passed'])
        self.assertFalse(report['fixture_expectations_met'])
        self.assertTrue(all(r['tool_execution_count']==0 for r in report['rows']))

    def test_missing_calculation_and_evaluator_labels_never_exported(self):
        case=self.case('m6-eight');seen=[];original=ev.MeasuredFakeProvider.generate
        def capture(provider,request):
            seen.extend(m.content for m in request.messages)
            return original(provider,request)
        case['turns'][0]['expected']['calculation_parameters']['PRIVATE_EXPECTATION_MARKER']=True
        for turn in case['turns']:
            turn['fake']['output'].update(kind='clarification',capability=None,arguments={})
        with patch.object(ev.MeasuredFakeProvider,'generate',capture):
            report=ev.evaluate(cases=[case])
        self.assertNotIn('PRIVATE_EXPECTATION_MARKER',' '.join(seen))
        self.assertFalse(report['calculation_sequences'][0]['passed'])
        self.assertTrue(all(r['deterministic_calculation'] is None for r in report['rows']))




class M6VerificationBoundaryTests(unittest.TestCase):
    def test_request_scope_excludes_quotes_negations_and_general_questions(self):
        for text in ('Can I call it verified now?', 'Is the fix verified?', 'Has it been verified?'):
            self.assertIsNotNone(interpretation.verification_followup(text))
        for text in ('Say "Can I call it verified now?"', 'Do not call it verified.',
                     'How do I verify a fix?', 'Is my account verified?', 'Explain verification.',
                     'Can I call it verified now? Also open a file.'):
            self.assertIsNone(interpretation.verification_followup(text))

    def test_contextual_interpretation_uses_same_boundary(self):
        owner=Orchestrator();owner.context=ActiveContext(expires=owner.clock()+900)
        working=WorkingContextV1();turn='a'*32
        proposal=interpretation.parse(json.dumps(dict(version=1,turn=turn,kind='conversation',
            text='The verification is complete.',capability=None,arguments={},context=None)),turn)
        result=interpretation.apply(proposal,turn=turn,owner_text='Can I call it verified now?',
            orchestrator=owner,brain=None,working=working)
        self.assertEqual(result['response_source'],'host_verification_boundary')
        self.assertFalse(result['capability_applied'])
        self.assertEqual(owner.context.skill.rate,5)

    def test_runtime_blocks_false_claim_and_retains_only_host_reply_in_history(self):
        self.runtime_check(True,'Can I call it verified now?',True)

    def test_runtime_default_off_is_unchanged(self):
        self.runtime_check(False,'Can I call it verified now?',False)

    def test_runtime_unrelated_question_is_unchanged(self):
        self.runtime_check(True,'Explain how software tests work.',False)

    def test_semantic_host_warning_keeps_host_provenance(self):
        import tempfile
        from pathlib import Path
        from iris.desktop.runtime import DesktopRuntime
        from tests import test_brain_engine as fixtures

        brain,_,_=fixtures.BrainEngineTests().make_brain()

        with tempfile.TemporaryDirectory() as folder:
            app=DesktopRuntime(settings={
                'IRIS_PROVIDER_URL':'http://127.0.0.1:9',
                'IRIS_MODEL':'synthetic',
                'IRIS_AUTO_ORGANIZE_ENABLED':'false',
                'IRIS_EXPERIMENTAL_INTERPRETATION':'true'
            },data_dir=Path(folder)/'data',brain=brain)

            try:
                warning=interpretation.verification_followup(
                    'Can I call it verified now?'
                )

                with patch.object(app,'_semantic_answer',return_value={
                    'reply':warning,
                    'route':'FAST-EXPERIMENTAL',
                    'conversation_context':True,
                    'response_source':'host_verification_boundary'
                }):
                    answer=app.chat('Can I call it verified now?')

                self.assertEqual(answer['reply'],warning)

                snapshot=app.working_context.snapshot(app.orchestrator)
                refs=[
                    r for r in snapshot['references']
                    if r['text']==warning
                ]

                self.assertEqual(len(refs),1)
                self.assertEqual(refs[0]['source'],Source.GUIDANCE)
                self.assertIn('not a test receipt',prompt(snapshot))

            finally:
                app.close()

    def runtime_check(self,enabled,request,guarded):
        import tempfile
        from pathlib import Path
        from iris.desktop.runtime import DesktopRuntime
        from iris.brain.llm import LLMResponse
        from tests import test_brain_engine as fixtures
        brain,fast,deep=fixtures.BrainEngineTests().make_brain()
        raw='The verification is complete. The fix has been confirmed as working.'
        with tempfile.TemporaryDirectory() as folder:
            app=DesktopRuntime(settings={'IRIS_PROVIDER_URL':'http://127.0.0.1:9',
                'IRIS_MODEL':'synthetic','IRIS_AUTO_ORGANIZE_ENABLED':'false',
                'IRIS_EXPERIMENTAL_INTERPRETATION':str(enabled).lower()},
                data_dir=Path(folder)/'data',brain=brain)
            try:
                with patch.object(fast,'generate',return_value=LLMResponse(raw,'fast','fast-model')) as calls:
                    answer=app.chat(request)
                self.assertEqual(calls.call_count,1)
                if guarded:
                    self.assertEqual(answer['response_source'],'host_verification_boundary')
                    self.assertNotIn('verification is complete',answer['reply'])
                    self.assertEqual(app.history[-1].content,answer['reply'])
                    snapshot = app.working_context.snapshot(app.orchestrator)
                    self.assertNotIn(raw,str(snapshot))
                    matching = [ref for ref in snapshot['references']
                                if ref['text'] == answer['reply']]
                    self.assertEqual(len(matching),1)
                    self.assertEqual(matching[0]['source'],Source.GUIDANCE)
                else:
                    self.assertEqual(answer['reply'],raw)
            finally:
                app.close()


class M61ConversationTests(unittest.TestCase):
    def case(self):
        return copy.deepcopy(ev.load_cases(ev.M6_CORPUS.with_name('m61_development.json'))[0])

    def test_five_turn_state_chain_uses_deterministic_results(self):
        report=ev.evaluate(cases=[self.case()],max_calls=5,duration=180)
        self.assertTrue(report['fixture_expectations_met'])
        self.assertEqual(report['actual_adapter_calls'],5)
        self.assertEqual(report['actual_external_calls'],0)
        self.assertEqual(report['calculation_sequences'],[dict(case='m61-five-turn-compound',expected_turns=5,observed_turns=5,passed=True)])
        for row in report['rows']:
            self.assertTrue(row['expected_calculation_met'])
            self.assertEqual(row['tool_execution_count'],0)
        self.assertEqual(report['rows'][2]['deterministic_calculation']['visual']['points'][-1],[10,2219.64,1647.01])
        self.assertEqual(report['human_quality']['status'],'unreviewed')

    def test_plausible_prose_cannot_replace_calculation(self):
        case=self.case()
        case['turns'][1]['fake']['output'].update(kind='conversation',text='Done, the new total is 9999.',capability=None,arguments={})
        report=ev.evaluate(cases=[case])
        self.assertFalse(report['fixture_expectations_met'])
        self.assertFalse(report['calculation_sequences'][0]['passed'])
        self.assertIsNone(report['rows'][1]['deterministic_calculation'])
        self.assertFalse(report['rows'][2]['expected_calculation_met'])
        self.assertTrue(report['rows'][4]['expected_calculation_met'])

    def test_wrong_operation_cannot_be_hidden_by_later_recovery(self):
        case=self.case()
        case['turns'][1]['fake']['output']['arguments']={'operation':'compare_original','changes':{}}
        report=ev.evaluate(cases=[case])
        self.assertEqual(report['rows'][1]['stage'],'host_rejected')
        self.assertFalse(report['calculation_sequences'][0]['passed'])
        self.assertTrue(report['rows'][4]['expected_calculation_met'])

    def test_stale_context_is_rejected(self):
        case=self.case()
        case['turns'][2]['fake']['output']['context']={'id':'a'*32,'revision':0}
        report=ev.evaluate(cases=[case])
        self.assertEqual(report['rows'][2]['stage'],'host_rejected')
        self.assertFalse(report['calculation_sequences'][0]['passed'])

    def test_incomplete_conversation_is_not_a_pass(self):
        report=ev.evaluate(cases=[self.case()],max_calls=4)
        self.assertFalse(report['calculation_sequences'][0]['passed'])
        self.assertFalse(report['fixture_expectations_met'])

    def test_five_turn_context_preserves_owner_anchor_without_test_receipts(self):
        case=copy.deepcopy(next(c for c in ev.load_cases(ev.M6_CORPUS) if c['id']=='m6-specific-context'))
        case.update(id='m61-five-turn-verification',offline_only=True)
        for request,answer in [
            ('Which problem were we discussing?', 'The Java inventory file-saving problem.'),
            ('I have only changed the code.', 'That is a reported change, not a test result.'),
            ('Is the fix verified?', 'The verification is complete.')]:
            case['turns'].append({'request':request,'fake':{'response_text':answer},'expected':{'host_accept':True,'route':'FAST'}})
        seen=[]; original=ev.MeasuredFakeProvider.generate
        def capture(provider,request):
            seen.append(request)
            return original(provider,request)
        with patch.object(ev.MeasuredFakeProvider,'generate',capture):
            report=ev.evaluate(cases=[case],max_calls=5,duration=180)
        self.assertEqual(len(seen),5)
        self.assertIn('Java inventory application',seen[-1].messages[0].content)
        self.assertIn('I have only changed the code',str(seen[-1].messages))
        self.assertEqual(report['rows'][-1]['host_response_source'],'host_verification_boundary')
        self.assertEqual(report['human_quality']['status'],'unreviewed')
        for record in report['review']['records']:
            self.assertEqual(record['synthetic_context']['verified_result_references'],[])
        self.assertTrue(all(row['tool_execution_count']==0 for row in report['rows']))

    def test_five_turn_phrase_variants_preserve_same_state_chain(self):
        variants=[
            ['Please explain compound interest.', 'Set the rate to 8 percent.', 'Contrast that with the original.', 'Explain the difference.', 'Restore the original example.'],
            ['Could you show me how compound interest works?', 'Try eight percent as the rate.', 'Please compare that to the original.', 'Show that.', 'Please reset the example.'],
            ['Walk me through compound interest.', 'Change the rate to 8%.', 'Compare it with the initial example.', 'Could you explain the difference?', 'Reset it.']]
        for requests in variants:
            with self.subTest(requests=requests):
                case=self.case()
                for turn,request in zip(case['turns'],requests):
                    turn['request']=request
                report=ev.evaluate(cases=[case],max_calls=5,duration=180)
                self.assertTrue(report['fixture_expectations_met'])
                self.assertTrue(report['calculation_sequences'][0]['passed'])
                self.assertEqual(report['actual_adapter_calls'],5)
                self.assertTrue(all(r['tool_execution_count']==0 for r in report['rows']))

    def test_ambiguous_or_negated_update_cannot_change_state(self):
        requests=['Set the rate to eight or nine percent.',
                  'Set the rate between eight and nine percent.',
                  'Change the rate to eight percent and the years to twelve.',
                  'Do not change the rate to eight percent.',
                  'Set it to eight.',
                  'She said "set the rate to eight percent".']
        for request in requests:
            with self.subTest(request=request):
                case=self.case();case['turns'][1]['request']=request
                report=ev.evaluate(cases=[case])
                self.assertEqual(report['rows'][1]['stage'],'host_rejected')
                self.assertIsNone(report['rows'][1]['deterministic_calculation'])
                self.assertEqual(report['rows'][2]['deterministic_calculation']['parameters']['rate'],5)
                self.assertFalse(report['calculation_sequences'][0]['passed'])
                self.assertTrue(report['rows'][4]['expected_calculation_met'])
                self.assertTrue(all(r['tool_execution_count']==0 for r in report['rows']))

    def test_model_value_cannot_override_requested_rate(self):
        for proposed in (5,9,80):
            with self.subTest(proposed=proposed):
                case=self.case()
                case['turns'][1]['fake']['output']['arguments']['changes']['rate']=proposed
                report=ev.evaluate(cases=[case])
                self.assertEqual(report['rows'][1]['stage'],'host_rejected')
                self.assertEqual(report['rows'][2]['deterministic_calculation']['parameters']['rate'],5)
                self.assertFalse(report['calculation_sequences'][0]['passed'])

    def test_corpus_cannot_be_sent_to_live_provider(self):
        with self.assertRaises(ValueError):
            ev.evaluate(cases=[self.case()],live_provider=object())


class M62RecoveryTests(unittest.TestCase):
    case = M61ConversationTests.case
    # Reuse fixture construction, not the inherited test methods.
    def recovery(self, request, corrected, *, proposed=8, stale=False):
        case=self.case();case['id']='m62-recovery'
        case['turns'][1]['request']=request
        case['turns'][1]['fake']['output']['arguments']['changes']['rate']=proposed
        case['turns'][1]['expected'].update(host_accept=False,no_effects=True)
        if stale:
            case['turns'][1]['fake']['output']['context']='$stale'
        correction=copy.deepcopy(self.case()['turns'][1]);correction['request']=corrected
        case['turns']=[case['turns'][0],case['turns'][1],correction,case['turns'][2],case['turns'][4]]
        return case

    def test_recovery_preserves_failure_and_has_one_attempt_per_turn(self):
        for request,corrected,options,missing in [
            ('Set it to eight.','I meant the annual interest rate. Make it 8%.',{},'parameter'),
            ('Try eight or nine percent.','Use eight percent.',{},'single annual interest rate'),
            ('Try eight percent.','Use eight percent.',{'proposed':9},'specify'),
            ('Try eight percent.','Use eight percent.',{'stale':True},'specify')]:
            with self.subTest(request=request,options=options):
                report=ev.evaluate(cases=[self.recovery(request,corrected,**options)],max_calls=5)
                failed=report['rows'][1];recovered=report['rows'][2]
                self.assertEqual(failed['stage'],'host_rejected')
                self.assertTrue(failed['metrics']['security_expectation'])
                self.assertIn(missing,failed['host_response'])
                self.assertEqual(failed['host_response_source'],'host_clarification')
                self.assertTrue(recovered['expected_calculation_met'])
                self.assertTrue(report['rows'][3]['expected_calculation_met'])
                self.assertFalse(report['calculation_sequences'][0]['passed'])
                self.assertEqual([row['adapter_calls'] for row in report['rows']],[1]*5)
                self.assertTrue(all(not row['receipts'] and row['tool_execution_count']==0 for row in report['rows']))


class M62ContextTests(unittest.TestCase):
    def test_rejected_turn_context_is_guidance_and_not_calculation_evidence(self):
        case=M62RecoveryTests().recovery('Set it to eight.','Use eight percent.')
        report=ev.evaluate(cases=[case])
        before_recovery=report['review']['records'][2]['synthetic_context']
        warnings=[r for r in before_recovery['references'] if r['source']==Source.GUIDANCE]
        self.assertEqual(len(warnings),1)
        self.assertIn('parameter',warnings[0]['text'])
        self.assertEqual(before_recovery['scenario']['parameters']['rate'],5)
        self.assertEqual(before_recovery['scenario']['revision'],1)
        self.assertEqual(report['review']['records'][3]['synthetic_context']['scenario']['revision'],2)

    def test_explicit_transition_clears_scenario_before_interpretation(self):
        case=M61ConversationTests().case()
        case['turns'][1]['request']='New topic: tell me about Java file saving.'
        case['turns'][1]['expected'].update(host_accept=False,no_effects=True)
        report=ev.evaluate(cases=[case])
        self.assertIsNone(report['review']['records'][1]['synthetic_context']['scenario'])
        self.assertFalse(report['rows'][1]['host_accepted'])
        self.assertTrue(report['rows'][1]['metrics']['security_expectation'])
        self.assertIsNone(report['rows'][2]['deterministic_calculation'])

    def test_owner_model_guidance_and_result_remain_distinct(self):
        clock=[0.0];working=WorkingContextV1(clock=lambda:clock[0],ttl=2)
        owner=Orchestrator(clock=lambda:clock[0]);owner.context=ActiveContext(expires=2)
        for text,source in [('My Java app saves files.',Source.OWNER),('The test passed.',Source.MODEL),('Please test it.',Source.GUIDANCE)]:
            working.remember(text,source=source,privacy=Privacy.CONVERSATION,export=Export.REASONING)
        state=working.snapshot(owner)
        self.assertEqual([r['source'] for r in state['references']],[Source.OWNER,Source.MODEL,Source.GUIDANCE])
        self.assertEqual(len(state['verified_result_references']),1)
        self.assertEqual(state['verified_result_references'][0]['kind'],'compound_calculation')
        clock[0]=3
        state=working.snapshot(owner)
        self.assertEqual(state['references'],[])
        self.assertEqual(state['verified_result_references'],[])


if __name__=='__main__':unittest.main()

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.brain.llm import LLMResponse
from iris.desktop.runtime import DesktopRuntime
from iris.generalist.controlled_plan import parse_proposal, validate_proposal, preview_text
from iris.generalist.orchestration import Orchestrator
from iris.memory.working import WorkingContextV1
from iris.tools import ToolExecutor
from iris.tools.workspace import workspace_registry
from tests import test_brain_engine as fixtures


def proposal(turn='a'*32,nodes=None,**extra):
    value={'version':1,'turn':turn,'objective':'List the workspace and inspect the named README snapshot.',
           'nodes':nodes if nodes is not None else [
               {'id':'list','tool':'workspace_list','arguments':{'path':'.'},'depends_on':[]},
               {'id':'read','tool':'workspace_read','arguments':{'path':'README.md','max_chars':1000},'depends_on':['list']}],
           'context_refs':[]}
    value.update(extra)
    return json.dumps(value)


class PlanPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.executor=ToolExecutor(workspace_registry(self.temp.name))
        self.working=WorkingContextV1();self.owner=Orchestrator()

    def validate(self,raw=None,permissions=frozenset({'workspace.read'})):
        return validate_proposal(parse_proposal(raw or proposal(),'a'*32),
            request='/plan workspace List then read README.md',turn='a'*32,session='test-session',
            executor=self.executor,permissions=permissions,working=self.working,orchestrator=self.owner)

    def test_preview_does_not_check_nonexistent_file_or_execute(self):
        plan=self.validate()
        self.assertEqual(plan.plan.order,('list','read'))
        self.assertEqual(len(plan.digest),64)
        self.assertIn('No actions have been executed',preview_text(plan))
        self.assertFalse((Path(self.temp.name)/'README.md').exists())

    def test_wire_authority_duplicate_fields_and_stale_turn(self):
        for raw in (proposal(approved=True),proposal(origin='user'),proposal(version=True),proposal(turn='old'),
                    proposal().replace('"version": 1','"version": 1, "version": 1'), ' '*12001):
            with self.assertRaises(ValueError):self.validate(raw)

    def test_unknown_tools_arguments_cycles_output_references_and_limits(self):
        base=json.loads(proposal())
        variants=[]
        for tool,args in [('shell',{'command':'inert'}),('workspace_read',{'path':'../escape.md'}),
                         ('workspace_read',{'path':'${list.first}'}),('workspace_read',{'path':'file.md','max_chars':True}),
                         ('workspace_read',{'path':'file.md','max_chars':1e100}),('workspace_list',{'path':'.','approved':True})]:
            variants.append([{'id':'step','tool':tool,'arguments':args,'depends_on':[]}])
        variants += [base['nodes']*2,[dict(base['nodes'][0],depends_on=['read']),base['nodes'][1]],
                     [dict(base['nodes'][0],depends_on=['missing'])],
                     [dict(base['nodes'][0],output_ref='x')]]
        for nodes in variants:
            with self.subTest(nodes=nodes),self.assertRaises(ValueError):self.validate(proposal(nodes=nodes))

    def test_missing_permission_and_forged_context_denied(self):
        with self.assertRaises(ValueError):self.validate(permissions=frozenset())
        with self.assertRaises(ValueError):self.validate(proposal(context_refs=[{'id':'f'*32,'revision':0}]))

    def test_prepared_arguments_are_in_preview_and_digest(self):
        self.executor._registry._preparers['workspace_list']=lambda args:({'path':'docs'},'Canonical directory')
        plan=self.validate()
        self.assertEqual(dict(plan.plan.nodes[0].arguments),{'path':'docs'})
        self.assertIn('docs',preview_text(plan))
        self.executor._registry._preparers.clear()
        self.assertNotEqual(plan.digest,self.validate().digest)


class PlanRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'workspace';self.root.mkdir()
        (self.root/'README.md').write_text('Synthetic project notes.\n',encoding='utf-8')
        brain,self.fast,_=fixtures.BrainEngineTests().make_brain()
        brain._tool_executor=ToolExecutor(workspace_registry(self.root))
        brain._tool_permissions=frozenset({'workspace.read'})
        self.app=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9',
            'IRIS_AUTO_ORGANIZE_ENABLED':'false','IRIS_EXPERIMENTAL_INTERPRETATION':'true'},
            data_dir=Path(self.temp.name)/'data',brain=brain)
        self.addCleanup(self.app.close)

    def preview(self,nodes=None):
        def generate(request):
            data=json.loads(request.messages[-1].content)
            return LLMResponse(proposal(data['turn'],nodes),'fast','fast-model')
        with patch.object(self.fast,'generate',side_effect=generate) as model:
            answer=self.app.chat('/plan workspace List files, then read README.md')
        self.assertEqual(model.call_count,1)
        return answer

    def test_model_proposal_previews_without_tools_history_or_memory(self):
        answer=self.preview()
        self.assertIn('No actions have been executed',answer['reply'])
        self.assertEqual(self.app.action_history.rows(),[])
        self.assertEqual(self.app.history,[])
        self.assertEqual(self.app.working_context.snapshot(self.app.orchestrator)['references'],[])

    def test_disabled_and_malformed_proposals_do_not_run(self):
        self.app.settings['IRIS_EXPERIMENTAL_INTERPRETATION']='false'
        with patch.object(self.fast,'generate',side_effect=AssertionError('must not call')):
            self.assertIn('disabled',self.app.chat('/plan workspace list')['reply'])
        self.app.settings['IRIS_EXPERIMENTAL_INTERPRETATION']='true'
        with patch.object(self.fast,'generate',return_value=LLMResponse('{"approved":true}','fast','fast-model')) as model:
            self.assertIn('No tools executed',self.app.chat('/plan workspace list')['reply'])
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.app.action_history.rows(),[])

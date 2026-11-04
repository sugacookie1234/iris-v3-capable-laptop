from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import tempfile
import unittest
from iris.desktop.runtime import DesktopRuntime,BusyError
from iris.desktop.visual_window import VisualWindowController
from tests.test_desktop import FakeBrain
from tests.test_desktop_app import Event

class WindowTests(unittest.TestCase):
    def test_coalesced_ui_dispatch_close_reopen_shutdown(self):
        queue=[];windows=[];revoke=Mock()
        def create():
            window=SimpleNamespace(events=SimpleNamespace(closed=Event()),destroy=Mock())
            windows.append(window);return window
        control=VisualWindowController(queue.append,create,revoke)
        control.request('one',1);control.request('one',2)
        self.assertEqual(windows,[]);self.assertEqual(len(queue),1)
        queue.pop(0)();self.assertEqual(len(windows),1)
        control.request('one',3);queue.pop(0)();self.assertEqual(len(windows),1)
        control.closed(windows[0]);control.request('one',4);queue.pop(0)()
        self.assertEqual(len(windows),1) # Manual close survives ordinary updates.
        control.request('one',4,action='open');queue.pop(0)();self.assertEqual(len(windows),2)
        control.request('one',2);self.assertEqual(queue,[])
        control.shutdown_on_ui();windows[1].destroy.assert_called_once()
        control.request('two',1);self.assertEqual(queue,[])
    def test_explicit_open_renews_auth_without_duplicate_window(self):
        queue=[];window=SimpleNamespace(events=SimpleNamespace(closed=Event()),destroy=Mock())
        create=Mock(return_value=window);refresh=Mock()
        control=VisualWindowController(queue.append,create,Mock(),refresh=refresh)
        control.request('one',1);queue.pop(0)()
        control.request('one',1,action='open');queue.pop(0)()
        create.assert_called_once();refresh.assert_called_once_with(window)
        control.request('two',1);queue.pop(0)()
        self.assertEqual(refresh.call_count,2)

    def test_close_before_queued_open_and_creation_failure(self):
        queue=[];create=Mock(side_effect=RuntimeError('synthetic'))
        control=VisualWindowController(queue.append,create,Mock())
        control.request('one',1);control.request(action='close');queue.pop(0)();create.assert_not_called()
        control.request('one',1,action='open');queue.pop(0)()
        self.assertEqual(control.state,'closed');self.assertTrue(control.manually_closed)

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.brain=FakeBrain()
        self.app=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9','IRIS_AUTO_ORGANIZE_ENABLED':'false'},data_dir=Path(self.temp.name),brain=self.brain)
        self.addCleanup(self.app.close)
        self.app.visual_window=SimpleNamespace(request=Mock(),state='open')
    def test_voice_ui_replay_and_organizer_bypass(self):
        with patch.object(self.app.autonomy,'submit') as organize:
            self.app.chat('Explain compound interest')
            first=self.app.visual_state()
            self.app.chat('What if the rate was uh 8%?')
            self.app.chat('Compare it with five percent')
            self.app.chat('Why is there such a difference?')
            state=self.app.visual_state()
            self.assertEqual(state['id'],first['id']);self.assertGreater(state['revision'],first['revision'])
            changed=self.app.update_visual({'id':state['id'],'revision':state['revision'],'changes':{'principal':2000,'rate':7}})
            self.assertEqual(changed['parameters']['principal'],2000)
            self.assertIn('7%',self.app.chat('Why did the balance increase?')['reply'])
            self.app.chat('What happens if I contribute 200 units every month?')
            self.assertEqual(self.app.visual_state()['parameters']['contribution'],200)
            self.app.chat('Restore the original example')
            self.assertEqual(self.app.visual_state()['parameters'],{'principal':1000,'rate':5,'years':10,'contribution':0,'compared_rate':None})
            self.app.chat('Close the graph');self.app.visual_window.request.assert_called_with(action='close')
            self.app.chat('Open the graph again');self.assertEqual(self.app.visual_window.request.call_args.kwargs['action'],'open')
            self.assertEqual(self.brain.calls,[]);organize.assert_not_called()
    def test_personal_commitments_reach_normal_organizer_path(self):
        for text in ('I will contribute 200 units monthly',
                     'Remind me to review the graph tomorrow',
                     'I plan to save for five years'):
            with self.subTest(text=text):
                self.app.chat('Explain compound interest')
                skill=self.app.orchestrator.context.skill
                before=skill.parameters()
                with patch.object(self.app.autonomy,'submit') as organize:
                    reply=self.app.chat(text)
                    organize.assert_called_once()
                    self.assertEqual(organize.call_args.args[0],text)
                self.assertNotIn('visual',reply)
                self.assertEqual(skill.parameters(),before)
                self.assertIsNone(self.app.orchestrator.context)

    def test_invalid_duplicate_and_expired_updates_preserve_state(self):
        self.app.chat('Explain compound interest');state=self.app.visual_state()
        for changes in ({'principal':-1},{'years':1.5},{'rate':True},{'html':'<script>'}):
            with self.assertRaises(ValueError):self.app.update_visual({'id':state['id'],'revision':state['revision'],'changes':changes})
            current=self.app.visual_state()
            self.assertEqual({k:v for k,v in current.items() if k!='expires_in'},{k:v for k,v in state.items() if k!='expires_in'})
        request={'id':state['id'],'revision':state['revision'],'changes':{'rate':8}}
        self.app.update_visual(request)
        with self.assertRaises(BusyError):self.app.update_visual(request)
        self.app.orchestrator.context.expires=0
        with self.assertRaises(BusyError):self.app.update_visual(request)
    def test_contribution_matches_closed_form(self):
        from decimal import Decimal,localcontext
        self.app.chat('Explain compound interest');state=self.app.visual_state()
        result=self.app.update_visual({'id':state['id'],'revision':state['revision'],'changes':{'principal':2000,'contribution':200,'rate':8}})
        with localcontext() as ctx:
            ctx.prec=40;r=Decimal(8)/1200;q=(1+r)**120
            expected=(Decimal(2000)*q+Decimal(200)*(q-1)/r).quantize(Decimal('.01'))
        self.assertEqual(Decimal(str(result['totals']['final'])),expected)
        self.assertEqual(result['totals']['contributed'],26000)

    def test_concurrent_edits_accept_at_most_one_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        self.app.chat('Explain compound interest');state=self.app.visual_state();gate=threading.Barrier(2)
        def edit(rate):
            gate.wait()
            try:return self.app.update_visual({'id':state['id'],'revision':state['revision'],'changes':{'rate':rate}})['parameters']['rate']
            except BusyError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(edit,[7,8]))
        self.assertEqual(sum(result is not None for result in results),1)
        self.assertEqual(self.app.visual_state()['revision'],state['revision']+1)

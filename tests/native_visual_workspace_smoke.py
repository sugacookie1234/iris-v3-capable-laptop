r"""Opt-in real WebView2 smoke. Opens only synthetic windows; never run in unittest discovery.
Run from repo root: .venv\Scripts\python.exe tests/native_visual_workspace_smoke.py
WebView2 may briefly retain its synthetic temp profile after window shutdown.
"""
import json,sys,threading,time,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from iris.desktop import app
from iris.desktop.runtime import DesktopRuntime
from tests.test_desktop import FakeBrain
from unittest.mock import patch
result={}
servers=[]
original_server=app.DesktopServer
def capture_server(*args,**kwargs):
    server=original_server(*args,**kwargs);servers.append(server);return server
deadline=time.monotonic()+120
def wait_for(check,timeout=25):
    end=min(time.monotonic()+timeout,deadline)
    while time.monotonic()<end:
        try:
            value=check()
            if value:return value
        except Exception:pass
        time.sleep(.15)
    raise RuntimeError('Synthetic native acceptance timed out')
with tempfile.TemporaryDirectory(prefix='iris-visual-smoke-',ignore_cleanup_errors=True) as directory:
    runtime=DesktopRuntime(settings={'IRIS_MODEL':'synthetic','IRIS_PROVIDER_URL':'http://127.0.0.1:9','IRIS_AUTO_ORGANIZE_ENABLED':'false'},data_dir=Path(directory),brain=FakeBrain())
    def exercise():
        try:
            main=wait_for(lambda:webview.windows and webview.windows[0])
            wait_for(lambda:main.native is not None)
            wait_for(lambda:main.events.loaded.is_set())
            wait_for(lambda:main.evaluate_js("!!document.getElementById('typeBox') && !location.hash && !!window.irisPairing"))
            runtime.chat('Explain compound interest')
            child=wait_for(lambda:runtime.visual_window.window)
            wait_for(lambda:child.evaluate_js("document.querySelector('svg')!==null"))
            result['native_svg']=True
            result['keyboard_activation_enabled']=child.focus is True
            # Attempt a real cross-origin fetch from the restricted child. The
            # synthetic runtime has no private owner records and no live providers.
            main_origin=wait_for(lambda:child.evaluate_js('location.origin')).replace('://localhost:', '://127.0.0.1:')
            child.evaluate_js("window.__irisProbe='pending';fetch("+json.dumps(main_origin+'/api/memories')+",{credentials:'include'}).then(r=>window.__irisProbe='http:'+r.status).catch(()=>window.__irisProbe='blocked');")
            blocked=wait_for(lambda:child.evaluate_js("window.__irisProbe !== 'pending' && window.__irisProbe"))
            if blocked != 'blocked':raise RuntimeError('Visual-to-main fetch was not blocked: '+str(blocked))
            result['visual_to_main_fetch_blocked']=True
            runtime.chat('Change the rate to eight percent')
            wait_for(lambda:'2,219.64' in str(child.evaluate_js("document.getElementById('totals').textContent")))
            result['same_window_updates']=runtime.visual_window.window is child
            child.evaluate_js("document.getElementById('principal').value='2000';document.getElementById('controls').dispatchEvent(new Event('submit',{cancelable:true}));")
            wait_for(lambda:runtime.visual_state()['parameters']['principal']==2000)
            result['ui_to_host']=True
            runtime.chat('Close the graph');wait_for(lambda:runtime.visual_window.window is None)
            result['main_continues']=main in webview.windows
            result['phase']='reopen-create'
            runtime.chat('Open the graph again');second=wait_for(lambda:runtime.visual_window.window)
            result['phase']='reopen-render'
            wait_for(lambda:second.evaluate_js("document.querySelector('svg')!==null"))
            result['reopen']=second is not child
            result['stress_cycles']=0
            for iteration in range(2):
                runtime.chat('Close the graph');wait_for(lambda:runtime.visual_window.window is None)
                runtime.chat('Open the graph again');current=wait_for(lambda:runtime.visual_window.window)
                wait_for(lambda:current.evaluate_js("document.documentElement.dataset.visualState === 'rendered'"))
                runtime.chat('Use eight percent')
                revision=runtime.visual_state()['revision']
                wait_for(lambda:current.evaluate_js("document.getElementById('status').textContent")==f'Active example \u00b7 revision {revision}')
                current.evaluate_js("document.getElementById('principal').value='3000';document.getElementById('controls').dispatchEvent(new Event('submit',{cancelable:true}));")
                wait_for(lambda:runtime.visual_state()['parameters']['principal']==3000)
                result['stress_cycles']+=1
            server=servers[0]
            with server._bootstrap_lock:
                server._visual_session=(server._visual_session[0],0)
            wait_for(lambda:current.evaluate_js("document.documentElement.dataset.visualState === 'expired'"))
            result['expiry']=True
            runtime.chat('Open the graph again')
            wait_for(lambda:current.evaluate_js("document.documentElement.dataset.visualState === 'rendered'"))
            result['reauthentication']=runtime.visual_window.window is current
            result['provider_calls']=len(runtime.brain.calls)
        except Exception as error:
            result['error']=type(error).__name__+': '+str(error)[:120]
            result['controller_state']=runtime.visual_window.state
            child=runtime.visual_window.window
            if child:
                try:result['synthetic_page_status']=child.evaluate_js("({path:location.pathname,hashPresent:!!location.hash,pairingPromise:!!window.irisPairing,renderer:typeof window.renderVisual,status:document.getElementById('status')?.textContent,pair:document.getElementById('pairStatus')?.textContent,resources:performance.getEntriesByType('resource').map(r=>({path:new URL(r.name).pathname,status:r.responseStatus,bytes:r.decodedBodySize}))})")
                except Exception:result['synthetic_page_status']='unavailable'
        finally:
            Path('.local/visual-native-smoke-result.json').write_text(json.dumps(result),encoding='utf-8')
            try:webview.windows[0].destroy()
            except Exception:pass
    threading.Thread(target=exercise,daemon=True).start()
    with (patch.object(app,'DesktopServer',side_effect=capture_server),
          patch.object(app,'install_tray',return_value=None),
          patch.object(app,'TITLE','IRIS synthetic Visual Workspace acceptance'),
          patch('iris.desktop.server.dashboard_markets',return_value={'items':[]}),
          patch('iris.desktop.server.dashboard_weather',side_effect=ValueError('Synthetic weather disabled')),
          patch('iris.desktop.server.NativeClapListener.update',side_effect=ValueError('Synthetic microphone disabled')),
          patch('urllib.request.urlopen',side_effect=AssertionError('Synthetic native test blocks provider network'))):
        app.run_window(webview,runtime,port=0)
result['shutdown']=runtime.visual_window.disposed and runtime.visual_window.window is None
if Path(directory).exists():result['synthetic_profile_cleanup']='deferred until WebView2 releases its files'
print(json.dumps(result))
sys.exit(1 if 'error' in result else 0)

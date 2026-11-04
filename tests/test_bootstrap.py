import http.client
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from iris.desktop.server import DesktopServer

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.server=DesktopServer(('127.0.0.1',0),SimpleNamespace())
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def request(self,method,path,body=None,origin=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
        try:
            headers={'Content-Type':'application/json','X-IRIS-Request':'1'}
            if origin:headers['Origin']=origin
            c.request(method,path,json.dumps(body) if body is not None else None,headers)
            r=c.getresponse();result=(r.status,r.getheader('Set-Cookie'));r.read();return result
        finally:c.close()
    def test_homepage_and_assets_never_issue_cookie(self):
        for path in ('/','/pair.js','/app.js'):
            self.assertEqual(self.request('GET',path),(200,None))
        self.assertEqual(self.request('GET','/api/status')[0],403)
    def test_pair_requires_exact_origin_and_consumes_token_once(self):
        token=self.server.bootstrap_url().split('#pair=')[1]
        for origin in (None,'null','https://evil.example'):
            self.assertEqual(self.request('POST','/api/pair',{'token':token},origin)[0],403)
        origin=f'http://127.0.0.1:{self.server.server_address[1]}'
        status,cookie=self.request('POST','/api/pair',{'token':token},origin)
        self.assertEqual(status,200);self.assertIn('HttpOnly',cookie)
        self.assertEqual(self.request('POST','/api/pair',{'token':token},origin),(403,None))
    def test_expiry_replacement_invalid_and_failed_attempt_limit(self):
        with patch('iris.desktop.server.time.monotonic',return_value=100):
            old=self.server.bootstrap_url().split('#pair=')[1]
            token=self.server.bootstrap_url().split('#pair=')[1]
            self.assertFalse(self.server.redeem_bootstrap(old))
        with patch('iris.desktop.server.time.monotonic',return_value=161):
            self.assertFalse(self.server.redeem_bootstrap(token))
            fresh=self.server.bootstrap_url().split('#pair=')[1]
            for _ in range(10):self.assertFalse(self.server.redeem_bootstrap('wrong'))
            self.assertFalse(self.server.redeem_bootstrap(fresh))

    def test_concurrent_redemption_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        token=self.server.bootstrap_url().split('#pair=')[1]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(self.server.redeem_bootstrap,[token]*8))
        self.assertEqual(sum(results),1)

    def test_authenticated_chat_quota_prevents_execution(self):
        from iris.desktop.limits import UsageLimits
        from unittest.mock import Mock
        self.server.limits=UsageLimits({'IRIS_LIMIT_CHAT_PER_MINUTE':'1'})
        self.server.runtime.chat=Mock(return_value={'reply':'Synthetic'})
        for expected in (200,429):
            c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
            try:
                c.request('POST','/api/chat',json.dumps({'text':'hello'}),
                    {'Cookie':'iris_session='+self.server.session,'X-IRIS-Request':'1','Content-Type':'application/json'})
                r=c.getresponse();self.assertEqual(r.status,expected);r.read()
            finally:c.close()
        self.server.runtime.chat.assert_called_once()

    def test_visual_pairing_does_not_replace_main_and_is_revocable(self):
        from concurrent.futures import ThreadPoolExecutor
        main=self.server.bootstrap_url().split('#pair=')[1]
        visual=self.server.visual_bootstrap_url().split('#pair=')[1]
        with ThreadPoolExecutor(max_workers=4) as pool:
            leases=list(pool.map(self.server.redeem_visual,[visual]*4))
        valid=[lease for lease in leases if lease]
        self.assertEqual(len(valid),1)
        self.assertTrue(self.server.redeem_bootstrap(main))
        self.assertTrue(self.server.visual_authorized(valid[0]))
        self.server.revoke_visual()
        self.assertFalse(self.server.visual_authorized(valid[0]))
        self.assertIsNone(self.server.redeem_visual(visual))

    def test_visual_expiry_and_api_requires_both_session_and_window_lease(self):
        from unittest.mock import Mock
        self.server.runtime.visual_state=Mock(return_value={'synthetic':True})
        with patch('iris.desktop.server.time.monotonic',return_value=10):
            token=self.server.visual_bootstrap_url().split('#pair=')[1]
            lease=self.server.redeem_visual(token)
            for cookie,key,expected in [('',lease,403),('iris_visual='+self.server._visual_cookie,'public-visual-id',403),('iris_visual='+self.server._visual_cookie,lease,200)]:
                c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
                try:
                    c.request('GET','/api/visual/state',headers={'Host':f'localhost:{self.server.server_address[1]}','Cookie':cookie,'X-IRIS-Visual':key})
                    response=c.getresponse();self.assertEqual(response.status,expected);response.read()
                finally:c.close()
        with patch('iris.desktop.server.time.monotonic',return_value=911):
            self.assertFalse(self.server.visual_authorized(lease))
        self.server.runtime.visual_state.assert_called_once()

    def test_visual_writes_reject_foreign_origin_and_revoked_lease(self):
        from unittest.mock import Mock
        self.server.runtime.update_visual=Mock(return_value={'revision':2})
        lease=self.server.redeem_visual(self.server.visual_bootstrap_url().split('#pair=')[1])
        origin=f'http://localhost:{self.server.server_address[1]}'
        cookie=self.server._visual_cookie
        for supplied,revoked,expected in [('https://example.invalid',False,403),(origin,False,200),(origin,True,403)]:
            if revoked:self.server.revoke_visual()
            c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
            try:
                c.request('POST','/api/visual/update',json.dumps({'id':'public','revision':1,'changes':{'rate':8}}),
                    {'Host':f'localhost:{self.server.server_address[1]}','Cookie':'iris_visual='+cookie,'X-IRIS-Request':'1','X-IRIS-Visual':lease,'Origin':supplied,'Content-Type':'application/json'})
                response=c.getresponse();self.assertEqual(response.status,expected);response.read()
            finally:c.close()
        self.server.runtime.update_visual.assert_called_once()

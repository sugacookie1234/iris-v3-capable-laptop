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

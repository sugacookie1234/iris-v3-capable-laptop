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

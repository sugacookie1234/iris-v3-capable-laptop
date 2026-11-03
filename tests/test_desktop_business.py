import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from iris.desktop.runtime import DesktopRuntime
from iris.desktop.server import DesktopServer
from iris.generalist.business import BusinessWorkspace
from tests.test_business import scenario
from tests.test_desktop import FakeBrain


class DesktopBusinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = DesktopRuntime(settings={'IRIS_PROVIDER_URL':'http://127.0.0.1:9',
            'IRIS_MODEL':'synthetic','IRIS_AUTO_ORGANIZE_ENABLED':'false'},
            data_dir=Path(temporary.name), brain=FakeBrain())
        self.addCleanup(self.app.close)
        self.server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.headers = {'Cookie': 'iris_session='+self.server.session,
            'X-IRIS-Request':'1', 'Content-Type':'application/json'}

    def request(self, method, path, value=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, json.dumps(value) if value else None,
                self.headers if headers is None else headers)
            result = connection.getresponse()
            return result.status, json.loads(result.read())
        finally:
            connection.close()

    def test_origin_session_and_write_guards_apply_before_local_writes(self):
        value = {'project':scenario(), 'request_id':'synthetic-001'}
        self.assertEqual(self.request('GET','/api/business',headers={})[0],403)
        for headers in ({}, {'Cookie': self.headers['Cookie']}, {**self.headers,'Origin':'https://example.com'}):
            self.assertEqual(self.request('POST','/api/business/save',value,headers)[0],403)
        self.assertEqual(BusinessWorkspace(self.app.memory_path).list(), [])
        self.assertEqual(self.request('POST','/api/business/save',{**value,'purchase':True})[0],400)

    def test_save_reload_local_command_and_private_receipt(self):
        value = {'project':scenario(), 'request_id':'synthetic-001'}
        status, item = self.request('POST','/api/business/save',value)
        self.assertEqual(status,200)
        self.assertEqual(self.request('POST','/api/business/save',value)[1],item)
        self.assertEqual(self.request('GET','/api/business')[1]['items'],[item])
        answer = self.app.chat('Show business')
        self.assertEqual(answer['route'],'LOCAL')
        self.assertEqual(answer['business'],[item])
        self.assertEqual(self.app.brain.calls,[])
        self.assertEqual(self.app.history,[])
        receipts = self.app.action_history.rows()
        self.assertEqual(receipts[0]['tool'],'business_evaluate')
        self.assertEqual(receipts[0]['verification'],'unverified')
        self.assertNotIn('Synthetic research',json.dumps(receipts))

    def test_invalid_amount_returns_error_without_creating_project(self):
        value = {'project':scenario(), 'request_id':'synthetic-001'}
        value['project']['products'][0]['price'] = 'NaN'
        self.assertEqual(self.request('POST','/api/business/save',value)[0],400)
        self.assertEqual(self.request('GET','/api/business')[1]['items'],[])

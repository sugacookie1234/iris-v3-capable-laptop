import socket
import threading
import unittest
from types import SimpleNamespace
from iris.desktop.server import DesktopServer


class DesktopSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = DesktopServer(('127.0.0.1', 0), SimpleNamespace())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, extra='', body=b'{}', cookie=True):
        port=self.server.server_address[1]
        headers=f'POST /api/chat HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nX-IRIS-Request: 1\r\n'
        if cookie:headers+=f'Cookie: iris_session={self.server.session}\r\n'
        with socket.create_connection(self.server.server_address,timeout=2) as connection:
            connection.sendall(headers.encode()+extra.encode()+b'\r\n'+body)
            return connection.recv(4096).split(b'\r\n')[0]

    def test_ambiguous_framing_rejected(self):
        for header in ('Content-Length: 2\r\nContent-Length: 2\r\n',
                       'Content-Length: 2\r\nTransfer-Encoding: chunked\r\n',
                       'Content-Length: -1\r\n', ''):
            self.assertIn(b'400',self.request(header))

    def test_duplicate_json_and_nonfinite_numbers_rejected(self):
        for body in (b'{"text":"a","text":"b"}',b'{"text":NaN}'):
            self.assertIn(b'400',self.request(f'Content-Length: {len(body)}\r\n',body))

    def test_rejected_auth_does_not_wait_for_body(self):
        self.assertIn(b'403',self.request('Content-Length: 50000\r\n',b'',False))

    def test_duplicate_host_and_origin_rejected(self):
        for extra in ('Host: evil.example\r\n','Origin: http://evil.example\r\nOrigin: null\r\n'):
            self.assertIn(b'403',self.request('Content-Length: 2\r\n'+extra))

    def test_public_bind_rejected(self):
        with self.assertRaises(ValueError):DesktopServer(('0.0.0.0',0),SimpleNamespace())

    def test_worker_capacity_is_bounded(self):
        for _ in range(32):self.assertTrue(self.server._connections.acquire(False))
        self.assertFalse(self.server._connections.acquire(False))
        for _ in range(32):self.server._connections.release()

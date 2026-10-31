"""Exercise real HTTP request handling without requiring a listening network socket."""
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from inspection_app.server import create_server
from inspection_app.store import Store

class HttpInProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'plan.db')
        self.server = type('FakeServer', (), {'server_port': 8642})()
        def construct(address, handler):
            self.handler = handler
            return self.server
        with patch('inspection_app.server.ThreadingHTTPServer', construct): create_server(self.store)

    def tearDown(self): self.tmp.cleanup()

    def request(self, method, path, body=b'', headers=None):
        client, endpoint = socket.socketpair()
        def serve():
            try: self.handler(endpoint, ('127.0.0.1', 1), self.server)
            finally: endpoint.close()
        thread = threading.Thread(target=serve)
        thread.start()
        headers = {'Host': '127.0.0.1:8642', 'Connection':'close', 'Content-Length':str(len(body)), **(headers or {})}
        request = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k,v in headers.items()) + '\r\n'
        client.sendall(request.encode()+body)
        chunks=[]
        while True:
            chunk=client.recv(65536)
            if not chunk: break
            chunks.append(chunk)
        client.close(); thread.join(); endpoint.close()
        head, data = b''.join(chunks).split(b'\r\n\r\n', 1)
        return int(head.split()[1]), data

    def test_foreign_origin_cannot_read_or_mutate(self):
        self.assertEqual(self.request('GET','/api/assets',headers={'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('POST','/api/assets',body=b'{}',headers={'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('GET','/api/assets')[0],200)

    def test_save_and_export(self):
        import re
        status, page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        payload=json.dumps({'name':'Test asset','family':'Flowline'}).encode()
        status, data=self.request('POST','/api/assets',payload,{'X-App-Token':token,'Content-Type':'application/json'})
        self.assertEqual(status,201)
        self.assertEqual(json.loads(data)['name'],'Test asset')
        status, data=self.request('GET','/api/export')
        self.assertEqual(status,200)
        self.assertTrue(data.startswith(b'PK'))

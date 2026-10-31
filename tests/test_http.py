import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from inspection_app.server import create_server
from inspection_app.store import Store

class ServerTests(unittest.TestCase):
    def test_local_service_rejects_foreign_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                server = create_server(Store(Path(tmp) / 'db.sqlite'))
            except PermissionError as exc:
                self.skipTest('Environment does not permit a listening socket: ' + str(exc))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = 'http://127.0.0.1:%s/api/assets' % server.server_port
            try:
                with urlopen(url) as response:
                    self.assertEqual(json.load(response), [])
                request = Request(url, data=b'{}', headers={'Origin':'https://evil.example','Content-Type':'application/json'}, method='POST')
                with self.assertRaises(HTTPError) as failure: urlopen(request)
                self.assertEqual(failure.exception.code, 403)
            finally:
                server.shutdown(); server.server_close(); thread.join()

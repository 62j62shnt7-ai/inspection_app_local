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

    def test_yearly_excel_preserves_filtered_rows_and_literal_asset_names(self):
        import io, re, openpyxl
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        body = json.dumps({'rows': [['2027-03', '=Asset', 'OSI', 'GP Piping']]}).encode()
        status, data = self.request('POST', '/api/yearly-export', body, {'X-App-Token': token, 'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        book = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
        sheet = book.active
        self.assertEqual([cell.value for cell in sheet[2]], ['2027-03', '=Asset', 'OSI', 'GP Piping'])
        self.assertEqual(sheet['B2'].data_type, 's')

    def test_clear_requires_confirmation_and_creates_restorable_backup(self):
        import re, sqlite3
        asset = self.store.save_asset(None, {'name': 'Keep safe', 'family': 'Flowline'}, None)
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token': token, 'Content-Type': 'application/json'}
        self.assertEqual(self.request('POST', '/api/clear', b'{}', headers)[0], 400)
        status, data = self.request('POST', '/api/clear', b'{"confirmation":"CLEAR"}', headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.request('GET', '/api/assets')[1]), [])
        with sqlite3.connect(json.loads(data)['backup']) as conn:
            self.assertEqual(conn.execute('SELECT name FROM assets WHERE id=?', (asset['id'],)).fetchone()[0], 'Keep safe')

    def test_list_and_restore_saved_backups_rejects_traversal(self):
        import re
        from inspection_app.backups import create_backup
        asset = self.store.save_asset(None, {'name': 'Original', 'family': 'Flowline'}, None)
        backup = create_backup(self.store)
        self.store.save_asset(asset['id'], {'name': 'Changed'}, asset['version'])
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token': token, 'Content-Type': 'application/json'}
        status, body = self.request('GET', '/api/backups')
        self.assertEqual(status, 200)
        self.assertIn(backup.name, [row['filename'] for row in json.loads(body)])
        self.assertEqual(self.request('POST', '/api/backups/restore', json.dumps({'filename':'../plan.db'}).encode(), headers)[0], 400)
        status, body = self.request('POST', '/api/backups/restore', json.dumps({'filename':backup.name}).encode(), headers)
        self.assertEqual(status, 200)
        self.assertEqual(self.store.get_asset(asset['id'])['name'], 'Original')
        self.assertTrue(Path(json.loads(body)['safety_backup']).exists())

    def test_reconciliation_preview_does_not_modify_master(self):
        import io, re
        from openpyxl import Workbook
        asset = self.store.save_asset(None, {'name':'Vessel', 'family':'Vessel', 'asset_number_original':'V-1'}, None)
        book = Workbook(); sheet = book.active; sheet.title = 'Full Inspection Plan'
        sheet.append(['Plan']); sheet.append(['Category','Package# or Asset#','Item','Planned Insp Date','Next Inspection Category'])
        sheet.append(['Vessel','V-1','Vessel','2026-03','OSI'])
        stream = io.BytesIO(); book.save(stream)
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        status, body = self.request('POST', '/api/reconciliation/preview', stream.getvalue(), {'X-App-Token':token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['rows'][0]['candidates'][0]['id'], asset['id'])
        self.assertEqual(self.store.get_asset(asset['id']), asset)

    def test_reconciliation_apply_requires_token_and_checks_version(self):
        import re
        asset = self.store.save_asset(None, {'name':'Vessel','family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]}, None)
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        payload = json.dumps({'updates':[{'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'next_inspection_month':'2027-03'}}]}).encode()
        self.assertEqual(self.request('POST','/api/reconciliation/apply',payload)[0],403)
        headers = {'X-App-Token':token,'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/reconciliation/apply',payload,headers)[0],200)
        self.assertEqual(self.store.get_asset(asset['id'])['inspections'][0]['next_inspection_month'],'2027-03')
        self.assertEqual(self.request('POST','/api/reconciliation/apply',payload,headers)[0],400)

    def test_reconciliation_script_is_served_as_javascript(self):
        status, data = self.request('GET', '/reconciliation.js')
        self.assertEqual(status, 200)
        self.assertIn(b'recon-import', data)

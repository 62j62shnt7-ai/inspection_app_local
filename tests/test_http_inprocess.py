from contextlib import closing
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
    def test_main_browser_script_includes_import_review_without_extra_route(self):
        status, page = self.request('GET', '/')
        self.assertEqual(status, 200)
        import re
        scripts = re.findall(rb'<script[^>]+src="([^"]+)"', page)
        self.assertNotIn(b'/import-review.js', scripts)
        status, script = self.request('GET', '/app.js')
        self.assertEqual(status, 200)
        self.assertIn(b'function renderImportPreview(', script)
        self.assertIn(b'function resolveImportPreview(', script)

    def test_original_duplicate_choices_update_preview_before_applying(self):
        import re
        from test_legacy_import import flowlines
        path = Path(self.tmp.name) / 'duplicates.xlsx'
        flowlines(path, records=[['AG-1', 'Yes', 'Oil'], ['AG-1', 'Yes', 'Oil']])
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token': token, 'Content-Type': 'application/json'}
        status, body = self.request('POST', '/api/import/preview', path.read_bytes(), headers)
        self.assertEqual(status, 200)
        preview = json.loads(body)
        choices = [{'row_key': row['row_key'], 'action': 'separate'} for row in preview['conflicts']]
        status, body = self.request('POST', '/api/import/resolve', json.dumps({'token': preview['token'], 'resolutions': choices}).encode(), headers)
        self.assertEqual(status, 200)
        reviewed = json.loads(body)
        self.assertFalse(reviewed['errors'])
        self.assertEqual(json.loads(self.request('GET', '/api/assets')[1]), [])
        self.assertEqual(self.request('POST', '/api/import/apply', json.dumps({'token': preview['token']}).encode(), headers)[0], 400)
        self.assertEqual(self.request('POST', '/api/import/apply', json.dumps({'token': reviewed['token']}).encode(), headers)[0], 200)
        self.assertEqual(len(json.loads(self.request('GET', '/api/assets')[1])), 2)

    def test_original_import_discovers_tabs_and_previews_only_selection(self):
        import re
        from test_legacy_import import flowlines
        path = Path(self.tmp.name) / 'original.xlsx'
        flowlines(path)
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token': token, 'Content-Type': 'application/octet-stream'}
        status, body = self.request('POST', '/api/import/inspect', path.read_bytes(), headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['format'], 'legacy')
        headers['X-Import-Sheets'] = json.dumps(['FLs'])
        status, body = self.request('POST', '/api/import/preview', path.read_bytes(), headers)
        self.assertEqual(status, 200)
        preview = json.loads(body)
        self.assertEqual(preview['included_sheets'], ['FLs'])
        self.assertEqual(preview['excluded_sheets'], ['Coolers'])
        self.assertEqual(preview['counts']['Assets'], 1)
        status, _ = self.request('POST', '/api/import/apply', json.dumps({'token': preview['token'], 'mode': 'replace'}).encode(), {'X-App-Token': token})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(self.request('GET', '/api/assets')[1]), [])
        headers['X-Import-Sheets'] = 'invalid-json'
        self.assertEqual(self.request('POST', '/api/import/preview', path.read_bytes(), headers)[0], 400)

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
        with closing(sqlite3.connect(json.loads(data)['backup'])) as conn, conn:
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

    def test_selective_backup_deletion_requires_auth_and_removes_only_requested_file(self):
        import re
        from inspection_app.backups import create_backup
        selected=create_backup(self.store);retained=create_backup(self.store)
        payload=json.dumps({'filenames':[selected.name]}).encode()
        self.assertEqual(self.request('POST','/api/backups/delete',payload,{'Content-Type':'application/json'})[0],403)
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token,'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/backups/delete',json.dumps({'filenames':['../plan.db']}).encode(),headers)[0],400)
        status,body=self.request('POST','/api/backups/delete',payload,headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),{'deleted':[selected.name],'failed':[]})
        self.assertFalse(selected.exists());self.assertTrue(retained.is_file())

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

    def test_page_preserves_unicode_with_windows_default_encoding(self):
        original = Path.read_text
        def windows_read_text(path, *args, **kwargs):
            if not args and kwargs.get('encoding') is None:
                kwargs['encoding'] = 'cp1252'
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', windows_read_text):
            status, data = self.request('GET', '/')
        self.assertEqual(status, 200)
        page = data.decode('utf-8')
        self.assertIn('◫', page)
        self.assertIn('⇄', page)
        self.assertIn('LOCAL WORKSPACE · ASSET INTEGRITY', page)

    def test_quality_verification_snapshot_and_recovery_routes_work_together(self):
        import re
        from inspection_app.quality import verification_fields
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token,'Content-Type':'application/json'}
        asset=self.store.save_asset(None,{'name':'Synthetic vessel','family':'Vessel / tank','record_status':'Active','location_from':'North','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-04'},{'inspection_type':'Internal','applicable':'No'}]},None)
        self.assertEqual(self.request('GET','/quality.js')[0],200)
        status,body=self.request('POST','/api/quality/query',json.dumps({'page':1,'size':50}).encode(),headers)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['readiness']['excluded_count'],0)
        payload={'asset_id':asset['id'],'version':asset['version'],'fields':list(verification_fields(asset)),'evidence':'Synthetic acceptance fixture checked'}
        status,body=self.request('POST','/api/verification',json.dumps(payload).encode(),headers)
        self.assertEqual(status,200)
        readiness=json.loads(self.request('GET','/api/readiness')[1])
        self.assertEqual(readiness['eligible'],[asset['id']])
        status,body=self.request('POST','/api/snapshots',json.dumps({'name':'Synthetic acceptance','revision':readiness['revision']}).encode(),headers)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['assets'][0]['id'],asset['id'])
        status,package=self.request('GET','/api/recovery/export')
        self.assertEqual(status,200);self.assertTrue(package.startswith(b'PK'))

    def test_bulk_verification_preview_and_apply_require_authenticated_evidence(self):
        import re
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token,'Content-Type':'application/json'}
        asset=self.store.save_asset(None,{'name':'Batch checked line','family':'Flowline','location_from':'North'},None)
        status,body=self.request('POST','/api/verification/bulk/preview',json.dumps({'asset_ids':[asset['id']]}).encode(),headers)
        self.assertEqual(status,200)
        preview=json.loads(body)
        self.assertEqual(preview['asset_count'],1)
        self.assertEqual(preview['assets'][0]['id'],asset['id'])
        payload={'preview_id':preview['preview_id'],'revision':preview['revision'],'evidence':'Plan workbook · FLs row 12'}
        status,body=self.request('POST','/api/verification/bulk/apply',json.dumps({**payload,'evidence':' '}).encode(),headers)
        self.assertEqual(status,400)
        status,body=self.request('POST','/api/verification/bulk/apply',json.dumps(payload).encode(),headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['verified_asset_count'],1)
        self.assertEqual(self.request('POST','/api/verification/bulk/preview',json.dumps({'asset_ids':[asset['id']]}).encode(),{'Content-Type':'application/json'})[0],403)

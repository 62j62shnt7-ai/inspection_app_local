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
    def test_cleanup_reset_rejects_old_browser_and_old_preview(self):
        import re
        self.store.save_asset(None, {'name':'Reset sample','family':'Flowline'}, None)
        _,page = self.request('GET','/')
        token = re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers = {'X-App-Token':token,'X-Data-Epoch':'initial','Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/data/preview',b'{"category":"reset"}')[0],403)
        status,body = self.request('POST','/api/data/preview',b'{"category":"reset"}',headers)
        self.assertEqual(status,200,body)
        preview = json.loads(body)
        status,body = self.request('POST','/api/data/delete',json.dumps({'preview_id':preview['preview_id'],'confirmation':preview['confirmation']}).encode(),headers)
        self.assertEqual(status,200,body)
        result = json.loads(body)
        self.assertTrue(result['reload_required'])
        status,body = self.request('POST','/api/assets',b'{"name":"Old browser","family":"Flowline"}',headers)
        self.assertEqual(status,400);self.assertIn('Reload',json.loads(body)['error'])
        headers['X-Data-Epoch'] = result['data_epoch']
        status,body = self.request('POST','/api/assets',b'{"name":"Fresh browser","family":"Flowline"}',headers)
        self.assertEqual(status,201,body)
        self.assertEqual(self.request('POST','/api/data/delete',json.dumps({'preview_id':preview['preview_id'],'confirmation':preview['confirmation']}).encode(),headers)[0],400)
        # Restoring data must not reactivate pre-reset pages.
        with open(result['recovery'],'rb') as stream:
            self.assertEqual(self.request('POST','/api/recovery/restore',stream.read(),headers)[0],200)
        headers['X-Data-Epoch'] = 'initial'
        status,body = self.request('POST','/api/assets',b'{"name":"Stale after restore","family":"Flowline"}',headers)
        self.assertEqual(status,400,body)

    def test_yearly_export_after_reset_requires_current_epoch(self):
        import io, re, openpyxl
        self.store.save_asset(None, {'name':'Synthetic','family':'Flowline'}, None)
        _, page = self.request('GET','/')
        token = re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token,'X-Data-Epoch':'initial','Content-Type':'application/json'}
        status, body = self.request('POST','/api/data/preview',b'{"category":"reset"}',headers)
        self.assertEqual(status,200,body); preview=json.loads(body)
        payload=json.dumps({'preview_id':preview['preview_id'],'confirmation':preview['confirmation']}).encode()
        status, body = self.request('POST','/api/data/delete',payload,headers)
        self.assertEqual(status,200,body); epoch=json.loads(body)['data_epoch']
        data=json.dumps({'rows':[['2027-03','Synthetic','OSI','Manual']]}).encode()
        self.assertEqual(self.request('POST','/api/yearly-export',data,headers)[0],400)
        headers['X-Data-Epoch']=epoch
        status, data=self.request('POST','/api/yearly-export',data,headers)
        self.assertEqual(status,200)
        book=openpyxl.load_workbook(io.BytesIO(data),data_only=False)
        self.assertEqual([cell.value for cell in book.active[2]],['2027-03','Synthetic','OSI','Manual'])
        book.close()

    def test_save_and_clear_with_windows_flush_requirement(self):
        import re
        from windows_io import windows_flush_requirement
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token':token, 'Content-Type':'application/json'}
        with windows_flush_requirement():
            status, body = self.request('POST', '/api/assets', json.dumps({'name':'Windows save', 'family':'Flowline'}).encode(), headers)
            self.assertEqual(status, 201, body)
            asset = json.loads(body)
            status, body = self.request('PUT', '/api/assets/'+asset['id'], json.dumps({'asset':{'name':'Windows edit'},'version':asset['version']}).encode(), headers)
            self.assertEqual(status, 200, body)
            status, body = self.request('POST', '/api/clear', b'{"confirmation":"CLEAR"}', headers)
            self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(self.request('GET', '/api/assets')[1]), [])
        from inspection_app.backups import restore_backup
        restore_backup(self.store, json.loads(body)['backup'])
        self.assertEqual(self.store.get_asset(asset['id'])['name'], 'Windows edit')

    def test_database_reads_wait_for_mutation_lock(self):
        entered = threading.Event()
        original = __import__('inspection_app.server', fromlist=['read_summaries']).read_summaries
        def read(conn):
            entered.set()
            return original(conn)
        with patch('inspection_app.server.read_summaries', side_effect=read):
            with self.store._lock:
                result = []
                thread = threading.Thread(target=lambda: result.append(self.request('GET', '/api/assets?summary=1')))
                thread.start()
                overlapped = entered.wait(0.2)
            thread.join(5)
        self.assertFalse(overlapped, 'Database read overlapped the mutation lock')
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0][0], 200)

    def test_disconnected_response_does_not_raise_or_send_twice(self):
        from unittest.mock import Mock
        for error in (ConnectionAbortedError(10053, 'aborted'), BrokenPipeError(), ConnectionResetError()):
            handler = object.__new__(self.handler)
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = Mock()
            handler.wfile.write.side_effect = error
            with self.subTest(error=type(error).__name__):
                handler.respond(200, {'saved': True})
                self.assertTrue(handler.close_connection)
                handler.send_response.assert_called_once_with(200)

    def test_response_is_sent_after_database_lock_is_released(self):
        from unittest.mock import Mock
        handler = object.__new__(self.handler)
        lock_available = threading.Event()
        def send(status, payload, content_type):
            def acquire():
                with self.store._lock:
                    lock_available.set()
            thread = threading.Thread(target=acquire)
            thread.start()
            self.assertTrue(lock_available.wait(1), 'Response still holds the database lock')
            thread.join(2)
        handler.respond = Mock(wraps=handler.respond)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        handler.wfile.write.side_effect = lambda body: send(200, body, '')
        handler.run_locked(lambda: handler.respond(200, {'ok': True}))
        self.assertTrue(lock_available.is_set())

    def test_busy_database_returns_retryable_error(self):
        import sqlite3
        with patch('inspection_app.server.read_summaries', side_effect=sqlite3.OperationalError('database is locked')):
            status, body = self.request('GET', '/api/assets?summary=1')
        self.assertEqual(status, 503)
        self.assertIn('Database is busy', json.loads(body)['error'])

    def test_review_preview_resolves_without_saving_and_requires_token(self):
        import re
        from test_review_resolution import ReviewResolutionTests
        asset=ReviewResolutionTests().asset()
        asset['inspections'][0]['last_inspection_month']='2019-06'
        body=json.dumps(asset).encode()
        self.assertEqual(self.request('POST','/api/assets/review-preview',body)[0],403)
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        status,data=self.request('POST','/api/assets/review-preview',body,{'X-App-Token':token})
        self.assertEqual(status,200)
        preview=json.loads(data)
        self.assertEqual(preview['review_items'][0]['review_status'],'Resolved')
        self.assertEqual(preview['review_items'][1]['review_status'],'Review')
        self.assertEqual(json.loads(self.request('GET','/api/assets')[1]),[])

    def test_year_only_preview_requires_token_and_changes_no_asset(self):
        import re
        asset=self.store.save_asset(None,{'name':'Line','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_original':'2025'}]},None)
        self.assertEqual(self.request('POST','/api/bulk/year-only/preview',b'{}')[0],403)
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        status,data=self.request('POST','/api/bulk/year-only/preview',b'{}',{'X-App-Token':token})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['date_count'],1)
        self.assertEqual(self.store.get_asset(asset['id']),asset)

    def test_month_year_preview_requires_token_and_preserves_asset(self):
        import re
        asset=self.store.save_asset(None,{'name':'Line','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_original':'2-2026'}]},None)
        self.assertEqual(self.request('POST','/api/bulk/month-year/preview',b'{}')[0],403)
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        status,data=self.request('POST','/api/bulk/month-year/preview',b'{}',{'X-App-Token':token})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['changes'][0]['date_changes'][0]['after'],'2026-02')
        self.assertEqual(self.store.get_asset(asset['id']),asset)

    def test_century_review_endpoints_require_token_and_preview_selection(self):
        import re
        self.store.save_asset(None,{'name':'Line','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'1935-08'}]},None)
        self.assertEqual(self.request('POST','/api/bulk/century/candidates',b'{}')[0],403)
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token}
        status,data=self.request('POST','/api/bulk/century/candidates',b'{}',headers)
        self.assertEqual(status,200)
        listing=json.loads(data)
        body=json.dumps({'revision':listing['revision'],'selected_keys':[listing['candidates'][0]['key']]}).encode()
        self.assertEqual(self.request('POST','/api/bulk/century/preview',body)[0],403)
        status,data=self.request('POST','/api/bulk/century/preview',body,headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['changes'][0]['date_changes'][0]['after'],'2035-08')

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
        from inspection_app.backups import restore_backup
        restore_backup(self.store, json.loads(data)['backup'])
        self.assertEqual(self.store.get_asset(asset['id'])['name'], 'Keep safe')

    def test_uploaded_compressed_and_legacy_database_backups_restore(self):
        import re
        from inspection_app.backups import create_backup
        asset = self.store.save_asset(None, {'name':'Upload original', 'family':'Flowline'}, None)
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        for compressed in (False, True):
            backup = create_backup(self.store, compress=compressed)
            current = self.store.get_asset(asset['id'])
            self.store.save_asset(asset['id'], {'name':'Changed'}, current['version'])
            status, body = self.request('POST', '/api/restore', backup.read_bytes(), {'X-App-Token':token})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.store.get_asset(asset['id'])['name'], 'Upload original')
            self.assertTrue(Path(json.loads(body)['safety_backup']).is_file())

    def test_generated_legacy_migration_backup_restores_via_http(self):
        import hashlib, re, shutil, sqlite3
        from inspection_app.backups import list_backups
        from inspection_app.recovery import configure_backup_folder, backup_status
        root = Path(self.tmp.name)
        old = root/'legacy'/'master.db'; old.parent.mkdir()
        with closing(sqlite3.connect(old)) as conn, conn:
            conn.execute('CREATE TABLE assets(id TEXT PRIMARY KEY,name TEXT NOT NULL,family TEXT NOT NULL,version INTEGER NOT NULL)')
            conn.execute("INSERT INTO assets VALUES ('legacy','Original','Flowline',7)")
        legacy = Store(old)
        source = old.parent/'backups'/next(x['filename'] for x in list_backups(legacy) if 'migration' in x['filename'])
        target = root/'backups'/source.name; target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        original_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        folder = root/'independent'; folder.mkdir()
        configure_backup_folder(self.store, str(folder))
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            raw = json.loads(conn.execute('SELECT contents FROM backup_settings WHERE id=1').fetchone()[0])
            raw['data_epoch'] = 'synthetic-epoch'
            conn.execute('UPDATE backup_settings SET contents=? WHERE id=1', (json.dumps(raw),))
        _, page = self.request('GET', '/')
        token = re.search(rb'name="app-token" content="([^"]+)"', page).group(1).decode()
        headers = {'X-App-Token':token, 'X-Data-Epoch':'synthetic-epoch', 'Content-Type':'application/json'}
        status, body = self.request('POST', '/api/backups/restore', json.dumps({'filename':target.name}).encode(), headers)
        self.assertEqual(status, 200, body)
        restored = self.store.get_asset('legacy')
        self.assertEqual(restored['name'], 'Original')
        self.assertGreater(restored['version'], 7)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(backup_status(self.store)['folder'], str(folder.resolve()))
        self.assertEqual(backup_status(self.store)['data_epoch'], 'synthetic-epoch')
        with self.assertRaises(ValueError):
            self.store.save_asset('legacy', {'name':'Stale'}, 7)

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
        payload = json.dumps({'updates':[{'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'next_inspection_month':'2027-03'},'source':{'completion_evidence':[{'column':'ut progress','value':'Done'}]}}]}).encode()
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

    def test_completed_ut_excel_reconciliation_updates_done_and_preserves_pending(self):
        import io, re
        from openpyxl import Workbook
        from inspection_app.backups import restore_backup
        before={}
        for tag in ('UT-DONE','UT-PENDING'):
            before[tag]=self.store.save_asset(None,{'name':tag,'family':'Vessel','tag_original':tag,'location_from':'Sample location','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2020-01','next_inspection_month':'2026-01'}]},None)
        book=Workbook();sheet=book.active;sheet.title='UT Results'
        sheet.append(['Tag','Inspection type','Actual inspection date','Next due date','UT Progress'])
        sheet.append(['UT-DONE','OSI','2026-09-14','2028-09','Done'])
        sheet.append(['UT-PENDING','OSI','2026-10-05','2028-10','Pending'])
        stream=io.BytesIO();book.save(stream);book.close()
        _,page=self.request('GET','/')
        token=re.search(rb'name="app-token" content="([^"]+)"',page).group(1).decode()
        headers={'X-App-Token':token,'Content-Type':'application/json'}
        status,body=self.request('POST','/api/reconciliation/preview',stream.getvalue(),{**headers,'Content-Type':'application/octet-stream'})
        self.assertEqual(status,200,body)
        rows=json.loads(body)['rows']
        self.assertEqual([row['completion_status'] for row in rows],['done','not_done'])
        updates=[]
        for row in rows:
            asset=before[row['identifier']]
            self.assertEqual(row['candidates'][0]['id'],asset['id'])
            self.assertEqual(self.store.get_asset(asset['id']),asset,'Preview must be read-only')
            updates.append({'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':row['last_month'],'next_inspection_month':row['next_month']},'source':{'workbook':'ut-results.xlsx','sheet':'UT Results','row':row['row'],'last_original':row['last_original'],'completion_evidence':row['completion_evidence']}})
        # Even if a client submits Pending dates, the entire request is rejected.
        status,body=self.request('POST','/api/reconciliation/apply',json.dumps({'updates':updates}).encode(),headers)
        self.assertEqual(status,400,body)
        self.assertIn('marked done',json.loads(body)['error'])
        for asset in before.values():self.assertEqual(self.store.get_asset(asset['id']),asset)
        # Apply the completed row, as selected by the browser batch preparation.
        status,body=self.request('POST','/api/reconciliation/apply',json.dumps({'updates':updates[:1]}).encode(),headers)
        self.assertEqual(status,200,body);applied=json.loads(body)
        self.assertEqual(applied['updated'],1)
        changed=self.store.get_asset(before['UT-DONE']['id'])
        self.assertEqual(changed['inspections'][0]['last_inspection_month'],'2026-09')
        self.assertEqual(changed['inspections'][0]['next_inspection_month'],'2028-09')
        for field in ('id','name','tag_original','location_from'):self.assertEqual(changed[field],before['UT-DONE'][field])
        self.assertEqual(self.store.get_asset(before['UT-PENDING']['id']),before['UT-PENDING'])
        restored=Store(Path(self.tmp.name)/'restored.db')
        restore_backup(restored,applied['backup'])
        for asset in before.values():
            self.assertEqual(restored.get_asset(asset['id'])['inspections'],asset['inspections'])
        # Re-preview sees the same records and a repeated identical update is a no-op.
        updates[0]['version']=changed['version']
        status,body=self.request('POST','/api/reconciliation/apply',json.dumps({'updates':updates[:1]}).encode(),headers)
        self.assertEqual(status,200,body);self.assertEqual(json.loads(body)['updated'],0)
        self.assertEqual(self.store.get_asset(changed['id']),changed)

import json
import io
import secrets
import sqlite3
import tempfile
from contextlib import closing
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .imports import preview_import, apply_import
from .backups import create_backup, restore_backup, list_backups, restore_saved_backup
from .exports import export_workbook
from .reconciliation import reconcile_workbook, apply_reconciliation

STATIC = Path(__file__).resolve().parent.parent / 'static'

def create_server(store, port=0):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload, content_type='application/json'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, default=str).encode()
            self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(body)
        def permitted(self, mutation=False):
            host = self.headers.get('Host','')
            expected = '127.0.0.1:' + str(self.server.server_port)
            if host != expected: return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected: return False
            return not mutation or self.headers.get('X-App-Token') == token
        def do_GET(self):
            if not self.permitted(): return self.respond(403, {'error':'Forbidden'})
            parsed = urlparse(self.path); path = parsed.path; params = parse_qs(parsed.query)
            try:
                if path in ('/', '/index.html'):
                    html = (STATIC / 'index.html').read_text().replace('__APP_TOKEN__',token)
                    return self.respond(200,html.encode(),'text/html; charset=utf-8')
                if path in ('/app.js','/style.css','/reconciliation.js'):
                    return self.respond(200,(STATIC/path[1:]).read_bytes(),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
                if path == '/api/export':
                    with tempfile.TemporaryDirectory() as directory:
                        output = Path(directory) / 'inspection-plan.xlsx'
                        export_workbook(store, output)
                        return self.respond(200, output.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                if path == '/api/backups': return self.respond(200, list_backups(store))
                if path == '/api/assets':
                    with closing(sqlite3.connect(store.db_path)) as conn:
                        rows = conn.execute('SELECT id FROM assets ORDER BY name COLLATE NOCASE').fetchall()
                    return self.respond(200,[store.get_asset(r[0]) for r in rows])
                if path.startswith('/api/assets/'):
                    return self.respond(200,store.get_asset(path.removeprefix('/api/assets/')))
                if path == '/api/dashboard':
                    current = params.get('current',[date.today().strftime('%Y-%m')])[0]
                    start = params.get('start',[current])[0]; end = params.get('end',[current])[0]
                    return self.respond(200,store.dashboard(current,start,end))
                return self.respond(404,{'error':'Not found'})
            except KeyError: return self.respond(404,{'error':'Asset not found'})
            except ValueError as exc: return self.respond(400,{'error':str(exc)})
        def do_POST(self): self.mutate()
        def do_PUT(self): self.mutate()
        def mutate(self):
            if not self.permitted(True): return self.respond(403,{'error':'Forbidden'})
            try:
                length = int(self.headers.get('Content-Length','0'))
                if length < 1 or length > 20*1024*1024: return self.respond(400,{'error':'Invalid request size'})
                body = self.rfile.read(length); path = urlparse(self.path).path
                if path == '/api/restore':
                    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp:
                        temp.write(body); temp_path = Path(temp.name)
                    try: result = restore_backup(store, temp_path)
                    finally: temp_path.unlink(missing_ok=True)
                    return self.respond(200, result)
                if path == '/api/reconciliation/preview':
                    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp:
                        temp.write(body); temp_path = Path(temp.name)
                    try: result = reconcile_workbook(store, temp_path)
                    finally: temp_path.unlink(missing_ok=True)
                    return self.respond(200, result)
                if path == '/api/import/preview':
                    with tempfile.NamedTemporaryFile(suffix='.xlsx',delete=False) as temp:
                        temp.write(body); temp_path = Path(temp.name)
                    try: result = preview_import(store,temp_path)
                    finally: temp_path.unlink(missing_ok=True)
                    return self.respond(200,result)
                data = json.loads(body)
                if path == '/api/yearly-export' and self.command == 'POST':
                    from openpyxl import Workbook
                    from openpyxl.cell import WriteOnlyCell
                    rows = data.get('rows')
                    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != 4 or any(not isinstance(value, str) for value in row) for row in rows):
                        raise ValueError('Invalid yearly plan rows')
                    book = Workbook(write_only=True)
                    sheet = book.create_sheet('Yearly plan')
                    sheet.append(['Month', 'Asset', 'Inspection', 'Source sheet'])
                    for row in rows:
                        cells = []
                        for value in row:
                            cell = WriteOnlyCell(sheet, value=value)
                            cell.data_type = 's'
                            cells.append(cell)
                        sheet.append(cells)
                    output = io.BytesIO()
                    book.save(output)
                    return self.respond(200, output.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                if path == '/api/clear':
                    if data.get('confirmation') != 'CLEAR': raise ValueError('Type CLEAR to confirm')
                    backup = create_backup(store)
                    with closing(sqlite3.connect(store.db_path)) as conn, conn:
                        conn.execute('DELETE FROM assets')
                        conn.execute('DROP TABLE IF EXISTS import_reference')
                    if hasattr(store, '_previews'): store._previews.clear()
                    return self.respond(200, {'backup': str(backup)})
                if path == '/api/backups/restore': return self.respond(200, restore_saved_backup(store, data.get('filename')))
                if path == '/api/reconciliation/apply': return self.respond(200, apply_reconciliation(store, data.get('updates')))
                if path == '/api/backup': return self.respond(200,{'path':str(create_backup(store))})
                if path == '/api/import/apply': return self.respond(200,apply_import(store,data['token'],data.get('mode','merge')))
                if path == '/api/assets' and self.command == 'POST': return self.respond(201,store.save_asset(None,data,None))
                if path.startswith('/api/assets/') and self.command == 'PUT':
                    return self.respond(200,store.save_asset(path.removeprefix('/api/assets/'),data['asset'],data['version']))
                return self.respond(404,{'error':'Not found'})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc: return self.respond(400,{'error':str(exc)})
            except Exception: return self.respond(400,{'error':'Unable to process request; no changes were saved.'})
        def log_message(self, format, *args): pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

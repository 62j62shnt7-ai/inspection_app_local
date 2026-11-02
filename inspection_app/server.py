from .quality import list_snapshots,get_snapshot
from .import_batches import list_staged_batches, list_import_history
from .imports import resume_import
from .quality import query_quality
from .register import query_register, read_summaries
from .consolidation import preview_consolidation, apply_consolidation
from .quality import preview_bulk_correction, apply_bulk_correction, revert_bulk_correction, preview_bulk_verification, apply_bulk_verification
from .recovery import export_master_package, restore_master_package, automatic_backup, configure_backup_folder, backup_status
from .quality import scan_quality, assess_readiness, verify_fields, asset_verification, resolve_issue, publish_snapshot
from .import_batches import invalidate_batches
from .mutations import clear_master
from .cleanup import inventory, preview_cleanup, apply_cleanup, set_coverage_dismissed, data_epoch
import json
import io
import secrets
import sqlite3
import tempfile
from contextlib import closing
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from .imports import preview_import, apply_import, resolve_import
from .legacy import inspect_workbook
from .backups import create_backup, restore_backup, list_backups, restore_saved_backup, delete_saved_backups
from .exports import export_workbook
from .reconciliation import reconcile_workbook, apply_reconciliation

STATIC = Path(__file__).resolve().parent.parent / 'static'

def create_server(store, port=0):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload, content_type='application/json'):
            if getattr(self, '_defer_response', False):
                self._pending_response = (status, payload, content_type)
                return
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, default=str).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionError, TimeoutError):
                # The operation may already be committed. Never retry the response
                # or report a disconnected client as a failed database mutation.
                self.close_connection = True

        def run_locked(self, operation):
            # Serialize reads with writes/restores, but release the database lock
            # before sending bytes to a potentially slow or disconnected browser.
            self._pending_response = None
            self._defer_response = True
            try:
                with store._lock:
                    operation()
            finally:
                self._defer_response = False
            if self._pending_response is not None:
                self.respond(*self._pending_response)
        def permitted(self, mutation=False):
            host = self.headers.get('Host','')
            expected = '127.0.0.1:' + str(self.server.server_port)
            if host != expected: return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected: return False
            return not mutation or self.headers.get('X-App-Token') == token
        def do_GET(self):
            return self.run_locked(self._get)

        def _get(self):
            if not self.permitted(): return self.respond(403, {'error':'Forbidden'})
            parsed = urlparse(self.path); path = parsed.path; params = parse_qs(parsed.query)
            try:
                if path in ('/', '/index.html'):
                    html = (STATIC / 'index.html').read_text(encoding='utf-8').replace('__APP_TOKEN__',token).replace('__DATA_EPOCH__',data_epoch(store))
                    return self.respond(200,html.encode(),'text/html; charset=utf-8')
                if path in ('/app.js','/style.css','/reconciliation.js','/quality.js','/cleanup.js'):
                    return self.respond(200,(STATIC/path[1:]).read_bytes(),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
                if path == '/api/export':
                    with tempfile.TemporaryDirectory() as directory:
                        output = Path(directory) / 'inspection-plan.xlsx'
                        export_workbook(store, output)
                        return self.respond(200, output.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                if path == '/api/recovery/export':
                    with tempfile.TemporaryDirectory() as directory:
                        output=export_master_package(store,Path(directory)/'recovery.zip')
                        return self.respond(200,output.read_bytes(),'application/zip')
                if path.startswith('/api/source/'):
                    import re
                    digest=path.removeprefix('/api/source/')
                    if not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('Invalid source reference')
                    source=Path(store.db_path).parent/'source-archives'/(digest+'.xlsx')
                    if not source.is_file():raise ValueError('Source archive is unavailable')
                    return self.respond(200,source.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                if path == '/api/import/staged': return self.respond(200,list_staged_batches(store))
                if path == '/api/import/history': return self.respond(200,list_import_history(store))
                if path == '/api/data/inventory': return self.respond(200,inventory(store))
                if path == '/api/backup-status': return self.respond(200,backup_status(store))
                if path == '/api/snapshots': return self.respond(200,list_snapshots(store))
                if path.startswith('/api/snapshots/'): return self.respond(200,get_snapshot(store,path.removeprefix('/api/snapshots/')))
                if path == '/api/quality': return self.respond(200,scan_quality(store))
                if path == '/api/readiness': return self.respond(200,assess_readiness(store))
                if path.startswith('/api/verification/'):
                    return self.respond(200,asset_verification(store,unquote(path.removeprefix('/api/verification/'))))
                if path == '/api/backups': return self.respond(200, list_backups(store))
                if path == '/api/assets':
                    with closing(sqlite3.connect(store.db_path)) as conn:
                        from .quality import read_assets
                        rows = read_summaries(conn) if params.get('summary')==['1'] else read_assets(conn)
                    return self.respond(200,rows)
                if path.startswith('/api/assets/'):
                    return self.respond(200,store.get_asset(unquote(path.removeprefix('/api/assets/'))))
                if path == '/api/dashboard':
                    current = params.get('current',[date.today().strftime('%Y-%m')])[0]
                    start = params.get('start',[current])[0]; end = params.get('end',[current])[0]
                    return self.respond(200,store.dashboard(current,start,end))
                return self.respond(404,{'error':'Not found'})
            except sqlite3.OperationalError:
                return self.respond(503,{'error':'Database is busy or unavailable. Wait for the current operation to finish, then refresh.'})
            except KeyError: return self.respond(404,{'error':'Asset not found'})
            except ValueError as exc: return self.respond(400,{'error':str(exc)})
        def do_POST(self):
            if urlparse(self.path).path == '/api/backup-folder/browse':
                if not self.permitted(True): return self.respond(403, {'error':'Forbidden'})
                try:
                    from .folder_picker import choose_folder
                    folder = choose_folder()
                    if folder is None: return self.respond(200, {'cancelled':True})
                    return self.respond(200,configure_backup_folder(store,folder))
                except ValueError as exc:
                    return self.respond(400,{'error':str(exc)})
            self.mutate()
        def do_PUT(self): self.mutate()
        def mutate(self):
            return self.run_locked(self._mutate)
        def _mutate(self):
            if not self.permitted(True): return self.respond(403,{'error':'Forbidden'})
            try:
                epoch = data_epoch(store)
                if epoch!='initial' and self.headers.get('X-Data-Epoch')!=epoch:
                    raise ValueError('Working data was reset. Reload this page before making changes.')
                path=urlparse(self.path).path
                length = int(self.headers.get('Content-Length','0'))
                limit=256*1024*1024 if path in ('/api/restore','/api/recovery/restore') else 20*1024*1024
                if length < 1 or length > limit: return self.respond(400,{'error':'Invalid request size'})
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
                if path == '/api/recovery/restore':
                    with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as temp:
                        temp.write(body); temp_path=Path(temp.name)
                    try: result=restore_master_package(store,temp_path)
                    finally: temp_path.unlink(missing_ok=True)
                    return self.respond(200,result)
                if path in ('/api/import/preview', '/api/import/inspect'):
                    with tempfile.NamedTemporaryFile(suffix='.xlsx',delete=False) as temp:
                        temp.write(body); temp_path = Path(temp.name)
                    try:
                        # Invalidate earlier previews even if this upload or its
                        # selection fails validation.
                        invalidate_batches(store)
                        if path.endswith('/inspect'):
                            result = inspect_workbook(temp_path)
                        else:
                            selection = self.headers.get('X-Import-Sheets')
                            selected = json.loads(selection) if selection is not None else None
                            if selection is not None and not isinstance(selected, list):
                                raise ValueError('Invalid tab selection')
                            result = preview_import(store, temp_path, selected_sheets=selected)
                    finally: temp_path.unlink(missing_ok=True)
                    return self.respond(200,result)
                data = json.loads(body)
                if path == '/api/data/preview': return self.respond(200,preview_cleanup(store,data))
                if path == '/api/data/delete': return self.respond(200,apply_cleanup(store,data.get('preview_id'),data.get('confirmation')))
                if path == '/api/data/coverage': return self.respond(200,set_coverage_dismissed(store,data.get('batch_id'),data.get('dismissed')))
                if path == '/api/consolidation/preview': return self.respond(200,preview_consolidation(store,data.get('survivor_id'),data.get('duplicate_id')))
                if path == '/api/consolidation/apply': return self.respond(200,apply_consolidation(store,data.get('preview_id'),data.get('revision'),data.get('choices'),data.get('evidence')))
                if path == '/api/quality/query': return self.respond(200,query_quality(store,data))
                if path == '/api/import/resume': return self.respond(200,resume_import(store,data.get('token')))
                if path == '/api/register/query': return self.respond(200,query_register(store,data))
                if path == '/api/bulk/year-only/preview':
                    from .quality import preview_year_only_dates
                    return self.respond(200,preview_year_only_dates(store))
                if path == '/api/bulk/preview': return self.respond(200,preview_bulk_correction(store,data.get('asset_ids'),data.get('operation')))
                if path == '/api/bulk/apply': return self.respond(200,apply_bulk_correction(store,data.get('preview_id'),data.get('revision'),data.get('reason')))
                if path == '/api/bulk/revert': return self.respond(200,revert_bulk_correction(store,data.get('operation_id'),data.get('reason')))
                if path == '/api/assets/review-preview':
                    from .validation import reconcile_import_reviews, validate_record
                    if not isinstance(data,dict): raise ValueError('Asset must be an object')
                    store._validate_details(data.get('family',''),{k:v for k,v in data.items() if k not in ('id','name','family','version')})
                    reconcile_import_reviews(data)
                    return self.respond(200,{**data,'review_findings':validate_record(data)})
                if path == '/api/backup-folder': return self.respond(200,configure_backup_folder(store,data.get('folder')))
                if path == '/api/backup-test': return self.respond(200,automatic_backup(store,force=True))
                if path == '/api/verification': return self.respond(200,verify_fields(store,data.get('asset_id'),data.get('version'),data.get('fields'),data.get('evidence')))
                if path == '/api/verification/bulk/preview': return self.respond(200,preview_bulk_verification(store,data.get('asset_ids')))
                if path == '/api/verification/bulk/apply': return self.respond(200,apply_bulk_verification(store,data.get('preview_id'),data.get('revision'),data.get('evidence')))
                if path == '/api/quality/resolve': return self.respond(200,resolve_issue(store,data.get('issue_id'),data.get('revision'),data.get('disposition'),data.get('evidence')))
                if path == '/api/snapshots': return self.respond(200,publish_snapshot(store,data.get('revision'),data.get('name')))
                if path == '/api/import/resolve':
                    return self.respond(200, resolve_import(store, data.get('token'), data.get('resolutions')))
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
                    context=data.get('context')
                    if context is not None:
                        if not isinstance(context,dict) or not isinstance(context.get('scope'),str) or not isinstance(context.get('omissions'),list):raise ValueError('Invalid yearly export context')
                        exclusions=book.create_sheet('Scope and omissions')
                        def text_row(values):
                            cells=[]
                            for value in values:
                                value=str(value or '')
                                if len(value)>32767:raise ValueError('Yearly export value exceeds Excel cell size')
                                cell=WriteOnlyCell(exclusions,value=value);cell.data_type='s';cells.append(cell)
                            exclusions.append(cells)
                        text_row(['Export scope',context['scope']])
                        text_row(['Asset ID','Asset','Inspection','Month / condition','Reason'])
                        for item in context['omissions']:
                            if not isinstance(item,dict):raise ValueError('Invalid yearly omission')
                            text_row([item.get(k,'') for k in ('asset_id','name','type','due','reason')])
                    output = io.BytesIO()
                    book.save(output)
                    return self.respond(200, output.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                if path == '/api/clear':
                    if data.get('confirmation') != 'CLEAR': raise ValueError('Type CLEAR to confirm')
                    backup = automatic_backup(store,force=True)['local_path']
                    with closing(sqlite3.connect(store.db_path)) as conn, conn:
                        clear_master(store, conn)
                    if hasattr(store, '_previews'): store._previews.clear()
                    return self.respond(200, {'backup': str(backup)})
                if path == '/api/backups/delete': return self.respond(200, delete_saved_backups(store, data.get('filenames')))
                if path == '/api/backups/restore': return self.respond(200, restore_saved_backup(store, data.get('filename')))
                if path == '/api/reconciliation/apply': return self.respond(200, apply_reconciliation(store, data.get('updates')))
                if path == '/api/backup':
                    status=automatic_backup(store,force=True)
                    return self.respond(200,{'path':status['local_path'],'independent_success':status.get('independent_success',False),'warning':status.get('error')})
                if path == '/api/import/apply': return self.respond(200,apply_import(store,data['token'],data.get('mode','merge'),data.get('acknowledge_coverage',False)))
                if path == '/api/assets' and self.command == 'POST': return self.respond(201,store.save_asset(None,data,None))
                if path.startswith('/api/assets/') and self.command == 'PUT':
                    return self.respond(200,store.save_asset(unquote(path.removeprefix('/api/assets/')),data['asset'],data['version']))
                return self.respond(404,{'error':'Not found'})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc: return self.respond(400,{'error':str(exc)})
            except sqlite3.OperationalError:
                return self.respond(503,{'error':'Database is busy or unavailable. Refresh and check the result before retrying.'})
            except Exception: return self.respond(500,{'error':'Unable to complete the request. Refresh and check the result before retrying.'})
        def log_message(self, format, *args): pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

import io
import json
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from openpyxl import load_workbook
from inspection_app.store import Store
from inspection_app.server import create_server
from inspection_app.imports import preview_import
from inspection_app.excel_io import export_full_workbook
from unittest.mock import patch

class ExcelHttpTests(unittest.TestCase):
    def test_export_preview_apply_and_report_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite');store.save_asset(None,{'name':'A','family':'Vessel','record_status':'Active','inspections':[{'inspection_id':'i','inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2025-01','next_inspection_month':'2027-01'}]},None)
            try:server=create_server(store)
            except PermissionError as exc:self.skipTest(str(exc))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urlopen(base) as r:html=r.read().decode()
                token=re.search('name="app-token" content="([^"]+)"',html)[1]
                def post(route,data):
                    raw=data if isinstance(data,bytes) else json.dumps(data).encode()
                    with urlopen(Request(base+route,data=raw,headers={'X-App-Token':token,'Content-Type':'application/json'})) as r:return r.read()
                entered=threading.Event();release=threading.Event()
                from inspection_app import excel_io
                original=excel_io._flat_source_sheets
                def pause_after_snapshot(*args,**kwargs):
                    entered.set();self.assertTrue(release.wait(5));return original(*args,**kwargs)
                with patch.object(excel_io,'_flat_source_sheets',side_effect=pause_after_snapshot):
                    request=Request(base+'/api/excel/export',data=json.dumps({'mode':'full'}).encode(),headers={'X-App-Token':token,'Content-Type':'application/json'})
                    with urlopen(request) as response:
                        self.assertEqual(response.status,202);job_id=json.loads(response.read())['job_id']
                    self.assertTrue(entered.wait(3),'Export worker did not reach workbook generation')
                    # The workbook phase must not hold the database lock and stall other app requests.
                    with urlopen(base+'/api/backup-status',timeout=2) as response:self.assertEqual(response.status,200)
                    release.set()
                    for _ in range(100):
                        with urlopen(base+'/api/excel/export-progress/'+job_id) as response:job=json.loads(response.read())
                        if job['state'] in ('ready','error'):break
                        time.sleep(.05)
                    self.assertEqual(job['state'],'ready',job)
                    with urlopen(base+'/api/excel/export-download/'+job_id) as response:raw=response.read()
                b=load_workbook(io.BytesIO(raw));self.assertIn('Master Plan',b.sheetnames);self.assertIn('Unassigned',b.sheetnames);b.close()
                p=json.loads(post('/api/excel/preview',raw));self.assertFalse(p['errors'])
                result=json.loads(post('/api/excel/apply',{'token':p['token'],'resolutions':{}}))
                with urlopen(base+'/api/excel/reconciled/'+result['download_id']) as r:self.assertTrue(r.read().startswith(b'PK'))
                report=post('/api/excel/export',{'mode':'annual','options':{'year':2027}})
                with self.assertRaises(HTTPError) as e:post('/api/excel/preview',report)
                self.assertEqual(e.exception.code,400);e.exception.close()
                path=Path(tmp)/'report.xlsx';path.write_bytes(report)
                with self.assertRaises(ValueError):preview_import(store,path)
                full=Path(tmp)/'full.xlsx';export_full_workbook(store,full)
                with self.assertRaises(ValueError):preview_import(store,full)
            finally:server.shutdown();server.server_close();thread.join()

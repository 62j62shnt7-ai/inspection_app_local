"""Reproducible 10,000-asset benchmark. Always uses a disposable database."""
from contextlib import closing
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from inspection_app.store import Store
from inspection_app.register import query_register
from inspection_app.quality import query_quality


def run(count=10000):
    with tempfile.TemporaryDirectory(prefix='inspection-benchmark-') as tmp:
        store=Store(Path(tmp)/'master.db')
        with closing(sqlite3.connect(store.db_path)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            for n in range(count):
                details={'record_status':'Active','location_from':'Plant '+str(n%20),'tag_original':'V-'+str(n),
                    'inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-04'},{'inspection_type':'Internal','applicable':'No'}],
                    'notes':[{'note_id':'note-'+str(n),'note_text':'Synthetic engineering evidence with retained source references. '*5}],
                    'technical_details':[{'field_id':'diameter','field_label':'Diameter','value':'300','unit_explicit':'mm'}],
                    'source_cells':[{'source_sheet':'Synthetic','source_row':n+2,'source_cell':chr(65+c)+str(n+2),'original_value':'Preserved source evidence '*10} for c in range(20)]}
                conn.execute('INSERT INTO assets(id,name,family,version,details) VALUES (?,?,?,?,?)',(str(n),'Vessel '+str(n),'Vessel / tank',n+1,json.dumps(details)))
        timings={}
        for label,operation in [('register_page',lambda:query_register(store,{'page':1,'size':100})),('register_filter',lambda:query_register(store,{'search':'Vessel 101','page':1,'size':100})),('editor',lambda:store.get_asset('101')),('quality_first_scan',lambda:query_quality(store,{'page':1,'size':50})),('quality_warm',lambda:query_quality(store,{'page':1,'size':50}))]:
            start=time.perf_counter();result=operation();timings[label]=round(time.perf_counter()-start,3)
        return {'assets':count,'platform':platform.platform(),'python':platform.python_version(),'seconds':timings,'database_mb':round(Path(store.db_path).stat().st_size/1024/1024,2)}

if __name__=='__main__':print(json.dumps(run(),indent=2))

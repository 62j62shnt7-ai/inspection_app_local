"""Read-only source profiling and recovery comparison using disposable directories."""
from collections import Counter
from contextlib import closing
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from inspection_app.store import Store
from inspection_app.imports import preview_import,apply_import
from inspection_app.quality import scan_quality,assess_readiness,read_assets
from inspection_app.recovery import export_master_package,restore_master_package


def profile(source):
    source=Path(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='inspection-source-check-') as tmp:
        root=Path(tmp);(root/'one').mkdir();(root/'two').mkdir()
        store=Store(root/'one'/'master.db');preview=preview_import(store,source)
        if preview['errors']:return {'source':source.name,'sha256':digest,'preview_errors':preview['errors'],'applied':False}
        if any(s.get('unclassified_rows') for s in preview.get('sheet_summary',[])):
            return {'source':source.name,'sha256':digest,'coverage_needs_owner_review':True,'applied':False}
        apply_import(store,preview['token'])
        quality=scan_quality(store);readiness=assess_readiness(store)
        package=export_master_package(store,root/'recovery.zip')
        restored=Store(root/'two'/'master.db');restore_master_package(restored,package)
        with closing(sqlite3.connect(store.db_path)) as conn:left=read_assets(conn)
        with closing(sqlite3.connect(restored.db_path)) as conn:right=read_assets(conn)
        for asset in left+right:asset.pop('version',None)
        return {'source':source.name,'sha256':digest,'assets':len(left),'inspection_rows':sum(len(a.get('inspections',[])) for a in left),
                'open_issues':quality['issue_count'],'issues_by_rule':dict(Counter(i['rule_id'] for i in quality['issues'] if i['state']=='open')),
                'eligible_without_owner_verification':len(readiness['eligible']),'excluded':len(readiness['excluded']),
                'recovery_assets_equal_ignoring_fresh_edit_tokens':left==right,'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==digest}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=json.dumps(profile(args.source),indent=2)+'\n';print(result,end='')
    if args.output:args.output.write_text(result,encoding='utf-8')

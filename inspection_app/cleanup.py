"""Explicit, previewed removal of working data and separately managed copies."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import time

from .store import serialized
from .mutations import next_revision, _append_event
from .recovery import automatic_backup, export_master_package

WORKING_TABLES = ('assets', 'import_batches', 'master_snapshots', 'bulk_operations',
                  'asset_aliases', 'consolidation_previews', 'source_baselines',
                  'import_batch_assets', 'correction_events', 'field_verifications', 'quality_issues')
HISTORY_TABLES = ('correction_events', 'bulk_operations', 'consolidation_previews', 'quality_issues')
LABELS = {'assets':'Assets', 'references':'Imported reference data', 'staged':'Staged imports',
          'imports':'Stored import evidence', 'sources':'Archived source workbooks',
          'snapshots':'Saved snapshots', 'verification':'Verification evidence',
          'history':'Correction, bulk and issue history', 'recovery_packages':'Recovery ZIP copies'}
_SOURCE = re.compile(r'[a-f0-9]{64}\.xlsx\Z')
_PACKAGE = re.compile(r'inspection-recovery-\d{8}-\d{6}-[a-f0-9]{8}(?:-optimized)?\.zip\Z')


def _settings(conn):
    row = conn.execute('SELECT contents FROM backup_settings WHERE id=1').fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='backup_settings'").fetchone() else None
    return json.loads(row[0]) if row else {}


@serialized
def data_epoch(store):
    with closing(sqlite3.connect(store.db_path)) as conn:
        return _settings(conn).get('data_epoch', 'initial')


def _roots(store):
    root = Path(store.db_path).resolve().parent
    roots = {root/'recovery-copies'}
    with closing(sqlite3.connect(store.db_path)) as conn:
        folder = _settings(conn).get('folder')
    if folder:
        roots.add(Path(folder).expanduser().resolve())
    return sorted(roots, key=str)


def _file_item(path, identifier):
    stat = path.stat()
    return {'id':identifier, 'label':path.name, 'filename':path.name, 'folder':str(path.parent),
            'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns}


@serialized
def inventory(store):
    root = Path(store.db_path).resolve().parent
    items = {key:[] for key in LABELS}
    with closing(sqlite3.connect(store.db_path)) as conn:
        revision = conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        items['assets'] = [{'id':a, 'label':name, 'version':version} for a,name,version in conn.execute('SELECT id,name,version FROM assets ORDER BY name,id')]
        for token,state,digest,raw in conn.execute('SELECT token,state,digest,contents FROM import_batches ORDER BY rowid DESC'):
            batch = json.loads(raw)
            entry = {'id':token, 'label':f'{state} · {digest[:12]} · {len(batch.get("data",{}).get("Assets",[]))} proposed assets',
                     'digest':digest, 'dismissed':bool(batch.get('coverage_dismissed')), 'evidence_deleted':bool(batch.get('evidence_deleted')),
                     'signature':hashlib.sha256(raw.encode()).hexdigest()}
            items['staged' if state=='staged' else 'imports'].append(entry)
        for snapshot_id,raw in conn.execute('SELECT snapshot_id,contents FROM master_snapshots ORDER BY rowid DESC'):
            snap = json.loads(raw)
            items['snapshots'].append({'id':snapshot_id, 'label':snap.get('name') or snapshot_id, 'signature':hashlib.sha256(raw.encode()).hexdigest()})
        for name,table in [('verification','field_verifications')]+[('history',t) for t in HISTORY_TABLES]:
            count = conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
            if count: items[name].append({'id':table,'label':f'{table.replace("_"," ")} · {count} records','count':count})
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='import_reference'").fetchone():
            items['references'] = [{'id':name,'label':name,'signature':hashlib.sha256(raw.encode()).hexdigest()} for name,raw in conn.execute('SELECT name,contents FROM import_reference ORDER BY name')]
    folder = root/'source-archives'
    if folder.is_dir() and not folder.is_symlink():
        items['sources'] = [_file_item(p,p.stem) for p in sorted(folder.glob('*.xlsx')) if _SOURCE.fullmatch(p.name) and p.is_file() and not p.is_symlink()]
    for folder in _roots(store):
        if folder.is_dir() and not folder.is_symlink():
            items['recovery_packages'].extend(_file_item(p,hashlib.sha256(str(p).encode()).hexdigest()) for p in sorted(folder.glob('*.zip')) if _PACKAGE.fullmatch(p.name) and p.is_file() and not p.is_symlink())
    return {'revision':revision,'items':items,'counts':{key:sum(x.get('count',1) for x in rows) for key,rows in items.items()}, 'labels':LABELS}


def _signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def _source_gaps(store):
    from .import_batches import _archive_hash
    folder=Path(store.db_path).resolve().parent/'source-archives'
    unavailable=set()
    with closing(sqlite3.connect(store.db_path)) as conn:
        for digest,raw in conn.execute("SELECT digest,contents FROM import_batches WHERE state IN ('committed','staged')"):
            batch=json.loads(raw)
            if batch.get('evidence_deleted') or batch.get('source_archive_deleted'):continue
            path=folder/(digest+'.xlsx')
            try:
                stat=path.stat()
                if path.is_symlink() or _archive_hash(str(path),stat.st_mtime_ns,stat.st_size)!=digest:unavailable.add(digest)
            except OSError:unavailable.add(digest)
    if folder.is_dir() and not folder.is_symlink():
        for path in folder.glob('*.xlsx'):
            if not _SOURCE.fullmatch(path.name):continue
            try:
                stat=path.stat()
                if path.is_symlink() or _archive_hash(str(path),stat.st_mtime_ns,stat.st_size)!=path.stem:unavailable.add(path.stem)
            except OSError:unavailable.add(path.stem)
    return sorted(unavailable)


def _build_plan(store, request, state):
    if not isinstance(request,dict) or request.get('category') not in {*LABELS,'reset'}:
        raise ValueError('Choose a supported data category')
    category = request['category']
    known = {row['id']:row for row in state['items'].get(category,[])}
    ids = request.get('ids',list(known))
    if not isinstance(ids,list) or len(ids)>10000 or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):
        raise ValueError('Invalid deletion selection')
    if category!='reset' and (not ids or any(x not in known for x in ids)):
        raise ValueError('Select existing records from this category')
    selected = [known[x] for x in ids] if category!='reset' else []
    files = state['items']['sources'][:] if category=='reset' else selected[:] if category in ('sources','recovery_packages') else []
    if category in ('imports','staged'):
        with closing(sqlite3.connect(store.db_path)) as conn:
            selected_set = set(ids)
            retained = {digest for token,digest in conn.execute('SELECT token,digest FROM import_batches') if token not in selected_set}
        digests = {row['digest'] for row in selected}
        files = [row for row in state['items']['sources'] if row['id'] in digests-retained]
    dependent = set()
    if category in ('imports','sources','reset'):
        digests = {row['id'] for row in files}
        with closing(sqlite3.connect(store.db_path)) as conn:
            for token,digest,asset_id in conn.execute('SELECT b.token,b.digest,a.id FROM import_batches b JOIN import_batch_assets l ON l.token=b.token LEFT JOIN asset_aliases aa ON aa.retired_id=l.asset_id JOIN assets a ON a.id=COALESCE(aa.survivor_id,l.asset_id)'):
                if category=='reset' or token in ids or digest in digests: dependent.add(asset_id)
    counts = state['counts'].copy() if category=='reset' else {category:sum(row.get('count',1) for row in selected)}
    if category=='reset':
        counts.pop('recovery_packages')
        with closing(sqlite3.connect(store.db_path)) as conn:
            for label,table in [('identity aliases','asset_aliases'),('source baselines','source_baselines'),('import links','import_batch_assets')]:
                counts[label]=conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
    return {'category':category,'ids':ids,'selected':selected,'files':files,'counts':counts,'dependent_assets':len(dependent),
            'unavailable_sources':_source_gaps(store) if category!='recovery_packages' else [],
            'confirmation':'RESET WORKING DATA' if category=='reset' else 'DELETE',
            'notice':('Backups and recovery ZIPs are kept separately. Browser drafts will be cleared in this browser.' if category=='reset' else
                      'Current assets are retained. Missing source files remain visible to quality checks; embedded copies can remain in assets, journals, snapshots and backups.' if category in ('imports','sources') else
                      'This removes only the selected records. Copies in other history, archived workbooks and backups remain. Issue findings can reappear when checks run.')}


@serialized
def preview_cleanup(store, request):
    state = inventory(store)
    plan = _build_plan(store,request,state)
    token = secrets.token_urlsafe(24)
    store._cleanup_previews = {token:{'request':json.loads(json.dumps(request)),'signature':_signature(state),'created':time.monotonic()}}
    return {**plan,'preview_id':token,'revision':state['revision']}


@serialized
def set_coverage_dismissed(store, batch_id, dismissed):
    if not isinstance(dismissed,bool): raise ValueError('Choose dismiss or restore')
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        row = conn.execute("SELECT contents FROM import_batches WHERE token=? AND state='committed'",(batch_id,)).fetchone()
        if not row: raise ValueError('Import history entry not found')
        batch = json.loads(row[0]);batch['coverage_dismissed'] = dismissed
        conn.execute('UPDATE import_batches SET contents=? WHERE token=?',(json.dumps(batch,ensure_ascii=False),batch_id))
        next_revision(conn)
    return {'dismissed':dismissed}


def _delete_assets(conn, ids, revision):
    from .quality import canonical_identifier
    chosen = set(ids)
    rows = conn.execute('SELECT id,name,family,details FROM assets').fetchall()
    selection = json.dumps(ids)
    conn.execute('UPDATE field_verifications SET active=0 WHERE asset_id IN (SELECT value FROM json_each(?))',(selection,))
    conn.execute("UPDATE quality_issues SET state='superseded' WHERE asset_id IN (SELECT value FROM json_each(?)) AND state IN ('resolved','accepted_exception')",(selection,))
    shared = set()
    for asset_id,name,family,raw in rows:
        if asset_id not in chosen: continue
        before = {'name':name,'family':family,**json.loads(raw)}
        shared.update((key,canonical_identifier(before.get(key))) for key in ('tag_original','asset_number_original') if canonical_identifier(before.get(key)))
        _append_event(conn,asset_id,before,None,'clear',revision)
    # A removed identity can invalidate a surviving peer's collision exception.
    # Parse each retained asset at most once rather than once per removed asset.
    if shared:
        for asset_id,_,_,raw in rows:
            if asset_id in chosen: continue
            details = json.loads(raw)
            if any((key,canonical_identifier(details.get(key))) in shared for key in ('tag_original','asset_number_original')):
                conn.execute("UPDATE quality_issues SET state='superseded' WHERE asset_id=? AND rule_id='identity-collision' AND state IN ('resolved','accepted_exception')",(asset_id,))
    conn.executemany('DELETE FROM assets WHERE id=?',[(x,) for x in ids])


def _mutate(conn, plan, revision):
    category,ids = plan['category'],plan['ids']
    if category=='reset':
        for table in WORKING_TABLES: conn.execute('DELETE FROM '+table)
        conn.execute('DROP TABLE IF EXISTS import_reference')
        settings = _settings(conn);settings['data_epoch'] = secrets.token_hex(16)
        settings.update(local_success=False,independent_success=False,error='Working data reset. Run Back up and test copy for the new dataset.')
        for key in ('day','local_path','local_at','independent_at','independent_path'): settings.pop(key,None)
        conn.execute('CREATE TABLE IF NOT EXISTS backup_settings (id INTEGER PRIMARY KEY CHECK(id=1), contents TEXT NOT NULL)')
        conn.execute('INSERT OR REPLACE INTO backup_settings VALUES (1,?)',(json.dumps(settings),))
    elif category=='assets': _delete_assets(conn,ids,revision)
    elif category=='snapshots': conn.executemany('DELETE FROM master_snapshots WHERE snapshot_id=?',[(x,) for x in ids])
    elif category=='references': conn.executemany('DELETE FROM import_reference WHERE name=?',[(x,) for x in ids])
    elif category in ('verification','history'):
        for table in ids: conn.execute('DELETE FROM '+table)  # validated against inventory, never arbitrary SQL
    elif category=='recovery_packages':
        settings = _settings(conn)
        removed = {str((Path(row['folder'])/row['filename']).resolve()) for row in plan['files']}
        if settings.get('independent_path') and str(Path(settings['independent_path']).resolve()) in removed:
            settings.update(independent_success=False,error='Selected recovery copy deleted. Run Back up and test copy to renew protection.')
            for key in ('day','independent_at','independent_path'): settings.pop(key,None)
            conn.execute('UPDATE backup_settings SET contents=? WHERE id=1',(json.dumps(settings),))
    elif category in ('imports','staged'):
        for token in ids:
            live = conn.execute('SELECT 1 FROM import_batch_assets l LEFT JOIN asset_aliases aa ON aa.retired_id=l.asset_id JOIN assets a ON a.id=COALESCE(aa.survivor_id,l.asset_id) WHERE l.token=? LIMIT 1',(token,)).fetchone()
            if live and category=='imports':
                # Keep the minimal dependency so deleting an archive cannot make
                # retained assets silently pass the source-evidence check.
                row = conn.execute('SELECT contents FROM import_batches WHERE token=?',(token,)).fetchone()
                batch = json.loads(row[0])
                tombstone = {'format':batch.get('format'),'data':{'Assets':[]},'evidence_deleted':True,'coverage_dismissed':True}
                conn.execute('UPDATE import_batches SET contents=? WHERE token=?',(json.dumps(tombstone),token))
            else:
                conn.execute('DELETE FROM import_batch_assets WHERE token=?',(token,))
                conn.execute('DELETE FROM import_batches WHERE token=?',(token,))
    if category in ('imports','staged','sources'):
        removed = {row['filename'][:-5] for row in plan['files']}
        for token,digest,raw in conn.execute('SELECT token,digest,contents FROM import_batches').fetchall():
            if digest in removed:
                batch = json.loads(raw);batch['source_archive_deleted'] = True
                conn.execute('UPDATE import_batches SET contents=? WHERE token=?',(json.dumps(batch,ensure_ascii=False),token))


def _journal_path(store, token):
    return Path(store.db_path).resolve().parent/'.cleanup-journals'/(token+'.json')


def _complete_journal(store, path):
    """Finish a committed deletion, or restore files from an uncommitted one."""
    journal = json.loads(path.read_text(encoding='utf-8'))
    token = path.stem
    if not re.fullmatch(r'[a-f0-9]{32}',token): raise ValueError('Invalid cleanup journal')
    source_root = Path(store.db_path).resolve().parent/'source-archives'
    roots = _roots(store)
    with closing(sqlite3.connect(store.db_path)) as conn:
        has_receipts = conn.execute("SELECT 1 FROM sqlite_master WHERE name='cleanup_receipts'").fetchone()
        committed = bool(has_receipts and conn.execute('SELECT 1 FROM cleanup_receipts WHERE token=?',(token,)).fetchone())
    for item in journal['moves']:
        source,staged = Path(item['source']),Path(item['staged'])
        valid_source = source.parent==source_root and _SOURCE.fullmatch(source.name)
        valid_package = source.parent in roots and _PACKAGE.fullmatch(source.name)
        if not (valid_source or valid_package) or staged!=source.parent/('.cleanup-'+token)/source.name or source.is_symlink() or staged.is_symlink():
            raise ValueError('Unsafe cleanup journal path')
        if staged.exists():
            if committed: staged.unlink()
            elif source.exists(): raise ValueError('Cleanup recovery cannot overwrite an existing file')
            else: os.replace(staged,source)
        if staged.parent.is_dir():
            try: staged.parent.rmdir()
            except OSError: pass
    path.unlink()
    if has_receipts:
        with closing(sqlite3.connect(store.db_path)) as conn,conn: conn.execute('DELETE FROM cleanup_receipts WHERE token=?',(token,))


@serialized
def recover_pending_cleanup(store):
    folder = Path(store.db_path).resolve().parent/'.cleanup-journals'
    if folder.is_symlink(): raise ValueError('Cleanup journal folder cannot be a symbolic link')
    if folder.is_dir():
        for path in sorted(folder.glob('*.json')):
            if path.is_symlink(): raise ValueError('Cleanup journal cannot be a symbolic link')
            _complete_journal(store,path)


@serialized
def apply_cleanup(store, preview_id, confirmation):
    recover_pending_cleanup(store)
    preview = getattr(store,'_cleanup_previews',{}).get(preview_id)
    if not preview or time.monotonic()-preview['created']>900: raise ValueError('Deletion preview expired. Preview again.')
    state = inventory(store)
    if _signature(state)!=preview['signature']: raise ValueError('Stored data changed. Preview deletion again.')
    plan = _build_plan(store,preview['request'],state)
    if confirmation!=plan['confirmation']: raise ValueError('Type '+plan['confirmation']+' to confirm')
    root = Path(store.db_path).resolve().parent
    recovery = None
    if plan['category']!='recovery_packages':
        # Protect the working data independently of the removable source files.
        status = automatic_backup(store,force=True)
        if status.get('independent_success') and status.get('independent_path'):
            recovery = Path(status['independent_path'])
        else:
            copies = root/'recovery-copies'
            if copies.is_symlink(): raise ValueError('Recovery folder cannot be a symbolic link')
            copies.mkdir(exist_ok=True)
            recovery = export_master_package(store,copies/('inspection-recovery-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.zip'),allow_missing_sources=True)
    deletion_id = secrets.token_hex(16)
    journal = _journal_path(store,deletion_id)
    moves = []
    for row in plan['files']:
        source = Path(row['folder'])/row['filename']
        if source.is_symlink() or not source.is_file() or source.parent.is_symlink(): raise ValueError('Deletion target is not a regular managed file')
        staged = source.parent/('.cleanup-'+deletion_id)/source.name
        moves.append({'source':str(source),'staged':str(staged)})
    if moves:
        journal.parent.mkdir(exist_ok=True)
        # Startup ignores unpublished .partial files. Only a complete, flushed
        # journal becomes visible, and no archive moves until publication.
        fd,temporary = tempfile.mkstemp(dir=journal.parent,suffix='.partial')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump({'moves':moves},stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,journal)
        finally: Path(temporary).unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(store.db_path)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            revision = next_revision(conn)
            for move in moves:
                staged = Path(move['staged']);staged.parent.mkdir(exist_ok=True)
                os.replace(move['source'],staged)
            _mutate(conn,plan,revision)
            if moves:
                conn.execute('CREATE TABLE IF NOT EXISTS cleanup_receipts (token TEXT PRIMARY KEY)')
                conn.execute('INSERT INTO cleanup_receipts VALUES (?)',(deletion_id,))
    except BaseException:
        if moves: _complete_journal(store,journal)
        raise
    warning = ('Protection saved all available bytes. '+str(len(plan['unavailable_sources']))+' original source paths were missing or damaged; the manifest records source gaps and any content-based relocations.' if plan['unavailable_sources'] else None)
    if moves:
        try: _complete_journal(store,journal)
        except OSError: warning = (warning+' ' if warning else '')+'Deletion committed; temporary quarantined files will be removed when the app restarts.'
    store._cleanup_previews = {}
    if hasattr(store,'_previews'): store._previews.clear()
    return {'deleted':plan['counts'],'recovery':str(recovery) if recovery else None,'warning':warning,
            'reload_required':plan['category']=='reset','data_epoch':data_epoch(store)}

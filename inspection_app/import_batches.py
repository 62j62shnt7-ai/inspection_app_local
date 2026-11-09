"""Durable local staging, immutable content-addressed source evidence."""
from . import payloads
from contextlib import closing
from pathlib import Path
import hashlib
import os
import sqlite3
import tempfile


def archive_source(store, source):
    contents=Path(source).read_bytes()
    digest=hashlib.sha256(contents).hexdigest()
    folder=Path(store.db_path).parent/'source-archives'
    folder.mkdir(exist_ok=True)
    target=folder/(digest+'.xlsx')
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
            raise ValueError('Source archive checksum mismatch')
    else:
        fd,name=tempfile.mkstemp(dir=folder,suffix='.partial')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(contents);stream.flush();os.fsync(stream.fileno())
            os.replace(name,target)
        finally:
            Path(name).unlink(missing_ok=True)
    return digest


def invalidate_batches(store):
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute("UPDATE import_batches SET state='cancelled' WHERE state='staged'")
    if hasattr(store,'_previews'): store._previews.clear()


def persist_batch(store,token,staged):
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute("UPDATE import_batches SET state='cancelled' WHERE state='staged'")
        conn.execute('INSERT INTO import_batches(token,state,digest,base_revision,contents) VALUES (?,?,?,?,?)',
                     (token,'staged',staged['digest'],staged['revision'],payloads.dumps(staged,ensure_ascii=False,default=str)))


def load_batch(store,token):
    with closing(sqlite3.connect(store.db_path)) as conn:
        row=conn.execute("SELECT contents FROM import_batches WHERE token=? AND state='staged'",(token,)).fetchone()
    if not row:return None
    result=payloads.loads(row[0])
    archive=Path(store.db_path).parent/'source-archives'/(result['digest']+'.xlsx')
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=result['digest']:
        raise ValueError('Source archive missing or damaged. Preview the workbook again.')
    return result


def list_staged_batches(store):
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows=conn.execute("SELECT token,digest,contents FROM import_batches WHERE state='staged'").fetchall()
    return [{'token':token,'digest':digest,'format':payloads.loads(contents).get('format'),'assets':len(payloads.loads(contents)['data']['Assets'])} for token,digest,contents in rows]


from functools import lru_cache

@lru_cache(maxsize=256)
def _archive_hash(path,mtime_ns,size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_archive_problems(conn):
    database=conn.execute('PRAGMA database_list').fetchone()[2]
    folder=Path(database).parent/'source-archives'
    aliases=dict(conn.execute('SELECT retired_id,survivor_id FROM asset_aliases'))
    problems={}
    status={}
    for asset_id,digest in conn.execute("SELECT l.asset_id,b.digest FROM import_batch_assets l JOIN import_batches b ON b.token=l.token WHERE b.state='committed'"):
        if digest not in status:
            path=folder/(digest+'.xlsx')
            try:
                stat=path.stat()
                status[digest]=path.is_symlink() or _archive_hash(str(path),stat.st_mtime_ns,stat.st_size)!=digest
            except OSError:status[digest]=True
        if status[digest]:problems.setdefault(aliases.get(asset_id,asset_id),set()).add(digest)
    return problems


def list_import_history(store, limit=20):
    """Return compact committed import summaries, including retained source gaps."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError('Invalid import history limit')
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows=conn.execute("SELECT token,digest,contents FROM import_batches WHERE state='committed' ORDER BY rowid DESC LIMIT ?",(limit,)).fetchall()
    history=[]
    folder=Path(store.db_path).parent/'source-archives'
    for token,digest,raw in rows:
        batch=payloads.loads(raw)
        summaries=batch.get('sheet_summary',[])
        unclassified=[{'sheet':sheet.get('name'),'rows':sheet.get('unclassified_rows',[])} for sheet in summaries if sheet.get('unclassified_rows')]
        source=folder/(digest+'.xlsx')
        try:
            stat=source.stat()
            available=not source.is_symlink() and _archive_hash(str(source),stat.st_mtime_ns,stat.st_size)==digest
        except OSError:
            available=False
        history.append({'batch_id':token,'digest':digest,'format':batch.get('format'),'assets':len(batch.get('data',{}).get('Assets',[])),
                        'dismissed':bool(batch.get('coverage_dismissed')),'evidence_deleted':bool(batch.get('evidence_deleted')),
                        'source_archive_deleted':bool(batch.get('source_archive_deleted')),
                        'coverage_acknowledged':batch.get('coverage_acknowledged') is True,
                        'unclassified_count':sum(len(item['rows']) for item in unclassified),
                        'unclassified_rows':unclassified,'excluded_sheets':batch.get('excluded_sheets',[]),
                        'source_available':available})
    return history

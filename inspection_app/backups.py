from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
import secrets
import re
import sqlite3
import json
import gzip
import os
import shutil
import tempfile
import zlib
import hashlib
from .store import serialized, initialize_version_clock

_BACKUP_FILENAME=re.compile(r'inspection-(?:migration-)?\d{8}-\d{6}-[0-9a-f]{8}\.db(?:\.gz)?\Z')
MAX_BACKUP_BYTES = 1024 * 1024 * 1024


def compact_database_copy(source_path, destination):
    """Compact only a snapshot; never VACUUM the operational database."""
    with closing(sqlite3.connect(Path(source_path).resolve().as_uri()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        target.execute('VACUUM')
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup failed integrity validation')


@contextmanager
def materialized_database(path):
    """Yield raw SQLite, detecting gzip by content even for uploaded .db files."""
    path = Path(path)
    with path.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    if not compressed:
        yield path
        return
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp)/'backup.db'
        try:
            with gzip.open(path, 'rb') as source, database.open('wb') as target:
                total = 0
                while True:
                    chunk = source.read(min(1024*1024, MAX_BACKUP_BYTES-total+1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BACKUP_BYTES:
                        raise ValueError('Expanded backup is too large (1 GiB limit)')
                    target.write(chunk)
        except (OSError, EOFError, zlib.error) as exc:
            raise ValueError('Compressed backup is damaged or incomplete') from exc
        yield database

@serialized
def create_backup(store, compress=False):
    folder = Path(store.db_path).parent / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('inspection-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4) + ('.db.gz' if compress else '.db'))
    # Same-filesystem staging keeps interrupted writes out of the managed list.
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=folder) as tmp:
        database = Path(tmp)/'snapshot.db'
        compact_database_copy(store.db_path, database)
        staged = database
        if compress and database.stat().st_size > MAX_BACKUP_BYTES:
            # Keep large databases independently restorable without requiring an
            # unbounded decompressor or blocking the edit that needs protection.
            compress = False
            path = path.with_suffix('')
        if compress:
            staged = Path(tmp)/'snapshot.db.gz'
            with database.open('rb') as source, gzip.open(staged, 'wb', compresslevel=6) as target:
                shutil.copyfileobj(source, target)
            # Verify gzip CRC and the exact compacted payload before publication.
            with materialized_database(staged) as expanded:
                def digest(file):
                    with file.open('rb') as stream:
                        return hashlib.file_digest(stream, 'sha256').digest()
                if digest(expanded) != digest(database):
                    raise ValueError('Compressed backup failed validation')
        # Windows FlushFileBuffers requires a writable handle; opening read-only
        # makes every protected save/clear fail before its backup is published.
        with staged.open('r+b') as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
    return path


@contextmanager
def normalized_database(path):
    """Normalize the supported four-column legacy layout on a disposable copy."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
        columns = {row[1] for row in source.execute('PRAGMA table_info(assets)')}
        if columns != {'id', 'name', 'family', 'version'}:
            yield Path(path)
            return
        if source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone():
            raise ValueError('Backup is not a compatible legacy inspection database')
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)/'normalized.db'
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
                from .store import initialize_schema
                initialize_schema(target)
                target.commit()
            yield copy


def validate_database(store, path):
    with normalized_database(path) as normalized:
        return _validate_database(store, normalized)


def _validate_database(store, path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Backup failed integrity validation')
        tables={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'schema_info' in tables:
            from .migrations import SCHEMA_VERSION
            row=source.execute('SELECT version FROM schema_info WHERE id=1').fetchone()
            if not row or not isinstance(row[0],int) or row[0]>SCHEMA_VERSION:raise ValueError('Backup requires a newer or compatible app schema')
        asset_ids={r[0] for r in source.execute('SELECT id FROM assets')}
        for asset_id, name, family, version, raw in source.execute('SELECT id,name,family,version,details FROM assets'):
            if not isinstance(asset_id, str) or not asset_id or not isinstance(name, str) or not name.strip() or not isinstance(family, str) or not family.strip() or not isinstance(version, int) or version < 1:
                raise ValueError('Backup contains invalid asset identity or version')
            try:
                details = json.loads(raw)
                store._validate_details(family, details)
            except (ValueError, TypeError) as exc:
                raise ValueError('Backup contains invalid asset details: ' + str(exc)) from exc
        # Validate portable trust/history JSON before it becomes operational.
        json_tables={'import_reference':('contents',list),'master_snapshots':('contents',dict),'import_batches':('contents',dict),'bulk_operations':('contents',dict),'consolidation_previews':('contents',dict),'backup_settings':('contents',dict),'source_baselines':('contents',dict)}
        for table,(column,shape) in json_tables.items():
            if table not in tables:continue
            for (raw,) in source.execute(f'SELECT {column} FROM {table}'):
                try:value=json.loads(raw)
                except (ValueError,TypeError) as exc:raise ValueError('Backup contains invalid metadata JSON in '+table) from exc
                if not isinstance(value,shape):raise ValueError('Backup contains invalid metadata shape in '+table)
        if 'correction_events' in tables:
            for revision,before,after in source.execute('SELECT revision,before_json,after_json FROM correction_events'):
                if not isinstance(revision,int) or revision<1:raise ValueError('Backup contains invalid correction revision')
                for raw in (before,after):
                    try:value=json.loads(raw)
                    except (ValueError,TypeError) as exc:raise ValueError('Backup contains invalid correction metadata JSON') from exc
                    if value is not None and not isinstance(value,dict):raise ValueError('Backup contains invalid correction metadata')
        if 'asset_aliases' in tables:
            for retired,survivor in source.execute('SELECT retired_id,survivor_id FROM asset_aliases'):
                if retired in asset_ids or retired==survivor or source.execute('SELECT 1 FROM asset_aliases WHERE retired_id=?',(survivor,)).fetchone():raise ValueError('Backup contains a broken asset alias')
        if 'quality_issues' in tables:
            for state,severity in source.execute('SELECT state,severity FROM quality_issues'):
                if state not in ('open','resolved','accepted_exception','superseded') or severity not in ('blocking','warning'):raise ValueError('Backup contains invalid quality metadata')


@serialized
def restore_backup(store, path):
    """Validate a backup, save the current database, then restore atomically."""
    path = Path(path).resolve()
    if not path.is_file() or path == Path(store.db_path).resolve():
        raise ValueError('Select an existing backup file')
    try:
        with materialized_database(path) as database, normalized_database(database) as normalized:
            return _restore_database(store, normalized)
    except sqlite3.DatabaseError as exc:
        raise ValueError('Backup is invalid or could not be restored') from exc


def _restore_database(store, path):
    try:
        validate_database(store,path)
        from .cleanup import recover_pending_cleanup
        recover_pending_cleanup(store)
        # Read-only mode prevents accidentally creating a missing backup.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup failed the integrity check')
            columns = {row[1] for row in source.execute('PRAGMA table_info(assets)')}
            if not {'id', 'name', 'family', 'version', 'details'} <= columns:
                raise ValueError('Backup is not a compatible inspection database')
            from .recovery import automatic_backup
            safety = automatic_backup(store,force=True)['local_path']
            with closing(sqlite3.connect(store.db_path)) as target, closing(sqlite3.connect(':memory:')) as staged:
                # Prepare fresh versions before the atomic SQLite backup replaces
                # the live database. Old editor and reconciliation versions stay stale.
                has_settings=target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='backup_settings'").fetchone()
                settings_row=target.execute('SELECT contents FROM backup_settings WHERE id=1').fetchone() if has_settings else None
                local_settings=json.loads(settings_row[0]) if settings_row else {}
                source.backup(staged)
                initialize_version_clock(staged)
                from .migrations import migrate_database
                migrate_database(staged)
                current_clock = target.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
                restored_clock = staged.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
                next_version = max(current_clock, restored_clock) + 1
                staged.execute('UPDATE assets SET version=?', (next_version,))
                staged.execute('UPDATE version_clock SET value=? WHERE id=1', (next_version,))
                staged.execute('CREATE TABLE IF NOT EXISTS backup_settings (id INTEGER PRIMARY KEY CHECK(id=1),contents TEXT NOT NULL)')
                staged.execute('DELETE FROM backup_settings')
                settings={'folder':local_settings['folder']} if local_settings.get('folder') else {}
                if local_settings.get('data_epoch'):
                    settings['data_epoch']=local_settings['data_epoch']
                settings.update(local_success=False,independent_success=False,error='Restored database: run a backup and test the independent copy destination')
                staged.execute('INSERT INTO backup_settings VALUES (1,?)',(json.dumps(settings),))
                staged.execute("UPDATE import_batches SET state='cancelled' WHERE state='staged'")
                staged.commit()
                staged.backup(target)
    except sqlite3.DatabaseError as exc:
        raise ValueError('Backup is invalid or could not be restored') from exc
    if hasattr(store, '_previews'):
        store._previews.clear()
    with closing(sqlite3.connect(store.db_path)) as conn:
        digests=[r[0] for r in conn.execute("SELECT digest FROM import_batches WHERE state='committed'")]
    missing=[digest for digest in digests if not (Path(store.db_path).parent/'source-archives'/(digest+'.xlsx')).is_file()]
    return {'safety_backup': str(safety),'warning':('Source archives are unavailable for '+str(len(missing))+' import batches. Restore a full recovery package to recover the evidence.') if missing else None}


def list_backups(store):
    folder = Path(store.db_path).parent / 'backups'
    if not folder.is_dir(): return []
    files = [p for p in folder.glob('inspection-*') if _BACKUP_FILENAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()]
    return [{'filename': p.name, 'modified': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'), 'size': p.stat().st_size} for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]


@serialized
def delete_saved_backups(store, filenames):
    if not isinstance(filenames,list) or not filenames or any(not isinstance(name,str) or not name for name in filenames):
        raise ValueError('Select one or more saved backups to delete')
    if len(set(filenames))!=len(filenames):
        raise ValueError('Selected backups must be distinct')
    folder=Path(store.db_path).parent/'backups'
    if folder.is_symlink():raise ValueError('Managed backup folder must not be a symbolic link')
    data_root=Path(store.db_path).parent.resolve()
    folder_path=folder.resolve()
    try:folder_path.relative_to(data_root)
    except ValueError as exc:raise ValueError('Managed backup folder is outside the app data folder') from exc
    known={row['filename'] for row in list_backups(store)}
    if any(name not in known for name in filenames):
        raise ValueError('One or more selected backups no longer exist or are not managed by this app')
    paths=[]
    for name in filenames:
        path=folder/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('One or more selected backups are not regular managed files')
        resolved=path.resolve()
        try:resolved.relative_to(folder_path)
        except ValueError as exc:raise ValueError('Selected backup is outside the managed backup folder') from exc
        if resolved.parent!=folder_path:
            raise ValueError('Selected backup is outside the managed backup folder')
        paths.append((name,path))
    deleted=[];failed=[]
    for name,path in paths:
        try:
            path.unlink()
            deleted.append(name)
        except OSError as exc:
            failed.append({'filename':name,'error':str(exc) or exc.__class__.__name__})
    if deleted:
        from .recovery import invalidate_deleted_local_backup
        invalidate_deleted_local_backup(store,[path for name,path in paths if name in deleted])
    return {'deleted':deleted,'failed':failed}


def restore_saved_backup(store, filename):
    if not isinstance(filename, str) or filename not in {row['filename'] for row in list_backups(store)}:
        raise ValueError('Backup not found')
    return restore_backup(store, Path(store.db_path).parent / 'backups' / filename)

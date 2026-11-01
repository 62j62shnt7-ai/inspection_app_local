from contextlib import closing
from datetime import datetime
from pathlib import Path
import secrets
import sqlite3

def create_backup(store):
    folder = Path(store.db_path).parent / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('inspection-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4) + '.db')
    with closing(sqlite3.connect(store.db_path)) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
    return path


def restore_backup(store, path):
    """Validate a backup, save the current database, then restore atomically."""
    path = Path(path).resolve()
    if not path.is_file() or path == Path(store.db_path).resolve():
        raise ValueError('Select an existing backup file')
    try:
        # Read-only mode prevents accidentally creating a missing backup.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup failed the integrity check')
            columns = {row[1] for row in source.execute('PRAGMA table_info(assets)')}
            if not {'id', 'name', 'family', 'version', 'details'} <= columns:
                raise ValueError('Backup is not a compatible inspection database')
            safety = create_backup(store)
            with closing(sqlite3.connect(store.db_path)) as target:
                source.backup(target)
    except sqlite3.DatabaseError as exc:
        raise ValueError('Backup is invalid or could not be restored') from exc
    if hasattr(store, '_previews'):
        store._previews.clear()
    return {'safety_backup': str(safety)}


def list_backups(store):
    folder = Path(store.db_path).parent / 'backups'
    if not folder.is_dir(): return []
    files = [p for p in folder.glob('inspection-*.db') if p.is_file() and not p.is_symlink()]
    return [{'filename': p.name, 'modified': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'), 'size': p.stat().st_size} for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]


def restore_saved_backup(store, filename):
    if not isinstance(filename, str) or filename not in {row['filename'] for row in list_backups(store)}:
        raise ValueError('Backup not found')
    return restore_backup(store, Path(store.db_path).parent / 'backups' / filename)

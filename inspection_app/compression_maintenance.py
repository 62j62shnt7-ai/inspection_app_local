"""Explicit offline compression with an independent backup and preservation proof.

Run only as an owner-requested maintenance action, never during app startup:
python3 -m inspection_app.compression_maintenance --database PATH --backup-folder PATH
"""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from . import payloads
from .backups import validate_database
from .lock import data_lock
from .migrations import migrate_database, SCHEMA_VERSION
from .store import Store


def database_fingerprint(path):
    """Hash every typed value and rowid, decoding only selected payload columns.

Schema version is checked separately because the intentional migration changes
it. Include internal sqlite_sequence and all unknown tables and schema objects.
"""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database failed integrity validation')
        c.execute('BEGIN')
        schema = c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        tables = {}
        for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            quoted = '"' + table.replace('"', '""') + '"'
            names = [row[1] for row in c.execute(f'PRAGMA table_info({quoted})')]
            columns = payloads.COLUMNS.get(table, ())
            digest = hashlib.sha256(); count = 0
            try:
                rows = c.execute(f'SELECT rowid,* FROM {quoted} ORDER BY rowid')
                fields = ['__rowid__'] + names
            except sqlite3.OperationalError:  # WITHOUT ROWID extension tables.
                rows = c.execute(f'SELECT * FROM {quoted} ORDER BY ' + ','.join('"' + name.replace('"', '""') + '"' for name in names))
                fields = names
            for row in rows:
                values = []
                for field, value in zip(fields, row):
                    if table == 'schema_info' and field == 'version':
                        value = '<schema version checked separately>'
                    elif field in columns:
                        value = payloads.decode_text(value)
                    values.append(value)
                encoded = repr(tuple(values)).encode('utf-8')
                digest.update(len(encoded).to_bytes(8, 'big')); digest.update(encoded)
                count += 1
            tables[table] = {'rows': count, 'sha256': digest.hexdigest()}
        pragmas = {name: c.execute('PRAGMA ' + name).fetchone()[0] for name in ('user_version', 'application_id', 'encoding')}
        return {'schema': schema, 'tables': tables, 'pragmas': pragmas}


def _export_tables(database, destination):
    from . import exports
    from .imports import read_workbook
    counter = itertools.count()
    # The exporter assigns UUIDs to source rows with missing optional IDs.
    # Deterministic IDs isolate that normal randomness during comparison only;
    # no generated value is written back to the database.
    identifiers = SimpleNamespace(uuid4=lambda: uuid.UUID(int=next(counter)))
    with patch.object(exports, 'uuid', identifiers):
        exports.export_workbook(SimpleNamespace(db_path=str(database)), destination)
    return read_workbook(destination)


def _install_candidate(candidate, target):
    with closing(sqlite3.connect(candidate.resolve().as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(target.resolve().as_uri() + '?mode=rw', uri=True)) as live:
        source.backup(live)
        live.execute('VACUUM')


def compress_database(database, backup_folder):
    """Migrate/compact a verified candidate, preserving an independent original."""
    database = Path(database).absolute()
    if database.is_symlink() or not database.is_file():
        raise ValueError('Choose an existing regular database')
    database = database.resolve()
    backup_folder = Path(backup_folder).resolve()
    if backup_folder == database.parent or database.parent in backup_folder.parents:
        raise ValueError('Choose an independent maintenance folder outside the data directory')
    with data_lock(database.parent):
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
            version = source.execute('SELECT version FROM schema_info WHERE id=1').fetchone()
            if not version or version[0] not in (10, SCHEMA_VERSION):
                raise ValueError('Offline compression requires schema 10 or 11')
            if source.execute('PRAGMA journal_mode').fetchone()[0] == 'wal':
                raise ValueError('Close/checkpoint WAL connections before offline compression')
            before = database_fingerprint(database)
            before_bytes = database.stat().st_size
            backup_folder.mkdir(parents=True, exist_ok=True)
            run = Path(tempfile.mkdtemp(prefix='lossless-compression-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-', dir=backup_folder))
            original = run / 'original.db'
            candidate = run / 'candidate.db'
            for destination in (original, candidate):
                with closing(sqlite3.connect(destination)) as copy:
                    source.backup(copy)
                if database_fingerprint(destination) != before:
                    raise ValueError('Independent snapshot preservation check failed')
        report_path = run / 'report.json'
        report = {'before_bytes': before_bytes, 'backup': str(original), 'report': str(report_path), 'database': str(database), 'verification': 'pending', 'original_schema_version': version[0]}
        installed = False
        try:
            with closing(sqlite3.connect(candidate)) as c, c:
                migrate_database(c)
            with closing(sqlite3.connect(candidate)) as c:
                c.execute('VACUUM')
                if c.execute('SELECT version FROM schema_info WHERE id=1').fetchone() != (SCHEMA_VERSION,):
                    raise ValueError('Candidate schema version is incorrect')
            if database_fingerprint(candidate) != before:
                raise ValueError('Candidate data/history preservation check failed')
            validator = SimpleNamespace(db_path=str(candidate), _validate_details=Store._validate_details)
            validate_database(validator, candidate)
            before_export = _export_tables(original, run / 'before.xlsx')
            after_export = _export_tables(candidate, run / 'after.xlsx')
            if before_export != after_export:
                raise ValueError('Workbook export preservation check failed')
            # Recheck immediately before installing; never overwrite intervening data.
            if database_fingerprint(database) != before:
                raise ValueError('Database changed during maintenance; original was not replaced')
            installed = True
            _install_candidate(candidate, database)
            if database_fingerprint(database) != before:
                raise ValueError('Installed database preservation check failed')
            with closing(sqlite3.connect(database)) as c:
                if c.execute('SELECT version FROM schema_info WHERE id=1').fetchone() != (SCHEMA_VERSION,):
                    raise ValueError('Installed schema version is incorrect')
            validate_database(validator, database)
            report.update(verification='passed', after_bytes=database.stat().st_size,
                          saved_bytes=before_bytes-database.stat().st_size, schema_version=SCHEMA_VERSION,
                          export_tables_equal=True, preserved=before)
        except BaseException as exc:
            report.update(verification='failed', error=str(exc))
            if installed:
                # Retain every original byte/value if installation or final
                # validation fails. Do not reuse the failing installation helper.
                with closing(sqlite3.connect(original)) as source, closing(sqlite3.connect(database)) as live:
                    source.backup(live)
                if database_fingerprint(database) != before:
                    raise RuntimeError('Rollback verification failed; independent backup: ' + str(original)) from exc
                report['original_restored'] = True
            report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
            raise
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--backup-folder', required=True, type=Path)
    args = parser.parse_args()
    report = compress_database(args.database, args.backup_folder)
    print(json.dumps({key: value for key, value in report.items() if key != 'preserved'}, indent=2))


if __name__ == '__main__':
    main()

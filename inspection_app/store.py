from contextlib import closing
import sqlite3
import uuid
import json
import threading
from functools import wraps
from .months import validate_month, due_bucket
from .migrations import migrate_database, backup_before_migration
from .mutations import next_revision, record_event

def serialized(operation):
    @wraps(operation)
    def run(store, *args, **kwargs):
        with store._lock:
            return operation(store, *args, **kwargs)
    return run

def initialize_version_clock(conn):
    # Keep the highest issued version even when assets are cleared or removed.
    conn.execute('CREATE TABLE IF NOT EXISTS version_clock (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
    conn.execute('INSERT OR IGNORE INTO version_clock VALUES (1, 0)')
    conn.execute('UPDATE version_clock SET value=MAX(value, (SELECT COALESCE(MAX(version),0) FROM assets)) WHERE id=1')
    for event in ('INSERT', 'UPDATE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS version_clock_{event.lower()} AFTER {event} ON assets
                        BEGIN UPDATE version_clock SET value=MAX(value, NEW.version) WHERE id=1; END''')

class Store:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        backup_before_migration(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, name TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL)')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(assets)')}
            if 'details' not in columns:
                conn.execute("ALTER TABLE assets ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
            initialize_version_clock(conn)
            migrate_database(conn)
        from .cleanup import recover_pending_cleanup
        recover_pending_cleanup(self)

    @serialized
    def get_asset(self, asset_id):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            alias=conn.execute('SELECT survivor_id FROM asset_aliases WHERE retired_id=?',(asset_id,)).fetchone()
            if alias:asset_id=alias[0]
            row = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
            if row is None:
                raise KeyError(asset_id)
            result = dict(row)
            result.update(json.loads(result.pop('details')))
            return result

    @serialized
    def save_asset(self, asset_id, payload, expected_version):
        from .recovery import automatic_backup
        automatic_backup(self)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            before = None
            if asset_id is None:
                name, family = payload.get('name'), payload.get('family')
                if not isinstance(name, str) or not name.strip() or not isinstance(family, str) or not family.strip():
                    raise ValueError('Name and family are required')
                asset_id = str(uuid.uuid4())
                details = {k:v for k,v in payload.items() if k not in ('id','version','name','family')}
                from .validation import reconcile_import_reviews
                self._validate_details(family, details)
                reconcile_import_reviews({'id':asset_id,'name':name,'family':family,**details})
                conn.execute('INSERT INTO assets (id,name,family,version,details) VALUES (?, ?, ?, ?, ?)', (asset_id, name, family, next_revision(conn), json.dumps(details)))
            else:
                conn.row_factory = sqlite3.Row
                row = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
                if row is None:
                    raise KeyError(asset_id)
                name, family = payload.get('name', row['name']), payload.get('family', row['family'])
                if not isinstance(name, str) or not name.strip() or not isinstance(family, str) or not family.strip():
                    raise ValueError('Name and family are required')
                if not isinstance(expected_version, int) or isinstance(expected_version, bool) or row['version'] != expected_version:
                    raise ValueError('Asset was changed by another edit. Reload and review again.')
                before = {'name': row['name'], 'family': row['family'], **json.loads(row['details'])}
                details = json.loads(row['details'])
                details.update({k:v for k,v in payload.items() if k not in ('id','version','name','family')})
                from .validation import reconcile_import_reviews
                self._validate_details(family, details)
                reconcile_import_reviews({'id':asset_id,'name':name,'family':family,**details})
                changed = conn.execute('UPDATE assets SET name=?, family=?, details=?, version=? WHERE id=? AND version=?', (name, family, json.dumps(details), next_revision(conn), asset_id, expected_version)).rowcount
                if changed != 1:
                    raise ValueError('Asset was changed by another edit')
            revision = conn.execute('SELECT version FROM assets WHERE id=?', (asset_id,)).fetchone()[0]
            record_event(conn, asset_id, before, {'name': name, 'family': family, **details}, 'manual', revision)
        return self.get_asset(asset_id)

    @staticmethod
    def _validate_details(family, details):
        if not isinstance(details, dict):
            raise ValueError('Asset details must be an object')
        if set(details)&{'id','name','family','version','details'}:
            raise ValueError('Asset details contain reserved identity fields')
        for key, label in [('inspections', 'Inspections'), ('technical_details', 'Technical details'), ('notes', 'Notes'), ('review_items', 'Review items'), ('source_cells', 'Source cells')]:
            values = details.get(key, [])
            if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
                raise ValueError(label + ' must be a list of objects')
        if details.get('record_status', 'Active') not in ('Active', 'Archived'):
            raise ValueError('Record status must be Active or Archived')
        seen = set()
        for inspection in details.get('inspections', []):
            kind = inspection.get('inspection_type')
            if kind not in ('OSI', 'Internal') or kind in seen:
                raise ValueError('Each inspection type may appear only once')
            seen.add(kind)
            if inspection.get('applicable') not in ('Yes', 'No'):
                raise ValueError('Inspection applicability must be Yes or No')
            for key in ('last_inspection_month', 'next_inspection_month', 'condition_review_by'):
                validate_month(inspection.get(key))
            if inspection.get('inspection_type') == 'Internal' and inspection.get('applicable') == 'Yes' and family.lower() in ('piping', 'flowline', 'trunkline', 'gas lift line'):
                raise ValueError('Internal inspections are not applicable to piping')

    def dashboard(self, current_month, start_month, end_month):
        start, end = validate_month(start_month), validate_month(end_month)
        if not start or not end or start > end:
            raise ValueError('Invalid upcoming period')
        totals = {'overdue': 0, 'due_this_month': 0, 'upcoming': 0, 'undated': 0, 'review': 0}
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            from .register import read_summaries
            for details in read_summaries(conn):
                for i in details.get('inspections', []):
                    if details.get('record_status') != 'Archived' and i.get('applicable') == 'Yes' and i.get('review_status') == 'Review':
                        totals['review'] += 1
                        continue
                    due = i.get('next_inspection_month')
                    bucket = due_bucket(due, current_month, i.get('applicable') == 'Yes', details.get('record_status') == 'Archived')
                    if bucket in totals:
                        totals[bucket] += 1
                    if bucket == 'future' and start <= due <= end:
                        totals['upcoming'] += 1
        return totals

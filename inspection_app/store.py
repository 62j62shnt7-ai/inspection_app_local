from contextlib import closing
import sqlite3
import uuid
import json
from .months import validate_month, due_bucket

class Store:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, name TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL)')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(assets)')}
            if 'details' not in columns:
                conn.execute("ALTER TABLE assets ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")

    def get_asset(self, asset_id):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
            if row is None:
                raise KeyError(asset_id)
            result = dict(row)
            result.update(json.loads(result.pop('details')))
            return result

    def save_asset(self, asset_id, payload, expected_version):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            if asset_id is None:
                name, family = payload.get('name'), payload.get('family')
                if not isinstance(name, str) or not name.strip() or not isinstance(family, str) or not family.strip():
                    raise ValueError('Name and family are required')
                asset_id = str(uuid.uuid4())
                details = {k:v for k,v in payload.items() if k not in ('id','version','name','family')}
                self._validate_details(family, details)
                conn.execute('INSERT INTO assets (id,name,family,version,details) VALUES (?, ?, ?, ?, ?)', (asset_id, name, family, 1, json.dumps(details)))
            else:
                conn.row_factory = sqlite3.Row
                row = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
                if row is None:
                    raise KeyError(asset_id)
                name, family = payload.get('name', row['name']), payload.get('family', row['family'])
                if not isinstance(name, str) or not name.strip() or not isinstance(family, str) or not family.strip():
                    raise ValueError('Name and family are required')
                details = json.loads(row['details'])
                details.update({k:v for k,v in payload.items() if k not in ('id','version','name','family')})
                self._validate_details(family, details)
                changed = conn.execute('UPDATE assets SET name=?, family=?, details=?, version=version+1 WHERE id=? AND version=?', (name, family, json.dumps(details), asset_id, expected_version)).rowcount
                if changed != 1:
                    raise ValueError('Asset was changed by another edit')
        return self.get_asset(asset_id)

    @staticmethod
    def _validate_details(family, details):
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
            for key in ('last_inspection_month', 'next_inspection_month'):
                validate_month(inspection.get(key))
            if inspection.get('inspection_type') == 'Internal' and inspection.get('applicable') == 'Yes' and family.lower() in ('piping', 'flowline', 'trunkline', 'gas lift line'):
                raise ValueError('Internal inspections are not applicable to piping')

    def dashboard(self, current_month, start_month, end_month):
        start, end = validate_month(start_month), validate_month(end_month)
        if not start or not end or start > end:
            raise ValueError('Invalid upcoming period')
        totals = {'overdue': 0, 'due_this_month': 0, 'upcoming': 0, 'undated': 0, 'review': 0}
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            for (raw,) in conn.execute('SELECT details FROM assets'):
                details = json.loads(raw)
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

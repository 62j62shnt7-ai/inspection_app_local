from contextlib import closing
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from collections import defaultdict
import openpyxl
from .months import validate_month
from .backups import create_backup

TABLES = ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells', 'Field Map')

def _revision(store):
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        rows = conn.execute('SELECT id,name,family,version,details FROM assets ORDER BY id').fetchall()
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()

def read_workbook(path):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    result = {}
    for name in TABLES:
        if name not in workbook.sheetnames:
            raise ValueError('Missing worksheet: ' + name)
        rows = workbook[name].iter_rows(values_only=True)
        headings = next(rows)
        if len(set(headings)) != len(headings):
            raise ValueError('Duplicate headings in ' + name)
        result[name] = [{heading: row[index] if index < len(row) else None for index, heading in enumerate(headings)} for row in rows if any(v is not None for v in row)]
    workbook.close()
    return result

def preview_import(store, path):
    path = Path(path)
    data = read_workbook(path)
    errors = []
    ids = [a.get('asset_id') for a in data['Assets']]
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        errors.append('Missing or duplicate asset IDs')
    existing = set(ids)
    inspection_ids = set()
    inspection_types = set()
    for row in data['Inspection Plan']:
        if row.get('asset_id') not in existing:
            errors.append('Inspection references an unknown asset')
        if not row.get('inspection_id') or row['inspection_id'] in inspection_ids:
            errors.append('Missing or duplicate inspection ID')
        inspection_ids.add(row.get('inspection_id'))
        identity = (row.get('asset_id'), row.get('inspection_type'))
        if identity in inspection_types:
            errors.append('Duplicate inspection type for an asset')
        inspection_types.add(identity)
        if row.get('inspection_type') not in ('OSI', 'Internal') or row.get('applicable') not in ('Yes', 'No'):
            errors.append('Invalid inspection type or applicability')
        for field in ('last_inspection_month', 'next_inspection_month'):
            try: validate_month(row.get(field))
            except ValueError: errors.append('Invalid inspection month')
    for name in ('Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells'):
        if any(row.get('asset_id') and row.get('asset_id') not in existing for row in data[name]):
            errors.append(name + ' references an unknown asset')
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        old_rows = {r[0]: r for r in conn.execute('SELECT id,name,family,details FROM assets')}
        old_ids = set(old_rows)
    incoming_inspections = defaultdict(dict)
    for row in data['Inspection Plan']:
        incoming_inspections[row.get('asset_id')][row.get('inspection_type')] = row
    comparison = []
    for asset in data['Assets']:
        asset_id = asset.get('asset_id')
        if asset_id not in old_rows:
            comparison.append({'id': asset_id, 'name': asset.get('asset_description') or '(unnamed asset)', 'status': 'new', 'changes': []})
            continue
        _, name, family, raw = old_rows[asset_id]
        details = json.loads(raw)
        pairs = [('Asset name', name, asset.get('asset_description') or '(unnamed asset)'), ('Family', family, asset.get('asset_family') or 'Unknown')]
        old_inspections = {row.get('inspection_type'): row for row in details.get('inspections', [])}
        for kind in ('OSI', 'Internal'):
            before, after = old_inspections.get(kind, {}), incoming_inspections[asset_id].get(kind, {})
            for label, key in [('Applicable', 'applicable'), ('Last month', 'last_inspection_month'), ('Next month', 'next_inspection_month')]:
                pairs.append((kind + ' ' + label, before.get(key), after.get(key)))
        changes = [{'field': label, 'current': str(old or ''), 'incoming': str(new or '')} for label, old, new in pairs if (old or '') != (new or '')]
        comparison.append({'id': asset_id, 'name': name, 'status': 'changed' if changes else 'matching', 'changes': changes})
    token = secrets.token_urlsafe(24)
    if not hasattr(store, '_previews'): store._previews = {}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    store._previews[token] = {'data': data, 'revision': _revision(store), 'digest': digest, 'errors': errors}
    return {'token': token, 'digest': digest, 'counts': {k:len(v) for k,v in data.items()}, 'additions':len(existing-old_ids), 'updates':len(existing & old_ids), 'retained':len(old_ids-existing), 'errors':list(dict.fromkeys(errors)), 'comparison':comparison}

def apply_import(store, token, mode='merge'):
    if mode not in ('merge', 'replace'): raise ValueError('Invalid import mode')
    staged = getattr(store, '_previews', {}).get(token)
    if not staged or staged['errors'] or staged['revision'] != _revision(store):
        raise ValueError('Import preview is invalid, has errors, or is stale')
    data = staged['data']
    if mode == 'replace' and not data['Assets']: raise ValueError('Cannot replace the database with an empty workbook')
    children = {}
    for sheet, key in [('Inspection Plan','inspections'), ('Technical Details','technical_details'), ('Notes & Actions','notes'), ('Review Items','review_items'), ('Source Cells','source_cells')]:
        grouped = defaultdict(list)
        for row in data[sheet]: grouped[row.get('asset_id')].append(row)
        children[key] = grouped
    backup = create_backup(store)
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute('SELECT id,name,family,version,details FROM assets ORDER BY id').fetchall()
        revision = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()
        if revision != staged['revision']:
            raise ValueError('Import preview is stale')
        conn.execute('CREATE TABLE IF NOT EXISTS import_reference (name TEXT PRIMARY KEY, contents TEXT NOT NULL)')
        if mode == 'replace':
            incoming_ids = {asset['asset_id'] for asset in data['Assets']}
            conn.executemany('DELETE FROM assets WHERE id=?', [(row[0],) for row in rows if row[0] not in incoming_ids])
            conn.execute('DELETE FROM import_reference')
        for asset in data['Assets']:
            asset_id = asset['asset_id']
            old = conn.execute('SELECT version FROM assets WHERE id=?', (asset_id,)).fetchone()
            details = {k:v for k,v in asset.items() if k not in ('asset_id','asset_description','asset_family')}
            details.update({key: rows.get(asset_id, []) for key,rows in children.items()})
            name = asset.get('asset_description') or '(unnamed asset)'
            family = asset.get('asset_family') or 'Unknown'
            store._validate_details(family, details)
            conn.execute('INSERT INTO assets (id,name,family,version,details) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,family=excluded.family,version=excluded.version,details=excluded.details', (asset_id,name,family,(old[0]+1 if old else 1),json.dumps(details,default=str,ensure_ascii=False)))
        for sheet in ('Field Map','Source Cells','Review Items'):
            prior = conn.execute('SELECT contents FROM import_reference WHERE name=?', (sheet,)).fetchone()
            previous = json.loads(prior[0]) if prior else []
            if sheet in ('Source Cells', 'Review Items'):
                # Replace evidence only for IDs explicitly in the import; keep other records.
                previous = [row for row in previous if row.get('asset_id') not in {a['asset_id'] for a in data['Assets']}]
            combined = previous + data[sheet]
            # Avoid accumulating duplicate unassigned evidence on re-import.
            unique = {json.dumps(row, sort_keys=True, default=str, ensure_ascii=False): row for row in combined}
            conn.execute('INSERT OR REPLACE INTO import_reference VALUES (?,?)', (sheet,json.dumps(list(unique.values()),default=str,ensure_ascii=False)))
    del store._previews[token]
    return {'imported': len(data['Assets']), 'backup': str(backup)}

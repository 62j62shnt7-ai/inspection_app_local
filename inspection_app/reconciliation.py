"""Read-only campaign comparison against the current master register."""
from contextlib import closing
from datetime import date, datetime
from difflib import SequenceMatcher
import re
import json
import uuid
from .backups import create_backup
from .store import serialized
from .months import validate_month
from .mutations import next_revision, record_event
import sqlite3
import openpyxl


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


from .months import parse_month as month

def inspection_type(value):
    text = str(value or '').lower()
    internal = bool(re.search(r'\binternal\b', text))
    osi = bool(re.search(r'\bosi\b|\bexternal\b', text))
    return None if internal == osi else ('Internal' if internal else 'OSI')


def reconcile_workbook(store, path):
    # Own the file handle: read-only worksheet iterators may outlive book.close().
    with open(path, 'rb') as source:
        book = openpyxl.load_workbook(source, data_only=True, read_only=True)
        try:
            sheet = book['Full Inspection Plan'] if 'Full Inspection Plan' in book else book.active
            rows = sheet.iter_rows(values_only=True)
            header = None
            for index, cells in enumerate(rows, 1):
                if index > 15: break
                labels = [str(c or '').strip().lower() for c in cells]
                if any('package' in c and 'asset' in c for c in labels) and 'item' in labels and any('planned' in c and 'date' in c for c in labels):
                    def column(predicate):
                        return next((i for i, label in enumerate(labels) if predicate(label)), None)
                    header = {'identifier': column(lambda x:'package' in x and 'asset' in x), 'description': labels.index('item'), 'category':column(lambda x:x == 'category'), 'last':column(lambda x:'last' in x and 'date' in x), 'progress':column(lambda x:'ut progress' in x), 'report':column(lambda x:'report issued' in x), 'final_remarks':column(lambda x:x == 'remarks'), 'planned':column(lambda x:'planned' in x and 'date' in x), 'scope':column(lambda x:'inspection category' in x), 'remarks':column(lambda x:'scope' in x and 'remark' in x)}
                    break
            if not header or header['scope'] is None:
                raise ValueError('Workbook must contain the old Full Inspection Plan columns: asset/package, item, planned date and inspection category.')
            with closing(sqlite3.connect(store.db_path)) as conn:
                ids = [r[0] for r in conn.execute('SELECT id FROM assets')]
            assets = [store.get_asset(i) for i in ids]
            assets = [a for a in assets if a.get('record_status') != 'Archived']
            result = []
            for row_number, cells in enumerate(rows, index + 1):
                def value(key):
                    pos = header[key]
                    return cells[pos] if pos is not None and pos < len(cells) else None
                ident, desc = str(value('identifier') or '').strip(), str(value('description') or '').strip()
                if not ident and not desc: continue
                key = normalized(ident)
                if key in ('na', 'none', 'unknown', 'null'): key = ''
                exact = []
                for a in assets:
                    for field, label in [('id','Exact asset ID'),('asset_number_original','Exact asset number'),('tag_original','Exact tag'),('pack_original','Exact package')]:
                        if key and key == normalized(a.get(field)):
                            exact.append({'id': a['id'], 'name': a['name'], 'evidence':label}); break
                if exact:
                    candidates = exact
                else:
                    needle = normalized(desc)
                    scored = []
                    if len(needle) >= 8:
                        for a in assets:
                            name = normalized(a.get('name'))
                            score = SequenceMatcher(None, needle, name).ratio() if len(name) >= 8 else 0
                            if score >= .68: scored.append((score, a))
                    candidates = [{'id':a['id'],'name':a['name'],'evidence':f'Similar description ({round(score*100)}%)'} for score,a in sorted(scored,key=lambda pair:pair[0],reverse=True)[:5]]
                result.append({'row':row_number,'identifier':ident,'description':desc,'category':str(value('category') or ''),'scope':str(value('scope') or ''),'inspection_type':inspection_type(value('scope')),'last_month':month(value('last')), 'last_original':str(value('last') or ''), 'progress':str(value('progress') or ''), 'report':str(value('report') or ''), 'final_remarks':str(value('final_remarks') or ''), 'planned_month':month(value('planned')),'planned_original':str(value('planned') or ''),'remarks':str(value('remarks') or ''),'candidates':candidates,'ambiguous':len(candidates)>1})
            if not result: raise ValueError('No plan items found in the workbook.')
            return {'sheet':sheet.title,'rows':result}
        finally:
            book.close()


@serialized
def apply_reconciliation(store, updates):
    """Apply explicitly reviewed changes together, preserving an earlier backup."""
    if not isinstance(updates, list) or not updates or len(updates) > 2000:
        raise ValueError('Select at least one change')
    allowed = {'last_inspection_month', 'next_inspection_month', 'service_status_original', 'remark'}
    grouped = {}
    for item in updates:
        if not isinstance(item, dict) or not isinstance(item.get('asset_id'), str) or not isinstance(item.get('version'), int):
            raise ValueError('Invalid reconciliation update')
        fields = item.get('fields')
        if not isinstance(fields, dict) or not fields or not set(fields) <= allowed or item.get('inspection_type') not in ('OSI', 'Internal'):
            raise ValueError('Invalid reconciliation fields or inspection type')
        for key, value in fields.items():
            if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                raise ValueError('Selected values must not be blank')
            if key.endswith('_month'): validate_month(value)
        grouped.setdefault(item['asset_id'], []).append(item)
    from .recovery import automatic_backup
    backup = automatic_backup(store, force=True)['local_path']
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        for asset_id, items in grouped.items():
            row = conn.execute('SELECT name,family,version,details FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not row or any(item['version'] != row[2] for item in items):
                raise ValueError('Master record changed since review. Reload and review again.')
            name, family, version, raw = row
            details = json.loads(raw)
            if details.get('record_status') == 'Archived': raise ValueError('Archived assets cannot be updated')
            used = set()
            for item in items:
                kind, fields = item['inspection_type'], item['fields']
                if kind == 'Internal' and not re.search(r'tank|vessel', family, re.I):
                    raise ValueError('Internal inspections are limited to tanks and vessels')
                for key in fields:
                    identity = (kind if key.endswith('_month') else 'asset', key)
                    if identity in used: raise ValueError('Conflicting changes for the same field')
                    used.add(identity)
                if any(key.endswith('_month') for key in fields):
                    inspection = next((i for i in details.get('inspections', []) if i.get('inspection_type') == kind), None)
                    if not inspection or inspection.get('applicable') != 'Yes':
                        raise ValueError('An applicable master inspection is required before updating its dates')
                    for key in ('last_inspection_month', 'next_inspection_month'):
                        if key in fields: inspection[key] = fields[key]
                if 'service_status_original' in fields: details['service_status_original'] = fields['service_status_original']
                if 'remark' in fields:
                    details.setdefault('notes', []).append({'note_id':str(uuid.uuid4()),'asset_id':asset_id,'note_type':'Remark','note_text':fields['remark']})
            store._validate_details(family, details)
            revision = next_revision(conn)
            record_event(conn, asset_id, {'name': name, 'family': family, **json.loads(raw)}, {'name': name, 'family': family, **details}, 'reconciliation', revision)
            conn.execute('UPDATE assets SET details=?, version=? WHERE id=?', (json.dumps(details,ensure_ascii=False), revision, asset_id))
    if hasattr(store, '_previews'): store._previews.clear()
    return {'updated':len(grouped), 'backup':str(backup)}

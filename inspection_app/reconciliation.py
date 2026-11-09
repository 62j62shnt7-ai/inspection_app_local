"""Preview completed inspection batches and update existing master records."""
from contextlib import closing
from datetime import date, datetime
from difflib import SequenceMatcher
import re
import json
import uuid
import unicodedata
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


def completion_status(evidence):
    """Require explicit, consistent completion evidence, never report issuance."""
    states = []
    for entry in evidence:
        label = str(entry.get('column') or '').strip().lower()
        if label not in ('status', 'ut status', 'inspection status', 'completion status', 'ut completion status', 'progress', 'ut progress', 'done', 'completed', 'ut completed', 'inspection completed'):
            continue
        text = str(entry.get('value') or '').strip().lower()
        if not text:
            continue
        dedicated = label in ('done', 'completed', 'ut completed', 'inspection completed')
        if text in ('done', 'completed', 'complete', 'finished', '100%', '100') or (dedicated and text in ('yes', 'true')):
            states.append('done')
        elif text in ('not done', 'not completed', 'incomplete', 'pending', 'not started', 'in progress', 'ongoing', 'no', 'false', '0', '0%'):
            states.append('not_done')
        else:
            states.append('unknown')
    if 'not_done' in states:
        return 'not_done'
    return 'done' if states and all(state == 'done' for state in states) else 'unknown'


def remark_present(text, notes):
    """Match complete retained paragraphs, never arbitrary text substrings."""
    def normalize(value):
        value = ' '.join(unicodedata.normalize('NFC', value).split()).casefold()
        return re.sub(r'(?<!\.)\.$', '', value)
    target = normalize(text)
    blocks = [normalize(block) for note in notes for block in re.split(r'\n\s*\n', note) if block.strip()]
    for start in range(len(blocks)):
        combined = ''
        for block in blocks[start:]:
            combined += (' ' if combined else '') + block
            if combined == target:
                return True
            if not target.startswith(combined + ' '):
                break
    return False


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
                def column(predicate):
                    return next((i for i, label in enumerate(labels) if predicate(label)), None)
                identifier = column(lambda x: x in ('asset id', 'asset number', 'asset#', 'tag', 'tag number', 'package', 'package number') or ('package' in x and 'asset' in x))
                scope = column(lambda x: x in ('inspection type', 'scope') or 'inspection category' in x)
                last = column(lambda x: ('date' in x or 'month' in x) and ('last' in x or 'actual' in x or 'completion' in x or 'completed' in x or x in ('ut date', 'inspection date')))
                actual = column(lambda x: ('date' in x or 'month' in x) and any(word in x for word in ('actual', 'completion', 'completed')) and not any(word in x for word in ('planned', 'next', 'due')))
                if actual is not None:
                    last = actual
                planned = column(lambda x: 'planned' in x and ('date' in x or 'month' in x))
                next_due = column(lambda x: ('next' in x or 'due' in x) and ('date' in x or 'month' in x) and 'planned' not in x)
                if identifier is not None and scope is not None and any(v is not None for v in (last, planned, next_due)):
                    completion_columns = [i for i, label in enumerate(labels) if label in ('status', 'ut status', 'inspection status', 'completion status', 'ut completion status', 'progress', 'ut progress', 'done', 'completed', 'ut completed', 'inspection completed')]
                    header = {'identifier':identifier, 'description':column(lambda x:x in ('item', 'description', 'asset name', 'name')), 'category':column(lambda x:x == 'category'), 'last':last, 'next':next_due, 'service':column(lambda x:x in ('service status','original service status')), 'progress':column(lambda x:'ut progress' in x or x == 'progress'), 'report':column(lambda x:'report issued' in x), 'final_remarks':column(lambda x:x == 'remarks'), 'planned':planned, 'scope':scope, 'remarks':column(lambda x:'scope' in x and 'remark' in x)}
                    break
            if not header:
                raise ValueError('Workbook needs an asset ID, number, tag or package; an inspection type (OSI or Internal); and an actual/last inspection date, next due date or planned date.')
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
                    exact_names = [a for score, a in scored if score == 1]
                    candidates = ([{'id':a['id'],'name':a['name'],'evidence':'Exact description'} for a in exact_names] if exact_names else [{'id':a['id'],'name':a['name'],'evidence':f'Similar description ({round(score*100)}%)'} for score,a in sorted(scored,key=lambda pair:pair[0],reverse=True)[:5]])
                kind = inspection_type(value('scope'))
                kind_source = 'Workbook scope' if kind else None
                if kind is None and not re.search(r'\b(?:osi|external|internal)\b', str(value('scope') or ''), re.I) and len(candidates) == 1 and candidates[0]['evidence'].startswith('Exact'):
                    matched = next(a for a in assets if a['id'] == candidates[0]['id'])
                    kinds = {i.get('inspection_type') for i in matched.get('inspections', []) if str(i.get('applicable')).lower() == 'yes' and i.get('inspection_type') in ('OSI', 'Internal')}
                    if len(kinds) == 1:
                        kind = kinds.pop()
                        kind_source = 'Only applicable inspection in matched master asset'
                if len(candidates) == 1 and candidates[0]['evidence'].startswith('Exact'):
                    matched = next(a for a in assets if a['id'] == candidates[0]['id'])
                    if re.search(r'\b(?:pip(?:e|es|ing)|flow\s*lines?|trunk\s*lines?|fl|tl|gl)\b', str(matched.get('family', '')), re.I):
                        kind = 'OSI'
                        kind_source = 'OSI-only master asset family'
                last_raw = str(value('last') or '').strip()
                empty_history = actual is None and last_raw.casefold() in ('', 'none', 'never', 'na', 'n/a', 'not applicable', 'check history')
                last_kind = 'dated' if month(value('last')) else ('empty' if empty_history or not last_raw else 'invalid')
                completion_evidence = [{'column':labels[i], 'value':str(cells[i]) if cells[i] is not None else ''} for i in completion_columns if i < len(cells)]
                result.append({'completion_status':completion_status(completion_evidence), 'completion_evidence':completion_evidence, 'source_sheet':sheet.title,'row':row_number,'identifier':ident,'description':desc,'category':str(value('category') or ''),'scope':str(value('scope') or ''),'inspection_type':kind,'inspection_type_source':kind_source,'last_date_role':'actual' if actual is not None else 'historical','last_value_kind':last_kind,'last_month':month(value('last')), 'last_original':str(value('last') or ''), 'next_month':month(value('next')), 'next_original':str(value('next') or ''), 'service_status':str(value('service') or ''), 'progress':str(value('progress') or ''), 'report':str(value('report') or ''), 'final_remarks':str(value('final_remarks') or ''), 'planned_month':month(value('planned')),'planned_original':str(value('planned') or ''),'remarks':str(value('remarks') or ''),'candidates':candidates,'ambiguous':len(candidates)>1})
            if not result: raise ValueError('No plan items found in the workbook.')
            return {'sheet':sheet.title,'rows':result,'purpose':'completed-inspections'}
        finally:
            book.close()


@serialized
def apply_reconciliation(store, updates):
    """Apply explicitly reviewed changes together, preserving an earlier backup."""
    if not isinstance(updates, list) or not updates or len(updates) > 2000:
        raise ValueError('Select at least one change')
    allowed = {'last_inspection_month', 'next_inspection_month', 'service_status_original', 'remark', 'remarks'}
    grouped = {}
    for item in updates:
        if not isinstance(item, dict) or not isinstance(item.get('asset_id'), str) or not isinstance(item.get('version'), int):
            raise ValueError('Invalid reconciliation update')
        if 'source' in item and (not isinstance(item['source'], dict) or len(json.dumps(item['source'])) > 50000):
            raise ValueError('Invalid reconciliation source evidence')
        fields = item.get('fields')
        if not isinstance(fields, dict) or not fields or not set(fields) <= allowed or item.get('inspection_type') not in ('OSI', 'Internal'):
            raise ValueError('Invalid reconciliation fields or inspection type')
        for key, value in fields.items():
            if key == 'remarks':
                if not isinstance(value, list) or not value or len(value) > 100 or any(not isinstance(text, str) or not text.strip() or len(text) > 10000 for text in value):
                    raise ValueError('Invalid proposed remarks')
                continue
            if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                raise ValueError('Selected values must not be blank')
            if key.endswith('_month'): validate_month(value)
        if any(key.endswith('_month') for key in fields):
            evidence = item.get('source', {}).get('completion_evidence')
            if not isinstance(evidence, list) or not all(isinstance(entry, dict) for entry in evidence) or completion_status(evidence) != 'done':
                raise ValueError('Incoming inspection must be explicitly marked done before its dates can update the master. Preview the workbook again.')
        grouped.setdefault(item['asset_id'], []).append(item)
    from .recovery import automatic_backup
    backup = automatic_backup(store, force=True)['local_path']
    versions = {}
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
                        if key in fields:
                            current = inspection.get(key)
                            if current and fields[key] < current:
                                raise ValueError('Incoming inspection date is older than the master. Newer master dates cannot be replaced by reconciliation.')
                            inspection[key] = fields[key]
                if 'service_status_original' in fields: details['service_status_original'] = fields['service_status_original']
                remarks = fields.get('remarks', []) + ([fields['remark']] if 'remark' in fields else [])
                existing_notes = [note.get('note_text', '') for note in details.get('notes', [])]
                for text in remarks:
                    if remark_present(text, existing_notes):
                        continue
                    details.setdefault('notes', []).append({'note_id':str(uuid.uuid4()),'asset_id':asset_id,'note_type':'Remark','note_text':text})
                    existing_notes.append(text)
            if details == json.loads(raw):
                continue
            store._validate_details(family, details)
            revision = next_revision(conn)
            versions[asset_id] = revision
            record_event(conn, asset_id, {'name': name, 'family': family, **json.loads(raw)}, {'name': name, 'family': family, **details}, 'reconciliation', revision, reason=json.dumps([item['source'] for item in items if 'source' in item], ensure_ascii=False))
            conn.execute('UPDATE assets SET details=?, version=? WHERE id=?', (json.dumps(details,ensure_ascii=False), revision, asset_id))
    if hasattr(store, '_previews'): store._previews.clear()
    return {'updated':len(versions), 'versions':versions, 'backup':str(backup)}

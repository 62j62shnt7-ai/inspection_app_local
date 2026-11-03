from .import_batches import archive_source, invalidate_batches, persist_batch, load_batch
from .mutations import next_revision, record_event
from contextlib import closing
import hashlib
from copy import deepcopy
import json
import secrets
import sqlite3
from pathlib import Path
from collections import defaultdict
import openpyxl
from .months import validate_month
from .backups import create_backup
from .store import serialized
from .legacy import inspect_workbook, read_legacy
from .import_identity import DECISION_SHEET, identities, match_legacy, validate_decisions

TABLES = ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells', 'Field Map')

def _revision(store):
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        rows = conn.execute('SELECT id,name,family,version,details FROM assets ORDER BY id').fetchall()
        clock = conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
    return hashlib.sha256(json.dumps([clock,rows], ensure_ascii=False).encode()).hexdigest()

def read_workbook(path):
    # Own the file handle: read-only worksheet iterators may outlive book.close().
    with open(path, 'rb') as source:
        workbook = openpyxl.load_workbook(source, data_only=True, read_only=True)
        try:
            result = {}
            for name in TABLES + ((DECISION_SHEET,) if DECISION_SHEET in workbook.sheetnames else ()):
                if name not in workbook.sheetnames:
                    raise ValueError('Missing worksheet: ' + name)
                rows = workbook[name].iter_rows(values_only=True)
                headings = next(rows)
                if len(set(headings)) != len(headings):
                    raise ValueError('Duplicate headings in ' + name)
                result[name] = [{heading: row[index] if index < len(row) else None for index, heading in enumerate(headings)} for row in rows if any(v is not None for v in row)]
            for row in result['Source Cells']:
                if row.get('historical_asset_id') is None: row.pop('historical_asset_id',None)
            for row in result['Inspection Plan']:
                if row.get('condition_review_by') is None: row.pop('condition_review_by',None)
            if 'Long Values' in workbook.sheetnames:
                parts = defaultdict(dict)
                for sheet,row,column,part,text in workbook['Long Values'].iter_rows(min_row=2,values_only=True):
                    if sheet not in result or not isinstance(row,int) or row<2 or not isinstance(part,int) or part<0 or not isinstance(text,str):
                        raise ValueError('Invalid long-value continuation')
                    identity=(sheet,row,column)
                    if part in parts[identity]: raise ValueError('Duplicate long-value continuation')
                    parts[identity][part]=text
                for (sheet,row,column),chunks in parts.items():
                    if sorted(chunks)!=list(range(len(chunks))) or row-2>=len(result[sheet]) or column not in result[sheet][row-2]:
                        raise ValueError('Incomplete long-value continuation')
                    result[sheet][row-2][column]=''.join(chunks[i] for i in range(len(chunks)))
            return result
        finally:
            workbook.close()

# Compatibility helpers retained for existing callers/tests.
_legacy_identities = identities

def _resolve_legacy_ids(store, data):
    return match_legacy(store, data)[0]


@serialized
def preview_import(store, path, selected_sheets=None):
    invalidate_batches(store)
    path = Path(path)
    info = inspect_workbook(path)
    metadata = {'format': 'cleaned', 'partial': False, 'warnings': []}
    if info['format'] == 'legacy':
        data, metadata = read_legacy(path, selected_sheets)
        raw_data = deepcopy(data)
        errors, review = match_legacy(store, data)
        metadata.update(review)
    else:
        if selected_sheets is not None:
            raise ValueError('Cleaned workbooks must import all linked tables together.')
        data = read_workbook(path)
        errors = []
        raw_data = None
    digest = archive_source(store, path)
    return _stage_preview(store, data, metadata, errors, digest, raw_data)


def _stage_preview(store, data, metadata, errors, digest, raw_data=None, resolutions=None):
    metadata = {**metadata, 'partial': metadata.get('partial', False) or bool(metadata.get('skipped_count'))}
    if metadata.get('format')=='cleaned':
        with closing(sqlite3.connect(store.db_path)) as conn:
            aliases=dict(conn.execute('SELECT retired_id,survivor_id FROM asset_aliases'))
        for rows in data.values():
            for row in rows:
                if row.get('asset_id') in aliases:row['asset_id']=aliases[row['asset_id']]
    if DECISION_SHEET in data: validate_decisions(data[DECISION_SHEET])
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
        baselines={asset_id:json.loads(raw) for asset_id,raw in conn.execute('SELECT asset_id,contents FROM source_baselines')}
    incoming_inspections = defaultdict(dict)
    for row in data['Inspection Plan']:
        incoming_inspections[row.get('asset_id')][row.get('inspection_type')] = row
    comparison_children={}
    for sheet,key in [('Technical Details','technical_details'),('Notes & Actions','notes'),('Review Items','review_items')]:
        grouped=defaultdict(list)
        for row in data[sheet]:grouped[row.get('asset_id')].append(row)
        comparison_children[key]=grouped
    comparison = []
    for asset in data['Assets']:
        asset_id = asset.get('asset_id')
        if asset_id not in old_rows:
            comparison.append({'id': asset_id, 'name': asset.get('asset_description') or '(unnamed asset)', 'status': 'new', 'changes': []})
            continue
        _, name, family, raw = old_rows[asset_id]
        details = json.loads(raw)
        pairs = [('Asset name', name, asset.get('asset_description') or '(unnamed asset)'), ('Family', family, asset.get('asset_family') or 'Unknown')]
        baseline=baselines.get(asset_id,{})
        baseline_values={'Asset name':baseline.get('asset_description'),'Family':baseline.get('asset_family')}
        baseline_inspections={row.get('inspection_type'):row for row in baseline.get('inspections',[])}
        old_inspections = {row.get('inspection_type'): row for row in details.get('inspections', [])}
        for kind in ('OSI', 'Internal'):
            before, after = old_inspections.get(kind, {}), incoming_inspections[asset_id].get(kind, {})
            fields=[('Applicable','applicable'),('Last month','last_inspection_month'),('Next month','next_inspection_month')]
            fields.extend((key.replace('_',' ').capitalize(),key) for key in sorted(set(before)|set(after)) if key not in ('applicable','last_inspection_month','next_inspection_month','inspection_id','asset_id','inspection_type'))
            for label,key in fields:
                label=kind+' '+label
                pairs.append((label,before.get(key),after.get(key)))
                baseline_values[label]=baseline_inspections.get(kind,{}).get(key)
        current_fields={**details,'name':name,'family':family}
        incoming_fields={k:v for k,v in asset.items() if k not in ('asset_id','asset_description','asset_family')}
        for sheet,key in [('Technical Details','technical_details'),('Notes & Actions','notes'),('Review Items','review_items')]:
            incoming_fields[key]=comparison_children[key].get(asset_id,[])
        for key in sorted(set(current_fields)|set(incoming_fields)):
            if key in ('name','family','inspections','source_cells'):continue
            before,after=current_fields.get(key),incoming_fields.get(key)
            if isinstance(before,(dict,list)) or isinstance(after,(dict,list)):
                before=json.dumps(before,ensure_ascii=False,sort_keys=True,default=str)
                after=json.dumps(after,ensure_ascii=False,sort_keys=True,default=str)
            label=key.replace('_',' ').capitalize()
            previous=baseline.get(key)
            baseline_values[label]=json.dumps(previous,ensure_ascii=False,sort_keys=True,default=str) if isinstance(previous,(dict,list)) else previous
            pairs.append((label,before,after))
        changes = [{'field': label, 'current': str(old or ''), 'incoming': str(new or ''),'previous_source':str(baseline_values[label] or '') if baseline and label in baseline_values else None} for label, old, new in pairs if (old or '') != (new or '')]
        comparison.append({'id': asset_id, 'name': name, 'status': 'changed' if changes else 'matching', 'changes': changes})
    token = secrets.token_urlsafe(24)
    if not hasattr(store, '_previews'): store._previews = {}
    # One preview is actionable at a time; tab changes/re-previews cannot revive
    # an older staged selection. Bound memory for source-cell evidence as well.
    store._previews.clear()
    store._previews[token] = {'data': data, 'revision': _revision(store), 'digest': digest, 'errors': errors, 'raw_data': raw_data, 'resolutions': resolutions or {}, **metadata}
    persist_batch(store, token, store._previews[token])
    return {'token': token, 'digest': digest, 'counts': {k:len(v) for k,v in data.items()}, 'additions':len(existing-old_ids), 'updates':len(existing & old_ids), 'retained':len(old_ids-existing), 'errors':list(dict.fromkeys(errors)), 'comparison':comparison, **metadata}

@serialized
def resolve_import(store, token, resolutions):
    staged = load_batch(store, token)
    if not staged or staged.get('raw_data') is None or staged['revision'] != _revision(store):
        raise ValueError('Import preview is invalid or stale. Preview the workbook again.')
    if not isinstance(resolutions, list) or len(resolutions) > 10000:
        raise ValueError('Invalid duplicate resolutions')
    allowed = {row['row_key'] for row in staged.get('conflicts', [])}
    decisions, seen = dict(staged.get('resolutions', {})), set()
    for item in resolutions:
        if not isinstance(item, dict) or set(item) - {'row_key', 'action', 'asset_id'}:
            raise ValueError('Invalid duplicate resolution fields')
        key = item.get('row_key')
        if not isinstance(key, str) or key not in allowed or key in seen:
            raise ValueError('Unknown or duplicate conflict row')
        action = item.get('action')
        if action not in ('review', 'separate', 'skip', 'match'):
            raise ValueError('Invalid duplicate resolution action')
        if action == 'match':
            if not isinstance(item.get('asset_id'), str) or not item['asset_id']:
                raise ValueError('Choose an existing asset to update')
        elif item.get('asset_id'):
            raise ValueError('Only an existing match can specify an asset ID')
        seen.add(key); decisions[key] = item
    data = deepcopy(staged['raw_data'])
    errors, review = match_legacy(store, data, decisions)
    metadata = {key: staged[key] for key in ('format', 'included_sheets', 'excluded_sheets', 'sheet_summary', 'warnings')}
    metadata['partial'] = bool(metadata['excluded_sheets'])
    metadata.update(review)
    return _stage_preview(store, data, metadata, errors, staged['digest'], staged['raw_data'], decisions)


@serialized
def apply_import(store, token, mode='merge', acknowledge_coverage=False):
    if mode not in ('merge', 'replace'): raise ValueError('Invalid import mode')
    staged = load_batch(store, token)
    if not staged or staged['errors'] or staged['revision'] != _revision(store):
        raise ValueError('Import preview is invalid, has errors, or is stale')
    if mode == 'replace' and staged.get('partial'):
        raise ValueError('Cannot replace with a partial import: excluded tabs must retain their existing records. Use merge.')
    if any(sheet.get('unclassified_rows') for sheet in staged.get('sheet_summary',[])) and acknowledge_coverage is not True:
        raise ValueError('Review extraction coverage and explicitly acknowledge rows not classified as assets')
    data = staged['data']
    if mode == 'replace' and not data['Assets']: raise ValueError('Cannot replace the database with an empty workbook')
    children = {}
    for sheet, key in [('Inspection Plan','inspections'), ('Technical Details','technical_details'), ('Notes & Actions','notes'), ('Review Items','review_items'), ('Source Cells','source_cells')]:
        grouped = defaultdict(list)
        for row in data[sheet]: grouped[row.get('asset_id')].append(row)
        children[key] = grouped
    from .recovery import automatic_backup
    backup = automatic_backup(store, force=True)['local_path']
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute('SELECT id,name,family,version,details FROM assets ORDER BY id').fetchall()
        clock=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        revision = hashlib.sha256(json.dumps([clock,rows], ensure_ascii=False).encode()).hexdigest()
        if revision != staged['revision']:
            raise ValueError('Import preview is stale')
        conn.execute('CREATE TABLE IF NOT EXISTS import_reference (name TEXT PRIMARY KEY, contents TEXT NOT NULL)')
        if mode == 'replace':
            incoming_ids = {asset['asset_id'] for asset in data['Assets']}
            for asset_id,name,family,version,raw in rows:
                if asset_id not in incoming_ids:
                    revision=next_revision(conn)
                    record_event(conn,asset_id,{'name':name,'family':family,**json.loads(raw)},None,'import',revision)
                    conn.execute('DELETE FROM assets WHERE id=?',(asset_id,))
            conn.execute('DELETE FROM import_reference')
        for asset in data['Assets']:
            asset_id = asset['asset_id']
            old = conn.execute('SELECT name,family,details FROM assets WHERE id=?', (asset_id,)).fetchone()
            source_view={**asset,**{key:rows.get(asset_id,[]) for key,rows in children.items() if key!='source_cells'}}
            conn.execute('INSERT OR REPLACE INTO source_baselines VALUES (?,?)',(asset_id,json.dumps(source_view,default=str,ensure_ascii=False)))
            details = {k:v for k,v in asset.items() if k not in ('asset_id','asset_description','asset_family')}
            details.update({key: rows.get(asset_id, []) for key,rows in children.items()})
            name = asset.get('asset_description') or '(unnamed asset)'
            family = asset.get('asset_family') or 'Unknown'
            if old:
                old_details=json.loads(old[2])
                for key,identifier in [('inspections','inspection_type'),('notes','note_id'),('technical_details','field_id'),('review_items','review_id')]:
                    existing_keys={r.get(identifier) for r in details.get(key,[]) if r.get(identifier)}
                    for retained in old_details.get(key,[]):
                        if (retained.get(identifier) and retained[identifier] not in existing_keys) or (not retained.get(identifier) and retained not in details.get(key,[])):
                            details.setdefault(key,[]).append(retained)
                from .quality import protect_verified_fields
                protected = protect_verified_fields(conn, {'id':asset_id,'name':old[0],'family':old[1],**json.loads(old[2])}, {'id':asset_id,'name':name,'family':family,**details})
                name, family = protected.pop('name'), protected.pop('family')
                protected.pop('id',None)
                details = protected
            store._validate_details(family, details)
            revision = next_revision(conn)
            record_event(conn, asset_id, {'name': old[0], 'family': old[1], **json.loads(old[2])} if old else None, {'name': name, 'family': family, **details}, 'import', revision)
            conn.execute('INSERT INTO assets (id,name,family,version,details) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,family=excluded.family,version=excluded.version,details=excluded.details', (asset_id,name,family,revision,json.dumps(details,default=str,ensure_ascii=False)))
        for sheet in ('Field Map','Source Cells','Review Items') + ((DECISION_SHEET,) if DECISION_SHEET in data else ()):
            prior = conn.execute('SELECT contents FROM import_reference WHERE name=?', (sheet,)).fetchone()
            previous = json.loads(prior[0]) if prior else []
            if staged.get('format') == 'legacy':
                # Replace unassigned evidence only for selected tabs; excluded
                # tabs and evidence belonging to retained assets stay intact.
                selected = set(staged['included_sheets'])
                incoming_ids = {a['asset_id'] for a in data['Assets']}
                previous = [r for r in previous if not (r.get('source_sheet') in selected and (sheet == 'Field Map' or (sheet != DECISION_SHEET and (not r.get('asset_id') or r.get('asset_id') in incoming_ids))))]
            if sheet in ('Source Cells', 'Review Items'):
                # Replace evidence only for IDs explicitly in the import; keep other records.
                previous = [row for row in previous if row.get('asset_id') not in {a['asset_id'] for a in data['Assets']}]
            if sheet == DECISION_SHEET:
                incoming_keys = {r['row_key'] for r in data[sheet]}
                previous = [r for r in previous if r['row_key'] not in incoming_keys]
            combined = previous + data[sheet]
            # Avoid accumulating duplicate unassigned evidence on re-import.
            unique = {json.dumps(row, sort_keys=True, default=str, ensure_ascii=False): row for row in combined}
            conn.execute('INSERT OR REPLACE INTO import_reference VALUES (?,?)', (sheet,json.dumps(list(unique.values()),default=str,ensure_ascii=False)))
        conn.executemany('INSERT OR IGNORE INTO import_batch_assets VALUES (?,?)',[(token,a['asset_id']) for a in data['Assets']])
        staged['coverage_acknowledged']=acknowledge_coverage is True
        conn.execute("UPDATE import_batches SET state='committed',contents=? WHERE token=?", (json.dumps(staged,default=str,ensure_ascii=False),token))
    getattr(store, '_previews', {}).pop(token, None)
    return {'imported': len(data['Assets']), 'backup': str(backup)}


@serialized
def resume_import(store,token):
    staged=load_batch(store,token)
    if not staged or staged['revision']!=_revision(store):raise ValueError('Staged import is stale. Preview the source workbook again.')
    keys=('format','included_sheets','excluded_sheets','sheet_summary','warnings','partial','conflicts','unresolved_count','skipped_count','remembered_count')
    metadata={key:staged[key] for key in keys if key in staged}
    return _stage_preview(store,staged['data'],metadata,staged['errors'],staged['digest'],staged.get('raw_data'),staged.get('resolutions'))

"""Explicit duplicate consolidation; aliases retain retired permanent identities."""
from contextlib import closing
import copy
import json
import sqlite3
import uuid
from .store import serialized
from .mutations import next_revision,record_event
from .validation import fingerprint

COLLECTIONS={'inspections':'inspection_type','notes':'note_id','technical_details':'field_id','review_items':'review_id','source_cells':None}


def _merge_proposal(survivor,duplicate):
    merged=copy.deepcopy(survivor);conflicts=[]
    for key in sorted((set(survivor)|set(duplicate))-{'id','version'}-set(COLLECTIONS)):
        before,after=survivor.get(key),duplicate.get(key)
        if before==after or after is None or after=='':continue
        if before is None or before=='':merged[key]=after
        else:conflicts.append({'field':key,'survivor':before,'duplicate':after})
    for collection,identifier in COLLECTIONS.items():
        rows=merged.setdefault(collection,[])
        for incoming in duplicate.get(collection,[]):
            incoming=dict(incoming)
            if collection=='source_cells' and not incoming.get('historical_asset_id'):
                incoming['historical_asset_id']=incoming.get('asset_id') or duplicate['id']
            incoming={**incoming,'asset_id':survivor['id']}
            prior=next((r for r in rows if identifier and r.get(identifier) and r.get(identifier)==incoming.get(identifier)),None)
            if prior is not None:
                left={k:v for k,v in prior.items() if k!='asset_id'};right={k:v for k,v in incoming.items() if k!='asset_id'}
                if left!=right:conflicts.append({'field':collection+'.'+str(incoming[identifier]),'survivor':prior,'duplicate':incoming})
            elif fingerprint({k:v for k,v in incoming.items() if k!='asset_id'}) not in {fingerprint({k:v for k,v in r.items() if k!='asset_id'}) for r in rows}:
                rows.append(incoming)
    return merged,conflicts


@serialized
def preview_consolidation(store,survivor_id,duplicate_id):
    if survivor_id==duplicate_id:raise ValueError('Choose two different assets')
    survivor,duplicate=store.get_asset(survivor_id),store.get_asset(duplicate_id)
    if survivor['id']==duplicate['id']:raise ValueError('These IDs already refer to the same asset')
    merged,conflicts=_merge_proposal(survivor,duplicate)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        result={'preview_id':str(uuid.uuid4()),'survivor':survivor,'duplicate':duplicate,'merged':merged,'conflicts':conflicts,'revision':conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]}
        conn.execute('INSERT INTO consolidation_previews(preview_id,contents) VALUES (?,?)',(result['preview_id'],json.dumps(result,ensure_ascii=False)))
    return result


@serialized
def apply_consolidation(store,preview_id,expected_revision,choices,evidence):
    if not isinstance(evidence,str) or not evidence.strip():raise ValueError('Record evidence confirming these are the same equipment')
    from .recovery import automatic_backup
    backup=automatic_backup(store,force=True)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]!=expected_revision:raise ValueError('Master changed. Review again.')
        row=conn.execute('SELECT contents FROM consolidation_previews WHERE preview_id=?',(preview_id,)).fetchone()
        if not row:raise ValueError('Consolidation preview is unavailable')
        proposal=json.loads(row[0]);survivor=proposal['survivor'];duplicate=proposal['duplicate'];merged=proposal['merged']
        if proposal['revision']!=expected_revision:raise ValueError('Consolidation preview is stale')
        fields={c['field'] for c in proposal['conflicts']}
        if not isinstance(choices,dict) or set(choices)!=fields or any(v not in ('survivor','duplicate') for v in choices.values()):raise ValueError('Review every conflict and choose its value')
        for conflict in proposal['conflicts']:
            if choices[conflict['field']]=='survivor':continue
            field=conflict['field']
            if '.' in field and field.split('.',1)[0] in COLLECTIONS:
                collection,key=field.split('.',1);identifier=COLLECTIONS[collection]
                merged[collection]=[conflict['duplicate'] if str(r.get(identifier))==key else r for r in merged[collection]]
            else:merged[field]=conflict['duplicate']
        details={k:v for k,v in merged.items() if k not in ('id','name','family','version')}
        for rows in (details.get(k,[]) for k in COLLECTIONS):
            for item in rows:item['asset_id']=survivor['id']
        store._validate_details(merged['family'],details)
        revision=next_revision(conn)
        conn.execute('UPDATE assets SET name=?,family=?,details=?,version=? WHERE id=?',(merged['name'],merged['family'],json.dumps(details,ensure_ascii=False),revision,survivor['id']))
        record_event(conn,survivor['id'],survivor,{**merged,**details},'consolidation',revision,reason=evidence)
        record_event(conn,duplicate['id'],duplicate,None,'consolidation',revision,reason=evidence)
        conn.execute('DELETE FROM assets WHERE id=?',(duplicate['id'],))
        conn.execute('UPDATE asset_aliases SET survivor_id=? WHERE survivor_id=?',(survivor['id'],duplicate['id']))
        conn.execute('INSERT INTO asset_aliases(retired_id,survivor_id,evidence) VALUES (?,?,?)',(duplicate['id'],survivor['id'],evidence))
        # Relink retained unassigned evidence without discarding prior source decisions.
        has_ref=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_reference'").fetchone()
        if has_ref:
            for name,raw in conn.execute('SELECT name,contents FROM import_reference').fetchall():
                rows=json.loads(raw)
                for item in rows:
                    if item.get('asset_id')==duplicate['id']:
                        if name=='Source Cells' and not item.get('historical_asset_id'):
                            item['historical_asset_id']=duplicate['id']
                        item['asset_id']=survivor['id']
                conn.execute('UPDATE import_reference SET contents=? WHERE name=?',(json.dumps(rows,ensure_ascii=False),name))
        conn.execute('DELETE FROM consolidation_previews WHERE preview_id=?',(preview_id,))
    return {'survivor_id':survivor['id'],'retired_id':duplicate['id'],'revision':revision,'backup':backup['local_path']}

"""Field verification, persistent findings and reproducible snapshot eligibility."""
from contextlib import closing
from datetime import datetime, timezone, date
import json
import sqlite3
import uuid
from .store import serialized
from .mutations import next_revision, record_event
from .validation import fingerprint, validate_record, RULES_VERSION


def verification_fields(asset):
    result = {k:v for k,v in asset.items() if k not in ('id','version','inspections','source_cells','technical_details','notes','review_items')}
    # These semantic fields make explicit identity and context confirmation possible.
    result['identity'] = {k:asset.get(k) for k in ('tag_original','asset_number_original','name','location_from','unit_or_location_to','plant','field')}
    result['context'] = {k:asset.get(k) for k in ('location_from','unit_or_location_to','plant','field','parent_group')}
    for inspection in asset.get('inspections', []):
        for key,value in inspection.items():
            if key not in ('asset_id','inspection_id'):
                result['inspections.'+inspection['inspection_type']+'.'+key] = value
    for collection,identifier in [('notes','note_id'),('technical_details','field_id')]:
        for item in asset.get(collection,[]):
            key=str(item.get(identifier) or fingerprint([item.get('field_label'),item.get('source_sheet'),item.get('source_cell')]))
            result[collection+'.'+key]=item
    return result


def field_fingerprint(asset, field):
    values = verification_fields(asset)
    value = values.get(field)
    # Applicability is an engineering decision dependent on the family.
    if field.startswith('inspections.') and field.endswith('.applicable'):
        value = [asset.get('family'), value]
    return fingerprint(value)


def current_verifications(conn, asset):
    rows = conn.execute('SELECT field, fingerprint FROM field_verifications WHERE asset_id=? AND active=1 ORDER BY verification_id', (asset['id'],))
    latest = dict(rows)
    return {key for key,value in latest.items() if field_fingerprint(asset, key)==value}


def read_assets(conn):
    return [{'id':a,'name':n,'family':f,'version':v,**json.loads(raw)} for a,n,f,v,raw in conn.execute('SELECT id,name,family,version,details FROM assets ORDER BY name COLLATE NOCASE')]


@serialized
def verify_fields(store, asset_id, expected_version, fields, evidence):
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError('Record evidence or engineering rationale before verifying')
    if not isinstance(fields, list) or not fields or any(not isinstance(f,str) for f in fields):
        raise ValueError('Choose the fields you have checked')
    from .recovery import automatic_backup
    automatic_backup(store)
    asset = store.get_asset(asset_id)
    if not isinstance(expected_version,int) or isinstance(expected_version,bool) or asset['version']!=expected_version:
        raise ValueError('Asset changed. Reload and review again.')
    if not set(fields) <= set(verification_fields(asset)):
        raise ValueError('Unknown verification field')
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT version FROM assets WHERE id=?',(asset_id,)).fetchone()[0]!=expected_version:
            raise ValueError('Asset changed. Reload and review again.')
        revision = next_revision(conn)
        for field in dict.fromkeys(fields):
            conn.execute('INSERT INTO field_verifications(asset_id,field,fingerprint,evidence,actor,verified_at,rules_version,revision) VALUES (?,?,?,?,?,?,?,?)',
                         (asset_id,field,field_fingerprint(asset,field),evidence.strip(),'Owner',datetime.now(timezone.utc).isoformat(),RULES_VERSION,revision))
        conn.execute('UPDATE assets SET version=? WHERE id=?',(revision,asset_id))
        record_event(conn, asset_id, None, {'fields':fields,'evidence':evidence}, 'verification', revision)
    return {'asset':store.get_asset(asset_id),'verified_fields':fields,'revision':revision}


def required_fields(asset):
    required = ['name','family','record_status','context','identity']
    for i in asset.get('inspections',[]):
        prefix='inspections.'+i['inspection_type']+'.'
        required.append(prefix+'applicable')
        if i.get('applicable')=='Yes':
            required.extend([prefix+'next_inspection_month'] if i.get('next_inspection_month') else [prefix+'scheduling_condition',prefix+'condition_review_by'])
    return required


def issue_fingerprint(asset, finding):
    field=finding['field']
    if field.startswith('inspections.'):
        kind=field.split('.')[1]
        inspection=next((i for i in asset.get('inspections',[]) if i.get('inspection_type')==kind),{})
        if finding['rule_id']=='chronology':
            value=[inspection.get('last_inspection_month'),inspection.get('next_inspection_month')]
        else: value=[asset.get('family'),inspection]
    elif field.startswith('source_cells.'):
        value=next((cell for cell in asset.get('source_cells',[]) if field=='source_cells.'+str(cell.get('source_cell'))),None)
    elif field=='context':value=verification_fields(asset)['context']
    elif field.startswith('review_items.'):value=next((i for i in asset.get('review_items',[]) if field=='review_items.'+str(i.get('review_id') or fingerprint(i))),None)
    elif finding['rule_id']=='incoming-difference':value=field_fingerprint(asset,field)
    elif finding['rule_id']=='identity-collision':value=[finding['value_fingerprint'],verification_fields(asset)['identity']]
    else:value=asset.get(field)
    return fingerprint([finding['rule_id'],field,value])


def invalidate_verifications(conn, asset_id, before, after):
    if before is None:return
    fields={row[0] for row in conn.execute('SELECT DISTINCT field FROM field_verifications WHERE asset_id=? AND active=1',(asset_id,))}
    old={'id':asset_id,**before}
    new={'id':asset_id,**after} if after is not None else None
    for field in fields:
        if new is None or field_fingerprint(old,field)!=field_fingerprint(new,field):
            conn.execute('UPDATE field_verifications SET active=0 WHERE asset_id=? AND field=?',(asset_id,field))
    for issue_id,rule,field,stored in conn.execute("SELECT issue_id,rule_id,field,fingerprint FROM quality_issues WHERE asset_id=? AND state IN ('resolved','accepted_exception')",(asset_id,)).fetchall():
        finding={'rule_id':rule,'field':field,'value_fingerprint':stored}
        if new is None or issue_fingerprint(old,finding)!=issue_fingerprint(new,finding):
            conn.execute("UPDATE quality_issues SET state='superseded' WHERE issue_id=?",(issue_id,))
    if new is None or verification_fields(old)['identity']!=verification_fields(new)['identity']:
        shared={(key,canonical_identifier(record.get(key))) for record in (old,new or {}) for key in ('tag_original','asset_number_original') if canonical_identifier(record.get(key))}
        for peer_id,raw in conn.execute('SELECT id,details FROM assets').fetchall():
            if peer_id==asset_id:continue
            peer=json.loads(raw)
            if any((key,canonical_identifier(peer.get(key))) in shared for key in ('tag_original','asset_number_original')):
                conn.execute("UPDATE quality_issues SET state='superseded' WHERE asset_id=? AND rule_id='identity-collision' AND state IN ('accepted_exception','resolved')",(peer_id,))


def canonical_identifier(value):
    text=str(value or '').strip().casefold()
    return '' if text in ('','n/a','na','none','null','unknown','-','—') else text


def identity_findings(assets):
    identities={}
    by_id={a['id']:a for a in assets}
    for asset in assets:
        for key in ('tag_original','asset_number_original'):
            value=canonical_identifier(asset.get(key))
            if value:identities.setdefault((key,value),set()).add(asset['id'])
    result={a['id']:[] for a in assets}
    for asset in assets:
        for key in ('tag_original','asset_number_original'):
            value=canonical_identifier(asset.get(key))
            peers=identities.get((key,value),set())
            if value and len(peers)>1:
                result[asset['id']].append({'rule_id':'identity-collision','asset_id':asset['id'],'field':key,'severity':'blocking','message':'Identifier is shared by multiple assets; review identity','value_fingerprint':fingerprint([[peer,verification_fields(by_id[peer])['identity']] for peer in sorted(peers)]),'rules_version':RULES_VERSION})
    return result


def _scan(conn, current_month):
    assets = read_assets(conn)
    findings=[]
    collisions=identity_findings(assets)
    by_id={a['id']:a for a in assets}
    from .import_batches import source_archive_problems
    archive_problems=source_archive_problems(conn)
    for asset in assets:
        found=validate_record(asset,current_month)
        for digest in archive_problems.get(asset['id'],set()):
            found.append({'rule_id':'source-archive-integrity','asset_id':asset['id'],'field':'source_archive.'+digest,'severity':'warning','message':'Original source archive is missing or damaged. Data checks can pass, but source evidence is unavailable; restore a complete recovery package.','value_fingerprint':digest,'rules_version':RULES_VERSION})
        found.extend(collisions[asset['id']])
        for finding in found:
            # Entire relevant record fingerprint ensures stale decisions reopen.
            finding['value_fingerprint']=issue_fingerprint(asset,finding)
            issue_id=fingerprint([finding['rule_id'],asset['id'],finding['field'],finding['value_fingerprint']])
            finding['issue_id']=issue_id
            conn.execute('INSERT OR IGNORE INTO quality_issues(issue_id,asset_id,rule_id,field,severity,message,fingerprint,state) VALUES (?,?,?,?,?,?,?,?)',
                         (issue_id,asset['id'],finding['rule_id'],finding['field'],finding['severity'],finding['message'],finding['value_fingerprint'],'open'))
            conn.execute("UPDATE quality_issues SET state='open',evidence=NULL,resolved_at=NULL WHERE issue_id=? AND state='superseded'",(issue_id,))
            conn.execute('UPDATE quality_issues SET severity=?,message=? WHERE issue_id=?',(finding['severity'],finding['message'],issue_id))
            findings.append(issue_id)
    # Preserve incoming conflicts until explicitly reviewed.
    existing_ids={a['id'] for a in assets}
    for issue_id,asset_id,field,expected in conn.execute("SELECT issue_id,asset_id,field,expected_fingerprint FROM quality_issues WHERE rule_id='incoming-difference' AND state='open'"):
        if asset_id in existing_ids and (expected is None or field_fingerprint(by_id[asset_id],field)==expected): findings.append(issue_id)
    active=set(findings)
    for issue_id,state in conn.execute('SELECT issue_id,state FROM quality_issues').fetchall():
        if issue_id not in active and state in ('open','accepted_exception','resolved'): conn.execute("UPDATE quality_issues SET state='superseded' WHERE issue_id=?",(issue_id,))
    issues=[]
    for row in conn.execute('SELECT issue_id,asset_id,rule_id,field,severity,message,state FROM quality_issues ORDER BY severity,asset_id,rule_id'):
        if row[0] in active:
            issues.append(dict(zip(('issue_id','asset_id','rule_id','field','severity','message','state'),row)))
    return assets,issues


@serialized
def scan_quality(store, current_month=None):
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        assets,issues=_scan(conn,current_month or date.today().strftime('%Y-%m'))
        return {'issues':issues,'issue_count':len([i for i in issues if i['state']=='open']), 'affected_assets':len({i['asset_id'] for i in issues if i['state']=='open'}),'asset_count':len(assets),'revision':conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0], 'rules_version':RULES_VERSION}


@serialized
def assess_readiness(store, current_month=None):
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        assets,issues=_scan(conn,current_month or date.today().strftime('%Y-%m'))
        return _readiness_from_scan(conn,assets,issues)


def _readiness_from_scan(conn, assets, issues):
    eligible=[];excluded=[];warnings=[]
    by_asset={}
    for issue in issues: by_asset.setdefault(issue['asset_id'],[]).append(issue)
    for asset in assets:
        reasons=[i['message'] for i in by_asset.get(asset['id'],[]) if i['severity']=='blocking' and i['state']=='open']
        if reasons: excluded.append({'asset_id':asset['id'],'name':asset['name'],'reasons':list(dict.fromkeys(reasons))})
        else: eligible.append(asset['id'])
    warnings=[i for i in issues if i['severity']=='warning' and i['state']=='open']
    return {'eligible':eligible,'excluded':excluded,'warnings':warnings,'eligibility_basis':'automatic_quality_checks','asset_count':len(assets),'revision':conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0],'rules_version':RULES_VERSION}


@serialized
def asset_verification(store, asset_id):
    asset=store.get_asset(asset_id)
    with closing(sqlite3.connect(store.db_path)) as conn:
        verified=current_verifications(conn,asset)
        history=[dict(zip(('source_asset_id','field','evidence','actor','verified_at','active'),row)) for row in conn.execute('SELECT asset_id,field,evidence,actor,verified_at,active FROM field_verifications WHERE asset_id=? OR asset_id IN (SELECT retired_id FROM asset_aliases WHERE survivor_id=?) ORDER BY verification_id DESC LIMIT 100',(asset['id'],asset['id']))]
        return {'asset_id':asset['id'],'version':asset['version'],'history':history,'source':{'sheet':asset.get('source_sheet'),'row':asset.get('source_row')},'fields':[{'field':k,'value':v,'verified':k in verified,'required':k in required_fields(asset)} for k,v in verification_fields(asset).items()]}


def protect_verified_fields(conn, current, incoming):
    """Preserve verified master fields; record every incoming difference."""
    verified=current_verifications(conn,current)
    populated_blanks=set()
    current_values,incoming_values=verification_fields(current),verification_fields(incoming)
    for field,before in current_values.items():
        if field in ('identity','context') or isinstance(before,(dict,list)) or before is None or before=='':continue
        after=incoming_values.get(field)
        if after is None or after=='' or (field=='name' and after=='(unnamed asset)') or (field=='family' and after=='Unknown'):populated_blanks.add(field)
    for composite in ('identity','context'):
        if composite in verified: verified.update(verification_fields(current)[composite])
    for field in sorted(verified|populated_blanks):
        if field in ('identity','context'): continue
        before=verification_fields(current).get(field)
        after=verification_fields(incoming).get(field)
        if before==after: continue
        if field.startswith(('notes.','technical_details.')):
            collection,key=field.split('.',1)
            identifier='note_id' if collection=='notes' else 'field_id'
            rows=incoming.setdefault(collection,[])
            index=next((n for n,item in enumerate(rows) if str(item.get(identifier) or fingerprint([item.get('field_label'),item.get('source_sheet'),item.get('source_cell')]))==key),None)
            if index is None: rows.append(before)
            else: rows[index]=before
        elif field.startswith('inspections.'):
            _,kind,key=field.split('.',2)
            row=next((i for i in incoming.get('inspections',[]) if i.get('inspection_type')==kind),None)
            if row is None:
                old=next(i for i in current['inspections'] if i['inspection_type']==kind)
                incoming.setdefault('inspections',[]).append(dict(old))
            else: row[key]=before
        else: incoming[field]=before
        issue_id=fingerprint(['incoming-difference',current['id'],field,before,after])
        severity='blocking' if field in verified else 'warning'
        message='Incoming '+field+(' differs from verified master; retained verified value. Incoming: ' if field in verified else ' is blank; retained populated master value. Incoming: ')+json.dumps(after,ensure_ascii=False)
        conn.execute('INSERT OR IGNORE INTO quality_issues(issue_id,asset_id,rule_id,field,severity,message,fingerprint,state,expected_fingerprint) VALUES (?,?,?,?,?,?,?,?,?)',
                     (issue_id,current['id'],'incoming-difference',field,severity,message,fingerprint([before,after]),'open',field_fingerprint(current,field)))
        conn.execute("UPDATE quality_issues SET state='open',evidence=NULL,resolved_at=NULL WHERE issue_id=? AND state='superseded'",(issue_id,))
    return incoming


@serialized
def resolve_issue(store, issue_id, expected_revision, disposition, evidence):
    if not isinstance(evidence,str) or not evidence.strip():
        raise ValueError('Record evidence or engineering rationale')
    if disposition not in ('accepted_exception','resolved'):
        raise ValueError('Choose a supported review disposition')
    from .recovery import automatic_backup
    automatic_backup(store)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        revision=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        if revision!=expected_revision:
            raise ValueError('Master changed. Reload and review again.')
        _,issues=_scan(conn,date.today().strftime('%Y-%m'))
        issue=next((i for i in issues if i['issue_id']==issue_id and i['state']=='open'),None)
        if not issue: raise ValueError('Issue changed or is no longer open')
        allowed=('chronology','source-review','source-review-item','incoming-difference','identity-collision')
        if issue['rule_id']=='identity-collision':
            asset=next(a for a in read_assets(conn) if a['id']==issue['asset_id'])
            if 'identity' not in current_verifications(conn,asset):raise ValueError('Verify equipment identity before accepting distinct equipment with a shared identifier')
        if issue['rule_id'] not in allowed:
            raise ValueError('Correct the underlying value before resolving this blocking issue')
        if disposition=='resolved' and issue['rule_id']!='incoming-difference':
            raise ValueError('Correct the value or explicitly accept an evidenced exception')
        revision=next_revision(conn)
        conn.execute('UPDATE quality_issues SET state=?,evidence=?,resolved_at=? WHERE issue_id=?',
                     (disposition,evidence.strip(),datetime.now(timezone.utc).isoformat(),issue_id))
        record_event(conn,issue['asset_id'],issue,{'state':disposition,'evidence':evidence},'issue-resolution',revision)
    return scan_quality(store)


@serialized
def publish_snapshot(store, expected_revision, name):
    if not isinstance(name,str) or not name.strip(): raise ValueError('Give this snapshot a name')
    from .recovery import automatic_backup
    automatic_backup(store)
    report=assess_readiness(store)
    if expected_revision!=report['revision']: raise ValueError('Master changed. Assess readiness again.')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]!=expected_revision:
            raise ValueError('Master changed. Assess readiness again.')
        assets=read_assets(conn)
        manifest={**report,'snapshot_id':str(uuid.uuid4()),'name':name.strip(),'created_at':datetime.now(timezone.utc).isoformat(),
                  'assets':[a for a in assets if a['id'] in set(report['eligible'])],
                  'exceptions':[dict(zip(('issue_id','asset_id','rule_id','evidence'),row)) for row in conn.execute("SELECT issue_id,asset_id,rule_id,evidence FROM quality_issues WHERE state='accepted_exception'")],
                  'source_batches':[{'token':t,'digest':d} for t,d in conn.execute("SELECT token,digest FROM import_batches WHERE state='committed'")]}
        conn.execute('INSERT INTO master_snapshots(snapshot_id,contents) VALUES (?,?)',(manifest['snapshot_id'],json.dumps(manifest,ensure_ascii=False)))
    return manifest


@serialized
def preview_bulk_verification(store, asset_ids):
    if not isinstance(asset_ids,list) or not asset_ids or len(asset_ids)>10000 or any(not isinstance(item,str) or not item for item in asset_ids) or len(set(asset_ids))!=len(asset_ids):
        if isinstance(asset_ids,list) and len(asset_ids)>10000:
            raise ValueError('Select up to 10,000 distinct asset IDs explicitly')
        raise ValueError('Select distinct asset IDs explicitly')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        revision=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        assets=read_assets(conn)
        by_id={asset['id']:asset for asset in assets}
        if any(asset_id not in by_id for asset_id in asset_ids):raise ValueError('A selected asset no longer exists')
        _,issues=_scan(conn,date.today().strftime('%Y-%m'))
        blockers={}
        for issue in issues:
            if issue['severity']=='blocking' and issue['state']=='open':
                blockers.setdefault(issue['asset_id'],[]).append(issue['message'])
        preview_assets=[]
        for asset_id in asset_ids:
            asset=by_id[asset_id]
            values=verification_fields(asset)
            preview_assets.append({'id':asset_id,'name':asset['name'],'version':asset['version'],
                'source':{'sheet':asset.get('source_sheet'),'row':asset.get('source_row')},
                'required_fields':[{'field':field,'value':values.get(field)} for field in required_fields(asset)],
                'blockers':blockers.get(asset_id,[])})
        preview={'kind':'verification','preview_id':str(uuid.uuid4()),'revision':revision,
                 'asset_count':len(preview_assets),'assets':preview_assets}
        conn.execute('INSERT INTO bulk_operations(operation_id,state,contents) VALUES (?,?,?)',
                     (preview['preview_id'],'preview',json.dumps(preview,ensure_ascii=False)))
    return preview


@serialized
def apply_bulk_verification(store,preview_id,expected_revision,evidence):
    if not isinstance(evidence,str) or not evidence.strip():raise ValueError('Record an evidence reference or engineering rationale')
    if not isinstance(preview_id,str) or not preview_id:raise ValueError('Refresh the bulk verification preview')
    from .recovery import automatic_backup
    backup=automatic_backup(store,force=True)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        current_revision=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        if current_revision!=expected_revision:raise ValueError('Master changed. Review a new preview.')
        row=conn.execute("SELECT contents FROM bulk_operations WHERE operation_id=? AND state='preview'",(preview_id,)).fetchone()
        if not row:raise ValueError('Bulk verification preview is no longer available')
        preview=json.loads(row[0])
        if preview.get('kind')!='verification' or preview['revision']!=expected_revision:raise ValueError('Bulk verification preview is stale')
        selected=preview['assets']
        current={asset['id']:asset for asset in read_assets(conn)}
        if any(item['id'] not in current or current[item['id']]['version']!=item['version'] for item in selected):
            raise ValueError('A selected asset changed. Review a new preview.')
        checked_at=datetime.now(timezone.utc).isoformat()
        verified_field_count=0
        for item in selected:
            asset=current[item['id']]
            fields=[field['field'] for field in item['required_fields']]
            values=verification_fields(asset)
            if fields!=required_fields(asset) or any(field['value']!=values.get(field['field']) for field in item['required_fields']):
                raise ValueError('Required fields changed. Review a new preview.')
            revision=next_revision(conn)
            for field in fields:
                conn.execute('INSERT INTO field_verifications(asset_id,field,fingerprint,evidence,actor,verified_at,rules_version,revision) VALUES (?,?,?,?,?,?,?,?)',
                    (item['id'],field,field_fingerprint(asset,field),evidence.strip(),'Owner',checked_at,RULES_VERSION,revision))
            conn.execute('UPDATE assets SET version=? WHERE id=?',(revision,item['id']))
            record_event(conn,item['id'],None,{'fields':fields,'evidence':evidence.strip()},'verification',revision)
            verified_field_count+=len(fields)
        assets,issues=_scan(conn,date.today().strftime('%Y-%m'))
        readiness=_readiness_from_scan(conn,assets,issues)
        excluded_ids={item['asset_id'] for item in readiness['excluded']}
        selected_ids={item['id'] for item in selected}
        result={'verified_asset_count':len(selected),'verified_field_count':verified_field_count,
                'still_excluded_count':len(selected_ids&excluded_ids),
                'revision':conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0],
                'backup':backup['local_path']}
        conn.execute("UPDATE bulk_operations SET state='applied',contents=? WHERE operation_id=?",
                     (json.dumps({**preview,'result':result,'evidence':evidence.strip()},ensure_ascii=False),preview_id))
    return result


BULK_FIELDS={'name','family','record_status','location_from','unit_or_location_to','plant','field','tag_original','asset_number_original','service_status_original','parent_group'}


@serialized
def preview_bulk_correction(store, asset_ids, operation):
    if not isinstance(asset_ids,list) or not asset_ids or len(asset_ids)>10000 or len(set(asset_ids))!=len(asset_ids):raise ValueError('Select distinct asset IDs explicitly')
    if not isinstance(operation,dict) or operation.get('field') not in BULK_FIELDS or operation.get('operation') not in ('set','clear','trim','upper','lower'):
        raise ValueError('Unsupported bulk correction')
    if operation['operation']=='set' and not isinstance(operation.get('value'),str):raise ValueError('Enter a text value')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        revision=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
        by_id={a['id']:a for a in read_assets(conn)}
        if any(asset_id not in by_id for asset_id in asset_ids):raise ValueError('Selected asset no longer exists')
        changes=[]
        for asset_id in asset_ids:
            asset=by_id[asset_id];field=operation['field'];before=asset.get(field)
            op=operation['operation']
            after=operation.get('value') if op=='set' else None if op=='clear' else getattr(str(before or ''),{'trim':'strip','upper':'upper','lower':'lower'}[op])()
            if before!=after:changes.append({'asset_id':asset_id,'version':asset['version'],'field':field,'before':before,'after':after})
        result={'preview_id':str(uuid.uuid4()),'revision':revision,'changes':changes,'selected_count':len(asset_ids),'operation':operation}
        conn.execute('INSERT INTO bulk_operations(operation_id,state,contents) VALUES (?,?,?)',(result['preview_id'],'preview',json.dumps(result,ensure_ascii=False)))
    return result


def _write_bulk(conn,store,changes,origin,reason):
    applied=[]
    for change in changes:
        row=conn.execute('SELECT name,family,version,details FROM assets WHERE id=?',(change['asset_id'],)).fetchone()
        if not row or row[2]!=change['version']:raise ValueError('Affected asset changed. Review a new preview.')
        before={'name':row[0],'family':row[1],**json.loads(row[3])}
        after={**before,change['field']:change['after']}
        if not isinstance(after.get('name'),str) or not after['name'].strip() or not isinstance(after.get('family'),str) or not after['family'].strip():
            raise ValueError('Name and family are required')
        details={k:v for k,v in after.items() if k not in ('name','family')}
        store._validate_details(after['family'],details)
        revision=next_revision(conn)
        conn.execute('UPDATE assets SET name=?,family=?,details=?,version=? WHERE id=?',(after['name'],after['family'],json.dumps(details,ensure_ascii=False),revision,change['asset_id']))
        record_event(conn,change['asset_id'],before,after,origin,revision,reason=reason)
        applied.append({**change,'applied_version':revision})
    return applied


@serialized
def apply_bulk_correction(store,preview_id,expected_revision,reason):
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Record a reason for this bulk correction')
    from .recovery import automatic_backup
    backup=automatic_backup(store,force=True)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]!=expected_revision:raise ValueError('Master changed. Review a new preview.')
        row=conn.execute("SELECT contents FROM bulk_operations WHERE operation_id=? AND state='preview'",(preview_id,)).fetchone()
        if not row:raise ValueError('Bulk preview is no longer available')
        preview=json.loads(row[0])
        if preview['revision']!=expected_revision:raise ValueError('Bulk preview is stale')
        changes=_write_bulk(conn,store,preview['changes'],'bulk',reason)
        conn.execute("UPDATE bulk_operations SET state='applied',contents=? WHERE operation_id=?",(json.dumps({**preview,'changes':changes},ensure_ascii=False),preview_id))
    return {'operation_id':preview_id,'updated':len(changes),'backup':backup['local_path']}


@serialized
def revert_bulk_correction(store,operation_id,reason):
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Record a revert reason')
    from .recovery import automatic_backup
    automatic_backup(store,force=True)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute("SELECT contents FROM bulk_operations WHERE operation_id=? AND state='applied'",(operation_id,)).fetchone()
        if not row:raise ValueError('Applied bulk operation not found')
        operation=json.loads(row[0])
        inverse=[{**c,'version':c['applied_version'],'before':c['after'],'after':c['before']} for c in operation['changes']]
        _write_bulk(conn,store,inverse,'bulk-revert',reason)
        conn.execute("UPDATE bulk_operations SET state='reverted' WHERE operation_id=?",(operation_id,))
    return {'reverted':len(inverse),'operation_id':operation_id}


@serialized
def query_quality(store,filters):
    if not isinstance(filters,dict):raise ValueError('Invalid workbench filters')
    try:size=min(100,max(1,int(filters.get('size',50))));page=max(1,int(filters.get('page',1)))
    except (TypeError,ValueError):raise ValueError('Invalid workbench page')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        assets,issues=_scan(conn,date.today().strftime('%Y-%m'))
        quality={'issues':issues,'issue_count':sum(i['state']=='open' for i in issues),'affected_assets':len({i['asset_id'] for i in issues if i['state']=='open'}),'asset_count':len(assets),'revision':conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0],'rules_version':RULES_VERSION}
        readiness=_readiness_from_scan(conn,assets,issues)
    query=str(filters.get('search') or '').casefold();severity=filters.get('severity')
    issues=[i for i in quality['issues'] if i['state']=='open' and (not severity or i['severity']==severity) and (not query or query in ' '.join(str(i.get(k) or '') for k in ('asset_id','field','message')).casefold())]
    total=len(issues);excluded_count=len(readiness['excluded'])
    pages=max(1,(max(total,excluded_count)+size-1)//size);page=min(page,pages);start=(page-1)*size
    return {'quality':{**quality,'issues':issues[start:start+size],'filtered_issue_count':total},
            'readiness':{**readiness,'excluded':readiness['excluded'][start:start+size],'excluded_count':excluded_count,'eligible_count':len(readiness['eligible'])},
            'page':page,'pages':pages,'size':size}


@serialized
def list_snapshots(store):
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows=conn.execute("SELECT snapshot_id,json_extract(contents,'$.name'),json_extract(contents,'$.created_at'),json_extract(contents,'$.revision'),json_array_length(contents,'$.assets'),json_array_length(contents,'$.excluded') FROM master_snapshots ORDER BY rowid DESC").fetchall()
    return [dict(zip(('snapshot_id','name','created_at','revision','eligible_count','excluded_count'),row)) for row in rows]


@serialized
def get_snapshot(store,snapshot_id):
    with closing(sqlite3.connect(store.db_path)) as conn:
        row=conn.execute('SELECT contents FROM master_snapshots WHERE snapshot_id=?',(snapshot_id,)).fetchone()
    if not row:raise ValueError('Snapshot not found')
    return json.loads(row[0])

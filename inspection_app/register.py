"""Paginated summary views; detailed evidence is loaded by asset ID on demand."""
from contextlib import closing
from datetime import date
import json
import re
import sqlite3
from .store import serialized
from .months import validate_month


def read_summaries(conn):
    rows=conn.execute("SELECT id,name,family,version,json_remove(details,'$.source_cells','$.technical_details') FROM assets ORDER BY name COLLATE NOCASE")
    assets=[{**json.loads(raw),'id':a,'name':n,'family':f,'version':v} for a,n,f,v,raw in rows]
    from .quality import issue_fingerprint
    from .validation import validate_record,fingerprint
    decisions={(asset_id,rule,field,fp):state for asset_id,rule,field,fp,state in conn.execute("SELECT asset_id,rule_id,field,fingerprint,state FROM quality_issues WHERE state IN ('resolved','accepted_exception')")}
    current_month=date.today().strftime('%Y-%m')
    for asset in assets:
        findings=validate_record(asset,current_month)
        for inspection in asset.get('inspections',[]):
            related=[i for i in findings if i['field'].startswith('inspections.'+inspection['inspection_type']+'.') and i['rule_id'] in ('source-review','chronology','internal-family')]
            open_findings=[i for i in related if (asset['id'],i['rule_id'],i['field'],issue_fingerprint(asset,i)) not in decisions]
            if open_findings:
                inspection['review_status']='Review';inspection['review_reason']='; '.join(i['message'] for i in open_findings)
            elif related and inspection.get('review_status')=='Review':inspection['review_status']='Accepted exception'
        for item in asset.get('review_items',[]):
            field='review_items.'+str(item.get('review_id') or fingerprint(item))
            finding=next((f for f in findings if f['field']==field),None)
            if finding and (asset['id'],finding['rule_id'],field,issue_fingerprint(asset,finding)) in decisions:item['review_status']='Accepted exception'
    return assets


def matches_summary(asset,filters):
    status=filters.get('status','active');archived=asset.get('record_status')=='Archived'
    if status!='all' and (archived if status=='active' else not archived):return False
    scope=filters.get('ids')
    if scope is not None and asset['id'] not in scope:return False
    sheet=filters.get('sheet')
    if sheet and (bool(asset.get('source_sheet')) if sheet=='__manual__' else asset.get('source_sheet')!=sheet):return False
    for filter_key,key in [('family','family'),('service','service_status_original')]:
        if filters.get(filter_key) and asset.get(key)!=filters[filter_key]:return False
    review=any(i.get('review_status')=='Review' for i in asset.get('inspections',[])+asset.get('review_items',[]))
    if filters.get('review') and (not review if filters['review']=='review' else review):return False
    text=' '.join(str(asset.get(k) or '').lower() for k in ('name','tag_original','asset_number_original','oracle_description','source_sheet','location_from','source_group','field','plant','pack_original'))
    for token in re.findall(r'[^\W_]+',str(filters.get('search') or '').lower()):
        variants=['compressor','compress','comp','com'] if token in ('compressor','compressors','compress','comp','com') else ['turbine','turb'] if token in ('turbine','turbines','turb') else ['generator','gen'] if token in ('generator','generators','gen') else [token]
        if not any(v in text for v in variants):return False
    due_filter=filters.get('due')
    if not due_filter:return True
    now=filters.get('current') or date.today().strftime('%Y-%m');end=filters.get('end') or now
    validate_month(now);validate_month(end)
    for inspection in asset.get('inspections',[]):
        if inspection.get('applicable')!='Yes':continue
        due=inspection.get('next_inspection_month')
        if due_filter=='attention' and (inspection.get('review_status')=='Review' or not due):return True
        if due_filter in ('shutdown','evaluation') and str(inspection.get('scheduling_condition') or '').lower()==('at next shutdown' if due_filter=='shutdown' else 'awaiting evaluation'):return True
        if inspection.get('review_status')=='Review':continue
        if due_filter=='undated' and not due:return True
        if not due:continue
        if due_filter=='due' and due==now:return True
        if due_filter=='upcoming' and now<due<=end:return True
        if due_filter.startswith('overdue') and due<now and (due_filter=='overdue' or inspection['inspection_type']==('OSI' if due_filter=='overdueOSI' else 'Internal')):return True
        if due_filter.startswith('age') and due<now:
            age=(int(now[:4])-int(due[:4]))*12+int(now[5:])-int(due[5:])
            if (due_filter=='age1' and age<=3) or (due_filter=='age2' and 4<=age<=6) or (due_filter=='age3' and 7<=age<=12) or (due_filter=='age4' and age>=13):return True
    return False


def natural_key(value):
    return [(0,int(p)) if p.isdigit() else (1,p.casefold()) for p in re.split(r'(\d+)',value)]


@serialized
def query_register(store,filters):
    if not isinstance(filters,dict):raise ValueError('Invalid register filters')
    try:size=min(200,max(1,int(filters.get('size',100))));page=max(1,int(filters.get('page',1)))
    except (TypeError,ValueError):raise ValueError('Invalid register page')
    filters=dict(filters)
    if filters.get('due') and not filters.get('current'):filters['current']=date.today().strftime('%Y-%m')
    if filters.get('ids') is not None:
        if not isinstance(filters['ids'],list) or any(not isinstance(i,str) for i in filters['ids']):raise ValueError('Invalid asset scope')
        filters['ids']=set(filters['ids'])
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows=[a for a in read_summaries(conn) if matches_summary(a,filters)]
        revision=conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
    group=filters.get('group')
    if group:
        if group not in ('source_sheet','plant','field','pack_original','location_from'):raise ValueError('Invalid register grouping')
        rows.sort(key=lambda a:(not bool(str(a.get(group) or '').strip()),natural_key(str(a.get(group) or '').strip())))
    total=len(rows);pages=max(1,(total+size-1)//size);page=min(page,pages)
    return {'rows':rows[(page-1)*size:page*size],'total':total,'page':page,'pages':pages,'revision':revision}

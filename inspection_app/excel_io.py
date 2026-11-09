"""Offline editable workbooks, explicit three-way synchronization and staged recovery.

The hidden snapshot preserves unexposed fields; it is data, never executable SQL.
Only issued baselines may synchronize back into the issuing database.
"""
from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import uuid
import zipfile
import xml.etree.ElementTree as ET

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .store import serialized, initialize_schema, Store
from . import payloads
from .migrations import SCHEMA_VERSION
from .months import validate_month
from .mutations import next_revision, record_event
from .backups import create_backup

VERSION=2
MARKER='Inspection editable database'
SYSTEM='Export System'
SNAPSHOT='Export Baseline'
LONG='Long Text'
# Explicit business-table allowlist. Never import paths, triggers, SQL or backup settings.
BUSINESS=('assets','version_clock','correction_events','field_verifications','quality_issues',
          'import_batches','master_snapshots','bulk_operations','asset_aliases','consolidation_previews',
          'source_baselines','import_batch_assets','import_reference','excel_identity','excel_exports','excel_new_ids','excel_created_rows','sqlite_sequence')
ASSET_FIELDS='name family tag_original asset_number_original oracle_description field plant location_from unit_or_location_to service_status_original record_status pack_original parent_group source_group'.split()
GROUPS={
 'Asset Register':(None,['_key','asset_id']+ASSET_FIELDS),
 'Inspection Records':('inspections','_key asset_id inspection_id inspection_type applicable last_inspection_month next_inspection_month last_inspection_status scheduling_condition condition_review_by review_status review_reason'.split()),
 'Technical Details':('technical_details','_key asset_id field_id field_label value unit_explicit'.split()),
 'Notes & Comments':('notes','_key asset_id note_id note_type note_text'.split()),
 'Review Items':('review_items','_key asset_id review_id field review_status reason'.split()),
}
IDENTITY={'inspections':'inspection_id','technical_details':'field_id','notes':'note_id','review_items':'review_id'}
from .excel_style import NAVY, BLUE


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _hash(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def _ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS excel_identity (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
    conn.execute('INSERT OR IGNORE INTO excel_identity VALUES (1,?)',(str(uuid.uuid4()),))
    conn.execute('CREATE TABLE IF NOT EXISTS excel_exports (export_id TEXT PRIMARY KEY, digest TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS excel_previews (token TEXT PRIMARY KEY, kind TEXT NOT NULL, contents TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS excel_created_rows (export_id TEXT NOT NULL, local_key TEXT NOT NULL, contents TEXT NOT NULL, PRIMARY KEY(export_id,local_key))')
    conn.execute('CREATE TABLE IF NOT EXISTS excel_new_ids (export_id TEXT NOT NULL, local_key TEXT NOT NULL, permanent_id TEXT NOT NULL, PRIMARY KEY(export_id,local_key))')


def _pack(value):
    if isinstance(value,bytes):return {'_blob':base64.b64encode(value).decode('ascii')}
    return value


def _unpack(value):
    if isinstance(value,dict) and set(value)=={'_blob'}:return base64.b64decode(value['_blob'],validate=True)
    if isinstance(value,(dict,list)):raise ValueError('Invalid snapshot cell type')
    return value


def _snapshot(conn):
    result={}
    existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in BUSINESS:
        if table not in existing:continue
        columns=[r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        result[table]={'columns':columns,'rows':[[_pack(v) for v in r] for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]}
    return result


def _assets(snapshot):
    table=snapshot['assets'];result={}
    for values in table['rows']:
        row=dict(zip(table['columns'],values));details=json.loads(row['details'])
        if set(details)&{'id','name','family','version','details'}:raise ValueError('Reserved asset field in snapshot')
        result[row['id']]={**details,'id':row['id'],'name':row['name'],'family':row['family'],'version':row['version']}
    return result


def _rows(assets):
    result={sheet:{} for sheet in GROUPS}
    for aid,asset in assets.items():
        result['Asset Register'][aid]={'_key':aid,'asset_id':aid,**{f:asset.get(f) for f in ASSET_FIELDS}}
        for sheet,(group,columns) in GROUPS.items():
            if not group:continue
            for index,item in enumerate(asset.get(group,[])):
                ident=item.get(IDENTITY[group])
                if group=='inspections' and not ident:
                    # The model permits exactly one obligation of each type.
                    # Legacy records lacking IDs therefore have a stable identity
                    # independent of list order or editable schedule values.
                    ident=str(uuid.uuid5(uuid.NAMESPACE_URL,f'inspection-obligation:{aid}:{item.get("inspection_type")}'))
                key=str(uuid.uuid5(uuid.NAMESPACE_URL,f'inspection-excel:{aid}:{group}:{ident if ident else "content:"+_hash(item)}'))
                if key in result[sheet]:
                    if ident:raise ValueError('Duplicate child identity in '+sheet)
                    key=str(uuid.uuid5(uuid.NAMESPACE_URL,key+':duplicate:'+str(index)))
                result[sheet][key]={'_key':key,'asset_id':aid,**{f:(ident if group=='inspections' and f=='inspection_id' else item.get(f)) for f in columns[2:]}}
    return result


def _literal(ws,row,col,value):
    cell=ws.cell(row,col,value)
    if isinstance(value,str):cell.data_type='s'
    return cell


def style_table(ws,headers,rows,table_name):
    ws.append(headers)
    # max_row scans all existing cells; querying it for every cell makes
    # large evidence tables quadratic. Track the appended row directly.
    for row_number,values in enumerate(rows,2):
        for c,value in enumerate(values,1):_literal(ws,row_number,c,value)
    for cell in ws[1]:cell.fill=PatternFill('solid',fgColor=NAVY);cell.font=Font(name='Calibri',bold=True,color='FFFFFF');cell.alignment=Alignment(wrap_text=True)
    ws.row_dimensions[1].height=27
    ws.freeze_panes='C2';ws.sheet_view.showGridLines=False
    for n,h in enumerate(headers,1):
        ws.column_dimensions[get_column_letter(n)].width=46 if any(x in h for x in ('text','reason','name','description')) else 23
    for row in ws.iter_rows(min_row=2):
        for c in row:c.alignment=Alignment(vertical='top',wrap_text=True);c.font=Font(name='Aptos',size=10,color='26383C')
    if rows:
        table=Table(displayName=table_name,ref=f'A1:{get_column_letter(len(headers))}{ws.max_row}')
        table._initialise_columns()
        for column,header in zip(table.tableColumns,headers):column.name=header
        table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium4',showRowStripes=True)
        ws.add_table(table)
    else:ws.auto_filter.ref=f'A1:{get_column_letter(len(headers))}1'
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
    ws.print_area=f'A1:{get_column_letter(len(headers))}{max(1,ws.max_row)}'
    ws.oddFooter.center.text='Page &P of &N';ws.oddHeader.center.text='Local Master Inspection Plan'


def _atomic_save(book,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.excel-',suffix='.xlsx',dir=path.parent);os.close(fd)
    try:book.save(tmp);_dynamic_array_metadata(tmp);os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True);book.close()
    return path


def _dynamic_array_metadata(path):
    """Add OOXML dynamic-array anchors and XLDAPR metadata omitted by openpyxl.

    Uses standard SpreadsheetML metadata, not an executable dependency or macro.
    Excel still must recalculate; an XML check cannot verify desktop behavior.
    """
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    dynamic='http://schemas.microsoft.com/office/spreadsheetml/2017/dynamicarray'
    package='http://schemas.openxmlformats.org/package/2006/relationships'
    document='http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    content='http://schemas.openxmlformats.org/package/2006/content-types'
    changed={}
    with zipfile.ZipFile(path) as source:
        for name in source.namelist():
            if not (name.startswith('xl/worksheets/sheet') and name.endswith('.xml')):continue
            raw=source.read(name)
            if b'_xlfn._xlws.FILTER' not in raw:continue
            root=ET.fromstring(raw)
            for cell in root.iter('{'+main+'}c'):
                formula=cell.find('{'+main+'}f')
                if formula is not None and '_xlfn._xlws.FILTER' in (formula.text or ''):
                    formula.set('t','array');formula.set('ref',cell.attrib['r']);cell.set('cm','1')
            changed[name]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        if not changed:return
        metadata=ET.Element('{'+main+'}metadata')
        types=ET.SubElement(metadata,'{'+main+'}metadataTypes',count='1')
        attributes={key:'1' for key in ('copy','pasteAll','pasteValues','merge','splitFirst','rowColShift','clearFormats','clearComments','assign','coerce','cellMeta')}
        ET.SubElement(types,'{'+main+'}metadataType',name='XLDAPR',minSupportedVersion='120000',**attributes)
        future=ET.SubElement(metadata,'{'+main+'}futureMetadata',name='XLDAPR',count='1')
        block=ET.SubElement(future,'{'+main+'}bk');exts=ET.SubElement(block,'{'+main+'}extLst')
        ext=ET.SubElement(exts,'{'+main+'}ext',uri='{bdbb8cdc-fa1e-496e-a857-3c3f30c029c3}')
        ET.SubElement(ext,'{'+dynamic+'}dynamicArrayProperties',fDynamic='1',fCollapsed='0')
        cells=ET.SubElement(metadata,'{'+main+'}cellMetadata',count='1')
        block=ET.SubElement(cells,'{'+main+'}bk');ET.SubElement(block,'{'+main+'}rc',t='1',v='0')
        changed['xl/metadata.xml']=ET.tostring(metadata,encoding='utf-8',xml_declaration=True)
        rels=ET.fromstring(source.read('xl/_rels/workbook.xml.rels'))
        used={r.get('Id') for r in rels};number=1
        while 'rId'+str(number) in used:number+=1
        ET.SubElement(rels,'{'+package+'}Relationship',Type=document+'sheetMetadata',Target='metadata.xml',Id='rId'+str(number))
        changed['xl/_rels/workbook.xml.rels']=ET.tostring(rels,encoding='utf-8',xml_declaration=True)
        ct=ET.fromstring(source.read('[Content_Types].xml'))
        ET.SubElement(ct,'{'+content+'}Override',PartName='/xl/metadata.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml')
        changed['[Content_Types].xml']=ET.tostring(ct,encoding='utf-8',xml_declaration=True)
        staged=str(path)+'.dynamic'
        try:
            with zipfile.ZipFile(staged,'w',compression=zipfile.ZIP_DEFLATED) as target:
                for item in source.infolist():target.writestr(item,changed.pop(item.filename,source.read(item.filename)))
                for name,data in changed.items():target.writestr(name,data)
        except BaseException:
            Path(staged).unlink(missing_ok=True);raise
    os.replace(staged,path)


def _write_chunks(book,name,text):
    ws=book.create_sheet(name);ws.append(['part','text'])
    for n,start in enumerate(range(0,len(text),28000)):_literal(ws,n+2,1,n);_literal(ws,n+2,2,text[start:start+28000])
    ws.sheet_state='veryHidden';ws.protection.sheet=True


ASSET_LABELS={
 'name':'Asset name','family':'Asset family','tag_original':'Tag','asset_number_original':'Asset number',
 'oracle_description':'Full description','field':'Field','plant':'Plant','location_from':'Location',
 'unit_or_location_to':'Unit / location','service_status_original':'Service status','record_status':'Record status',
 'pack_original':'Pack','parent_group':'Parent group','source_group':'Source group'
}
INSPECTION_LABELS={
 'applicable':'Applicable','last_inspection_month':'Last month','next_inspection_month':'Next month',
 'last_inspection_status':'Last status','scheduling_condition':'Next condition',
 'condition_review_by':'Condition review by','review_status':'Review status','review_reason':'Review reason'
}
ASSET_FIELD_ORDER=['field','plant','location_from','unit_or_location_to','name','tag_original','asset_number_original','oracle_description','service_status_original','family','record_status','pack_original','parent_group','source_group']


def _flat_layout(assets,tables):
    """Build a source-tab layout whose rows keep an asset and its editable children together."""
    names=[]
    for asset in assets.values():
        name=asset.get('source_sheet')
        if not isinstance(name,str) or not name.strip():name='Unassigned'
        name=name.strip()[:31]
        if name in ('Master Plan','Guide','Source Cells','Field Map','Long Text','Export System','Export Baseline'):
            name=(name[:24]+' Assets')[:31]
        if name not in names:names.append(name)
    if not names:names=['Unassigned']
    result={'sheets':{},'asset_sheet_by_key':{}}
    notes=tables['Notes & Comments'];reviews=tables['Review Items'];tech=tables['Technical Details']
    for name in names:
        aids=[aid for aid,a in assets.items() if (a.get('source_sheet') or 'Unassigned').strip()==name]
        # Avoid sorting field identities away from their source-column order.
        tech_ids=[];tech_labels={}
        for aid in aids:
            for item in assets[aid].get('technical_details',[]):
                field_id=item.get('field_id')
                if field_id and field_id not in tech_ids:
                    tech_ids.append(field_id);tech_labels[field_id]=item.get('field_label') or field_id
        max_notes=max([sum(1 for row in notes.values() if row['asset_id']==aid) for aid in aids]+[0])+1
        max_reviews=max([sum(1 for row in reviews.values() if row['asset_id']==aid) for aid in aids]+[0])+1
        columns=[];hidden=[];asset_columns={};inspection_slots={};technical_slots={};new_technical=[];note_slots=[];review_slots=[];groups=[]
        def col(header,kind,**meta):
            idx=len(columns);columns.append({'header':header,'kind':kind,**meta})
            if kind in ('asset_key','asset_identity','inspection_key','inspection_id','technical_key','note_key','note_id','review_key','review_id'):hidden.append(idx)
            return idx
        start=len(columns);col('_asset_key','asset_key');asset_id_column=col('_asset_id','asset_identity');new_asset_id=col('New asset ID · use new: label','new_asset_id')
        asset_columns={field:col(ASSET_LABELS.get(field,field.replace('_',' ').title()),'asset',field=field) for field in ASSET_FIELD_ORDER}
        groups.append(('ASSET DETAILS',start,len(columns)-1))
        for kind in ('OSI','Internal'):
            start=len(columns);key=col('_'+kind.lower()+'_key','inspection_key',inspection_type=kind);ident=col('_'+kind.lower()+'_id','inspection_id',inspection_type=kind)
            fields={field:col(kind+' · '+INSPECTION_LABELS.get(field,field.replace('_',' ').title()),'inspection',inspection_type=kind,field=field) for field in GROUPS['Inspection Records'][1][2:] if field not in ('inspection_id','inspection_type')}
            inspection_slots[kind]={'key':key,'id':ident,'fields':fields};groups.append((kind+' INSPECTION',start,len(columns)-1))
        start=len(columns)
        for field_id in tech_ids:
            label=str(tech_labels[field_id] or field_id).replace('\n',' ').strip()
            base=label
            if sum(1 for v in tech_labels.values() if str(v).replace('\n',' ').strip()==base)>1:label=f'{base} [{field_id}]'
            key=col('_tech_'+str(len(technical_slots)+1)+'_key','technical_key',field_id=field_id)
            value=col('Tech · '+label,'technical',field_id=field_id,field='value')
            unit=col('Tech unit · '+label,'technical',field_id=field_id,field='unit_explicit')
            technical_slots[field_id]={'key':key,'value':value,'unit_explicit':unit,'field_label':tech_labels[field_id]}
        for slot in range(1,3):
            new_technical.append({'key':col(f'_new_tech_{slot}_key','technical_key',new_slot=slot),'field_label':col(f'New technical {slot} · label','technical_new',new_slot=slot,field='field_label'),'value':col(f'New technical {slot} · value','technical_new',new_slot=slot,field='value'),'unit_explicit':col(f'New technical {slot} · unit','technical_new',new_slot=slot,field='unit_explicit')})
        if len(columns)>start:groups.append(('TECHNICAL DETAILS',start,len(columns)-1))
        start=len(columns)
        for slot in range(1,max_notes+1):
            note_slots.append({'key':col(f'_note_{slot}_key','note_key',slot=slot),'id':col(f'_note_{slot}_id','note_id',slot=slot),'type':col(f'Note {slot} · type','note',slot=slot,field='note_type'),'text':col(f'Note {slot} · text','note',slot=slot,field='note_text')})
        groups.append(('NOTES & ACTIONS',start,len(columns)-1))
        start=len(columns)
        for slot in range(1,max_reviews+1):
            review_slots.append({'key':col(f'_review_{slot}_key','review_key',slot=slot),'id':col(f'_review_{slot}_id','review_id',slot=slot),'field':col(f'Review {slot} · field','review',slot=slot,field='field'),'status':col(f'Review {slot} · status','review',slot=slot,field='review_status'),'reason':col(f'Review {slot} · reason','review',slot=slot,field='reason')})
        groups.append(('REVIEW ITEMS',start,len(columns)-1))
        result['sheets'][name]={'columns':columns,'hidden':hidden,'groups':groups,'asset_columns':asset_columns,'asset_key':0,'asset_id':asset_id_column,'new_asset_id':new_asset_id,'inspection_slots':inspection_slots,'technical_slots':technical_slots,'new_technical':new_technical,'note_slots':note_slots,'review_slots':review_slots,'assets':aids}
        for aid in aids:
            key=aid
            result['asset_sheet_by_key'][key]=name
    return result


def _flat_master_plan(book,assets,tables,summaries,layout):
    ws=book.create_sheet('Master Plan',0);ws.append(['MASTER INSPECTION PLAN'])
    ws.append(['Filter source tabs for your area. Each asset row keeps its editable details together on its original source tab.'])
    ws.append(['Read-only overview. Dates show YYYY-MM; full notes and linked details are on the matching asset row.'])
    headers=['Asset name','Tag','Location / group','Source tab','Service status','Last OSI','Next OSI','OSI condition','Last internal','Next internal','Internal condition','Review','Remarks (preview)','Asset ID','Record status']
    ws.append(headers)
    for aid,asset in assets.items():
        by_type={r.get('inspection_type'):r for r in asset.get('inspections',[])}
        review=summaries.get(aid,{})
        flagged=any(r.get('review_status')=='Review' for r in review.get('inspections',[]))
        notes=asset.get('notes',[]);preview=next((n.get('note_text') for n in notes if n.get('note_text')), '')
        values = [asset.get('name'),asset.get('tag_original'),asset.get('location_from'),asset.get('source_sheet') or 'Unassigned',asset.get('service_status_original'),by_type.get('OSI',{}).get('last_inspection_month'),by_type.get('OSI',{}).get('next_inspection_month'),by_type.get('OSI',{}).get('scheduling_condition'),by_type.get('Internal',{}).get('last_inspection_month'),by_type.get('Internal',{}).get('next_inspection_month'),by_type.get('Internal',{}).get('scheduling_condition'),'Review' if flagged else '',str(preview)[:240],aid,asset.get('record_status')]
        row = ws.max_row + 1
        for column, value in enumerate(values, 1):
            _literal(ws, row, column, value)
    for r in range(1,ws.max_row+1):
        ws.row_dimensions[r].height=26 if r>4 else (37 if r==1 else 24)
        for c in ws[r]:c.font=Font(name='Aptos',size=10,color='26383C');c.alignment=Alignment(vertical='center',wrap_text=c.row in (2,3) or c.column in (1,3,8,11,13))
    ws.merge_cells('A1:O1');ws.merge_cells('A2:O2');ws.merge_cells('A3:O3')
    ws['A1'].fill=PatternFill('solid',fgColor=NAVY);ws['A1'].font=Font(name='Aptos Display',size=19,bold=True,color='FFFFFF')
    for r in (2,3):ws.cell(r,1).fill=PatternFill('solid',fgColor=BLUE);ws.cell(r,1).font=Font(name='Aptos',size=10,color='425A5E',italic=r==3)
    for c in ws[4]:c.fill=PatternFill('solid',fgColor=NAVY);c.font=Font(name='Aptos',size=10,bold=True,color='FFFFFF');c.alignment=Alignment(wrap_text=True,vertical='center')
    ws.row_dimensions[4].height=32;ws.freeze_panes='C5';ws.auto_filter.ref=f'A4:O{ws.max_row}';ws.sheet_view.showGridLines=False;ws.sheet_view.zoomScale=85
    for r in range(5,ws.max_row+1):
        for c in ws[r]:
            if r%2==0:c.fill=PatternFill('solid',fgColor='F1F6F6')
    for i,width in enumerate([36,17,20,22,15,13,13,22,13,13,22,13,42,18,15],1):ws.column_dimensions[get_column_letter(i)].width=width
    ws.sheet_properties.tabColor=NAVY;ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=2;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.print_title_rows='1:4';ws.oddFooter.center.text='Page &P of &N'


def _flat_source_sheets(book,assets,tables,layout,long,progress=None):
    total_assets=sum(len(spec['assets']) for spec in layout['sheets'].values())
    completed_assets=0
    progress_every=max(1,total_assets//50)
    for n,(name,spec) in enumerate(layout['sheets'].items(),1):
        ws=book.create_sheet(name);headers=[c['header'] for c in spec['columns']]
        ws.append([name.upper()]);ws.append([None]*len(headers));ws.append(headers)
        for group_name,start,end in spec['groups']:
            if end>=start:ws.cell(2,start+1,group_name)
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers));ws.row_dimensions[1].height=36
        ws.cell(1,1).fill=PatternFill('solid',fgColor=NAVY);ws.cell(1,1).font=Font(name='Aptos Display',size=17,bold=True,color='FFFFFF')
        for label,start,end in spec['groups']:
            if end>=start:
                if end>start:ws.merge_cells(start_row=2,start_column=start+1,end_row=2,end_column=end+1)
                c=ws.cell(2,start+1);c.value=label;c.fill=PatternFill('solid',fgColor=BLUE);c.font=Font(name='Aptos',size=9,bold=True,color=NAVY);c.alignment=Alignment(vertical='center')
        ws.row_dimensions[2].height=22;ws.row_dimensions[3].height=38;ws.freeze_panes='C4';ws.sheet_view.showGridLines=False;ws.sheet_view.zoomScale=85
        for c in ws[3]:c.fill=PatternFill('solid',fgColor=NAVY);c.font=Font(name='Aptos',size=9,bold=True,color='FFFFFF');c.alignment=Alignment(wrap_text=True,vertical='center')
        source_rows=[];asset_keys=spec['assets'];note_rows=tables['Notes & Comments'];review_rows=tables['Review Items'];tech_rows=tables['Technical Details'];inspection_rows=tables['Inspection Records']
        by_asset={aid:{'inspection':{},'technical':{},'notes':[],'reviews':[]} for aid in asset_keys}
        for row in inspection_rows.values():
            if row['asset_id'] in by_asset:by_asset[row['asset_id']]['inspection'][row['inspection_type']]=row
        for row in tech_rows.values():
            if row['asset_id'] in by_asset:by_asset[row['asset_id']]['technical'][row['field_id']]=row
        for row in note_rows.values():
            if row['asset_id'] in by_asset:by_asset[row['asset_id']]['notes'].append(row)
        for row in review_rows.values():
            if row['asset_id'] in by_asset:by_asset[row['asset_id']]['reviews'].append(row)
        for aid in asset_keys:
            row=[None]*len(headers);asset=assets[aid];row[spec['asset_key']]=aid;row[spec['asset_id']]=aid
            for field,index in spec['asset_columns'].items():row[index]=asset.get(field)
            long_keys={index:('Asset Register',aid,field) for field,index in spec['asset_columns'].items()}
            for kind,slot in spec['inspection_slots'].items():
                child=by_asset[aid]['inspection'].get(kind)
                if child:
                    row[slot['key']]=child['_key'];row[slot['id']]=child.get('inspection_id')
                    for field,index in slot['fields'].items():row[index]=child.get(field)
                    long_keys.update({index:('Inspection Records',child['_key'],field) for field,index in slot['fields'].items()})
            for field_id,slot in spec['technical_slots'].items():
                child=by_asset[aid]['technical'].get(field_id)
                if child:
                    row[slot['key']]=child['_key'];row[slot['value']]=child.get('value');row[slot['unit_explicit']]=child.get('unit_explicit')
                    long_keys[slot['value']]=('Technical Details',child['_key'],'value')
            for slot_no,slot in enumerate(spec['note_slots']):
                child=by_asset[aid]['notes'][slot_no] if slot_no<len(by_asset[aid]['notes']) else None
                if child:
                    row[slot['key']]=child['_key'];row[slot['id']]=child.get('note_id');row[slot['type']]=child.get('note_type');row[slot['text']]=child.get('note_text')
                    long_keys[slot['type']]=('Notes & Comments',child['_key'],'note_type');long_keys[slot['text']]=('Notes & Comments',child['_key'],'note_text')
            for slot_no,slot in enumerate(spec['review_slots']):
                child=by_asset[aid]['reviews'][slot_no] if slot_no<len(by_asset[aid]['reviews']) else None
                if child:
                    row[slot['key']]=child['_key'];row[slot['id']]=child.get('review_id')
                    for field,column in (('field','field'),('review_status','status'),('reason','reason')):row[slot[column]]=child.get(field)
                    long_keys.update({slot[column]:('Review Items',child['_key'],field) for field,column in (('field','field'),('review_status','status'),('reason','reason'))})
            if len(row)==0:continue
            ws.append([None]*len(headers));target_row=ws.max_row
            for c,value in enumerate(row,1):
                if value is None:continue
                if isinstance(value,str) and len(value)>28000:
                    target=long_keys.get(c-1)
                    if target is None:raise ValueError('Long editable value needs a mapped field')
                    target_sheet,target_key,target_field=target
                    for part,start in enumerate(range(0,len(value),28000)):long.append([target_sheet,target_key,target_field,part,value[start:start+28000]])
                    value=f'[Long Text: {target_key}:{target_field}]'
                _literal(ws,target_row,c,value)
            for c,meta in enumerate(spec['columns'],1):
                cell=ws.cell(target_row,c);cell.alignment=Alignment(vertical='top',wrap_text=meta['kind'] in ('asset','note','review','technical_new'))
                cell.font=Font(name='Aptos',size=9,color='26383C')
                if c in spec['hidden']:cell.number_format='@'
            ws.row_dimensions[target_row].height=40
            completed_assets+=1
            if progress and (completed_assets%progress_every==0 or completed_assets==total_assets):
                percent=18+round(55*completed_assets/max(1,total_assets))
                progress(percent,f'Preparing {name}: {completed_assets:,} of {total_assets:,} assets')
        end=ws.max_row
        table=Table(displayName=f'AssetSource{n}',ref=f'A3:{get_column_letter(len(headers))}{max(3,end)}');table._initialise_columns()
        for column,header in zip(table.tableColumns,headers):column.name=header
        # Excel Tables already carry their own filter. A duplicate worksheet-level
        # AutoFilter on the same range makes desktop Excel repair this worksheet.
        table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium4',showRowStripes=True);ws.add_table(table)
        for index,meta in enumerate(spec['columns'],1):
            letter=get_column_letter(index)
            if index-1 in spec['hidden']:ws.column_dimensions[letter].hidden=True;ws.column_dimensions[letter].width=3
            elif meta['kind'] in ('note','review'):ws.column_dimensions[letter].width=38
            elif meta['kind']=='asset':ws.column_dimensions[letter].width=27
            elif meta['kind']=='technical_new':ws.column_dimensions[letter].width=22
            else:ws.column_dimensions[letter].width=19
            if meta['kind'] in ('inspection',) and 'month' in meta.get('field',''):
                dv=DataValidation(type='custom',formula1=f'OR({letter}4="",ISNUMBER({letter}4),AND(LEN({letter}4)=7,MID({letter}4,5,1)="-",ISNUMBER(--LEFT({letter}4,4)),--LEFT({letter}4,4)>0,ISNUMBER(--RIGHT({letter}4,2)),--RIGHT({letter}4,2)>0,--RIGHT({letter}4,2)<13))',allow_blank=True);dv.showErrorMessage=True;dv.error='Use YYYY-MM text or a valid Excel date.';ws.add_data_validation(dv);dv.add(f'{letter}4:{letter}1048576')
        ws.sheet_properties.tabColor='4B9798';ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=2;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.print_title_rows='1:3';ws.oddFooter.center.text='Page &P of &N'


def _read_flat_tables(book,baseline):
    layout=baseline.get('flat_layout')
    if not isinstance(layout,dict) or not isinstance(layout.get('sheets'),dict):raise ValueError('Missing asset-sheet layout metadata')
    tables={name:{} for name in GROUPS};asset_ids=set();source_sheet_by_key=layout.get('asset_sheet_by_key',{})
    for name,spec in layout['sheets'].items():
        if name not in book:raise ValueError('Missing source asset sheet: '+name)
        ws=book[name];columns=spec['columns'];headers=[c.value for c in ws[3]]
        if headers!=[c['header'] for c in columns]:raise ValueError('Changed or missing headings in '+name)
        for cells in ws.iter_rows(min_row=4,max_col=len(columns)):
            values=[c.value for c in cells]
            if any(c.data_type=='f' for c in cells):
                formula=next(c for c in cells if c.data_type=='f');raise ValueError('Formulas are not allowed in editable source rows: '+name+' '+formula.coordinate)
            stored_id=values[spec['asset_id']];new_label=values[spec['new_asset_id']];key=values[spec['asset_key']]
            if stored_id in (None,'') and new_label in (None,'') and not any(v not in (None,'') for v in values):continue
            if new_label not in (None,''):
                if not isinstance(new_label,str) or not new_label.startswith('new:'):raise ValueError('New asset ID must use a unique new: label on '+name)
                if stored_id not in (None,''):raise ValueError('Do not replace the permanent ID on an existing row in '+name)
                aid=new_label.strip();key=key or aid
            else:
                aid=stored_id
                if not isinstance(aid,str) or not aid.strip():raise ValueError('Use New asset ID to add an asset row in '+name)
                aid=aid.strip()
            if not isinstance(key,str) or not key.strip():key=aid
            key=key.strip()
            if key in asset_ids:raise ValueError('Duplicate asset row across source tabs: '+key)
            if not key.startswith('new:') and source_sheet_by_key.get(key)!=name:raise ValueError('Move existing assets only by editing their original source tab: '+name)
            if key.startswith('new:') and aid!=key:raise ValueError('New asset ID must match its new: row key')
            asset_ids.add(key);asset_row={'_key':key,'asset_id':aid}
            if key.startswith('new:'):asset_row['_source_sheet']=name
            for field,index in spec['asset_columns'].items():
                value=values[index]
                asset_row[field]=value
            tables['Asset Register'][key]=asset_row
            def child_value(index,field,coordinate):
                value=values[index]
                if field in ('last_inspection_month','next_inspection_month','condition_review_by') and isinstance(value,(date,datetime)):value=value.strftime('%Y-%m')
                return value
            for kind,slot in spec['inspection_slots'].items():
                child_key=values[slot['key']];ident=values[slot['id']]
                fields={field:child_value(index,field,name) for field,index in slot['fields'].items()}
                if child_key in (None,'') and not any(v not in (None,'') for v in fields.values()):continue
                child_key=child_key or (f'new:{key}:inspection:{kind}')
                row={'_key':child_key,'asset_id':aid,'inspection_id':ident,'inspection_type':kind,**fields}
                if ident is None and child_key in baseline['tables']['Inspection Records']:ident=baseline['tables']['Inspection Records'][child_key].get('inspection_id');row['inspection_id']=ident
                tables['Inspection Records'][child_key]=row
            for field_id,slot in spec['technical_slots'].items():
                child_key=values[slot['key']];value=child_value(slot['value'],'value',name);unit=child_value(slot['unit_explicit'],'unit_explicit',name)
                if child_key in (None,'') and value in (None,'') and unit in (None,''):continue
                child_key=child_key or f'new:{key}:technical:{field_id}'
                tables['Technical Details'][child_key]={'_key':child_key,'asset_id':aid,'field_id':field_id,'field_label':slot['field_label'],'value':value,'unit_explicit':unit}
            for slot_no,slot in enumerate(spec['new_technical'],1):
                child_key=values[slot['key']];fields={field:child_value(index,field,name) for field,index in slot.items() if field not in ('key',)}
                if child_key in (None,'') and not any(v not in (None,'') for v in fields.values()):continue
                child_key=child_key or f'new:{key}:technical:new{slot_no}'
                tables['Technical Details'][child_key]={'_key':child_key,'asset_id':aid,'field_id':None,**fields}
            for slot_no,slot in enumerate(spec['note_slots'],1):
                child_key=values[slot['key']];ident=values[slot['id']];kind=child_value(slot['type'],'note_type',name);text=child_value(slot['text'],'note_text',name)
                if child_key in (None,'') and kind in (None,'') and text in (None,''):continue
                child_key=child_key or f'new:{key}:note:{slot_no}'
                tables['Notes & Comments'][child_key]={'_key':child_key,'asset_id':aid,'note_id':ident,'note_type':kind,'note_text':text}
            for slot_no,slot in enumerate(spec['review_slots'],1):
                child_key=values[slot['key']];ident=values[slot['id']];fields={'field':child_value(slot['field'],'field',name),'review_status':child_value(slot['status'],'review_status',name),'reason':child_value(slot['reason'],'reason',name)}
                if child_key in (None,'') and not any(v not in (None,'') for v in fields.values()):continue
                child_key=child_key or f'new:{key}:review:{slot_no}'
                tables['Review Items'][child_key]={'_key':child_key,'asset_id':aid,'review_id':ident,**fields}
    return tables


def export_full_workbook(store,path,progress=None):
    if progress:progress(2,'Reading the database')
    # Read a consistent snapshot under the app lock, then release it before
    # building thousands of cells and writing the workbook.
    with store._lock:
        with closing(sqlite3.connect(store.db_path)) as conn,conn:
            _ensure(conn)
            conn.commit();conn.execute('BEGIN')
            snapshot=_snapshot(conn);database_id=conn.execute('SELECT value FROM excel_identity WHERE id=1').fetchone()[0]
            from .register import read_summaries
            summaries={a['id']:a for a in read_summaries(conn)}
    if progress:progress(12,'Organizing asset rows')
    assets=_assets(snapshot);tables=_rows(assets)
    layout=_flat_layout(assets,tables)
    baseline={'version':VERSION,'schema':SCHEMA_VERSION,'export_id':str(uuid.uuid4()),'database_id':database_id,'snapshot':snapshot,'tables':tables,'flat_layout':layout,'generated':datetime.now().isoformat()}
    digest=_hash(baseline)
    book=Workbook();book.remove(book.active)
    guide=book.create_sheet('Guide')
    for row in [
        ['LOCAL MASTER INSPECTION PLAN','Original source tabs, with one row per asset'],
        ['Start here','Use Master Plan for a read-only overview. Open the asset’s original source tab to edit it.'],
        ['One asset, one row','Each source tab puts the asset fields, OSI/Internal dates, technical details, notes, and review items on the same asset row.'],
        ['Find an asset','Use the filter row on the source tab. Source tab names follow the original workbook. Assets without a source tab appear under Unassigned.'],
        ['Edit existing assets','Edit cells on the asset row. Keep its hidden permanent ID and hidden child IDs unchanged.'],
        ['Add an asset','Add a row inside the appropriate source-tab table. Put a unique new: label in New asset ID. Fill the asset fields and any OSI/Internal, technical, note, or review fields on that same row.'],
        ['Add child details','Use the blank Note, Review, or New technical slots on the asset row. For new technical details, enter a label, value and unit. Reconciled exports assign permanent IDs.'],
        ['Months','Enter YYYY-MM text or a valid Excel date. Dates are kept at month precision; unknown dates stay blank.'],
        ['Long text','Values above 28,000 characters are held in Long Text chunks. Edit the matching chunks; keep their row key, field and part sequence intact.'],
        ['Synchronization','Preview changes, resolve every conflict and apply. Download the reconciled workbook before the next editing cycle. Missing rows never delete app records.'],
        ['Review','Importing is not verification. Current rules derive review status in the app. Engineering exceptions still need app review.'],
        ['Recovery','Recovery restores supported business rows, IDs and history into a validated temporary database. Original binary workbooks and machine settings require a native recovery ZIP.'],
        ['Compatibility','This workbook uses Excel Tables, filters and date validation. No dynamic-array formulas are needed for editing.'],
    ]:guide.append(row)
    guide.merge_cells('A1:B1');guide['A1'].fill=PatternFill('solid',fgColor=NAVY);guide['A1'].font=Font(name='Aptos Display',size=17,bold=True,color='FFFFFF');guide.row_dimensions[1].height=36
    guide.column_dimensions['A'].width=24;guide.column_dimensions['B'].width=105
    for row in guide.iter_rows(min_row=2):
        for c in row:c.alignment=Alignment(wrap_text=True,vertical='center');c.font=Font(name='Aptos',size=10,color='26383C')
        guide.row_dimensions[row[0].row].height=34
    guide.sheet_view.showGridLines=False;guide.sheet_properties.tabColor='78A9AA';guide.freeze_panes='A2'
    long=[]
    _flat_source_sheets(book,assets,tables,layout,long,progress)
    if progress:progress(76,'Building the overview and reference tabs')
    _flat_master_plan(book,assets,tables,summaries,layout)
    if long:style_table(book.create_sheet(LONG),['sheet','_key','field','part','text'],long,'LongTextData')
    evidence=[]
    for aid,asset in assets.items():
        for item in asset.get('source_cells',[]):
            value=item.get('original_value')
            if isinstance(value,str) and len(value)>28000:value='[Complete value retained in Export Baseline]'
            evidence.append([item.get('source_sheet'),item.get('source_row'),item.get('source_cell'),aid,item.get('row_role'),str(value) if isinstance(value,(dict,list)) else value,item.get('excel_type'),('[Complete annotation retained in Export Baseline]' if len(str(item.get('original_annotation') or ''))>28000 else item.get('original_annotation')),item.get('historical_asset_id')])
    ws=book.create_sheet('Source Cells');style_table(ws,['source_sheet','source_row','source_cell','asset_id','row_role','original_value','excel_type','original_annotation','historical_asset_id'],evidence or [[None]*9],'SourceCells');ws.protection.sheet=True
    refs=snapshot.get('import_reference',{});reference_rows={dict(zip(refs['columns'],r))['name']:dict(zip(refs['columns'],r))['contents'] for r in refs.get('rows',[])}
    # Snapshot values encode SQLite BLOBs as JSON-safe {_blob: ...} objects.
    # Field Map can be compressed in storage, so restore its raw bytes before
    # passing it to the lossless payload decoder.
    field_map=payloads.loads(_unpack(reference_rows.get('Field Map','[]')))
    fields=[[row.get('source_sheet'),row.get('source_column'),row.get('source_heading'),row.get('destination'),row.get('field_id'),row.get('preservation')] for row in field_map]
    ws=book.create_sheet('Field Map');style_table(ws,['source_sheet','source_column','source_heading','destination','field_id','preservation'],fields or [[None]*6],'FieldMap');ws.protection.sheet=True
    order=['Master Plan','Guide']+list(layout['sheets'])+['Source Cells','Field Map','Annual Plan',LONG,SYSTEM,SNAPSHOT]
    book._sheets=[book[name] for name in order if name in book]+[ws for ws in book.worksheets if ws.title not in order]
    for name in layout['sheets']:book[name].sheet_properties.tabColor='4B9798'
    meta=book.create_sheet(SYSTEM)
    for row in [('type',MARKER),('version',VERSION),('schema',SCHEMA_VERSION),('export_id',baseline['export_id']),('database_id',database_id),('digest',digest)]:meta.append(row)
    meta.sheet_state='veryHidden';meta.protection.sheet=True
    _write_chunks(book,SNAPSHOT,_json(baseline))
    if progress:progress(88,'Writing the Excel workbook')
    result=_atomic_save(book,path)
    if progress:progress(97,'Finalizing the export')
    with store._lock:
        with closing(sqlite3.connect(store.db_path)) as conn,conn:
            _ensure(conn)
            current_identity=conn.execute('SELECT value FROM excel_identity WHERE id=1').fetchone()[0]
            if current_identity!=database_id:raise ValueError('The database was reset while the workbook was being prepared. Export again.')
            conn.execute('INSERT INTO excel_exports VALUES (?,?)',(baseline['export_id'],digest))
    if progress:progress(100,'Workbook ready')
    return result


def _read(path):
    try:
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist())>512*1024*1024:raise ValueError('Workbook exceeds expanded size limit')
        with open(path,'rb') as stream:book=load_workbook(stream,data_only=False)
    except (OSError,zipfile.BadZipFile,KeyError) as exc:raise ValueError('Invalid Excel workbook') from exc
    try:
        if SYSTEM not in book or SNAPSHOT not in book:raise ValueError('Only a Full Editable Database Workbook supports synchronization or recovery. Reports are read-only snapshots.')
        meta=dict(book[SYSTEM].iter_rows(values_only=True))
        if meta.get('type')!=MARKER or meta.get('version')!=VERSION or meta.get('schema')!=SCHEMA_VERSION:raise ValueError('Unsupported workbook type, version or database schema')
        chunks=list(book[SNAPSHOT].iter_rows(min_row=2,values_only=True))
        if any(len(r)!=2 or r[0]!=n or not isinstance(r[1],str) for n,r in enumerate(chunks)):raise ValueError('Invalid baseline chunks')
        baseline=json.loads(''.join(r[1] for r in chunks))
        if _hash(baseline)!=meta.get('digest'):raise ValueError('Workbook baseline was modified or corrupted')
        if any(meta.get(k)!=baseline.get(k) for k in ('version','schema','export_id','database_id')):raise ValueError('Workbook metadata does not match baseline')
        if _rows(_assets(baseline['snapshot']))!=baseline['tables']:raise ValueError('Workbook baseline relationship mismatch')
        tables=_read_flat_tables(book,baseline)
        if LONG in book:
            parts={}
            for sheet,key,field,part,text in book[LONG].iter_rows(min_row=2,values_only=True):
                if sheet in tables and key not in tables[sheet] and key in baseline['tables'][sheet]:continue
                if sheet not in tables or key not in tables[sheet] or field not in GROUPS[sheet][1] or not isinstance(part,int) or isinstance(part,bool) or part<0 or not isinstance(text,str):raise ValueError('Invalid long text reference')
                identity=(sheet,key,field)
                if part in parts.setdefault(identity,{}):raise ValueError('Duplicate long text part')
                parts[identity][part]=text
            for (sheet,key,field),values in parts.items():
                if sorted(values)!=list(range(len(values))):raise ValueError('Missing long text part')
                if tables[sheet][key][field]!='[Long Text: '+key+':'+field+']':raise ValueError('Long Text marker changed; edit the chunks instead')
                tables[sheet][key][field]=''.join(values[n] for n in range(len(values)))
        for sheet,rows in tables.items():
            for row in rows.values():
                if any(isinstance(v,str) and v.startswith('[Long Text: ') for v in row.values()):raise ValueError('Missing long text continuation')
        return meta,baseline,tables
    except (TypeError,KeyError,json.JSONDecodeError) as exc:raise ValueError('Malformed workbook metadata or structure') from exc
    finally:book.close()


def _revision(conn):
    # Covers business evidence as well as asset versions (acceptance/verification can change independently).
    return _hash(_snapshot(conn))


def _equal(a,b):
    if a in (None,'') and b in (None,''):return True
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        # Excel stores at most 15 significant decimal digits. Keep the original
        # exact database number when serialization alone rounds its tail.
        return format(a,'.15g')==format(b,'.15g')
    return a==b


def _merge(baseline,excel,current,resolutions=None):
    if resolutions and any(not isinstance(r,dict) or r.get('choice') not in ('app','excel','manual') for r in resolutions.values()):raise ValueError('Invalid conflict resolution')
    original=baseline['tables'];now=_rows(current);changes=[];conflicts=[];errors=[]
    for sheet,rows in excel.items():
        for key,row in rows.items():
            base=original[sheet].get(key)
            if base is None:
                changes.append({'key':sheet+'|'+key,'sheet':sheet,'row_key':key,'new':True,'row':row});continue
            app=now[sheet].get(key)
            edited=[f for f in GROUPS[sheet][1][2:] if not _equal(row.get(f),base.get(f))]
            if not edited:continue
            group=GROUPS[sheet][0]
            if group and not base.get(IDENTITY[group]):
                original_asset=_assets(baseline['snapshot'])[base['asset_id']]
                candidates=[i for i in original_asset.get(group,[]) if all(_equal(i.get(f),base.get(f)) for f in GROUPS[sheet][1][2:])]
                if len(candidates)>1:
                    errors.append('Ambiguous identical records without permanent IDs in '+sheet+'. Distinguish the records in the app and re-export before editing these rows offline.');continue
            if app is None:
                errors.append('Edited record no longer exists in application: '+sheet+' '+key);continue
            for field in edited:
                old=base.get(field);incoming=row.get(field);live=app.get(field)
                if _equal(incoming,live):continue
                change={'key':sheet+'|'+key+'|'+field,'sheet':sheet,'row_key':key,'asset_id':row['asset_id'],'field':field,'original':old,'excel':incoming,'application':live,'value':incoming,'new':False}
                if not _equal(live,old):
                    conflicts.append(change.copy())
                    resolution=(resolutions or {}).get(change['key'])
                    if resolution:
                        if resolution.get('choice')=='app':continue
                        if resolution.get('choice')=='manual':change['value']=resolution.get('value')
                        elif resolution.get('choice')!='excel':raise ValueError('Invalid conflict choice')
                    else:continue
                changes.append(change)
    return changes,conflicts,errors


def _materialize(current,baseline,changes,idmap):
    assets=deepcopy(current);pointers={}
    for aid,asset in assets.items():
        for sheet,(group,columns) in GROUPS.items():
            if not group:continue
            for item,key in zip(asset.get(group,[]),[k for k,r in _rows({aid:asset})[sheet].items()]):pointers[(sheet,key)]=item
    for change in sorted(changes,key=lambda c:0 if c['sheet']=='Asset Register' else 1):
        sheet=change['sheet'];group,columns=GROUPS[sheet];key=change['row_key']
        if change['new']:
            row=deepcopy(change['row']);aid=idmap.get(row['asset_id'],row['asset_id'])
            if not group:
                if row['asset_id']!=key:raise ValueError('New asset_id must equal its new: _key')
                aid=idmap[key]
                if aid in assets:continue  # repeated stale workbook: creation already committed
                assets[aid]={'id':aid,'version':0,**{f:row.get(f) for f in ASSET_FIELDS}}
                if row.get('_source_sheet'):assets[aid]['source_sheet']=row['_source_sheet']
            else:
                if aid not in assets:raise ValueError('Broken parent relationship in '+sheet)
                ident=IDENTITY[group]
                if row.get(ident):raise ValueError('Leave permanent IDs blank for new child rows')
                assigned=idmap[sheet+'|'+key]
                if any(item.get(ident)==assigned for item in assets[aid].get(group,[])):continue
                row={f:row.get(f) for f in columns[2:]};row[ident]=assigned
                assets[aid].setdefault(group,[]).append(row)
        else:
            aid=change['asset_id']
            if group:
                item=pointers[(sheet,key)];item[change['field']]=change['value']
                if group=='inspections' and not item.get('inspection_id'):item['inspection_id']=baseline['tables'][sheet][key]['inspection_id']
            else:assets[aid][change['field']]=change['value']
    for asset in assets.values():
        if not isinstance(asset.get('name'),str) or not asset['name'].strip() or not isinstance(asset.get('family'),str) or not asset['family'].strip():raise ValueError('Name and family are required')
        Store._validate_details(asset['family'],{k:v for k,v in asset.items() if k not in ('id','name','family','version')})
    # Validate child identity uniqueness database-wide, not only within a sheet.
    for group,ident in IDENTITY.items():
        seen=set()
        for asset in assets.values():
            for item in asset.get(group,[]):
                value=item.get(ident)
                # Technical field IDs are scoped to their parent asset.
                key=(asset['id'],value) if group=='technical_details' else value
                if value and key in seen:raise ValueError('Duplicate permanent identity: '+ident)
                if value:seen.add(key)
    return assets


def _idmap(conn,baseline,tables):
    result=dict(conn.execute('SELECT local_key,permanent_id FROM excel_new_ids WHERE export_id=?',(baseline['export_id'],)))
    for sheet,rows in tables.items():
        for key,row in rows.items():
            if key not in baseline['tables'][sheet]:result.setdefault(key if sheet=='Asset Register' else sheet+'|'+key,str(uuid.uuid4()))
    return result


def _creation_filter(conn,baseline,tables,changes,current):
    created=dict(conn.execute('SELECT local_key,contents FROM excel_created_rows WHERE export_id=?',(baseline['export_id'],)))
    ids=dict(conn.execute('SELECT local_key,permanent_id FROM excel_new_ids WHERE export_id=?',(baseline['export_id'],)))
    filtered=[];errors=[]
    for change in changes:
        if not change['new']:
            filtered.append(change);continue
        key=change['row_key'] if change['sheet']=='Asset Register' else change['sheet']+'|'+change['row_key']
        if key not in created:
            filtered.append(change);continue
        if _json(change['row'])!=created[key]:
            errors.append('Previously imported new row was edited in a stale workbook: '+key+'. Use the reconciled workbook with assigned permanent IDs.');continue
        permanent=ids.get(key);group=GROUPS[change['sheet']][0]
        exists=permanent in current if not group else any(item.get(IDENTITY[group])==permanent for a in current.values() for item in a.get(group,[]))
        if not exists:errors.append('Previously imported new row was removed in the application: '+key+'. Re-export and review. Do not recreate it silently.')
    return filtered,errors


def _store_preview(conn,kind,payload):
    conn.execute('DELETE FROM excel_previews WHERE kind=?',(kind,))
    token=secrets.token_urlsafe(24);conn.execute('INSERT INTO excel_previews VALUES (?,?,?)',(token,kind,payloads.dumps(payload,ensure_ascii=False,allow_nan=False)))
    return token


def _load_preview(conn,token,kind):
    row=conn.execute('SELECT contents FROM excel_previews WHERE token=? AND kind=?',(token,kind)).fetchone()
    if not row:raise ValueError('Preview expired or already applied; preview the workbook again')
    return payloads.loads(row[0])


@serialized
def preview_sync(store,path):
    meta,baseline,tables=_read(path)
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        _ensure(conn)
        identity=conn.execute('SELECT value FROM excel_identity WHERE id=1').fetchone()[0]
        issued=conn.execute('SELECT digest FROM excel_exports WHERE export_id=?',(meta['export_id'],)).fetchone()
        if identity!=meta['database_id'] or not issued or issued[0]!=meta['digest']:raise ValueError('Workbook was not exported from this database, or baseline is unrecognized. Use Recover from Excel for disaster recovery.')
        current=_assets(_snapshot(conn));changes,conflicts,errors=_merge(baseline,tables,current)
        changes,creation_errors=_creation_filter(conn,baseline,tables,changes,current);errors.extend(creation_errors)
        ids=_idmap(conn,baseline,tables)
        try:_materialize(current,baseline,changes,ids)
        except ValueError as exc:errors.append(str(exc))
        payload={'baseline':baseline,'tables':tables,'revision':_revision(conn),'idmap':ids}
        token=_store_preview(conn,'sync',payload)
    counts={name:sum(c['sheet']==name for c in changes) for name in GROUPS}
    return {'token':token,'changes':changes,'conflicts':conflicts,'errors':errors,'counts':counts,'added':sum(c['new'] for c in changes),'modified':sum(not c['new'] for c in changes),'missing_rows_retained':sum(len(set(baseline['tables'][s])-set(tables[s])) for s in GROUPS),'unchanged':sum(len(v) for v in tables.values())-len({(c['sheet'],c['row_key']) for c in changes+conflicts}),'archived':sum(c.get('field')=='record_status' and c.get('value')=='Archived' for c in changes)}


@serialized
def apply_sync(store,token,resolutions=None):
    if not isinstance(resolutions or {},dict):raise ValueError('Invalid resolutions')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        _ensure(conn);p=_load_preview(conn,token,'sync')
        if _revision(conn)!=p['revision']:raise ValueError('Application changed since preview. Preview again.')
        current=_assets(_snapshot(conn));changes,conflicts,errors=_merge(p['baseline'],p['tables'],current,resolutions)
        for conflict in conflicts:
            resolution=(resolutions or {}).get(conflict['key'])
            if not isinstance(resolution,dict) or resolution.get('choice') not in ('app','excel','manual'):raise ValueError('Resolve every conflict before applying')
        changes,creation_errors=_creation_filter(conn,p['baseline'],p['tables'],changes,current);errors.extend(creation_errors)
        if errors:raise ValueError('; '.join(errors))
        merged=_materialize(current,p['baseline'],changes,p['idmap'])
        p['applied_at']=datetime.now(timezone.utc).isoformat()
    backup=create_backup(store)
    # Prepare reconciliation output against a disposable candidate BEFORE touching the live DB.
    folder=Path(store.db_path).parent/'excel-reconciled';folder.mkdir(exist_ok=True)
    output=folder/('reconciled-'+secrets.token_hex(12)+'.xlsx')
    with tempfile.TemporaryDirectory() as directory:
        candidate=Path(directory)/'candidate.db'
        with closing(sqlite3.connect(store.db_path)) as source,closing(sqlite3.connect(candidate)) as target:source.backup(target)
        staged=Store(candidate)
        _commit_merge(staged,p,current,merged,token)
        export_full_workbook(staged,output)
        with closing(sqlite3.connect(candidate)) as c:
            issued=list(c.execute('SELECT export_id,digest FROM excel_exports'))
        try:
            _commit_merge(store,p,current,merged,token,issued)
        except BaseException:
            output.unlink(missing_ok=True);raise
    return {'applied':len(changes),'conflicts_resolved':len(conflicts),'backup':str(backup),'workbook':str(output),'download_id':output.stem,'asset_ids':p['idmap']}


def _commit_merge(store,p,current,merged,token,issued=()):
    from .validation import reconcile_import_reviews
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE');_ensure(conn)
        if _revision(conn)!=p['revision']:raise ValueError('Application changed since preview. Preview again.')
        for aid,asset in merged.items():
            before=current.get(aid)
            if before==asset:continue
            # Reconcile generated review evidence only for changed assets.
            reconcile_import_reviews(asset)
            details={k:v for k,v in asset.items() if k not in ('id','name','family','version')}
            revision=next_revision(conn)
            conn.execute('INSERT INTO assets (id,name,family,version,details) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,family=excluded.family,version=excluded.version,details=excluded.details',(aid,asset['name'],asset['family'],revision,json.dumps(details,ensure_ascii=False)))
            record_event(conn,aid,{k:v for k,v in before.items() if k not in ('id','version')} if before else None,{'name':asset['name'],'family':asset['family'],**details},'import',revision,reason='Excel three-way synchronization')
            if p.get('applied_at'):conn.execute('UPDATE correction_events SET occurred_at=? WHERE event_id=last_insert_rowid()',(p['applied_at'],))
        for sheet,rows in p['tables'].items():
            for key,row in rows.items():
                if key not in p['baseline']['tables'][sheet]:
                    local_key=key if sheet=='Asset Register' else sheet+'|'+key
                    conn.execute('INSERT OR IGNORE INTO excel_created_rows VALUES (?,?,?)',(p['baseline']['export_id'],local_key,_json(row)))
        for key,value in p['idmap'].items():conn.execute('INSERT OR IGNORE INTO excel_new_ids VALUES (?,?,?)',(p['baseline']['export_id'],key,value))
        for eid,digest in issued:conn.execute('INSERT OR IGNORE INTO excel_exports VALUES (?,?)',(eid,digest))
        conn.execute('DELETE FROM excel_previews WHERE token=?',(token,))
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Post-import database integrity check failed')


def _restore_snapshot(path,snapshot):
    with closing(sqlite3.connect(path)) as conn,conn:
        initialize_schema(conn);_ensure(conn)
        for table,data in snapshot.items():
            if table not in BUSINESS:raise ValueError('Unsupported recovery table')
            if table=='import_reference':conn.execute('CREATE TABLE IF NOT EXISTS import_reference (name TEXT PRIMARY KEY,contents TEXT NOT NULL)')
            expected=[r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            if data['columns']!=expected:raise ValueError('Unsupported recovery columns in '+table)
            conn.execute(f'DELETE FROM "{table}"')
            placeholders=','.join('?' for _ in expected)
            for row in data['rows']:
                if len(row)!=len(expected):raise ValueError('Invalid recovery row')
                conn.execute(f'INSERT INTO "{table}" VALUES ({placeholders})',[_unpack(v) for v in row])
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Recovery integrity check failed')
        if list(conn.execute('PRAGMA foreign_key_check')):raise ValueError('Recovery relationship check failed')
        # Decode every compressed business payload as part of validation.
        from .payloads import loads
        for table,columns in [('correction_events',['before_json','after_json']),('source_baselines',['contents']),('import_batches',['contents']),('import_reference',['contents'])]:
            if table not in snapshot:continue
            for row in conn.execute(f'SELECT {",".join(columns)} FROM "{table}"'):
                for value in row:loads(value)


@serialized
def preview_recovery(store,path):
    meta,baseline,tables=_read(path)
    original=_assets(baseline['snapshot']);changes,conflicts,errors=_merge(baseline,tables,original)
    # Recovery uses workbook as authority against its own baseline, never a merge with the target.
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        _ensure(conn);ids=_idmap(conn,baseline,tables)
        try:merged=_materialize(original,baseline,changes,ids)
        except ValueError as exc:raise ValueError('Recovery validation failed: '+str(exc)) from exc
        if errors:raise ValueError('; '.join(errors))
        p={'baseline':baseline,'tables':tables,'idmap':ids,'revision':_revision(conn)}
        token=_store_preview(conn,'recovery',p)
    # Prove the recovery candidate now, before offering activation.
    with tempfile.TemporaryDirectory() as directory:
        candidate=Path(directory)/'recovery.db';_restore_snapshot(candidate,baseline['snapshot'])
        staged=Store(candidate)
        with closing(sqlite3.connect(candidate)) as c:p2={**p,'revision':_revision(c)}
        _commit_merge(staged,p2,original,merged,token)
    return {'token':token,'assets':len(merged),'inspections':sum(len(a.get('inspections',[])) for a in merged.values()),'tables':{t:len(v['rows']) for t,v in baseline['snapshot'].items()},'warning':'Replaces current business database after a backup. Original source workbook files and machine backup settings require the native recovery package.'}


@serialized
def apply_recovery(store,token,confirmed=False):
    if confirmed is not True:raise ValueError('Confirm recovery activation after reviewing the preview')
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        _ensure(conn);p=_load_preview(conn,token,'recovery')
        if _revision(conn)!=p['revision']:raise ValueError('Application changed since recovery preview. Preview again.')
    original=_assets(p['baseline']['snapshot']);changes,_,errors=_merge(p['baseline'],p['tables'],original)
    if errors:raise ValueError('; '.join(errors))
    merged=_materialize(original,p['baseline'],changes,p['idmap'])
    backup=create_backup(store)
    with tempfile.TemporaryDirectory() as directory:
        candidate=Path(directory)/'recovery.db';_restore_snapshot(candidate,p['baseline']['snapshot']);staged=Store(candidate)
        with closing(sqlite3.connect(candidate)) as c:p2={**p,'revision':_revision(c)}
        _commit_merge(staged,p2,original,merged,token)
        # Restore original workbook lineage and creation mapping for subsequent sync.
        with closing(sqlite3.connect(candidate)) as c,c:
            _ensure(c);c.execute('UPDATE excel_identity SET value=? WHERE id=1',(p['baseline']['database_id'],))
            c.execute('INSERT OR REPLACE INTO excel_exports VALUES (?,?)',(p['baseline']['export_id'],_hash(p['baseline'])))
        with closing(sqlite3.connect(store.db_path)) as live, closing(sqlite3.connect(candidate)) as c,c:
            from .cleanup import _settings
            settings=_settings(live);settings['data_epoch']=secrets.token_hex(16)
            settings.update(local_success=False,independent_success=False,error='Recovered from Excel; test your independent backup destination')
            c.execute('CREATE TABLE IF NOT EXISTS backup_settings (id INTEGER PRIMARY KEY CHECK(id=1),contents TEXT NOT NULL)')
            c.execute('INSERT OR REPLACE INTO backup_settings VALUES (1,?)',(json.dumps(settings),))
            clock=live.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]
            c.execute('UPDATE version_clock SET value=MAX(value,?)',(clock+1,))
            c.execute("UPDATE import_batches SET state='cancelled' WHERE state='staged'")
            c.execute('DELETE FROM consolidation_previews')
            c.execute('DELETE FROM excel_previews')
        # SQLite backup writes a consistent candidate and handles open SQLite readers.
        with closing(sqlite3.connect(candidate)) as source,closing(sqlite3.connect(store.db_path)) as target:source.backup(target)
    return {'restored':len(merged),'backup':str(backup),'reload_required':True}

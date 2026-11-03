"""Loss-preserving export of the current plan to the linked workbook format."""
from contextlib import closing
import json
import sqlite3
import uuid
from openpyxl import Workbook
from .imports import TABLES
from .import_identity import DECISION_SHEET

HEADERS = {
 'Assets': 'asset_id asset_family asset_description tag_original asset_number_original oracle_description field plant location_from unit_or_location_to service_status_original record_status source_sequence pack_original parent_group source_group source_sheet source_row',
 'Inspection Plan': 'inspection_id asset_id inspection_type applicable last_inspection_month next_inspection_month last_inspection_status scheduling_condition condition_review_by review_status review_reason last_original next_original next_category_original source_sheet source_row last_source_cell next_source_cell',
 'Technical Details': 'asset_id field_id field_label value unit_explicit value_original source_sheet source_cell',
 'Notes & Actions': 'note_id asset_id note_type note_text source_sheet source_cell',
 'Review Items': 'review_id asset_id source_sheet source_row field original_value review_status reason',
 'Source Cells': 'source_sheet source_row source_cell asset_id row_role original_value excel_type original_annotation historical_asset_id',
 'Field Map': 'source_sheet source_column source_heading destination field_id preservation',
 'Import Decisions': 'row_key source_sheet source_row action asset_id',
}

def export_workbook(store, path):
    with closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute('BEGIN')
        rows = conn.execute('SELECT id,name,family,details FROM assets ORDER BY id').fetchall()
        has_ref = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_reference'").fetchone()
        refs = dict(conn.execute('SELECT name,contents FROM import_reference')) if has_ref else {}
        aliases = dict(conn.execute('SELECT retired_id,survivor_id FROM asset_aliases'))
    tables = {name: [] for name in TABLES}
    for asset_id, name, family, raw in rows:
        details = json.loads(raw)
        tables['Assets'].append({**details, 'asset_id': asset_id, 'asset_description': name, 'asset_family': family, 'record_status': details.get('record_status', 'Active')})
        for sheet, key, identifier in [('Inspection Plan','inspections','inspection_id'),('Technical Details','technical_details',None),('Notes & Actions','notes','note_id'),('Review Items','review_items','review_id'),('Source Cells','source_cells',None)]:
            for item in details.get(key, []):
                item = {**item, 'asset_id': asset_id}
                if identifier and not item.get(identifier): item[identifier] = str(uuid.uuid4())
                tables[sheet].append(item)
    live_ids={row[0] for row in rows}
    def normalize_reference(row):
        row=dict(row)
        original=row.get('asset_id')
        if original and original not in live_ids:
            if not row.get('historical_asset_id'):
                row['historical_asset_id']=original
            row['asset_id']=aliases.get(original) if aliases.get(original) in live_ids else None
        return row
    def unique_rows(sheet, values):
        # Compare exported fields only; omitted optional values and None are equal.
        columns=HEADERS[sheet].split()
        unique={}
        for value in values:
            row={key:value.get(key) for key in columns}
            unique[json.dumps(row,sort_keys=True,default=str,ensure_ascii=False)]=row
        return list(unique.values())
    source_rows=[normalize_reference(row) for row in tables['Source Cells']+json.loads(refs.get('Source Cells','[]'))]
    tables['Source Cells']=unique_rows('Source Cells',source_rows)
    attached={(row.get('asset_id'),row.get('review_id')) for row in tables['Review Items'] if row.get('review_id')}
    for retained in json.loads(refs.get('Review Items','[]')):
        retained=dict(retained)
        original=retained.get('asset_id')
        if original and original not in live_ids:
            retained['asset_id']=aliases.get(original) if aliases.get(original) in live_ids else None
        if (retained.get('asset_id'),retained.get('review_id')) not in attached:
            tables['Review Items'].append(retained)
    tables['Review Items']=unique_rows('Review Items',tables['Review Items'])
    tables['Field Map'] = json.loads(refs.get('Field Map', '[]'))
    if DECISION_SHEET in refs: tables[DECISION_SHEET] = json.loads(refs[DECISION_SHEET])
    book = Workbook(write_only=True)
    continuations = []
    for name in tables:
        ws = book.create_sheet(name)
        columns = HEADERS[name].split()
        ws.append(columns)
        for row_number, row in enumerate(tables[name], 2):
            # Explicit string cells prevent source values beginning with '=' becoming formulas.
            from openpyxl.cell import WriteOnlyCell
            cells = []
            for column in columns:
                value = row.get(column)
                if isinstance(value, str) and len(value)>30000:
                    for part, start in enumerate(range(0,len(value),30000)):
                        continuations.append([name,row_number,column,part,value[start:start+30000]])
                    value = '[Long value: reconstructed from Long Values sheet]'
                cell = WriteOnlyCell(ws, value=value)
                if isinstance(value, str): cell.data_type = 's'
                cells.append(cell)
            ws.append(cells)
    if continuations:
        ws=book.create_sheet('Long Values')
        ws.append(['sheet','row','column','part','text'])
        for values in continuations:
            cells=[]
            for value in values:
                cell=WriteOnlyCell(ws,value=value)
                if isinstance(value,str): cell.data_type='s'
                cells.append(cell)
            ws.append(cells)
    book.save(path)
    return path

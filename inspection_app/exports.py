"""Loss-preserving export of the current plan to the linked workbook format."""
from contextlib import closing
import json
import sqlite3
import uuid
from openpyxl import Workbook
from .imports import TABLES

HEADERS = {
 'Assets': 'asset_id asset_family asset_description tag_original asset_number_original oracle_description field plant location_from unit_or_location_to service_status_original record_status source_sequence pack_original parent_group source_group source_sheet source_row',
 'Inspection Plan': 'inspection_id asset_id inspection_type applicable last_inspection_month next_inspection_month last_inspection_status scheduling_condition review_status review_reason last_original next_original next_category_original source_sheet source_row last_source_cell next_source_cell',
 'Technical Details': 'asset_id field_id field_label value unit_explicit value_original source_sheet source_cell',
 'Notes & Actions': 'note_id asset_id note_type note_text source_sheet source_cell',
 'Review Items': 'review_id asset_id source_sheet source_row field original_value review_status reason',
 'Source Cells': 'source_sheet source_row source_cell asset_id row_role original_value excel_type original_annotation',
 'Field Map': 'source_sheet source_column source_heading destination field_id preservation',
}

def export_workbook(store, path):
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute('SELECT id,name,family,details FROM assets ORDER BY id').fetchall()
        has_ref = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_reference'").fetchone()
        refs = dict(conn.execute('SELECT name,contents FROM import_reference')) if has_ref else {}
    tables = {name: [] for name in TABLES}
    for asset_id, name, family, raw in rows:
        details = json.loads(raw)
        tables['Assets'].append({**details, 'asset_id': asset_id, 'asset_description': name, 'asset_family': family})
        for sheet, key, identifier in [('Inspection Plan','inspections','inspection_id'),('Technical Details','technical_details',None),('Notes & Actions','notes','note_id'),('Review Items','review_items','review_id')]:
            for item in details.get(key, []):
                item = {**item, 'asset_id': asset_id}
                if identifier and not item.get(identifier): item[identifier] = str(uuid.uuid4())
                tables[sheet].append(item)
    tables['Source Cells'] = json.loads(refs.get('Source Cells', '[]'))
    tables['Field Map'] = json.loads(refs.get('Field Map', '[]'))
    book = Workbook(write_only=True)
    for name in TABLES:
        ws = book.create_sheet(name)
        columns = HEADERS[name].split()
        ws.append(columns)
        for row in tables[name]:
            # Explicit string cells prevent source values beginning with '=' becoming formulas.
            from openpyxl.cell import WriteOnlyCell
            cells = []
            for column in columns:
                value = row.get(column)
                cell = WriteOnlyCell(ws, value=value)
                if isinstance(value, str): cell.data_type = 's'
                cells.append(cell)
            ws.append(cells)
    book.save(path)
    return path

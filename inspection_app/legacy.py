"""Adapter for the recognized original Master Inspection Plan layout.

Mappings contain headings only, never source asset data. Workbook text is data.
"""
from contextlib import ExitStack
from datetime import date, datetime
import json
from pathlib import Path
import re
import warnings

import openpyxl
from openpyxl.utils import get_column_letter


LAYOUTS = json.loads(Path(__file__).with_name('legacy_layouts.json').read_text(encoding='utf-8'))
TABLES = ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells', 'Field Map')
REFERENCES = {'DWG', 'Coolers', 'Insulated Piping', 'OP Dead Legs', 'GP Dead Legs',
              'GP Inlet Lines', 'FF', 'Temp-Repair', 'Critical Assets', 'Evaluation Criteria',
              'Inspection Sequence', 'Anodes Reporting& As-Found Insp',
              'API-574 Tables & Pipe Sch', 'HT Press Tables'}
CONFIG = {
    'Vessels & TKs': (1, 'Vessel / tank', {'B': 'source_sequence', 'C': 'field', 'D': 'plant', 'E': 'location_from', 'F': 'unit_or_location_to', 'G': 'asset_description', 'H': 'tag_original', 'I': 'asset_number_original', 'J': 'oracle_description', 'K': 'service_status_original'}, [('OSI', 'N', 'O'), ('Internal', 'P', 'Q')]),
    'OP Piping': (2, 'Piping', {'B': 'source_sequence', 'C': 'asset_description'}, [('OSI', 'G', 'H')]),
    'GP Piping': (3, 'Piping', {'B': 'source_sequence', 'C': 'asset_description', 'D': 'pack_original'}, [('OSI', 'I', 'J')]),
    'Turbines Piping': (4, 'Piping', {'B': 'source_sequence', 'C': 'asset_description', 'D': 'pack_original'}, [('OSI', 'H', 'I')]),
    'WD-33 Piping': (5, 'Piping', {'B': 'source_sequence', 'C': 'asset_description', 'D': 'service_status_original', 'E': 'location_from', 'F': 'pack_original'}, [('OSI', 'I', 'J')]),
    'EPFs': (6, 'Piping', {'B': 'source_sequence', 'C': 'asset_description', 'D': 'service_status_original'}, [('OSI', 'G', 'H')]),
    'MFDs': (7, 'Manifold', {'A': 'source_sequence', 'B': 'asset_description'}, [('OSI', 'G', 'H')]),
    'TLs': (8, 'Trunkline', {'B': 'location_from', 'C': 'unit_or_location_to', 'D': 'asset_description', 'E': 'service_status_original'}, [('OSI', 'T', 'U')]),
    'FLs': (9, 'Flowline', {'A': 'asset_description', 'B': 'service_status_original'}, [('OSI', 'I', 'J')]),
    'GL Lines': (10, 'Gas lift line', {'B': 'source_sequence', 'C': 'asset_description'}, [('OSI', 'M', 'N')]),
}


def normalized(value):
    return re.sub(r'\s+', ' ', str(value if value is not None else '').strip()).casefold()


def heading(value):
    return re.sub(r'[^a-z0-9]', '', normalized(value))


def original(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def role(name):
    return 'assets' if name in CONFIG else 'reference' if name.strip() in REFERENCES else 'unsupported'


def inspect_workbook(path):
    with open(path, 'rb') as source:
        book = openpyxl.load_workbook(source, read_only=True, data_only=True)
        try:
            names = book.sheetnames
            clean = 'Assets' in names or 'Inspection Plan' in names
            if not clean and not any(role(name) != 'unsupported' for name in names):
                raise ValueError('Unrecognized workbook layout. Choose the original Master Inspection Plan or a cleaned export.')
            return {'format': 'cleaned' if clean else 'legacy',
                    'sheets': [{'name': name, 'role': 'linked' if clean else role(name)} for name in names]}
        finally:
            book.close()


from .months import parse_month

def date_status(value, last=False):
    if parse_month(value): return 'Dated'
    text = normalized(value)
    if last and text in ('never', 'not inspected', 'never inspected'): return 'Never inspected'
    if text in ('na', 'n/a', 'not applicable'): return 'Not applicable'
    if text in ('oos', 'out of service'): return 'OOS'
    if not last and (text.startswith('w/eval') or 'waiting evaluation' in text): return 'Awaiting evaluation'
    if not last and text in ('next sd', 'sd', 'next shutdown'): return 'At next shutdown'
    return str(value).strip() if value is not None else 'Undated'


def find_header(sheet, fields):
    # All mapped headings must remain in their verified columns. Multi-row TL/GL
    # headings are explicitly checked; moved/unknown layouts are rejected.
    checks = [(f['source_column'], f['source_heading']) for f in fields
              if f['source_heading'] and not f['source_heading'].startswith('Column ')]
    if sheet.title == 'TLs': checks = [(c, h) for c, h in checks if c not in ('B', 'C')]
    for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 40)):
        n = row[0].row
        if all(heading(sheet[f'{c}{n}'].value) == heading(h) for c, h in checks):
            if sheet.title == 'TLs':
                if heading(sheet[f'B{n+1}'].value) != 'from' or heading(sheet[f'C{n+1}'].value) != 'to':
                    continue
                return n + 1
            return n
    raise ValueError(f'{sheet.title}: unsupported header layout; expected the original columns. Exclude this tab or restore its headings.')


def is_asset(name, values):
    def v(col): return values.get(col)
    if name == 'Vessels & TKs': return any(v(c) not in (None, '') for c in ('G', 'H', 'I', 'J'))
    if name == 'FLs': return bool(v('A'))
    if name == 'TLs': return bool(v('D'))
    if name == 'MFDs': return bool(v('B')) and (isinstance(v('A'), (int, float)) or any(v(c) is not None for c in ('G', 'H')))
    return bool(v('C')) and (isinstance(v('B'), (int, float)) or bool(re.fullmatch(r'(?:\d+[a-z]?(?:\.\d+)?|xx)', str(v('B') or '').strip(), re.I)))


def read_legacy(path, selected_sheets=None):
    info = inspect_workbook(path)
    names = [s['name'] for s in info['sheets']]
    selected = names if selected_sheets is None else selected_sheets
    if not isinstance(selected, list) or not selected or any(not isinstance(n, str) or n not in names for n in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select at least one valid workbook tab, without duplicates.')
    selected = [name for name in names if name in selected]
    unknown = [name for name in selected if role(name) == 'unsupported']
    if unknown: raise ValueError('Unsupported tabs: ' + ', '.join(unknown) + '. Exclude these tabs before previewing.')
    data = {name: [] for name in TABLES}
    summaries = []
    with ExitStack() as stack:
        formula_source = stack.enter_context(open(path, 'rb'))
        cached_source = stack.enter_context(open(path, 'rb'))
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='wmf image format is not supported.*')
            formulas = openpyxl.load_workbook(formula_source, data_only=False)
        cached = openpyxl.load_workbook(cached_source, read_only=True, data_only=True)
        stack.callback(formulas.close)
        stack.callback(cached.close)
        for name in selected:
            sheet = formulas[name]
            if sheet.max_row * sheet.max_column > 200000:
                raise ValueError(f'{name}: worksheet is too large for this original layout.')
            values_by_cell = {cell.coordinate: cell.value for row in cached[name] for cell in row if cell.value is not None}
            fields = LAYOUTS.get(name, [])
            header = find_header(sheet, fields) if name in CONFIG else sheet.max_row
            start_assets, start_inspections = len(data['Assets']), len(data['Inspection Plan'])
            if name in CONFIG:
                code, family, mapping, inspections = CONFIG[name]
                data['Field Map'].extend({'source_sheet': name, **f, 'preservation': 'Selected original cells preserved in Source Cells'} for f in fields)
            parent = group = None
            if name == 'EPFs':
                # Area titles precede each repeated table; "MOP" is a pressure
                # heading, never an area. The first title precedes the header.
                for pre_row in sheet.iter_rows(max_row=header - 1):
                    title = pre_row[4].value if len(pre_row) > 4 else None
                    if title: group = str(title)
            group_notes = []
            # Propagate explicitly merged data cells only, never arbitrary blanks.
            merged = {}
            section_rows = set()
            for area in sheet.merged_cells.ranges:
                if area.min_row <= header or area.max_row * area.max_col > 200000: continue
                identity_col = {'Vessels & TKs': 7, 'FLs': 1, 'TLs': 4}.get(name)
                if identity_col and area.min_col == identity_col and area.max_col > identity_col:
                    section_rows.update(range(area.min_row, area.max_row + 1))
                anchor = sheet.cell(area.min_row, area.min_col).coordinate
                for row in range(area.min_row, area.max_row + 1):
                    for col in range(area.min_col, area.max_col + 1): merged[(row, col)] = anchor
            coverage=[]
            for row in sheet:
                n = row[0].row
                row_kind='reference' if name not in CONFIG else 'header' if n<=header else 'unclassified'
                values = {}
                for cell in row:
                    coordinate = merged.get((n, cell.column), cell.coordinate)
                    values[get_column_letter(cell.column)] = values_by_cell.get(coordinate)
                asset = None
                repeated_header = name in CONFIG and n > header and any(heading(values.get(c)) == heading(label) for c, label in [('C', 'Item'), ('G', 'Asset Name'), ('A', 'Well'), ('D', 'Pipeline Name'), ('C', 'Gas Lift Line')])
                if repeated_header or n in section_rows:row_kind='context'
                if name in CONFIG and n > header and n not in section_rows and not repeated_header and is_asset(name, values):
                    row_kind='asset'
                    asset_id = f'A{code:02d}-{n:04d}'
                    asset = {'asset_id': asset_id, 'asset_family': family, 'record_status': 'Active', 'source_sheet': name, 'source_row': n, 'parent_group': parent, 'source_group': group}
                    asset.update({key: original(values.get(col)) for col, key in mapping.items()})
                    if name == 'EPFs': asset['location_from'] = group
                    data['Assets'].append(asset)
                    for kind, last_col, next_col in inspections:
                        last, nxt = values.get(last_col), values.get(next_col)
                        last_original = sheet[f'{last_col}{n}'].value
                        next_original = sheet[f'{next_col}{n}'].value
                        applicable = 'No' if normalized(last) in ('na', 'n/a', 'not applicable') and normalized(nxt) in ('na', 'n/a', 'not applicable') else 'Yes'
                        item = {'inspection_id': asset_id + '-' + kind.upper(), 'asset_id': asset_id, 'inspection_type': kind, 'applicable': applicable, 'last_inspection_month': parse_month(last), 'next_inspection_month': parse_month(nxt), 'last_inspection_status': date_status(last, True), 'scheduling_condition': date_status(nxt), 'last_original': original(last_original), 'next_original': original(next_original), 'next_category_original': values.get('R') if name == 'Vessels & TKs' and kind == 'OSI' else None, 'source_sheet': name, 'source_row': n, 'last_source_cell': f'{last_col}{n}', 'next_source_cell': f'{next_col}{n}'}
                        reasons = []
                        for label, val, raw in [('last inspection', last, last_original), ('next inspection', nxt, next_original)]:
                            if applicable == 'Yes' and not parse_month(val):
                                reason = 'No unambiguous month; original value retained for review.'
                                reasons.append(f'{label}: {reason}')
                                data['Review Items'].append({'review_id': f'{asset_id}-{kind}-{label}', 'asset_id': asset_id, 'source_sheet': name, 'source_row': n, 'field': f'{kind}: {label}', 'original_value': original(raw), 'review_status': 'Review', 'reason': reason})
                        last_month, next_month = item['last_inspection_month'], item['next_inspection_month']
                        if applicable == 'Yes' and last_month and next_month and next_month < last_month:
                            reason = 'Next inspection precedes last inspection; verify the original dates. No correction was inferred.'
                            reasons.append(reason)
                            data['Review Items'].append({'review_id': f'{asset_id}-{kind}-chronology', 'asset_id': asset_id, 'source_sheet': name, 'source_row': n, 'field': f'{kind}: date order', 'original_value': f'{original(last_original)} → {original(next_original)}', 'review_status': 'Review', 'reason': reason})
                        if reasons: item.update(review_status='Review', review_reason=' '.join(reasons))
                        data['Inspection Plan'].append(item)
                    for f in fields:
                        col = f['source_column']; val = values.get(col)
                        if val is None: continue
                        common = {'asset_id': asset_id, 'source_sheet': name, 'source_cell': f'{col}{n}'}
                        if f['destination'] == 'Technical Details':
                            data['Technical Details'].append({**common, 'field_id': f['field_id'], 'field_label': f['source_heading'] or f'Column {col}', 'value': original(val), 'value_original': original(sheet[f'{col}{n}'].value), 'unit_explicit': None})
                        elif f['destination'] == 'Notes & Actions':
                            data['Notes & Actions'].append({**common, 'note_id': f'{asset_id}-{col}', 'note_type': f['source_heading'], 'note_text': str(val)})
                    for note in group_notes:
                        data['Notes & Actions'].append({**note, 'asset_id': asset_id, 'note_id': f'{asset_id}-section-{note["source_cell"]}'})
                elif name in CONFIG and n > header and not repeated_header:
                    label = values.get('B')
                    if name in ('OP Piping', 'GP Piping', 'Turbines Piping') and isinstance(label, str) and label.strip():
                        row_kind='context'
                        group = label
                        if re.match(r'\s*PACK\s*\d+(?:\s|[-—]|$)', label, re.I): parent = label
                        group_notes = [{'source_sheet': name, 'source_cell': f'B{n}', 'note_type': 'Section note', 'note_text': label}]
                    elif name == 'EPFs' and values.get('E') and not values.get('C') and n > header:
                        row_kind='context'
                        group = str(values['E'])
                        group_notes = [{'source_sheet': name, 'source_cell': f'E{n}', 'note_type': 'Section note', 'note_text': group}]
                # Keep all populated cells/comments, including headings, reference tabs,
                # and unclassified notes, without pretending they describe assets.
                if any(cell.value is not None or cell.comment is not None for cell in row):coverage.append({'row':n,'classification':row_kind})
                for cell in row:
                    if cell.value is None and cell.comment is None: continue
                    annotation = None
                    if cell.data_type == 'f' or cell.comment:
                        annotation = json.dumps({'cached_value': original(values_by_cell.get(cell.coordinate)) if cell.data_type == 'f' else None, 'comment': {'text': cell.comment.text, 'author': cell.comment.author} if cell.comment else None}, ensure_ascii=False)
                    data['Source Cells'].append({'source_sheet': name, 'source_row': n, 'source_cell': cell.coordinate, 'asset_id': asset['asset_id'] if asset else None, 'row_role': row_kind, 'original_value': original(cell.value), 'excel_type': cell.data_type, 'original_annotation': annotation})
            summaries.append({'name': name, 'role': role(name), 'assets': len(data['Assets']) - start_assets, 'inspections': len(data['Inspection Plan']) - start_inspections,'populated_rows':len(coverage),'row_accounting':coverage,'unclassified_rows':[r['row'] for r in coverage if r['classification']=='unclassified']})
    return data, {'format': 'legacy', 'included_sheets': selected, 'excluded_sheets': [n for n in names if n not in selected], 'sheet_summary': summaries, 'partial': len(selected) != len(names), 'warnings': ['Uncertain or missing inspection months are retained as review items; no dates were invented.'] if data['Review Items'] else []}

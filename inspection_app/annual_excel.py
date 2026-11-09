"""Offline, report-only Excel inspection plans built from current application rules.

A report is a dated snapshot, never an authoritative synchronization artifact.
All counts represent independent OSI/Internal obligations, not asset counts.
"""
from calendar import month_abbr, month_name
from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
import re
from pathlib import Path
import sqlite3
import tempfile

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.views import Selection
from openpyxl.utils import get_column_letter

from .months import due_bucket, validate_month
from .register import read_summaries, matches_summary
from .store import serialized

from .excel_style import NAVY, BLUE, RED, configure_month_chart
HEADERS = ['Permanent asset ID', 'Equipment tag / number', 'Description', 'Equipment type',
           'Area / location', 'Inspection type', 'Last inspection month', 'Next inspection month',
           'Scheduled planning month', 'Condition', 'Applicable', 'Planning status',
           'Inspection notes / remarks', 'Source reference', 'Permanent inspection ID']
WIDTHS = [25, 22, 42, 20, 26, 17, 18, 18, 18, 28, 14, 24, 58, 30, 25]


def _options(options, require_year=True):
    if options is None: options = {}
    if not isinstance(options, dict): raise ValueError('Report options must be an object')
    result = dict(options)
    result['_asset_report']=False
    raw = options.get('year', date.today().year)
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise ValueError('Planning year must be between 1 and 9999')
    if isinstance(raw, str) and not raw.isdigit():
        raise ValueError('Planning year must be between 1 and 9999')
    year = int(raw)
    if not 1 <= year <= 9999: raise ValueError('Planning year must be between 1 and 9999')
    result['year'] = year
    result['inspection_type'] = options.get('inspection_type') or ''
    if result['inspection_type'] not in ('', 'OSI', 'Internal'):
        raise ValueError('Inspection type must be OSI, Internal, or both')
    result['reference_month'] = validate_month(options.get('reference_month') or date.today().strftime('%Y-%m'))
    for key, default in [('include_overdue', True), ('include_unscheduled', True),
                         ('monthly_sheets', False), ('include_summary', True)]:
        result[key] = options.get(key, default)
        if not isinstance(result[key], bool): raise ValueError(key+' must be true or false')
    for key in ('area', 'family', 'tag', 'source_sheet'):
        result[key] = options.get(key) or ''
        if not isinstance(result[key], str): raise ValueError(key+' must be text')
    return result


def _snapshot(store):
    # Derived review statuses and accepted exceptions are exactly those used by
    # the application's register; source evidence remains in SQLite unchanged.
    with closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute('BEGIN')
        return read_summaries(conn)


def _in_scope(asset, options, include_archived=False):
    if not include_archived and asset.get('record_status') == 'Archived': return False
    if options['area'] and asset.get('location_from') != options['area']: return False
    if options['family'] and asset.get('family') != options['family']: return False
    sheet = options['source_sheet']
    if sheet and (bool(asset.get('source_sheet')) if sheet == '__manual__' else asset.get('source_sheet') != sheet):
        return False
    if options['tag']:
        tags = ' '.join(str(asset.get(key) or '') for key in ('tag_original', 'asset_number_original', 'name'))
        if options['tag'].casefold() not in tags.casefold(): return False
    return True


def _scope_text(options):
    fields = [('Year', str(options['year'])), ('Reference month', options['reference_month']),
              ('Inspection', options['inspection_type'] or 'OSI + Internal'),
              ('Area / location', options['area'] or 'All'), ('Asset family', options['family'] or 'All'),
              ('Tag / equipment search', options['tag'] or 'All'), ('Source sheet', options['source_sheet'] or 'All')]
    if options.get('_asset_report'):fields=fields[3:]
    scope = '; '.join(key+': '+value for key, value in fields)
    if options.get('filters'): scope += '; Register filters: '+json.dumps(options['filters'],ensure_ascii=False,sort_keys=True)
    return scope


def _source(asset, inspection):
    sheet = inspection.get('source_sheet') or asset.get('source_sheet')
    row = inspection.get('source_row') or asset.get('source_row')
    return str(sheet or '') + ((' · row '+str(row)) if row is not None else '')


def _record(asset, inspection, status, planned):
    remarks = '\n'.join(str(n.get('note_text')) for n in asset.get('notes', []) if n.get('note_text') is not None)
    if inspection.get('review_reason'):
        remarks += ('\n' if remarks else '') + str(inspection['review_reason'])
    return [asset['id'], asset.get('tag_original') or asset.get('asset_number_original'), asset['name'],
            asset['family'], asset.get('location_from'), inspection.get('inspection_type'),
            inspection.get('last_inspection_month'), inspection.get('next_inspection_month'), planned,
            inspection.get('scheduling_condition') or inspection.get('last_inspection_status'),
            inspection.get('applicable'), status, remarks, _source(asset, inspection),
            inspection.get('inspection_id')]


def planning_records(assets, options):
    """Return scheduled, overdue, unresolved records and reconciled monthly counts."""
    scheduled, overdue, unresolved = [], [], []
    year = f"{options['year']:04d}"
    for asset in assets:
        if not _in_scope(asset, options): continue
        for inspection in asset.get('inspections', []):
            if inspection.get('applicable') != 'Yes': continue
            if options['inspection_type'] and inspection.get('inspection_type') != options['inspection_type']: continue
            due = inspection.get('next_inspection_month')
            if inspection.get('review_status') == 'Review':
                unresolved.append(_record(asset, inspection, 'Needs review', None))
                continue
            bucket = due_bucket(due, options['reference_month'], True, False)
            if due and due[:4] == year:
                status = 'Overdue' if bucket == 'overdue' else 'Due this month' if bucket == 'due_this_month' else 'Scheduled'
                scheduled.append(_record(asset, inspection, status, due))
            if bucket == 'overdue': overdue.append(_record(asset, inspection, 'Overdue', None))
            if bucket == 'undated':
                unresolved.append(_record(asset, inspection, 'Condition-based / undated', None))
    scheduled.sort(key=lambda r: (r[8], str(r[1] or ''), r[0], str(r[5])))
    overdue.sort(key=lambda r: (r[7], r[0], str(r[5])))
    unresolved.sort(key=lambda r: (r[0], str(r[5])))
    distribution = []
    for month in range(1, 13):
        due = f'{year}-{month:02d}'
        counts = [sum(row[8] == due and row[5] == kind for row in scheduled) for kind in ('OSI', 'Internal')]
        distribution.append([month_name[month], *counts, sum(counts)])
    return scheduled, overdue, unresolved, distribution


def _text(ws, row, column, value):
    if value is None: return
    cell = ws.cell(row, column, value)
    if isinstance(value, str): cell.data_type = 's'
    return cell


def _base_sheet(book, name, title, scope, widths):
    ws = book.create_sheet(name)
    end = max(len(widths), 4)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=end)
    _text(ws, 1, 1, title)
    _text(ws, 2, 1, scope)
    _text(ws, 3, 1, 'REPORT ONLY · Dated application snapshot · Not for database re-import or recovery')
    ws['A1'].font = Font(name='Calibri', size=19, bold=True, color='FFFFFF')
    ws['A1'].fill = PatternFill('solid', fgColor=NAVY)
    ws['A2'].font = Font(name='Calibri', size=10, color=NAVY)
    ws['A2'].alignment = Alignment(wrap_text=True, vertical='top')
    ws['A3'].font = Font(name='Calibri', size=10, italic=True, color='595959')
    ws.row_dimensions[1].height = 32
    ws.row_dimensions[2].height = 42
    ws.row_dimensions[3].height = 23
    for index, width in enumerate(widths, 1): ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = 'C6'
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3 if len(widths) > 10 else ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 0 if len(widths) > 10 else 1
    ws.page_setup.fitToHeight = 0
    if len(widths) > 10:
        # Keep eleven-point report text readable across horizontal pages rather
        # than shrinking fifteen columns onto a single illegible page.
        ws.page_setup.scale = 85
        ws.sheet_properties.pageSetUpPr.fitToPage = False
        ws.print_title_cols = 'A:C'
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.oddHeader.center.text = title
    ws.oddFooter.left.text = 'Inspection management · Report snapshot'
    ws.oddFooter.right.text = 'Page &P of &N'
    ws.print_title_rows = '5:5'
    return ws


def _table(book, name, title, options, columns, rows, widths, empty='No scheduled inspections'):
    ws = _base_sheet(book, name, title, _scope_text(options), widths)
    for col, heading in enumerate(columns, 1):
        cell = _text(ws, 5, col, heading)
        cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor=NAVY)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[5].height = 32
    for row_number, values in enumerate(rows, 6):
        for col, value in enumerate(values, 1):
            if isinstance(value, str) and len(value) > 32767:
                # Excel has a fixed cell limit; preserve complete report text in
                # numbered chunks with stable asset/inspection references.
                if 'Full Report Text' not in book:
                    full = book.create_sheet('Full Report Text')
                    full.append(['Report sheet', 'Asset ID', 'Inspection ID', 'Column', 'Part', 'Text'])
                full = book['Full Report Text']
                for part, start in enumerate(range(0, len(value), 30000), 1):
                    for c, v in enumerate([name, values[0], values[-1], columns[col-1], part, value[start:start+30000]], 1):
                        _text(full, full.max_row+1 if c == 1 else full.max_row, c, v)
                value = value[:32000]+'\n[Complete text in Full Report Text]'
            cell = _text(ws, row_number, col, value)
            if cell is not None:
                cell.font = Font(name='Calibri', size=11)
                cell.alignment = Alignment(wrap_text=True, vertical='top')
                if row_number % 2 == 0: cell.fill = PatternFill('solid', fgColor='F0F4F8')
        ws.row_dimensions[row_number].height = 48
    if rows:
        ref = f'A5:{get_column_letter(len(columns))}{5+len(rows)}'
        table = Table(displayName='ReportTable'+str(len(book.sheetnames)), ref=ref)
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        ws.add_table(table)
        if 'Planning status' in columns:
            col = get_column_letter(columns.index('Planning status')+1)
            ws.conditional_formatting.add(f'{col}6:{col}{5+len(rows)}',
                CellIsRule(operator='equal', formula=['"Overdue"'], fill=PatternFill('solid', fgColor=RED)))
    else: _text(ws, 6, 1, empty)
    ws.print_area = f'A1:{get_column_letter(len(columns))}{max(6,5+len(rows))}'
    return ws


def _overview(book, options, scheduled, overdue, unresolved, distribution, title=None):
    ws = _base_sheet(book, '01 - Annual Overview', title or f"Annual Inspection Plan · {options['year']}",
                     _scope_text(options), [34, 19, 19, 19, 19, 19, 19, 19])
    kpis = [('Total scheduled obligations',len(scheduled)), ('OSI obligations',sum(r[5]=='OSI' for r in scheduled)),
            ('Internal obligations',sum(r[5]=='Internal' for r in scheduled)), ('Outstanding overdue',len(overdue)),
            ('Applicable undated / review',len(unresolved)),
            ('Generated (UTC)',datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))]
    for row_number, (label, value) in enumerate(kpis, 5):
        _text(ws,row_number,1,label); _text(ws,row_number,2,value)
        ws.cell(row_number,1).font=Font(name='Calibri',bold=True,color=NAVY)
    for col, value in enumerate(['Month','OSI','Internal','Total'],1):
        _text(ws,13,col,value);ws.cell(13,col).font=Font(bold=True,color='FFFFFF');ws.cell(13,col).fill=PatternFill('solid',fgColor=NAVY)
    for row_number, row in enumerate(distribution,14):
        for col, value in enumerate(row,1): _text(ws,row_number,col,value)
    chart=BarChart();chart.title='Monthly inspection distribution';chart.y_axis.title='Obligations';chart.x_axis.title='Planning month'
    chart.add_data(Reference(ws,min_col=2,max_col=3,min_row=13,max_row=25),titles_from_data=True)
    chart.set_categories(Reference(ws,min_col=1,min_row=14,max_row=25));chart.height=10;chart.width=20
    configure_month_chart(chart,Reference(ws,min_col=1,min_row=14,max_row=25))
    ws.add_chart(chart,'F13')
    _text(ws,27,1,'Overdue totals use the reference month; obligations become overdue only after their due month ends.')
    _text(ws,28,1,'Prior-year overdue obligations remain outside selected-year totals. Current-year overdue may appear in both registers.')
    _text(ws,29,1,'Undated and unresolved obligations are excluded from scheduled totals. Counts are independent inspections.')
    _text(ws,30,1,'Optional detail-sheet exclusions do not change the overview KPI scope.')
    for row in range(27,31):
        ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=8)
        ws.cell(row,1).alignment=Alignment(wrap_text=True);ws.row_dimensions[row].height=28
    ws.print_area='A1:M31'
    ws.freeze_panes='A5'
    ws.sheet_view.selection=[Selection(pane='bottomLeft',activeCell='A5',sqref='A5')]
    return ws


def _notes(book, options):
    rows=[['Report purpose','Standalone dated snapshot for inspection planning and management reporting.'],
          ['Planning year',str(options['year'])], ['Reference month',options['reference_month']],
          ['Scope',_scope_text(options)],
          ['Scheduling','Only applicable inspections on active assets with a current valid next month and no current inspection review blocker enter the schedule.'],
          ['Month precision','YYYY-MM. An inspection is overdue only when its due month is earlier than the reference month.'],
          ['Overdue separation','The selected-year register excludes all previous-year obligations. The overdue register covers all prior due months in scope; current-year overdue can appear in both.'],
          ['Undated / review','Includes condition-based undated obligations and current review findings. Unknown dates are never treated as overdue.'],
          ['Service conditions','Raw service text and recorded conditions are preserved. Applicability and archive status follow current application logic; no engineering exclusion is inferred from free text.'],
          ['Source evidence','Available sheet and row references are shown. This report is not a source archive or a full database recovery artifact.'],
          ['Editing','Manual annotations or edits to this report are not authoritative database edits. Use Export Editable Database for synchronization.'],
          ['Print layout','A3 landscape for detailed registers; repeated table headings. Adjust printer settings or hide selected columns if your printer only supports A4.'],
          ['Preparation / review','Prepared by: __________________    Reviewed by: __________________    Approval (if applicable): __________________'],
          ['Approval status','Blank fields do not imply approval, safety certification, or regulatory acceptance.']]
    _table(book,'06 - Planning Notes','Planning Notes',options,['Topic','Definition / information'],rows,[32,120])


def _metadata(book, kind, options, count):
    ws=book.create_sheet('Report Metadata')
    for row in [['Key','Value'],['export_type',kind],['workbook_version',1],
                ['generated_utc',datetime.now(timezone.utc).isoformat()],['scope',_scope_text(options)],
                ['scheduled_obligations',count],['reimport','Not supported; report only']]:
        index=ws.max_row+1 if ws.max_row>1 or ws['A1'].value is not None else 1
        for col,value in enumerate(row,1):_text(ws,index,col,value)
    ws.column_dimensions['A'].width=28;ws.column_dimensions['B'].width=110
    ws.protection.sheet=True


def _save(book,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.inspection-report-',suffix='.xlsx',dir=path.parent)
    os.close(fd)
    try:
        book.save(temp)
        os.replace(temp,path)
    finally:
        book.close()
        Path(temp).unlink(missing_ok=True)
    return path


def _source_plan_tabs(book, options, assets, records):
    """Present selected obligations together on each asset's original source tab."""
    selected = {}
    for record in records:
        selected.setdefault(record[0], {})[record[5]] = record
    groups = {}
    for asset in assets:
        if asset['id'] in selected:
            groups.setdefault(asset.get('source_sheet') or 'Unassigned', []).append(asset)
    columns = ['Asset name', 'Tag / equipment number', 'Location', 'Service status',
               'OSI · last month', 'OSI · next month', 'OSI · condition', 'OSI · planning status',
               'Internal · last month', 'Internal · next month', 'Internal · condition',
               'Internal · planning status', 'Notes / actions', 'Technical details', 'Permanent asset ID']
    tabs = []
    for source, members in groups.items():
        stem = re.sub(r'[\\/*?:\[\]]', ' ', source).strip().strip("'") or 'Unassigned'
        name = stem[:31]; suffix = 1
        while name.casefold() in {n.casefold() for n in book.sheetnames}:
            suffix += 1; tail = f' ({suffix})'; name = stem[:31-len(tail)] + tail
        rows = []
        for asset in members:
            obligations = selected[asset['id']]
            row = [asset['name'], asset.get('tag_original') or asset.get('asset_number_original'),
                   asset.get('location_from'), asset.get('service_status_original')]
            for kind in ('OSI', 'Internal'):
                obligation = obligations.get(kind)
                row.extend([obligation[i] for i in (6, 7, 9, 11)] if obligation else [None]*4)
            notes = '\n'.join(str(n.get('note_text') or '') for n in asset.get('notes', []))
            technical = '\n'.join(f"{t.get('field_label') or t.get('field_id')}: {t.get('value', '')} {t.get('unit_explicit') or ''}".rstrip() for t in asset.get('technical_details', []))
            rows.append(row + [notes, technical, asset['id']])
        ws = _table(book, name, f"{source} · {options['year']} inspection plan", options,
                    columns, rows, [36,22,24,18,15,15,28,22,15,15,28,22,55,42,25])
        ws.column_dimensions['O'].hidden = True
        ws.freeze_panes = 'C6'; ws.sheet_view.zoomScale = 85
        ws.sheet_properties.tabColor = '4B9798'
        tabs.append(ws)
    # Source tabs are the primary working view after the overview.
    book._sheets = [book.worksheets[0]] + tabs + [ws for ws in book.worksheets[1:] if ws not in tabs]


@serialized
def export_annual_workbook(store,path,options=None):
    """Export a professional standalone annual snapshot; no full workbook needed."""
    options=_options(options)
    assets = _snapshot(store)
    scheduled,overdue,unresolved,distribution=planning_records(assets,options)
    book=Workbook();book.remove(book.active)
    _overview(book,options,scheduled,overdue,unresolved,distribution)
    _table(book,'02 - Master Annual Plan',f"Master Annual Inspection Plan · {options['year']}",options,HEADERS,scheduled,WIDTHS)
    if options['include_summary']:
        _table(book,'03 - Monthly Schedule',f"Monthly Inspection Schedule · {options['year']}",options,
               ['Month','OSI','Internal','Total'],distribution,[28,18,18,18])
    if options['include_overdue'] and overdue:
        _table(book,'04 - Overdue Inspections','Outstanding Overdue Inspections',options,HEADERS,overdue,WIDTHS)
    if options['include_unscheduled'] and unresolved:
        _table(book,'05 - Unscheduled Review','Applicable Unscheduled / Review Items',options,HEADERS,unresolved,WIDTHS)
    _notes(book,options)
    if options['monthly_sheets']:
        for month in range(1,13):
            rows=[r for r in scheduled if r[8]==f"{options['year']:04d}-{month:02d}"]
            _table(book,month_abbr[month],f"{month_name[month]} {options['year']} · {len(rows)} scheduled obligations",
                   options,HEADERS,rows,WIDTHS)
    records = scheduled + (overdue if options['include_overdue'] else []) + (unresolved if options['include_unscheduled'] else [])
    _source_plan_tabs(book, options, assets, records)
    _metadata(book,'annual_report',options,len(scheduled))
    return _save(book,path)


@serialized
def export_filtered_workbook(store,path,options=None):
    """Export selected current register rows, explicitly report-only."""
    options=_options(options,False)
    options['_asset_report']=True
    filters=options.get('filters')
    if filters is not None and not isinstance(filters,dict):raise ValueError('Register filters must be an object')
    include_archived=bool(filters and filters.get('status') in ('all','archived'))
    assets=[a for a in _snapshot(store) if _in_scope(a,options,include_archived)]
    # Also accept the application's existing register filters for direct export.
    filters=options.get('filters')
    if filters is not None:
        if not isinstance(filters,dict):raise ValueError('Register filters must be an object')
        assets=[a for a in assets if matches_summary(a,filters)]
    rows=[[a['id'],a.get('tag_original'),a.get('asset_number_original'),a['name'],a['family'],a.get('location_from'),
           a.get('field'),a.get('plant'),a.get('service_status_original'),a.get('record_status','Active'),
           a.get('source_sheet'),a.get('source_row'),a.get('quality_status'),
           '\n'.join(str(n.get('note_text') or '') for n in a.get('notes',[]))] for a in assets]
    book=Workbook();book.remove(book.active)
    _table(book,'Asset Register','Filtered Asset Register',options,
           ['Permanent asset ID','Tag','Asset number','Description','Asset family','Area / location','Field','Plant',
            'Service status','Record status','Source sheet','Source row','Quality status','Notes'],rows,
           [25,22,22,42,20,26,18,18,24,18,24,14,24,58],empty='No assets match these filters')
    _metadata(book,'filtered_register',options,len(rows))
    return _save(book,path)


@serialized
def export_management_workbook(store,path,options=None):
    """Export management KPIs/charts without an editable database or schedule."""
    options=_options(options)
    scheduled,overdue,unresolved,distribution=planning_records(_snapshot(store),options)
    book=Workbook();book.remove(book.active)
    _overview(book,options,scheduled,overdue,unresolved,distribution,
              title=f"Inspection Management Summary · {options['year']}")
    _notes(book,options)
    _metadata(book,'management_summary',options,len(scheduled))
    return _save(book,path)

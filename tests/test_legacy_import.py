from contextlib import closing
"""Original-layout imports use tiny hand-checked workbooks, never operational data."""
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import openpyxl
from openpyxl.comments import Comment
from inspection_app.imports import preview_import, apply_import
from inspection_app.store import Store
from inspection_app.exports import export_workbook


def flowlines(path, records=None, reference=True):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = 'FLs'
    sheet.append(['Updated on', datetime(2026, 10, 25)])
    sheet.append(['Updated by', 'Tester'])
    sheet.append(['Well', 'In-service?', 'Service', 'WSW / WIW / OPW', 'MOP',
                  'ESD or Switch Set press', 'BOPD', 'WC%', 'Last Insp', 'Next Insp',
                  'Number of Leaks after last Insp date', 'Total Clamps#',
                  'Remarks / Recommendation of recent Insp.', 'Req. Action?'])
    for row in records or [['AG-101', 'Yes', 'Oil', None, 300, None, None, None,
                           datetime(2024, 1, 12), datetime(2034, 1, 1), None, None, 'Keep this note']]:
        sheet.append(row)
    if reference:
        book.create_sheet('Coolers').append(['Reference cooler note'])
    book.save(path)
    book.close()


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'original.xlsx'
        self.store = Store(Path(self.tmp.name) / 'plan.db')
        flowlines(self.path)

    def test_discovery_lists_tabs_and_roles_without_importing(self):
        from inspection_app.legacy import inspect_workbook
        info = inspect_workbook(self.path)
        self.assertEqual(info['format'], 'legacy')
        self.assertEqual(info['sheets'], [{'name': 'FLs', 'role': 'assets'}, {'name': 'Coolers', 'role': 'reference'}])
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)

    def test_selected_tab_import_preserves_dates_notes_and_excludes_reference(self):
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertEqual(preview['counts']['Assets'], 1)
        self.assertEqual(preview['counts']['Inspection Plan'], 1)
        self.assertEqual(preview['excluded_sheets'], ['Coolers'])
        self.assertFalse(preview['errors'])
        result = apply_import(self.store, preview['token'])
        self.assertTrue(Path(result['backup']).exists())
        asset = self.store.get_asset('A09-0004')
        self.assertEqual(asset['name'], 'AG-101')
        self.assertEqual(asset['inspections'][0]['last_inspection_month'], '2024-01')
        self.assertEqual(asset['inspections'][0]['next_inspection_month'], '2034-01')
        self.assertEqual(asset['notes'][0]['note_text'], 'Keep this note')
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            refs = json.loads(conn.execute("SELECT contents FROM import_reference WHERE name='Source Cells'").fetchone()[0])
        self.assertTrue(refs)
        self.assertEqual({row['source_sheet'] for row in refs}, {'FLs'})

    def test_selection_is_validated_and_partial_replace_is_blocked(self):
        for selection in ([], ['Missing'], ['FLs', 'FLs'], 'FLs'):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                preview_import(self.store, self.path, selected_sheets=selection)
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        with self.assertRaisesRegex(ValueError, 'excluded|partial'):
            apply_import(self.store, preview['token'], 'replace')
        apply_import(self.store, preview['token'])

    def test_unknown_included_tab_blocks_but_excluded_tab_does_not(self):
        book = openpyxl.load_workbook(self.path)
        book.create_sheet('Unrecognized').append(['Do not guess'])
        book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            preview_import(self.store, self.path)
        self.assertFalse(preview_import(self.store, self.path, selected_sheets=['FLs'])['errors'])

    def test_shifted_columns_are_rejected(self):
        book = openpyxl.load_workbook(self.path)
        book['FLs'].insert_cols(9)
        book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, 'FLs.*layout|FLs.*header'):
            preview_import(self.store, self.path, selected_sheets=['FLs'])

    def test_ambiguous_dates_and_formula_comments_survive_export(self):
        book = openpyxl.load_workbook(self.path)
        sheet = book['FLs']
        sheet['I4'] = 2020
        sheet['I4'].number_format = 'General'
        sheet['J4'] = '=DATE(2030,1,1)'
        sheet['J4'].comment = Comment('Verify against report', 'Inspector')
        book.save(self.path); book.close()
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertFalse(preview['errors'])
        self.assertGreaterEqual(preview['counts']['Review Items'], 2)
        apply_import(self.store, preview['token'])
        asset = self.store.get_asset('A09-0004')
        inspection = asset['inspections'][0]
        self.assertIsNone(inspection['last_inspection_month'])
        self.assertIsNone(inspection['next_inspection_month'])
        self.assertEqual(inspection['review_status'], 'Review')
        formula = next(row for row in asset['source_cells'] if row['source_cell'] == 'J4')
        self.assertEqual(formula['original_value'], '=DATE(2030,1,1)')
        self.assertIn('Verify against report', formula['original_annotation'])
        exported = Path(self.tmp.name) / 'export.xlsx'
        export_workbook(self.store, exported)
        other = Store(Path(self.tmp.name) / 'other.db')
        again = preview_import(other, exported)
        apply_import(other, again['token'])
        self.assertEqual(other.get_asset('A09-0004')['source_cells'], asset['source_cells'])

    def test_reordered_rows_reuse_existing_ids_and_new_rows_do_not_overwrite(self):
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        apply_import(self.store, preview['token'])
        row = ['AG-101', 'Yes', 'Oil', None, 300, None, None, None, '2024-01', '2035-02']
        flowlines(self.path, records=[['AG-NEW', 'Yes', 'Oil'], row])
        second = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertFalse(second['errors'])
        self.assertEqual(second['additions'], 1)
        self.assertEqual(second['updates'], 1)
        apply_import(self.store, second['token'])
        self.assertEqual(self.store.get_asset('A09-0004')['name'], 'AG-101')
        self.assertEqual(self.store.get_asset('A09-0004')['inspections'][0]['next_inspection_month'], '2035-02')
        third = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertEqual(third['additions'], 0)
        self.assertEqual(third['updates'], 2)

    def test_duplicate_identity_blocks_apply(self):
        flowlines(self.path, records=[['AG-101', 'Yes', 'Oil'], ['AG-101', 'Yes', 'Oil']])
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertTrue(preview['errors'])
        with self.assertRaises(ValueError): apply_import(self.store, preview['token'])

    def test_shared_tag_with_distinct_asset_numbers_is_not_collapsed(self):
        from inspection_app.imports import _resolve_legacy_ids
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [
            {'asset_id': 'A01-0008', 'source_sheet': 'Vessels & TKs', 'source_row': 8, 'asset_family': 'Vessel / tank', 'asset_description': 'New filter', 'tag_original': 'F-1', 'asset_number_original': 'NEW-FILTER'},
            {'asset_id': 'A01-0009', 'source_sheet': 'Vessels & TKs', 'source_row': 9, 'asset_family': 'Vessel / tank', 'asset_description': 'Old filter', 'tag_original': 'F-1', 'asset_number_original': 'OLD-FILTER'}]
        self.assertEqual(_resolve_legacy_ids(self.store, data), [])
        for row in data['Assets']:
            self.store.save_asset(None, {'name': row['asset_description'], 'family': row['asset_family'], **{k:v for k,v in row.items() if k not in ('asset_id', 'asset_family', 'asset_description')}}, None)
        self.assertEqual(_resolve_legacy_ids(self.store, data), [])
        self.assertEqual(len({r['asset_id'] for r in data['Assets']}), 2)

    def test_report_sequence_distinguishes_identical_descriptions_in_same_section(self):
        from inspection_app.imports import _resolve_legacy_ids
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [{'asset_id': f'A02-000{i}', 'source_sheet': 'OP Piping', 'source_row': i, 'asset_family': 'Piping', 'asset_description': 'Same label', 'source_group': 'PACK 1', 'source_sequence': i} for i in (5, 6)]
        self.assertFalse(_resolve_legacy_ids(self.store, data))

    def test_changed_strong_identifier_does_not_overwrite_by_description(self):
        from inspection_app.imports import _resolve_legacy_ids
        existing = self.store.save_asset(None, {'name': 'Filter', 'family': 'Vessel / tank', 'source_sheet': 'Vessels & TKs', 'asset_number_original': 'OLD'}, None)
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [{'asset_id': 'A01-0008', 'source_sheet': 'Vessels & TKs', 'source_row': 8, 'asset_family': 'Vessel / tank', 'asset_description': 'Filter', 'asset_number_original': 'NEW'}]
        self.assertFalse(_resolve_legacy_ids(self.store, data))
        self.assertNotEqual(data['Assets'][0]['asset_id'], existing['id'])

    def test_conflicting_asset_number_cannot_be_ignored_when_tag_matches(self):
        from inspection_app.imports import _resolve_legacy_ids
        self.store.save_asset(None, {'name': 'Filter', 'family': 'Vessel / tank', 'source_sheet': 'Vessels & TKs', 'asset_number_original': 'OLD', 'tag_original': 'F-1'}, None)
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [{'asset_id': 'A01-0008', 'source_sheet': 'Vessels & TKs', 'source_row': 8, 'asset_family': 'Vessel / tank', 'asset_description': 'Filter', 'asset_number_original': 'NEW', 'tag_original': 'F-1'}]
        self.assertTrue(_resolve_legacy_ids(self.store, data))

    def test_next_date_before_last_date_is_flagged_without_correcting_source(self):
        flowlines(self.path, records=[['AG-101', 'Yes', 'Oil', None, 300, None, None, None, datetime(2024, 1, 1), datetime(1931, 2, 1)]])
        preview = preview_import(self.store, self.path, selected_sheets=['FLs'])
        self.assertGreater(preview['counts']['Review Items'], 0)
        apply_import(self.store, preview['token'])
        inspection = self.store.get_asset('A09-0004')['inspections'][0]
        self.assertEqual(inspection['next_inspection_month'], '1931-02')
        self.assertEqual(inspection['review_status'], 'Review')
        self.assertEqual(self.store.dashboard('2026-11', '2026-11', '2027-02')['overdue'], 0)

    def test_epf_matches_cleaned_identity_despite_old_mop_header_as_location(self):
        from inspection_app.imports import _resolve_legacy_ids
        existing = self.store.save_asset(None, {'name': 'Separator outlet', 'family': 'Piping', 'source_sheet': 'EPFs', 'source_group': 'MOP', 'location_from': 'MOP', 'source_sequence': 1}, None)
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [{'asset_id': 'A06-0005', 'source_sheet': 'EPFs', 'source_row': 5, 'asset_family': 'Piping', 'asset_description': 'Separator outlet', 'source_group': 'SAG Area', 'location_from': 'SAG Area', 'source_sequence': 1}]
        self.assertFalse(_resolve_legacy_ids(self.store, data))
        self.assertEqual(data['Assets'][0]['asset_id'], existing['id'])

    def test_reference_only_merge_does_not_delete_existing_assets_or_excluded_evidence(self):
        full = preview_import(self.store, self.path)
        apply_import(self.store, full['token'])
        prior = self.store.get_asset('A09-0004')
        partial = preview_import(self.store, self.path, selected_sheets=['Coolers'])
        self.assertEqual(partial['counts']['Assets'], 0)
        apply_import(self.store, partial['token'])
        self.assertEqual(self.store.get_asset('A09-0004'), prior)

    def test_section_rows_do_not_become_assets(self):
        # OP has a different header and section rows containing PACK in column B.
        book = openpyxl.Workbook(); sheet = book.active; sheet.title = 'OP Piping'
        sheet.append([None, 'Report#', 'Item', 'Operat. Press.', 'Max. Operat.Press.',
                      'Design Press. 1st safety device', 'Last Insp.', 'Next insp.',
                      'Related to OP SD?', 'Repair Status', 'Recommended Action', 'Further Recommendation'])
        sheet.append([None, 'PACK 01 - FLARE HEADER'])
        sheet.append([None, 1, 'Flare branch', None, None, None, '2020', 'W/Eval'])
        book.save(self.path); book.close()
        preview = preview_import(self.store, self.path)
        self.assertEqual(preview['counts']['Assets'], 1)
        apply_import(self.store, preview['token'])
        asset = self.store.get_asset('A02-0003')
        self.assertEqual(asset['source_group'], 'PACK 01 - FLARE HEADER')
        self.assertIsNone(asset['inspections'][0]['last_inspection_month'])
        self.assertEqual(asset['inspections'][0]['scheduling_condition'], 'Awaiting evaluation')

    def test_alphanumeric_report_numbers_are_retained_as_assets(self):
        book = openpyxl.Workbook(); sheet = book.active; sheet.title = 'OP Piping'
        sheet.append([None, 'Report#', 'Item', 'Operat. Press.', 'Max. Operat.Press.',
                      'Design Press. 1st safety device', 'Last Insp.', 'Next insp.',
                      'Related to OP SD?', 'Repair Status', 'Recommended Action', 'Further Recommendation'])
        sheet.append([None, '13A', 'Gas lift section', None, None, None, '2020-01', '2030-01'])
        sheet.append([None, 'xx', 'Related lines recorded in another package', None, None, None, 'xx', 'xx'])
        book.save(self.path); book.close()
        preview = preview_import(self.store, self.path)
        self.assertEqual(preview['counts']['Assets'], 2)
        self.assertEqual(preview['counts']['Review Items'], 2)

    def test_merged_vessel_section_heading_is_evidence_not_an_asset(self):
        book = openpyxl.Workbook(); sheet = book.active; sheet.title = 'Vessels & TKs'
        sheet.append([None, 'SN', 'Field', 'Plant', 'Location', 'Unit Name', 'Asset Name',
                      'Tag #', 'Asset #', 'Full asset Description (Oracle Name)', 'In-service?',
                      'Insulation type', 'Last Insp. Category', 'Last OSI Date', 'Next OSI Due Date',
                      'Last Internal Insp. Date', 'Next Internal Insp. Date', 'Next Insp. Category',
                      'Actual Worst CR (mm/yr)', 'RL (from last insp)', 'RBI Due Date (Internal)',
                      'RBI Due Date (OSI)', 'Remarks & Recommendations'])
        sheet['G2'] = 'Compressor area'; sheet.merge_cells('G2:W2')
        sheet['G3'] = 'Receiver'; sheet['I3'] = 'V-100'
        book.save(self.path); book.close()
        preview = preview_import(self.store, self.path)
        self.assertEqual(preview['counts']['Assets'], 1)
        apply_import(self.store, preview['token'])
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            refs = json.loads(conn.execute("SELECT contents FROM import_reference WHERE name='Source Cells'").fetchone()[0])
        section = next(r for r in refs if r['source_cell'] == 'G2')
        self.assertIsNone(section['asset_id'])


if __name__ == '__main__': unittest.main()

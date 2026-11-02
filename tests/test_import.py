import tempfile
import unittest
from pathlib import Path
from inspection_app.imports import preview_import, apply_import
from inspection_app.store import Store

WORKBOOK = Path(__file__).resolve().parent.parent / 'reference' / 'Master_Inspection_Plan_Cleaned_Draft.xlsx'

class ImportTests(unittest.TestCase):
    def test_reimport_requires_preview_and_keeps_absent_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            first = preview_import(store, WORKBOOK)
            apply_import(store, first['token'])
            extra = store.save_asset(None, {'name': 'Extra', 'family': 'Flowline'}, None)
            asset = store.get_asset('A03-0015')
            store.save_asset(asset['id'], {'name': 'Edited name'}, asset['version'])
            second = preview_import(store, WORKBOOK)
            self.assertFalse(second['errors'])
            self.assertEqual(second['updates'], 1066)
            self.assertEqual(second['retained'], 1)
            self.assertEqual(store.get_asset('A03-0015')['name'], 'Edited name')
            apply_import(store, second['token'])
            self.assertNotEqual(store.get_asset('A03-0015')['name'], 'Edited name')
            self.assertEqual(store.get_asset(extra['id'])['name'], 'Extra')
    def test_preview_compares_existing_and_incoming_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            first = preview_import(store, WORKBOOK)
            apply_import(store, first['token'])
            asset = store.get_asset('A03-0015')
            store.save_asset(asset['id'], {'name': 'Edited name'}, asset['version'])
            preview = preview_import(store, WORKBOOK)
            changed = next(row for row in preview['comparison'] if row['id'] == asset['id'])
            self.assertEqual(changed['status'], 'changed')
            self.assertTrue(any(field['field'] == 'Asset name' and field['current'] == 'Edited name' for field in changed['changes']))

    def test_replace_import_removes_absent_assets_and_backup_recovers_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            extra = store.save_asset(None, {'name': 'Extra', 'family': 'Flowline'}, None)
            preview = preview_import(store, WORKBOOK)
            result = apply_import(store, preview['token'], mode='replace')
            with self.assertRaises(KeyError): store.get_asset(extra['id'])
            self.assertEqual(Store(result['backup']).get_asset(extra['id'])['name'], 'Extra')
            self.assertEqual(store.get_asset('A03-0015')['id'], 'A03-0015')

    def test_reviewed_workbook_imports_with_all_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            preview = preview_import(store, WORKBOOK)
            self.assertEqual(preview['counts']['Assets'], 1066)
            self.assertEqual(preview['counts']['Inspection Plan'], 1324)
            self.assertFalse(preview['errors'])
            apply_import(store, preview['token'])
            asset = store.get_asset('A03-0015')
            self.assertEqual(asset['inspections'][0]['next_inspection_month'], '2032-12')
            self.assertTrue(any('Joint#15' in note['note_text'] for note in asset['notes']))

    def test_preview_is_invalidated_by_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            preview = preview_import(store, WORKBOOK)
            store.save_asset(None, {'name': 'New asset', 'family': 'Flowline'}, None)
            with self.assertRaises(ValueError):
                apply_import(store, preview['token'])

    def test_preview_blocks_duplicate_inspection_types(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            workbook = openpyxl.load_workbook(WORKBOOK)
            sheet = workbook['Inspection Plan']
            row = [cell.value for cell in sheet[2]]
            row[0] = 'unique-duplicate-test'
            sheet.append(row)
            source = Path(tmp) / 'invalid.xlsx'
            workbook.save(source)
            store = Store(Path(tmp) / 'plan.db')
            preview = preview_import(store, source)
            self.assertTrue(preview['errors'])
            with self.assertRaises(ValueError): apply_import(store, preview['token'])

    def test_invalid_workbook_closes_file_before_cleanup(self):
        from unittest.mock import patch
        from inspection_app.imports import read_workbook
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.xlsx'
            book = openpyxl.Workbook()
            book.save(path)
            opened = []
            original = openpyxl.load_workbook
            def load(*args, **kwargs):
                workbook = original(*args, **kwargs)
                opened.append(workbook)
                return workbook
            with patch('inspection_app.imports.openpyxl.load_workbook', load):
                with self.assertRaisesRegex(ValueError, 'Missing worksheet'):
                    read_workbook(path)
            self.assertIsNone(opened[0]._archive.fp, 'Invalid upload must be closed before Windows deletes it')

    def test_duplicate_headings_release_underlying_file_handle(self):
        from unittest.mock import patch
        from inspection_app.imports import read_workbook
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'duplicate.xlsx'
            book = openpyxl.Workbook()
            book.active.title = 'Assets'
            book.active.append(['asset_id', 'asset_id'])
            book.active.append(['one', 'two'])
            book.save(path)
            handles = []
            original = openpyxl.load_workbook
            def load(*args, **kwargs):
                workbook = original(*args, **kwargs)
                handles.append(workbook._archive.fp)
                return workbook
            with patch('inspection_app.imports.openpyxl.load_workbook', load):
                try:
                    read_workbook(path)
                except ValueError as exc:
                    self.assertIn('Duplicate headings', str(exc))
                    self.assertTrue(handles[0].closed, 'Partially consumed worksheet must release its Windows file handle')
                else:
                    self.fail('Duplicate headings should be rejected')

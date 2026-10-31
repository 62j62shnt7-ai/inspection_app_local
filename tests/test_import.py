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

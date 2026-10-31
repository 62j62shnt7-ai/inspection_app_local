import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.imports import preview_import, apply_import

WORKBOOK = Path(__file__).resolve().parent.parent / 'reference' / 'Master_Inspection_Plan_Cleaned_Draft.xlsx'

class RoundTripTests(unittest.TestCase):
    def test_full_export_import_preserves_edited_data_and_source(self):
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'one.db')
            p = preview_import(store, WORKBOOK)
            apply_import(store, p['token'])
            a = store.get_asset('A03-0015')
            a['name'] = 'Updated line'
            store.save_asset(a['id'], a, a['version'])
            export_workbook(store, root / 'export.xlsx')
            restored = Store(root / 'two.db')
            preview = preview_import(restored, root / 'export.xlsx')
            self.assertFalse(preview['errors'])
            apply_import(restored, preview['token'])
            b = restored.get_asset(a['id'])
            self.assertEqual(b['name'], 'Updated line')
            self.assertEqual(b['inspections'], a['inspections'])
            self.assertEqual(b['source_cells'], a['source_cells'])
            self.assertEqual(b['notes'], a['notes'])

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from openpyxl import load_workbook

from inspection_app import excel_io, payloads
from inspection_app.store import Store


class ExcelCompressedFieldMapTests(unittest.TestCase):
    def test_export_unpacks_compressed_field_map_from_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / 'master.db')
            store.save_asset(None, {
                'name': 'Tiny Asset', 'family': 'Vessel', 'record_status': 'Active',
                'source_sheet': 'Vessels & TKs',
            }, None)
            rows = [{
                'source_sheet': 'Vessels & TKs', 'source_column': index,
                'source_heading': 'Heading ' + str(index), 'destination': 'name',
                'field_id': None, 'preservation': 'Mapping documentation ' + ('field data ' * 30),
            } for index in range(35)]
            encoded = payloads.dumps(rows, ensure_ascii=False)
            self.assertIsInstance(encoded, bytes)

            with closing(sqlite3.connect(store.db_path)) as conn, conn:
                conn.execute('CREATE TABLE import_reference (name TEXT PRIMARY KEY, contents TEXT NOT NULL)')
                conn.execute('INSERT INTO import_reference VALUES (?,?)', ('Field Map', encoded))

            workbook_path = root / 'full.xlsx'
            excel_io.export_full_workbook(store, workbook_path)
            workbook = load_workbook(workbook_path, read_only=True, data_only=True)
            try:
                self.assertEqual(workbook['Field Map'].max_row, len(rows) + 1)
            finally:
                workbook.close()

            preview = excel_io.preview_sync(store, workbook_path)
            self.assertEqual(preview['errors'], [])
            self.assertEqual(preview['changes'], [])
            self.assertEqual(preview['conflicts'], [])


if __name__ == '__main__':
    unittest.main()

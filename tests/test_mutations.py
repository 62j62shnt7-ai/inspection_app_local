"""Mutation regressions use only disposable synthetic master records."""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.exports import export_workbook
from inspection_app.imports import preview_import, apply_import


class MutationTests(unittest.TestCase):
    def test_editor_token_cannot_revive_after_clear_and_reimport(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'master.db')
            original = store.save_asset(None, {'name': 'V-101', 'family': 'Vessel / tank'}, None)
            workbook = export_workbook(store, Path(tmp) / 'source.xlsx')
            with closing(sqlite3.connect(store.db_path)) as conn, conn:
                conn.execute('DELETE FROM assets')
            apply_import(store, preview_import(store, workbook)['token'])
            with self.assertRaisesRegex(ValueError, 'changed'):
                store.save_asset(original['id'], {'name': 'Stale correction'}, original['version'])
            self.assertEqual(store.get_asset(original['id'])['name'], 'V-101')

    def test_new_records_never_reuse_an_issued_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'master.db')
            first = store.save_asset(None, {'name': 'A', 'family': 'Flowline'}, None)
            second = store.save_asset(None, {'name': 'B', 'family': 'Flowline'}, None)
            self.assertGreater(second['version'], first['version'])

    def test_failed_stale_edit_leaves_record_and_journal_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'master.db')
            asset = store.save_asset(None, {'name': 'A', 'family': 'Flowline'}, None)
            store.save_asset(asset['id'], {'name': 'B'}, asset['version'])
            with self.assertRaises(ValueError):
                store.save_asset(asset['id'], {'name': 'C'}, asset['version'])
            with closing(sqlite3.connect(store.db_path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM correction_events').fetchone()[0], 2)
            self.assertEqual(store.get_asset(asset['id'])['name'], 'B')

    def test_import_validation_failure_rolls_back_records_and_events(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'master.db')
            first = store.save_asset(None, {'name': 'A', 'family': 'Flowline'}, None)
            second = store.save_asset(None, {'name': 'B', 'family': 'Flowline'}, None)
            workbook = export_workbook(store, Path(tmp) / 'source.xlsx')
            book = load_workbook(workbook)
            sheet = book['Assets']
            headings = [c.value for c in sheet[1]]
            sheet.cell(2, headings.index('asset_description')+1, 'Changed')
            sheet.cell(3, headings.index('record_status')+1, 'Invalid')
            book.save(workbook); book.close()
            preview = preview_import(store, workbook)
            with self.assertRaises(ValueError): apply_import(store, preview['token'])
            self.assertEqual(store.get_asset(first['id'])['name'], 'A')
            self.assertEqual(store.get_asset(second['id'])['name'], 'B')
            with closing(sqlite3.connect(store.db_path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM correction_events').fetchone()[0], 2)

    def test_replace_removal_invalidates_verification_before_id_returns(self):
        from inspection_app.quality import verify_fields,asset_verification
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            first=store.save_asset(None,{'name':'A','family':'Flowline'},None)
            first_book=export_workbook(store,root/'a.xlsx')
            verify_fields(store,first['id'],first['version'],['name'],'Checked drawing')
            other=Store(root/'other.db');other.save_asset(None,{'name':'B','family':'Flowline'},None)
            second_book=export_workbook(other,root/'b.xlsx')
            apply_import(store,preview_import(store,second_book)['token'],'replace')
            apply_import(store,preview_import(store,first_book)['token'])
            field=next(f for f in asset_verification(store,first['id'])['fields'] if f['field']=='name')
            self.assertFalse(field['verified'])

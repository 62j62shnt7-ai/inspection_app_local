from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from inspection_app.store import Store


class ConsolidationTests(unittest.TestCase):
    def test_explicit_survivor_preserves_evidence_alias_and_stale_guards(self):
        from inspection_app.consolidation import preview_consolidation,apply_consolidation
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            a=store.save_asset(None,{'name':'Survivor','family':'Flowline','notes':[{'note_id':'n1','note_text':'First source'}]},None)
            b=store.save_asset(None,{'name':'Duplicate','family':'Flowline','notes':[{'note_id':'n2','note_text':'Second source'}]},None)
            preview=preview_consolidation(store,a['id'],b['id'])
            self.assertTrue(any(c['field']=='name' for c in preview['conflicts']))
            choices={c['field']:'survivor' for c in preview['conflicts']}
            result=apply_consolidation(store,preview['preview_id'],preview['revision'],choices,'Same equipment confirmed against drawing D1')
            self.assertEqual(result['survivor_id'],a['id'])
            current=store.get_asset(a['id'])
            self.assertEqual({n['note_text'] for n in current['notes']},{'First source','Second source'})
            self.assertEqual(store.get_asset(b['id'])['id'],a['id'])
            with self.assertRaises(ValueError):store.save_asset(a['id'],{'name':'Stale'},a['version'])
            with closing(sqlite3.connect(store.db_path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0],1)

    def test_consolidation_requires_every_conflict_to_be_reviewed(self):
        from inspection_app.consolidation import preview_consolidation,apply_consolidation
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            a=store.save_asset(None,{'name':'A','family':'Flowline'},None)
            b=store.save_asset(None,{'name':'B','family':'Flowline'},None)
            preview=preview_consolidation(store,a['id'],b['id'])
            with self.assertRaisesRegex(ValueError,'conflict'):
                apply_consolidation(store,preview['preview_id'],preview['revision'],{},'Review')
            self.assertEqual(store.get_asset(b['id'])['name'],'B')

    def test_reimport_of_retired_id_updates_survivor_without_recreating_duplicate(self):
        from inspection_app.consolidation import preview_consolidation,apply_consolidation
        from inspection_app.imports import preview_import,apply_import
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            a=store.save_asset(None,{'name':'A','family':'Flowline'},None)
            source=Store(root/'source.db');b=source.save_asset(None,{'name':'B','family':'Flowline'},None)
            book=export_workbook(source,root/'b.xlsx');apply_import(store,preview_import(store,book)['token'])
            preview=preview_consolidation(store,a['id'],b['id'])
            apply_consolidation(store,preview['preview_id'],preview['revision'],{c['field']:'survivor' for c in preview['conflicts']},'Same asset')
            apply_import(store,preview_import(store,book)['token'])
            with closing(sqlite3.connect(store.db_path)) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0],1)

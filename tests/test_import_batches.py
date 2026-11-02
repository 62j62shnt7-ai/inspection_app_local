from pathlib import Path
import tempfile
import unittest
from inspection_app.store import Store
from inspection_app.exports import export_workbook
from inspection_app.imports import preview_import, apply_import


class BatchTests(unittest.TestCase):
    def test_preview_survives_restart_and_archives_exact_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=Store(root/'source.db')
            source.save_asset(None,{'name':'Synthetic','family':'Flowline'},None)
            path=export_workbook(source,root/'source.xlsx')
            target=Store(root/'target.db')
            preview=preview_import(target,path)
            target=Store(root/'target.db')
            result=apply_import(target,preview['token'])
            self.assertEqual(result['imported'],1)
            archives=list((root/'source-archives').glob('*.xlsx'))
            self.assertEqual(len(archives),1)
            self.assertEqual(archives[0].read_bytes(),path.read_bytes())

    def test_resumed_preview_keeps_source_digest_and_invalidates_old_token(self):
        from inspection_app.imports import resume_import
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            store.save_asset(None,{'name':'Synthetic','family':'Flowline'},None)
            path=export_workbook(store,root/'source.xlsx')
            first=preview_import(store,path)
            resumed=resume_import(Store(root/'master.db'),first['token'])
            self.assertEqual(resumed['digest'],first['digest'])
            self.assertNotEqual(resumed['token'],first['token'])
            with self.assertRaises(ValueError):apply_import(store,first['token'])

    def test_legacy_reimport_finds_original_identity_after_verified_context_correction(self):
        from test_legacy_import import flowlines
        from inspection_app.quality import verify_fields
        from inspection_app.imports import resolve_import
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'source.xlsx';flowlines(path)
            store=Store(root/'master.db');apply_import(store,preview_import(store,path)['token'])
            asset=store.get_asset('A09-0004')
            asset=store.save_asset(asset['id'],{'location_from':'Verified North context'},asset['version'])
            verify_fields(store,asset['id'],asset['version'],['identity','context'],'Checked drawing')
            preview=preview_import(store,path)
            self.assertEqual(preview['additions'],0)
            if preview['errors']:
                self.assertTrue(any(c['id']==asset['id'] for row in preview['conflicts'] for c in row['candidates']))
                preview=resolve_import(store,preview['token'],[{'row_key':row['row_key'],'action':'match','asset_id':asset['id']} for row in preview['conflicts']])
            apply_import(store,preview['token'])
            self.assertEqual(store.get_asset(asset['id'])['location_from'],'Verified North context')

    def test_preview_compares_previous_source_current_master_and_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            asset=store.save_asset(None,{'name':'Original source name','family':'Flowline'},None)
            path=export_workbook(store,root/'source.xlsx')
            apply_import(store,preview_import(store,path)['token'])
            asset=store.get_asset(asset['id']);store.save_asset(asset['id'],{'name':'Owner correction'},asset['version'])
            preview=preview_import(store,path)
            change=next(change for row in preview['comparison'] for change in row['changes'] if change['field']=='Asset name')
            self.assertEqual(change['previous_source'],'Original source name')
            self.assertEqual(change['current'],'Owner correction')
            self.assertEqual(change['incoming'],'Original source name')

    def test_unclassified_populated_rows_require_explicit_coverage_acknowledgement(self):
        from test_legacy_import import flowlines
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'source.xlsx';flowlines(path)
            book=load_workbook(path);book['FLs'].append([None,None,None,None,'Unclassified source note']);book.save(path);book.close()
            store=Store(root/'master.db');preview=preview_import(store,path)
            with self.assertRaisesRegex(ValueError,'coverage|classified'):
                apply_import(store,preview['token'])
            result=apply_import(store,preview['token'],acknowledge_coverage=True)
            self.assertEqual(result['imported'],1)

    def test_committed_import_history_keeps_unclassified_source_rows_reopenable(self):
        from test_legacy_import import flowlines
        from openpyxl import load_workbook
        from importlib import import_module
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'source.xlsx';flowlines(path)
            book=load_workbook(path);book['FLs'].append([None,None,None,None,'Possible omitted equipment']);book.save(path);book.close()
            store=Store(root/'master.db');preview=preview_import(store,path)
            apply_import(store,preview['token'],acknowledge_coverage=True)
            module=import_module('inspection_app.import_batches')
            self.assertTrue(hasattr(module,'list_import_history'))
            history=module.list_import_history(store)
            self.assertEqual(len(history),1)
            self.assertTrue(history[0]['coverage_acknowledged'])
            self.assertEqual(history[0]['unclassified_count'],1)
            self.assertEqual(history[0]['unclassified_rows'],[{'sheet':'FLs','rows':[5]}])
            self.assertEqual(history[0]['digest'],preview['digest'])
            self.assertTrue(history[0]['source_available'])

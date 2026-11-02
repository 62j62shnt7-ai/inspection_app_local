import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook
from inspection_app.reconciliation import reconcile_workbook
from inspection_app.store import Store

class ReconciliationTests(unittest.TestCase):
    def test_matching_ambiguity_and_month_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db.sqlite')
            a = store.save_asset(None, {'name':'Tank One','family':'Tank','asset_number_original':'TK-100','inspections':[{'inspection_type':'Internal','applicable':'Yes','next_inspection_month':'2026-03'}]}, None)
            store.save_asset(None, {'name':'Other','family':'Tank','tag_original':'DUP'}, None)
            store.save_asset(None, {'name':'Third','family':'Tank','tag_original':'DUP'}, None)
            book = Workbook(); sheet = book.active; sheet.title = 'Full Inspection Plan'
            sheet.append(['Plan']); sheet.append(['Category','Package# for Piping Or Asset# for vessels & TKs','Item','Last Insp Date','Planned Insp Date','Next Inspection Category'])
            sheet.append(['Tank','TK-100','Tank One',None,'2026-06','Internal'])
            sheet.append(['Tank','DUP','Unknown',None,'2026','OSI'])
            path = Path(directory) / 'plan.xlsx'; book.save(path)
            result = reconcile_workbook(store, path)
            self.assertEqual(result['rows'][0]['candidates'][0]['id'], a['id'])
            self.assertEqual(result['rows'][0]['candidates'][0]['evidence'], 'Exact asset number')
            self.assertEqual(result['rows'][0]['planned_month'], '2026-06')
            self.assertIsNone(result['rows'][1]['planned_month'])
            self.assertEqual(len(result['rows'][1]['candidates']), 2)
            self.assertTrue(result['rows'][1]['ambiguous'])

    def test_wrong_workbook_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            book = Workbook(); path = Path(directory) / 'wrong.xlsx'; book.save(path)
            with self.assertRaises(ValueError): reconcile_workbook(Store(Path(directory) / 'db'), path)

    def test_apply_selected_updates_is_atomic_and_backed_up(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db.sqlite')
            asset = store.save_asset(None, {'name':'Vessel','family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2020-01','next_inspection_month':'2027-01'}]}, None)
            update = {'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':'2025-03','next_inspection_month':'2026-09','service_status_original':'Out of service','remark':'Reviewed scope'}}
            result = apply_reconciliation(store, [update])
            changed = store.get_asset(asset['id'])
            self.assertEqual(changed['inspections'][0]['next_inspection_month'], '2026-09')
            self.assertEqual(changed['service_status_original'], 'Out of service')
            self.assertEqual(changed['notes'][0]['note_text'], 'Reviewed scope')
            self.assertEqual(Store(result['backup']).get_asset(asset['id'])['inspections'][0]['next_inspection_month'], '2027-01')
            with self.assertRaises(ValueError): apply_reconciliation(store, [update])
            self.assertEqual(store.get_asset(asset['id'])['version'], changed['version'])

    def test_conflicts_and_invalid_inspections_do_not_modify_any_asset(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db.sqlite')
            a = store.save_asset(None, {'name':'Vessel','family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]}, None)
            b = store.save_asset(None, {'name':'Line','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]}, None)
            updates = [{'asset_id':a['id'],'version':a['version'],'inspection_type':'OSI','fields':{'next_inspection_month':'2026-01'}},{'asset_id':b['id'],'version':b['version'],'inspection_type':'Internal','fields':{'next_inspection_month':'2026-01'}}]
            with self.assertRaises(ValueError): apply_reconciliation(store, updates)
            self.assertEqual(store.get_asset(a['id']), a)

    def test_invalid_plan_releases_underlying_file_before_cleanup(self):
        from unittest.mock import patch
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'invalid-plan.xlsx'
            book = openpyxl.Workbook()
            for _ in range(20): book.active.append(['Not a plan'])
            book.save(path)
            handles = []
            original = openpyxl.load_workbook
            def load(*args, **kwargs):
                workbook = original(*args, **kwargs)
                handles.append(workbook._archive.fp)
                return workbook
            with patch('inspection_app.reconciliation.openpyxl.load_workbook', load):
                try:
                    reconcile_workbook(Store(root / 'plan.db'), path)
                except ValueError:
                    self.assertTrue(handles[0].closed, 'Rejected plan must release its Windows file handle')
                else:
                    self.fail('Invalid plan should be rejected')

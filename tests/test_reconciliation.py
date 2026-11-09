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
            update = {'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':'2025-03','next_inspection_month':'2028-09','service_status_original':'Out of service','remark':'Reviewed scope'}}
            update['source']={'completion_evidence':[{'column':'ut progress','value':'Done'}]}
            result = apply_reconciliation(store, [update])
            changed = store.get_asset(asset['id'])
            self.assertEqual(changed['inspections'][0]['next_inspection_month'], '2028-09')
            self.assertEqual(changed['service_status_original'], 'Out of service')
            self.assertEqual(changed['notes'][0]['note_text'], 'Reviewed scope')
            from inspection_app.backups import restore_backup
            restored = Store(Path(directory)/'restored.db')
            restore_backup(restored, result['backup'])
            self.assertEqual(restored.get_asset(asset['id'])['inspections'][0]['next_inspection_month'], '2027-01')
            with self.assertRaises(ValueError): apply_reconciliation(store, [update])
            self.assertEqual(store.get_asset(asset['id'])['version'], changed['version'])

    def test_conflicts_and_invalid_inspections_do_not_modify_any_asset(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db.sqlite')
            a = store.save_asset(None, {'name':'Vessel','family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]}, None)
            b = store.save_asset(None, {'name':'Line','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]}, None)
            updates = [{'asset_id':a['id'],'version':a['version'],'inspection_type':'OSI','fields':{'next_inspection_month':'2026-01'}},{'asset_id':b['id'],'version':b['version'],'inspection_type':'Internal','fields':{'next_inspection_month':'2026-01'}}]
            for update in updates:update['source']={'completion_evidence':[{'column':'ut progress','value':'Done'}]}
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

    def test_completed_ut_batch_reads_actual_and_next_dates_without_using_planned(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db.sqlite')
            assets = [store.save_asset(None, {'name':name,'family':'Vessel','tag_original':name,'inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2020-01','next_inspection_month':'2026-01'}]}, None) for name in ('V1','V2')]
            book = Workbook(); sheet = book.active
            sheet.append(['Tag','Asset name','Inspection type','Actual inspection date','Next due date','Planned date'])
            for name in ('V1','V2'): sheet.append([name,name,'OSI','2026-09-14','2028-09','2026-06'])
            path=Path(directory)/'results.xlsx';book.save(path)
            result=reconcile_workbook(store,path)
            self.assertEqual(len(result['rows']),2)
            updates=[]
            for row,asset in zip(result['rows'],assets):
                self.assertEqual(row['last_month'],'2026-09')
                self.assertEqual(row['next_month'],'2028-09')
                self.assertEqual(row['planned_month'],'2026-06')
                self.assertEqual(store.get_asset(asset['id']),asset)
                updates.append({'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':row['last_month'],'next_inspection_month':row['next_month']},'source':{'row':row['row'],'last_original':row['last_original'],'completion_evidence':[{'column':'ut progress','value':'Done'}]}})
            applied=apply_reconciliation(store,updates)
            self.assertEqual(applied['updated'],2)
            self.assertEqual(len(applied['versions']),2)
            for asset in assets:
                current=store.get_asset(asset['id'])
                self.assertEqual(current['inspections'][0]['next_inspection_month'],'2028-09')
            # Re-uploading identical results does not create correction events or revisions.
            for update in updates:update['version']=applied['versions'][update['asset_id']]
            self.assertEqual(apply_reconciliation(store,updates)['updated'],0)

    def test_actual_completion_takes_priority_over_previous_last_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'db.sqlite')
            book=Workbook();sheet=book.active
            sheet.append(['Tag','Inspection type','Last inspection date','Actual completion date','Next due date'])
            sheet.append(['V1','UT','2020-01','2026-09','2028-09'])
            path=root/'ut.xlsx';book.save(path)
            row=reconcile_workbook(store,path)['rows'][0]
            self.assertEqual(row['last_month'],'2026-09')
            self.assertEqual(row['next_month'],'2028-09')
            # UT is a method, not evidence of OSI versus Internal scope.
            self.assertIsNone(row['inspection_type'])

    def test_completion_status_requires_explicit_consistent_done_evidence(self):
        from inspection_app.reconciliation import completion_status
        for value in ('Done', 'Completed', 'Complete', '100%'):
            self.assertEqual(completion_status([{'column':'ut progress','value':value}]),'done')
        for value in ('Not done', 'Pending', 'In progress', 'No'):
            self.assertEqual(completion_status([{'column':'ut progress','value':value}]),'not_done')
        self.assertEqual(completion_status([{'column':'ut completed','value':'Yes'}]),'done')
        self.assertEqual(completion_status([{'column':'ut progress','value':'Yes'}]),'unknown')
        self.assertEqual(completion_status([]),'unknown')
        self.assertEqual(completion_status([{'column':'report issued','value':'Done'}]),'unknown')
        self.assertEqual(completion_status([{'column':'ut status','value':'Done'},{'column':'ut progress','value':'In progress'}]),'not_done')

    def test_workbook_done_flag_controls_atomic_date_application(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'db.sqlite')
            assets=[store.save_asset(None,{'name':name,'family':'Vessel','tag_original':name,'inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2020-01'}]},None) for name in ('V1','V2')]
            book=Workbook();sheet=book.active
            sheet.append(['Tag','Inspection type','Actual inspection date','UT Progress','Report Issued'])
            sheet.append(['V1','OSI','2026-09','Done','Yes'])
            sheet.append(['V2','OSI','2026-09','In progress','Yes'])
            path=root/'ut.xlsx';book.save(path)
            rows=reconcile_workbook(store,path)['rows']
            self.assertEqual([row['completion_status'] for row in rows],['done','not_done'])
            updates=[{'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':row['last_month']},'source':{'completion_evidence':row['completion_evidence']}} for asset,row in zip(assets,rows)]
            with self.assertRaisesRegex(ValueError,'marked done'):
                apply_reconciliation(store,updates)
            for asset in assets:self.assertEqual(store.get_asset(asset['id']),asset)
            result=apply_reconciliation(store,updates[:1])
            self.assertEqual(result['updated'],1)
            self.assertEqual(store.get_asset(assets[0]['id'])['inspections'][0]['last_inspection_month'],'2026-09')
            self.assertEqual(store.get_asset(assets[1]['id'])['inspections'][0]['last_inspection_month'],'2020-01')

    def test_dates_without_completion_evidence_rejected_even_for_old_clients(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite')
            asset=store.save_asset(None,{'name':'Vessel','family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]},None)
            update={'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':'2026-09'}}
            for source in (None, {}, {'completion_evidence':[{'column':'ut progress','value':'Not done'}]}):
                if source is not None:update['source']=source
                with self.assertRaisesRegex(ValueError,'marked done'):apply_reconciliation(store,[update])
                self.assertEqual(store.get_asset(asset['id']),asset)

    def test_preview_retains_service_and_both_remark_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'db.sqlite')
            book=Workbook();sheet=book.active
            sheet.append(['Tag','Inspection type','Actual inspection date','UT Progress','Service status','Scope remarks','Remarks'])
            sheet.append(['V1','OSI','2026-09','Done','Out of service','Scope detail','Final detail'])
            path=root/'results.xlsx';book.save(path);book.close()
            row=reconcile_workbook(store,path)['rows'][0]
            self.assertEqual(row['service_status'],'Out of service')
            self.assertEqual(row['remarks'],'Scope detail')
            self.assertEqual(row['final_remarks'],'Final detail')

    def test_apply_all_proposals_preserves_separate_remarks_and_is_idempotent(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite')
            asset=store.save_asset(None,{'name':'Vessel','family':'Vessel','service_status_original':'In service','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2020-01'}]},None)
            update={'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'last_inspection_month':'2026-09','next_inspection_month':'2028-09','service_status_original':'Out of service','remarks':['Scope detail','Final detail',' scope  detail ']},'source':{'completion_evidence':[{'column':'UT Progress','value':'Done'}]}}
            result=apply_reconciliation(store,[update]);self.assertEqual(result['updated'],1)
            current=store.get_asset(asset['id'])
            self.assertEqual(current['service_status_original'],'Out of service')
            self.assertEqual([note['note_text'] for note in current['notes']],['Scope detail','Final detail'])
            update['version']=current['version'];self.assertEqual(apply_reconciliation(store,[update])['updated'],0)
            self.assertEqual(store.get_asset(asset['id']),current)
            update['fields']['remarks']=['Valid',None]
            with self.assertRaises(ValueError):apply_reconciliation(store,[update])
            self.assertEqual(store.get_asset(asset['id']),current)

    def test_reconciliation_never_regresses_last_or_next_dates_and_rolls_back_batch(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite')
            assets=[store.save_asset(None,{'name':name,'family':'Vessel','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2026-04','next_inspection_month':'2036-04'}]},None) for name in ('First','Second')]
            for key,value in [('last_inspection_month','2021-04'),('next_inspection_month','2035-04')]:
                updates=[{'asset_id':assets[0]['id'],'version':assets[0]['version'],'inspection_type':'OSI','fields':{'remark':'Disposable rollback probe'}},{'asset_id':assets[1]['id'],'version':assets[1]['version'],'inspection_type':'OSI','fields':{key:value},'source':{'completion_evidence':[{'column':'UT Progress','value':'Done'}]}}]
                with self.assertRaisesRegex(ValueError,'older than the master'):apply_reconciliation(store,updates)
                for asset in assets:self.assertEqual(store.get_asset(asset['id']),asset)

    def test_whole_retained_paragraph_does_not_get_appended_again(self):
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite')
            text='Existing inspection recommendation.\n\nLater inspection history remains here.'
            asset=store.save_asset(None,{'name':'Vessel','family':'Vessel','notes':[{'note_id':'original','note_type':'Remark','note_text':text}]},None)
            result=apply_reconciliation(store,[{'asset_id':asset['id'],'version':asset['version'],'inspection_type':'OSI','fields':{'remark':'existing inspection recommendation'}}])
            self.assertEqual(result['updated'],0);self.assertEqual(store.get_asset(asset['id']),asset)

    def test_unique_exact_description_uses_existing_unambiguous_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'db.sqlite')
            asset=store.save_asset(None,{'name':'HAWK-05ST','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2026-01'}]},None)
            book=Workbook();sheet=book.active;sheet.append(['Package','Item','Last inspection date','Planned date','Inspection type'])
            sheet.append(['FLs','HAWK-05ST','Never','2025-05','UT + VT']);path=root/'results.xlsx';book.save(path);book.close()
            row=reconcile_workbook(store,path)['rows'][0]
            self.assertEqual(row['candidates'],[{'id':asset['id'],'name':'HAWK-05ST','evidence':'Exact description'}])
            self.assertEqual(row['inspection_type'],'OSI');self.assertEqual(row['last_value_kind'],'empty')


    def test_scope_fallback_preserves_multiple_or_explicitly_mixed_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'db.sqlite')
            store.save_asset(None,{'name':'Vessel One','family':'Vessel','tag_original':'V1','inspections':[{'inspection_type':'OSI','applicable':'Yes'},{'inspection_type':'Internal','applicable':'Yes'}]},None)
            store.save_asset(None,{'name':'Vessel Two','family':'Vessel','tag_original':'V2','inspections':[{'inspection_type':'OSI','applicable':'Yes'}]},None)
            book=Workbook();sheet=book.active;sheet.append(['Tag','Last inspection date','Inspection type'])
            sheet.append(['V1','2026-09','UT + VT']);sheet.append(['V2','2026-09','OSI / Internal'])
            path=root/'results.xlsx';book.save(path);book.close()
            rows=reconcile_workbook(store,path)['rows']
            self.assertTrue(all(row['inspection_type'] is None for row in rows))

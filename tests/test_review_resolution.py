import unittest
from inspection_app.validation import reconcile_import_reviews

REASON = 'No unambiguous month; original value retained for review.'

class ReviewResolutionTests(unittest.TestCase):
    def asset(self):
        return {'id':'a','name':'Line','family':'Flowline','record_status':'Active',
                'inspections':[{'inspection_type':'OSI','applicable':'Yes','last_original':'June -19','next_inspection_month':'2027-01','review_status':'Review','review_reason':'last inspection: '+REASON}],
                'review_items':[{'review_id':'r','field':'OSI: last inspection','reason':REASON,'original_value':'June -19','review_status':'Review'},
                                {'review_id':'other','field':'notes','reason':'Check coating','review_status':'Review'}]}

    def test_correction_resolves_linked_items_only_and_retains_evidence(self):
        asset=self.asset()
        reconcile_import_reviews(asset)
        self.assertEqual(asset['review_items'][0]['review_status'],'Review')
        asset['inspections'][0]['last_inspection_month']='2019-06'
        reconcile_import_reviews(asset)
        self.assertEqual(asset['review_items'][0]['review_status'],'Resolved')
        self.assertIsNone(asset['inspections'][0]['review_status'])
        self.assertEqual(asset['inspections'][0]['review_reason'],'')
        self.assertEqual(asset['review_items'][0]['original_value'],'June -19')
        self.assertEqual(asset['review_items'][0]['reason'],REASON)
        self.assertEqual(asset['review_items'][1]['review_status'],'Review')

    def test_clearing_summary_alone_does_not_resolve_bad_date(self):
        asset=self.asset();asset['inspections'][0]['review_status']=None
        reconcile_import_reviews(asset)
        self.assertEqual(asset['review_items'][0]['review_status'],'Review')

    def test_reintroduced_problem_reopens_linked_warning(self):
        asset=self.asset();inspection=asset['inspections'][0]
        inspection['last_inspection_month']='2019-06'
        reconcile_import_reviews(asset)
        inspection['last_inspection_month']=None
        reconcile_import_reviews(asset)
        self.assertEqual(asset['review_items'][0]['review_status'],'Review')
        self.assertEqual(inspection['review_status'],'Review')

    def test_save_persists_resolution_without_destroying_source_evidence(self):
        import tempfile
        from pathlib import Path
        from inspection_app.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            asset=store.save_asset(None,self.asset(),None)
            asset['inspections'][0]['last_inspection_month']='2019-06'
            saved=store.save_asset(asset['id'],asset,asset['version'])
            self.assertEqual(saved['review_items'][0]['review_status'],'Resolved')
            self.assertEqual(saved['review_items'][1]['review_status'],'Review')
            self.assertIsNone(saved['inspections'][0]['review_status'])
            self.assertEqual(saved['review_items'][0]['reason'],REASON)

    def test_independent_concern_survives_unrelated_save_after_generated_resolution(self):
        asset = self.asset()
        inspection = asset['inspections'][0]
        reconcile_import_reviews(asset)
        inspection['last_inspection_month'] = '2019-06'
        reconcile_import_reviews(asset)
        inspection.update(review_status='Review', review_reason='Confirm scope against drawing D1')
        asset['name'] = 'Renamed line'
        reconcile_import_reviews(asset)
        self.assertEqual(inspection['review_status'], 'Review')
        self.assertEqual(inspection['review_reason'], 'Confirm scope against drawing D1')
        self.assertEqual(asset['review_items'][0]['original_value'], 'June -19')

    def test_independent_imported_concern_survives_unrelated_save(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        from openpyxl import load_workbook
        from inspection_app.exports import export_workbook
        from inspection_app.imports import preview_import, apply_import
        from inspection_app.quality import assess_readiness, publish_snapshot
        from inspection_app.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'test.db')
            saved = store.save_asset(None, self.asset(), None)
            saved['inspections'][0]['last_inspection_month'] = '2019-06'
            saved = store.save_asset(saved['id'], saved, saved['version'])
            path = export_workbook(store, root / 'synthetic.xlsx')
            book = load_workbook(path)
            sheet = book['Inspection Plan']
            headers = {cell.value: cell.column for cell in sheet[1]}
            sheet.cell(2, headers['review_status'], 'Review')
            sheet.cell(2, headers['review_reason'], 'Confirm scope against drawing D1')
            book.save(path)
            preview = preview_import(store, path)
            self.assertFalse(preview['errors'])
            apply_import(store, preview['token'])
            saved = store.get_asset(saved['id'])
            saved['name'] = 'Renamed line'
            saved = store.save_asset(saved['id'], saved, saved['version'])
            self.assertEqual(saved['inspections'][0]['review_reason'], 'Confirm scope against drawing D1')
            self.assertEqual(saved['inspections'][0]['review_status'], 'Review')
            self.assertEqual(saved['review_items'][0]['original_value'], 'June -19')
            report = assess_readiness(store)
            self.assertNotIn(saved['id'], report['eligible'])
            manifest = publish_snapshot(store, report['revision'], 'Review retained')
            self.assertNotIn(saved['id'], [asset['id'] for asset in manifest['assets']])
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute('select count(*) from field_verifications').fetchone()[0], 0)

    def test_independent_concern_survives_correction_of_generated_item(self):
        asset = self.asset()
        inspection = asset['inspections'][0]
        reconcile_import_reviews(asset)
        inspection.update(review_reason='Confirm scope against drawing D1', last_inspection_month='2019-06')
        reconcile_import_reviews(asset)
        self.assertEqual(inspection['review_status'], 'Review')
        self.assertEqual(inspection['review_reason'], 'Confirm scope against drawing D1')
        self.assertEqual(asset['review_items'][0]['review_status'], 'Resolved')

    def test_partial_correction_keeps_other_date_warning(self):
        asset=self.asset();inspection=asset['inspections'][0]
        inspection.update(next_inspection_month=None,next_original='June -20')
        inspection['review_reason']+=' next inspection: '+REASON
        asset['review_items'].append({'review_id':'next','field':'OSI: next inspection','reason':REASON,'original_value':'June -20','review_status':'Review'})
        inspection['last_inspection_month']='2019-06'
        reconcile_import_reviews(asset)
        self.assertEqual(asset['review_items'][0]['review_status'],'Resolved')
        self.assertEqual(asset['review_items'][2]['review_status'],'Review')
        self.assertEqual(inspection['review_status'],'Review')
        self.assertEqual(inspection['review_reason'],'next inspection: '+REASON)

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

import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import named_year_candidates, preview_named_year_dates, query_quality, apply_bulk_correction, revert_bulk_correction

class NamedYearBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db')
    def asset(self,raw,**inspection):
        return self.store.save_asset(None,{'name':'Line','family':'Flowline','record_status':'Active','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_original':raw,'next_inspection_month':'2027-01',**inspection}]},None)
    def test_select_preview_apply_revert_and_preserve_source(self):
        a=self.asset('June -19');self.asset('aug-35')
        listing=named_year_candidates(self.store);self.assertEqual([x['after'] for x in listing['candidates']],['2019-06','2035-08'])
        self.assertEqual(query_quality(self.store,{})['date_review_counts']['named_year'],2)
        preview=preview_named_year_dates(self.store,listing['revision'],[listing['candidates'][0]['key']]);self.assertEqual(preview['date_count'],1)
        self.assertIsNone(self.store.get_asset(a['id'])['inspections'][0].get('last_inspection_month'))
        applied=apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Confirmed this century')
        saved=self.store.get_asset(a['id']);self.assertEqual(saved['inspections'][0]['last_inspection_month'],'2019-06');self.assertEqual(saved['inspections'][0]['last_original'],'June -19')
        self.assertEqual(query_quality(self.store,{})['date_review_counts']['named_year'],1)
        revert_bulk_correction(self.store,applied['operation_id'],'Undo');self.assertEqual(self.store.get_asset(a['id'])['inspections'],a['inspections'])
    def test_only_exact_month_names_and_missing_current_values(self):
        for raw in ('June -19','JAN-00','september -99'):self.asset(raw)
        for raw in ('June 19','June -2019','Junk -19','03/04/25','June -1'):self.asset(raw)
        self.asset('June -19',last_inspection_month='2018-01')
        listing=named_year_candidates(self.store)
        self.assertEqual([c['after'] for c in listing['candidates']],['2019-06','2000-01','2099-09'])
        for selection in ([],[listing['candidates'][0]['key']]*2,['bad']):
            with self.assertRaises(ValueError):preview_named_year_dates(self.store,listing['revision'],selection)
        a=self.asset('May-20')
        with self.assertRaisesRegex(ValueError,'changed'):preview_named_year_dates(self.store,listing['revision'],[listing['candidates'][0]['key']])

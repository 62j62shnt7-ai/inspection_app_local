import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import century_date_candidates, preview_century_dates, apply_bulk_correction, revert_bulk_correction
from inspection_app.validation import validate_record

class CenturyBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db')
        self.asset=self.store.save_asset(None,{'name':'Line','family':'Flowline','record_status':'Active','inspections':[
            {'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'1935-08','next_inspection_month':'1938-09',
             'last_original':'1935-08-01T00:00:00','next_original':'1938-09-01T00:00:00','last_source_cell':'I4','next_source_cell':'J4'}]},None)

    def test_selected_dates_preview_apply_and_revert(self):
        listing=century_date_candidates(self.store)
        self.assertEqual(len(listing['candidates']),2)
        candidate=listing['candidates'][0]
        self.assertEqual((candidate['before'],candidate['after'],candidate['source_cell']),('1935-08','2035-08','I4'))
        preview=preview_century_dates(self.store,listing['revision'],[candidate['key']])
        self.assertEqual(preview['date_count'],1)
        self.assertIn('chronology',{i['rule_id'] for i in preview['changes'][0]['remaining_issues']})
        self.assertEqual(self.store.get_asset(self.asset['id']),self.asset)
        result=apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Source confirmed')
        saved=self.store.get_asset(self.asset['id'])
        self.assertEqual(saved['inspections'][0]['last_inspection_month'],'2035-08')
        self.assertEqual(saved['inspections'][0]['next_inspection_month'],'1938-09')
        self.assertEqual(saved['inspections'][0]['last_original'],'1935-08-01T00:00:00')
        self.assertIn('chronology',{i['rule_id'] for i in validate_record(saved)})
        self.assertTrue(Path(result['backup']).is_file())
        revert_bulk_correction(self.store,result['operation_id'],'Undo')
        self.assertEqual(self.store.get_asset(self.asset['id'])['inspections'],self.asset['inspections'])

    def test_invalid_selection_and_stale_revisions_rejected(self):
        listing=century_date_candidates(self.store); key=listing['candidates'][0]['key']
        for selection in ([],[key,key],['not-a-candidate']):
            with self.subTest(selection=selection),self.assertRaises(ValueError):
                preview_century_dates(self.store,listing['revision'],selection)
        preview=preview_century_dates(self.store,listing['revision'],[key])
        self.store.save_asset(self.asset['id'],{'name':'Edited'},self.asset['version'])
        with self.assertRaisesRegex(ValueError,'changed'):
            preview_century_dates(self.store,listing['revision'],[key])
        with self.assertRaisesRegex(ValueError,'changed'):
            apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Source confirmed')

    def test_only_active_applicable_valid_19xx_months_are_candidates(self):
        self.store.save_asset(None,{'name':'Archived','family':'Flowline','record_status':'Archived','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'1935-01'}]},None)
        self.store.save_asset(None,{'name':'Not applicable','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'No','last_inspection_month':'1935-01'}]},None)
        self.store.save_asset(None,{'name':'Current','family':'Flowline','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2035-01'}]},None)
        self.assertEqual(len(century_date_candidates(self.store)['candidates']),2)

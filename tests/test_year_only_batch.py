from inspection_app import payloads
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import preview_year_only_dates, apply_bulk_correction, revert_bulk_correction

REASON='No unambiguous month; original value retained for review.'

class YearOnlyBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db')

    def asset(self, last='2020', next='2025', **extra):
        payload={'name':'Line','family':'Flowline','record_status':'Active','inspections':[{'inspection_type':'OSI','applicable':'Yes','last_original':last,'next_original':next}],**extra}
        return self.store.save_asset(None,payload,None)

    def apply(self, preview):
        return apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Owner chose January for year-only dates')

    def test_preview_apply_and_revert_both_dates_preserve_evidence(self):
        a=self.asset(review_items=[{'review_id':'r','field':'OSI: last inspection','original_value':'2020','reason':REASON,'review_status':'Review'}])
        preview=preview_year_only_dates(self.store)
        self.assertEqual(preview['date_count'],2)
        self.assertEqual(len(preview['changes']),1)
        self.assertIsNone(self.store.get_asset(a['id'])['inspections'][0].get('last_inspection_month'))
        result=self.apply(preview)
        saved=self.store.get_asset(a['id'])
        self.assertEqual(saved['inspections'][0]['last_inspection_month'],'2020-01')
        self.assertEqual(saved['inspections'][0]['next_inspection_month'],'2025-01')
        self.assertEqual(saved['inspections'][0]['last_original'],'2020')
        self.assertEqual(saved['review_items'][0]['review_status'],'Resolved')
        self.assertTrue(Path(result['backup']).is_file())
        reverted=revert_bulk_correction(self.store,result['operation_id'],'Undo January defaults')
        restored=self.store.get_asset(a['id'])
        self.assertEqual(restored['inspections'],a['inspections'])
        self.assertEqual(restored['review_items'],a['review_items'])
        self.assertEqual(reverted['reverted'],1)

    def test_blank_ambiguous_and_existing_months_are_unchanged(self):
        assets=[self.asset(last=raw,next=raw) for raw in (None,'','June -19','03/04/25','2020/2021','20','0000','2020.0')]
        existing=self.asset(inspections=[{'inspection_type':'OSI','applicable':'Yes','last_original':'2020','last_inspection_month':'2020-06','next_original':'2025','next_inspection_month':'2025-09'}])
        preview=preview_year_only_dates(self.store)
        self.assertEqual(preview['changes'],[])
        self.assertEqual(preview['date_count'],0)
        for asset in assets+[existing]:
            self.assertEqual(self.store.get_asset(asset['id']),asset)

    def test_applies_all_inspection_types_but_not_archived_or_inapplicable(self):
        active=self.asset(family='Vessel / tank',inspections=[{'inspection_type':kind,'applicable':'Yes','last_original':' 2020 ','next_original':'2025'} for kind in ('OSI','Internal')])
        self.asset(record_status='Archived')
        self.asset(inspections=[{'inspection_type':'OSI','applicable':'No','last_original':'2020','next_original':'2025'}])
        preview=preview_year_only_dates(self.store)
        self.assertEqual(preview['date_count'],4)
        self.assertEqual([c['asset_id'] for c in preview['changes']],[active['id']])
        self.apply(preview)
        self.assertTrue(all(i['last_inspection_month']=='2020-01' for i in self.store.get_asset(active['id'])['inspections']))

    def test_stale_preview_rejected_and_chronology_warning_visible(self):
        a=self.asset(inspections=[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2025-06','next_original':'2025'}])
        preview=preview_year_only_dates(self.store)
        self.assertIn('chronology',{i['rule_id'] for i in preview['changes'][0]['remaining_issues']})
        self.store.save_asset(a['id'],{'name':'Edited'},a['version'])
        with self.assertRaisesRegex(ValueError,'Master changed'):
            self.apply(preview)
        self.assertIsNone(self.store.get_asset(a['id'])['inspections'][0].get('next_inspection_month'))

    def test_repeat_preview_is_empty_and_change_is_audited_not_verified(self):
        a=self.asset()
        self.apply(preview_year_only_dates(self.store))
        self.assertEqual(preview_year_only_dates(self.store)['date_count'],0)
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM field_verifications').fetchone()[0],0)
            row=conn.execute("SELECT before_json,after_json,reason FROM correction_events WHERE origin='bulk'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(payloads.loads(row[1])['inspections'][0]['last_inspection_month'],'2020-01')
            self.assertIn('January',row[2])

    def test_revert_refuses_to_overwrite_a_later_edit(self):
        a=self.asset()
        result=self.apply(preview_year_only_dates(self.store))
        current=self.store.get_asset(a['id'])
        self.store.save_asset(a['id'],{'name':'Later edit'},current['version'])
        with self.assertRaisesRegex(ValueError,'Affected asset changed'):
            revert_bulk_correction(self.store,result['operation_id'],'Undo')
        self.assertEqual(self.store.get_asset(a['id'])['inspections'][0]['next_inspection_month'],'2025-01')

    def test_failed_batch_rolls_back_all_date_changes(self):
        first=self.asset()
        second=self.asset()
        preview=preview_year_only_dates(self.store)
        # Simulate an affected-row version mismatch without changing the global clock.
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('UPDATE assets SET version=version-1 WHERE id=?',(preview['changes'][-1]['asset_id'],))
        with self.assertRaisesRegex(ValueError,'Affected asset changed'):
            self.apply(preview)
        for asset in (first,second):
            self.assertIsNone(self.store.get_asset(asset['id'])['inspections'][0].get('last_inspection_month'))

    def test_existing_field_verification_is_invalidated_only_for_changed_values(self):
        from inspection_app.quality import verify_fields,asset_verification
        a=self.asset(inspections=[{'inspection_type':'OSI','applicable':'Yes','last_original':'2020','next_original':'2025','last_inspection_month':None}])
        verify_fields(self.store,a['id'],a['version'],['name','inspections.OSI.last_inspection_month'],'Checked source')
        self.apply(preview_year_only_dates(self.store))
        fields={f['field']:f['verified'] for f in asset_verification(self.store,a['id'])['fields']}
        self.assertTrue(fields['name'])
        self.assertFalse(fields['inspections.OSI.last_inspection_month'])

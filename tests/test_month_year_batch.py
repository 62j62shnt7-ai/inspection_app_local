import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import preview_month_year_dates, apply_bulk_correction, revert_bulk_correction
from inspection_app.validation import validate_record

REASON = 'No unambiguous month; original value retained for review.'

class MonthYearBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'test.db')

    def asset(self, last='2-2026', next='12-2026', **extra):
        return self.store.save_asset(None, {'name':'Line', 'family':'Flowline', 'record_status':'Active',
            'inspections':[{'inspection_type':'OSI', 'applicable':'Yes', 'last_original':last, 'next_original':next,
                            'review_status':'Review', 'review_reason':'last inspection: '+REASON}],
            'review_items':[{'review_id':'r', 'field':'OSI: last inspection', 'original_value':last,
                             'reason':REASON, 'review_status':'Review'}], **extra}, None)

    def test_preview_apply_and_revert_preserve_source_and_show_remaining_issues(self):
        asset = self.asset(last=' 2-2026 ', next='1-2026')
        preview = preview_month_year_dates(self.store)
        self.assertEqual(preview['date_count'], 2)
        self.assertEqual([d['after'] for d in preview['changes'][0]['date_changes']], ['2026-02','2026-01'])
        self.assertIn('chronology', {i['rule_id'] for i in preview['changes'][0]['remaining_issues']})
        self.assertEqual(self.store.get_asset(asset['id']), asset)
        result = apply_bulk_correction(self.store, preview['preview_id'], preview['revision'], 'Normalize source dates')
        saved = self.store.get_asset(asset['id'])
        self.assertEqual(saved['inspections'][0]['last_original'], ' 2-2026 ')
        self.assertEqual(saved['review_items'][0]['review_status'], 'Resolved')
        self.assertIn('chronology', {i['rule_id'] for i in validate_record(saved)})
        self.assertTrue(Path(result['backup']).is_file())
        revert_bulk_correction(self.store, result['operation_id'], 'Undo')
        restored = self.store.get_asset(asset['id'])
        self.assertEqual(restored['inspections'], asset['inspections'])
        self.assertEqual(restored['review_items'], asset['review_items'])

    def test_only_valid_missing_months_on_active_applicable_inspections(self):
        good = self.asset(last='02-2026', next='13-2026')
        for raw in ('0-2026','2-26','2/2026','2-0000','2026-02','',None):
            self.asset(last=raw,next=raw)
        self.asset(record_status='Archived')
        self.asset(inspections=[{'inspection_type':'OSI','applicable':'No','last_original':'2-2026'}])
        self.asset(inspections=[{'inspection_type':'OSI','applicable':'Yes','last_original':'2-2026','last_inspection_month':'2025-02'}])
        preview = preview_month_year_dates(self.store)
        self.assertEqual(preview['date_count'], 1)
        self.assertEqual(preview['changes'][0]['asset_id'], good['id'])

    def test_stale_preview_is_rejected(self):
        asset = self.asset()
        preview = preview_month_year_dates(self.store)
        self.store.save_asset(asset['id'], {'name':'Edited'}, asset['version'])
        with self.assertRaisesRegex(ValueError, 'Master changed'):
            apply_bulk_correction(self.store, preview['preview_id'], preview['revision'], 'Normalize source dates')
        self.assertIsNone(self.store.get_asset(asset['id'])['inspections'][0].get('last_inspection_month'))

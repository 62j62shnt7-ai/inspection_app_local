import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.reconciliation import month


class ValidationTests(unittest.TestCase):
    def test_reconciliation_does_not_reduce_impossible_days_to_valid_months(self):
        for value in ('2026-02-31', '2026-04-00', '2026-11-99', '0000-01'):
            with self.subTest(value=value):
                self.assertIsNone(month(value))
        self.assertEqual(month('2024-02-29'), '2024-02')

    def test_wrong_child_shapes_fail_with_actionable_error_without_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'master.db')
            for value in ({'OSI': {}}, [None], 'bad'):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Inspections'):
                    store.save_asset(None, {'name': 'V', 'family': 'Vessel / tank', 'inspections': value}, None)

    def test_restore_details_cannot_override_permanent_identity_or_version(self):
        with self.assertRaisesRegex(ValueError,'reserved|identity'):
            Store._validate_details('Flowline',{'id':'other','version':99})

    def test_unclassified_family_and_missing_formula_cache_remain_visible(self):
        from inspection_app.validation import validate_record
        asset={'id':'synthetic','name':'Asset','family':'Unclassified machinery','record_status':'Active','location_from':'North','inspections':[],
               'source_cells':[{'source_sheet':'Source','source_cell':'C4','excel_type':'f','original_value':'=A4+B4','original_annotation':'{"cached_value": null}'}]}
        rules={finding['rule_id'] for finding in validate_record(asset)}
        self.assertIn('unclassified-family',rules)
        self.assertIn('formula-cache-missing',rules)

    def test_supported_manifold_layout_is_not_treated_as_unclassified(self):
        from inspection_app.validation import validate_record
        rules={i['rule_id'] for i in validate_record({'id':'m','name':'M-1','family':'Manifold','record_status':'Active','location_from':'North','inspections':[{'inspection_type':'OSI','applicable':'No'}]})}
        self.assertNotIn('unclassified-family',rules)

    def test_historical_date_flags_are_superseded_by_passing_current_checks(self):
        from inspection_app.validation import validate_record
        reason='No unambiguous month; original value retained for review.'
        asset={'id':'v','name':'V','family':'Vessel / tank','record_status':'Active','location_from':'North',
               'inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-01','review_status':'Review','review_reason':'last inspection: '+reason}, {'inspection_type':'Internal','applicable':'No'}],
               'review_items':[{'review_id':'last','field':'OSI: last inspection','review_status':'Review','reason':reason}]}
        findings=validate_record(asset)
        self.assertEqual(findings,[])
        asset['inspections'][0]['review_reason']+=' Additional independent concern.'
        self.assertIn('source-review',[i['rule_id'] for i in validate_record(asset)])

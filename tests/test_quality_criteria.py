import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from inspection_app.validation import validate_record
from inspection_app.store import Store
from inspection_app.quality import assess_readiness, publish_snapshot


class QualityCriteriaTests(unittest.TestCase):
    def asset(self, **inspection):
        return {'id':'line','name':'Line 1','family':'Flowline','record_status':'Active',
                'inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2025-01',**inspection}]}

    def test_overdue_schedule_and_missing_location_pass_without_manual_verification(self):
        self.assertEqual(validate_record(self.asset()), [])

    def test_blank_or_never_last_date_passes(self):
        for raw in (None, '', 'Never', 'Never inspected'):
            with self.subTest(raw=raw):
                self.assertEqual(validate_record(self.asset(last_original=raw)), [])

    def test_recorded_conditions_pass_without_review_by_month(self):
        for condition in ('At next shutdown','Awaiting evaluation','OOS','Out of Scope','Insulated','Confirm serviceability'):
            with self.subTest(condition=condition):
                self.assertEqual(validate_record(self.asset(next_inspection_month=None,scheduling_condition=condition,next_original=condition)), [])

    def test_condition_review_by_is_optional_in_core_verification_fields(self):
        from inspection_app.quality import required_fields
        for month in (None, '2025-01', '2030-01'):
            asset = self.asset(next_inspection_month=None, scheduling_condition='OOS', condition_review_by=month)
            with self.subTest(month=month):
                self.assertNotIn('inspections.OSI.condition_review_by', required_fields(asset))
                self.assertEqual(validate_record(asset, current_month='2026-11'), [])

    def test_blank_and_placeholder_schedule_conditions_are_flagged(self):
        for condition in (None,'','   ','Undated','Dated','XX','Unknown','—'):
            with self.subTest(condition=condition):
                self.assertIn('missing-schedule',{i['rule_id'] for i in validate_record(self.asset(next_inspection_month=None,scheduling_condition=condition))})

    def test_ambiguous_dates_are_not_misclassified_as_conditions(self):
        for raw in ('June -19','2026-02-31','03/04/25'):
            with self.subTest(raw=raw):
                findings=validate_record(self.asset(next_inspection_month=None,next_original=raw,scheduling_condition=raw))
                self.assertIn('ambiguous-date',{i['rule_id'] for i in findings})
        self.assertIn('ambiguous-date',{i['rule_id'] for i in validate_record(self.asset(last_original='June -19'))})

    def test_current_corrected_dates_override_historical_import_date_flags(self):
        reason='No unambiguous month; original value retained for review.'
        asset=self.asset(last_original='June -19',last_inspection_month='2019-06',review_status='Review',review_reason='last inspection: '+reason)
        asset['review_items']=[{'review_id':'old','field':'OSI: last inspection','original_value':'June -19','review_status':'Review','reason':reason}]
        self.assertEqual(validate_record(asset), [])
        self.assertEqual(asset['review_items'][0]['review_status'],'Review')

    def test_missing_applicability_is_flagged(self):
        for value in (None,'','Unknown'):
            with self.subTest(value=value):
                self.assertIn('required-applicability',{i['rule_id'] for i in validate_record(self.asset(applicable=value))})

    def test_chronology_internal_family_and_missing_name_still_block(self):
        self.assertIn('chronology',{i['rule_id'] for i in validate_record(self.asset(last_inspection_month='2026-01'))})
        asset=self.asset();asset['name']='';asset['tag_original']='TAG-1'
        self.assertIn('required-name',{i['rule_id'] for i in validate_record(asset)})
        asset=self.asset();asset['inspections'][0]['inspection_type']='Internal'
        self.assertIn('internal-family',{i['rule_id'] for i in validate_record(asset)})

    def test_automatic_snapshot_pass_does_not_write_manual_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            asset=self.asset();asset.pop('id')
            saved=store.save_asset(None,asset,None)
            report=assess_readiness(store)
            self.assertEqual(report['eligible'],[saved['id']])
            manifest=publish_snapshot(store,report['revision'],'Automatic criteria')
            self.assertEqual([a['id'] for a in manifest['assets']],[saved['id']])
            self.assertEqual(manifest['eligibility_basis'],'automatic_quality_checks')
            with closing(sqlite3.connect(store.db_path)) as conn:
                self.assertEqual(conn.execute('select count(*) from field_verifications').fetchone()[0],0)

    def test_shared_identifiers_still_exclude_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            for name in ('First','Second'):
                asset=self.asset();asset.pop('id');asset.update(name=name,tag_original='TAG-1')
                store.save_asset(None,asset,None)
            report=assess_readiness(store)
            self.assertEqual(report['eligible'],[])
            self.assertEqual(len(report['excluded']),2)
            self.assertTrue(all(any('Identifier' in r for r in a['reasons']) for a in report['excluded']))

    def test_summary_clears_historical_flags_but_retains_ambiguous_dates(self):
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            reason='No unambiguous month; original value retained for review.'
            for name,raw in [('Pass','Never'),('Check','June -19')]:
                asset=self.asset(last_original=raw,review_status='Review',review_reason='last inspection: '+reason)
                asset.pop('id');asset['name']=name
                asset['review_items']=[{'review_id':'old','field':'OSI: last inspection','original_value':raw,'review_status':'Review','reason':reason}]
                store.save_asset(None,asset,None)
            rows=query_register(store,{'review':'review'})['rows']
            self.assertEqual([a['name'] for a in rows],['Check'])
            rows=query_register(store,{'due':'overdue','current':'2026-11'})['rows']
            self.assertEqual([a['name'] for a in rows],['Pass'])

    def test_condition_only_schedule_is_not_in_attention_filter(self):
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            asset=self.asset(next_inspection_month=None,scheduling_condition='OOS');asset.pop('id')
            store.save_asset(None,asset,None)
            self.assertEqual(query_register(store,{'due':'attention'})['total'],0)
            self.assertEqual(query_register(store,{'due':'undated'})['total'],1)

    def test_ambiguous_source_date_is_flagged_even_with_a_valid_condition(self):
        findings=validate_record(self.asset(next_inspection_month=None,next_original='June -19',scheduling_condition='OOS'))
        self.assertIn('ambiguous-date',{i['rule_id'] for i in findings})

    def test_scheduling_condition_can_contain_a_year_without_becoming_a_date(self):
        self.assertEqual(validate_record(self.asset(next_inspection_month=None,scheduling_condition='At shutdown in 2027',next_original='At shutdown in 2027')), [])

    def test_bad_next_date_has_one_actionable_issue_instead_of_duplicate_missing_schedule(self):
        findings=validate_record(self.asset(next_inspection_month=None,next_original='June -19',scheduling_condition='June -19'))
        self.assertEqual([i['rule_id'] for i in findings],['ambiguous-date'])

    def test_asset_level_blockers_appear_in_review_without_hiding_valid_overdue_schedule(self):
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            asset=self.asset();asset.pop('id');asset['family']='Unknown'
            saved=store.save_asset(None,asset,None)
            rows=query_register(store,{'review':'review'})['rows']
            self.assertEqual([a['id'] for a in rows],[saved['id']])
            self.assertTrue(rows[0]['asset_review_reasons'])
            self.assertEqual(query_register(store,{'due':'attention'})['total'],1)
            self.assertEqual(query_register(store,{'due':'overdue','current':'2026-11'})['total'],1)

    def test_duplicate_identity_review_filter_matches_snapshot_exclusions(self):
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            for name in ('First','Second'):
                asset=self.asset();asset.pop('id');asset.update(name=name,tag_original='SHARED')
                store.save_asset(None,asset,None)
            self.assertEqual(query_register(store,{'review':'review'})['total'],2)

    def test_missing_family_and_plan_each_produce_one_actionable_issue(self):
        asset=self.asset();asset['family']='Unknown';asset['inspections']=[]
        findings=validate_record(asset)
        self.assertEqual(len([i for i in findings if i['field']=='family']),1)
        self.assertEqual(len([i for i in findings if i['field']=='inspections']),1)

    def test_protected_technical_difference_remains_visible_in_summary_review(self):
        from inspection_app.quality import verify_fields, protect_verified_fields
        from inspection_app.register import query_register
        import copy
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            asset=self.asset();asset.pop('id');asset['technical_details']=[{'field_id':'wall','field_label':'Wall','value':'10'}]
            saved=store.save_asset(None,asset,None)
            verify_fields(store,saved['id'],saved['version'],['technical_details.wall'],'Checked drawing')
            current=store.get_asset(saved['id']);incoming=copy.deepcopy(current);incoming['technical_details'][0]['value']='8'
            with closing(sqlite3.connect(store.db_path)) as conn,conn:
                protect_verified_fields(conn,current,incoming)
            self.assertEqual(assess_readiness(store)['eligible'],[])
            rows=query_register(store,{'review':'review'})['rows']
            self.assertEqual([a['id'] for a in rows],[saved['id']])
            self.assertNotIn('technical_details',rows[0])

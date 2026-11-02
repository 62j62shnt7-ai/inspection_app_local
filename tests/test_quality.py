import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from inspection_app.store import Store


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'master.db')

    def asset(self):
        return self.store.save_asset(None, {'name': 'V-101', 'family': 'Vessel / tank', 'location_from': 'North plant', 'record_status': 'Active', 'inspections': [{'inspection_type': 'OSI', 'applicable': 'Yes', 'next_inspection_month': '2027-05'}, {'inspection_type': 'Internal', 'applicable': 'No'}]}, None)

    def test_passing_rules_never_implicitly_verifies_asset(self):
        from inspection_app.quality import assess_readiness
        asset = self.asset()
        report = assess_readiness(self.store)
        self.assertEqual(report['eligible'], [asset['id']])
        self.assertEqual(report['excluded'], [])
        from inspection_app.quality import asset_verification
        self.assertFalse(any(f['verified'] for f in asset_verification(self.store,asset['id'])['fields']))

    def test_verification_is_bound_to_field_values_and_preserves_unchanged_fields(self):
        from inspection_app.quality import verify_fields, assess_readiness, verification_fields
        asset = self.asset()
        verify_fields(self.store, asset['id'], asset['version'], list(verification_fields(asset)), 'Checked workbook and identity against drawing D1')
        self.assertEqual(assess_readiness(self.store)['eligible'], [asset['id']])
        current = self.store.get_asset(asset['id'])
        self.store.save_asset(asset['id'], {'name': 'Revised description'}, current['version'])
        report = assess_readiness(self.store)
        self.assertEqual(report['eligible'], [asset['id']])
        from inspection_app.quality import asset_verification
        verified={f['field']:f['verified'] for f in asset_verification(self.store,asset['id'])['fields']}
        self.assertFalse(verified['name'])
        self.assertTrue(verified['family'])

    def test_overdue_verified_condition_is_warning_without_exclusion(self):
        from inspection_app.quality import verify_fields, assess_readiness, verification_fields
        asset = self.asset()
        asset['inspections'][0].update(next_inspection_month=None, scheduling_condition='At next shutdown', condition_review_by='2025-01')
        asset = self.store.save_asset(asset['id'], asset, asset['version'])
        verify_fields(self.store, asset['id'], asset['version'], list(verification_fields(asset)), 'Reviewed schedule and shutdown condition')
        report = assess_readiness(self.store, current_month='2026-11')
        self.assertEqual(report['eligible'], [asset['id']])
        self.assertTrue(any(i['rule_id']=='condition-review-due' for i in report['warnings']))

    def test_verified_correction_survives_reimport_with_visible_difference(self):
        from inspection_app.exports import export_workbook
        from inspection_app.imports import preview_import, apply_import
        from inspection_app.quality import verify_fields
        asset = self.asset()
        path = export_workbook(self.store, Path(self.tmp.name) / 'old.xlsx')
        asset = self.store.save_asset(asset['id'], {'name': 'Verified engineering description'}, asset['version'])
        verify_fields(self.store, asset['id'], asset['version'], ['name'], 'Checked drawing')
        preview = preview_import(self.store, path)
        apply_import(self.store, preview['token'])
        current = self.store.get_asset(asset['id'])
        self.assertEqual(current['name'], 'Verified engineering description')
        from inspection_app.quality import scan_quality
        issues = scan_quality(self.store)['issues']
        self.assertTrue(any(i['rule_id']=='incoming-difference' and i['asset_id']==asset['id'] for i in issues))

    def test_issue_resolution_requires_evidence_and_stale_revision_is_rejected(self):
        from inspection_app.quality import scan_quality, resolve_issue
        self.asset()
        asset=self.store.save_asset(None,{'name':'Missing context','family':'Flowline'},None)
        report=scan_quality(self.store)
        issue=next(i for i in report['issues'] if i['asset_id']==asset['id'] and i['rule_id']=='required-applicability')
        with self.assertRaisesRegex(ValueError,'evidence|rationale'):
            resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','')
        self.store.save_asset(asset['id'],{'name':'Changed'},asset['version'])
        with self.assertRaisesRegex(ValueError,'changed|stale'):
            resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Owner rationale')

    def test_snapshot_is_immutable_and_lists_every_excluded_record(self):
        from inspection_app.quality import assess_readiness, publish_snapshot
        asset=self.asset()
        asset['inspections'][0]['next_inspection_month']=None
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        report=assess_readiness(self.store)
        snapshot=publish_snapshot(self.store,report['revision'],'Before cleaning')
        self.assertEqual(snapshot['excluded'][0]['asset_id'],asset['id'])
        self.assertEqual(snapshot['assets'],[])
        self.store.save_asset(asset['id'],{'name':'Updated'},asset['version'])
        self.assertEqual(snapshot['excluded'][0]['name'],'V-101')
        with self.assertRaisesRegex(ValueError,'changed|stale'):
            publish_snapshot(self.store,report['revision'],'Stale')

    def test_changed_and_restored_field_does_not_revive_old_verification(self):
        from inspection_app.quality import verify_fields, asset_verification
        asset=self.asset()
        verify_fields(self.store,asset['id'],asset['version'],['name'],'Checked source')
        asset=self.store.get_asset(asset['id'])
        asset=self.store.save_asset(asset['id'],{'name':'Temporary changed value'},asset['version'])
        self.store.save_asset(asset['id'],{'name':'V-101'},asset['version'])
        field=next(f for f in asset_verification(self.store,asset['id'])['fields'] if f['field']=='name')
        self.assertFalse(field['verified'])

    def test_unrelated_change_does_not_reopen_accepted_chronology_exception(self):
        from inspection_app.quality import scan_quality,resolve_issue
        asset=self.asset();asset['inspections'][0]['last_inspection_month']='2028-01'
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        report=scan_quality(self.store)
        issue=next(i for i in report['issues'] if i['rule_id']=='chronology')
        resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Retained overdue schedule checked against engineering record')
        self.store.save_asset(asset['id'],{'service_status_original':'In service'},asset['version'])
        issue=next(i for i in scan_quality(self.store)['issues'] if i['rule_id']=='chronology')
        self.assertEqual(issue['state'],'accepted_exception')

    def test_bulk_preview_is_atomic_and_revert_cannot_overwrite_later_edit(self):
        from inspection_app.quality import preview_bulk_correction,apply_bulk_correction,revert_bulk_correction
        asset=self.asset()
        preview=preview_bulk_correction(self.store,[asset['id']],{'field':'location_from','operation':'set','value':'South plant'})
        self.assertEqual(self.store.get_asset(asset['id'])['location_from'],'North plant')
        result=apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Reviewed location correction')
        current=self.store.get_asset(asset['id'])
        self.assertEqual(current['location_from'],'South plant')
        self.store.save_asset(asset['id'],{'name':'Later correction'},current['version'])
        with self.assertRaisesRegex(ValueError,'changed'):
            revert_bulk_correction(self.store,result['operation_id'],'Revert original bulk')

    def test_bulk_invalid_value_rolls_back_all_records(self):
        from inspection_app.quality import preview_bulk_correction,apply_bulk_correction
        asset=self.asset()
        preview=preview_bulk_correction(self.store,[asset['id']],{'field':'record_status','operation':'set','value':'Bogus'})
        with self.assertRaises(ValueError):apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Check')
        self.assertEqual(self.store.get_asset(asset['id'])['record_status'],'Active')

    def test_verified_identity_protects_context_and_tags_across_reimport(self):
        from inspection_app.exports import export_workbook
        from inspection_app.imports import preview_import,apply_import
        from inspection_app.quality import verify_fields
        asset=self.asset();path=export_workbook(self.store,Path(self.tmp.name)/'old.xlsx')
        asset=self.store.save_asset(asset['id'],{'location_from':'Verified location','tag_original':'V-NEW'},asset['version'])
        verify_fields(self.store,asset['id'],asset['version'],['identity','context'],'Checked asset physically and drawing')
        apply_import(self.store,preview_import(self.store,path)['token'])
        current=self.store.get_asset(asset['id'])
        self.assertEqual(current['location_from'],'Verified location')
        self.assertEqual(current['tag_original'],'V-NEW')

    def test_fixed_then_recurring_problem_reopens_as_blocking(self):
        from inspection_app.quality import scan_quality
        asset=self.asset();asset['inspections'][0]['next_inspection_month']=None
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        self.assertTrue(any(i['rule_id']=='missing-schedule' and i['state']=='open' for i in scan_quality(self.store)['issues']))
        asset['inspections'][0]['next_inspection_month']='2027-05'
        asset=self.store.save_asset(asset['id'],asset,asset['version']);scan_quality(self.store)
        asset['inspections'][0]['next_inspection_month']=None
        self.store.save_asset(asset['id'],asset,asset['version'])
        self.assertTrue(any(i['rule_id']=='missing-schedule' and i['state']=='open' for i in scan_quality(self.store)['issues']))

    def test_changed_then_restored_schedule_does_not_revive_exception_without_scan(self):
        from inspection_app.quality import scan_quality,resolve_issue
        asset=self.asset();asset['inspections'][0]['last_inspection_month']='2028-01'
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        report=scan_quality(self.store)
        issue=next(i for i in report['issues'] if i['rule_id']=='chronology')
        resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Retained overdue date checked')
        asset['inspections'][0]['next_inspection_month']='2029-01'
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        asset['inspections'][0]['next_inspection_month']='2027-05'
        self.store.save_asset(asset['id'],asset,asset['version'])
        self.assertEqual(next(i for i in scan_quality(self.store)['issues'] if i['rule_id']=='chronology')['state'],'open')

    def test_paginated_workbench_keeps_whole_master_exclusion_count(self):
        from inspection_app.quality import query_quality
        for n in range(3):self.store.save_asset(None,{'name':'Asset '+str(n),'family':'Flowline'},None)
        page=query_quality(self.store,{'page':2,'size':1})
        self.assertEqual(page['readiness']['excluded_count'],3)
        self.assertEqual(len(page['readiness']['excluded']),1)
        self.assertEqual(page['page'],2)

    def test_accepted_source_review_is_consistent_in_schedule_summaries(self):
        from inspection_app.quality import scan_quality,resolve_issue
        from inspection_app.register import query_register
        asset=self.asset();asset['inspections'][0].update(review_status='Review',review_reason='Check source')
        asset=self.store.save_asset(asset['id'],asset,asset['version'])
        report=scan_quality(self.store);issue=next(i for i in report['issues'] if i['rule_id']=='source-review')
        resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Source checked: dates intentionally retained')
        summary=query_register(self.store,{'page':1,'size':50})['rows'][0]
        self.assertNotEqual(summary['inspections'][0].get('review_status'),'Review')
        self.assertEqual(self.store.get_asset(asset['id'])['inspections'][0]['review_status'],'Review')

    def test_missing_identifier_placeholders_do_not_create_permanent_collision(self):
        from inspection_app.quality import scan_quality
        for n in range(2):self.store.save_asset(None,{'name':'Asset '+str(n),'family':'Flowline','tag_original':'N/A'},None)
        self.assertFalse(any(i['rule_id']=='identity-collision' for i in scan_quality(self.store)['issues']))

    def test_legitimate_shared_tag_can_be_reviewed_as_separate_verified_equipment(self):
        from inspection_app.quality import scan_quality,verify_fields,resolve_issue
        first=self.asset();first=self.store.save_asset(first['id'],{'tag_original':'SHARED'},first['version'])
        second=self.store.save_asset(None,{'name':'Different component','family':'Flowline','tag_original':'SHARED','location_from':'South'},None)
        report=scan_quality(self.store);issue=next(i for i in report['issues'] if i['rule_id']=='identity-collision' and i['asset_id']==first['id'])
        with self.assertRaisesRegex(ValueError,'identity|Identity'):
            resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Separate equipment confirmed by drawing')
        verify_fields(self.store,first['id'],first['version'],['identity'],'Checked distinct equipment with shared tag')
        report=scan_quality(self.store);issue=next(i for i in report['issues'] if i['rule_id']=='identity-collision' and i['asset_id']==first['id'])
        resolve_issue(self.store,issue['issue_id'],report['revision'],'accepted_exception','Separate equipment confirmed by drawing')
        self.assertEqual(next(i for i in scan_quality(self.store)['issues'] if i['issue_id']==issue['issue_id'])['state'],'accepted_exception')

    def test_missing_archived_source_warns_without_blocking_trusted_snapshot(self):
        from inspection_app.quality import verify_fields,verification_fields,assess_readiness
        from inspection_app.exports import export_workbook
        from inspection_app.imports import preview_import,apply_import
        asset=self.asset();path=export_workbook(self.store,Path(self.tmp.name)/'source.xlsx')
        apply_import(self.store,preview_import(self.store,path)['token'])
        asset=self.store.get_asset(asset['id']);verify_fields(self.store,asset['id'],asset['version'],list(verification_fields(asset)),'Checked source')
        self.assertEqual(assess_readiness(self.store)['eligible'],[asset['id']])
        for archive in (Path(self.tmp.name)/'source-archives').glob('*.xlsx'):archive.unlink()
        report=assess_readiness(self.store)
        self.assertEqual(report['eligible'],[asset['id']])
        self.assertEqual(report['excluded'],[])
        self.assertTrue(any(i['rule_id']=='source-archive-integrity' for i in report['warnings']))

    def test_incoming_blank_does_not_erase_populated_unverified_month(self):
        from inspection_app.exports import export_workbook
        from inspection_app.imports import preview_import,apply_import
        from openpyxl import load_workbook
        asset=self.asset();path=export_workbook(self.store,Path(self.tmp.name)/'blank.xlsx')
        book=load_workbook(path);sheet=book['Inspection Plan'];headings=[c.value for c in sheet[1]]
        sheet.cell(2,headings.index('next_inspection_month')+1).value=None
        book.save(path);book.close()
        apply_import(self.store,preview_import(self.store,path)['token'])
        self.assertEqual(self.store.get_asset(asset['id'])['inspections'][0]['next_inspection_month'],'2027-05')

    def test_bulk_revert_restores_values_without_reviving_old_verification(self):
        from inspection_app.quality import preview_bulk_correction,apply_bulk_correction,revert_bulk_correction,verify_fields,asset_verification
        asset=self.asset();verify_fields(self.store,asset['id'],asset['version'],['location_from'],'Checked source')
        preview=preview_bulk_correction(self.store,[asset['id']],{'field':'location_from','operation':'set','value':'South'})
        result=apply_bulk_correction(self.store,preview['preview_id'],preview['revision'],'Reviewed location')
        reverted=revert_bulk_correction(self.store,result['operation_id'],'Reverting checked bulk')
        self.assertEqual(reverted['reverted'],1)
        self.assertEqual(self.store.get_asset(asset['id'])['location_from'],'North plant')
        field=next(f for f in asset_verification(self.store,asset['id'])['fields'] if f['field']=='location_from')
        self.assertFalse(field['verified'])

    def test_saved_snapshot_can_be_retrieved_after_master_changes(self):
        from inspection_app.quality import assess_readiness,publish_snapshot,list_snapshots,get_snapshot
        asset=self.asset();report=assess_readiness(self.store)
        snapshot=publish_snapshot(self.store,report['revision'],'Before correction')
        self.store.save_asset(asset['id'],{'name':'Changed later'},asset['version'])
        saved=get_snapshot(self.store,snapshot['snapshot_id'])
        self.assertEqual(saved['assets'][0]['name'],'V-101')
        self.assertEqual(list_snapshots(self.store)[0]['name'],'Before correction')

    def test_bulk_verification_preview_shows_all_selected_required_values(self):
        from inspection_app.quality import preview_bulk_verification
        first=self.store.save_asset(None,{'name':'V-101','family':'Vessel / tank','record_status':'Active','location_from':'North','source_sheet':'Vessels & TKs','source_row':7,'inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-05'},{'inspection_type':'Internal','applicable':'No'}]},None)
        second=self.store.save_asset(None,{'name':'FL-2','family':'Flowline','record_status':'Active','location_from':'South','source_sheet':'FLs','source_row':9,'inspections':[{'inspection_type':'OSI','applicable':'No'}]},None)
        preview=preview_bulk_verification(self.store,[second['id'],first['id']])
        self.assertEqual(preview['asset_count'],2)
        by_id={asset['id']:asset for asset in preview['assets']}
        self.assertEqual(by_id[first['id']]['source'],{'sheet':'Vessels & TKs','row':7})
        fields={item['field']:item['value'] for item in by_id[first['id']]['required_fields']}
        self.assertEqual(fields['inspections.OSI.next_inspection_month'],'2027-05')
        self.assertEqual(fields['name'],'V-101')
        self.assertEqual(fields['family'],'Vessel / tank')
        self.assertEqual(fields['record_status'],'Active')
        self.assertEqual(fields['context']['location_from'],'North')
        self.assertIsNone(fields['identity']['tag_original'])
        self.assertEqual(fields['inspections.OSI.applicable'],'Yes')
        self.assertEqual(fields['inspections.Internal.applicable'],'No')
        self.assertEqual(set(fields),{'name','family','record_status','context','identity','inspections.OSI.applicable','inspections.OSI.next_inspection_month','inspections.Internal.applicable'})
        second_fields={item['field']:item['value'] for item in by_id[second['id']]['required_fields']}
        self.assertEqual(second_fields['name'],'FL-2')
        self.assertEqual(second_fields['family'],'Flowline')
        self.assertEqual(second_fields['record_status'],'Active')
        self.assertEqual(second_fields['context']['location_from'],'South')
        self.assertIsNone(second_fields['identity']['tag_original'])
        self.assertEqual(second_fields['inspections.OSI.applicable'],'No')
        self.assertEqual(set(second_fields),{'name','family','record_status','context','identity','inspections.OSI.applicable'})

    def test_bulk_verification_preview_rejects_empty_duplicate_and_unknown_scope(self):
        from inspection_app.quality import preview_bulk_verification
        asset=self.asset()
        for selected in ([],[asset['id'],asset['id']],['missing-id']):
            with self.subTest(selected=selected),self.assertRaises(ValueError):preview_bulk_verification(self.store,selected)

    def test_bulk_verification_preview_rejects_more_than_ten_thousand_ids_with_clear_limit(self):
        from inspection_app.quality import preview_bulk_verification
        with self.assertRaisesRegex(ValueError,'10,000'):
            preview_bulk_verification(self.store,['asset-'+str(index) for index in range(10001)])

    def test_bulk_verification_can_make_clean_heterogeneous_assets_eligible(self):
        from inspection_app.quality import preview_bulk_verification,apply_bulk_verification,assess_readiness
        first=self.store.save_asset(None,{'name':'V-101','family':'Vessel / tank','record_status':'Active','location_from':'North','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-05'},{'inspection_type':'Internal','applicable':'No'}]},None)
        second=self.store.save_asset(None,{'name':'FL-2','family':'Flowline','record_status':'Active','location_from':'South','inspections':[{'inspection_type':'OSI','applicable':'No'}]},None)
        preview=preview_bulk_verification(self.store,[first['id'],second['id']])
        result=apply_bulk_verification(self.store,preview['preview_id'],preview['revision'],'Master Inspection Plan · reviewed rows 7 and 9')
        self.assertEqual(result['verified_asset_count'],2)
        self.assertEqual(result['still_excluded_count'],0)
        self.assertCountEqual(assess_readiness(self.store)['eligible'],[first['id'],second['id']])

    def test_bulk_verification_records_each_required_field_and_audit_without_resolving_blockers(self):
        from inspection_app.quality import preview_bulk_verification,apply_bulk_verification,assess_readiness
        first=self.store.save_asset(None,{'name':'A','family':'Flowline','tag_original':'SHARED','location_from':'North'},None)
        second=self.store.save_asset(None,{'name':'B','family':'Flowline','tag_original':'SHARED','location_from':'South'},None)
        preview=preview_bulk_verification(self.store,[first['id'],second['id']])
        result=apply_bulk_verification(self.store,preview['preview_id'],preview['revision'],'Master workbook · FLs rows 2–3')
        with closing(sqlite3.connect(self.store.db_path)) as conn,conn:
            verifications=conn.execute('SELECT COUNT(*) FROM field_verifications WHERE asset_id IN (?,?) AND active=1',(first['id'],second['id'])).fetchone()[0]
            events=conn.execute("SELECT COUNT(*) FROM correction_events WHERE asset_id IN (?,?) AND origin='verification'",(first['id'],second['id'])).fetchone()[0]
            blockers=conn.execute("SELECT COUNT(*) FROM quality_issues WHERE asset_id IN (?,?) AND rule_id='identity-collision' AND state='open'",(first['id'],second['id'])).fetchone()[0]
        self.assertEqual(result['verified_asset_count'],2)
        self.assertEqual(result['verified_field_count'],10)
        self.assertEqual(result['still_excluded_count'],2)
        self.assertEqual(verifications,10)
        self.assertEqual(events,2)
        self.assertEqual(blockers,2)
        self.assertEqual(len(assess_readiness(self.store)['eligible']),0)

    def test_bulk_verification_rejects_missing_evidence_and_stale_master(self):
        from inspection_app.quality import preview_bulk_verification,apply_bulk_verification
        asset=self.asset();preview=preview_bulk_verification(self.store,[asset['id']])
        with self.assertRaisesRegex(ValueError,'evidence|Evidence|reason'):
            apply_bulk_verification(self.store,preview['preview_id'],preview['revision'],'  ')
        self.store.save_asset(asset['id'],{'name':'Changed after preview'},asset['version'])
        with self.assertRaisesRegex(ValueError,'changed|stale|Master'):
            apply_bulk_verification(self.store,preview['preview_id'],preview['revision'],'Checked workbook')
        with closing(sqlite3.connect(self.store.db_path)) as conn,conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM field_verifications').fetchone()[0],0)

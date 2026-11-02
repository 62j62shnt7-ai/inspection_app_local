from pathlib import Path
import tempfile
import unittest
from inspection_app.store import Store


class RegisterTests(unittest.TestCase):
    def test_filters_apply_before_pagination_and_summary_omits_source_payloads(self):
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            for name in ('North 1','South 2','North 3'):
                store.save_asset(None,{'name':name,'family':'Flowline','source_cells':[{'original_value':'large evidence'}],'notes':[{'note_text':'remark'}]},None)
            page=query_register(store,{'search':'North','status':'active','page':2,'size':1})
            self.assertEqual(page['total'],2)
            self.assertEqual(page['rows'][0]['name'],'North 3')
            self.assertNotIn('source_cells',page['rows'][0])
            self.assertNotIn('technical_details',page['rows'][0])
            self.assertEqual(page['pages'],2)

    def test_resolved_source_item_clears_duplicate_dashboard_flag(self):
        from inspection_app.quality import scan_quality, resolve_issue
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            reason='Check source drawing against the physical asset.'
            asset=store.save_asset(None,{'name':'F','family':'Flowline','record_status':'Active','location_from':'North',
                'inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-01','review_status':'Review','review_reason':'last inspection: '+reason}],
                'review_items':[{'review_id':'last','field':'OSI: last inspection','review_status':'Review','reason':reason}]},None)
            report=scan_quality(store)
            issue=next(i for i in report['issues'] if i['rule_id']=='source-review-item')
            resolve_issue(store,issue['issue_id'],report['revision'],'accepted_exception','Checked original evidence')
            rows=query_register(store,{'due':'attention'})
            self.assertEqual(rows['total'],0)
            self.assertEqual(store.get_asset(asset['id'])['inspections'][0]['review_status'],'Review')

    def test_partial_source_review_does_not_clear_inspection_attention(self):
        from inspection_app.quality import scan_quality, resolve_issue
        from inspection_app.register import query_register
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            reason='Check source drawing against the physical asset.'
            asset=store.save_asset(None,{'name':'F','family':'Flowline','record_status':'Active','location_from':'North',
                'inspections':[{'inspection_type':'OSI','applicable':'Yes','review_status':'Review','review_reason':'last inspection: '+reason+' next inspection: '+reason}],
                'review_items':[{'review_id':label,'field':'OSI: '+label+' inspection','review_status':'Review','reason':reason} for label in ('last','next')]},None)
            report=scan_quality(store)
            issue=next(i for i in report['issues'] if i['field']=='review_items.last')
            resolve_issue(store,issue['issue_id'],report['revision'],'accepted_exception','Checked historical evidence')
            rows=query_register(store,{'due':'attention'})
            self.assertEqual(rows['total'],1)
            self.assertEqual(rows['rows'][0]['inspections'][0]['review_status'],'Review')
            report=scan_quality(store)
            self.assertEqual({i['rule_id'] for i in report['issues'] if i['state']=='open'}, {'source-review-item','missing-schedule'})

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import (preview_year_only_dates,preview_month_year_dates,century_date_candidates,preview_century_dates,named_year_candidates,preview_named_year_dates,preview_bulk_correction,apply_bulk_correction)

class DateReviewReasonTests(unittest.TestCase):
    def test_date_corrections_apply_without_reason_and_record_audit(self):
        for mode in ('year','month','century','named'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                store=Store(Path(tmp)/'test.db')
                dates={'year':{'last_original':'2020'},'month':{'last_original':'2-2026'},'century':{'last_inspection_month':'1935-08'},'named':{'last_original':'June -19'}}
                a=store.save_asset(None,{'name':'Line','family':'Flowline','record_status':'Active','inspections':[{'inspection_type':'OSI','applicable':'Yes','next_inspection_month':'2027-01',**dates[mode]}]},None)
                if mode=='year':preview=preview_year_only_dates(store)
                elif mode=='month':preview=preview_month_year_dates(store)
                else:
                    listing=century_date_candidates(store) if mode=='century' else named_year_candidates(store)
                    preview=(preview_century_dates if mode=='century' else preview_named_year_dates)(store,listing['revision'],[listing['candidates'][0]['key']])
                result=apply_bulk_correction(store,preview['preview_id'],preview['revision'],None)
                self.assertEqual(result['updated'],1)
                self.assertTrue(Path(result['backup']).is_file())
                with closing(sqlite3.connect(store.db_path)) as conn:
                    self.assertTrue(conn.execute("select reason from correction_events where origin='bulk'").fetchone()[0])
    def test_other_bulk_corrections_still_require_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            a=store.save_asset(None,{'name':'Line','family':'Flowline'},None)
            preview=preview_bulk_correction(store,[a['id']],{'field':'name','operation':'set','value':'New'})
            with self.assertRaisesRegex(ValueError,'reason'):
                apply_bulk_correction(store,preview['preview_id'],preview['revision'],None)
            self.assertEqual(store.get_asset(a['id'])['name'],'Line')

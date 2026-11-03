import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.quality import query_quality, preview_year_only_dates, preview_month_year_dates, century_date_candidates, apply_bulk_correction

class DateReviewVisibilityTests(unittest.TestCase):
    def test_counts_match_available_previews_and_refresh_after_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            for name,inspection in [('Year',{'last_original':'2020','next_inspection_month':'2027-01'}),('Month',{'last_original':'2-2026','next_inspection_month':'2027-01'}),('Century',{'last_inspection_month':'1935-08','next_inspection_month':'2027-01'})]:
                store.save_asset(None,{'name':name,'family':'Flowline','record_status':'Active','inspections':[{'inspection_type':'OSI','applicable':'Yes',**inspection}]},None)
            counts=query_quality(store,{'search':'no matching issue'})['date_review_counts']
            self.assertEqual(counts,{'year_only':1,'month_year':1,'century':1,'named_year':0})
            self.assertEqual(counts['year_only'],preview_year_only_dates(store)['date_count'])
            self.assertEqual(counts['month_year'],preview_month_year_dates(store)['date_count'])
            self.assertEqual(counts['century'],len(century_date_candidates(store)['candidates']))
            for preview in (preview_year_only_dates(store),):
                apply_bulk_correction(store,preview['preview_id'],preview['revision'],'Confirmed source')
            self.assertEqual(query_quality(store,{})['date_review_counts'],{'year_only':0,'month_year':1,'century':1,'named_year':0})

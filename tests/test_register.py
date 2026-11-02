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

import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store

class StoreTests(unittest.TestCase):
    def test_dashboard_counts_inspections_and_ignores_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            a = store.save_asset(None, {'name': 'Vessel', 'family': 'Vessel / tank', 'inspections': [{'inspection_type': 'OSI', 'applicable': 'Yes', 'next_inspection_month': '2027-06'}, {'inspection_type': 'Internal', 'applicable': 'Yes', 'next_inspection_month': '2027-06'}]}, None)
            self.assertEqual(store.dashboard('2027-07', '2027-07', '2027-12')['overdue'], 2)
            store.save_asset(a['id'], {'record_status': 'Archived'}, a['version'])
            self.assertEqual(store.dashboard('2027-07', '2027-07', '2027-12')['overdue'], 0)
    def test_save_persists_and_stale_update_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.db'
            store = Store(path)
            asset = store.save_asset(None, {'name': 'AG-101', 'family': 'Flowline'}, None)
            updated = store.save_asset(asset['id'], {'name': 'AG-101 updated'}, asset['version'])
            with self.assertRaises(ValueError):
                store.save_asset(asset['id'], {'name': 'stale'}, asset['version'])
            self.assertEqual(Store(path).get_asset(asset['id'])['name'], 'AG-101 updated')
            self.assertEqual(updated['version'], 2)

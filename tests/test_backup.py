import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.backups import create_backup

class BackupTests(unittest.TestCase):
    def test_backups_are_distinct_and_restore_committed_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            asset = store.save_asset(None, {'name':'AG-101','family':'Flowline'}, None)
            one, two = create_backup(store), create_backup(store)
            self.assertNotEqual(one, two)
            self.assertEqual(Store(one).get_asset(asset['id'])['name'], 'AG-101')

    def test_restore_and_invalid_backup_preserves_current_data(self):
        from inspection_app.backups import restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'plan.db')
            asset = store.save_asset(None, {'name': 'Original', 'family': 'Flowline'}, None)
            backup = create_backup(store)
            store.save_asset(asset['id'], {'name': 'Changed'}, asset['version'])
            invalid = root / 'invalid.db'
            invalid.write_text('not a database')
            with self.assertRaises(ValueError):
                restore_backup(store, invalid)
            self.assertEqual(store.get_asset(asset['id'])['name'], 'Changed')
            result = restore_backup(store, backup)
            self.assertTrue(Path(result['safety_backup']).exists())
            self.assertEqual(store.get_asset(asset['id'])['name'], 'Original')

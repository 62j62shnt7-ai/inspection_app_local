from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.backups import create_backup

class BackupTests(unittest.TestCase):
    def test_migration_backups_are_listed_and_can_be_deleted(self):
        from inspection_app.backups import list_backups,delete_saved_backups
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            raw=create_backup(store)
            migration=raw.with_name('inspection-migration-20261102-123456-1234abcd.db')
            raw.rename(migration)
            self.assertIn(migration.name,[row['filename'] for row in list_backups(store)])
            self.assertEqual(delete_saved_backups(store,[migration.name])['deleted'],[migration.name])
    def test_delete_saved_backups_removes_only_selected_backups(self):
        from inspection_app.backups import delete_saved_backups, list_backups
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'plan.db')
            selected=create_backup(store);retained=create_backup(store)
            result=delete_saved_backups(store,[selected.name])
            self.assertEqual(result,{'deleted':[selected.name],'failed':[]})
            self.assertFalse(selected.exists())
            self.assertTrue(retained.is_file())
            self.assertEqual([row['filename'] for row in list_backups(store)],[retained.name])

    def test_delete_saved_backups_rejects_invalid_scope_before_deleting_any_file(self):
        from inspection_app.backups import delete_saved_backups
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'plan.db');backup=create_backup(store)
            for filenames in ([],[backup.name,backup.name],['inspection-stale.db'],['../plan.db'],[str(Path(tmp)/'plan.db')]):
                with self.subTest(filenames=filenames),self.assertRaises(ValueError):
                    delete_saved_backups(store,filenames)
                self.assertTrue(backup.is_file())

    def test_delete_saved_backups_rejects_symlinks_and_backup_like_unmanaged_files(self):
        from inspection_app.backups import delete_saved_backups,list_backups
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'plan.db')
            unrelated=root/'backups'/'inspection-project-notes.db';unrelated.parent.mkdir();unrelated.write_text('unmanaged')
            target=root/'outside.db';target.write_text('keep');link=root/'backups'/'inspection-link.db';link.symlink_to(target)
            self.assertNotIn(unrelated.name,[row['filename'] for row in list_backups(store)])
            for filename in (unrelated.name,link.name):
                with self.subTest(filename=filename),self.assertRaises(ValueError):delete_saved_backups(store,[filename])
            self.assertEqual(unrelated.read_text(),'unmanaged')
            self.assertTrue(link.is_symlink());self.assertEqual(target.read_text(),'keep')

    def test_delete_saved_backups_reports_partial_unlink_failure(self):
        from unittest.mock import patch
        from inspection_app.backups import delete_saved_backups
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'plan.db');locked=create_backup(store);removable=create_backup(store)
            original=Path.unlink
            def unlink_with_locked_backup(path,*args,**kwargs):
                if path==locked:raise PermissionError('locked for test')
                return original(path,*args,**kwargs)
            with patch.object(Path,'unlink',unlink_with_locked_backup):
                result=delete_saved_backups(store,[locked.name,removable.name])
            self.assertEqual(result['deleted'],[removable.name])
            self.assertEqual(result['failed'],[{'filename':locked.name,'error':'locked for test'}])
            self.assertTrue(locked.exists());self.assertFalse(removable.exists())

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

    def test_restore_rejects_old_editor_and_reconciliation_versions(self):
        from inspection_app.backups import restore_backup
        from inspection_app.reconciliation import apply_reconciliation
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            asset = store.save_asset(None, {'name':'Original','family':'Tank'}, None)
            backup = create_backup(store)
            latest = store.save_asset(asset['id'], {'name':'Later'}, asset['version'])
            for _ in range(2):
                restore_backup(store, backup)
                restored = store.get_asset(asset['id'])
                self.assertGreater(restored['version'], latest['version'])
                for stale in (asset, latest):
                    with self.assertRaises(ValueError):
                        store.save_asset(asset['id'], {'name':'Stale'}, stale['version'])
                    with self.assertRaises(ValueError):
                        apply_reconciliation(store, [{'asset_id':asset['id'], 'version':stale['version'], 'inspection_type':'OSI', 'fields':{'remark':'Stale'}}])
                latest = store.save_asset(asset['id'], {'name':'Fresh'}, restored['version'])
                self.assertEqual(latest['name'], 'Fresh')

    def test_restore_keeps_version_watermark_after_clear(self):
        import sqlite3
        from inspection_app.backups import restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'plan.db')
            asset = store.save_asset(None, {'name':'Original','family':'Tank'}, None)
            backup = create_backup(store)
            for _ in range(3):
                asset = store.save_asset(asset['id'], {'name':'Later'}, asset['version'])
            with closing(sqlite3.connect(store.db_path)) as conn, conn:
                conn.execute('DELETE FROM assets')
            restore_backup(store, backup)
            self.assertGreater(store.get_asset(asset['id'])['version'], asset['version'])

class SemanticRestoreTests(unittest.TestCase):
    def test_corrupt_details_are_rejected_before_live_replacement(self):
        import sqlite3
        from contextlib import closing
        from inspection_app.backups import create_backup, restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'live.db')
            asset = store.save_asset(None, {'name': 'Original', 'family': 'Flowline'}, None)
            backup = create_backup(store)
            with closing(sqlite3.connect(backup)) as conn, conn:
                conn.execute("UPDATE assets SET details='invalid json'")
            with self.assertRaisesRegex(ValueError, 'details|JSON|invalid'):
                restore_backup(store, backup)
            self.assertEqual(store.get_asset(asset['id'])['name'], 'Original')

    def test_restore_rejects_wrong_detail_shape_without_touching_live_records(self):
        import sqlite3
        from inspection_app.backups import create_backup,restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'live.db')
            asset=store.save_asset(None,{'name':'Original','family':'Flowline'},None)
            backup=create_backup(store)
            with closing(sqlite3.connect(backup)) as conn,conn:
                conn.execute("UPDATE assets SET details='[]'")
            with self.assertRaisesRegex(ValueError,'details'):
                restore_backup(store,backup)
            self.assertEqual(store.get_asset(asset['id'])['name'],'Original')

    def test_restore_rejects_corrupt_trust_metadata(self):
        import sqlite3
        from inspection_app.backups import create_backup,restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'live.db')
            asset=store.save_asset(None,{'name':'Original','family':'Flowline'},None)
            backup=create_backup(store)
            with closing(sqlite3.connect(backup)) as conn,conn:
                conn.execute("INSERT INTO master_snapshots VALUES ('broken','not json')")
            with self.assertRaisesRegex(ValueError,'metadata|snapshot|JSON'):
                restore_backup(store,backup)
            self.assertEqual(store.get_asset(asset['id'])['name'],'Original')

from pathlib import Path
import tempfile
import unittest
from inspection_app.store import Store


class RecoveryTests(unittest.TestCase):
    def test_package_restores_database_and_source_archives_to_clean_directory(self):
        from inspection_app.recovery import export_master_package, restore_master_package
        from inspection_app.imports import preview_import,apply_import
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'source').mkdir();(root/'target').mkdir()
            source=Store(root/'source'/'master.db')
            a=source.save_asset(None,{'name':'Synthetic','family':'Flowline'},None)
            workbook=export_workbook(source,root/'source.xlsx')
            apply_import(source,preview_import(source,workbook)['token'])
            package=export_master_package(source,root/'recovery.zip')
            target=Store(root/'target'/'master.db')
            restore_master_package(target,package)
            self.assertEqual(target.get_asset(a['id'])['name'],'Synthetic')
            self.assertEqual(len(list((root/'target'/'source-archives').glob('*.xlsx'))),1)

    def test_unavailable_independent_folder_reports_partial_failure(self):
        from inspection_app.recovery import configure_backup_folder, backup_status, automatic_backup
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'external';folder.mkdir()
            store=Store(root/'master.db')
            configure_backup_folder(store,str(folder))
            folder.rmdir()
            automatic_backup(store,force=True)
            status=backup_status(store)
            self.assertTrue(status['local_success'])
            self.assertFalse(status['independent_success'])
            self.assertTrue(status['error'])

    def test_missing_committed_source_archive_prevents_false_complete_package(self):
        from inspection_app.recovery import export_master_package
        from inspection_app.imports import preview_import,apply_import
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            store.save_asset(None,{'name':'Synthetic','family':'Flowline'},None)
            path=export_workbook(store,root/'source.xlsx')
            apply_import(store,preview_import(store,path)['token'])
            for archive in (root/'source-archives').glob('*.xlsx'):archive.unlink()
            with self.assertRaisesRegex(ValueError,'archive|source'):
                export_master_package(store,root/'incomplete.zip')

    def test_restore_resets_machine_local_backup_success(self):
        from inspection_app.recovery import configure_backup_folder,automatic_backup,export_master_package,restore_master_package,backup_status
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').mkdir();(root/'target').mkdir();(root/'copy').mkdir()
            source=Store(root/'source'/'master.db');configure_backup_folder(source,str(root/'copy'))
            source.save_asset(None,{'name':'A','family':'Flowline'},None)
            self.assertTrue(backup_status(source)['independent_success'])
            path=export_master_package(source,root/'package.zip')
            target=Store(root/'target'/'master.db');restore_master_package(target,path)
            status=backup_status(target)
            self.assertFalse(status.get('independent_success',False))
            self.assertIsNone(status.get('day'))
            self.assertIsNone(status.get('folder'))
            target.save_asset(None,{'name':'B','family':'Flowline'},None)
            self.assertIn(str(root/'target'),backup_status(target)['local_path'])

    def test_changing_copy_folder_retries_on_next_edit_even_same_day(self):
        from inspection_app.recovery import automatic_backup,configure_backup_folder,backup_status
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'master.db')
            automatic_backup(store,force=True)
            folder=root/'copies';folder.mkdir();configure_backup_folder(store,str(folder))
            store.save_asset(None,{'name':'A','family':'Flowline'},None)
            self.assertTrue(backup_status(store)['independent_success'])
            self.assertTrue(list(folder.glob('*.zip')))

    def test_deleting_current_local_backup_invalidates_status_and_retries_before_next_edit(self):
        from inspection_app.backups import create_backup,delete_saved_backups,list_backups
        from inspection_app.recovery import automatic_backup,backup_status
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'master.db')
            older=create_backup(store);current=automatic_backup(store,force=True)
            self.assertTrue(Path(current['local_path']).is_file())
            delete_saved_backups(store,[older.name])
            self.assertEqual(backup_status(store)['local_path'],current['local_path'])
            deleted=delete_saved_backups(store,[Path(current['local_path']).name])
            self.assertEqual(deleted['deleted'],[Path(current['local_path']).name])
            status=backup_status(store)
            self.assertFalse(status['local_success'])
            self.assertNotIn('local_path',status)
            self.assertNotIn('local_at',status)
            self.assertNotIn('day',status)
            self.assertEqual(list_backups(store),[])
            store.save_asset(None,{'name':'Next edit','family':'Flowline'},None)
            retried=backup_status(store)
            self.assertTrue(retried['local_success'])
            self.assertTrue(Path(retried['local_path']).is_file())
            self.assertNotEqual(retried['local_path'],current['local_path'])

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from inspection_app.store import Store
from inspection_app.exports import export_workbook
from inspection_app.imports import preview_import, apply_import
from inspection_app.import_batches import list_import_history, source_archive_problems
from inspection_app.recovery import restore_master_package, validate_restore_package
from inspection_app import cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'master.db')
        self.asset = self.store.save_asset(None, {'name':'Keep history', 'family':'Flowline'}, None)
        path = export_workbook(self.store, self.root/'source.xlsx')
        preview = preview_import(self.store, path)
        apply_import(self.store, preview['token'])
        self.batch = preview['token']
        self.digest = preview['digest']
        self.archive = self.root/'source-archives'/(self.digest+'.xlsx')

    def apply(self, category, ids=None):
        request = {'category':category}
        if ids is not None: request['ids'] = ids
        preview = cleanup.preview_cleanup(self.store, request)
        return cleanup.apply_cleanup(self.store, preview['preview_id'], preview['confirmation'])

    def test_preview_does_not_change_data_or_create_backups(self):
        before = self.archive.read_bytes()
        files = set(self.root.rglob('*'))
        preview = cleanup.preview_cleanup(self.store, {'category':'reset'})
        self.assertTrue(preview['counts']['assets'])
        self.assertIn(self.archive.name, [f['filename'] for f in preview['files']])
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual(set(self.root.rglob('*')), files)
        self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_dismiss_and_restore_coverage_retains_evidence(self):
        cleanup.set_coverage_dismissed(self.store, self.batch, True)
        self.assertTrue(list_import_history(self.store)[0]['dismissed'])
        cleanup.set_coverage_dismissed(self.store, self.batch, False)
        self.assertFalse(list_import_history(self.store)[0]['dismissed'])
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_source_deletion_keeps_missing_evidence_lineage_and_recovery(self):
        result = self.apply('sources', [self.digest])
        self.assertFalse(self.archive.exists())
        self.assertTrue(self.store.get_asset(self.asset['id']))
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            self.assertIn(self.asset['id'], source_archive_problems(conn))
        self.assertTrue(Path(result['recovery']).is_file())
        # Later protection packages explicitly retain the missing-source status.
        from inspection_app.recovery import export_master_package
        after = export_master_package(self.store, self.root/'after.zip')
        validate_restore_package(after)
        after_folder=self.root/'after-restore';after_folder.mkdir()
        after_store=Store(after_folder/'master.db')
        after_result=restore_master_package(after_store,after)
        self.assertIsNotNone(after_result['warning'])
        with closing(sqlite3.connect(after_store.db_path)) as conn:
            self.assertIn(self.asset['id'],source_archive_problems(conn))
        target = self.root/'restored';target.mkdir()
        restore_master_package(Store(target/'master.db'), result['recovery'])
        self.assertEqual((target/'source-archives'/self.archive.name).read_bytes(), (self.root/'source.xlsx').read_bytes())

    def test_delete_import_evidence_keeps_live_asset_lineage(self):
        self.apply('imports', [self.batch])
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            raw = conn.execute('SELECT contents FROM import_batches WHERE token=?', (self.batch,)).fetchone()[0]
            self.assertTrue(json.loads(raw)['evidence_deleted'])
            self.assertIn(self.asset['id'], source_archive_problems(conn))
        self.assertFalse(self.archive.exists())
        self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_shared_import_archive_is_retained(self):
        preview = preview_import(self.store, self.root/'source.xlsx')
        apply_import(self.store, preview['token'])
        self.apply('imports', [self.batch])
        self.assertTrue(self.archive.exists())
        remaining = [b for b in list_import_history(self.store) if not b['evidence_deleted']]
        self.assertEqual(len(remaining), 1)

    def test_consolidated_asset_import_retains_survivor_lineage(self):
        survivor = self.store.save_asset(None,{'name':'Survivor','family':'Flowline'},None)
        with closing(sqlite3.connect(self.store.db_path)) as conn,conn:
            conn.execute('INSERT INTO asset_aliases VALUES (?,?,?)',(self.asset['id'],survivor['id'],'Consolidated evidence'))
            conn.execute('DELETE FROM assets WHERE id=?',(self.asset['id'],))
        preview = cleanup.preview_cleanup(self.store,{'category':'imports','ids':[self.batch]})
        self.assertEqual(preview['dependent_assets'],1)
        cleanup.apply_cleanup(self.store,preview['preview_id'],preview['confirmation'])
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            self.assertIn(survivor['id'],source_archive_problems(conn))

    def test_selected_asset_deletion_keeps_other_assets_and_journal(self):
        other = self.store.save_asset(None, {'name':'Other', 'family':'Flowline'}, None)
        self.apply('assets', [self.asset['id']])
        with self.assertRaises(KeyError): self.store.get_asset(self.asset['id'])
        self.assertEqual(self.store.get_asset(other['id'])['name'], 'Other')
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM correction_events WHERE asset_id=? AND origin='clear'", (self.asset['id'],)).fetchone())

    def test_bulk_asset_deletion_invalidates_peer_collisions_without_repeated_scans(self):
        current=self.store.get_asset(self.asset['id'])
        self.store.save_asset(current['id'],{'tag_original':'SHARED'},current['version'])
        peer=self.store.save_asset(None,{'name':'Peer','family':'Flowline','tag_original':'SHARED'},None)
        with closing(sqlite3.connect(self.store.db_path)) as conn,conn:
            for key,rule in [('collision','identity-collision'),('other','source-review')]:
                conn.execute('INSERT INTO quality_issues(issue_id,asset_id,rule_id,field,severity,message,fingerprint,state) VALUES (?,?,?,?,?,?,?,?)',(key,peer['id'],rule,'identity','warning','Recorded issue','fp','accepted_exception'))
            trace=[];conn.set_trace_callback(trace.append)
            cleanup._delete_assets(conn,[self.asset['id']],999)
            conn.set_trace_callback(None)
            self.assertEqual(dict(conn.execute('SELECT issue_id,state FROM quality_issues')),{'collision':'superseded','other':'accepted_exception'})
            self.assertFalse(any('SELECT id,details FROM assets' in query for query in trace))

    def test_reset_removes_working_data_and_keeps_all_backups(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute("INSERT INTO master_snapshots VALUES ('snap','{}')")
            conn.execute("INSERT INTO bulk_operations VALUES ('bulk','applied','{}')")
            conn.execute("INSERT INTO consolidation_previews VALUES ('preview','{}')")
        existing = {p:p.read_bytes() for p in (self.root/'backups').glob('*') if p.is_file()}
        old_epoch = cleanup.data_epoch(self.store)
        result = self.apply('reset')
        self.assertNotEqual(cleanup.data_epoch(self.store), old_epoch)
        self.assertFalse(self.archive.exists())
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            for table in cleanup.WORKING_TABLES:
                self.assertEqual(conn.execute('SELECT count(*) FROM '+table).fetchone()[0], 0, table)
            self.assertGreater(conn.execute('SELECT value FROM version_clock').fetchone()[0], 0)
        for path,contents in existing.items(): self.assertEqual(path.read_bytes(), contents)
        self.assertTrue(Path(result['recovery']).is_file())
        target = self.root/'restore';target.mkdir()
        restored = Store(target/'master.db');restore_master_package(restored, result['recovery'])
        self.assertEqual(restored.get_asset(self.asset['id'])['name'], 'Keep history')

    def test_stale_preview_and_wrong_confirmation_are_rejected(self):
        preview = cleanup.preview_cleanup(self.store, {'category':'reset'})
        with self.assertRaises(ValueError): cleanup.apply_cleanup(self.store, preview['preview_id'], 'wrong')
        self.store.save_asset(None, {'name':'New', 'family':'Flowline'}, None)
        with self.assertRaisesRegex(ValueError, 'changed|stale'):
            cleanup.apply_cleanup(self.store, preview['preview_id'], preview['confirmation'])
        self.assertTrue(self.archive.exists())

    def test_file_move_failure_rolls_back_assets_and_history(self):
        preview = cleanup.preview_cleanup(self.store, {'category':'reset'})
        original = cleanup.os.replace
        def fail_move(source, target):
            if Path(source).resolve() == self.archive.resolve(): raise PermissionError('Test locked archive')
            return original(source, target)
        with patch('inspection_app.cleanup.os.replace', side_effect=fail_move):
            with self.assertRaises(PermissionError): cleanup.apply_cleanup(self.store, preview['preview_id'], preview['confirmation'])
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_database_failure_restores_quarantined_files(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON assets BEGIN SELECT RAISE(ABORT,'test failure'); END")
        preview = cleanup.preview_cleanup(self.store, {'category':'reset'})
        with self.assertRaises(sqlite3.IntegrityError): cleanup.apply_cleanup(self.store, preview['preview_id'], preview['confirmation'])
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_second_file_move_failure_restores_first_file(self):
        asset = self.store.get_asset(self.asset['id'])
        self.store.save_asset(asset['id'],{'name':'Second source'},asset['version'])
        path = export_workbook(self.store,self.root/'second.xlsx')
        preview = preview_import(self.store,path);apply_import(self.store,preview['token'])
        plan = cleanup.preview_cleanup(self.store,{'category':'reset'})
        self.assertEqual(len(plan['files']),2)
        second = Path(plan['files'][1]['folder'])/plan['files'][1]['filename']
        original = cleanup.os.replace
        def fail_second(source,target):
            if Path(source).resolve()==second: raise PermissionError('Second archive locked')
            return original(source,target)
        with patch('inspection_app.cleanup.os.replace',side_effect=fail_second):
            with self.assertRaises(PermissionError): cleanup.apply_cleanup(self.store,plan['preview_id'],plan['confirmation'])
        for item in plan['files']: self.assertTrue((Path(item['folder'])/item['filename']).is_file())
        self.assertTrue(self.store.get_asset(asset['id']))

    def test_selected_snapshot_and_staged_import_deletion(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.executemany('INSERT INTO master_snapshots VALUES (?,?)', [('one','{}'),('two','{}')])
        self.apply('snapshots', ['one'])
        staged = preview_import(self.store, self.root/'source.xlsx')
        self.apply('staged', [staged['token']])
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            self.assertEqual(conn.execute('SELECT snapshot_id FROM master_snapshots').fetchall(), [('two',)])
            self.assertFalse(conn.execute('SELECT 1 FROM import_batches WHERE token=?', (staged['token'],)).fetchone())
        self.assertTrue(self.archive.exists())

    def test_recovery_packages_are_separately_managed_and_scope_checked(self):
        from inspection_app.recovery import export_master_package
        folder = self.root/'recovery-copies';folder.mkdir()
        package = export_master_package(self.store, folder/'inspection-recovery-20261102-123456-1234abcd.zip')
        unrelated = folder/'notes.zip';unrelated.write_bytes(b'Keep')
        items = cleanup.inventory(self.store)['items']['recovery_packages']
        self.assertEqual(len(items), 1)
        self.apply('recovery_packages', [items[0]['id']])
        self.assertFalse(package.exists())
        self.assertTrue(unrelated.exists())
        with self.assertRaises(ValueError): cleanup.preview_cleanup(self.store, {'category':'sources','ids':['../master.db']})

    def test_interrupted_file_move_is_recovered_on_startup(self):
        token = 'a'*32
        journal = cleanup._journal_path(self.store,token);journal.parent.mkdir()
        staged = self.archive.parent/('.cleanup-'+token)/self.archive.name
        staged.parent.mkdir();self.archive.rename(staged)
        journal.write_text(json.dumps({'moves':[{'source':str(self.archive.resolve()),'staged':str(staged.resolve())}]}))
        Store(self.store.db_path)
        self.assertTrue(self.archive.exists());self.assertFalse(staged.exists());self.assertFalse(journal.exists())

    def test_committed_deletion_is_finished_on_startup(self):
        token = 'b'*32
        journal = cleanup._journal_path(self.store,token);journal.parent.mkdir()
        staged = self.archive.parent/('.cleanup-'+token)/self.archive.name
        staged.parent.mkdir();self.archive.rename(staged)
        journal.write_text(json.dumps({'moves':[{'source':str(self.archive.resolve()),'staged':str(staged.resolve())}]}))
        with closing(sqlite3.connect(self.store.db_path)) as conn,conn:
            conn.execute('CREATE TABLE cleanup_receipts (token TEXT PRIMARY KEY)')
            conn.execute('INSERT INTO cleanup_receipts VALUES (?)',(token,))
        Store(self.store.db_path)
        self.assertFalse(self.archive.exists());self.assertFalse(staged.exists());self.assertFalse(journal.exists())

    def test_backup_failure_leaves_working_data_unchanged(self):
        preview = cleanup.preview_cleanup(self.store, {'category':'reset'})
        with patch('inspection_app.cleanup.automatic_backup',side_effect=OSError('Disk full')):
            with self.assertRaises(OSError): cleanup.apply_cleanup(self.store,preview['preview_id'],preview['confirmation'])
        self.assertTrue(self.archive.exists());self.assertTrue(self.store.get_asset(self.asset['id']))

    def test_reset_can_protect_a_dataset_with_an_already_missing_source(self):
        self.archive.unlink()
        preview=cleanup.preview_cleanup(self.store,{'category':'reset'})
        self.assertIn(self.digest,preview['unavailable_sources'])
        result=cleanup.apply_cleanup(self.store,preview['preview_id'],preview['confirmation'])
        self.assertIsNotNone(result['warning'])
        manifest=validate_restore_package(result['recovery'])
        self.assertIn(self.digest,manifest['unavailable_sources'])
        folder=self.root/'missing-restore';folder.mkdir();store=Store(folder/'master.db')
        restored=restore_master_package(store,result['recovery'])
        self.assertEqual(store.get_asset(self.asset['id'])['name'],'Keep history')
        self.assertIsNotNone(restored['warning'])

    def test_reset_protection_preserves_damaged_source_bytes_with_explicit_mapping(self):
        from zipfile import ZipFile
        import hashlib
        contents=b'Previously damaged source contents; preserve these bytes'
        self.archive.write_bytes(contents)
        result=self.apply('reset')
        manifest=validate_restore_package(result['recovery'])
        actual=hashlib.sha256(contents).hexdigest()
        self.assertEqual(manifest['source_relocations'][self.digest],actual)
        with ZipFile(result['recovery']) as archive:
            self.assertEqual(archive.read('source-archives/'+actual+'.xlsx'),contents)

    def test_protection_handles_swapped_content_addressed_source_files(self):
        current=self.store.get_asset(self.asset['id'])
        self.store.save_asset(current['id'],{'name':'Second original'},current['version'])
        path=export_workbook(self.store,self.root/'other-source.xlsx')
        batch=preview_import(self.store,path);apply_import(self.store,batch['token'])
        other=self.archive.with_name(batch['digest']+'.xlsx')
        original_a,original_b=self.archive.read_bytes(),other.read_bytes()
        self.archive.write_bytes(original_b);other.write_bytes(original_a)
        result=self.apply('reset')
        manifest=validate_restore_package(result['recovery'])
        self.assertEqual(manifest.get('unavailable_sources',[]),[])
        self.assertEqual(manifest['source_relocations'],{self.digest:batch['digest'],batch['digest']:self.digest})

    def test_interrupted_journal_publication_does_not_block_startup(self):
        preview = cleanup.preview_cleanup(self.store,{'category':'reset'})
        original = cleanup.os.replace
        def fail_publication(source,target):
            if Path(target).parent.name=='.cleanup-journals': raise OSError('Journal publication failure')
            return original(source,target)
        with patch('inspection_app.cleanup.os.replace',side_effect=fail_publication):
            with self.assertRaises(OSError): cleanup.apply_cleanup(self.store,preview['preview_id'],preview['confirmation'])
        self.assertTrue(self.archive.exists())
        self.assertFalse(list((self.root/'.cleanup-journals').glob('*.json')))
        # A process crash can leave an unpublished temporary file; ignore it.
        (self.root/'.cleanup-journals'/'incomplete.partial').write_text('{')
        self.assertEqual(Store(self.store.db_path).get_asset(self.asset['id'])['name'],'Keep history')

    def test_pending_package_cleanup_finishes_before_folder_change(self):
        from inspection_app.recovery import configure_backup_folder, automatic_backup
        import re
        old = self.root/'old copies'; old.mkdir()
        new = self.root/'new copies'; new.mkdir()
        unrelated = old/'keep.txt'; unrelated.write_text('keep')
        configure_backup_folder(self.store, str(old))
        package = Path(automatic_backup(self.store, force=True)['independent_path'])
        item = next(x for x in cleanup.inventory(self.store)['items']['recovery_packages'] if x['filename'] == package.name)
        unlink = Path.unlink
        def locked(path, *args, **kwargs):
            if re.fullmatch(r'\.cleanup-[0-9a-f]{32}', path.parent.name):
                raise OSError('locked')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', locked):
            result = self.apply('recovery_packages', [item['id']])
        self.assertIn('quarantined', result['warning'])
        configure_backup_folder(self.store, str(new))
        Store(self.store.db_path)
        self.assertEqual(unrelated.read_text(), 'keep')
        self.assertFalse(list((self.root/'.cleanup-journals').glob('*.json')))
        with sqlite3.connect(self.store.db_path) as conn:
            self.assertEqual(conn.execute('select count(*) from cleanup_receipts').fetchone()[0], 0)

    def test_folder_change_retries_when_pending_cleanup_remains_locked(self):
        from inspection_app.recovery import configure_backup_folder, automatic_backup, backup_status
        import re
        old = self.root/'old copies'; old.mkdir()
        new = self.root/'new copies'; new.mkdir()
        configure_backup_folder(self.store, str(old))
        package = Path(automatic_backup(self.store, force=True)['independent_path'])
        item = next(x for x in cleanup.inventory(self.store)['items']['recovery_packages'] if x['filename'] == package.name)
        unlink = Path.unlink
        def locked(path, *args, **kwargs):
            if re.fullmatch(r'\.cleanup-[0-9a-f]{32}', path.parent.name):
                raise OSError('locked')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', locked):
            self.apply('recovery_packages', [item['id']])
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                configure_backup_folder(self.store, str(new))
            self.assertEqual(backup_status(self.store)['folder'], str(old.resolve()))
        configure_backup_folder(self.store, str(new))
        Store(self.store.db_path)

    def test_deleting_last_independent_package_invalidates_status_and_retries(self):
        from inspection_app.recovery import configure_backup_folder,automatic_backup,backup_status
        folder = self.root/'other copies';folder.mkdir()
        configure_backup_folder(self.store,str(folder));status=automatic_backup(self.store,force=True)
        path = Path(status['independent_path'])
        item = next(x for x in cleanup.inventory(self.store)['items']['recovery_packages'] if x['filename']==path.name)
        self.apply('recovery_packages',[item['id']])
        self.assertFalse(backup_status(self.store)['independent_success'])
        self.assertNotIn('day',backup_status(self.store))
        self.store.save_asset(None,{'name':'Retry backup','family':'Flowline'},None)
        self.assertTrue(backup_status(self.store)['independent_success'])

    def test_reset_keeps_external_recovery_copies_and_configuration(self):
        from inspection_app.recovery import configure_backup_folder,automatic_backup,backup_status
        folder=self.root/'external copies';folder.mkdir()
        configure_backup_folder(self.store,str(folder));status=automatic_backup(self.store,force=True)
        old=Path(status['independent_path']);contents=old.read_bytes()
        result=self.apply('reset')
        self.assertEqual(old.read_bytes(),contents)
        self.assertEqual(backup_status(self.store)['folder'],str(folder.resolve()))
        self.assertEqual(Path(result['recovery']).parent,folder.resolve())

    def test_unicode_path_cleanup_with_windows_flush_requirement(self):
        from windows_io import windows_flush_requirement
        root=self.root/'تفتيش # 100%';root.mkdir()
        with windows_flush_requirement():
            store=Store(root/'خطة.db')
            preview=preview_import(store,self.root/'source.xlsx');apply_import(store,preview['token'])
            plan=cleanup.preview_cleanup(store,{'category':'reset'})
            result=cleanup.apply_cleanup(store,plan['preview_id'],plan['confirmation'])
            restored_folder=root/'restore';restored_folder.mkdir()
            target=Store(restored_folder/'master.db');restore_master_package(target,result['recovery'])
            self.assertEqual(target.get_asset(self.asset['id'])['name'],'Keep history')

"""Backup size reduction must preserve logical data and independent restores."""
from contextlib import closing
import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from inspection_app.store import Store
from inspection_app.backups import create_backup, restore_backup, list_backups, restore_saved_backup, delete_saved_backups
from inspection_app.recovery import automatic_backup, export_master_package, restore_master_package


def records(path):
    with closing(sqlite3.connect(path)) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(conn.execute('SELECT rowid,* FROM "'+name.replace('"', '""')+'"').fetchall(), key=repr) for name in tables}


class CompressedBackupTests(unittest.TestCase):
    def test_backups_publish_and_restore_with_windows_flush_requirement(self):
        from windows_io import windows_flush_requirement
        with windows_flush_requirement():
            for compressed in (False, True):
                path = create_backup(self.store, compress=compressed)
                self.assertTrue(path.is_file())
                restore_backup(self.store, path)
                self.assertEqual(self.store.get_asset(self.asset['id'])['name'], 'Original')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'master.db')
        self.asset = self.store.save_asset(None, {'name':'Original', 'family':'Flowline'}, None)

    def test_compaction_preserves_all_tables_and_live_file(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('CREATE TABLE disposable_space (contents BLOB)')
            conn.execute('INSERT INTO disposable_space VALUES (zeroblob(2000000))')
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('DROP TABLE disposable_space')
            conn.execute("INSERT INTO master_snapshots VALUES ('historical', '{}')")
        before = Path(self.store.db_path).read_bytes()
        backup = create_backup(self.store)
        self.assertEqual(records(backup), records(self.store.db_path))
        self.assertLess(backup.stat().st_size, len(before)//2)
        self.assertEqual(Path(self.store.db_path).read_bytes(), before)

    def test_automatic_backup_is_compressed_and_preserves_all_records(self):
        result = automatic_backup(self.store, force=True)
        path = Path(result['local_path'])
        self.assertTrue(path.name.endswith('.db.gz'))
        raw = self.root/'expanded.db'
        raw.write_bytes(gzip.decompress(path.read_bytes()))
        # Backup settings are updated after the snapshot; compare against a raw
        # snapshot taken before the automatic backup instead in the roundtrip test.
        self.assertEqual(records(raw)['assets'], records(self.store.db_path)['assets'])
        self.assertEqual(records(raw)['correction_events'], records(self.store.db_path)['correction_events'])
        self.assertLess(path.stat().st_size, raw.stat().st_size)

    def test_raw_and_compressed_backups_restore_history_and_snapshots(self):
        from inspection_app.quality import verify_fields
        verify_fields(self.store, self.asset['id'], self.asset['version'], ['name'], 'Disposable source evidence')
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute("INSERT INTO master_snapshots(rowid,snapshot_id,contents) VALUES (10,'older','{}')")
            conn.execute("INSERT INTO master_snapshots VALUES ('historical', '{}')")
        expected = records(self.store.db_path)
        raw = create_backup(self.store)
        compressed = create_backup(self.store, compress=True)
        extracted = self.root/'expanded.db'
        extracted.write_bytes(gzip.decompress(compressed.read_bytes()))
        self.assertEqual(records(extracted), expected)
        for path in (raw, compressed):
            current = self.store.get_asset(self.asset['id'])
            self.store.save_asset(current['id'], {'name':'Changed'}, current['version'])
            result = restore_backup(self.store, path)
            self.assertTrue(Path(result['safety_backup']).is_file())
            self.assertEqual(self.store.get_asset(current['id'])['name'], 'Original')
            restored = records(self.store.db_path)
            self.assertEqual(restored['correction_events'], expected['correction_events'])
            self.assertEqual(restored['master_snapshots'], expected['master_snapshots'])
            self.assertEqual(restored['field_verifications'], expected['field_verifications'])

    def test_mixed_saved_formats_restore_and_delete(self):
        raw = create_backup(self.store)
        compressed = create_backup(self.store, compress=True)
        self.assertTrue({raw.name, compressed.name} <= {r['filename'] for r in list_backups(self.store)})
        restore_saved_backup(self.store, compressed.name)
        restore_saved_backup(self.store, raw.name)
        self.assertEqual(delete_saved_backups(self.store, [compressed.name])['deleted'], [compressed.name])
        self.assertTrue(raw.is_file())

    def test_corrupt_truncated_and_oversized_gzip_preserve_live_data(self):
        compressed = create_backup(self.store, compress=True).read_bytes()
        before = records(self.store.db_path)
        for data in (compressed[:-5], compressed[:-8]+b'badcrc!!', gzip.compress(b'not SQLite')):
            upload = self.root/'upload.db'  # HTTP temporary extension cannot identify compression.
            upload.write_bytes(data)
            with self.assertRaises(ValueError):
                restore_backup(self.store, upload)
            self.assertEqual(records(self.store.db_path), before)
        upload.write_bytes(compressed)
        with patch('inspection_app.backups.MAX_BACKUP_BYTES', 32):
            with self.assertRaisesRegex(ValueError, 'large|limit'):
                restore_backup(self.store, upload)
        self.assertEqual(records(self.store.db_path), before)

    def test_failed_compression_keeps_previous_backup_and_cleans_partial_files(self):
        previous = create_backup(self.store, compress=True)
        before = {p.name for p in previous.parent.iterdir()}
        with patch('inspection_app.backups.gzip.open', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                create_backup(self.store, compress=True)
        self.assertEqual({p.name for p in previous.parent.iterdir()}, before)
        restore_backup(self.store, previous)

    def test_large_database_falls_back_to_raw_restorable_backup(self):
        # Never block editing or create a backup our bounded gzip reader rejects.
        with patch('inspection_app.backups.MAX_BACKUP_BYTES', 32):
            backup = create_backup(self.store, compress=True)
            self.assertEqual(backup.suffix, '.db')
            restore_backup(self.store, backup)
        self.assertEqual(self.store.get_asset(self.asset['id'])['name'], 'Original')

    def test_failed_publication_does_not_leave_incomplete_managed_backup(self):
        previous = create_backup(self.store, compress=True)
        before = {p.name for p in previous.parent.iterdir()}
        with patch('inspection_app.backups.os.replace', side_effect=OSError('Publication failed')):
            with self.assertRaises(OSError):
                create_backup(self.store, compress=True)
        self.assertEqual({p.name for p in previous.parent.iterdir()}, before)
        restore_backup(self.store, previous)

    def test_recovery_zip_contains_compact_database_with_all_records(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('CREATE TABLE disposable_space (contents BLOB)')
            conn.execute('INSERT INTO disposable_space VALUES (zeroblob(2000000))')
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('DROP TABLE disposable_space')
        expected = records(self.store.db_path)
        package = export_master_package(self.store, self.root/'recovery.zip')
        with ZipFile(package) as archive:
            raw = self.root/'package.db'
            raw.write_bytes(archive.read('master.db'))
        self.assertEqual(records(raw), expected)
        self.assertLess(raw.stat().st_size, Path(self.store.db_path).stat().st_size//2)
        target = Store(self.root/'target.db')
        restore_master_package(target, package)
        self.assertEqual(target.get_asset(self.asset['id'])['name'], 'Original')

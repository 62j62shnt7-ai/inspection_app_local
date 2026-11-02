"""Portable regressions for paths and operating-system file handles."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from inspection_app.backups import create_backup, restore_backup
from inspection_app.exports import export_workbook
from inspection_app.imports import preview_import, apply_import
from inspection_app.lock import data_lock
from inspection_app.store import Store


class WindowsCompatibilityTests(unittest.TestCase):
    def test_unicode_and_uri_characters_in_data_and_workbook_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Inspection plan تفتيش # 100%'
            root.mkdir()
            store = Store(root / 'خطة.db')
            asset = store.save_asset(None, {'name': 'خزان – Tank', 'family': 'Tank'}, None)
            backup = create_backup(store)
            workbook = root / 'Inspection plan تفتيش.xlsx'
            export_workbook(store, workbook)
            imported = Store(root / 'Imported.db')
            preview = preview_import(imported, workbook)
            self.assertFalse(preview['errors'])
            apply_import(imported, preview['token'])
            self.assertEqual(imported.get_asset(asset['id'])['name'], asset['name'])
            store.save_asset(asset['id'], {'name': 'Changed'}, asset['version'])
            restore_backup(store, backup)
            self.assertEqual(store.get_asset(asset['id'])['name'], asset['name'])
            # These operations fail on Windows if any source handles remain open.
            workbook.unlink()
            backup.unlink()
            Path(imported.db_path).unlink()
            Path(store.db_path).unlink()

    def test_data_lock_blocks_another_process_and_releases_after_exit(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "from pathlib import Path; from inspection_app.lock import data_lock; "
                "lock=data_lock(Path(sys.argv[2])); lock.__enter__(); lock.__exit__(None,None,None)")
        app_root = str(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable, '-I', '-c', code, app_root, tmp]
            with data_lock(Path(tmp)):
                blocked = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('already using this data folder', blocked.stderr)
            released = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(released.returncode, 0, released.stderr)

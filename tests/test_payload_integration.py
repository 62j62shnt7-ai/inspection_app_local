"""Compression must remain transparent to portable evidence workflows."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from inspection_app import payloads
from inspection_app.store import Store
from inspection_app.imports import preview_import, apply_import, read_workbook, _revision
from inspection_app.import_batches import load_batch, list_staged_batches, list_import_history
from inspection_app.exports import export_workbook
from inspection_app.backups import create_backup, restore_backup, validate_database
from inspection_app.recovery import export_master_package, restore_master_package, validate_restore_package
from inspection_app.cleanup import inventory, set_coverage_dismissed


class PayloadIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        producer = Store(self.root / 'producer.db')
        self.text = 'é漢字 retained evidence\n' * 2000
        asset = producer.save_asset(None, {
            'name': 'Synthetic', 'family': 'Flowline',
            'notes': [{'note_id': 'note-1', 'note_text': self.text, 'note_type': 'Remark'}],
            'source_cells': [{'source_sheet': 'Synthetic', 'source_row': 2, 'source_cell': 'A2', 'original_value': self.text, 'original_annotation': '{"extra": "retained"}'}],
        }, None)
        self.asset_id = asset['id']
        self.workbook = export_workbook(producer, self.root / 'input.xlsx')
        self.store = Store(self.root / 'master.db')

    def import_fixture(self):
        preview = preview_import(self.store, self.workbook)
        self.assertFalse(preview['errors'])
        apply_import(self.store, preview['token'])
        return preview

    def selected_values(self, path):
        with closing(sqlite3.connect(path)) as c:
            result = {}
            for table, columns in payloads.COLUMNS.items():
                names = [r[1] for r in c.execute(f'PRAGMA table_info({table})')]
                if not names: continue
                result[table] = [tuple(payloads.decode_text(v) if name in columns else v for name, v in zip(names, row)) for row in c.execute(f'SELECT * FROM {table} ORDER BY rowid')]
            return result

    def test_compressed_staging_survives_restart_and_import_export_roundtrip(self):
        preview = preview_import(self.store, self.workbook)
        staged = load_batch(self.store, preview['token'])
        with closing(sqlite3.connect(self.store.db_path)) as c, c:
            raw = c.execute('SELECT contents FROM import_batches').fetchone()[0]
            self.assertIsInstance(raw, bytes)  # Exercises actual compressed writes.
            c.execute('UPDATE import_batches SET contents=?', (payloads.encode_text(json.dumps(staged)),))
        self.store = Store(self.store.db_path)
        self.assertEqual(list_staged_batches(self.store)[0]['token'], preview['token'])
        self.assertEqual(load_batch(self.store, preview['token']), staged)
        apply_import(self.store, preview['token'])
        history = list_import_history(self.store)
        self.assertEqual(history[0]['assets'], 1)
        self.assertTrue(history[0]['source_available'])
        exported = export_workbook(self.store, self.root / 'out.xlsx')
        self.assertEqual(read_workbook(exported), read_workbook(self.workbook))
        second = Store(self.root / 'second.db')
        apply_import(second, preview_import(second, exported)['token'])
        self.assertEqual(second.get_asset(self.asset_id)['notes'][0]['note_text'], self.text)
        # Reimport matching reads compressed baselines and retained references.
        again = preview_import(self.store, exported)
        self.assertFalse(again['errors'])
        apply_import(self.store, again['token'])
        for table, column in [('source_baselines', 'contents'), ('import_reference', 'contents'), ('correction_events', 'after_json')]:
            with closing(sqlite3.connect(self.store.db_path)) as c:
                values = [r[0] for r in c.execute(f'SELECT {column} FROM {table}')]
                self.assertTrue(any(isinstance(v, bytes) for v in values), table)

    def test_backup_recovery_legacy_restore_and_preserved_history(self):
        preview = self.import_fixture()
        expected = self.selected_values(self.store.db_path)
        for compressed in (False, True):
            backup = create_backup(self.store, compress=compressed)
            target = Store(self.root / ('target-' + str(compressed) + '.db'))
            restore_backup(target, backup)
            self.assertEqual(self.selected_values(target.db_path), expected)
        package = export_master_package(self.store, self.root / 'recovery.zip')
        validate_restore_package(package)
        target_dir = self.root / 'recovered'; target_dir.mkdir()
        target = Store(target_dir / 'master.db')
        restore_master_package(target, package)
        self.assertEqual(self.selected_values(target.db_path), expected)
        self.assertEqual((target_dir / 'source-archives' / (preview['digest'] + '.xlsx')).read_bytes(), self.workbook.read_bytes())
        legacy = create_backup(self.store)
        with closing(sqlite3.connect(legacy)) as c, c:
            for table, columns in payloads.COLUMNS.items():
                for column in columns:
                    for rowid, raw in c.execute(f'SELECT rowid,{column} FROM {table}').fetchall():
                        c.execute(f'UPDATE {table} SET {column}=? WHERE rowid=?', (payloads.decode_text(raw), rowid))
            c.execute('UPDATE schema_info SET version=10')
        restore_backup(target, legacy)
        self.assertEqual(self.selected_values(target.db_path), expected)
        with closing(sqlite3.connect(target.db_path)) as c:
            self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 11)

    def test_cleanup_rewrites_and_revision_stability(self):
        preview = self.import_fixture()
        before = _revision(self.store)
        initial = inventory(self.store)
        with closing(sqlite3.connect(self.store.db_path)) as c, c:
            for table, columns in payloads.COLUMNS.items():
                for column in columns:
                    for rowid, raw in c.execute(f'SELECT rowid,{column} FROM {table}').fetchall():
                        c.execute(f'UPDATE {table} SET {column}=? WHERE rowid=?', (payloads.decode_text(raw), rowid))
        self.assertEqual(_revision(self.store), before)
        self.assertEqual(inventory(self.store), initial)
        with closing(sqlite3.connect(self.store.db_path)) as c, c:
            payloads.migrate_payloads(c)
        self.assertEqual(_revision(self.store), before)
        set_coverage_dismissed(self.store, preview['token'], True)
        self.assertTrue(list_import_history(self.store)[0]['dismissed'])
        with closing(sqlite3.connect(self.store.db_path)) as c:
            self.assertIsInstance(c.execute('SELECT contents FROM import_batches').fetchone()[0], bytes)

    def test_corrupt_compressed_backup_and_package_rejected_without_changes(self):
        self.import_fixture()
        bad = create_backup(self.store)
        with closing(sqlite3.connect(bad)) as c, c:
            raw = c.execute('SELECT after_json FROM correction_events LIMIT 1').fetchone()[0]
            self.assertIsInstance(raw, bytes)
            c.execute('UPDATE correction_events SET after_json=?', (raw[:-1],))
        before = Path(self.store.db_path).read_bytes()
        with self.assertRaises(ValueError): validate_database(self.store, bad)
        with self.assertRaises(ValueError): restore_backup(self.store, bad)
        self.assertEqual(Path(self.store.db_path).read_bytes(), before)
        # Correct package checksums cannot disguise an internally corrupt payload.
        manifest = {'format': 'inspection-master-recovery', 'version': 1, 'files': {'master.db': hashlib.sha256(bad.read_bytes()).hexdigest()}}
        archives = list((self.root / 'source-archives').glob('*.xlsx'))
        for archive in archives: manifest['files']['source-archives/' + archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
        package = self.root / 'bad.zip'
        with ZipFile(package, 'w', ZIP_DEFLATED) as z:
            z.write(bad, 'master.db')
            for archive in archives: z.write(archive, 'source-archives/' + archive.name)
            z.writestr('manifest.json', json.dumps(manifest))
        with self.assertRaises(ValueError): validate_restore_package(package)
        with self.assertRaises(ValueError): restore_master_package(self.store, package)
        self.assertEqual(Path(self.store.db_path).read_bytes(), before)

    def test_consolidation_relinks_compressed_reference_and_keeps_history(self):
        from inspection_app.consolidation import preview_consolidation, apply_consolidation
        self.import_fixture()
        survivor = self.store.save_asset(None, {'name': 'Survivor', 'family': 'Flowline'}, None)
        proposal = preview_consolidation(self.store, survivor['id'], self.asset_id)
        apply_consolidation(self.store, proposal['preview_id'], proposal['revision'], {c['field']: 'survivor' for c in proposal['conflicts']}, 'Synthetic duplicate evidence')
        self.assertEqual(self.store.get_asset(self.asset_id)['id'], survivor['id'])
        with closing(sqlite3.connect(self.store.db_path)) as c:
            raw = c.execute("SELECT contents FROM import_reference WHERE name='Source Cells'").fetchone()[0]
            self.assertIsInstance(raw, bytes)
            row = payloads.loads(raw)[0]
            self.assertEqual(row['asset_id'], survivor['id'])
            self.assertEqual(row['historical_asset_id'], self.asset_id)
            history = [payloads.loads(r[0]) for r in c.execute("SELECT before_json FROM correction_events WHERE asset_id=? AND origin='consolidation'", (self.asset_id,))]
            self.assertEqual(history[0]['notes'][0]['note_text'], self.text)

    def test_envelope_in_plain_json_table_rejected_before_restore(self):
        self.import_fixture()
        before = Path(self.store.db_path).read_bytes()
        compressed = payloads.dumps({'unexpected': 'x' * 10000})
        self.assertIsInstance(compressed, bytes)
        for table in ('master_snapshots', 'bulk_operations', 'consolidation_previews', 'backup_settings'):
            with self.subTest(table=table):
                bad = create_backup(self.store)
                with closing(sqlite3.connect(bad)) as c, c:
                    if table == 'master_snapshots': c.execute('INSERT INTO master_snapshots VALUES (?,?)', ('bad', compressed))
                    elif table == 'bulk_operations': c.execute('INSERT INTO bulk_operations VALUES (?,?,?)', ('bad', 'preview', compressed))
                    elif table == 'consolidation_previews': c.execute('INSERT INTO consolidation_previews VALUES (?,?)', ('bad', compressed))
                    else: c.execute('UPDATE backup_settings SET contents=?', (compressed,))
                with self.assertRaises(ValueError): validate_database(self.store, bad)
                with self.assertRaises(ValueError): restore_backup(self.store, bad)
                self.assertEqual(Path(self.store.db_path).read_bytes(), before)

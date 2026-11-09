from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from inspection_app.store import Store
from inspection_app import compression_maintenance as maintenance
from inspection_app.lock import data_lock


class CompressionMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.data = self.root / 'data'; self.data.mkdir()
        self.path = self.data / 'inspection_plan.db'
        store = Store(self.path)
        store.save_asset(None, {'name': 'Keep', 'family': 'Flowline'}, None)
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('UPDATE schema_info SET version=10')
            text = json.dumps({'preserve': 'é漢字' * 100000}, ensure_ascii=False)
            c.execute('UPDATE correction_events SET after_json=?', (text,))
            c.execute('INSERT INTO source_baselines VALUES (?,?)', ('asset-source', text))
            c.execute("INSERT INTO bulk_operations(rowid,operation_id,state,contents) VALUES (10,'old','applied','{}')")

    def test_reduction_preserves_every_table_value_and_backup(self):
        before = maintenance.database_fingerprint(self.path)
        report = maintenance.compress_database(self.path, self.root / 'independent')
        self.assertLess(report['after_bytes'], report['before_bytes'])
        self.assertEqual(maintenance.database_fingerprint(self.path), before)
        self.assertEqual(maintenance.database_fingerprint(report['backup']), before)
        self.assertEqual(json.loads(Path(report['report']).read_text())['verification'], 'passed')
        with closing(sqlite3.connect(report['backup'])) as c:
            self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 10)
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 11)
            self.assertEqual(c.execute('SELECT rowid FROM bulk_operations').fetchone()[0], 10)

    def test_locked_app_prevents_maintenance(self):
        before = self.path.read_bytes()
        with data_lock(self.data):
            with self.assertRaises(RuntimeError): maintenance.compress_database(self.path, self.root / 'independent')
        self.assertEqual(self.path.read_bytes(), before)

    def test_bad_candidate_never_replaces_original(self):
        before = self.path.read_bytes()
        real_migrate = maintenance.migrate_database
        def damaged(conn):
            real_migrate(conn)
            conn.execute("UPDATE assets SET name='WRONG'")
        with patch.object(maintenance, 'migrate_database', side_effect=damaged):
            with self.assertRaisesRegex(ValueError, 'preserv'):
                maintenance.compress_database(self.path, self.root / 'independent')
        self.assertEqual(self.path.read_bytes(), before)

    def test_install_failure_restores_original(self):
        before = maintenance.database_fingerprint(self.path)
        real_install = maintenance._install_candidate
        def interrupted(candidate, target):
            real_install(candidate, target)
            raise OSError('injected installation failure')
        with patch.object(maintenance, '_install_candidate', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'injected'):
                maintenance.compress_database(self.path, self.root / 'independent')
        self.assertEqual(maintenance.database_fingerprint(self.path), before)
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 10)

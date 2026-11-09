from inspection_app import payloads
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from inspection_app.store import Store
from inspection_app.mutations import clear_master
from inspection_app.quality import verify_fields


class ClearTests(unittest.TestCase):
    def test_clear_preserves_history_without_repeated_peer_scans(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'master.db')
            assets = [store.save_asset(None, {'name':f'Asset {i}', 'family':'Flowline', 'tag_original':'Shared'}, None) for i in range(3)]
            verify_fields(store, assets[0]['id'], assets[0]['version'], ['name'], 'Recorded evidence')
            with closing(sqlite3.connect(store.db_path)) as conn, conn:
                for key, asset_id, state in [('accepted',assets[0]['id'],'accepted_exception'),('resolved',assets[1]['id'],'resolved'),('open',assets[2]['id'],'open'),('historical','retired-asset','resolved')]:
                    conn.execute('INSERT INTO quality_issues(issue_id,asset_id,rule_id,field,severity,message,fingerprint,state) VALUES (?,?,?,?,?,?,?,?)', (key,asset_id,'identity-collision','identity','blocking','Shared tag','fingerprint',state))
                conn.execute("INSERT INTO master_snapshots VALUES ('snapshot','{}')")
                before = {row[0]:{'name':row[1],'family':row[2],**json.loads(row[3])} for row in conn.execute('SELECT id,name,family,details FROM assets')}
                old_events = conn.execute('SELECT * FROM correction_events ORDER BY event_id').fetchall()
                trace = []
                conn.set_trace_callback(trace.append)
                revision = clear_master(store, conn)
                conn.set_trace_callback(None)
                self.assertEqual(conn.execute('SELECT count(*) FROM assets').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT * FROM correction_events ORDER BY event_id LIMIT ?', (len(old_events),)).fetchall(), old_events)
                cleared = conn.execute("SELECT asset_id,before_json,after_json,revision FROM correction_events WHERE origin='clear'").fetchall()
                self.assertEqual({asset_id:payloads.loads(raw) for asset_id,raw,_,_ in cleared}, before)
                self.assertTrue(all(payloads.loads(after) is None and rev==revision for _,_,after,rev in cleared))
                self.assertEqual(conn.execute('SELECT evidence,active FROM field_verifications').fetchall(), [('Recorded evidence',0)])
                self.assertEqual(dict(conn.execute('SELECT issue_id,state FROM quality_issues')), {'accepted':'superseded','resolved':'superseded','open':'open','historical':'resolved'})
                self.assertEqual(conn.execute('SELECT contents FROM master_snapshots').fetchall(), [('{}',)])
                self.assertEqual(conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0], revision)
                # Repeated full peer scans make clear quadratic in the asset count.
                peer_scans = [sql for sql in trace if 'SELECT id,details FROM assets' in sql]
                self.assertEqual(peer_scans, [])

    def test_failed_clear_rolls_back_history_verification_and_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'master.db')
            asset = store.save_asset(None, {'name':'Retain', 'family':'Flowline'}, None)
            verify_fields(store, asset['id'], asset['version'], ['name'], 'Retain evidence')
            with closing(sqlite3.connect(store.db_path)) as conn:
                before = conn.execute('SELECT * FROM correction_events').fetchall()
            # A SQLite trigger reproduces a journal write failure without relying
            # on which Python function inserts clear history.
            with closing(sqlite3.connect(store.db_path)) as conn, conn:
                conn.execute("CREATE TRIGGER fail_clear BEFORE INSERT ON correction_events WHEN NEW.origin='clear' BEGIN SELECT RAISE(ABORT,'clear failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                with closing(sqlite3.connect(store.db_path)) as conn, conn:
                    clear_master(store, conn)
            self.assertEqual(store.get_asset(asset['id'])['name'], 'Retain')
            with closing(sqlite3.connect(store.db_path)) as conn:
                self.assertEqual(conn.execute('SELECT * FROM correction_events').fetchall(), before)
                self.assertEqual(conn.execute('SELECT active FROM field_verifications').fetchall(), [(1,)])

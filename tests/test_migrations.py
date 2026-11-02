from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from inspection_app.store import Store


class MigrationTests(unittest.TestCase):
    def test_upgrade_backs_up_existing_database_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db'
            with closing(sqlite3.connect(path)) as conn,conn:
                conn.execute('CREATE TABLE assets(id TEXT PRIMARY KEY,name TEXT NOT NULL,family TEXT NOT NULL,version INTEGER NOT NULL,details TEXT NOT NULL)')
                conn.execute("INSERT INTO assets VALUES ('a','Original','Flowline',7,'{}')")
            store=Store(path)
            self.assertEqual(store.get_asset('a')['name'],'Original')
            backups=list((Path(tmp)/'backups').glob('*migration*.db'))
            self.assertEqual(len(backups),1)
            Store(path)
            self.assertEqual(len(list((Path(tmp)/'backups').glob('*migration*.db'))),1)
            with closing(sqlite3.connect(backups[0])) as conn:
                self.assertEqual(conn.execute('SELECT version FROM assets').fetchone()[0],7)

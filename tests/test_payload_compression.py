from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from inspection_app import payloads
from inspection_app.store import Store, initialize_schema
from inspection_app.migrations import migrate_database


class PayloadCodecTests(unittest.TestCase):
    def test_exact_text_round_trip_and_small_values(self):
        for text in ('null', '{}', '""', json.dumps({'unknown': ['é漢字\x00' * 5000]}, ensure_ascii=False)):
            encoded = payloads.encode_text(text)
            self.assertEqual(payloads.decode_text(encoded), text)
            self.assertEqual(payloads.loads(encoded), json.loads(text))
        self.assertIsInstance(payloads.encode_text('{}'), str)
        self.assertIsInstance(payloads.encode_text('x' * 5000), bytes)
        self.assertEqual(payloads.loads(payloads.dumps({'extra': 'abc' * 5000}, ensure_ascii=False)), {'extra': 'abc' * 5000})
        text = os.urandom(100).hex()
        self.assertEqual(payloads.encode_text(text), text)

    def test_rejects_corruption(self):
        good = payloads.encode_text('é' * 5000)
        variants = [b'bad', good[:10], good[:-1], good + b'x', good[:len(payloads.MAGIC)-1] + b'9' + good[len(payloads.MAGIC):]]
        for offset in (len(payloads.MAGIC), len(payloads.MAGIC) + 8, len(good) - 5):
            bad = bytearray(good); bad[offset] ^= 1; variants.append(bytes(bad))
        for bad in variants:
            with self.subTest(raw=bad[:20]), self.assertRaises(ValueError):
                payloads.decode_text(bad)

    def test_decoder_enforces_limit_and_valid_utf8(self):
        good = payloads.encode_text('x' * 5000)
        with patch.object(payloads, 'MAX_PAYLOAD_BYTES', 100):
            with self.assertRaises(ValueError): payloads.decode_text(good)
            with self.assertRaises(ValueError): payloads.encode_text('x' * 101)
        raw = b'\xff' * 2000
        envelope = payloads.MAGIC + struct.pack('>Q', len(raw)) + hashlib.sha256(raw).digest() + zlib.compress(raw)
        with self.assertRaises(ValueError): payloads.decode_text(envelope)
        # A forged small declaration must not allow a much larger expansion.
        envelope = payloads.MAGIC + struct.pack('>Q', 10) + hashlib.sha256(b'x' * 5000).digest() + zlib.compress(b'x' * 5000)
        with self.assertRaises(ValueError): payloads.decode_text(envelope)


class PayloadMigrationTests(unittest.TestCase):
    def test_exact_migration_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'old.db'
            text = '{ "extra" : "' + 'é漢字' * 3000 + '" }'
            with closing(sqlite3.connect(path)) as c, c:
                initialize_schema(c)
                c.execute('UPDATE schema_info SET version=10')
                c.execute('CREATE TABLE import_reference(name TEXT PRIMARY KEY, contents TEXT NOT NULL)')
                c.execute('INSERT INTO assets VALUES (?,?,?,?,?)', ('a', 'Original', 'Flowline', 7, '{}'))
                c.execute('INSERT INTO import_reference VALUES (?,?)', ('Source Cells', text))
                c.execute('INSERT INTO source_baselines VALUES (?,?)', ('a', text))
                c.execute('INSERT INTO import_batches VALUES (?,?,?,?,?)', ('t', 'cancelled', 'd', 'r', text))
                c.execute('INSERT INTO correction_events(asset_id,revision,origin,actor,reason,occurred_at,before_json,after_json) VALUES (?,?,?,?,?,?,?,?)', ('a', 7, 'manual', 'Owner', 'reason', 'time', text, 'null'))
            Store(path)
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 11)
                for table, column in [('import_reference', 'contents'), ('import_batches', 'contents'), ('source_baselines', 'contents'), ('correction_events', 'before_json')]:
                    raw = c.execute(f'SELECT {column} FROM {table}').fetchone()[0]
                    self.assertIsInstance(raw, bytes)
                    self.assertEqual(payloads.decode_text(raw), text)
                self.assertEqual(c.execute('SELECT * FROM assets').fetchone(), ('a', 'Original', 'Flowline', 7, '{}'))
                original = c.execute('SELECT before_json FROM correction_events').fetchone()[0]
            Store(path)
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute('SELECT before_json FROM correction_events').fetchone()[0], original)
            backups = list((Path(tmp) / 'backups').glob('*migration*.db'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as c:
                self.assertEqual(c.execute('SELECT contents FROM source_baselines').fetchone()[0], text)
                self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 10)

    def test_failed_migration_rolls_back_all_payloads_and_schema(self):
        with closing(sqlite3.connect(':memory:')) as c:
            initialize_schema(c)
            c.execute('UPDATE schema_info SET version=10')
            c.execute('INSERT INTO source_baselines VALUES (?,?)', ('a', json.dumps({'a': 'x' * 10000})))
            c.execute('INSERT INTO source_baselines VALUES (?,?)', ('b', b'damaged'))
            c.commit()
            before = c.execute('SELECT * FROM source_baselines').fetchall()
            with self.assertRaises(ValueError):
                with c: migrate_database(c)
            self.assertEqual(c.execute('SELECT * FROM source_baselines').fetchall(), before)
            self.assertEqual(c.execute('SELECT version FROM schema_info').fetchone()[0], 10)

    def test_older_app_guard_rejects_new_schema_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'new.db'
            Store(path)
            before = path.read_bytes()
            with patch('inspection_app.migrations.SCHEMA_VERSION', 10):
                with self.assertRaisesRegex(ValueError, 'newer version'):
                    Store(path)
            self.assertEqual(path.read_bytes(), before)

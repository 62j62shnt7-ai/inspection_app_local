"""Idempotent schema upgrades; called within the initialization transaction."""

SCHEMA_VERSION = 11


def migrate_database(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS schema_info (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)')
    existing = conn.execute('SELECT version FROM schema_info WHERE id=1').fetchone()
    if existing and existing[0] > SCHEMA_VERSION:
        raise ValueError('This database requires a newer version of the app')
    conn.execute('''CREATE TABLE IF NOT EXISTS correction_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL,
        revision INTEGER NOT NULL, origin TEXT NOT NULL, actor TEXT NOT NULL,
        reason TEXT NOT NULL, occurred_at TEXT NOT NULL,
        before_json TEXT NOT NULL, after_json TEXT NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS correction_events_asset ON correction_events(asset_id, event_id)')
    conn.execute("""CREATE TABLE IF NOT EXISTS field_verifications (
        verification_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL,
        field TEXT NOT NULL, fingerprint TEXT NOT NULL, evidence TEXT NOT NULL,
        actor TEXT NOT NULL, verified_at TEXT NOT NULL, rules_version TEXT NOT NULL, revision INTEGER NOT NULL)""")
    if 'active' not in {r[1] for r in conn.execute('PRAGMA table_info(field_verifications)')}:
        conn.execute('ALTER TABLE field_verifications ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
    conn.execute('CREATE INDEX IF NOT EXISTS verification_asset ON field_verifications(asset_id, field)')
    conn.execute("""CREATE TABLE IF NOT EXISTS quality_issues (
        issue_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, rule_id TEXT NOT NULL,
        field TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
        fingerprint TEXT NOT NULL, state TEXT NOT NULL, evidence TEXT, resolved_at TEXT)""")
    if 'expected_fingerprint' not in {r[1] for r in conn.execute('PRAGMA table_info(quality_issues)')}:
        conn.execute('ALTER TABLE quality_issues ADD COLUMN expected_fingerprint TEXT')
    conn.execute("""CREATE TABLE IF NOT EXISTS import_batches (
        token TEXT PRIMARY KEY, state TEXT NOT NULL, digest TEXT NOT NULL,
        base_revision TEXT NOT NULL, contents TEXT NOT NULL)""")
    conn.execute('CREATE TABLE IF NOT EXISTS master_snapshots (snapshot_id TEXT PRIMARY KEY, contents TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS bulk_operations (operation_id TEXT PRIMARY KEY, state TEXT NOT NULL, contents TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS asset_aliases (retired_id TEXT PRIMARY KEY,survivor_id TEXT NOT NULL,evidence TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS consolidation_previews (preview_id TEXT PRIMARY KEY,contents TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS source_baselines (asset_id TEXT PRIMARY KEY, contents TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS import_batch_assets (token TEXT NOT NULL, asset_id TEXT NOT NULL,PRIMARY KEY(token,asset_id))')
    if existing and existing[0]<9:
        import json
        for token,raw in conn.execute("SELECT token,contents FROM import_batches WHERE state='committed'").fetchall():
            batch=json.loads(raw)
            conn.executemany('INSERT OR IGNORE INTO import_batch_assets VALUES (?,?)',[(token,a['asset_id']) for a in batch.get('data',{}).get('Assets',[])])
    if not existing or existing[0] < 11:
        from .payloads import migrate_payloads
        migrate_payloads(conn)
    conn.execute('INSERT OR REPLACE INTO schema_info VALUES (1, ?)', (SCHEMA_VERSION,))


def backup_before_migration(db_path):
    from contextlib import closing
    from pathlib import Path
    from datetime import datetime
    import sqlite3
    import secrets
    path=Path(db_path)
    if not path.is_file() or not path.stat().st_size:return
    with closing(sqlite3.connect(str(path))) as source:
        has_assets=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assets'").fetchone()
        if not has_assets:return
        has_schema=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone()
        row=source.execute('SELECT version FROM schema_info WHERE id=1').fetchone() if has_schema else None
        if row and row[0]>SCHEMA_VERSION:raise ValueError('This database requires a newer version of the app')
        if row and row[0]==SCHEMA_VERSION:return
        folder=path.parent/'backups';folder.mkdir(exist_ok=True)
        target=folder/('inspection-migration-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
        with closing(sqlite3.connect(target)) as backup:source.backup(backup)

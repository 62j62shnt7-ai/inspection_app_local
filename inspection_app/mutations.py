"""Shared transactional revision allocation and correction journal.

Callers own the SQLite transaction: tokens and events roll back with records.
"""
import json
from . import payloads
from datetime import datetime, timezone


def next_revision(conn):
    conn.execute('UPDATE version_clock SET value=value+1 WHERE id=1')
    return conn.execute('SELECT value FROM version_clock WHERE id=1').fetchone()[0]


def record_event(conn, asset_id, before, after, origin, revision, actor='Owner', reason=''):
    if origin in ('manual','import','reconciliation','clear','bulk','bulk-revert','consolidation'):
        from .quality import invalidate_verifications
        invalidate_verifications(conn, asset_id, before, after)
    _append_event(conn, asset_id, before, after, origin, revision, actor, reason)


def _append_event(conn, asset_id, before, after, origin, revision, actor='Owner', reason=''):
    conn.execute('''INSERT INTO correction_events
        (asset_id, revision, origin, actor, reason, occurred_at, before_json, after_json)
        VALUES (?,?,?,?,?,?,?,?)''',
        (asset_id, revision, origin, actor, reason,
         datetime.now(timezone.utc).isoformat(),
         payloads.dumps(before, ensure_ascii=False, default=str),
         payloads.dumps(after, ensure_ascii=False, default=str)))


def clear_master(store, conn):
    revision = next_revision(conn)
    # All live assets are being removed, so invalidate their evidence once.
    # Per-asset identity invalidation scans every peer and makes clear quadratic.
    # Keep evidence rows and historical issues for previously retired assets.
    conn.execute('UPDATE field_verifications SET active=0 WHERE asset_id IN (SELECT id FROM assets)')
    conn.execute("UPDATE quality_issues SET state='superseded' WHERE asset_id IN (SELECT id FROM assets) AND state IN ('resolved','accepted_exception')")
    for asset_id, name, family, details in conn.execute('SELECT id,name,family,details FROM assets').fetchall():
        _append_event(conn, asset_id, {'name': name, 'family': family, **json.loads(details)}, None, 'clear', revision)
    conn.execute('DELETE FROM assets')
    conn.execute('DROP TABLE IF EXISTS import_reference')
    conn.execute("UPDATE import_batches SET state='cancelled' WHERE state='staged'")
    return revision

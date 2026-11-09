"""Lossless, versioned encoding for selected SQLite JSON payload columns.

Only storage boundaries use this codec. Plain JSON TEXT remains readable; BLOBs
must be a valid envelope. No global SQLite adapters or JSON hooks are installed.
"""
import hashlib
import json
import struct
import zlib

MAGIC = b'INSPECTION-JSON-ZLIB\x00\x01'
MAX_PAYLOAD_BYTES = 1024 * 1024 * 1024  # Same ceiling as expanded database backups.
MIN_COMPRESS_BYTES = 1024
_HEADER_SIZE = len(MAGIC) + 8 + 32

# Keep this list explicit: asset details participate in raw revision hashes,
# and snapshots are queried using SQLite JSON functions.
COLUMNS = {
    'correction_events': ('before_json', 'after_json'),
    'import_batches': ('contents',),
    'source_baselines': ('contents',),
    'import_reference': ('contents',),
}


def encode_text(text):
    """Preserve exact UTF-8 bytes, compressing only when the envelope is smaller."""
    if not isinstance(text, str):
        raise ValueError('Database payload must be text')
    raw = text.encode('utf-8')
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError('Database payload exceeds the 1 GiB limit')
    if len(raw) < MIN_COMPRESS_BYTES:
        return text
    compressed = zlib.compress(raw, level=6)
    if _HEADER_SIZE + len(compressed) >= len(raw):
        return text
    return MAGIC + struct.pack('>Q', len(raw)) + hashlib.sha256(raw).digest() + compressed


def decode_text(value):
    """Decode legacy text or a strict, size-bounded compressed envelope."""
    if isinstance(value, str):
        if len(value.encode('utf-8')) > MAX_PAYLOAD_BYTES:
            raise ValueError('Database payload exceeds the 1 GiB limit')
        return value
    if not isinstance(value, bytes) or len(value) < _HEADER_SIZE or not value.startswith(MAGIC):
        raise ValueError('Unsupported or damaged compressed database payload')
    size = struct.unpack('>Q', value[len(MAGIC):len(MAGIC) + 8])[0]
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError('Database payload exceeds the 1 GiB limit')
    expected = value[len(MAGIC) + 8:_HEADER_SIZE]
    try:
        stream = zlib.decompressobj()
        # At most one byte beyond the declaration: never decompress an unbounded
        # stream or flush() a stream that might still contain expansive input.
        raw = stream.decompress(value[_HEADER_SIZE:], size + 1)
        if len(raw) != size or not stream.eof or stream.unused_data or stream.unconsumed_tail:
            raise ValueError('Compressed database payload has invalid length or stream')
        if hashlib.sha256(raw).digest() != expected:
            raise ValueError('Compressed database payload checksum mismatch')
        return raw.decode('utf-8')
    except (zlib.error, UnicodeError) as exc:
        raise ValueError('Compressed database payload is damaged') from exc


def dumps(value, **kwargs):
    return encode_text(json.dumps(value, **kwargs))


def loads(value):
    return json.loads(decode_text(value))


def migrate_payloads(conn):
    """Convert in the caller's transaction; retain exact original JSON text."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, columns in COLUMNS.items():
        if table not in tables:
            continue
        # Read one row at a time, using another cursor to update. These tables
        # have rowid and conversion never changes row identity or ordering.
        selected = ','.join(columns)
        for row in conn.execute(f'SELECT rowid,{selected} FROM {table}'):
            converted = []
            for value in row[1:]:
                text = decode_text(value)
                json.loads(text)  # Fail migration on damaged legacy JSON, too.
                converted.append(encode_text(text))
            if tuple(converted) != row[1:]:
                assignments = ','.join(column + '=?' for column in columns)
                conn.execute(f'UPDATE {table} SET {assignments} WHERE rowid=?', (*converted, row[0]))


def validate_payloads(conn):
    """Validate selected payloads without changing any stored bytes."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, columns in COLUMNS.items():
        if table in tables:
            for row in conn.execute(f"SELECT {','.join(columns)} FROM {table}"):
                for value in row:
                    loads(value)

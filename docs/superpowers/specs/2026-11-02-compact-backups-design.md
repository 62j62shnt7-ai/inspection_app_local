# Compact, compressed backups

Approved scope: compact and compress new backups without losing history or recovery functionality; keep existing backups restorable.

Use SQLite backup into a disposable database, VACUUM that copy, and check integrity. Automatic local backups become gzip-compressed `.db.gz` files, published atomically only when complete. Restore detects gzip by content (uploads have temporary names), decompresses into a bounded temporary file, and uses the existing validated restore and safety-backup path. Existing raw databases remain supported. Saved-backup listing/deletion recognizes both managed formats. Recovery ZIP structure remains unchanged, with a compact database and all archived workbooks. No operational database compaction, history deletion, retention changes, or conversion/deletion of existing backups.

Alternatives considered: compaction alone saves only unused space; shared/differential archives reduce duplication but make restores dependent on other files. Self-contained compressed copies preserve independent recovery.

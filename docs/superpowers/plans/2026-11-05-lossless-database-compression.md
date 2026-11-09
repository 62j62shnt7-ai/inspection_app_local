# Lossless Database Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce retained payload storage without losing data or history or changing interchange behavior.

**Architecture:** An explicit versioned zlib BLOB codec preserves original UTF-8 bytes. Schema 11 migrates selected payload columns transactionally; plain JSON remains readable. Assets and SQLite JSON snapshot queries stay unchanged.

**Tech Stack:** Python standard library, SQLite, zlib, unittest, existing openpyxl interchange.

**Spec:** docs/superpowers/specs/2026-11-05-lossless-database-compression-design.md

## Global Constraints
- Preserve existing uncommitted UI work.
- Development and tests use disposable databases.
- Never remove history, source evidence, backups or identities.
- No new runtime dependency; macOS/Windows compatible code.
- Operational installation requires a data-directory lock, independent backup and exact decoded-value comparison.

## Review Focus
- Unknown/corrupt compressed payloads must fail closed before restore.
- Legacy plain-text backups and mixed rows must remain readable.
- Import revisions must not change merely because payload storage changed.
- Cleanup and consolidation rewrites must continue compressing selected columns.
- Failed migration must roll back rows and schema version together.

### Task 1: Codec and migration
Files: new inspection_app/payloads.py; inspection_app/migrations.py; tests/test_payload_compression.py.
Interfaces: encode_text(str)->str|bytes; decode_text(str|bytes)->str; dumps(value,**kwargs)->str|bytes; loads(raw)->object; migrate_payloads(conn)->None.
- [x] Add failing tests for exact-byte Unicode/JSON round trips, incompressible/small text, corruption, limits, schema-10 migration, idempotency and rollback.
- [x] Run focused unittest discovery to confirm failure before implementation.
- [x] Implement versioned magic, length, SHA-256 and bounded strict zlib decoder; 1024-byte threshold and 1 GiB maximum decoded payload. Migrate only selected columns before advancing schema version to 11.
- [x] Run focused tests.

### Task 2: Storage boundaries and compatibility
Files: mutations.py, import_batches.py, imports.py, import_identity.py, exports.py, consolidation.py, cleanup.py, backups.py, recovery.py; affected tests and new compression integration tests.
Interfaces: consume Task 1 codec only at selected column boundaries; external JSON and asset details unchanged.
- [x] Add round-trip tests covering compressed history/imports/baselines/references, backup and gzip restore, recovery ZIPs, workbook export/import and corrupt-backup rejection.
- [x] Replace selected-column JSON reads/writes explicitly and retain legacy reads.
- [x] Verify import hashes remain stable, restart staging works, and cleanup/consolidation stay compatible.
- [x] Run focused tests, then full Python and Node suites; document schema compatibility in README/data contract.

### Task 3: Review and operational reduction
Files: reusable maintenance script and preservation report in database-maintenance-backups (operational evidence, not test fixtures).
Interfaces: data_lock, sqlite backup, migration, codec, export tables.
- [x] Review final diff for missed boundaries and failure paths; fix and repeat relevant checks.
- [x] Under the app lock, independently back up original and prepare a candidate in the maintenance folder; migrate, compact and integrity-check candidate.
- [x] Compare exact decoded selected values, every other table/value except schema version, sqlite_sequence, schema objects and export tables.
- [x] Validate backup/recovery and workbook compatibility using disposable synthetic fixtures; never run restore/import against operational data.
- [x] Install verified candidate through SQLite backup under the same lock, compact active file, reverify all content and retain independent backup and report.

## Execution record
- Task 1: codec tests first failed on missing module, then passed. Migration preserves exact JSON text and rolls back malformed payload conversion; old-app schema guard tested.
- Task 2: integration tests first failed on missing compressed writes/readers, then passed after explicit boundary updates. Full Python suite: 279 passed; Node suite: 105 passed. Existing direct-SQL evidence assertions now use the payload decoder. No UI code changed by this work.
- Task 3: maintenance tests first failed on missing module, then 4 passed, covering active-app lock, exact preservation, candidate rejection and rollback after installation failure. Final independent review pending before operational installation.
- Implementation choices within approved design: 1024-byte threshold, zlib level 6, versioned binary envelope with UTF-8 byte length and SHA-256, 1 GiB maximum decoded value. Deterministic temporary UUID generation compares workbook exports where exporter normally generates missing IDs; it never writes IDs back to the database.

- Final review: one Important finding fixed. Backup validator accepted compressed envelopes in unsupported plain-JSON tables. Regression test failed for all four tables, then passed with explicit table/column decoder selection; full suite 280/280 Python and 105/105 Node passed. No deferred findings.
- Operational maintenance: data-directory lock acquired; independent schema-10 original retained. Active database reduced from 44,974,080 to 12,640,256 bytes (32,333,824 bytes reclaimed). Exact decoded values, all table rows/rowids, schema objects, sequence values and workbook export tables match the original; schema intentionally advanced to 11. SQLite integrity_check passed and free pages are zero. Independent post-install fingerprint comparison also passed.
- Preservation report and original: database-maintenance-backups/lossless-compression-20261105-195914-ln706513/. Existing UI changes were preserved. Native Windows and owner acceptance were not tested.

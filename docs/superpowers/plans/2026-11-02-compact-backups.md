# Compact Backups Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Reduce new backup size while preserving complete history and old restores.
**Architecture:** Compact disposable SQLite copies, gzip automatic local backups, detect compression during restore, keep recovery ZIPs self-contained.
**Tech Stack:** Python standard library sqlite3, gzip, tempfile, unittest; existing browser JS.
**Spec:** docs/superpowers/specs/2026-11-02-compact-backups-design.md

## Global Constraints
Preserve all history, source evidence and existing backups. Never alter operational data during development. Maintain macOS/Windows compatibility; native Windows remains unverified.

## Review Focus
- Truncated/corrupt gzip must fail before live changes.
- Expansion limit must prevent unbounded temporary output.
- Failed publication must not leave managed-looking partial backups.
- Mixed old/new backup lists must restore and delete only requested files.
- Copy compaction must preserve every table's records, including history and snapshots.

### Task 1: Backup storage and restore
Files: inspection_app/backups.py, inspection_app/recovery.py, tests/test_compressed_backups.py.
Interfaces: create_backup(store, compress=False) returns Path; materialized_database(path) yields raw Path; compact_database_copy(source, destination) writes validated copy.
- [x] Write regression tests for compressed automatic backups, copy compaction and full logical-table equality, raw and compressed restores, checksum/truncation/size rejection, mixed listing/deletion, failed publication.
- [x] Run new tests and confirm expected failures.
- [x] Implement standard-library copy compaction, atomic gzip publication and bounded restore materialization; use compact copy in recovery exports.
- [x] Run focused backup/recovery/HTTP tests and adapt tests that previously opened automatic backups directly as SQLite.

### Task 2: User flow, docs, verification
Files: static/index.html, README.md, tests/test_http_inprocess.py.
- [x] Test HTTP compressed upload and saved restore; retain legacy raw restore coverage.
- [x] Accept .gz uploads and explain compressed local backups in documentation.
- [x] Run all Python and Node tests, a disposable live browser restore flow, and review the final diff.

Execution ruling: reuse the current feature checkout and preserve its uncommitted work. User explicitly requested proceeding; no additional approval gate. Leave changes uncommitted to avoid combining unrelated work.

Verification: nine compression regressions cover table/rowid equality, populated verification history, truncation/CRC/size rejection, old/raw restore, mixed management and publication/compression failures. HTTP raw/compressed uploads pass. Disposable live browser compressed restore recovered original record; backup-copy test succeeded. Independent reviewer could not run because of a usage limit; reviewed changes inline.

Ruling: use raw compact `.db` for generated copies larger than the 1 GiB bounded decompression limit, preserving recovery and allowing protected edits. No existing backups converted or removed.

Final results: 201/201 Python tests passed on Python 3.14 and Python 3.11; 78/78 Node tests passed. Homebrew Python 3.11 initially lacked openpyxl; its full rerun passed using temporary copies of the already-installed pure-Python openpyxl/et_xmlfile dependencies, with no environment installation. Disposable reference-workbook import: 26,382,336 bytes original SQLite, 21,757,952 bytes compact SQLite, 1,511,609 bytes gzip (94.3% reduction). Native Windows remains unverified. Live test server and tab closed; operational data untouched.

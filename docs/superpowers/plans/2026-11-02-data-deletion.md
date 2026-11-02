# Data deletion implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; preserve the current checkout and uncommitted work.

**Goal:** Owner-controlled cleanup, dismissible coverage and complete working-data reset with separately managed backups.
**Architecture:** A cleanup module provides inventory, revision-bound previews, protected mutations and rollback of managed files. A dedicated browser script renders selections and exact confirmation previews. Existing imports use small metadata flags for dismissed coverage and explicitly deleted source evidence; quality keeps missing-evidence lineage.
**Tech Stack:** Python standard library, SQLite, existing JavaScript and HTML.
**Spec:** docs/superpowers/specs/2026-11-02-data-deletion-design.md

## Global constraints
Never use operational data for testing. Preserve existing edits. Full reset keeps database backups, recovery ZIPs and backup configuration. Deleting a source cannot silently remove missing-evidence checks. Preserve revision watermark; reject stale browser mutations after reset. Windows native execution remains unverified.

## Review focus
Shared source archives; missing source archives during later recovery; stale previews and browser sessions; rollback after partial file moves; separately configured recovery folders and symlinks.

### Task 1 — backend and evidence semantics
Files: inspection_app/cleanup.py (new), imports history/recovery/store/server integration, tests/test_cleanup.py (new).
Interfaces: inventory(store), preview_cleanup(store, request), apply_cleanup(store, preview_id, confirmation), set_coverage_dismissed(store, batch_id, dismissed), data_epoch(store).
- [x] Write failing tests for preview-only behavior, selected deletion, dismissal/undo, shared archives, missing-evidence lineage, reset preserving backups, stale revisions, file/transaction failures and roundtrip recovery.
- [x] Implement inventory and immutable preview calculation; save recovery before data deletion; quarantine and roll back managed files, with durable receipts for interrupted operations.
- [x] Add routes and reset-epoch checks; adapt source coverage and recovery to explicit source deletion.
- [x] Run focused backend and HTTP tests.

### Task 2 — browser controls
Files: static/cleanup.js (new), static/index.html, static/app.js, static/quality.js; tests/cleanup.test.cjs (new).
- [x] Write failing browser-logic tests for category selection, preview confirmation, coverage controls and browser-state cleanup.
- [x] Add inventory/category controls, per-item selection, reset and separately managed recovery ZIP deletion; add per-asset, snapshot and staged-import shortcuts.
- [x] Rename Clear database to Clear asset register and explain retention. Explain coverage and embedded copies. Reset app-owned drafts/reconciliation state and reload on epoch changes.
- [x] Verify with Node tests and a live disposable browser.

### Task 3 — delivery
- [x] Run complete Python and Node suites; review safety paths and roundtrips.
- [x] Update owner documentation, build a complete Windows ZIP without operational data, and test its extracted contents with Python 3.11.

Authorization: owner approved the design and selected separately managed backups. Implement inline without additional approval gates. Leave changes uncommitted rather than combine unrelated work.

Final verification: 232 Python tests passed on Python 3.14 and on the extracted Windows package with host Python 3.11 and only the packaged dependencies, under a Unicode/space/#/% path. 83 Node tests passed. Live disposable browser checks covered dismissal/undo, cancelled preview, full reset with separately retained backup/recovery files, import-evidence deletion retaining the asset, and the existing missing-source warning. Native Windows and power-loss durability remain unverified.

Independent review found consolidated-identity lineage, epoch loss on restore and interrupted journal publication issues. All were reproduced and fixed with regressions; follow-up review confirmed the fixes. The incomplete-source fallback subsequently gained a regression for swapped content-addressed archives and normalizes availability against final packaged hashes. Ordinary recovery downloads remain strict.

Ruling: incomplete existing datasets remain clearable. Cleanup-only safety packages explicitly record source gaps and preserve damaged bytes under their actual content hashes with relocation mappings; they do not claim to recreate already-missing originals. This keeps the database snapshot exact and source warnings visible. Optional backup packages remain independently deletable; no operational deletion was performed.

Delivered package: inspection-app-windows-2026-11-02-data-cleanup.zip. All source changes are uncommitted to preserve the existing mixed work. Disposable servers and browser closed.

# In-app import duplicate resolution implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the user resolve original-plan identity conflicts inside the preview.
**Architecture:** Isolate matching in import_identity.py; keep raw extracted tables in each staged preview and add a JSON resolution endpoint. Persist reviewed choices in the existing transactional reference store and optional export sheet.
**Tech Stack:** Existing Python/openpyxl/SQLite and native JavaScript.
**Spec:** docs/superpowers/specs/2026-11-01-import-duplicate-resolution-design.md

## Global constraints

- Preserve the existing checkout's unrelated modifications and user's database.
- No guessed matching, inferred merging or silently deleting skipped records.
- All explicit choices receive a fresh preview, stale-data validation and backup before final apply.

## Review focus

- A separate asset must not overwrite an existing asset with the same source-derived ID.
- Repeated rows with identical values must still have distinct decision keys.
- Changed or moved rows must not inherit stale saved decisions.
- Skipped rows must keep original evidence and protect existing records in merge.
- Old asynchronous responses must not restore an actionable obsolete preview.

### Task 1: Matching and staged resolution

**Files:** Create inspection_app/import_identity.py, tests/test_import_resolution.py; modify inspection_app/imports.py.
**Interfaces:** match_legacy(store, data, decisions) -> errors and structured metadata; resolve_import(store, token, resolutions) -> new preview.

- [x] Write failing tests for explicit separate/skip/match and all validation failures.
- [x] Extract existing matching logic, add source-row fingerprints, conflict metadata and explicit decision validation; preserve compatibility wrapper used by existing tests.
- [x] Stage pristine tables, rebuild resolved previews, and persist decisions atomically on apply.
- [x] Verify resolution tests and existing import tests.

### Task 2: HTTP and export persistence

**Files:** Modify inspection_app/server.py, inspection_app/exports.py, tests/test_http_inprocess.py and tests/test_import_resolution.py.
**Interfaces:** POST /api/import/resolve accepts token/resolutions JSON. Optional Import Decisions export/import stores row_key/source_sheet/source_row/action/asset_id.

- [x] Write failing HTTP and export round-trip tests.
- [x] Add route, optional-sheet support and validation; preserve old seven-table workbook support.
- [x] Verify saved-choice reuse, stale/changed rows, backups and partial import restrictions.

### Task 3: Actionable conflict interface

**Files:** Modify static/app.js, static/style.css, tests/frontend.test.cjs, README.md.
**Interfaces:** renderImportPreview(result) displays conflict cards; updateImportDecision and resolveImportPreview invalidate old apply and request an updated preview.

- [x] Add failing browser-logic tests for choices, empty decisions, preserved editable state and stale responses.
- [x] Implement conflict cards, source/existing comparisons, Update preview, remembered-decision notice and clear import instructions.
- [x] Run full Python/JavaScript suites and browser workflow against disposable data.
- [x] Request fresh review and fix material findings with regression tests.

## Ledger

Ruling: Implement the user's explicitly requested in-app resolution as an extension of the authorized import feature, in the active checkout. No additional approval or integration action is needed. Do not commit mixed pre-existing edits.

## Completion evidence

- Task 1 complete: structured conflicts show original rows and possible existing matches; explicit separate/skip/match and reset-to-review actions rebuild a staged preview without database writes. Row fingerprints include source contents and position; changed/moved rows do not inherit stale decisions.
- Task 2 complete: HTTP resolve route rejects invalid/stale/forged decisions; final application persists choices atomically with the import. Optional Import Decisions export/re-import preserves separate and skipped choices, including after a reference-only partial import.
- Task 3 complete: browser verified eight actionable rows from the actual original workbook, selected separate/skip choices, updated the preview to 1,065 assets / 1,322 inspections, and observed Import becoming available. These were disposable test choices, never applied to the user's database or source file.
- Actual-workbook server verification: all eight rows kept separate in an empty temporary register imported 1,066 assets / 1,324 inspections; re-import produced zero additions and 1,066 updates with eight remembered choices. Explicitly selecting the corresponding existing cleaned records also yielded zero additions and 1,066 updates, with successful repeat import.
- Independent review found that saved match targets needed current-candidate validation. Fixed for both remembered match and separate choices; regression tests reject unrelated targets even within the same source tab/family. Incompatible saved choices return to review.
- Python: bundled macOS runtime full suite passed 78 tests with loopback access, no skips. Existing SQLite resource warnings remain. JavaScript: full suite passed 50 tests. Syntax checks and git diff --check pass. Native Windows execution remains unverified.
- Added import-state reset after apply/restore/clear so late resolution responses cannot revive an obsolete preview; regression test confirms file and pending decisions clear when the register is cleared.
- No commits, pushes, integration actions, changes to operational data, or Excel source edits were performed. Browser screenshot capture became unavailable after the user's continue message; the actionable dropdowns and successful updated preview had already been verified in the native browser.

### Follow-up: browser script loading

The user reported `Can't find variable: renderImportPreview`. Read-only checks established that the running app had started at 07:39, before its new static route existed: it served the updated HTML and app.js but returned 404 for import-review.js. Moved the review helpers into app.js and removed the separate script dependency. Added a clear restart message for incompatible old preview responses, an actual full-main-script execution regression test, and HTTP dependency checks. Full verification passed 79 Python tests and 52 JavaScript tests. Gracefully restarted the confirmed outdated app process with the bundled runtime and its existing data; this discards unfinished previews but preserves saved records.

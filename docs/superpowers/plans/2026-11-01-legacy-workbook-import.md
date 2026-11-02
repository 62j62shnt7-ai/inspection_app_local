# Original workbook import implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Import the original inspection workbook with user-selected tabs and reviewed changes.

**Architecture:** An explicit layout adapter produces the existing seven import tables. A workbook-inspection endpoint supplies tab choices; preview accepts the same uploaded bytes and chosen tabs. Existing staged application remains the single database write path.

**Tech Stack:** Python, openpyxl, SQLite, native browser JavaScript.

**Spec:** docs/superpowers/specs/2026-11-01-legacy-workbook-import-design.md

## Global constraints

- Preserve unrelated working-tree changes and operational data; use temporary databases for verification.
- No fuzzy automatic matching or invented inspection months.
- Excluded tabs contribute no incoming data; partial original imports permit merge only.
- Preserve cleaned-format import/export compatibility and current backup/stale-preview protections.

## Review focus

- Duplicate and conflicting identities must block overwrite, including moved rows.
- Section rows and merged headings must not become phantom assets.
- Formula-only dates and unknown statuses remain reviewable evidence.
- Late asynchronous upload responses must not restore an obsolete preview.
- Reference-only selection must not permit deleting the asset register.

### Task 1: Original layout adapter

**Files:** Create inspection_app/legacy.py, inspection_app/legacy_layouts.json, tests/test_legacy_import.py.
**Interfaces:** inspect_workbook(path) returns format and sheet roles; read_legacy(path, selected_sheets) returns seven-table data and preview metadata.

- [x] Write synthetic workbook tests for tab discovery, exclusion, headers, sections, dates, comments, and formula preservation; run and observe failures.
- [x] Implement fixed mappings from verified original/cleaned metadata, section classification, conservative date/status conversion, and source evidence.
- [x] Run adapter tests and compare all ten source sheets against cleaned asset rows and representative fields.

### Task 2: Staged import and HTTP selection

**Files:** Modify inspection_app/imports.py, inspection_app/server.py; extend tests/test_legacy_import.py and tests/test_http_inprocess.py.
**Interfaces:** preview_import(store, path, selected_sheets=None) auto-detects format. POST /api/import/inspect accepts workbook bytes. POST /api/import/preview accepts workbook bytes with an optional JSON X-Import-Sheets header.

- [x] Write failing tests for identity reuse after row movement, duplicates, collision-safe additions, partial replace rejection, and evidence round-trip.
- [x] Implement identity resolution against existing source/family identities, selection-bound previews, scoped reference replacement, and routes.
- [x] Run import/HTTP tests; verify backup, merge, blocked apply, and exported re-import.

### Task 3: Tab-selection interface and completion

**Files:** Modify static/app.js, static/index.html, static/style.css, tests/frontend.test.cjs, README.md.
**Interfaces:** Upload discovery renders Include checkboxes and resets preview; preview submits current selected names and ignores stale responses.

- [x] Add failing browser-logic tests for selection invalidation, empty selection, replace restriction, and stale responses.
- [x] Implement accessible sheet list, bulk selection, included/excluded counts, warnings and per-sheet preview summaries.
- [x] Run full Python and JavaScript suites, syntax/diff checks, and manual original-workbook preview/import/export verification in temporary storage.
- [x] Request a fresh review, address material findings with regression tests, document limitations and verification.

## Execution ledger

Ruling: Execute in the current checkout to preserve the user's active uncommitted implementation; do not create a checkout that omits it, stage unrelated edits, or commit mixed existing changes. The user explicitly requested implementation here. Native execution is the default under the session's no-proactive-delegation rule; use a reviewer only as required by the execution skill.

### Completion evidence

- Task 1 complete: explicit mappings extract the same 1,066 source asset rows and 1,324 inspections as the cleaned draft. Synthetic adapter/import tests were observed failing before implementation and now pass.
- Task 2 complete: selected-tab HTTP discovery/preview and partial replace rejection tested; original import excluding Vessels & TKs and FLs yields 617 assets, re-import yields zero additions and 617 updates, export/re-import preserves 617 assets and 8,410 source cells. Import into the existing cleaned register yields zero additions, 617 updates and 449 retained records.
- Task 3 complete: browser verified all 24 checkboxes, excluded-tab counts, disabled replace, preview and import into a disposable database. JavaScript suite passes 45 tests; bundled macOS Python suite passes 61 tests with loopback enabled, no skipped tests. Existing SQLite resource warnings remain. Native Windows execution remains unverified.
- Fresh independent review identified description fallback despite changed strong identifiers; fixed with regression tests. Review also identified possible merged vessel section headings becoming assets; reproduced and fixed with a regression test.
- Final review resolution: matching identifiers with a conflicting second identifier now block; chronological date inconsistencies remain original values but get review flags.
- Ruling: Match EPF records from the supplied cleaned draft's known erroneous MOP location only with a unique exact description and report number. This avoids duplicating all 25 EPF records while preserving their permanent IDs; ambiguous cases still block. A wrong compatibility match could replace the wrong EPF record, so a regression test pins both identity requirements and preview remains mandatory.
- Ruling: Shared descriptions/tags do not alone establish duplication. Complete identity includes original report sequence and context, so distinct OP report numbers remain separate. Indistinguishable identities block. Misinterpreting source report numbers could retain a duplicate record; no fuzzy or row-only overwrite is used.
- No commits or integration operations were performed because feature changes share files with pre-existing uncommitted work.

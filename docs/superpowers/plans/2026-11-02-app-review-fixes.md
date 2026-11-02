# App Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the nine confirmed findings without losing evidence, weakening reset protection or changing owner-approved eligibility rules.

**Architecture:** Keep the Python/SQLite app and vanilla browser interface. Repair lifecycle boundaries in place: generated-review ownership, async preview/save state, cleanup configuration, staged restore validation and evidence-preserving exports. Add failing behavioral regressions before each fix.

**Tech Stack:** Python standard library, SQLite, openpyxl, vanilla JavaScript, unittest and Node test runner.

**Spec:** [Full review and reproduction requirements](../../app-review-2026-11-02.md), reviewed commit `b9ccfa1fff084226a71ec58fc4108eaf80a9fea7`, and [data contract](../../data-contract.md). This plan is proposed; no application fixes have been implemented.

## Global Constraints

- Preserve existing uncommitted work. Do not reset, clean, or overwrite the user's files.
- Treat `data/`, backups, recovery packages and source workbooks as user data. Never alter or delete them for development or tests.
- Preserve permanent identities, source evidence, audit history, backups, and export/import compatibility.
- Snapshot eligibility uses the owner-approved automatic quality criteria in `docs/data-contract.md` (rules version 2).
- Importing or editing is not verification. Manual verification remains optional; automatic eligibility must not write verification evidence.
- Maintain local-only operation and macOS/Windows compatibility. Native Windows and owner acceptance remain unverified unless tested.
- Never rewrite saved backup/package inputs; normalize disposable copies only.
- Run commands from the repo root and use disposable synthetic data for every live check.

## Review Focus

- New independent concerns after generated warnings: unrelated saves retain the concern and snapshot exclusion. Task 1.
- Deferred/out-of-order responses after intent changes: only the currently reviewed operation/editor receives completion. Tasks 5–6.
- File lock followed by backup-folder change: pending cleanup cannot strand startup or authorize arbitrary paths. Task 2.
- Recovery over corrupt evidence/legacy schema: retain pre-restore bytes, support valid inputs and roll back failures. Task 3.
- Evidence linked to deleted/retired/no IDs: exports remain importable without losing evidence or recreating assets. Task 4.

## Task 1: Preserve independent inspection concerns — R1, first priority

**Files:** Modify `inspection_app/validation.py`; touch `quality.py`/`imports.py` only if incoming-summary ownership requires it. Test `tests/test_review_resolution.py`, `tests/test_quality_criteria.py`. Update the contract/review status after verification.

**Interfaces:** Preserve `reconcile_import_reviews(asset) -> asset`, `Store.save_asset(asset_id, payload, expected_version)` and `assess_readiness(store)`. Generated date warnings still resolve when corrected; independent concerns remain until explicitly addressed.

- [ ] Add `test_independent_imported_concern_survives_unrelated_save`: resolve a generated date warning, export, set inspection status/reason to `Review` / `Confirm scope against drawing D1`, reimport, rename only. Assert reason/status retained, readiness and published snapshot exclude the ID, raw evidence remains, and no manual verification is created.
- [ ] Add cases with an independent concern alongside a still-open generated item, and repeated corrections/saves with only generated items. Assert automatic date resolution continues to work.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_review_resolution.py'`; confirm the new concern-retention test fails for R1 before implementation.
- [ ] Replace boolean-only ownership with content-sensitive ownership. Only rewrite a summary proven to belong to the generated date items; preserve independent text in marker-only legacy records rather than guessing. New internal metadata must be optional for older DBs/exports.
- [ ] Run review-resolution, quality-criteria and year-only suites using their individual discovery patterns; repeat the complete import/save/readiness case. All must pass.
- [ ] Record the regression/fixing commit under R1, update contract caveats and commit this task's code/tests/docs.

## Task 2: Finish cleanup before changing its authorized folder — R4

**Files:** Modify `inspection_app/recovery.py` and, if needed, `inspection_app/cleanup.py`. Test `tests/test_cleanup.py`, `tests/test_recovery.py`. Update backup/deletion docs.

**Interfaces:** Preserve `configure_backup_folder(store, folder)` and `recover_pending_cleanup(store)`. Folder changes stay serialized; failure leaves the prior configured folder authoritative.

- [ ] Add `test_pending_package_cleanup_finishes_before_folder_change`: delete a valid synthetic package with unlink failure injected only for `.cleanup-[32 hex]` parents; release failure; change destination; reopen Store. Assert startup succeeds, journal/receipt are gone and unrelated files remain.
- [ ] Add a continued-lock case: folder configuration returns a controlled error and leaves the old setting intact; releasing the lock and retrying succeeds. Retain an unsafe-journal-path rejection test.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_cleanup.py'`; confirm the new lifecycle fails before the fix.
- [ ] Drain pending cleanup under the Store lock before persisting a destination change. Surface a controlled retryable configuration error if cleanup cannot finish. Do not loosen journal root checks.
- [ ] Run cleanup, recovery and folder-picker suites individually; reopen the disposable Store after the complete sequence.
- [ ] Update R4 with evidence and commit this repair/tests/docs.

## Task 3: Restore supported recovery inputs safely — R5 and R6

**Files:** Modify `inspection_app/recovery.py`, `inspection_app/backups.py`; share legacy schema initialization from `inspection_app/store.py` if needed. Test `tests/test_recovery.py`, `tests/test_backup.py`, `tests/test_migrations.py`, `tests/test_http_inprocess.py`.

**Interfaces:** Preserve `restore_master_package(store, path)`, `restore_saved_backup(store, filename)` and `validate_database(store, path)`. Keep local settings/data epoch, non-reused edit versions, future-schema rejection and byte-for-byte input preservation.

- [ ] Add `test_recovery_repairs_corrupt_existing_archive`: import synthetic workbook, export good package, corrupt canonical live archive. Assert verified originals restored, damaged bytes preserved separately, assets correct and safety protection returned.
- [ ] Inject failure after archive replacement starts but before DB restore completes. Assert pre-restore DB/archive bytes remain recoverable, rollback/retry work, and existing valid protection is not replaced by partial output. Retain healthy-archive and invalid-package rejection cases.
- [ ] Add `test_generated_legacy_migration_backup_restores`: create the supported four-column assets table, initialize Store, restore its listed migration backup through storage and saved-backup HTTP routes. Assert identity/content restored, input hash unchanged, old tokens stale and local epoch/settings retained.
- [ ] Run recovery/backup tests and confirm failures show R5's checksum rejection and R6's missing `details` column before implementation.
- [ ] Normalize supported legacy schemas on a disposable copy before semantic validation. Share Store's supported initialization; do not accept arbitrary missing columns or rewrite the backup.
- [ ] Preflight the package and protect current DB/damaged archive bytes before replacement. Install only verified package bytes; track replaced and newly installed files for rollback. Keep symlink/path/checksum checks intact.
- [ ] Run backup, compressed-backup, recovery, migration and in-process HTTP suites. Repeat valid round trips and corrupt/legacy failure paths with disposable inputs.
- [ ] Update R5/R6 and recovery/acceptance docs, then commit this task.

## Task 4: Preserve valid workbook references and unassigned reviews — R7 and R8

**Files:** Modify `inspection_app/exports.py`; change cleanup only if historical provenance needs explicit retention. Test `tests/test_roundtrip.py`, `tests/test_cleanup.py`, `tests/test_consolidation.py`.

**Interfaces:** Preserve `export_workbook(store, path) -> path` and all existing linked-sheet columns. Append an optional `historical_asset_id` Source Cells column for the original ID when `asset_id` must be remapped; older workbooks without it remain supported. Do not emit deleted IDs as live foreign keys, recreate removed assets or alter original source/review content.

- [ ] Add `test_selected_deletion_export_reimports_with_unassigned_evidence`: import two synthetic assets with source cells, delete one through cleanup, export/reimport into a fresh Store. Assert zero preview errors, only the survivor exists, `asset_id` is blank and `historical_asset_id` retains the removed ID. Compare every other source field exactly, including Excel type, row role, coordinates, original text and original annotation/comment/formula-cache content.
- [ ] Add a retired/consolidated-ID case mapping `asset_id` to the survivor and retaining the retired ID in `historical_asset_id`, without recreating retired assets. Test repeated export/import preserves this optional field, and older workbooks without it still import.
- [ ] Add `test_unassigned_review_items_survive_roundtrip`: compare exact review ID, status, original value, reason and coordinates across import/export/fresh import. Include multiline/formula-like text and repeated cycles without duplicate rows.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_roundtrip.py'`; confirm the reported reference/loss cases fail before implementation.
- [ ] Build live-ID/alias lookup from the export snapshot, normalize absent/retired Source Cells references as above, and merge/deduplicate retained Review Items. Add the optional history column to export headers; retain it on import/export without overwriting any existing original_annotation. Keep literal-string/long-value behavior.
- [ ] Run roundtrip, cleanup, consolidation, import and import-resolution suites individually; every generated output in the new cases must import into a fresh Store.
- [ ] Update R7/R8, interchange caveats and acceptance docs, then commit.

## Task 5: Allow only one active editor save — R3

**Files:** Modify `static/app.js`; touch `static/index.html` only if a save-control identifier is needed. Test `tests/frontend.test.cjs`.

**Interfaces:** Preserve create/update payloads. Acquire the guard synchronously, and bind completion to the initiating editor instance and draft rather than mutable global `editing`.

- [ ] Add a deferred-request test submitting a new asset twice. Assert one POST/creation, with submission disabled until completion.
- [ ] Add failure/retry and editor-switch tests. Failure retains the draft/releases the guard; old completion cannot close another editor or remove its draft.
- [ ] Run `node --test tests/frontend.test.cjs`; confirm duplicate submission fails before implementation.
- [ ] Add the guard, pending-control state and try/finally release with captured editor identity/generation.
- [ ] Rerun frontend tests; check repeated Save clicks and recoverable save failure in a disposable browser.
- [ ] Update R3 and commit the repair/tests/docs.

## Task 6: Bind previews to current controls and dialog — R2

**Files:** Modify `static/quality.js`; test `tests/quality.test.cjs`.

**Interfaces:** Preserve bulk/consolidation payloads and backend revision guards. Only the latest response for current scope/controls/dialog may install an applicable preview.

- [ ] Add deferred bulk cases: Plant request then Field selection, operation/value changes, close/reopen with new scope and reversed preview responses. Assert no stale response enables Apply or supplies its token.
- [ ] Add consolidation survivor/scope/dialog equivalents; displayed keep/retire IDs must match the applied preview.
- [ ] Run `node --test tests/quality.test.cjs`; confirm Plant→Field fails before implementation.
- [ ] Add generation/signature ownership checks and dialog invalidation. Show field/operation explicitly. Apply must use a matching current preview; keep backend guards.
- [ ] Run all Node tests and check affected preview/apply flows in a disposable browser; capture the exact operation reviewed.
- [ ] Update R2 and commit the repair/tests/docs.

## Task 7: Send reset epochs with yearly binary exports — R9

**Files:** Modify `static/app.js`; test `tests/frontend.test.cjs`, `tests/test_http_inprocess.py`.

**Interfaces:** Preserve yearly XLSX payload/response format and token/epoch semantics. Share header construction with `api(path, options)` without parsing successful binary output as JSON.

- [ ] Add a frontend test capturing yearly fetch after loading a rotated epoch; assert token/epoch match other POSTs.
- [ ] Add reset→current epoch→yearly HTTP export returning 200 XLSX, with old-epoch requests still rejected.
- [ ] Run frontend/in-process HTTP suites; confirm the actual frontend-header test fails first. A correctly headed backend-only request already passes and cannot prove this fix alone.
- [ ] Use the shared request-header builder for binary export; audit other raw POST callers for the omission.
- [ ] Run full Python/Node suites and all application/tool syntax checks. In a disposable browser, reset/reload/export, inspect the downloaded workbook and verify stale writes remain rejected.
- [ ] Update R9, main report, README, task state, contract, acceptance and Windows status with actual results. Keep untested gates open. Commit the repair and final evidence.

## Completion criteria

- [ ] R1–R9 each link a passing regression and verified fixing commit; code inspection alone does not close a finding.
- [ ] Full `python3 -m unittest discover -s tests` and `node --test tests/*.test.cjs` pass; report environment skips honestly.
- [ ] Relevant round trips/injected failures pass without operational inputs; original saved inputs remain unchanged.
- [ ] Affected browser checks include download inspection, stale controls, duplicate submission and recovery feedback.
- [ ] Native macOS/Windows, owner and accessibility acceptance are completed or remain explicit release gates. Commits do not imply merge/deployment.

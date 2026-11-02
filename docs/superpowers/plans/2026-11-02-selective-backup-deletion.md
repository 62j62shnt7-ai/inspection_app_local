# Selective Saved-Backup Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator select and delete specific app-managed local database backups from the Saved backups list.

**Architecture:** Add a validated service function in `inspection_app/backups.py` and an authenticated POST route in `inspection_app/server.py`. Extend the existing Saved backups UI in `static/index.html` and `static/app.js` with per-file selection, select all, selected count, confirmation, and result feedback.

**Tech Stack:** Python standard library, SQLite-backed local app, existing HTTP API, browser JavaScript, Node test runner, and Python unittest.

**Spec:** `docs/superpowers/specs/2026-11-02-selective-backup-deletion-design.md`

## Global Constraints

- Restrict deletion to filenames matching the app's generated `inspection-YYYYMMDD-HHMMSS-<8 lowercase hex>.db` format in `backups/`.
- Reject traversal, symlinks, and unrelated files.
- Do not delete portable recovery packages, trusted snapshots, source archives, or the active database.
- Do not automatically delete old backups or change the backup retention policy.
- Do not create a new backup as part of clearing backups.
- If deletion removes the current automatic local backup, invalidate its `local_success`, `local_path`, `local_at`, and `day` metadata; do not clear independent-copy metadata.

## Review Focus

- Empty selection: delete action stays disabled and API rejects empty filenames (UI and service tests).
- Duplicate or stale names: reject the whole request before deleting anything (service tests).
- Traversal and absolute paths: no path outside managed backup directory is ever removed (service and HTTP tests).
- Symlink or backup-like unrelated file: not listed and not deletable unless its filename matches the exact app-generated format (service tests).
- Partial filesystem deletion failure: return deleted names and per-file failures so UI can report actual results (service and UI tests).

---

### Task 1: Validated backup deletion service and route

**Files:**
- Modify: `inspection_app/backups.py`
- Modify: `inspection_app/recovery.py`
- Modify: `inspection_app/server.py`
- Test: `tests/test_backup.py`
- Test: `tests/test_recovery.py`
- Test: `tests/test_http_inprocess.py`

**Interfaces:**
- Produces `delete_saved_backups(store, filenames) -> {'deleted': list[str], 'failed': list[{'filename': str, 'error': str}]}`.
- `filenames` must be a nonempty list of distinct names currently returned by `list_backups(store)`; validation happens before deletion starts.
- Produces authenticated `POST /api/backups/delete` accepting `{'filenames': list[str]}` and returning the deletion result.

- [x] **Step 1: Write failing service tests** for deleting selected backups while retaining unselected ones; rejecting empty, duplicate, stale, traversal, symlink, and backup-like unrelated files without deleting anything; reporting a simulated unlink failure; and invalidating the current local-backup daily guard when that exact backup is deleted.
- [x] **Step 2: Run `python3 -m unittest tests.test_backup` and confirm the new tests fail** because selective deletion is not implemented.
- [x] **Step 3: Implement `delete_saved_backups`** with exact app-generated filename recognition, managed-list membership validation, resolved-path containment, regular non-symlink file checks, per-file deletion results, and current local-backup metadata invalidation through `invalidate_deleted_local_backup` in `inspection_app/recovery.py`.
- [x] **Step 4: Write a failing authenticated HTTP test** covering valid deletion, missing token rejection, and traversal rejection.
- [x] **Step 5: Run `python3 -m unittest discover -s tests -p 'test_http_inprocess.py'` and confirm the new route tests fail** because the endpoint is missing. Discovery adds the test directory to the import path for its existing helper modules.
- [x] **Step 6: Add authenticated `POST /api/backups/delete`** using the service and existing mutation handling.
- [x] **Step 7: Run `python3 -m unittest discover -s tests -p 'test_backup.py'` and `python3 -m unittest discover -s tests -p 'test_http_inprocess.py'`; confirm both pass.**

### Task 2: Selectable deletion controls in Saved backups

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`
- Test: `tests/frontend.test.cjs`

**Interfaces:**
- Consumes `POST /api/backups/delete` with selected filenames.
- Each row exposes a labeled checkbox; select-all affects the current list; selected count is visible; delete stays disabled with no selected backups.
- Confirmation lists selected filenames; cancel makes no request; confirmed delete reloads the list and reports deleted and failed counts.

- [x] **Step 1: Write failing UI tests** for visible per-backup selection, select-all and selected count, disabled empty action, canceled confirmation, confirmed deletion of selected files only with list and backup-status refresh, and partial-result feedback.
- [x] **Step 2: Run `node --test tests/frontend.test.cjs` and confirm the new tests fail** because the selection UI and handler are missing.
- [x] **Step 3: Implement selection state and controls** in the existing Data & backups view; use accessible checkbox labels and an explicit confirmation naming selected files.
- [x] **Step 4: Run `node --test tests/frontend.test.cjs` and confirm all tests pass.**
- [x] **Step 5: Run `node --test tests/*.test.cjs`, `python3 -m unittest discover -s tests`, JavaScript syntax checks, and `git diff --check`.**
- [x] **Step 6: Update the README** with the selectable deletion behavior and its scope.

# Reviewed Batch Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner explicitly verify required fields for a selected group of assets in one evidence-backed operation after reviewing the exact scope.

**Architecture:** Add preview/apply operations to `inspection_app.quality` and expose them through the existing authenticated mutation API. Reuse the register's cross-page selection and audit/verification model; a stale preview fails, field fingerprints remain per asset, and open blockers still exclude affected assets.

**Tech Stack:** Python standard library, SQLite, existing local HTTP API, browser JavaScript, Node test runner and Python unittest.

**Spec:** `docs/superpowers/specs/2026-11-02-batch-verification-design.md`

## Global Constraints

- Import alone never creates verification records.
- Batch verification requires a nonempty evidence reference/rationale and an explicit final action.
- Preview every selected asset, each required field's current value, and blockers; do not silently filter selected records.
- Preserve fingerprinted field-level verification and invalidate only changed fields.
- Do not resolve blocking findings or identity conflicts through batch verification.
- Use one automatic backup and one atomic database transaction per batch.

## Review Focus

- Empty, oversized, duplicate, or unknown asset selections: reject clearly; pin in backend tests.
- Asset edits after preview: reject the stale operation; pin in backend tests.
- Assets with blockers: record reviewed fields but keep them ineligible; pin in backend tests.
- Heterogeneous inspection fields: show and verify the exact per-asset required set; pin in preview tests.
- Multi-page register selections: include every selected ID independent of filters/page; pin in frontend tests.

---

### Task 1: Atomic preview and apply service

**Files:**
- Modify: `inspection_app/quality.py`
- Test: `tests/test_quality.py`

**Interfaces:**
- Produce `preview_bulk_verification(store, asset_ids) -> dict` with `preview_id`, `revision`, `asset_count`, and every selected asset's `id`, `name`, `source`, `version`, required field names with current values, and open blocker messages.
- Produce `apply_bulk_verification(store, preview_id, revision, evidence) -> dict` with `verified_asset_count`, `verified_field_count`, `still_excluded_count`, and `revision`.

- [x] Write failing tests for exact scope/per-asset required-field preview, empty/unknown selection rejection, successful field-fingerprint and audit creation, missing evidence rejection, stale master refusal, and blockers remaining open/excluded.
- [x] Run `python3 -m unittest discover -s tests -p test_quality.py` and confirm the new tests fail because the service is missing.
- [x] Implement preview storage and transactional apply in `inspection_app/quality.py`. Create one backup before apply; recheck preview revision and every selected asset version; write the existing field-verification records and audit events per asset; do not modify issue states.
- [x] Run `python3 -m unittest discover -s tests -p test_quality.py` and confirm all tests pass.

### Task 2: Authenticated API routes

**Files:**
- Modify: `inspection_app/server.py`
- Test: `tests/test_http_inprocess.py`

**Interfaces:**
- `POST /api/verification/bulk/preview` accepts `{"asset_ids": [...]}` and returns the service preview.
- `POST /api/verification/bulk/apply` accepts `{"preview_id": "...", "revision": 1, "evidence": "..."}` and returns the service result.

- [x] Add failing in-process API tests for both successful routes, rejected missing evidence, and mutation-token enforcement.
- [x] Run the focused HTTP tests and confirm they fail because the routes are missing.
- [x] Add the two routes to `inspection_app/server.py` using the existing token and mutation lock behavior.
- [x] Run `python3 -m unittest discover -s tests -p test_http_inprocess.py` and confirm all tests pass.

### Task 3: Register preview and explicit confirmation UI

**Files:**
- Modify: `static/index.html`, `static/app.js`, `static/quality.js`, `static/style.css`
- Test: `tests/frontend.test.cjs`, `tests/quality.test.cjs`

**Interfaces:**
- Add a **Verify selected** action in the selection bar.
- Add a dialog that lists every selected asset, source sheet/row, required fields, and blocker count; require evidence text and a confirmation checkbox before apply.
- On success, show verified asset/field counts and still-excluded count, clear the selection, and refresh the register/quality views.

- [x] Add failing frontend tests that the action uses all IDs in `selectedAssets`, displays per-asset required fields, current values and blockers from the preview, and cannot apply without explicit confirmation/evidence.
- [x] Run `node --test tests/frontend.test.cjs tests/quality.test.cjs` and confirm the new tests fail because the action/dialog do not exist.
- [x] Implement the selection-bar action, preview rendering, evidence/confirmation guard, apply request and result feedback. Use text nodes for imported values.
- [x] Run `node --test tests/frontend.test.cjs tests/quality.test.cjs` and confirm all tests pass.
- [x] Run `node --test tests/*.test.cjs`, `python3 -m unittest discover -s tests`, JavaScript syntax checks, and `git diff --check`.
- [x] Update README usage notes to explain reviewed group verification and its limits.

# Reliable master database candidate — 2 November 2026

Implementation remains a testing candidate on `codex/reliable-master-database`. The working checkout already contained substantial uncommitted import and platform work; it has been preserved, and no operational database was migrated during development.

## Implemented candidate

- Existing original layouts, header validation, tab selection, permanent IDs and optional Import Decisions remain supported. New context conflicts require review. The established EPF/MOP compatibility fallback is preserved.
- Versioned migrations with pre-upgrade backups, non-reusable edit tokens and transactional correction events cover manual writes, imports, reconciliation, clear, bulk corrections and consolidation. Restore refreshes tokens.
- Shared calendar parsing, structural validation, reproducible engineering findings, required applicability/completeness checks, review-by warnings and missing formula-cache warnings.
- Durable import previews, exact source archives, checksums, row accounting, explicit unclassified-row acknowledgement, restart/resume, previous-source/current/incoming comparison, protection of verified corrections and populated values against incoming blanks, retained linked rows and explicit consolidation aliases.
- Persistent issues, evidence-backed resolutions, field-level verification/history, related-decision invalidation, readiness assessment and immutable named snapshots with a complete exclusion list. Accepted source review decisions drive schedule summaries without rewriting raw source evidence.
- Bulk normalization/set/clear previews, explicit selection across pages, atomic application and guarded compensating reverts.
- Full recovery packages containing database and source archives, semantic metadata validation, checksum validation, complete archive inventories, machine-local backup-status reset on restore and separate local/copy failure states. Default copy destination is `data/recovery-copies/`; it can be changed in the UI.
- Guided import stages, empty-state guidance, active-filter controls, readable verification labels, optional-field disclosure, month pickers, controlled applicability/status inputs, recoverable browser drafts, discard warnings, light/dark/system themes, focus indicators and narrow-screen layout rules.
- Register/quality pagination and one-connection summary reads; detailed source/technical payloads are omitted from register responses. Yearly exports carry scope and omission reasons. Long Excel values use exact continuation/reassembly.

## Evidence

Run `python3 -m unittest discover -s tests` and `node --test tests/*.test.cjs`. Python uses disposable databases. The ordinary sandbox prevents one listening-socket test; it is also run separately with localhost binding permitted. Existing unclosed SQLite warnings were traced to test-owned connections and corrected.

`tools/benchmark_master.py` creates a disposable 10,000-asset database with inspections, notes, technical rows and 200,000 source-cell rows. Timings are local measurements, not a guarantee for every machine. The measured database was about 78 MB. A later regression from calculating the date per record was profiled and removed. The subsequent run measured register page/filter queries at 0.183/0.190 seconds, editor load below the displayed 0.001-second precision, and the quality query at 0.583 seconds cold and 0.575 seconds warm on macOS arm64 / Python 3.14.6. Rerun on the target computer for its results.

`tools/profile_workbook.py` profiles a source without modifying it, imports into a temporary database, exports a full recovery package, restores into another clean directory and compares asset data while ignoring refreshed edit tokens. The available cleaned draft and its SHA-256/profile are recorded in `cleaned-draft-profile-2026-11-02.json`. This is a preliminary compatibility check, not owner sign-off on the original workbook or engineering values.

The browser verification used only synthetic data. It demonstrated the distinction between saved and explicitly verified fields and showed the asset becoming snapshot-eligible after the required checks. It does not establish complete WCAG conformance.

An independent reviewer reproduced six lifecycle defects; regression tests cover their corrections. That reviewer reached its usage limit before delivering a final complete report. Subsequent changes received author review and automated verification, not a completed independent release sign-off.

## Remaining release gates

- Select the exact intended original Master Inspection Plan and agree its expected extraction/issue inventory. Run the documented lifecycle on a disposable copy; do not infer engineering corrections from validation results.
- Observe the owner completing import, cleanup, verification, snapshot and recovery tasks without coaching; fix critical usability failures.
- Complete keyboard/screen-reader, contrast, zoom/reflow and target-size acceptance across the full application. Responsive styling and focus indicators alone do not establish WCAG 2.2 AA.
- Run the packaged candidate on native Windows and macOS launchers, including actual downloads/printing and unavailable/full/read-only backup destinations.
- Extend interruption/disk-failure testing beyond the covered atomic transactions, stale previews, checksum errors and unavailable-folder cases.
- Review the combined working change set and its pre-existing modifications before committing or integrating it. No merge, deployment or operational migration is included in this candidate.

## Rollout and rollback

Close the running app, retain the entire original `data/` folder and create a verified full recovery package before rollout. Start the candidate against a copied data directory first. Migrations create an additional database safety copy. Keep the old application and untouched data copy together for rollback; do not point an older app at an upgraded database. Choose and test an appropriate backup-copy destination before relying on it. All copies are retained until a retention policy is explicitly chosen.

## Latest verification checkpoint

### Original workbook disposable acceptance — 2 November 2026

The requested source was profiled by the app's read-only inspection and then imported through the real app API into a disposable database. Source: `Master Inspection Plan - Updated 25-10-2026.xlsx`, SHA-256 `b91eb5bbabf02b42bbf221bfff5a47e3103744e2553b86f37a6752aaf5254a97`. The original file remained unchanged. The workbook contains 24 recognized tabs, 1,066 extracted asset rows, 1,324 inspection rows, and 28 populated rows not classified as assets (26 on EPFs and 2 on GL Lines). It has 8 incoming identity conflicts in four indistinguishable pairs: Vessels & TKs rows 257–258, FLs rows 100–101, 120–121 and 180–181.

For exercising the downstream lifecycle only, the disposable run retained the 8 ambiguous rows as separate records and acknowledged the 28 unclassified rows. These were test harness choices to avoid dropping source rows; they are **not** owner decisions or engineering identity conclusions. The app imported 1,066 records and reported 2,012 open findings, including 740 source review items. Before owner field verification, 0 assets were eligible and all 1,066 were excluded from a trusted snapshot. A full recovery package restored with matching asset content, and a repeat import had no errors and reused the 8 temporary identity decisions. No engineering values were changed or inferred.

The import UI now exposes **Imported source coverage** under Data & backups for committed batches. It shows sheet names and source row numbers for unclassified rows and links to the exact archived workbook, so potential missed equipment remains reviewable after import. A browser check confirmed the 28 rows and archive link were available. The remaining owner acceptance is to review all 8 identity pairs and 28 unclassified rows, especially whether any EPF rows describe assets to add, and then explicitly resolve/verify the intended data. Until that is done, the disposable run is evidence of workflow behavior, not acceptance of the workbook's engineering content.

- Python: 138 tests ran; 137 passed and the listening-socket test was skipped by the ordinary sandbox. The same socket test then passed separately with localhost binding permitted. No remaining resource warnings appeared in those runs.
- JavaScript: all 62 tests passed.
- Python compilation, JavaScript syntax checks and `git diff --check` passed.
- Browser: synthetic field verification reached eligible status, automatic copy testing reported separate local/copy completion times, light-mode layout was visually corrected and rechecked, and saved-snapshot controls loaded. The original-workbook disposable DB showed the committed coverage panel, all 28 unclassified rows and the exact source archive download link. The header theme toggle and light/dark dashboard, data-quality and import screens were rechecked. Reviewed batch verification was exercised in the browser with disposable records; the full source/field/blocker preview displayed, and no owner verification was applied. Visual proof: `quality-candidate-light.jpg`.
- The copied cleaned-draft profile retained 1,066 assets / 1,324 inspections and found 1,103 open findings. All 1,066 records remained excluded until explicit owner verification. Full-package asset recovery matched while refreshing edit tokens, and the source hash stayed unchanged.

The candidate has not been operationally deployed or independently release-approved. The release gates above remain applicable.

### Month-entry usability increment — 2 November 2026

Inspection last/next months, condition review-by months, and the dashboard's custom through-month filter now share one combined field: type `YYYY-MM` directly or open its attached picker to choose from a 12-month grid under a year heading. There are no separate month/year inputs or day calendar. Blank values stay blank. Editor month changes continue through existing draft persistence, while dashboard filtering does not mark the editor dirty.

Verification: the focused frontend tests, all 66 JavaScript tests, all 146 Python tests (one sandbox socket test skipped), JavaScript syntax check, and `git diff --check` pass. This increment has not received an owner walkthrough or full browser/screen-reader acceptance; those remain release gates.

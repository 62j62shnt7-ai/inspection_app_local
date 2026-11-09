# Excel integration delivery

The application now provides four Excel export modes and a dedicated editable-workbook synchronization and recovery workflow. Open **Export to Excel** from the master register, or use **Data & backups → Export to Excel**.

## Implemented behavior

- Full Database Workbook: opens on a familiar filterable Master Plan, then Guide and the original asset source tabs. Each asset row keeps asset, inspection, technical, note and review fields together. Hidden identities map those cells back to separate app records for three-way sync. Source Cells and Field Map remain read-only reference tabs.
- Yearly Inspection Plan: independently selected year, actual location/family/source/equipment/inspection filters, monthly counts/charts, separate overdue and unresolved sections, optional January–December tabs, filterable registers and configured print layouts.
- Filtered Asset Register and Management Summary: explicitly marked report snapshots that cannot synchronize or recover the database.
- Three-way synchronization: original/Excel/current field comparisons, explicit Excel/app/manual conflict choices, validation, missing-row retention, stale-preview checks, permanent IDs for new records and repeated-import deduplication.
- Full editable export: background job with polled stage progress; the app lock covers only the consistent database snapshot, not cell generation or workbook writing. Temporary output is cleaned after download or expiry.
- Transactional application: safety backup, disposable candidate, validated reconciled workbook prepared before live changes, rollback on failure, post-update integrity check, exact committed audit evidence in the reconciled workbook.
- Recovery: validate a full workbook, reconstruct a temporary database, check integrity and supported relationships/counts, review the preview, explicitly confirm activation, save the current database first and reload stale browser state.

## Files created

- `inspection_app/excel_io.py`: complete editable workbook, manifests, synchronization, staging and recovery.
- `inspection_app/annual_excel.py`: annual, filtered and management report exports.
- `inspection_app/excel_style.py`: shared teal/slate palette and labeled chart defaults.
- `static/excel.js`: export, preview, conflict, reconciliation and recovery interface.
- `tests/test_excel_io.py`, `tests/test_excel_http.py`, `tests/test_annual_excel.py`, `tests/excel.test.cjs`.
- `docs/excel-workflows.md`, `docs/excel-panel.html`, this delivery report and `docs/implementation/excel-progress.md`.

## Existing files extended

- `inspection_app/server.py`: authenticated export/sync/recovery routes, large workbook uploads, reconciled downloads and the new script.
- `inspection_app/legacy.py`: prevent editable full workbooks and limited reports from entering the legacy importer.
- `inspection_app/cleanup.py`: clear Excel preview data and lineage on working-data reset.
- `static/index.html`, `static/app.js`: visible controls and professional annual export from the existing Yearly plan page.
- `README.md`: workflow entry points and guide.

Other pre-existing changed files were preserved. No commits or operational-data migrations were performed for this task.

## Verification and compatibility

All **401 Python tests** passed under the bundled macOS Python runtime, and **109 Node tests** passed. Live browser tests covered exports, conflict resolution, applying changes, downloading reconciliation, and activating recovery on disposable data. The supplied reference workbook's **1,066 assets** passed unchanged export/import preview and exact asset-row recovery equality checks.

Microsoft Excel for Mac **16.113.1** opened the corrected editable workbook and standalone annual report without repair. Focused native checks covered planning-year changes, due-month changes, detail/count/chart recalculation, new assets and linked inspections, automatic calculated-column expansion, saving, and importing the saved file. Initial native defects in table-formula notation, validation length and frozen-pane selections were reproduced, corrected, and regression-tested. Final annual reports opened cleanly with visible month labels and count axes.

Dynamic schedules target Excel 2021/Microsoft 365. Existing manual-calculation Excel sessions need Calculate Now or automatic calculation enabled. Native Windows, every desktop Excel version, physical printing, and six elapsed months of use remain unverified. Structural/formula tests alone are not a full Excel compatibility claim.

## Operating instructions and limits

The workbook now follows the original source-tab layout and keeps each asset's editable fields on one row. A disposable export and synchronization smoke check passed. Excel for Mac 16.113.1 opened a one-asset disposable workbook without repair. The source-tab table duplicated its filter at worksheet level in the first sample; removing the duplicate worksheet filter fixed the repair prompt. Full database export time and the full test suites were not rerun.

Follow [the workflow guide](../excel-workflows.md) for full export, editing/new local identities, import preview/conflicts, reconciliation, Excel recovery, and selected-year reports.

Use the reconciled workbook after every synchronization. Changed new rows from an already-imported stale workbook are blocked explicitly. Indistinguishable legacy notes/reviews without permanent IDs require distinguishing in the app and re-exporting before ambiguous offline edits can be matched. Missing workbook rows never delete records.

The full workbook retains supported source cell evidence and business history. Complete original source workbook files and machine configuration require native recovery packages. Native backup configuration is retained locally during Excel recovery.

Comparisons preserve exact database numbers when Excel only rounds beyond its 15-significant-digit precision. Subprecision numeric edits cannot be reliably represented in Excel. Worksheet protection prevents accidental editing and is not authentication. Issued baseline digests bind synchronization to its database; portable recovery checks structure and integrity and is not a cryptographic authenticity guarantee for third-party workbooks.

The decisions and their costs are recorded in [the execution ledger](excel-progress.md). No deferred review findings remain beyond the documented platform and ambiguity limits.

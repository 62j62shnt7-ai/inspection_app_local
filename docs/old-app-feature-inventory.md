# Old inspection app: feature inventory

Inventory of `../inspection_app` compared with `inspection_app_local`, based on source inspection on 2026-10-31. This describes implemented code and visible controls, not a claim that every workflow has been exercised or that engineering calculations are fit for use. No old-app fields or features are being reinstated by this inventory.

## 1. Dashboard and priorities

- Executive banner: inspection compliance for scheduled assets, unmanaged overdue backlog, approved MOC deferrals and CUI target lines.
- Summary cards include total equipment, overdue OSI/internal, due in 30/90 days, high risk, critical scope, temporary repairs and special statuses.
- Clickable overdue-aging buckets: 0–30, 31–90, 91–180 and over 180 days, plus managed/unmanaged deferral counts. Estimated placeholder dates are separated from aging buckets.
- Missing due dates worklist, with high-risk records first; clickable 5×5 RBI matrix and high-risk equipment queue.
- Audit activity, backup list with restore, overdue queue, temporary-repair expiry alerts and clickable counts by source sheet.
- **Local app:** separate OSI/internal overdue, due this month, upcoming-period, no-date and review counts, worklists and source-sheet shortcuts. Its dates are tracked by month; it has no old-app aging buckets, RBI matrix, compliance percentage, deferral metrics, audit feed, or temporary-repair dashboard.

## 2. Assets register

- Source-sheet tabs and search with token matching and some compressor/turbine/generator synonyms.
- Filters: source sheet, risk tier, overdue age, deferral state, internal/OSI/both overdue, special scheduling condition (next shutdown / waiting evaluation), overdue-only, and archived records. Grouping by pack/header, source sheet, plant, or location.
- Status, risk, RBI, CUI and scope badges; grouped rows; page size, previous/next pagination; selectable records and a floating bulk-action bar.
- Select assets for bulk inspection logs, bulk deferrals or selected-record CSV export. Separate filtered CSV export and new asset action.
- **Local app:** search, source, family, service, due/review and active/archive filters; sheet tabs, incremental show-more, filtered CSV and individual create/edit/archive. It has no selection, batch actions, old-app grouping, search synonyms, or risk/deferral filters.

## 3. Asset details, history and engineering tools

- Slide-over drawer with identity, location, design/operating envelope, OSI/internal dates, risk and deferral sections, original sheet metadata and remarks. Save, archive and restore.
- RBI risk level and matrix cell; corrosion rate and remaining life; deferral status, reference, approver, expiry, justification and mitigation.
- Inspection log: date, type, inspector, method, measured thickness, findings, action and next due date; view history and delete an entry. Saving can update last/next dates. Bulk logging supports selected assets.
- Remaining-life calculator accepts thickness readings and elapsed time, calculates corrosion rate, remaining life, a suggested interval and due date, and supports applying results to the form. It reports warnings for short intervals between readings or no measurable corrosion loss and flags thickness at/below minimum. A corrosion trend appears when suitable history exists.
- **Local app:** identity, month-based inspection details, technical details, remarks, review flags and read-only original source values in a tabbed editor. No separate inspection-history log, trend, engineering calculator, RBI or formal deferral workflow. Some old fields were deliberately excluded from the new app and should not be restored without a specific decision.

## 4. Critical turnaround and temporary repairs

- Critical turnaround table supports search and filtering by replacement status; its replacement completion status can be toggled from the table.
- Temporary-repair table supports search and active/expired/replaced filters, with area, asset/section, contractor, original and expiry dates, design life, hardness and status.
- Old backend also exposes create/update endpoints for critical assets and temporary repairs; the inspected screens primarily list/filter records and toggle critical completion. Do not assume full create/edit forms are present.
- **Local app:** no dedicated modules for either workflow.

## 5. Yearly plan

- Generate by year; filter by source and inspection scope (all, OSI or internal); include overdue carry-over with an optional earliest-year cutoff; print and export a dedicated yearly Excel workbook.
- **Local app:** select year, view dated OSI/internal inspections, open assets, print and export yearly CSV. No carry-over, scope/source selectors or dedicated yearly Excel export.

## 6. Campaign reconciliation

- Import a refined campaign workbook; compare campaign items with master assets, due dates and inspection scope.
- Display match rate, UT progress, matched/unmatched items, date variances, omitted overdue assets and progress. Filter/search by category and by all, variance, omission, completed, holding and unmatched queues; open matched assets.
- Export the reconciled schedule as CSV, clear the campaign, and sync eligible completed campaign items to the master inspection log and due dates. Backend also supports manually linking refined items and querying omissions; a matching link UI was not established in this inspection.
- **Local app:** no campaign module or synchronization.

## 7. Import, export, audit and recovery

- Old app can import an Excel workbook in clean/wipe or sync mode, import a refined campaign workbook, export CSV, clear the master database with confirmation, list backups and restore them. Backup creation is used before operations such as restore, wipe and synchronization. Audit records are available for supported changes.
- **Local app:** cleaned-workbook import with preview, permanent-ID matching and backup before apply; full-workbook export, filtered/yearly CSV, manual backup and restore with safety backup. It provides a guarded clear-database control; it has no activity audit feed. The Data page also lists and restores saved backups and offers merge or replace import modes, each with preview and a safety backup. Its workbook structure differs from the old app. The old system activity feed is not present.

## Review before reuse

- The old app computes inferred RBI categories and a matrix, and offers an interval calculator with defaults; review the inputs, assumptions and applicable engineering rules before treating its output as authoritative.
- The local app uses month precision and a different data model, while parts of the old app use day precision, placeholder/estimated dates, inspection logs and separate campaign/repair tables. Migrating behavior requires explicit mapping and validation; copying UI controls alone would be misleading.
- The old UI contains features intentionally excluded from the local app. This document is an inventory, not a proposal to turn them back on.

## Source references

- Old interface: `../inspection_app/static/index.html`, `../inspection_app/static/app.js`, `../inspection_app/static/style.css`.
- Old application/API: `../inspection_app/app.py`; workbook import and reconciliation helpers: `../inspection_app/import_excel.py`, `../inspection_app/import_refined_plan.py`.
- Local interface and API: `static/index.html`, `static/app.js`, `inspection_app/server.py`, `inspection_app/store.py`, `inspection_app/imports.py`, `inspection_app/exports.py`, `inspection_app/backups.py`.

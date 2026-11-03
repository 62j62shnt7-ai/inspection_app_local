# Task state — 2 November 2026

## Current goal and checkpoint

The requested commit-first full app review is in [app-review-2026-11-02.md](app-review-2026-11-02.md). Source/tests/docs were committed as **`b9ccfa1fff084226a71ec58fc4108eaf80a9fea7`** on `codex/reliable-master-database` before review. Three existing distribution ZIPs remain untracked and untouched; two contain the reference workbook. No operational data was used or modified for review.

Outcome: **one P1 and eight P2 findings remain open**. The [seven-task fix plan](superpowers/plans/2026-11-02-app-review-fixes.md) defines regression coverage and repair order. Review/report/documentation work is complete; application fixes have not been implemented. The current request was to review and plan repairs.

## Current owner decisions

- The master register and inspection schedule are primary, maintained by one operator on one computer.
- Snapshot eligibility uses owner-approved automatic quality criteria, **rules version 2** in [data-contract.md](data-contract.md). Manual verification is optional, distinct from Passed checks and retained as audit evidence.
- Missing location/identifiers do not themselves block inclusion. Applicable inspections need a valid next month or recorded scheduling condition; condition review-by is optional. Valid overdue work remains overdue without becoming a data-quality conflict.
- Verified corrections win over conflicting imports; populated values are protected from incoming blanks. Incoming differences remain reviewable. Only changed fields lose verification.
- Blocking issues exclude assets from snapshots while retaining register visibility. Manifests list exclusions, warnings and accepted exceptions.
- Identity ambiguity requires explicit decisions. Importing/editing is not verification and implies no engineering or regulatory certification.
- Supported original workbook layouts and app exports remain the import targets; the synthetic scale target is 10,000 assets. Optional batch verification requires a full preview of the exact selected assets and fields.
- Automatic local backups and user-chosen copy destinations remain required. Approved selective backup/data deletion uses explicit preview/confirmation; reset retains separately managed backups/recovery packages.
- Month inputs combine YYYY-MM typing/picking. The approved year-only correction chooses January while preserving the source year/evidence.

Older mandatory-verification/location requirements and the instruction never to commit the mixed tree are superseded by current policy and the explicit commit-first request.

## Implemented candidate

The checkpoint includes import/identity resolution, preserved source archives/evidence, reconciliation, quality/readiness, optional verification, snapshots, bulk corrections/consolidation, backup/recovery, compact compressed backups, year-only corrections, reviewed deletion/reset, reset epochs, folder picking, month inputs and theme/usability work. Details remain in [reliable-database-acceptance.md](reliable-database-acceptance.md). Implemented does not mean accepted or defect-free.

## Latest verification

- Full Python suite: **232 passed**, zero skipped, including the listening-socket test.
- Full Node suite: **83 passed**, zero skipped. All four browser scripts passed syntax; 25 Python application/tool files parsed successfully.
- Disposable 10,000-asset benchmark: register page/filter 0.153/0.161 seconds; quality first/warm 0.344/0.339 seconds. One local macOS/Python 3.14.6 run.
- Live synthetic browser: dashboard/quality classification, year-only preview/apply/undo, saved snapshot with two included/two excluded, backup/inventory listing and canceled reset preview.
- Targeted synthetic lifecycle reproductions confirmed nine findings despite the passing baseline. No application regression tests have been added yet; evidence/limits are in the report.

## Next work

1. R1: prevent unrelated saves from clearing newly imported independent concerns or changing snapshot eligibility.
2. R4–R8: repair cleanup destination changes, corrupt-source/legacy-backup recovery and evidence-preserving interchange.
3. R2/R3/R9: bind previews to current controls, prevent duplicate creation and send epochs on yearly export. Follow plan tasks with failing-then-passing behavioral tests.
4. Rerun full suites, round trips/failure injection and affected browser flows; record verified fixing commits before closing findings.
5. Complete owner source/identity decisions (the historical original-workbook checkpoint had eight conflicting rows in four pairs and 28 unclassified rows), uncoached workflow acceptance, full accessibility acceptance, native macOS/Windows launch/download/print/file-lock/picker checks and extended interruption/disk-failure acceptance. These remain release gates.

## Safety and scope

Preserve new uncommitted work and leave operational databases, source workbooks, backups, recovery packages and distribution ZIPs untouched. Use disposable synthetic data for development/acceptance. No operational migration, push, merge, deployment or engineering certification occurred. Later rollout must retain an independent untouched data copy and follow the acceptance document's rollout/rollback instructions.

## Repair progress — Task 1 / R1

Content-sensitive generated review ownership protects independently imported concerns. Synthetic regression covers export/reimport, rename, readiness, snapshot exclusion and absence of manual verification. Tasks 2–7 remain open.

## Repair progress — Task 2 / R4

Pending cleanup now finishes before backup-folder changes; locked cleanup leaves the old setting in place and can be retried. Tasks 3–7 remain open.

## Repair progress — Task 3 / R5–R6

Synthetic corrupt-archive recovery and generated legacy backup restore are covered through storage and HTTP, including safety-package collision and failure paths. Tasks 4–7 remain open.

## Repair progress — Task 4 / R7–R8

Deleted and consolidated source references and unassigned reviews survive synthetic workbook round trips. Tasks 5–7 remain open.

## Repair progress — Task 5 / R3

Editor saves are guarded and bound to the initiating editor; synthetic delayed-response tests and disposable browser failure/double-click checks pass. Tasks 6–7 remain open.

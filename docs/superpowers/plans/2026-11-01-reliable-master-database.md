# Reliable Master Database Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. This is a proposed implementation plan, not authorization to change operational data.

**Goal:** Convert messy inspection workbooks into a traceable, reviewed, maintainable master database without silently losing source information or overwriting verified corrections.

**Architecture:** Extend the existing local Python/SQLite application. Separate immutable source imports, staged proposals, current master records, data-quality issues, and correction events. Use one validation service and one transactional mutation service for all write paths. Keep existing permanent asset IDs and month-level dates.

**Tech Stack:** Existing Python, SQLite, openpyxl, vanilla JavaScript/CSS, Python unittest and Node tests. No cloud service or AI dependency required.

**Basis:** User's clarified intent and both reviews in this chat. All design choices below are recommendations for implementation; no new design has yet been approved.

## Global constraints

- Preserve the current data folder, permanent IDs, source provenance and compatibility with existing seven-table workbooks.
- Work against disposable copies during development and verification. Existing uncommitted changes must not be discarded.
- Keep the original source file unchanged; retain a content hash and managed archival copy for each committed import.
- Do not infer exact days, inspection completion, safe operating status or statutory compliance from month-only values.
- Internal inspection applicability is limited to recognized tanks and vessels; unclassified families require review.
- Keep source values even when canonical values cannot be interpreted. Invalid source data may enter staging, not silently become trusted master data.
- Clearing flags never proves correctness. Record reviewer label, time, reason, evidence and master revision for resolutions. A local reviewer label is attribution, not authenticated identity.
- Data correction events are distinct from inspection history. Inspection-history, RBI, CUI, deferrals, repair and turnaround modules remain outside this plan.
- Existing campaign comparison receives shared safety and validation fixes; expansion is not a prerequisite for database cleanup.
- Preserve a usable app at each milestone; migrate through versioned, repeatable migrations with pre-migration backups.

## Review focus

1. A source row moves, duplicates or disappears: preserve identity and require review when matching is uncertain (Tasks 4–5).
2. A corrected field reappears differently in a later workbook: protect the correction and show a three-way comparison (Task 5).
3. A crash occurs between file archival and database commit: incomplete imports must not become active; recovery must be explicit (Tasks 2, 4).
4. An issue is resolved while its underlying value changes: resolution becomes stale and must be reevaluated (Tasks 3, 6).
5. An export or backup is used on another computer: preserve meaning, IDs, events, issues and evidence; browser storage is not authoritative (Tasks 8–9).

## Chosen direction and alternatives

Recommended: incremental evolution of the existing app. It already has useful extraction adapters, source cells, backups, ID conflict resolution and regression tests. This limits migration risk.

A full rewrite could normalize every current detail immediately but introduces substantial migration and regression risk before improving source-data trust. Keeping Excel as the main cleaning workspace would be cheaper initially but would retain weak correction tracking and make future reimports difficult to control.

## Target workflow

Import source → inspect extraction coverage → resolve identities → review proposed changes → commit accepted data → resolve quality issues → verify readiness → publish a named master snapshot → maintain through controlled updates.

Import acceptance and master readiness are separate. An uncertain record may be retained in the database with visible open issues. A published scope must contain no unresolved blocking issue. Nonblocking exceptions require explicit acknowledgement with rationale. Readiness is always shown against a particular revision, rule-set version and selected scope; any change invalidates affected readiness results.

## File responsibilities

Existing modules remain responsible for adapters, HTTP routing, workbook serialization and UI. Add focused modules rather than putting all new behavior in server.py or app.js:

- inspection_app/migrations.py: versioned schema upgrades and safe migration checks.
- inspection_app/validation.py: canonical field validation and reproducible quality findings.
- inspection_app/mutations.py: transaction boundaries, revision allocation and correction events.
- inspection_app/import_batches.py: source archive, staged records, extraction accounting and durable decisions.
- inspection_app/quality.py: issue lifecycle, resolution and readiness reports.
- static/quality.js: quality workbench and guided correction.
- static/import-workflow.js: staged import steps and comparisons, extracted from existing UI as touched.
- tests/test_migrations.py, test_validation.py, test_mutations.py, test_quality.py, test_import_batches.py: backend contracts.
- tests/quality.test.cjs and import-workflow.test.cjs: meaningful UI state transitions.

## Task 1 — Freeze a representative baseline and define the data contract

**Files:** README.md, docs/data-contract.md, tests/fixtures/, tests/test_roundtrip.py.
**Produces:** A field dictionary describing canonical type, allowed values, requiredness by asset family, blank/unknown/not-applicable distinctions, precision and provenance. A synthetic messy-data fixture with an expected issue inventory.

- [ ] Document existing fields and original layout mappings. Identify business-critical fields separately from optional enrichment; use rules only supported by current domain requirements.
- [ ] Define canonical applicability, record status and issue states; preserve raw service text alongside proposed standardized status.
- [ ] Build fixtures for duplicate tags, reused package IDs, unnamed assets, shifted columns, dates stored as text, invalid dates, notes, formulas with/without caches and unsupported sheets.
- [ ] Capture a semantic baseline of IDs, records, linked rows and source evidence from a disposable copy. Do not commit operational source data.
- [ ] Run `python3 -m unittest discover -s tests` and `node --test tests/*.test.cjs`; record failures, skips and warnings as the starting baseline.

**Acceptance:** Every existing supported field has a preservation rule; fixtures distinguish genuine duplicates from legitimate similar assets. Missing business rules remain explicitly unresolved rather than invented.

## Task 2 — Versioned storage and a single safe write path

**Files:** migrations.py, mutations.py, store.py, imports.py, reconciliation.py, backups.py, server.py; tests/test_migrations.py, test_mutations.py, test_backup.py.
**Interfaces:** `migrate_database(store) -> None`; `mutate_master(store, changes, expected_revision, actor, reason, origin) -> MutationResult` (revision, changed IDs, event IDs). Every successful transaction allocates non-reusable edit tokens.

- [ ] Write failing regressions for stale editors after clear/reimport, replace/reimport and restore; multi-record failure must roll back all changes.
- [ ] Add schema version, persistent revision allocation and append-only correction events recording before/after values, origin, actor label, reason and UTC timestamp.
- [ ] Route manual editing, imports, reconciliation and clear through transaction helpers. Keep expected asset versions where needed; introduce database revision checks for staged batches.
- [ ] Ensure old API clients cannot bypass token checks after migration; define required request version and a reload error.
- [ ] Back up before migration and test migration twice, failure rollback and reopening the database using the current app.
- [ ] Run focused migration/mutation/backup tests, then the full suites. Commit only this task's implementation and tests.

**Acceptance:** A previously issued editor token never becomes valid again for the same ID after any removal, reimport or recovery operation. Events commit atomically with the data change.

## Task 3 — Shared validation and data profiling

**Files:** validation.py, months.py, legacy.py, store.py, imports.py, reconciliation.py; tests/test_validation.py, test_months.py, test_legacy_import.py.
**Interfaces:** `validate_record(record, rules_version) -> list[Finding]`; Finding contains rule ID, asset/field/source references, severity, message and value fingerprint. `parse_source_month(value) -> ParseResult` retains raw value, parsed month and uncertainty.

- [ ] Write failing tests for impossible days, wrong JSON shapes, invalid enums, inconsistent applicability and dates preceding last inspection.
- [ ] Share real calendar validation between adapters; preserve ambiguous formats without guessing. Missing formula caches require a visible issue.
- [ ] Apply structural rejection at master-write boundaries; represent uncertain engineering content as review findings. Chronology is a review condition, not an automatic date correction.
- [ ] Profile missing identifiers, duplicate identity candidates, unknown family/status, contradictory inspection fields, missing months and unclassified values.
- [ ] Test that all write paths produce equivalent findings and that family aliases cannot bypass internal applicability rules.
- [ ] Run validation and adapter tests and commit.

**Acceptance:** No entry path silently upgrades invalid or ambiguous source values to verified canonical values. Findings reference the actual field and source evidence.

## Task 4 — Durable import staging and extraction accounting

**Files:** import_batches.py, imports.py, legacy.py, server.py; tests/test_import_batches.py, test_legacy_import.py.
**Interfaces:** `stage_import(store, source_path, selected_sheets) -> BatchSummary`; `get_import_batch(store, batch_id) -> Batch`; batches have source hash, adapter/rule versions, base revision and lifecycle state (staged, committed, cancelled).

- [ ] Persist source file archives, extraction results, rejected/unclassified rows and review decisions outside browser memory. Use hash-derived archive names and a manifest.
- [ ] Record every populated source row as extracted asset, child/context, reference-only, explicitly skipped, excluded or unclassified. Display counts and original tab/row links.
- [ ] Show unsupported sheets, reference-only sheets and potentially missed assets prominently. No unexplained count discrepancy may be hidden behind a successful import message.
- [ ] Require acknowledgement for selected-sheet coverage exceptions; retain them in the batch manifest.
- [ ] Test restart during staging, cancellation, expired base revision, missing archive, duplicate upload and crash recovery around archive/commit boundaries.
- [ ] Run batch/import suites and commit.

**Acceptance:** Users can resume staged work after restart and explain where every included source row went. Preview never changes master records.

## Task 5 — Protect cleaned values and resolve duplicates safely

**Files:** imports.py, import_identity.py, import_batches.py, mutations.py; tests/test_import_resolution.py, test_import_batches.py.
**Interfaces:** `compare_batch(store, batch_id) -> list[FieldProposal]`; `decide_proposal(store, batch_id, proposal_id, decision, expected_revision) -> BatchSummary`; `commit_batch(store, batch_id, expected_revision, actor, reason) -> MutationResult`.

- [ ] Replace whole-record overwrite as the normal merge behavior with field-level decisions: keep current, accept incoming or enter a reviewed replacement.
- [ ] Show three-way evidence where available: last accepted source value, current master value and incoming value. Flag cleaned fields changed since the previous import. For legacy records without a baseline, show a two-way comparison requiring an explicit decision.
- [ ] Never automatically replace a nonblank master field with an incoming blank. Preserve missing incoming child rows unless explicit removal is reviewed.
- [ ] Keep exact and fuzzy matching as suggestions when ambiguous; never use package membership alone as proof of asset identity.
- [ ] Add an explicit duplicate consolidation operation: select survivor ID, review every conflict, relink child evidence, preserve retired-ID aliases and record all decisions. Distinguish this from simply updating an existing row.
- [ ] Retain separate/skip decisions, protect excluded scopes, and make batch application atomic with a backup.
- [ ] Test moved rows, changed identifiers, many-to-one collisions, partial imports, manual corrections, consolidation, and repeated import without duplicate growth or destructive changes.
- [ ] Run import/identity/mutation suites and commit.

**Acceptance:** Reimporting an older workbook cannot silently undo a verified correction. No record or linked evidence disappears without an explicit reviewed action.

## Task 6 — Persistent issues and a guided cleaning workbench

**Files:** quality.py, validation.py, server.py, static/quality.js, app.js, index.html; tests/test_quality.py, tests/quality.test.cjs.
**Interfaces:** `scan_quality(store, scope) -> QualitySummary`; `resolve_issue(store, issue_id, expected_revision, resolution) -> MutationResult`; resolution contains disposition, reason, evidence reference and optional correction. Issue states: open, resolved, accepted_exception, superseded.

- [ ] Persist issues by stable rule/record/field fingerprint; repeated scans must not duplicate them. Resolutions become stale when relevant underlying values change.
- [ ] Build a prioritized worklist by severity, issue type, source, family and asset. Show counts of issues and affected assets separately.
- [ ] Show original evidence beside the current value, suggested correction, reason and resolution action. Suggestions must not silently apply.
- [ ] Resolve related inspection/review flags through this workflow; derive dashboard and schedule review state from the same source.
- [ ] Add resumable progress and next-issue navigation; identify unknown values and accepted exceptions honestly.
- [ ] Test resolve/reopen, partial correction, changed evidence, duplicate scans, stale requests and agreement between all views.
- [ ] Run quality/backend/UI suites and commit.

**Acceptance:** A user can correct an issue and understand why it is resolved without manually editing independent flag strings.

## Task 7 — Safe normalization and bulk corrections

**Files:** quality.py, mutations.py, validation.py, static/quality.js; tests/test_quality.py, tests/quality.test.cjs.
**Interfaces:** `preview_bulk_correction(store, scope, operation) -> BulkPreview`; `apply_bulk_correction(store, preview_id, expected_revision, actor, reason) -> MutationResult`.

- [ ] Support reviewed whitespace/case normalization, family/status mapping, repeated field correction and explicit value clearing. Preserve originals and units; do not infer unit conversion.
- [ ] Show exact affected records and before/after values. State whether selection spans hidden/filtered records; never infer the selection from the current page.
- [ ] Back up and apply atomically with per-record event linkage. Revert uses a new compensating event and requires unchanged affected versions.
- [ ] Test stale preview, mixed invalid records, hidden selection, interrupted application and revert after a subsequent edit.
- [ ] Run bulk mutation/UI tests and commit.

**Acceptance:** Bulk cleaning saves work without creating invisible changes or overwriting later edits during revert.

## Task 8 — Readiness reports and named master snapshots

**Files:** quality.py, exports.py, server.py, static/quality.js, app.js; tests/test_quality.py, test_roundtrip.py.
**Interfaces:** `assess_readiness(store, scope) -> ReadinessReport`; `publish_snapshot(store, expected_revision, scope, acknowledgements) -> SnapshotManifest`.

- [ ] Define blocker rules: structural corruption, broken links, unresolved identity collisions and invalid canonical values. Report missing required business fields according to the data contract; unresolved optional information remains visible.
- [ ] Produce a readiness report listing coverage, unresolved findings, accepted exceptions, validation version and source batches. Avoid an opaque quality score.
- [ ] Publish a named immutable snapshot tied to the exact assessed revision and scope. Any later edit leaves that historical snapshot intact but invalidates current readiness.
- [ ] Include review/undated/overdue exclusions and filters in yearly plan exports, distinct from database-readiness status.
- [ ] Test concurrent edits during assessment/publication, partial scope, reopened issues and accepted exceptions.
- [ ] Run readiness/export tests and commit.

**Acceptance:** “Ready” has a reproducible meaning and cannot mean that unresolved blockers were merely hidden by a filter.

## Task 9 — Lossless interchange and proven recovery

**Files:** exports.py, imports.py, backups.py, import_batches.py, server.py; tests/test_roundtrip.py, test_backup.py, test_import_batches.py.
**Interfaces:** `export_master_package(store, destination) -> PackageManifest`; `validate_restore_package(path) -> RestoreValidation`. Full package includes database, source archives, schema/rule versions and checksums; workbook remains a portable structured view.

- [ ] Preserve issues, resolutions, correction events, import manifests and ID aliases in a versioned full package and optional workbook sheets where representable. Maintain seven-table backward compatibility; expose limitations of old exports.
- [ ] Prevent silent Excel truncation: oversized values use indexed continuation records with exact reassembly on import; exports without that mechanism must fail with field-specific guidance.
- [ ] Validate all restored records, JSON shapes, relationships, revisions and archive checksums in staging before changing live data. A standalone .db restore must disclose unavailable source archives.
- [ ] Use a coherent read snapshot during export, so assets and reference tables cannot come from different revisions.
- [ ] Provide backup creation/download, explain local versus independent copies, and test restore into an empty directory.
- [ ] Test long Unicode/multiline text, custom supported technical fields, formula text, optional sheets, missing archives, corrupt JSON, checksum failure and semantic equality after round trip.
- [ ] Run full export/restore suites and commit.

**Acceptance:** Recovery reconstructs the same master and its trust evidence. Invalid recovery inputs leave operational data unchanged; exports never report success after silent loss.

## Task 10 — User-friendly workflows and accessible visual design

**Files:** index.html, style.css, app.js, quality.js, import-workflow.js, reconciliation.js; tests/frontend.test.cjs, quality.test.cjs, import-workflow.test.cjs.

- [ ] Organize around Overview, Import & review, Data quality, Master register, Schedule and Data & backups. Make cleanup the primary first-use journey.
- [ ] Use guided import steps with resumable state, controlled inputs, month pickers, inline errors, visible required fields and clear current/proposed/source distinctions.
- [ ] Add an empty-state import action, readable asset summaries with explicit editing, active-filter chips, advanced-filter disclosure and locally visible date ranges.
- [ ] Show unsaved, draft, staged, committed and failed states accurately. Preserve drafts separately from master data and warn consistently before discarding changes.
- [ ] Use consistent typography, spacing and semantic colors with text labels. Support light/dark preference, responsive layouts and usable field touch controls.
- [ ] Verify WCAG 2.2 AA requirements through keyboard, screen-reader, contrast, focus, zoom/reflow and target-size checks. Treat this as an acceptance target, not a compliance claim based on appearance.
- [ ] Test browser Back behavior, return-to-list position, recovery from failed saves and visible versus hidden selections.
- [ ] Run UI suites and actual browser workflows using disposable data; commit.

**Acceptance:** A new user can import, find an issue, correct it, inspect its evidence and explain whether the master changed without reading the README.

## Task 11 — Release verification and operational handover

**Files:** README.md, tools/package_windows.py, launcher scripts, docs/reliable-database-acceptance.md; existing platform/package tests.

- [ ] Run the complete Python and JavaScript suites; investigate resource-cleanup warnings and explain every remaining skip.
- [ ] Exercise the whole lifecycle on representative synthetic messy workbooks and a disposable copy of the real source: stage, classify coverage, clean, repeat import, publish, export, recover and compare.
- [ ] Test process interruption, multi-tab stale edits, disk-write failures, Unicode paths, malformed files and archive unavailability without changing live data.
- [ ] Verify packaging and launch on actual Windows and macOS, plus browser download/print and narrow-screen behavior.
- [ ] Observe representative inspectors doing the core cleanup tasks without coaching. Record completion, errors, wrong turns and understanding of saved versus proposed state; fix critical failures before rollout.
- [ ] Document migration, rollback, storage locations, source retention, independent backups and the limits of local reviewer attribution.
- [ ] Deliver the candidate against a copied database first. Operational migration uses a verified backup and an agreed release point.

**Acceptance:** No unexplained source-data loss, no stale overwrite, no unresolved blocker in the published scope, no silent round-trip loss, and a demonstrated successful restore on another clean directory.

## Delivery order and gates

1. Foundation (Tasks 1–3): protect existing information and apply consistent rules.
2. Controlled ingestion (Tasks 4–5): account for sources and protect cleaned master values.
3. Cleaning workflow (Tasks 6–7): make actual data correction efficient and traceable.
4. Trust and portability (Tasks 8–9): prove readiness and recovery.
5. Usability and release (Tasks 10–11): verify the complete user experience and operational deployment. Apply relevant form/status improvements during preceding tasks rather than postponing all UI work.

Each task follows failing regression → implementation → focused checks → review → task-scoped commit. Run the full suites at milestone boundaries. Commit instructions apply only to task-owned changes; existing unrelated edits must not be swept into commits.

## Decisions to confirm before dependent implementation

- Required engineering fields and blocker rules by family: propose identifiers/context, family and inspection applicability first; absence of a tag alone must not reject legitimate untagged equipment.
- The person responsible for confirming duplicates and accepting data-quality exceptions.
- Source archive retention/storage policy and whether future source formats extend beyond the currently recognized Excel layouts.
- Local single-user operation remains the default. Shared editing and authenticated approvals require a separate architecture decision.

These decisions do not prevent the first safety regressions and disposable-data profiling from being prepared. No product implementation is part of creating this plan.


## Confirmed user decisions — requirements clarification

These decisions supersede conflicting proposals or open questions above:

- Purpose: maintain the master register and inspection schedule; inspection execution/reporting is outside scope.
- Operation: one owner performs import, cleanup, verification and maintenance on one computer. Shared access, role management and approval chains are unnecessary.
- Reimport precedence: preserve verified master corrections and flag incoming differences. Never silently replace a verified correction.
- Unresolved records remain in the master with visible warnings. Blocking issues exclude affected records from trusted snapshots.
- Trusted snapshots contain eligible verified assets and prominently list every excluded asset and its reasons. Exclusions must remain in the snapshot manifest and readiness report, not disappear through filtering.
- A missing tag/asset number is acceptable after explicit identity verification based on adequate description/location evidence. Lack of a tag alone is not a permanent blocker.
- Correction evidence may combine workbooks, reports, drawings and engineering knowledge. Record references or the engineering rationale; do not require a document attachment for every correction.
- Every applicable inspection requires a valid next month or an explicitly verified scheduling condition (for example, next shutdown or awaiting evaluation). Unverified free text does not satisfy this requirement.
- Initial imports support only the currently recognized original layouts and app exports. Generic mapping, CSV ingestion and arbitrary workbook layouts are deferred.

The decisions in the following clarification sections settle the remaining trust rules; later confirmed decisions take precedence over earlier proposals.


### Further confirmed trust rules

- Asset matching primarily uses tag or asset number, checked against location and description. Conflicting identifiers or context must trigger review; a single matching identifier is not permission to overwrite conflicting identity evidence.
- Snapshot eligibility requires the owner's explicit verification in addition to passing all blocking checks. Passing validation alone never means verified.
- Each verified scheduling condition requires a review-by month. When that month arrives, flag it for renewed review. The effect on snapshot eligibility must be confirmed before implementation.
- Verification must be tied to the relevant record content/revision, so subsequent changes cannot retain a misleading verified label; the exact re-verification policy remains to be confirmed.


### Confirmed verification granularity and minimum completeness

- Verification is field-level: changed values require verification again; unchanged verified fields retain their verification. Eligibility is derived from verified required fields and absence of blockers, not from a single manually cleared asset flag.
- Verification records should bind to field content fingerprints and include owner action, timestamp, rationale/evidence and rule version. Related dependency checks must be reevaluated when identity, family or applicability changes, without erasing unrelated verification evidence.
- When a scheduling condition reaches its review-by month, issue an overdue-review warning but retain trusted-snapshot eligibility. Include the warning in readiness reports and snapshot exceptions; do not silently exclude the asset.
- Minimum trusted record: description, family, identifiable location or context, record status and explicitly checked inspection applicability, plus the previously agreed applicable-inspection schedule/verified-condition requirements.
- Tag/asset number may be absent only with explicit identity verification. Unchanged blank identifiers must not be repeatedly treated as new unresolved defects once this exception is verified.

These confirmed rules supersede earlier suggestions that all affected-record changes necessarily invalidate whole-record verification or that an overdue condition review is automatically a blocker.


### Confirmed capacity, recovery and acceptance direction

- First-release capacity target: up to 10,000 assets. Benchmark using realistic linked inspections, source cells, issues and correction events, rather than 10,000 empty records.
- Acceptance example: the Master Inspection Plan. The user's wording identifies the example, not an exact path or confirmation of which original/cleaned revision is authoritative. Locate and confirm the intended file before the real-data acceptance run; use disposable copies only.
- Backups: create automatic local backups and automatically copy recovery packages to a user-selected folder. Select that folder during setup, show the destination and last successful copy, and provide a test-copy action.
- A local backup and an independent copy have separate success states. Missing/unwritable/disconnected destinations must cause a visible, actionable backup warning and allow retry; never report independent protection merely because the local backup succeeded.
- Build packages consistently from a single revision, write copies through temporary files with atomic finalization where supported, and verify manifest/checksums. Do not overwrite the last valid copy with an incomplete package.
- Proposed automatic policy (implementation recommendation, not a user-selected retention rule): one backup on the first mutation of each local calendar day and before bulk corrections, import application, consolidation, clear, migration and restore. Avoid duplicating unchanged recovery packages. Default to keeping all copies until an explicit retention policy is configured; show storage use.
- For 10,000 assets, implement paginated/filterable summary endpoints, load detailed source evidence on demand and avoid one SQLite connection per asset. Preserve whole-scope filtering/count/export semantics despite pagination.
- Proposed performance acceptance on a documented reference machine: warm summary page/filter response within 1 second and editor load within 1 second for representative 10,000-asset fixtures; measure large import/export/backup separately and keep progress visible. These are proposed targets to validate, not measured current results.

## Requirements closure and implementation amendments

Core product requirements are sufficiently defined to refine implementation and begin staged development once requested. Do not repeat settled architecture questions. Remaining setup facts are the exact acceptance workbook and backup destination; neither prevents isolated development.

Task 2: persist field-verification evidence alongside correction events. A changed field loses current verification; preserve its historical verification record and all unrelated field verifications.
Task 3: required trusted fields are description, family, identifiable location/context, record status and checked applicability; applicable inspections require a next month or verified condition. Conflicting identity context must be reviewed.
Task 5: verified values win over incoming differences by default; field-level acceptance is explicit. Blank identifiers with verified identity exceptions are permitted.
Task 6: allow explicit verification of individual fields and a reviewed multi-field confirmation showing exactly what will be verified. Reevaluate dependent checks without resetting unrelated verified fields. Overdue condition review is a warning.
Task 8: publish eligible verified records plus a complete excluded-record list with reasons, and retain overdue-condition warnings in the manifest. No silent exclusions or implicit verification from passing checks.
Task 9: implement user-selected automatic independent copy, explicit partial-failure states, checksum verification and interrupted-copy recovery. Test unavailable, full and unwritable destinations and recovery of source archives with the database.
Task 10: expose field verification clearly and implement server-side register/issue pagination with summary endpoints for the 10,000-asset target. Test selection/export across pages.
Task 11: benchmark representative 10,000-asset data and validate the exact agreed Master Inspection Plan copy, with a documented expected issue inventory and no operational-data mutation.

## Implementation checkpoint — 2 November 2026

The user authorized implementation and usability work in this chat. The candidate now contains the storage/validation foundation, durable controlled imports, field verification and issues, bulk corrections/consolidation, readiness/snapshots, recovery packages and the corresponding UI. Detailed implementation evidence and outstanding release gates are in `docs/reliable-database-acceptance.md`.

This checkpoint does not mark every original checkbox complete. The original source acceptance inventory, owner usability observation, full accessibility audit, exhaustive interruption/disk-failure matrix and native packaged-platform execution remain to be completed. Tests passing do not replace those gates. The working checkout preserves pre-existing uncommitted work and has not been committed, merged, deployed or used to migrate operational data.

User clarification: any backup-copy folder is acceptable for now. The launcher configures `data/recovery-copies/` only when no destination has already been selected. The UI explains its local-computer limitation and allows changing and testing the folder.

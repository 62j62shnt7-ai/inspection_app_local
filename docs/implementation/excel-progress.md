# Excel integration execution ledger
Approved plan: user attachment 352eaa12-b5b2-4202-8dee-ca29f29a7845/Pasted text.txt

Phase 1: assessed Store/schema 11, linked exports/imports, quality-derived register summaries, source payload compression, server and browser routes. Existing uncommitted work retained in place.
Ruling: keep the legacy linked exporter and import contracts intact; introduce a separately marked full editable workbook and dedicated sync/recovery routes. This prevents limited reports or old clean imports entering the sync path.
Ruling: use existing checkout as requested by repository guidance. No commits or resets of unrelated changes.
Data mapping: assets(id,name,family,version,details JSON); nested inspections,technical_details,notes,review_items,source_cells; correction_events,field_verifications,quality_issues,source_baselines,import_reference,asset_aliases,master_snapshots,import_batches and mappings retained as system business evidence. Backup paths/settings and source archive binary files belong to native recovery packages.
Work: full workbook/sync/recovery inline; independent annual report module delegated with exclusive file ownership.

Phases 2–5: complete. Added editable Tables, validation, typed month helpers, current-rule planning basis, dynamic annual/overdue detail views, dashboard/statistics/charts, chunked long text, protected baseline/evidence, issued-baseline validation, field-level three-way merge/conflict choices, workbook-local new identities, staged transactional application, reconciled exports, temporary-database recovery and explicit activation. Added separate annual, filtered and management reports and browser integration.

Ruling: complete editable exports always include archived assets, supported business metadata and source evidence. Excluding these from a recovery-capable export would make its scope misleading; limited exports are separate report-only modes. Cost: users cannot omit those categories from the full editable export.
Ruling: use modern Excel FILTER/CHOOSE for detailed expanding worklists. Target Excel 2021/Microsoft 365, preserve filtered editable Tables as detail fallback, and document manual-calculation sessions. Cost: older Excel versions do not provide dynamic detail views.
Ruling: retain exact database numeric values when Excel's 15-digit serialization changes only the unrepresentable tail. Cost: edits below Excel's own numeric precision cannot be distinguished.
Ruling: block edits to previously imported new: rows in stale workbooks and to indistinguishable legacy children lacking permanent IDs; require the reconciled workbook or distinguish/re-export the legacy records. Cost: these ambiguous cases require an explicit workflow step rather than guessed matches.

Independent review: found and fixed stale creation edits, recovery lineage, index-based child matching, empty conflict resolutions, native Excel date comparisons, current-rule baseline planning status, missing dynamic detail views, long-text missing-row handling and numeric serialization false changes. Added failure-path, rollback and repeated-cycle tests. Reconciled workbook audit-event timestamps now match the committed database exactly. Reset removes Excel previews, local creation history and retired workbook lineage.

Desktop investigation: Excel for Mac 16.113.1 initially exposed invalid table-formula shorthand and custom validation formulas longer than 255 characters. Isolated control workbooks reproduced the issue. Fully qualified structured Table row references and short validations fixed clean opening. Verified year change, due-month change, detail/count/chart recalc, new asset and linked inspection, automatic calculated-column extension, save, and exact supported import. Native Windows remains unverified.

Phase 6 evidence (7 November 2026):
- Bundled macOS Python: 401 tests passed, no skips, 20.401s.
- Node browser logic: 109 tests passed, no skips.
- Focused real browser: standalone annual download, unmodified sync, three-way conflict choice, reconciled download, recovery preview and activation/reload all passed using disposable data.
- Supplied reference workbook: 1,066 assets, 1,324 inspections, 3,192 technical rows, 834 notes, 231 review items, 11,563 source cells, 149 field-map rows. Export/import preview unchanged with zero conflicts/errors. Excel recovery preserved exact complete asset rows. Final check 56.02s; full workbook 4,311,344 bytes; annual report 147,098 bytes.
- git diff --check and JavaScript/Python syntax checks passed.
- Operational data, source workbooks, original backups and pre-existing uncommitted work were not altered by development/testing.

No platform acceptance or regulatory/safety certification is implied. Native Windows, every Excel version, physical print devices, and six elapsed months of operation were not verified. Source workbook binary files require the native recovery ZIP; Excel preserves their supported cell evidence and business history.

Final follow-up: retained original-date ambiguity and accepted chronology exceptions in the immutable planning basis, kept stable type-based identities for legacy inspections lacking IDs, and verified exact reconciled audit events. Native annual-report layout changes exposed stale selection panes when changing from a two-direction freeze to a vertical-only freeze; resetting selections to the valid bottom-left pane fixed the repair alert. The corrected report opened cleanly with readable month/count axes. The pane regression test passed; the final full bundled-runtime suite passed 401 tests.

Presentation follow-up: rebuilt the full workbook around the original per-area asset tabs. Every asset row now holds asset fields plus OSI/Internal, technical, notes and review items; hidden stable identities map each cell back to the separate app records. Added row slots for new notes, review items and technical details. A disposable one-row export, edit, add-asset and sync smoke check passed. Native Excel for Mac 16.113.1 exposed a repair prompt caused by a duplicate worksheet AutoFilter over the source Table. Removing the redundant AutoFilter cleared the prompt; a fresh one-asset workbook opened and displayed the source tab and table filters. The user's large full database export was not run because it can take time and make the app hang. Full test suites remain unrerun after the source-tab redesign.

Export responsiveness follow-up: full workbook generation now runs as a background job with stage/asset progress. Database reads take a consistent snapshot under the store lock; workbook assembly and file writing happen after releasing it. A disposable HTTP test paused workbook assembly and confirmed another app request completed before export resumed. A disposable one-asset browser session showed the progress control and completed download. The operational database export was not run.

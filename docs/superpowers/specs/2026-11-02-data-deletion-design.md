# Explicit data deletion and full reset

## Intent and confirmed decisions

The owner wants to understand Imported source coverage and control removal of stored app data. Saved database backups and recovery ZIPs must remain separately managed during a full reset (owner choice, 2026-11-02). Adding deletion controls does not authorize using them against the operational dataset during development.

## Current behavior verified

Imported source coverage shows committed imports with unclassified populated rows or excluded sheets. It records omitted rows and links to the original archived workbook; it does not itself add assets or indicate failed saving. The current UI filters the latest 20 imports and has no dismiss/delete control. Clear database removes assets and imported reference tables but retains committed import batches, source archives, snapshots, corrections and other history. Six import-batch tests passed; a disposable import/clear reproduction confirmed its coverage entry and source archive remain after assets disappear.

## Approaches

1. Add only a stronger reset. Simple, but users cannot remove individual obsolete records or manage coverage independently.
2. Add individual deletion controls plus a full reset (recommended). Makes scope explicit and supports both normal cleanup and starting over.
3. Repurpose Clear database to delete all history silently. Rejected: changes an existing operation's meaning without exposing its effects.

## Proposed behavior

- Rename the existing operation to **Clear asset register** and state exactly what it retains.
- Add **Manage stored data** with counts and selectable categories: assets; imported reference data; staged imports; import coverage/history; archived source workbooks; snapshots; verification evidence; correction/bulk/consolidation history; browser drafts and reconciliation state.
- Give coverage entries a stable batch identifier and controls to **Dismiss from coverage** or **Delete stored import evidence**. Dismissal only removes the item from the attention list and can be undone. Deletion previews the import records, current asset dependencies and affected archived workbooks; it never secretly deletes assets or purges copies embedded elsewhere.
- Keep permanent deletion honest: an archive used by another retained import is shared and cannot be removed as if unreferenced. Source deletion must retain explicit missing-evidence lineage for retained assets so quality checks do not silently pass. Removing required lineage is allowed together with the dependent assets, or in full reset, after the preview explains the consequence.
- Add per-item/selected asset and snapshot deletion, staged-import discard, and dedicated history/browser-state cleanup. Deleting an asset normally retains its audit journal; deleting history is an explicit separate choice. Show retained copies in history, snapshots or backups in the preview instead of calling normal record deletion a complete erasure.
- Add **Reset working data**: removes assets, imported reference values, import batches/coverage, aliases, baselines, import links, snapshots, verification/quality records, correction events, bulk/consolidation records and archived source workbooks. Reset browser-owned drafts, import/reconciliation state and selections in the current browser. Other browsers must reload; stale sessions cannot resurrect deleted records.
- Keep database backups, recovery ZIPs, the configured backup folder and appearance separately managed. Never delete files outside app-owned archives or infer that external/downloaded copies were erased. Preserve the internal revision watermark/schema so stale editors remain rejected.
- Keep existing selected-backup deletion. Add explicit selection/deletion for recovery packages in the configured destination, limited to app-named regular files; never recursively clear an arbitrary chosen folder.

## Execution and recoverability

Every destructive action first returns a read-only preview with counts, dependencies, exact managed filenames and a master revision. Require an explicit confirmation of that preview; reject stale previews. Normal data removal saves and reports a recovery copy before changing data. Backups are managed independently: a reset leaves that recovery copy and older backups intact. Backups deleted through their own explicit file-deletion flow do not generate more backups of themselves.

Use transaction-bound database changes and a same-filesystem archive quarantine so failures restore both metadata and files. Preview and mutation share the app lock. Cancelled previews do not modify data. Use bounded, local-only operations compatible with Windows file handles and Unicode paths. No changes to verification eligibility rules or import matching.

## Validation and delivery

Use only disposable datasets. Test dismissal/undo, selected versus shared archive deletion, source-evidence warnings under current rules, per-item deletion, full-reset table and file coverage, preservation of backups/recovery ZIPs, stale sessions, failure rollback, original/optimized backup restore and Unicode paths. Check the live browser flows and run Python/Node suites. Rebuild and test a complete Windows package; native Windows remains unverified until exercised on Windows.

## Review

Current-data removal, historical-evidence removal and backup-file removal are visibly distinct choices. Full reset is the path to a clean dataset with no residual coverage. All stored-data categories have either an individual/category cleanup action or inclusion in full reset. No operational deletion occurs merely because these controls are added.

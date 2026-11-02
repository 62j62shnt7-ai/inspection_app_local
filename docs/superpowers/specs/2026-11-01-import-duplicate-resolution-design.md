# Resolve original-import duplicates inside the app

The user's request extends the implemented original-workbook import: resolve duplicate and ambiguous identities in the import preview, without editing Excel or excluding entire tabs. This supersedes the earlier design's prohibition on an interactive matching editor.

## Approach

Extend the staged preview with structured conflict rows and an explicit resolution endpoint. Keep extraction, tab selection, backup, stale-preview checks and final Import confirmation. A generic workbook editor or automatic field merging would introduce unrelated work and ambiguous precedence; neither is needed to resolve identity conflicts.

Each conflict row displays source tab/row, description, original tag/asset number, context, service status, inspection dates and notes. Show possible existing assets with the same information, including their original source row. Each row starts undecided. The user chooses **Import as a separate asset**, **Skip this incoming row**, or **Update a specific existing asset**. Keeping one repeated row and skipping the other implements "use this row" without silently combining differing fields. Skipping never deletes the existing asset; separate never overwrites one. Updating replaces the full existing imported record, as the normal importer does, with a warning and final comparison.

## Server contract and persistence

Store a pristine extraction alongside the staged preview. POST /api/import/resolve receives the preview token and row-key/action/target choices; resolve only server-staged data, validate keys and candidates, and generate a new preview token. Never mutate the database on preview. An unresolved conflict or two incoming rows targeting the same existing asset blocks application. Reject stale tokens, unknown rows/actions/targets, cross-source/family matches, or a target absent since preview. Any skipped rows force merge, protecting retained existing records.

Assign row keys from source tab, source row and a hash of original row contents. Separate rows get distinct permanent IDs, even when their text is identical. Persist final choices only when Import succeeds, within the same transaction. Reuse remembered choices only for an unchanged source-row key and a compatible existing target; changed/moved source rows return to review instead of using a stale positional mapping. Show when saved choices were reused. Keep excluded-row original cells as unassigned evidence labelled skipped by review.

Store choices in import_reference and preserve them in an optional **Import Decisions** sheet in full exports. The seven required cleaned-format tables remain unchanged. Validate optional decision rows; old cleaned exports without this sheet still import normally. Partial imports retain decisions/evidence from excluded tabs.

## UI state

Render actionable conflict cards instead of cascading duplicate error strings. Changing a choice hides Import immediately. **Update preview** sends the choices and displays revised totals/comparison. Bind requests to the upload/selection generation so late responses cannot restore an obsolete preview. New uploads or tab selection clear pending decisions. Avoid unsafe default choices. All choices remain editable before final apply; no database changes occur until Import.

## Verification

Test separate/skip/match, saved choices and changed-row invalidation, multiple target collisions, forged requests, stale preview, source evidence, rollback/backup, export/re-import, excluded tabs and replace restriction. Test actual browser controls and a disposable database using the supplied workbook; never change the user's database. Preserve unrelated uncommitted work.

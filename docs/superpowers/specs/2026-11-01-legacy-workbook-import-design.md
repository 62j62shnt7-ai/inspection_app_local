# Original inspection workbook import

## Intent and scope

Import the original multi-sheet Master Inspection Plan directly, including future updates retaining its layout. The user chose a dedicated importer for this layout over a general column-mapping tool. Keep the existing cleaned-workbook importer and local Python/openpyxl architecture.

The user also requires choosing which workbook tabs to exclude before import.

## Approaches

1. **Selected: explicit mappings for the original workbook.** Validate known sheet headers and map their fields into the existing seven-table format. This is testable against the original and cleaned workbooks, with no per-upload mapping setup.
2. **Deferred: general mapping wizard.** Accommodates unrelated workbooks but adds setup, ambiguity, and a larger interface.

## Reading and preservation

Use the cleaned workbook's Field Map and source references as evidence for explicit, versioned mappings in application code. Do not depend on the user's Downloads file at runtime or embed its asset data in the importer. Recognize headers and sections, rather than assuming every populated row is an asset. Validate required columns before extracting a supported sheet; reject partial or shifted layouts instead of importing misaligned data.

Extract asset identity, description, family, service status, inspection dates, technical fields, and notes into the same structures used by cleaned imports. Preserve source sheet, row, cell, original values, formulas and available cached results, and cell comments as evidence. Keep section notes associated with their section; keep unassigned workbook evidence separately. Reference-only sheets must be identified in the preview and retained as cell evidence, without manufacturing assets. This preserves cell information, not Excel appearance, images, embedded objects, or original workbook round-tripping; retain the original file independently.

Normalize actual Excel dates and explicitly supported unambiguous date strings to YYYY-MM. Preserve statuses such as OOS, Never, and W/Eval as text with appropriate status fields. Never invent a month for a year-only value, ambiguous date, formula without a usable cached value, or unresolved text. Create review items and keep unresolved inspections out of ordinary dated scheduling through the app's existing review mechanism. Source text is data, never executable instructions.

## Identity and repeat imports

The cleaned workbook uses IDs derived from source sheet and row, so row position alone cannot safely identify future uploads. For a first import into an empty register, generate compatible IDs where possible. For an existing register, reuse IDs only for unique, strong identities within the appropriate family/source sheet (such as original asset number or tag). For records without strong identifiers, require an exact unique description and relevant contextual fields; fuzzy matching must never apply changes automatically. Source-row agreement alone is insufficient. Ambiguous, duplicate, or conflicting identities block application with actionable details. Do not silently collapse distinct assets or overwrite a different record after rows move.

## Preview and application

Automatically detect cleaned versus original format in the existing Import flow. For original files, first list every actual workbook tab with an Include checkbox, initially checked, and Select all / Deselect all controls. Label each tab as asset extraction, reference-only, or unsupported, so selection does not imply that every sheet becomes assets. Let the user uncheck any tab before generating the import preview. Reject an empty selection. Unsupported included tabs block preview with a message to exclude them; unsupported excluded tabs do not block import. Validate and extract selected tabs only. Excluded tabs contribute no assets, inspections, notes, source cells, or field-map entries. Do not treat a deliberately excluded sheet as a missing required sheet.

The selection belongs to the uploaded workbook and resets on a different upload. The server validates selected sheet names against the uploaded workbook and stages the exact selection with the preview data. Changing the selection invalidates the displayed preview and disables Apply until another preview succeeds. The UI must retain the workbook while selecting tabs and re-previewing; do not depend on an upload temporary path that has already been deleted.

For original files, show format, included and excluded sheets, per-sheet asset/inspection counts, reference-only sheets, review warnings, blocking errors, and existing versus incoming changes. Distinguish review warnings (importable unresolved source data) from structural/identity errors (apply blocked). Show a clear notice that importing an existing asset replaces its imported record, including manual edits, as the current import does.

Keep merge as the default: absent assets remain. Retain the explicit replace option and its existing confirmation. Every application uses the current staged preview, stale-data protection, transaction, and automatic backup. Preview never changes the database. Preserve original evidence and review items through full Excel export and cleaned-workbook re-import.

For an original-layout import with any tab excluded, disable replace mode and explain that merge retains existing records from excluded tabs. A partial import must never remove those records. This restriction is a proposed implementation safeguard, not an additional user request. Keep cleaned-format imports atomic across their seven linked tables; arbitrary exclusion there would break asset relationships, so this checklist applies only to original-layout workbooks.

## Validation

Compare extraction from the supplied original workbook with the cleaned draft's 1,066 assets and 1,324 inspection rows, investigating differences rather than forcing those totals. Verify representative fields and dates for every supported asset sheet. Add small synthetic fixtures covering section rows, merged headers, ambiguous dates and statuses, formulas, comments, missing/shifted columns, duplicate identities, reordered rows, repeated uploads, and importing into an existing cleaned register. Exercise HTTP preview and UI warnings, blocked apply, backups, merge/replace, and full export/re-import. Run the relevant existing Python and JavaScript suites. Tests must use temporary databases and leave the user's data unchanged.

Also verify selecting one or several asset tabs, excluding reference tabs, excluding an unsupported tab, empty and forged selections, invalidating previews after selection changes, and resetting selections on upload. Confirm excluded records and evidence remain unchanged in the database, excluded tabs contribute nothing incoming, and partial-import replace requests are rejected server-side.

## Builder decisions and limits

### Resolved implementation boundaries

- Asset extraction covers the ten sheets represented by the cleaned draft: Vessels & TKs, OP Piping, GP Piping, Turbines Piping, WD-33 Piping, EPFs, MFDs, TLs, FLs, and GL Lines. Other recognized original sheets, including dead-leg sheets and Coolers, are reference-only in this version; make that limitation explicit in the preview. Unexpected populated sheets block import until their treatment is understood.
- Initial IDs follow the cleaned draft's fixed sheet codes A01 through A10 and original source row, padded to four digits. Existing matches retain their permanent IDs after row movement. A new asset whose proposed ID is already occupied receives a deterministic collision-safe ID based on its source sheet and normalized identity; never replace an unrelated asset because of that collision.
- Read formula and cached-value views separately. Preserve formula text in Source Cells.original_value, mark its Excel type as formula, and preserve the available cached value and comment together in a documented JSON structure in original_annotation. Ordinary comments remain preserved. This fits the existing export columns and must survive export/re-import; it does not promise to recreate executable formulas in an exported original-layout workbook.
- Any unresolved identity conflict blocks the entire apply operation in both merge and replace modes. Replace cannot delete absent records while conflicting incoming identities remain. Resolving unsupported cases in the source workbook and uploading again is sufficient for this version; an interactive matching editor is out of scope.

The builder chooses mapping module structure, exact identity normalization, and compact preview presentation, documenting unsupported layout variants. Do not add a general mapping wizard, fuzzy automatic merging, or alter campaign Reconciliation. Keep unrelated working-tree changes intact. No claim of universal dirty-workbook support: support is limited to the recognized original layout and validated variations.

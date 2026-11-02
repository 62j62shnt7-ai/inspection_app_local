# Local Master Inspection Plan

This is a **testing build**. Do not rely on it as the only copy of an inspection plan until the launch and data workflows have been verified on your computer. Keep the original workbook and independent backups.

Use the **Light mode / Dark mode** control in the header to switch themes from any screen. The choice is remembered in this browser; **Data & backups → Appearance** also lets you follow the system preference.

## macOS

Extract the complete folder somewhere writable. Double-click `Start Inspection App.command`. The app uses its own Python and opens a browser on the local computer. Leave its terminal window open while using the app; close it to stop the app. If macOS blocks the downloaded file, use your organization's approved application procedure.

On first use, open **Data & backups**, choose `reference/Master_Inspection_Plan_Cleaned_Draft.xlsx`, preview the counts, then import. The application stores its database and backups under `data/`. Keep that folder when updating app files. The app is local to this computer and does not share changes with other people.

## Windows

Extract the complete folder to a writable location and double-click `Start Inspection App.bat`. It uses the bundled 64-bit Python 3.11 runtime and packages; Python installation and administrator rights are not required. Import the workbook in `reference/` on first use. Use Edge, Chrome, or Firefox; Internet Explorer is not supported. Native Windows execution still needs verification.

If you already have a database from an earlier version, **keep your existing `data/` folder**. Replace only the application files and runtime; do not overwrite that folder. Make a separate backup before updating.

To update from the Windows ZIP: close the app, extract the ZIP to a new writable folder, then copy your existing `data/` folder into it. Start the app from the new folder. The ZIP contains no database or backups.

The Windows package also includes the Python regression tests. From Command Prompt in the extracted app folder, run:

```bat
runtime\windows\python.exe -X utf8 -m unittest discover -s tests -v
```

These tests use temporary databases and do not alter your `data/` folder.

## Backups and imports

The Data & backups page accepts the original multi-sheet Master Inspection Plan as well as cleaned workbooks and app exports. After selecting an original workbook, choose which tabs to include using the checkboxes (or Select all / Deselect all), then click **Preview import**. Changing the file or tab selection clears the previous preview. Excluded tabs contribute no imported data, and partial imports use merge so existing records from excluded tabs remain.

Asset extraction supports the original layouts for Vessels & TKs, OP Piping, GP Piping, Turbines Piping, WD-33 Piping, EPFs, MFDs, TLs, FLs, and GL Lines. Other recognized original tabs, including Coolers and Dead Legs, are retained as reference cell data only; the checklist labels their role. Unsupported included tabs or shifted headers must be corrected or excluded. Cleaned workbooks import all seven linked tables together.

Original cell values, formula text with available cached values, and comments are preserved as source evidence. Workbook appearance, images and embedded objects are not imported. Missing or ambiguous inspection months and dates in the wrong order are flagged for review without inventing corrections. Keep the original file independently. The preview compares the last imported source, current master and incoming values. Verified master corrections are retained and incoming differences become review issues. Incoming blanks and missing linked evidence do not silently erase populated master data. Inspect all proposed differences before applying.

If the preview finds duplicate identities or conflicting matches, use **Resolve duplicate and matching conflicts** inside the app. Each affected incoming row shows its original details and any possible existing matches. Choose **Import as a separate asset**, **Skip this incoming row**, or the specific **Update existing** record, then click **Update preview**. To keep one repeated row, select its appropriate separate/existing action and skip the other row. The app does not combine conflicting dates or notes automatically. Skipping never deletes an existing asset, preserves the incoming source cells as skipped evidence, and requires merge mode. All identity conflicts must be resolved before Import becomes available.

Decisions are saved only when the import succeeds. They are reused for unchanged source rows while the existing target remains compatible; changed or moved rows require review again. Full exports preserve saved decisions in an optional **Import Decisions** sheet. Older cleaned workbooks without this sheet remain supported. Choosing a new file or changing selected tabs clears un-applied decisions; nothing is written to the source Excel file.

Automatic local backups run before the first edit each day and before imports, bulk corrections, consolidation, clear and restore. They are kept in `data/backups/`. In **Data & backups → Saved backups**, select individual backups (or Select all) and choose **Delete selected backups** to remove obsolete local restore points; the confirmation names the files. This does not delete recovery packages, snapshots, source archives, or the active database. The launcher initially configures `data/recovery-copies/` for automatic recovery-package copies, unless you have already chosen another folder. Change the destination and test it under **Data & backups**. Copies on this computer do not protect against loss of the computer; use another drive for that. Failed copies produce a visible warning while preserving the last completed copy. To restore, use the saved-backup selector or upload a full recovery package. A safety backup is created before replacement.

An Excel interchange export is available under Data & backups. Full recovery packages also preserve the verification journal, snapshots and archived original files; use those for complete recovery. Import matches permanent asset IDs: the preview shows proposed updates and records retained, and apply creates a backup. An exported workbook can be imported into an empty database. Different assets are not merged by name. CSV export is available on the asset register.

## Clean, verify and maintain

1. Import an original supported workbook or app export. Choose source tabs, inspect extraction coverage, resolve identities and compare proposed changes. Unclassified populated rows require an explicit coverage acknowledgement. The source file is archived unchanged by its content hash. A staged preview can be resumed after restart if the master has not changed. After import, **Imported source coverage** in Data & backups reopens each recent import's unclassified sheet rows and exact archived workbook for follow-up.
2. Use **Data quality** to find blockers, warnings and assets awaiting verification. Correct an asset in the editor; source cells remain available on the Source tab. Browser drafts can be recovered only against the same saved asset version.
3. For an individual asset, open **Review verification**, check only fields you reviewed, and record evidence or engineering rationale. To verify many records efficiently, select them in the master register across pages and choose **Verify selected**. Review the complete preview of source rows, required field values and blockers, cite the workbook/report, confirm the full selected scope, and apply once. The app still records verification per asset and field. Import alone never verifies anything; blocked assets remain outside trusted snapshots until their blockers are resolved. Saving a correction alone never verifies it. Changed fields lose current verification; unchanged fields retain it, and historical evidence remains visible.
4. An applicable inspection needs a next month or a verified scheduling condition with a review-by month. An overdue condition review warns but does not itself exclude an otherwise verified asset. Missing tags can be handled by explicitly confirming equipment identity and context. A shared tag needs review; legitimate separate equipment can retain its original tag after identity verification and an evidenced exception.
5. Publish a named trusted snapshot. It contains eligible assets and lists **every excluded asset and reason**, along with warnings, exceptions, rule version and source batches. Later edits do not rewrite historical snapshots.
6. For repeated corrections, select assets across register pages, preview all bulk changes and record a reason before applying. Reverting is a new correction and is refused if any affected asset has subsequently changed. Duplicate consolidation requires exactly two selected records, an explicit survivor and a decision for every conflict. Retired IDs remain aliases; evidence and history are preserved.

The register and quality worklist use server pagination; source-cell and technical evidence is loaded with the editor. Exporting filtered or selected records still covers the complete selected scope, rather than only the visible page. Yearly exports include scope and omitted-inspection reasons. Oversized Excel strings are stored in indexed continuation rows and reassembled on import.

Reviewer attribution is a local owner label and evidence record, not authenticated approval. This app maintains a master register and schedule; verification does not certify equipment safety or regulatory compliance.

## Known testing limits

The automated tests exercise workbook import, reconciliation, edits, export/re-import, backups, restore, month logic, local HTTP requests, Unicode paths, and cross-process data locking. The Python suite is checked on Python 3.11 and 3.14 on macOS. Windows encoding and isolated import-path failures have regression coverage. The new quality/verification workflow has been exercised in the macOS in-app browser using disposable synthetic data. Native Windows execution, a complete screen-reader/contrast audit and owner acceptance on the intended original workbook remain release gates. The app does not implement shared team access.

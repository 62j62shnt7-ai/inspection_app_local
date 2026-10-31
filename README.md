# Local Master Inspection Plan

This is a **testing build**. Do not rely on it as the only copy of an inspection plan until the launch and data workflows have been verified on your computer. Keep the original workbook and independent backups.

## macOS

Extract the complete folder somewhere writable. Double-click `Start Inspection App.command`. The app uses its own Python and opens a browser on the local computer. Leave its terminal window open while using the app; close it to stop the app. If macOS blocks the downloaded file, use your organization's approved application procedure.

On first use, open **Import**, choose `reference/Master_Inspection_Plan_Cleaned_Draft.xlsx`, preview the counts, then import. The application stores its database and backups under `data/`. Keep that folder when updating app files. The app is local to this computer and does not share changes with other people.

## Windows

Extract the complete folder to a writable location and double-click `Start Inspection App.bat`. It uses the bundled 64-bit Python 3.11 runtime and packages; Python installation and administrator rights are not required. Import the workbook in `reference/` on first use. This package has not yet been run on a Windows computer.

If you already have a database from an earlier version, **keep your existing `data/` folder**. Replace only the application files and runtime; do not overwrite that folder. Make a separate backup before updating.

## Backups and imports

Use **Create backup** before significant work. Backups are stored in `data/backups/`; copy them elsewhere periodically. To restore, use the backup selector under Import. Restoring replaces current data and first makes a safety copy.

A full Excel export is available under Import. Import matches permanent asset IDs: the preview shows records to be replaced and records retained, and apply creates a backup. An exported workbook can be imported into an empty database. Different assets are not merged by name. CSV export is available on the asset register.

## Known testing limits

The automated tests have exercised workbook import, edits, full export/re-import, backups, basic restore, month logic and local HTTP request handlers. This environment blocked opening a listening socket, so browser interaction has not been verified here. No Windows execution test has been performed. The app does not implement shared team access.

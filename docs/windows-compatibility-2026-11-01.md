# Windows compatibility review — 2026-11-01

Reviewed startup and isolated Python imports, HTML/text encoding, browser APIs and CSS, Unicode/space-containing paths, SQLite connections and restore URIs, workbook upload/validation/export, temporary-file cleanup, data-directory locks, and portable packaging.

## Fixes

- App bootstrap explicitly includes its own directory; generated embedded-runtime paths include the application root.
- HTML is explicitly decoded as UTF-8 before token substitution, avoiding Windows code-page corruption.
- Windows launcher uses isolated Python, explicit UTF-8, disabled bytecode writing, quoted paths, pushd, and argument forwarding. Batch files retain CRLF line endings through Git attributes.
- Failed workbook imports and reconciliation now close the underlying file even while partially consumed worksheet iterators and exception tracebacks remain alive. This prevents Windows temporary-file deletion failures.
- Unwritable data-directory creation is handled as a startup error. Legacy console encodings cannot turn Unicode error messages into another exception.
- Packaging accepts the existing Python 3.11 bundle and Python 3.14, includes tests, and finds dependencies in either platform bundle.
- The new export/import path test exposed an unrelated round-trip issue: manually created assets without an explicit record status exported a blank status that could not be reimported. Exports now write the default Active status.

## Verification

- Python 3.11 with the Windows bundle's pure-Python packages, on macOS: 42 tests passed.
- Bundled macOS Python 3.14: 42 tests passed.
- Actual ZIP extracted under a path containing spaces and Arabic text, then tested with host Python 3.11 using only the extracted package's dependencies: 42 tests passed.
- JavaScript: 42 tests passed.
- ZIP integrity verified; no operational database or backups included.
- Regression coverage includes isolated imports, Windows default text decoding, legacy console errors, rejected-workbook file handles, Unicode paths with # and %, backup restore, exported-workbook reimport, and cross-process data locking.

The Windows executable, cmd.exe launcher, native Windows file locks, and Windows browser rendering cannot be executed on this macOS host. The packaged Python tests can be run on Windows using the command in README.md. Existing test cleanup ResourceWarnings remain; the suites have no failing or skipped tests.

## Update

Close the running app. Extract inspection-app-windows-2026-11-01.zip to a new writable folder. Copy the existing data folder into the extracted inspection_app_local folder, then double-click Start Inspection App.bat. Keep the old folder until the new copy is verified. The operational database in the workspace was not changed by this review.

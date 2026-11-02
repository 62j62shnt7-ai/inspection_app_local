# Windows compatibility review — 2026-11-01

## Current status — 2 November 2026 full review

Source checkpoint `b9ccfa1` passed 232 Python and 83 Node tests on macOS, including current compatibility simulations. **Native Windows execution remains unverified.** Existing distribution ZIPs were not rebuilt or certified; source results do not establish their contents/runtime behavior.

The [full review](app-review-2026-11-02.md) found nine open defects. R4 reproduces startup-blocking cleanup after deferred deletion and a backup-folder change; R5/R6 affect archive/legacy-backup recovery; R9 breaks yearly export after reset. R4 used an injected macOS file-lock failure, not native Windows locking. Follow the [repair plan](superpowers/plans/2026-11-02-app-review-fixes.md), then repeat packaged launch/save/clear/reset/export/recovery on Windows. Earlier counts below are historical.

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

## 2026-11-02 — compressed-backup flush fix

A Windows save screenshot showed the generic HTTP 500 response. The new compressed-backup publication path reopened the staged file with `rb` before `os.fsync`. Windows flushing requires a writable file handle, so both the first protected save and clear can fail before the backup is published. The existing source-only `inspection_app_local.zip` also contains this defect and does not contain the Windows runtime. Use the new complete Windows package instead of mixing application files.

Changed the staging handle to `r+b`, explicitly flushed it, and kept fsync, integrity checks, compression validation and atomic publication. Regression coverage emulates Windows' writable-handle requirement: it reproduced the backup error and the screenshot's exact HTTP 500 response before the fix, then passed raw/compressed backup restore and HTTP create/edit/clear/recovery after the fix. No operational data was used.

Reference: Microsoft documents the GENERIC_WRITE requirement for FlushFileBuffers: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers

Native Windows execution and the reported Windows hang remain unverified on this macOS host. A complete-workbook clear is checked through live localhost HTTP with bounded request timeouts and recovery from the pre-clear backup. No UI behavior changes are included in this fix.

### Clear performance and history preservation

Profiling a disposable import of the 1,066-asset reference workbook found 1,136,357 JSON decodes: clear called peer identity invalidation once per removed asset, scanning the full asset table each time. Clear now bulk-invalidates evidence and resolved/accepted issues for the live asset set, then appends every original per-asset audit event. Historical retired-asset issues, open issues, evidence rows, snapshots, IDs and revision ordering are retained. A SQLite-trigger failure test confirms the whole operation rolls back.

Live localhost clear plus pre-clear backup: 13.45 seconds before and 0.433 seconds after, with an immediately responsive follow-up GET and successful restoration of all 1,066 assets. Full host suite: 205 Python tests passed; Node suite: 78 passed. The complete Windows ZIP includes the runtime, matching application files, tests, checksums and WINDOWS-UPDATE.txt; no operational database or backups are included.

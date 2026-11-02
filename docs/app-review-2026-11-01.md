# App review — 2026-11-01

Follow-up: the three findings below have been fixed. Restore now assigns versions above a persistent watermark and serializes mutations; ordinary source/dashboard navigation clears reconciliation-only restrictions; complete review CSV exports include every plan row and all selected changes. The CSV is explicitly described as a reference copy, not an importable review backup. Final verification: 32 Python tests passed with the bundled macOS runtime and loopback access; 42 JavaScript tests passed; `git diff --check` passed. Existing resource-cleanup warnings remain, and Windows execution is still unverified. The original findings below document the reviewed behavior before these fixes.

The current test suite passes, but the app has functional gaps that prevent an unqualified readiness sign-off. This review did not change application code or the working database.

## Findings

### P1 — Restore can revive stale edit permissions

`inspection_app/backups.py:30-31` restores the stored per-asset versions along with the database. `inspection_app/store.py:47` accepts edits solely by matching that version. A browser tab or saved reconciliation can therefore become valid again after a restore rolls a version backwards. Subsequent edits can also reuse versions belonging to the pre-restore timeline.

Reproduced using a temporary database: create asset version 1, keep a version-1 payload, back up, edit to version 2, restore the backup, and submit the old payload with expected version 1. The stale save succeeds. This needs a database generation/revision that changes on restore and is checked on mutations, or equivalent non-reusable edit tokens. Regression coverage should include stale editor and reconciliation requests across restore.

### P2 — Source shortcuts and dashboard cards retain reconciliation-only restrictions

`static/app.js:69-71` clears visible filters but leaves `onlyRecentRecon` and `onlyConfirmedRecon` set. `matches()` at line 105 applies those restrictions before ordinary filters. Dashboard summary-card and aging-card handlers have the same omission.

After “View updated assets” or “View confirmed matches,” selecting a source tab (including “All assets”) or a dashboard card can silently show only the reconciliation subset. This contradicts the source counts and the empty-state instruction to select a source tab to start fresh. A Node VM reproduction confirmed that selecting “GP Piping” leaves `onlyRecentRecon=true`. Clear both restrictions when opening an ordinary source/dashboard view; test navigation after both reconciliation modes.

### P2 — The advised reconciliation fallback export omits staged changes

`static/reconciliation.js:5` tells users to export their results if browser persistence fails. The CSV handler at line 83 never exports `row.changes`: proposed last/next months, service status, and manually entered remarks are missing. It exports only currently filtered rows and provides no review-state import mechanism.

A staged manual remark or edited proposed month exists only in memory when storage fails; following the displayed export advice and closing the page loses it. Provide a complete downloadable review-state backup and restore path, or at minimum export every selected field/value and accurately describe the export's recovery limits.

## Verification

- Bundled macOS Python 3.14.6 successfully imports SQLite and openpyxl 3.1.5.
- Full Python suite using that bundled runtime and loopback access: **30 passed, zero skipped**, 8.592 seconds. Covers import preview/apply, merge/replace, export round-trip, save conflicts, backups/restore, reconciliation atomicity, HTTP protections, month handling, data-directory locking, and packaging checks.
- JavaScript suite: **37 passed**, including register helpers, scheduling, selections, reconciliation decisions, conflicts, comparisons, and staged application.
- Working database: SQLite integrity check returned `ok`; all **1,066 assets** pass the store's current validation.
- Current-data read benchmark: fetching every asset through `get_asset` took approximately **0.088 seconds**; JSON payload approximately **4.59 MB**. One local measurement, not a sustained-load benchmark.
- Browser smoke review used a temporary SQLite backup copy. Dashboard, register navigation/search, editor inspection tabs, and yearly plan rendered; no warning/error console entries were observed during those checks.
- Dashboard displayed 1,061 active assets, 147 inspection review flags, and 302 inspections without a date/with a condition. These are recorded data-quality states, not evidence of software failure; source accuracy still needs human review.

## Limits and secondary observations

- Windows runtime execution and double-click launch behavior were not tested on Windows. Packaging tests do not substitute for a Windows run.
- Browser smoke checks are not exhaustive end-to-end coverage of every mutation, download, print layout, responsive layout, or multi-tab race. Automated tests cover many backend mutation paths separately.
- Restore validates SQLite integrity and column names, not the semantic validity of every restored record. Hand-modified or structurally compatible but malformed databases need stronger validation if supported.
- The store accepts arbitrary JSON detail keys, while workbook export uses fixed headers. Unsupported/custom API fields do not survive an Excel round-trip. The standard UI-supported fields are covered by existing round-trip tests.
- `/api/assets` opens one SQLite connection per asset and sends all detail/source evidence on every refresh. It was fast at the present size, but this design scales linearly and warrants a single-query summary endpoint if the register grows substantially.
- Tests emit resource-cleanup warnings, although they pass. These should be traced before treating warning-free operation as verified.

Recommended order: prevent stale writes across restore, correct navigation filter resets, then make reconciliation review recovery complete. Add focused regression coverage before claiming these findings resolved.

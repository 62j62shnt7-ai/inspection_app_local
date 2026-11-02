# Local Master Inspection Plan: agent guidance

## Working efficiently
- Start with the relevant files and focused `rg` searches; read large files in bounded sections and limit command output. Reuse findings instead of rescanning the repository.
- Use subagents only when useful for independent work; avoid duplicating broad repository exploration. Run focused tests while iterating and the applicable broader checks before finishing.
- Preserve existing uncommitted work. Do not reset, clean, or overwrite the user's files.

## Project map
- `app.py` starts the local server and locks the data directory. `inspection_app/server.py` handles HTTP; `store.py`, `migrations.py`, and `mutations.py` manage persisted data.
- `imports.py`, `legacy.py`, `import_batches.py`, `import_identity.py`, and `reconciliation.py` cover workbook import and matching. `exports.py`, `backups.py`, and `recovery.py` cover export and recovery.
- `quality.py`, `validation.py`, `register.py`, and `consolidation.py` implement quality, verification, register and consolidation workflows. `months.py` handles month logic.
- `static/` is the browser interface; `tests/` contains Python unittest and Node tests. Consult `README.md`, `docs/data-contract.md`, and `docs/reliable-database-acceptance.md` for details relevant to the task, checking the code when docs may be stale.

## Data and safety
- Treat `data/`, backups, recovery packages and source workbooks as user data. Never alter or delete them for development or tests; use disposable data directories and retain independent backups before migrations or recovery changes.
- Preserve permanent identities, source evidence, audit history, backups, and export/import compatibility. Preview and resolve ambiguous matches rather than guessing or silently overwriting populated or verified data.
- Importing or editing is not verification. Keep field-level verification, blockers, snapshot exclusions and historical evidence intact. Do not infer engineering conclusions or claim regulatory or safety certification.
- Maintain local-only operation and macOS/Windows compatibility. Native Windows and owner acceptance remain unverified unless tested; do not claim otherwise.

## Verification
- Python suite: `python3 -m unittest discover -s tests` (uses disposable databases). A listening-socket test may require permission for localhost binding.
- Browser logic: `node --test tests/*.test.cjs`. Run relevant focused tests first; add broader checks appropriate to the changes. For UI changes, check the affected flow in a browser with disposable data when feasible.
- For import/export, migrations, backups or recovery, test round trips and failure paths relevant to the change without using the operational database.

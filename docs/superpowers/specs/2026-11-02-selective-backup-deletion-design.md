# Selective saved-backup deletion

## Intent

Let the single app operator choose and remove obsolete local database backups from **Saved backups**, so backup storage can be managed without deleting useful restore points by mistake.

## Goals

- Show a checkbox for each app-managed saved database backup.
- Support selecting and deselecting listed backups, including a select-all control.
- Enable **Delete selected backups** only when there is a selection and show the selected count.
- Before deletion, name the selected files and ask for explicit confirmation.
- Restrict deletion to the app's managed `backups/inspection-*.db` files; reject traversal, symlinks, and unrelated files.
- Report how many files were deleted and any failures, then refresh the list.
- Recognize only backup filenames emitted by the app's backup creator; a lookalike prefix alone does not make a file app-managed.
- If a deleted file is the current automatic local backup, clear its success/path/date/day status and re-arm the next-edit backup. Refresh the displayed backup status after deletion.

## Non-goals

- Delete portable recovery packages, trusted snapshots, source archives, or the active database.
- Automatically delete old backups or change the backup retention policy.
- Create a new backup as part of clearing backups; that would counteract the selected deletion.

## Approaches

- **Delete all listed backups:** simple, but creates accidental-loss risk when only a few files are obsolete.
- **Keep the newest automatically:** safer by default, but prevents removing an unwanted newest backup and does not let the operator control the result.
- **Select individual backups (chosen):** matches the user's request for selectable deletion and gives the operator exact control over which restore points are removed.

## Design

The Saved backups list will present each backup with its current filename, modified time, size, restore action, and selection checkbox. A select-all checkbox affects the currently listed backups. A **Delete selected backups** control shows the selected count and stays disabled while nothing is selected. Confirmation names the selected files and makes clear that deletion is permanent. On completion, the app reports the actual deletion count and any failures, clears stale selection, and reloads the list.

The server will expose an authenticated deletion endpoint. It will accept only distinct filenames currently returned by the managed backup listing, resolve them under the configured app data directory, and refuse symlinks or paths outside that directory. Recovery-package copies, snapshots, source archives, and the live database remain untouched.

## Acceptance checks

- Empty selection cannot call the deletion endpoint.
- Canceling confirmation leaves all files in place.
- Selected valid files are deleted; unselected files remain restorable.
- Invalid names, duplicate names, traversal, symlinks, and unrelated files cannot be deleted.
- The UI shows the result and refreshes after success or partial failure.
- Existing backup listing and restore behavior continues to work.

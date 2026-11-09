# Excel inspection workflows

Open **Data & backups → Export to Excel**. All generation runs locally using bundled Python and openpyxl; Microsoft Excel is not required to generate a workbook.

The full editable export runs in the background and shows its current stage and progress while it builds. The database lock is held only while it reads a consistent snapshot, so the rest of the app remains available during workbook generation.

## Full editable database

Select **Full Database Workbook**, then **Export Editable Database**. This complete mode includes archived assets, supported metadata, original source cell evidence, and business history. Keep an independent native recovery ZIP as well.

The workbook opens on **Master Plan**, followed by **Guide** and the original source tabs such as **Vessels & TKs**, **GP Piping**, and **FLs**. Each source tab has one row per asset. That row contains its asset fields, OSI/Internal schedule, technical details, notes and review items together. Edit the asset on its source tab; **Master Plan**, **Source Cells**, and **Field Map** are reference views. Dates use month precision: enter `YYYY-MM` text or an Excel date. Preserve unknown dates as blanks and numerical zero as zero.

Keep permanent and child IDs unchanged. They are stored in hidden identity columns. To add an asset, add a row inside its source tab's Excel Table and enter a unique `new:` label in **New asset ID**. Enter the asset fields and any inspection, note, review or technical details in that same row. Use the blank Note, Review and New technical slots to add child records. The reconciled workbook assigns permanent IDs after synchronization. Existing assets stay on their original source tab; missing rows never delete their app records.

Values longer than 28,000 characters use the separate **Long Text** sheet; this is the only editing case that leaves the asset row. Edit the matching chunks and keep their sheet, row key, field and contiguous part numbers unchanged. Editing or importing a record does not verify it; the app applies current quality rules after synchronization.

## Preview, resolve, and synchronize

Choose the edited workbook under **Synchronize an edited database workbook**, then **Preview Excel changes**. Review additions, field changes, invalid items, retained missing rows, and every conflict. Each conflict shows the original exported, Excel, and current application values. Choose **Keep Excel**, **Keep application**, or **Enter manual value** for each conflict.

Apply after resolving conflicts and validation errors. The application creates a safety backup and commits validated changes transactionally. Download and use the **reconciled workbook** for your next cycle: it contains assigned permanent IDs and a refreshed baseline. A missing row does not delete its database record; archive assets explicitly where appropriate. If the app changes after preview, preview again.

Only an issued full editable database workbook can synchronize with its originating database. Annual plans, filtered registers, management reports, and legacy cleaned workbooks use different workflows and are not complete synchronization artifacts.

## Excel business-data recovery

Choose a full editable workbook under **Recover from Excel**, then **Validate Excel recovery**. Review the asset, obligation, and evidence counts. Recovery builds and validates a temporary database before activation. Confirm replacement using the checkbox, then activate. The current database is backed up first; reload follows recovery to invalidate stale browser edits.

Excel recovery preserves supported business records, permanent IDs, nested relationships, technical values, notes, review states, and retained evidence/history. It differs from a native recovery ZIP: machine backup configuration and the original binary source workbook files are not reconstructed from Excel. Keep native ZIP recovery packages independently for complete file recovery.

## Standalone annual plans and reports

Select **Yearly Inspection Plan**, choose a planning year independently of the dashboard, and optionally filter actual area/location, asset family, source sheet, inspection type, or tag/equipment description. Set a reporting reference month and choose whether to include separate overdue and unresolved sections, a monthly summary, or January–December worksheets. Click **Export Yearly Plan**.

The report includes an annual overview, inspection obligations, monthly counts, scope and planning notes, and selected optional sections. Prior-year overdue obligations remain separate from the selected year's monthly schedule. OSI and Internal obligations count separately. Overdue begins after the due month ends; unknown dates remain undated. Reports follow application applicability, archive, and current derived review rules.

**Filtered Asset Register** and **Management Summary** are also dated report snapshots. Manual report annotations are not authoritative database edits and cannot be synchronized or used to recover the full database.

## Compatibility and verification boundary

Microsoft Excel for Mac 16.113.1 opened a one-asset disposable source-tab workbook without repair. Its original area tab, grouped headings, table filters and same-row fields were visible. The sample avoided the slow full database export, so full-scale export time and behavior were not measured. Native Windows execution and Windows Excel remain unverified. Workbooks contain no VBA, external service dependency, Excel COM integration, or executable imported formulas.

Unmodified numbers are compared at Excel’s 15-significant-digit precision; exact original database numbers remain stored when Excel only rounds serialization tails. Changes below Excel’s numeric precision cannot be represented reliably in an Excel cell.

Continue edits in the reconciled workbook after every synchronization. Edited `new:` rows in an already-imported stale workbook are blocked with an explanation, so their changes are not silently discarded. Identical legacy notes/review items lacking permanent IDs must first be distinguished in the app and re-exported before ambiguous offline edits can be matched safely. Existing inspection obligations without IDs receive stable type-based workbook identities that persist when edits are applied.

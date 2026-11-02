# Task state — 2 November 2026

## Current goal

Continue improving the local inspection app so it can import a complicated workbook, help its single operator clean and verify records efficiently, and maintain a reliable master register and inspection schedule.

## User decisions

- The master register and inspection schedule are the primary uses.
- One operator will clean, verify, and maintain the database on one computer.
- Verified corrections win over conflicting later imports; incoming differences are flagged.
- Assets with unresolved issues remain visible in the master with warnings, but blocking issues exclude them from trusted snapshots.
- An asset without a tag/asset number can qualify after explicit identity verification.
- Trusted snapshots include eligible verified assets and prominently list excluded assets with reasons.
- Applicable inspections need a month or an explicitly verified scheduling condition. Such conditions need a review-by month; when overdue, warn but retain eligibility.
- Reverify only fields changed by later edits/imports; preserve verification of unchanged fields.
- For trust, require description, family, identifiable location/context, record status, and checked inspection applicability, plus explicit asset verification and no blocking checks.
- First import support: currently supported original workbook layouts and app exports. Target scale: 10,000 assets.
- Backups should be automatic locally with an automatic copy to a user-chosen folder. Selective backup deletion was approved.
- Reduce verification workload through batch sign-off only after a full preview of the exact assets and required fields.
- Month entry should be one combined type-or-pick field, `YYYY-MM`, with a month/year picker and no day grid or separate month/year inputs.

## Implemented in this checkout

The candidate includes the broader import, reconciliation, data-quality, verification, snapshot, backup/recovery, usability, theme, and performance work recorded in [reliable-database-acceptance.md](reliable-database-acceptance.md). The latest UI increment implements the combined month input and twelve-month picker for inspection months, scheduling-condition review-by months, and the dashboard custom through-month filter. The source file remains unchanged during acceptance profiling; owner decisions about ambiguous source rows are still outstanding.

## Latest verification recorded

- JavaScript: 66 tests passed.
- Python: 146 tests, one sandbox socket test skipped.
- `node --check static/app.js` and `git diff --check` passed.
- Month picker has automated interaction coverage. A live visual walkthrough and full keyboard/screen-reader accessibility acceptance have not been completed.
- Workbook import/recovery acceptance was exercised with disposable data; it is not owner sign-off of the engineering content.

See [reliable-database-acceptance.md](reliable-database-acceptance.md) for workbook findings, test details, limitations, rollout precautions, and remaining gates.

## Remaining work

1. Owner reviews the eight ambiguous identity pairs and 28 unclassified workbook rows against source evidence; resolve intended asset identities/content explicitly.
2. Walk through import, cleanup, batch verification, trusted snapshot, and recovery without coaching; fix usability issues found.
3. Check keyboard and screen-reader operation, contrast, zoom/reflow, and target sizes across the app.
4. Exercise packaged launchers on native macOS and Windows, including downloads/printing and unavailable, full, or read-only backup destinations.
5. Extend interruption and disk-failure testing, then review the complete mixed working tree before any integration or rollout.

## Safety and scope

Preserve the mixed uncommitted working tree. Do not reset, clean, stage, or commit as part of continuing this task. Treat operational databases, backups, recovery packages, and source workbooks as user data; use disposable copies for development and acceptance. Importing and editing are not verification, and the app must not claim engineering or regulatory certification. No operational migration, deployment, or merge has been performed.

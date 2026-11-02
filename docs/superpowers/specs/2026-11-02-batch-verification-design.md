# Batch verification for the master register

## Intent

Make owner verification practical for a large single-user register without weakening the trusted-snapshot rule. The owner can verify a reviewed group of assets in one deliberate, evidence-backed action instead of opening each asset separately.

## Goals

- Select assets from the existing master-register selection workflow, including selections spanning pages.
- Preview every selected asset, its source location, the current value of each exact required field that will be verified, and any open blocking issues.
- Require an explicit owner confirmation and a written evidence reference or engineering rationale before saving.
- Keep verification tied to each field's current fingerprint. A later change invalidates only that changed field.
- Preserve the existing rule that unresolved blocking issues exclude assets from trusted snapshots; batch verification does not dismiss or resolve issues.
- Keep the import and source workbook unchanged. Import alone never creates verification records.

## Non-goals

- Automatically approve imported data, infer corrections, or resolve duplicate identities.
- Change which fields and checks are required for snapshot eligibility in this change.
- Replace individual verification for exceptional or ambiguous records.

## Approaches considered

1. **Reviewed batch sign-off (recommended and selected):** select assets, preview every asset and required field, enter a source/evidence reference, and explicitly verify the displayed scope. This reduces repetitive navigation while retaining an auditable owner action and exact field-level records.
2. Keep verification one asset at a time. This is safe but scales poorly and is the current problem.
3. Automatically verify records from an imported workbook. This removes clicks but would claim owner review that did not occur, so it is rejected.

## Design details

- Add a **Verify selected** action alongside existing register bulk actions.
- Preview uses the selected asset IDs and current versions. It lists every asset (name, ID, source sheet/row), every currently required field with its current value, and open blockers. No rows are hidden by current page filters after selection.
- The owner supplies one evidence reference/rationale that applies to the displayed group and confirms that they reviewed the listed fields for those assets.
- On apply, the server rechecks asset versions and required fields in one transaction, creates per-asset/per-field fingerprinted verification records and audit events, and takes one automatic backup before the operation. A stale preview is refused and must be refreshed.
- Assets with unresolved blockers may have their reviewed fields recorded, but they remain excluded until blockers are separately resolved. The result reports verified, still-excluded, and blocker counts.
- Single-asset verification remains available for exceptions and subsequent corrections.

## Acceptance checks

- A selected multi-page group can be previewed and verified with one source-backed confirmation.
- The preview includes all and only selected assets, and every required field for each asset is visible.
- Missing evidence, empty scope, stale versions, and altered selections cannot be applied.
- Verification fingerprints remain field-specific; changed fields lose verification while unchanged fields remain verified.
- Batch verification does not resolve blockers or make blocked assets eligible.
- Importing a workbook without an owner action still creates no verification records.

## Builder decisions

Use the existing register selection state, audit journal, backup path, and required-field calculation. Keep confirmation in a dedicated dialog, with grouped counts plus a searchable complete asset/field list so large previews remain usable.

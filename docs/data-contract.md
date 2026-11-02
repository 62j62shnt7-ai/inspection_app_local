# Master register data contract

The application maintains asset identities and month-level inspection schedules. It does not certify equipment safety, inspection completion or regulatory compliance.

## Existing interchange

The seven existing linked sheets remain supported: Assets, Inspection Plan, Technical Details, Notes & Actions, Review Items, Source Cells and Field Map. Import Decisions is optional. Original-layout mappings remain in `inspection_app/legacy_layouts.json`; header validation and source sheet selection remain authoritative. Permanent asset IDs are never regenerated because source rows move. Package membership alone is insufficient identity evidence.

Assets preserve description/name, family, original tag and asset number, Oracle description, field, plant, locations, unit, raw service status, record status, source sequence, pack, parent/source groups, source sheet and row. Blank raw fields remain blank; unknown is not equivalent to not applicable. Raw service text is retained without inferring operating safety. Canonical record status is Active or Archived.

Inspection rows preserve IDs, type (OSI/Internal), explicit Yes/No applicability, last and next months, last status, scheduling condition, review status/reason, original last/next values and category, source sheet/row/cells. Month precision is YYYY-MM; a real source day is checked before reducing precision. No day is invented. Internal applicability requires a recognized tank/vessel family or review of classification. Next preceding last generates review, not an automatic correction.

Technical details preserve field ID/label, value, explicit unit, original value and source coordinates. No unit conversions are inferred. Notes preserve ID, type, full text and source. Review rows preserve original values, reason, status and provenance. Source cells preserve value, Excel type, annotation, row role and coordinates. Field Map preserves each extraction destination and preservation policy. Original source files are immutable evidence. Formula text and missing cached values must remain distinguishable.

## Trust

Required trusted fields: description, family, location/context, record status and explicitly checked inspection applicability. Applicable inspections require a next month or explicitly verified scheduling condition with review-by month. A missing tag is allowed with explicit identity verification. An overdue condition review is a warning, not a snapshot blocker.

Verification binds to field content, owner action, UTC time and evidence/rationale. Changes invalidate only affected fields. Passing rules never verifies an asset. Incoming differences preserve verified values and require review. Blocking issues keep assets visible in the master but exclude them from trusted snapshots; every exclusion and reason is published. Optional unknown enrichment does not by itself block trust.

Issue lifecycle: open, resolved, accepted_exception, superseded. Resolutions are checked against the relevant content fingerprint. Correction history is distinct from inspection history. Edit tokens are never reused after removal/reimport/restore. Transactions include their correction events.

## Synthetic acceptance inventory

Use disposable fixtures for duplicate tags with conflicting location, legitimate similar descriptions at different locations, reused package identifiers, missing names, moved source rows, invalid calendar dates, month-only dates, inverted chronology, multiline/formula-like notes and missing formula caches. Expected outcomes are explicit review or rejection without source loss, never inferred identity or engineering corrections. Operational workbooks must not be copied into test fixtures or edited by tests.

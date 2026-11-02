# Master register data contract

The application maintains asset identities and month-level inspection schedules. It does not certify equipment safety, inspection completion or regulatory compliance.

## Existing interchange

The seven existing linked sheets remain supported: Assets, Inspection Plan, Technical Details, Notes & Actions, Review Items, Source Cells and Field Map. Import Decisions is optional. Original-layout mappings remain in `inspection_app/legacy_layouts.json`; header validation and source sheet selection remain authoritative. Permanent asset IDs are never regenerated because source rows move. Package membership alone is insufficient identity evidence.

Assets preserve description/name, family, original tag and asset number, Oracle description, field, plant, locations, unit, raw service status, record status, source sequence, pack, parent/source groups, source sheet and row. Blank raw fields remain blank; unknown is not equivalent to not applicable. Raw service text is retained without inferring operating safety. Canonical record status is Active or Archived.

Inspection rows preserve IDs, type (OSI/Internal), explicit Yes/No applicability, last and next months, last status, scheduling condition, review status/reason, original last/next values and category, source sheet/row/cells. Month precision is YYYY-MM; a real source day is checked before reducing precision. No day is invented. Internal applicability requires a recognized tank/vessel family or review of classification. Next preceding last generates review, not an automatic correction.

Technical details preserve field ID/label, value, explicit unit, original value and source coordinates. No unit conversions are inferred. Notes preserve ID, type, full text and source. Review rows preserve original values, reason, status and provenance. Source cells preserve value, Excel type, annotation, row role and coordinates. Field Map preserves each extraction destination and preservation policy. Original source files are immutable evidence. Formula text and missing cached values must remain distinguishable.

## Trust

Snapshot eligibility uses automatic quality criteria (rules version 2), not mandatory manual verification. A name, recognized family, record status, inspection plan and explicit applicability are required. An applicable inspection needs a valid next month or a recorded scheduling condition; no review-by month is required. Missing location and identifiers do not themselves block inclusion. Blank or Never last-inspection dates pass; ambiguous/invalid dates, next-before-last chronology, duplicate identifiers and incompatible internal inspections require checking. Overdue work remains visible as overdue, not as a data conflict. Imported placeholder Undated is not a scheduling condition.

Historical import date flags are retained as evidence but superseded by current rule results. Independent source concerns and incoming differences retain their review workflow. Missing/damaged archived workbooks and formula-cache issues are warnings, not snapshot blockers. A recorded overdue condition-review month remains an informational warning. Open blocking issues exclude an asset; all exclusions, warnings and accepted exceptions are published. New manifests record `eligibility_basis: automatic_quality_checks` and `rules_version`; existing saved manifests are unchanged.

Manual verification is optional and distinct from Passed checks. It binds field content to an owner action, UTC time and evidence/rationale; changes invalidate only affected fields. Automatic eligibility never writes verification evidence or claims engineering certification. Incoming differences continue to preserve manually verified values and require review.

Issue lifecycle: open, resolved, accepted_exception, superseded. Resolutions are checked against the relevant content fingerprint. Correction history is distinct from inspection history. Edit tokens are never reused after removal/reimport/restore. Transactions include their correction events.

## Synthetic acceptance inventory

Use disposable fixtures for duplicate tags with conflicting location, legitimate similar descriptions at different locations, reused package identifiers, missing names, moved source rows, invalid calendar dates, month-only dates, inverted chronology, multiline/formula-like notes and missing formula caches. Expected outcomes are explicit review or rejection without source loss, never inferred identity or engineering corrections. Operational workbooks must not be copied into test fixtures or edited by tests.

# Old feature migration notes

The old and local apps use different storage, identifiers and date precision. Work in the repository only. Preserve local database, permanent IDs, month precision, source provenance, import preview, backup and export/re-import behavior. Do not add day-specific aging or claim statutory calculations from month-only values.

Known scope rule: internal inspections apply to tanks and vessels, not piping and lines. The remaining deliberate exclusions are not recorded in the repository and need clarification before implementing features that depend on new fields or modules.

## Independent first step

Bring source-sheet and OSI/internal filters to the existing yearly plan. Derive both the displayed rows and CSV from the same filtered list. Keep archived, not-applicable and review-pending inspection exclusions. Use the existing month and asset data; do not introduce new fields. Add a regression test for filtering and verify the existing tests.

## Dependencies for the remaining inventory

- History, bulk logging, audit and campaign synchronization require persistent event records, explicit update/undo rules and tested full-workbook/backup round trips. Current editable inspection schedule fields do not constitute history.
- RBI, CUI, deferrals and engineering calculations require data fields and business rules absent from the current schema. Do not infer them from display values or invent precise dates.
- Campaign reconciliation, temporary repairs and turnaround require new datasets, stable links and import/export mapping. Their eligibility depends on the user's exclusions.
- Overdue aging by days cannot be reconstructed accurately from year-month values; an alternative month-based display needs explicit labeling.
- Registry filtering, grouping and pagination can be built using existing local fields, without restoring excluded fields.

## Confirmed exclusions and delivered work

User excluded RBI, CUI, inspection history, temporary repairs, turnaround tracking, campaign reconciliation and deferrals. Internal inspection applicability remains limited to tanks and vessels. Inspection-history implementation was removed with the user's approval; no inspection-history records existed in the local database at that time.

Implemented using existing local data: source/type and carry-over filtering on yearly plans; filtered yearly CSV and XLSX; grouped register by source, plant, field, pack or location; asset selection and selected CSV; multi-token/abbreviation search; page size and pagination; overdue ranges by calendar months rather than inferred days. These are repository changes and do not migrate the old database.

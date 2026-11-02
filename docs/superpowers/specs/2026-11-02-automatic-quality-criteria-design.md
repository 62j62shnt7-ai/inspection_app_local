# Automatic data-quality criteria

## Intent and agreed behavior

Replace mandatory manual verification for snapshot eligibility with automatic checks against the criteria agreed with the owner on 2026-11-02. Manual verification remains available and retains its field-level evidence and protections. An automatic result is called **Passed checks**, never manually verified.

An entry with no open blocking findings qualifies for a trusted snapshot without manual verification. Warnings remain visible and are saved in the snapshot manifest without excluding the entry. Passing checks is not an engineering or regulatory certification.

## Criteria approved question by question

| Condition | Result |
| --- | --- |
| Valid next inspection month, not earlier than a recorded valid last inspection month | Pass schedule check, including when overdue |
| Last inspection is blank or says “Never”, with a valid next month | Pass |
| No next month, but a recorded scheduling condition such as At next shutdown, Awaiting evaluation, or OOS | Pass; no review-by month required |
| Applicable inspection has neither a next month nor a scheduling condition | Flag for checking |
| Missing location, with an asset name or identifier | Pass location check |
| Multiple assets share a tag or asset number | Flag for identity checking; never merge automatically |
| Missing asset name, even if an identifier exists | Flag |
| Missing or unrecognized asset family | Flag |
| Invalid or ambiguous inspection date | Flag, except the agreed blank-last-date, Never, and recognized scheduling-condition cases |
| Missing inspection plan or explicit applicability decision | Flag |
| Historical import review flag whose current record meets these criteria | Retain source evidence; do not treat the historical flag itself as a current issue |
| Internal inspection assigned to piping or line equipment | Flag |
| Missing or damaged archived source workbook | Separate source-evidence warning; does not block an otherwise passing entry |

## Implementation choices

Use the existing validation and quality engine as the single policy source for Data quality, register summaries, dashboard review status, and snapshot eligibility. A second policy engine would risk different counts and decisions across screens; blanket verification would misrepresent unchecked evidence. No new policy configuration screen or automatic field-verification records are needed.

Derive current findings without changing imported values, review items, original workbook evidence, or past snapshot manifests. Keep unresolved incoming differences and evidenced identity decisions subject to their existing review protections. Do not invent applicability, dates, identities, or engineering conclusions.

Builder choices: distinguish date-like ambiguous text from recorded conditions using the existing import/month parsing conventions; preserve unknown or independent concerns for checking. A dated overdue inspection stays in its overdue work queue, while a condition-only schedule can remain visible as scheduled by condition without being presented as a data-quality conflict. Version the criteria in new snapshot manifests so historic snapshots remain interpretable.

## Scope and validation

Update validation, readiness and snapshot metadata, summary review derivation, and UI wording to distinguish Passed checks, Needs checking, warnings, and optional manual verification. Preserve existing uncommitted changes and local-only macOS/Windows compatibility.

Test the agreed criteria individually, date/condition exceptions and ambiguity, stale import flags, missing applicability, duplicate identities, retained manual verification and incoming differences, and automatic snapshot inclusion with warnings. Use disposable databases for round trips and a live browser check of counts and eligibility. Do not alter the operational database during development. Native Windows and owner acceptance remain unverified unless separately tested.

# Automatic quality criteria implementation plan

> Execute inline with superpowers:executing-plans and test-driven development; request one focused review at the end.

**Goal:** Automatically include records meeting the owner-approved criteria without implying manual verification.
**Architecture:** Existing validation generates current findings; readiness uses open blockers only. Register and dashboard use the same findings instead of historical import flags. Retain immutable evidence and prior snapshots.
**Tech stack:** Python/SQLite, vanilla JavaScript, unittest and Node tests.
**Spec:** docs/superpowers/specs/2026-11-02-automatic-quality-criteria-design.md

## Constraints and rulings
- Reuse current codex/reliable-master-database checkout; preserve all preexisting dirty work. Do not commit unrelated work or modify operational data.
- Ruling: approved design authorizes inline execution; no additional workflow approval needed.
- Ruling: ambiguous date-like text and unknown historical concerns stay flagged. Recognized conditions and blank/Never historical dates pass; importer placeholder Undated is not a scheduling condition.
- Keep manual verification protections, incoming differences and audit evidence. Source archive defects become nonblocking warnings. Existing dated review-by warnings may remain informational.

## Review focus
- Placeholder dates and arbitrary text must not become automatic passes.
- Corrected current dates must supersede historical date flags without losing source evidence.
- Dashboard queues and register filters must agree on condition-only schedules.
- Old accepted exceptions and changed evidence must retain fingerprint protections.
- Snapshot publication/export/reimport must preserve policy identity and manual verification semantics.

## Task 1: Validation and readiness
- [x] Add failing tests for all agreed pass/flag cases, automatic readiness and warnings.
- [x] Implement current validation in inspection_app/validation.py; retain original evidence and generic independent review concerns.
- [x] Update inspection_app/quality.py to use open blockers for readiness, keep optional manual verification, version policy metadata and source archive warning severity.
- [x] Run focused Python tests; update old tests whose policy expectations intentionally changed, retaining their original audit/staleness coverage.

## Task 2: Consistent summaries and interface
- [x] Add failing summary and frontend tests for stale flags, ambiguous evidence, condition schedules, and automatic eligibility labels.
- [x] Update inspection_app/register.py and static/app.js to derive attention from current findings and separate condition schedules.
- [x] Update static/quality.js and static/index.html to say Passed checks and explain optional manual verification; document criteria and snapshot semantics.
- [x] Run focused Python/Node tests.

## Task 3: Verification
- [x] Run complete Python and Node suites and diff checks.
- [x] Exercise dashboard, data quality, and snapshot flow in a live browser with disposable records.
- [x] Request focused independent review, resolve material findings, report evidence and remaining platform limits.


## Completion evidence

- 168 Python unittest tests and 75 Node tests passed; diff whitespace check passed.
- Disposable current-database copy: 1,066 assets, 948 eligible, 118 excluded, 148 open findings (97 ambiguous dates, 25 missing schedules, 19 chronology, 6 identifier collisions, 1 missing name).
- Live disposable browser: overdue and OOS records passed without manual verification; ambiguous-date and unknown-family records needed checking. Valid overdue dates remained in schedule queues. Register displayed Passed checks / Needs checking per entry.
- Live snapshot saved with two included and two excluded examples, rules version 2, automatic_quality_checks eligibility basis and zero manual-verification records.
- Independent focused review found two summary consistency gaps (asset-level blockers and technical-field incoming fingerprints); both received failing regression tests and fixes. Final review reported no remaining material findings.
- Source operational database was opened read-only for a SQLite backup into a disposable directory; all validation writes and browser activity used disposable databases. No operational data, existing snapshots or manual verification evidence was changed.
- Ruling: optional core manual-review fields remain in the verification dialog and bulk workflow; they no longer gate snapshot inclusion. Existing source-review exception decisions and protections against incoming differences remain available.
- Native Windows and owner acceptance remain unverified. The owner subsequently requested documentation updates and a commit of the combined quality/UI candidate. No merge or push is included.

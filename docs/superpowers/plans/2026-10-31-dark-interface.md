# Dark Interface Implementation Plan

**Goal:** Deliver the approved dark frontend without adding fields.
**Architecture:** Retain existing IDs, API calls and data structures; replace presentation and group existing editor fields into tabs.
**Tech Stack:** Native HTML, CSS, JavaScript, Python unittest.
**Spec:** ../specs/2026-10-31-dark-interface-design.md

## Constraints
No schema changes or disabled fields restored. No external font or runtime dependency.

## Tasks
- [x] Restyle shell, dashboard, tables, import and print views with responsive dark tokens.
- [x] Add dashboard queue sections, status badges, register source shortcuts and reset action using existing filters.
- [x] Add keyboard accessible editor tabs; preserve all current fields and dirty-state protection.
- [x] Verify JavaScript syntax, existing Python suite and browser interactions where available.

## Review focus
Empty data, mixed inspection statuses, unsaved tab edits, mobile overflow, print contrast.

## Verification results
JavaScript syntax check passed. Python unittest: 18 tests, OK, one skip. Browser verified empty and populated dashboard/register, dashboard filter navigation, reset filters, create/save/reopen, tab value retention and arrow-key navigation against a temporary database. Narrow desktop layout visually inspected. No production database changes. Print stylesheet reviewed; physical print and Windows execution not tested.

## Second pass after user review
- Adapted compact cyan styling and asset drawer more closely to original app; added current active totals, counted scrollable sheet tabs, bounded dashboard queues and asset context.
- Source-sheet selection resets conflicting filters and pagination; empty Manual tab omitted. Browser checked all ten source sheets against 1,061 active assets in a copy of the 1,066-record database.
- Editor section ownership is explicit; newly added Internal groups participate when tabs are rebuilt.
- Blank new technical/remark drafts excluded at save; technical values require labels. Empty-state messages removed on adding entries. Existing imported records preserved.
- One unnamed source record now displays existing Oracle description Sep-204 with missing-name/source-row context. Stored name unchanged.
- Regression checks: four frontend Node tests pass; JavaScript syntax and git diff whitespace checks pass. Python suite 18 tests, OK, one skip. Browser verified populated source switching and missing-name display, plus mobile drawer geometry. No production data written.

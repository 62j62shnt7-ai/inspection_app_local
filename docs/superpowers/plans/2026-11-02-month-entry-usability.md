# Month Entry Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make month-only inspection date entry predictable with one field that combines `YYYY-MM` typing and a month-grid picker.

**Architecture:** Keep `YYYY-MM` as the stored value and implement a shared text input with an integrated picker button and nonmodal month-grid popup. Do not add dependencies, separate month/year inputs, or a blocking day calendar.

**Tech Stack:** Existing browser JavaScript, HTML/CSS, and Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-02-month-entry-usability-design.md`

## Global Constraints

- Store inspection timing at month precision as `YYYY-MM`.
- Do not infer dates or change inspection applicability or engineering rules.
- Preserve source evidence, verification behavior, editor drafts, and existing save semantics.
- Avoid adding dependencies and avoid a blocking date modal.

## Review Focus

- Blank month remains blank and is not silently converted to a date.
- The input is one `YYYY-MM` text box with an attached picker button; there are no separate month/year inputs.
- The popup shows 12 month buttons under a year header and contains no day numbers.
- Typing or picking updates the same value used by editor state and draft persistence.
- Blank stays blank and is not converted to a default month.
- Escape and outside click dismiss the popup; month buttons support keyboard navigation.
- Last/next/review-by month fields and custom dashboard month filtering use consistent, accurate labels.

### Task 1: Shared month entry field

**Files:**
- Modify: `static/app.js`
- Modify: `static/style.css`
- Modify: `static/index.html` only if shared hints or helper containers are required
- Test: `tests/frontend.test.cjs`

**Interfaces:**
- Replace the date/month branch of `field(parent, label, value, onchange, multiline)` with a shared month field renderer.
- The renderer accepts the existing canonical value and `onchange` callback, exposes one text input and an integrated picker popup, and reports valid `YYYY-MM` or `null` through the existing callback.

- [x] Add frontend tests for direct typing, popup visibility, year navigation, all month choices, blank value, and draft callback behavior; confirm failures before production edits.
- [x] Implement one text input with a calendar button and a year/month-grid popup, with inline validation.
- [x] Use the shared control for inspection last/next/review-by months and the dashboard custom end month.
- [x] Add responsive and theme-aware styles for the field and hint.
- [x] Run focused frontend tests, the complete JavaScript suite, Python suite, syntax checks, and `git diff --check`.
- [x] The inline instructions make the interaction self-explanatory; README changes were not needed.

## Delivery note

Preserve the existing mixed working tree. Do not stage or commit unrelated files. Owner usability observation and full accessibility acceptance remain release gates after implementation.

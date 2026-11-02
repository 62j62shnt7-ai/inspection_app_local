# UI review cues and input usability implementation plan

**Scope note:** This UI work preserved the eligibility rules in effect when designed. The subsequent owner-approved [automatic quality criteria](../specs/2026-11-02-automatic-quality-criteria-design.md) supersede that policy; current UI wording distinguishes automatic checks from optional manual verification. The original UI-only constraints below describe this plan's scope, not a prohibition on the later approved policy change.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make changes, review needs, and saved verification states easier to scan while making supported input types more obvious and usable.

**Architecture:** Keep the current editor, quality list, and browser JavaScript architecture. Reuse field-level status classes and server-provided verification/issue data; add accessible text labels and theme-aware styles without changing saved data or engineering rules.

**Tech Stack:** Existing HTML, CSS, JavaScript, Node tests, Python unittest suite.

**Spec:** `docs/superpowers/specs/2026-11-02-ui-review-and-inputs-design.md`

## Global Constraints

- Do not change import matching, validation meaning, verification rules, persistence format, or snapshot eligibility.
- Do not treat editing or visual highlighting as verification.
- Do not infer engineering values or force closed choices where source values vary.
- Keep local operation and current browser stack; add no dependencies.

## Review Focus

- Verified fields must be shown as verified only for current saved values; test a changed value loses the verified cue under existing server behavior.
- Review and changed cues must include readable labels and not rely on color; test in both themes.
- Blank and malformed month values must retain current semantics and inline correction behavior.
- Identifier and technical values may contain letters and punctuation; tests must ensure they are not restricted by numeric controls.
- Issue severity and action must stay distinct for warnings and blockers; test both issue classes.

## File responsibilities

- `static/app.js`: asset editor field construction, reconciliation highlights, issue context, supported control semantics.
- `static/quality.js`: issue severity/action rows and verification UI state cues.
- `static/style.css`: shared status treatments in light/dark themes and responsive layouts.
- `tests/frontend.test.cjs`: editor field types, review/change cues, labels and validation behavior.
- `tests/quality.test.cjs`: quality issue severity/action and verification state cues.

### Task 1: Shared asset editor field status cues

**Files:**
- Modify: `static/app.js`
- Modify: `static/style.css`
- Test: `tests/frontend.test.cjs`

**Interfaces:**
- Preserve `field(parent, label, value, onchange, multiline)` behavior and its existing callbacks.
- Add an optional status decoration path for changed, review-needed, or verified saved values; status must not modify the stored value.

- [x] Add failing frontend tests for changed/review/verified/neutral states, asserting visible text as well as classes.
- [x] Run the focused tests and confirm the new state assertions fail.
- [x] Implement shared field status labels and accessible status attributes, preserving draft persistence and the existing reconciliation callbacks.
- [x] Add tests for alphanumeric asset identifiers and month picker preservation; status text is exposed to assistive technology.
- [x] Run `node --test tests/frontend.test.cjs` and confirm the focused suite passes.

### Task 2: Quality issue and verification cues

**Files:**
- Modify: `static/quality.js`
- Modify: `static/style.css`
- Test: `tests/quality.test.cjs`

**Interfaces:**
- Continue consuming the existing quality issue and `/api/verification/:asset_id` response shapes.
- Keep resolution and verification actions unchanged; expose current state in text and presentation only.

- [x] Add failing tests for warning versus blocking labels and actionable issue rows.
- [x] Run the focused tests and confirm the new assertions fail.
- [x] Implement consistent status badges and direct actions, with the existing label, severity, and explanation available without color.
- [x] Keep existing empty-list and excluded-reason behavior intact.
- [x] Run `node --test tests/quality.test.cjs` and confirm the focused suite passes.

### Task 3: Appropriate controls and full regression check

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html` only if a control currently lacks its semantic input type
- Modify: `static/style.css`
- Test: `tests/frontend.test.cjs`, `tests/quality.test.cjs`

**Interfaces:**
- Keep open-ended asset identifiers and engineering values as text; use semantic search, month, choice, and numeric controls only where the app already defines those meanings.
- Preserve save validation and `YYYY-MM` persistence.

- [x] Add tests for search filters, numeric year fields, existing choices/month entry, and free-text identifiers.
- [x] Run focused tests and confirm the new search semantics assertions fail before markup updates.
- [x] Set search controls to `type="search"`; keep year fields numeric and engineering identifiers free text.
- [x] Run `node --test tests/*.test.cjs`, `python3 -m unittest discover -s tests`, syntax checks for the changed scripts, and `git diff --check`.
- [ ] Inspect light/dark and narrow layouts in a browser with disposable data; live visual/accessibility acceptance remains outstanding.

## Review Focus mapping

- Current-value verification invalidation: Tasks 1 and 2.
- Non-color labels in both themes: Tasks 1 and 2.
- Blank/malformed months: Tasks 1 and 3.
- Alphanumeric/free-text safety: Tasks 1 and 3.
- Warning/blocker distinctions: Task 2.

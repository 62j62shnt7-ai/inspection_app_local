# Local Inspection UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Give the local Master Inspection Plan a cohesive, responsive interface while preserving all existing workflows and API behavior.

**Architecture:** Keep the current static HTML, CSS, and JavaScript and the Python server. Reshape the shared app shell in `static/index.html`, add a final, scoped responsive style layer in `static/style.css`, and only adjust JavaScript if accessible navigation state needs it. Preserve section IDs and every control ID consumed by the existing scripts.

**Tech Stack:** Existing HTML, CSS, browser JavaScript, Python unittest suite, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-11-03-local-inspection-ui-redesign-design.md`

## Global Constraints

- Keep the app local-only; do not register, publish, or deploy a hosted Site.
- Preserve Python APIs, storage schema, import matching, quality rules, verification meaning, audit history, snapshot eligibility, and backup/recovery behavior.
- Keep the existing browser stack and avoid new dependencies unless an implementation need is demonstrated.
- Preserve current operational data and uncommitted user changes.
- Keep `main > section`, `data-view`, section IDs, and IDs used by `static/app.js`, `quality.js`, `reconciliation.js`, and `cleanup.js` working.
- Keep field-level status cues understandable without color alone; maintain visible keyboard focus.

## Review Focus

- A user can reach each of the six views at desktop and mobile widths; test that each `data-view` still selects its matching top-level section.
- Moving shared header controls does not break theme switching or backup creation; test both controls after the shell change.
- Narrow screens do not hide critical navigation, action buttons, filters, or dialog controls; check at 375px and 768px widths.
- The editor remains keyboard navigable with visible focus and its sticky save actions remain reachable; check open, tab navigation, and save controls.
- Print output remains legible after changing the app shell; inspect a yearly plan print preview.

---

### Task 1: Reshape the shared application shell

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Test: `tests/frontend.test.cjs`

**Interfaces:**
- Consumes: existing `button[data-view]`, `main > section#<view>`, `#theme-toggle`, and `#backup` contracts.
- Produces: responsive shell with brand and primary navigation in an app rail and existing global actions in the top bar; all current controls retain their IDs.

- [x] **Step 1: Add a focused shell contract test**

Add a Node test that reads the real `static/index.html` and confirms `nav[aria-label="Main navigation"]` is inside `aside#app-rail`, each of the six navigation `data-view` values has one matching top-level section, and `#theme-toggle` and `#backup` remain present exactly once.

- [x] **Step 2: Run the focused test to verify it fails for the new shell contract**

Run: `node --test tests/frontend.test.cjs`
Expected: FAIL on the missing `aside#app-rail` relationship before implementation.

- [x] **Step 3: Move the navigation into the app rail in `static/index.html`**

Preserve the existing six buttons and their labels, icons, and `data-view` values. Keep the brand and local-workspace label visible. Keep `#theme-toggle` and `#backup` in a top bar, each exactly once. Leave the `main > section` hierarchy and all section/control IDs intact.

- [x] **Step 4: Add shell and responsive styles in `static/style.css`**

Use a wide-screen left rail and content column, a compact horizontal navigation on narrow screens, a clear active state, a sticky or consistently visible top bar, readable spacing, and the existing dark/light theme variables. Keep focus styling and `@media print` behavior effective.

- [x] **Step 5: Run the focused browser logic tests**

Run: `node --test tests/frontend.test.cjs`
Expected: PASS.

### Task 2: Improve the dashboard and register visual hierarchy

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Test: `tests/frontend.test.cjs`

**Interfaces:**
- Consumes: existing dashboard cards, `#dashboard-list`, `#aging-panel`, `#sheet-summary`, register filter controls, `#asset-rows`, and current event handlers.
- Produces: clearer headings, grouped overview/worklist surfaces, and more legible tables without changing record data or filtering behavior.

- [x] **Step 1: Add DOM contract assertions for high-use regions**

Extend the shell contract test to verify the dashboard worklist and register search/filter/table targets remain present exactly once.

- [x] **Step 2: Run the focused test to verify the added assertions pass against the unchanged content structure**

Run: `node --test tests/frontend.test.cjs`
Expected: PASS, establishing that the existing dynamic targets remain intact.

- [x] **Step 3: Refine dashboard and register markup only where hierarchy requires it**

Keep all current IDs and dynamic containers. Use wrappers and headings to clarify overview, work to review, and register search/filter sections. Preserve first-use guidance, source sheet shortcuts, and all filters/actions.

- [x] **Step 4: Style dashboard cards, action queues, filter disclosure, and tables**

Use consistent panel spacing, clear overdue/review cues with text labels, readable row spacing, and responsive table overflow. Do not alter colors or copy in ways that change quality, verification, or inspection meaning.

- [x] **Step 5: Run the focused browser logic tests**

Run: `node --test tests/frontend.test.cjs`
Expected: PASS.

### Task 3: Verify the preserved workflows and responsive shell

**Files:**
- Modify: `static/app.js` only if navigation state must be exposed accessibly.
- Test: `tests/frontend.test.cjs`, `tests/*.test.cjs`, and Python `tests/` suite as appropriate.

**Interfaces:**
- Consumes: the existing navigation and section contracts.
- Produces: validated navigation, theme, dashboard, register, editor, and print behavior with existing business logic unchanged.

- [x] **Step 1: Add or update the navigation interaction test if `static/app.js` changes**

Assert the selected button exposes the active view and the matching section is visible after navigation; keyboard activation must work for native buttons.

- [x] **Step 2: Run browser and Python suites**

Run: `node --test tests/*.test.cjs`
Run: `python3 -m unittest discover -s tests`
Expected: PASS. If a localhost socket test cannot bind, report that specific limitation.

- [x] **Step 3: Inspect the live local app with disposable data**

Check dashboard, register filters, opening and navigating the asset editor, theme switching, backup action, narrow layouts, keyboard focus, and yearly print output. Do not open or mutate the operational database.

- [x] **Step 4: Review the final diff**

Confirm only the approved design, its plan, intended frontend files, and focused tests changed; verify no API, storage, import, quality, or backup implementation changed.

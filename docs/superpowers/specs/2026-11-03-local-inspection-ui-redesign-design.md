# Local inspection app UI redesign

## Intent

Give the local Master Inspection Plan a cohesive, more usable interface while preserving the existing inspection and data-management behavior. The app serves one operator working across a large inspection register, resolving data issues, planning work, and maintaining reliable local records.

## Goals

- Replace the current visual shell with a clear responsive application layout and stronger navigation hierarchy.
- Make the dashboard's upcoming work, overdue inspections, and review queues easier to scan and open.
- Improve register search, filter discovery, table readability, and screen-width behavior.
- Make status, review, and verification cues legible without relying on color alone.
- Keep existing editor, import, reconciliation, quality, yearly planning, export, backup, recovery, and cleanup actions available.

## Non-goals and constraints

- Keep the app local-only. Do not register, publish, or deploy a hosted Site.
- Preserve the Python server/API, storage schema, import matching, quality rules, verification meaning, audit history, snapshot eligibility, and backup/recovery behavior.
- Keep the existing browser stack and avoid new dependencies unless an implementation need is demonstrated.
- Preserve all current operational data and uncommitted user changes.
- Do not infer engineering conclusions or imply regulatory certification.

## Approaches

1. **Refresh the existing screens in place:** lowest implementation risk, but keeps today's overall visual hierarchy and navigation limitations.
2. **Replace the visual shell while retaining current screen behavior (selected):** create a consistent responsive app frame and improve screen hierarchy while preserving existing view IDs, controls, event handlers, and API calls. This gives the app a coherent redesign without reimplementing its domain logic.
3. **Rebuild the frontend in a new framework:** offers a broader component-system rewrite, but adds dependencies and increases the risk of changing established data workflows without a clear need.

## Design direction

Use a calm, high-contrast operations interface: a persistent left navigation rail on wide screens, a compact navigation treatment on small screens, a clear active-view title, consistent panel spacing, readable tables, and restrained status colors. Preserve the existing dark theme and theme switch unless the implementation review shows it conflicts with usability. Reuse the existing dashboard and worklist content, but organize the primary next actions and overview metrics more clearly.

## Behavior and implementation boundaries

- Keep the established `main > section` view structure and `data-view` navigation contract, or provide compatibility shims if the shell changes their placement.
- Keep all current control IDs used by `static/app.js`, `quality.js`, `reconciliation.js`, and `cleanup.js` so existing workflows continue to bind to the same controls.
- Improve navigation and responsive layout with HTML/CSS changes first; make JavaScript changes only where required for accessible menu state or clearer navigation affordances.
- Preserve focused asset editing, drafts, month entry, status cues, confirmation dialogs, and current save semantics.
- Ensure keyboard focus is visible and every navigation item and status is understandable without color alone.

## Validation

- Run existing browser logic tests and the Python suite as applicable after implementation.
- Check the affected dashboard, register, editor, and navigation flows in a live local browser using disposable data.
- Inspect wide and narrow layouts and keyboard navigation.
- Confirm local startup and API-backed workflows still operate; do not use the operational database for verification.

## Approval status

Draft for user review. No implementation changes are authorized by this document until approved.

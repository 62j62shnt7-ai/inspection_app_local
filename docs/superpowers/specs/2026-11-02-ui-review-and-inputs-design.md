# UI review cues and input usability design

**Scope note:** This UI work preserved the eligibility rules in effect when designed. The subsequent owner-approved [automatic quality criteria](../specs/2026-11-02-automatic-quality-criteria-design.md) supersede that policy; current UI wording distinguishes automatic checks from optional manual verification. The original UI-only constraints below describe this plan's scope, not a prohibition on the later approved policy change.

## Intent

Help the single operator clean the master register efficiently by making field state and the next review action easy to recognize, while making entry controls fit the value being entered.

## Goals

- Apply consistent, readable cues for changed values, values needing review, and values verified for their current content in the asset editor and data-quality workflow.
- Make changed/review states understandable without color alone, including in light and dark themes.
- Use suitable controls and concise inline guidance for known value types (for example, search, numeric year, month, choice, and free text); preserve flexible text entry for fields whose valid values vary by source.
- Keep review items actionable and distinguish warnings from blockers.

## Non-goals and constraints

- Do not change import matching, validation meaning, verification rules, persistence format, or snapshot eligibility.
- Do not treat editing or visual highlighting as verification.
- Do not infer engineering values or force a closed choice list where source values are open-ended.
- Keep local operation and current browser stack; add no dependencies.

## Approaches considered

1. **Shared status cues and targeted controls (selected):** Extend the existing reconciliation field highlights into a consistent set of labeled cues, and specialize controls only where the data contract is clear. This addresses both scanning and entry without changing the editing flow.
2. **Guided multi-step editor:** Reorganize asset editing into a wizard. This offers stronger guidance but adds navigation and changes the established workflow more substantially.
3. **Quality/reconciliation lists only:** Improve review tables but leave editor fields unchanged. This is narrower, but does not help identify field-level changes while correcting records.

The selected approach is the smallest coherent improvement across both finding and fixing data.

## Behavior

- A field changed by reconciliation or currently requiring review has a text label and consistent visual treatment; unchanged fields remain visually quiet.
- Verified state is shown only when available from persisted field-level verification data and is removed or refreshed by existing server rules when the value changes.
- Issue rows identify severity and provide a direct action; the asset editor exposes relevant issue/review context near affected fields when the source data supports that link.
- Inputs retain current values and blank semantics. Validation explains the expected format at the field, preserves invalid text for correction, and prevents invalid submission only where the contract already defines a format/range.
- Controls remain keyboard accessible, theme aware, and usable at narrow widths.

## Acceptance

- Tests cover changed, review, and verified cues, including fields without a state and both themes.
- Tests cover specialized controls, valid/invalid input, blank values, and editor draft behavior.
- Data-quality issue rows expose severity and a clear action.
- Existing verification, import, and snapshot behavior remains unchanged.

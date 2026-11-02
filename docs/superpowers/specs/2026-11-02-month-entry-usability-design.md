# Month Entry Usability Design

## Intent

Make inspection-month editing quick and clear during repeated cleanup, while retaining the app's month-level date precision and preserving source evidence.

## Approaches considered

- Manual text entry only: fastest for keyboard users, but offers little help when the month is not already known in a familiar format.
- A blocking calendar modal: discoverable, but adds navigation for a value that has no day precision and can be slow when editing many records.
- **Approved: one combined text-and-picker field.** The `YYYY-MM` input has an attached calendar button; its popup shows a year header, year navigation, and a 12-month grid. Do not add separate month/year inputs or a day calendar.

## Behavior

- Keep storage in `YYYY-MM` and label the field as a month, not an exact date.
- Keep one text input with an integrated calendar button; typing and month selection update the same value.
- Show twelve month choices under a year heading with previous/next year controls. Do not display days.
- Keep the popup nonmodal, keyboard-operable, and dismissible by Escape or outside click.
- Keep an empty month distinct from a scheduling condition; do not invent a date.
- Validate typed values as `YYYY-MM`, preserve invalid text for correction, and leave the field blank when no value is supplied.
- Use the same month-field behavior for last inspection, next inspection, condition review-by, and dashboard custom-period fields where compatible.
- Preserve existing evidence, verification fingerprints, save, and draft behavior.

## Out of scope

- Exact-day inspection dates, automatic date inference, bulk date changes, or changes to engineering validation rules.
- Claiming accessibility compliance without the planned keyboard, screen-reader, contrast, zoom/reflow, and target-size acceptance.

## Acceptance

- A user can type or choose a month from the same field; the popup has a month grid and no day choices.
- Blank stays blank; malformed text receives field-level guidance and cannot be saved.
- Existing month parsing, scheduling, draft, verification, and save behavior remains intact.

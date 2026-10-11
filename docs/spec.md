# Spec: Button outline fails WCAG 1.4.11 non-text contrast (G#66/GH#117)

Minimal spec written by the orchestrator — this is a small, single-layer, already-precedented
color-token fix with no product/design decision to make, per the project's token-efficiency
convention (skip the full product-manager/ux-designer pass for mechanical, well-understood fixes).

## Problem

`Button._colors()` (`afk_clicker.py:2178-2190`) returns `LINE` as the outline color for both the
default/neutral state and the disabled state. `LINE` on `CARD` measures:

- dark: 1.58:1
- light: 1.43:1

Both fail WCAG 1.4.11's 3:1 non-text contrast minimum for a UI component boundary. This affects
every `Button` in the app (every dialog's Cancel/Save/Delete/Duplicate/Record, every macro-row
button, etc.) in both the neutral and disabled states.

## Precedent

`ToggleCheckbox` already solved this exact problem for its own outline — its docstring
(`afk_clicker.py:2356-2358`) states explicitly: *"CARD fill, MUTED outline (not LINE -- LINE fails
the WCAG 1.4.11 3:1 floor for a UI component here, MUTED clears it in both themes...)"*.

Verified: `MUTED` on `CARD` measures 5.76:1 (dark) and 6.23:1 (light) — clears 3:1 with margin in
both themes.

## Fix

In `Button._colors()`, replace the two `LINE` references with `MUTED`:

```python
def _colors(self, hover):
    if not self._enabled:
        return CARD, MUTED, MUTED          # was: CARD, LINE, MUTED
    if self.danger:
        ...
    if self.primary:
        ...
    return (CARD_HI if hover else CARD), MUTED, INK   # was: ..., LINE, INK
```

No other `Button` states (`danger`, `primary`) use `LINE` — they already use their own fill color
as outline, unaffected by this change.

## Non-goals

- Do not change `LINE`'s own value or any other `LINE` usage in the file (it's used deliberately
  as a faint decorative divider/non-component boundary elsewhere — e.g. `TabBar`'s underline
  divider, `Sidebar`'s panel dividers — which WCAG 1.4.11 does not apply to since those aren't UI
  component boundaries needed to identify the component).
- Do not touch `Segmented`, `NumBox`'s focus-ring wrap, or any other widget's own outline — scoped
  to `Button` only, matching the signed-off proposal.

## Acceptance criteria

1. `Button`'s neutral-state outline is `MUTED`, not `LINE`, in both themes.
2. `Button`'s disabled-state outline is `MUTED`, not `LINE`, in both themes.
3. A regression test asserts the computed WCAG contrast ratio of `Button`'s outline against `CARD`
   is ≥ 3:1 in both `THEMES["dark"]` and `THEMES["light"]` (not just a hex-equality check — the
   point is to catch a *future* palette change that reintroduces the failure, not just this one).
4. No visual/behavioral change to `danger`/`primary` button states, hover states, or any other
   widget.
5. Full suite still green (no regression).

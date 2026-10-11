# Implementation: Button outline fails WCAG 1.4.11 non-text contrast (G#66/GH#117)

## Summary
`Button._colors()` returned `LINE` as its outline color in the neutral and disabled states,
which measures 1.58:1 (dark) / 1.43:1 (light) against `CARD` -- below WCAG 1.4.11's 3:1 floor
for a UI component boundary. Both returns now use `MUTED` (5.76:1 / 6.23:1), the same fix
`ToggleCheckbox` already applied for its own outline. Added a regression test that computes
the real WCAG contrast ratio rather than asserting a hex value, so a future palette edit that
reintroduces the failure gets caught.

## Root cause
`LINE` is a low-contrast divider color, intentionally faint for use as a decorative separator
(`TabBar` underline, `Sidebar` panel dividers) where WCAG 1.4.11 doesn't apply. `Button._colors()`
reused it as the outline for a real UI component boundary (every button's edge), which the
standard does cover. `ToggleCheckbox` had already hit and fixed this exact issue for its own
outline (see its docstring, `afk_clicker.py` near line 2356) but `Button` was never updated.

## Changes by file
- `afk_clicker.py` -- in `Button._colors()`: disabled-state return changed from
  `CARD, LINE, MUTED` to `CARD, MUTED, MUTED`; neutral-state return changed from
  `(CARD_HI if hover else CARD), LINE, INK` to `(CARD_HI if hover else CARD), MUTED, INK`.
  No other lines touched -- `danger`/`primary` states already use their own fill as outline,
  and `LINE`'s own value and its other usages (TabBar, Sidebar) are untouched.
- `tests/test_ui.py` -- added a module-level `_contrast(hex_a, hex_b)` helper (WCAG 2.x relative
  luminance, sRGB linearization, 0.03928 threshold -- the same formula `docs/history/ac-64-design.md`
  used by hand) and a new `@needs_display` test class `ButtonOutlineContrast` with two tests,
  one per theme, asserting `_contrast(MUTED, CARD) >= 3.0`. No existing contrast helper was found
  in the test suite (checked; the only prior WCAG contrast computations were done by hand in
  markdown design docs for G#63/G#64), so this is the first one and lives next to `PrimaryButtonTheme`,
  the nearest existing `Button`-theme test class.

## Key decisions / tradeoffs
- Wrote `_contrast()` as a small standalone module function in the test file rather than importing
  anything from `afk_clicker.py` -- the app module has no existing contrast computation to reuse
  (confirmed by grep), and the formula is small enough that duplicating app-internal color logic
  into test code isn't warranted.
- Used `>=` 3.0 rather than a tighter per-theme hex equality check, per the spec's explicit intent:
  catch a future palette change that reintroduces the failure, not just today's values.

## Deviations from spec
None. Only the two `LINE` references inside `Button._colors()` were changed; `LINE`'s value and
its other usages are untouched; `Segmented`/`NumBox`/other widgets are untouched.

## Known limitations
None observed. The fix is scoped exactly to `Button`'s outline per the spec's non-goals.

## How to verify locally
1. `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .`
   (CI's exact invocation, run against the project's existing Xvfb :99 + venv with `pynput`).
2. Confirm `ButtonOutlineContrast`'s two tests pass, and the full suite is green.
3. Visually: any `Button` in the app (e.g. a dialog's Cancel/Save) now outlines in `MUTED`
   instead of `LINE` in both themes; `danger`/`primary` buttons and hover states are unchanged.

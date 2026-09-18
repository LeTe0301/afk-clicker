# Implementation: macOS font-size floor (`fs(base, s)`) (G#23/GH#35)

## Summary
Added a module-level `FONT_SIZE_FLOOR = 6` constant and a pure `fs(base, s)`
helper (`afk_clicker.py:130`, next to `UI_SCALE_FACTORS`/`UI_SCALE_DEFAULT`)
that computes `int(base * s)`, floored at 6, and replaced every font-size
`int(<literal> * s)` expression in `afk_clicker.py` with `fs(<literal>, s)` —
34 call sites across the file (per `docs/spec.md`'s table), all mechanical
one-line substitutions. This fixes the reported case (macOS `_dpi_s ~= 0.75`
compounded with the 90% UI-scale step, `s = 0.675`: `int(8 * 0.675) == 5`,
illegible) while leaving the already-shipping mac-100% baseline
(`int(8 * 0.75) == 6`) and every non-mac scale step bit-for-bit unchanged,
since none of those cases fall below the floor today.

## Changes by file

### `afk_clicker.py`
- **New constant + helper** (`afk_clicker.py:130-153`): `FONT_SIZE_FLOOR = 6`
  and `fs(base, s) -> int`, with the why-comment from `docs/spec.md`'s
  proposed approach reproduced verbatim (compound-scale reasoning, why 6
  rather than a from-scratch legibility study, and the note that G#38 can
  reuse this unmodified since it has no dependency on the four discrete
  `UI_SCALE_FACTORS` keys).
- **The sweep.** Every font-size `int(<literal> * s)` expression across
  `Button`, `Segmented`, `ToggleCheckbox`, `TabBar`, `StatusPill`, `section()`,
  `GameItem`, `SettingsItem`, `Row`, `NumBox`, the header/sidebar/content/
  settings builders, and the update-failed log dialog is now `fs(<literal>,
  s)`. Non-font `int(x * s)` expressions (padding, wraplength, widget
  width/height in pixels, e.g. `afk_clicker.py:1883`, `2280`, `3949`'s
  `wraplength`) are untouched — confirmed by
  `grep -n 'int([0-9.]* \* s)' afk_clicker.py` after the change: every
  remaining hit is padding/width/height/wraplength, none inside a `font=`
  tuple or a `tkfont.Font(size=...)` call.
- **`TabBar`** (`afk_clicker.py:1793-1795`): the label font and its
  `tkfont.Font` width-measurer now both read one computed local
  (`font_size = fs(9.5, s)`) instead of calling `fs()` twice inline, so the
  two can't desync — the one call site `docs/spec.md`'s "Edge cases" flagged
  by name.
- **`Row`** (`afk_clicker.py:2237`): `self._hint_size = fs(8, s)`, computed
  once and still reused as-is at `set_hint()` (`afk_clicker.py:2259` area)
  and at construction — no separate fix needed at either reuse site, per the
  spec's own note.

### `tests/test_ui.py`
- **Import**: `from tkinter import font as tkfont` added alongside the
  existing `import tkinter as tk`, inside the `if app is not None:` guard —
  needed for the new widget-level test's `tkfont.Font(font=...).actual("size")`
  read.
- **`FontSizeFloor(unittest.TestCase)`** (placed directly after `Lighten`,
  the codebase's existing pure-helper test precedent): seven tests, one per
  `docs/spec.md`'s Acceptance criteria value — `fs(8, 0.75) == 6` (mac 100%,
  unchanged), `fs(8, 0.675) == 6` (mac 90%, the reported case, now floored),
  `fs(9.5, 0.675) == 6` (an unaffected base — no-op), `fs(8, 1.0) == 8` and
  `fs(8, 0.9) == 7` (Windows/Linux, unchanged), `fs(8, 0.8625) == 6` and
  `fs(8, 0.975) == 7` (mac 115%/130%, no-op at both).
- **`FontSizeFloorAtWorstCaseScale(UITestCase)`** (placed directly after
  `UIScale`, before `SettingsNavigation`): the one integration-level check
  the spec calls for, reusing `WindowMinimumHeight`'s own `_dpi_s`/
  `_apply_ui_scale` simulation pattern (`tests/test_ui.py:1148-1168`) since
  there is no real Mac available. Reads `self.ui.jitter_row.hint_label`'s
  actual rendered size via `tkfont.Font(font=widget.cget("font")).actual(
  "size")` — the jitter row's mutable hint is one of the spec table's
  "actually changes" call sites (`afk_clicker.py`'s `Row`, base 8) and is
  always built (both content panes are built unconditionally), so no game
  selection or Settings navigation is needed to reach it.
  `test_worst_case_mac_90_percent_floors_to_six` forces `_dpi_s = 0.75` +
  `_apply_ui_scale("90")` and asserts the rendered size is 6, not 5.
  `test_mac_100_percent_baseline_is_still_six` does the same at `"100"` and
  asserts it's still 6 — proving the floor didn't shift the already-shipping
  baseline.

## Key decisions / tradeoffs
- **Truncate, not round**, exactly as `docs/spec.md`'s proposed
  implementation specifies (`max(FONT_SIZE_FLOOR, int(base * s))`) — matches
  every existing call site's `int()` behaviour today, so no already-shipped
  size at a scale step above the floor shifts by rounding.
- **Widget-level test picked the jitter row's mutable hint, not
  `ToggleCheckbox`.** Both are "actually changes" (base 8) call sites per the
  spec's table, but `ToggleCheckbox` only exists inside the update-failed log
  dialog (extra setup to open), while `self.ui.jitter_row.hint_label` is a
  real `tk.Label`, always built as part of the Clicking pane regardless of
  which tab or profile is active, and reachable with a plain `.cget("font")`
  rather than a canvas `itemcget()` — the simpler of the two options the
  spec's Acceptance criteria explicitly names as acceptable alternatives.
- **`FontSizeFloorAtWorstCaseScale` as its own class**, not folded into
  `UIScale` or `WindowMinimumHeight` — keeps this ticket's own tests
  independently named and discoverable (`docs/spec.md`'s own Risk notes flag
  this hotfix's tests as the real gate, not the pre-existing pane-fit tests),
  while still sitting next to `UIScale` (the class it's thematically closest
  to) rather than scattered.

## Deviations from spec / design
None. The helper, its constant, its placement, its docstring/comment, and
every call-site substitution match `docs/spec.md`'s proposed approach and
table exactly; `docs/design.md` specifies no visual/UX changes beyond the
floor itself, which this implementation does not introduce. All listed
Acceptance criteria are covered by a test (enumerated above) or verified by
direct code reading (the `TabBar` single-computed-local criterion, and the
"every `grep` hit is non-font" criterion, both confirmed above and via a
literal `grep` run — see "How to verify locally").

## Known limitations
- **No real Mac available in this session** — per `docs/spec.md`'s own Risk
  notes, the only true verification is CI's macOS leg (or a real device).
  This session's evidence is: `fs()`'s own direct-value tests (unconditional,
  platform-independent pure-function assertions) plus the one widget-level
  check simulating `_dpi_s = 0.75` the same way the pre-existing
  `WindowMinimumHeight` worst-case test does. A green local/Linux run here is
  not itself evidence of correct macOS rendering — call this out in the PR
  description rather than treating this session's local run as sufficient.
- Carried from the spec, not addressed here (explicitly out of scope): no new
  settings UI for the floor value, no `WINDOW_MIN_H` change, no 90/100/115/130%
  step-value change, no G#38 continuous-scaling work, and no reliance on the
  G#42/GH#81 `WindowMinimumHeight` floor tests as a correctness gate for this
  change.

## How to verify locally
Environment (this repo's convention: a venv with `pynput==1.7.7` + Xvfb
`:99`):
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### This ticket's own tests
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.FontSizeFloor -v
# 7 tests, OK

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.FontSizeFloorAtWorstCaseScale -v
# 2 tests, OK
```
Confirmed red before implementing `fs()`: both classes failed
(`AttributeError: module 'afk_clicker' has no attribute 'fs'` for the pure
tests; `AssertionError: 5 != 6` for the worst-case widget test against the
pre-existing `int()` code) — the widget-level test's failure message before
the fix directly reproduces the ticket's reported 5pt case.

### Sweep verification
```
grep -n 'int([0-9.]* \* s)' afk_clicker.py
```
Every remaining hit is a non-font expression (padding, wraplength, pixel
width/height); none feed a `font=` tuple or `tkfont.Font(size=...)`.
```
grep -n 'font=.*int(' afk_clicker.py
```
Returns nothing except lines whose `font=` argument already reads `fs(...)`,
with the `int(...)` on the same line belonging to an unrelated trailing
`pady=`/`padx=` — no `font=` tuple still calls `int()` directly.

### Full suite result (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 423 tests in 74.134s

OK (skipped=10)
```
423 = the pre-existing baseline + 9 new tests this cycle (7 in
`FontSizeFloor`, 2 in `FontSizeFloorAtWorstCaseScale`). Same skip count as
before this change. The `invalid command name "..._drain_ui"`/`"..._sync_settings"`/
`"..._poll_games"` ("after" script) console noise and the `ResourceWarning`s
from `tests/test_updater.py`/`tests/test_ui.py`'s unclosed temp files are
pre-existing, unrelated to this diff (both already documented in earlier
`docs/history/*-implementation.md` cycles) — `tearDownModule()`'s own
unraisable-exception counter (see `tests/context.py`) is the thing that would
actually fail the run if this diff had introduced a real regression there,
and the run finished `OK`.

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
?? docs/design.md
?? docs/implementation.md
?? docs/spec.md
```
No file outside `afk_clicker.py`/`tests/test_ui.py` was touched by the code
change itself; no scratch file was left in the repo tree (the scratchpad venv
used to run tests lives outside the project directory).

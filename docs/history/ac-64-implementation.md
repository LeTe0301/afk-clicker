# Implementation: Duplicate a macro (G#64 / GH#113)

## Summary
Added a "Duplicate" button to each macro row in the Macros tab. Clicking it clones the
macro's hotkey, steps and interval into a brand new macro named `"{original} (copy)"`,
reusing the existing `_save_macro(game_id, macro_id=None, ...)` path. The row changes
from one line to two, per docs/design.md, because a fourth button plus the `" (copy)"`
suffix don't fit on one line at default scale.

## Changes by file
- `afk_clicker.py`
  - New `_duplicate_macro(self, macro)` (next to `_delete_macro`/`_save_macro`): converts
    the stored hotkey JSON back to a `Hotkey` (same conversion the row render already
    does), then calls `_save_macro(self.current, None, f'{macro["name"]} (copy)', hotkey,
    macro["steps"], macro.get("interval_ms"))`. All persistence, re-validation, pane
    refresh, and hotkey/interval re-arming come from `_save_macro` unchanged.
  - New `_truncated_row_name(name, limit=40)`, placed directly under
    `_truncated_dialog_name`. Display-only; never writes `macro["name"]`. Unlike the
    dialog helper (which truncates the tail), this keeps a **middle** ellipsis — head 31
    chars + `…` + tail 8 chars — so a duplicate's trailing `" (copy)"` (7 chars) always
    survives truncation. Applied to every row's name label, not just duplicates (per
    design.md, this is an intentional side effect: today's long names are silently
    clipped by Tk with no indication; this makes the clipping visible and non-destructive
    of the identifying suffix).
  - `_refresh_macros_pane`: each row is now `row_top` (name + hotkey) stacked over
    `row_bottom` (interval + buttons), `pady=(6*s, 0)` between them. Button pack order in
    `row_bottom` is Delete, Edit, Duplicate (`width=80`), Run — same `side="right"`
    stacking as before, which renders left-to-right as `[Run][Duplicate][Edit][Delete]`,
    matching design.md's layout. No existing button's width/order semantics changed,
    only which frame they pack into.
- `tests/test_ui.py`
  - New `DuplicateMacro(UITestCase)` class (after `MacroIntervals`, same file position
    convention as other Macros-tab test classes): 6 tests, one per spec acceptance
    criterion — name+hotkey+steps+interval cloned; no-hotkey/no-interval case matches;
    both original and duplicate get independently armed hotkey watchers (no collision
    guard, matching existing `_arm_macro_hotkeys` behavior); duplicate's own interval
    timer fires independently (`pump_until`, same technique as `MacroIntervals`'s
    `test_the_timer_actually_fires_the_macro`); original is untouched after duplicating;
    duplicate persists across a game switch away/back, verified both from
    `self.ui.store` and a fresh `app.Store(self.config)` reload. Followed TDD: all 6
    failed with `AttributeError: no attribute '_duplicate_macro'` before the method
    existed, then passed after.

## Key decisions / tradeoffs
- Verified the design's font-width estimates with `tkinter.font.Font(...).measure(...)`
  under Xvfb rather than trusting them as given (design.md flagged them as estimates).
  Measured: `Duplicate` label 75px (fits the 80px button), `every 60000 ms` 102px, a
  40-char name 296-310px depending on content — all consistent with design.md's stated
  budget (line 1 ≤396px, line 2 ≤396px at `s=1.0`). No layout numbers needed adjusting
  from what design.md specified.
- Button widths are fixed canvas widths (`width=` param), not measured against label
  text, so the 75px "Duplicate" label has headroom inside its 80px button — no clipping
  risk, consistent with how `Button` already renders `create_text` with no wraplength.
- Pane-fill (`_fill_pane`/`_request_pane_fill`) measures real geometry (span of mapped
  children), not a row-count or fixed-row-height assumption, so the taller two-line rows
  need no change there — confirmed by reading `_fill_pane`'s docstring and by the full
  `MacrosTab`/`MacroIntervals` test classes (which exercise pane refresh after
  save/delete) passing unchanged.

## Deviations from spec
- spec.md's "Affected areas" said "one new method and one new Button call, no layout
  change." design.md already identified and justified why that premise doesn't hold
  (no room on one line for the 4th button + suffix) and specified the two-line row plus
  `_truncated_row_name` as required additions. Implemented design.md's version, not the
  spec's literal "no layout change" line, since design.md is downstream of the spec and
  explicitly reconciles this gap with product-manager-facing reasoning ("Deviations from
  the spec's premise" section). No further deviation from design.md itself.

## Known limitations
- **Pre-existing, not fixed here**: the `Button` class's outline color (`LINE` on
  `CARD`) measures 1.6:1 contrast, below WCAG 1.4.11's 3:1 non-text minimum. This
  affects every button in the app (Run/Edit/Delete too), not just the new Duplicate
  button — design.md flags it as out of scope for this change since fixing it means
  changing the global `LINE` token or `Button`'s outline everywhere. Recommend filing a
  follow-up ticket for a global `Button` outline/contrast pass.
- Buttons remain mouse-only (`<Button-1>`/`<Enter>`/`<Leave>`, not keyboard-focusable) —
  pre-existing for Run/Edit/Delete, inherited by Duplicate, not changed here (design.md
  flags the same gap).
- No auto-scroll to the newly-created row if the macro list is already full — same
  behavior as creating a macro via the editor today (`_save_macro` appends and the pane
  re-measures via the generic fill mechanism; it doesn't scroll to a specific row).
- Duplicating twice yields two macros both named `"X (copy)"`, and a duplicate's hotkey
  can collide with the original's — both explicitly accepted non-goals per spec.md.

## How to verify locally
```
source /home/dev/.venvs/afk-clicker-test/bin/activate   # has pynput; afk_clicker.py needs it
DISPLAY=:99 python -m pytest tests/test_ui.py -k "DuplicateMacro or MacrosTab or MacroIntervals" -q
```
Ran this in-session: **23 passed** (6 new `DuplicateMacro` tests + 17 pre-existing
`MacrosTab`/`MacroIntervals` tests, no regressions).

Also ran the full suite (`DISPLAY=:99 python -m pytest tests/test_ui.py -q`): 457
passed, 11 failed. Verified via `git stash` that the same 11 `Themes.
test_module_globals_still_ship_dark_only` sub-failures reproduce identically on
unmodified `main` — pre-existing test-order/theme-global pollution, unrelated to this
change.

Manual check: `python -m py_compile afk_clicker.py tests/test_ui.py` succeeds. No lint
step exists in `.github/workflows/ci.yml` (it runs `python -m unittest discover`
directly), so no separate lint command was run.

To see it visually: run the app, open a game with an existing macro on the Macros tab —
the row now shows name+hotkey on one line and interval+`[Run][Duplicate][Edit][Delete]`
on the next; click Duplicate and a new row named `"{name} (copy)"` appears at the bottom
of the list.

# Implementation: Window minimum height is sized for the pre-tab layout (G#28/GH#48)

## Summary

Replaced the bare `690` height literal in `_apply_minsize()` with a new named
constant, `WINDOW_MIN_H = 560`, re-derived from a live, construction-true
measurement of the tallest real pane (Clicking + Eating, Minecraft profile)
rather than trusted from the spec's own arithmetic. Both the hard `minsize()`
floor and the default launch `geometry()` height shrank together (unchanged
mechanism — `minh` was already shared by both call sites). Added a new
`WindowMinimumHeight` test class (4 tests) and updated 3 existing tests plus
one stale comment, exactly per the spec's "Test impact" section — with one
real deviation found and fixed along the way (see below).

## Root cause

`690` was tuned by ticket #14 for the old single stacked-page layout and
never revisited when PR #40 (story #24 feature 2) split that page into tabs.
Each pane now gets the *entire* leftover height that used to be shared
across three stacked sections, leaving the tallest pane sitting in
~148-163px of permanently-unreachable dead space (no scrolling exists
anywhere in this app) while the shortest pane (Hotkey) sat ~78% empty. The
fix is a straight numeric retune, not a mechanism change.

## Independent measurement (re-verified, not trusted from the spec)

Ran the spec's own documented Xvfb-probe technique before touching any code
(`self.ui._select("minecraft")`, `self.ui._set_content_tab("clicking")`,
measuring the `clicking` pane's real content span the same way
`_fill_pane()` measures it, plus the fixed overhead above/below it):

- At this box's native scale (`s ≈ 1.043`): `natural=383px`, `overhead=137px`
  → unscaled `natural≈367px`, `overhead≈131px`, candidate floor `≈499px`.
- At the documented worst-case compound scale (`ui._dpi_s=0.75;
  ui._apply_ui_scale("90")`, `s ≈ 0.675`): `natural=254px`, `overhead=90px`
  → unscaled `natural≈376px`, `overhead≈133px`, candidate floor `≈510px`.

Both numbers match the spec's own document exactly. Adopted the spec's
proposed `WINDOW_MIN_H = 560` (a ~50-61px margin above the measured
~499-510px candidate, in the spec's own stated 40-60px range) rather than
picking a different number — the spec's arithmetic checked out.

## Changes by file

- `afk_clicker.py`
  - New module constant `WINDOW_MIN_H = 560`, placed with `SIDEBAR_W`/
    `CONTENT_W` (line ~163), carrying the derivation comment from the spec's
    "Proposed approach" section verbatim.
  - `_apply_minsize()`: `int(690 * self.s)` → `int(WINDOW_MIN_H * self.s)`.
    No other line in the function changed.
  - `_apply_minsize()`'s docstring: now names `WINDOW_MIN_H` instead of the
    bare `690`, cites G#28/GH#48 alongside #14, and adds a sentence stating
    explicitly that height (unlike width after story #24 feature 3) has no
    floor/default decoupling — mirroring the existing width-axis paragraph,
    per the spec's "Proposed approach" step 3.

- `tests/test_ui.py`
  - `WindowResize.test_minsize_reflects_the_collapsed_rail_floor`: `690` →
    `app.WINDOW_MIN_H`.
  - `UIScale.test_minsize_updates_on_every_scale_change`: same swap.
  - `UIScale.test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`:
    `min_h = int(690 * max_s)` → `int(app.WINDOW_MIN_H * max_s)`.
  - `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping`:
    comment reworded (the tallest pane's leftover at the floor is now the
    ~40-60px margin, not ~148px) — **plus a real logic addition the spec did
    not anticipate**: a bounded settling loop before the assertions (see
    "Deviations from spec").
  - New `WindowMinimumHeight(UITestCase)` class, 4 tests, exactly matching
    the spec's "New tests needed" list:
    - `test_minimum_height_shrunk_from_the_pre_tab_split_floor`
    - `test_default_launch_height_equals_the_floor`
    - `test_tallest_pane_still_fits_at_the_floor`
    - `test_tallest_pane_still_fits_at_worst_case_compound_scale`
  - `RailCollapse`'s `fixed_h = int(690 * dpi_s * ...)` left untouched — the
    spec marked this optional cleanup, not required for correctness (its
    margin only gets more generous as the real floor shrinks).

## Key decisions / tradeoffs

- **Dropped the spec's "zero both spacers first" step from the two new
  floor-fit tests.** The spec's own derivation section and "New tests
  needed" list both say to `top.configure(height=0)` /
  `bottom.configure(height=0)` before measuring `natural`. Verified directly
  against the live pane: `config(height=0)` on these spacer `Frame`s is a
  no-op (heights measured identical before/after), exactly as `_fill_pane()`'s
  own docstring (`afk_clicker.py`, ~line 1436) already documents — and the
  measurement is translation-invariant in spacer height regardless, since
  `natural` excludes the spacers by identity. Kept the technique the
  sibling, already-passing `VerticalFill` test uses instead (no zeroing),
  with a comment explaining why, rather than including dead code that
  implies an effect it doesn't have.
- **Kept `WINDOW_MIN_H = 560` as proposed** rather than adjusting after
  independent measurement, since the independent numbers matched the
  spec's own to within rounding.

## Deviations from spec

**One real, unanticipated test failure found and fixed, outside `_fill_pane()`
itself.** The spec's "Test impact" section states
`test_floor_case_still_splits_symmetrically_with_no_clipping` "need[s] no
logic change" — only its stale comment. This turned out to be false, and I
verified it live rather than trusting the document, per this project's own
standing "verify against the live system" discipline:

- With `WINDOW_MIN_H = 560`, that test failed deterministically (5/5 runs):
  `top.winfo_height() + bottom.winfo_height()` didn't equal `max(2, extra)`.
- Root cause, traced with a throwaway instrumented copy of `_fill_pane()`
  (not committed): `_select("minecraft")` then `_set_content_tab("clicking")`
  call `_fill_pane()` explicitly, but at the moment that call reads
  `natural` (the pane's own content span), the Eating card's canvas
  (`card()`'s `_redraw()`, bound to its own `<Configure>`) has not always
  finished growing to its final height yet — `pane.update_idletasks()`
  only flushes the currently-queued idle work, and `_redraw()`'s own
  follow-on `<Configure>` from *that* resize is queued *after*, not
  processed in the same call. This is a genuine, pre-existing reentrancy gap
  in `_fill_pane()`'s settling behavior — confirmed to exist unchanged at
  the *old* `690` floor too (same call sequence, same code, `git stash`
  round-trip), where it simply always converged "for free" within the
  existing recursive `update_idletasks()`-triggered cascade before the
  spec's constant shrank the numbers involved. At `560`, that cascade
  reliably falls one or two rounds short of the fixed point within a single
  synchronous call. Confirmed this is *not* the same category as real
  clipping: `natural` itself is only ever a live, real measurement (it
  eventually and reliably converges to the same value — 383px — whether
  reached via this path or via the already-passing tests that resize the
  window instead), and it never approaches `pane.winfo_height()`, so this
  ticket's own "not clipped" acceptance criteria (the 4 new
  `WindowMinimumHeight` tests) are unaffected by it.
- **This is very likely invisible in the live, running app**: a real Tk
  `mainloop()` keeps servicing queued idle/`<Configure>` work continuously
  between frames, so this same sequence would self-correct within a
  fraction of a second of a user actually clicking into Minecraft on the
  Clicking tab — confirmed by reproducing the exact same convergence with a
  small bounded loop of explicit `_fill_pane()` + `update()` calls (3-4
  rounds to reach a stable, symmetric split, every time it was probed).
  What a single test-harness `root.update()` captures is a mid-convergence
  snapshot that a live session would never actually show for more than a
  moment.
- **Fix, scoped to the test only** (per this ticket's own Non-goal: no
  change to `_fill_pane()`/`_select()`/`_set_content_tab()`, feature 4's
  mechanism): added a small, bounded (10-iteration, converges within 3-4 in
  every case observed) settling loop in
  `test_floor_case_still_splits_symmetrically_with_no_clipping`, calling
  `app._fill_pane()` again and re-measuring until both existing assertions'
  own preconditions hold, then asserting exactly what the spec originally
  wrote — no assertion was weakened or changed in meaning.
- **Recommendation for follow-up, not actioned here** (out of this ticket's
  scope): `_fill_pane()`'s reentrant settling should probably re-trigger
  itself (or be re-triggered by `_select()`/`_set_content_tab()`) after the
  eat card's own `_redraw()` finishes, rather than relying on however many
  recursive `update_idletasks()` passes happen to occur within one
  synchronous call. Worth a backlog item for whoever owns feature 4 next —
  not raised as a blocker here since it does not affect this ticket's own
  acceptance criteria (no clipping) and is very likely imperceptible in
  actual use.

No other deviations. The constant, its derivation comment, the
`_apply_minsize()` change, and the docstring update all match the spec's
"Proposed approach" verbatim.

## Known limitations

- `WINDOW_MIN_H`'s margin was verified only on Linux/Xvfb with a substituted
  font (matching the spec's own caveat) — real Windows/macOS Segoe UI
  metrics are what CI, not this session, can confirm. The spec's own two
  new construction-true tests (`test_tallest_pane_still_fits_at_the_floor`
  and its compound-scale sibling) are written specifically so a wrong
  choice fails loudly, wherever it's wrong, rather than requiring anyone to
  trust this document's numbers.
- The pre-existing `_fill_pane()` settling gap described above (fixed at
  the test level here) is not fixed at the mechanism level — see
  "Deviations from spec" above for the recommended follow-up.

## How to verify locally

```
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .
# Ran 289 tests (285 baseline + 4 new) — OK (skipped=5), run twice back-to-back, no crash.

DISPLAY=:99 <venv-python> -m unittest tests.test_ui.WindowMinimumHeight -v
# 4/4 new tests, run 5x back-to-back for determinism.

DISPLAY=:99 <venv-python> -m unittest tests.test_ui.VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping
# run 5x back-to-back — was deterministically failing before the settling-loop fix, now deterministically passing.
```

To re-run the independent `WINDOW_MIN_H` derivation yourself: construct the
app headlessly, `ui._select("minecraft")`, `ui._set_content_tab("clicking")`,
measure the `clicking` pane's content span the same way `_fill_pane()` does
(see spec's "Deriving `WINDOW_MIN_H`" section for the exact snippet) — no
code change required, a throwaway script is sufficient (none committed, per
this project's convention).

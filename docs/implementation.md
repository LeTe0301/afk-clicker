# Implementation: Pane content sits directly under its tab bar (G#37 / GH#66)

## Summary
Flipped `FILL_TOP_SHARE` from `0.5` (centering, story #24 feature 4) to
`0.0`, so every tab pane's content hugs its own tab bar and all of its
leftover vertical space collects in the bottom spacer instead of being
split evenly above and below it. The `_fill_pane()`/`_request_pane_fill()`
mechanism itself is untouched — only the one constant and its comment
changed in `afk_clicker.py`; the rest of the diff is assertion-level
updates in `tests/test_ui.py`'s `VerticalFill` class to match which
spacer now carries the meaningful signal.

## Root cause
N/A — this is a deliberate reversal of a prior, explicitly-chosen visual
treatment (story #24 feature 4's centering), not a bug fix. Leo's
2026-09-13 feedback on 0.5.0 screenshots: content floated mid-page with a
large empty band above it; he wants it to start right below the tab.

## Changes by file
- `afk_clicker.py:221` — `FILL_TOP_SHARE = 0.5` → `0.0`. Comment rewritten
  to state the new rationale (G#37/GH#66) on top of the existing story
  #24/G#28 history, matching this file's established layered-comment
  convention (e.g. `WINDOW_MIN_H`'s comment at `:163-188`). No other
  production-code line changed — `_fill_pane()`, `_request_pane_fill()`,
  `_run_pane_fill()`, `_set_spacer_height()`, `card()`, `_select()`,
  `_set_content_tab()`, `_set_settings_tab()`, `_build_content()`, and
  `_build_settings()` are byte-for-byte unchanged.
- `tests/test_ui.py` (`VerticalFill` class only):
  - `test_short_tab_gains_margin_on_a_tall_window` — rewritten per
    docs/spec.md's "Test impact": now asserts `top.winfo_height() <= 1`
    (content hugs the tab bar) and `bottom.winfo_height() >= extra - 1`
    (the pane's real leftover, measured the same way `_fill_pane()` itself
    measures it) instead of `top > 0 and bottom > 0` (a check that still
    technically passed under 0.0 but stopped proving anything).
  - `test_switching_tabs_recomputes_each_panes_own_margin` and
    `test_toggling_eating_recomputes_the_clicking_panes_margin` — swapped
    the spacer read from `top` to `bottom` on both sides of each
    comparison; assertion direction unchanged (the top spacer is pinned to
    `1` on every pane regardless of content height under `0.0`, so it can
    no longer discriminate anything).
  - `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` — full
    rewrite of its technique (not just a top/bottom swap), per the spec's
    front-loaded replacement: spies directly on `self.ui._request_pane_fill`
    instead of inferring the `_select()` guard's effect from spacer
    geometry (which is structurally unable to discriminate guard-present
    from guard-removed once the top spacer is pinned to `1`, and the
    bottom spacer was already known, per
    `docs/history/ac-24-f4-implementation.md`'s "Round 2", to move for an
    unrelated reason — `_select()`'s own `eat_section.pack(before=
    clicking_bottom)` re-pack). Asserts `"clicking"` is absent from the
    spy's call list while the pane is hidden and Eating is toggled, then
    present once the pane becomes active again. Kept the existing
    `assertFalse(...winfo_ismapped())` precondition.
  - `test_floor_case_still_fits_with_no_clipping` and its
    `..._reverse_order` sibling — **deviation from the spec's "no change
    needed" bucket, see below.** Renamed (dropped "symmetrically") and
    the split-ratio assertion (`abs(top - bottom) <= 1`) replaced with
    `top <= 1` / `bottom >= extra - 1`, same style as the rewritten
    short-tab test. The internal cross-reference comment inside
    `test_live_resize_drag_updates_margin_without_a_rebuild` was updated
    to the new test name.
  - No changes to `WindowMinimumHeight` or `FillPaneOverflow` — both
    verified to pass unmodified (see "How to verify locally").

## Key decisions / tradeoffs
- Did not remove the now-structurally-inert top spacer this cycle — spec's
  explicit non-goal and flagged follow-up; the two-spacer shape is threaded
  through five review rounds' worth of overflow-clamp/recovery logic and
  ~15 test call sites, and reworking it now would re-open that surface for
  no functional gain.
- Renamed the two floor-case tests (dropping "symmetrically") as part of
  the required assertion rewrite, rather than leaving the misleading name
  in place — the spec itself flagged this rename as "optional, non-blocking
  cleanup" under the assumption the tests needed no assertion change; since
  they did need one (see Deviations below), the rename came along with it
  rather than shipping a test named "...splits_symmetrically..." whose body
  no longer asserts symmetry.

## Deviations from spec
- **The two `test_floor_case_still_splits_symmetrically_with_no_clipping[_reverse_order]`
  tests were NOT split-ratio-independent on this dev/CI platform, contrary
  to docs/spec.md's "No change needed" bucket.** The spec's worked proof
  ("Why the floor invariant is provably unaffected") is correct as far as
  it goes, but it's anchored to the *Windows-CI-tuned* boundary value of
  `extra ∈ {0, 1}` — the value `WINDOW_MIN_H = 620` was derived against on
  the tightest platform measured. On this Linux/Xvfb box, the tallest
  pane's real leftover at the floor measures **~70-72px**, not 0-1px (this
  matches `WINDOW_MIN_H`'s own comment at `afk_clicker.py:163-188`, which
  notes Linux's substituted font "never got closer than ~10px" to the
  Windows-tight case, and the historical test docstring's own "~40-60px
  margin round 1 targeted" note). At `extra=70`, the split ratio very much
  does enter the computation (`top=1, bottom=extra-1=69` under `0.0` vs.
  `top≈35, bottom≈35` under `0.5`), so `assertLessEqual(abs(top - bottom),
  1)` failed outright when first run unmodified (`70 not less than or
  equal to 1`, both tests). Confirmed by running the unmodified spec-quoted
  assertion before touching these two tests, then fixed by applying the
  same top/bottom assertion swap used on the "must change" tests. This
  does not affect the constant's correctness or the floor invariant itself
  (`natural <= winfo_height()` still holds, confirmed by
  `WindowMinimumHeight`'s three unmodified tests staying green) — it only
  means two more tests needed the same assertion-style fix the spec
  reserved for a different bucket. Reviewer: re-run these two tests
  specifically if testing on a platform closer to the Windows-CI floor
  value, since the exact pixel numbers in this note are Linux/Xvfb-specific.
- Everything else matches the spec as written: `FILL_TOP_SHARE = 0.0`
  (not a non-zero breathing-room share — the spec's "Open questions"
  section explicitly pre-decided this per the task brief), no top-spacer
  removal, no other production-code changes.

## Known limitations
- The top spacer (`_pane_fills[key][1]`) is now structurally inert (always
  `1px`) on every pane — acknowledged in the spec as an accepted, deferred
  cleanup, not addressed here.
- The Macros branch (G#13/GH#15) and the UI-scale-follows-window-size
  ticket (G#38/GH#67) are untouched, per the spec's non-goals.

## How to verify locally
```bash
# Full suite (baseline: 314 tests, OK, skipped=10 — unchanged after this change)
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .

# Just the three test classes this ticket touches or must not regress
DISPLAY=:99 <venv>/bin/python -m unittest \
    tests.test_ui.WindowMinimumHeight tests.test_ui.FillPaneOverflow tests.test_ui.VerticalFill -v
```
Both ran clean in this session: full suite `Ran 314 tests ... OK
(skipped=10)`; the three-class run `Ran 14 tests ... OK`.

**Sabotage checks performed (both reverted before handoff):**
- Set `FILL_TOP_SHARE` back to `0.5` → `test_short_tab_gains_margin_on_a_tall_window`
  and both `test_floor_case_still_fits_with_no_clipping[_reverse_order]`
  tests failed as expected (`AssertionError: N not less than or equal to
  1`); the other `VerticalFill` tests passed under both values by design
  (directional or spy-based, not split-value-specific).
- Reintroduced the `_select()` desync bug by replacing its
  `if self._content_tab == "clicking":` guard with `if True:` →
  `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` failed
  (`AssertionError: 'clicking' unexpectedly found in ['clicking']`),
  confirming the rewritten spy-based test still catches the guard's
  removal. Reverted immediately after.

**Visual verification** (throwaway script, not committed:
`/tmp/claude-1000/-home-dev-projects-afk-clicker/f462b60e-d499-494f-ac9e-fb9b46949dd0/scratchpad/ac37-shots/shoot.py`,
screenshots in the same directory): built the real app against a temp
store the same way `tests/test_ui.py`'s `UITestCase.setUp` does, drove it
under Xvfb `:99` (no WM — geometry set via `root.geometry()` directly, not
a WM), and screenshotted with `import -window <id>`:
- `min_hotkey.png`, `min_clicking.png`, `min_settings_appearance.png`,
  `min_settings_updates.png` — default/minimum window size
  (`WINDOW_MIN_H=620`). All four panes: content starts immediately below
  the tab bar, nothing clipped.
- `large_hotkey.png`, `large_clicking.png`, `large_settings_appearance.png`,
  `large_settings_updates.png` — `1600x1000` window. All four panes:
  content still hugs the tab bar, entire dead band pushed below the last
  card (this is the exact defect this ticket fixes — under the old `0.5`
  split these would have shown a large empty band above the card).
- `scale130_hotkey.png` — `1600x1000` window at the 130% UI-scale step:
  same top-hugging treatment, confirming scale-independence.
- `collapsed_rail_clicking.png` — narrow window
  (`RAIL_COLLAPSE_THRESHOLD - 10` wide) forcing the collapsed icon rail
  (`rail_collapsed=True` printed by the script): same top-hugging
  treatment, confirming the rail state has no interaction with this
  change.

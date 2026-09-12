# Implementation: Icon rail — collapsing sidebar + rederived minimum width (story #24, Feature 3 of 5)

## Summary
The sidebar (`self.side`) now collapses to a fixed 64px icon-only rail
(`SIDEBAR_RAIL_W`) when the window narrows past `RAIL_COLLAPSE_THRESHOLD`
(the old expanded-only floor, `SIDEBAR_W + 1 + CONTENT_W`), and re-expands
above it with no hysteresis. `GameItem`/`SettingsItem` draw a centered
initial-letter badge when collapsed instead of the left-anchored dot-and-name
row; navigation is unaffected either way. `_apply_minsize()`'s hard floor is
now derived from `SIDEBAR_RAIL_W` instead of `SIDEBAR_W`, decoupled from the
window's default launch geometry, which is unchanged. Threshold-crossing is
debounced through the existing `_request_rebuild()`/`_rebuild_ui()`
coalescing machinery via a `<Configure>` handler on `root`, per the spec's
settled "debounce-on-threshold-crossing" decision.

## Changes by file
- `afk_clicker.py`
  - Three new constants (`SIDEBAR_RAIL_W = 64`, `RAIL_COLLAPSE_THRESHOLD =
    SIDEBAR_W + 1 + CONTENT_W`, `COLLAPSED_BADGE_D = 28`), placed after
    `TAB_UNDERLINE_H` with the other sidebar/content pixel constants.
  - `AfkAutoclicker.__init__`: new `self._rail_collapsed = False` attribute
    (placed next to `self._settings_open`, session-only, never persisted —
    same precedent as `_content_tab`/`_settings_tab`/`_settings_open`), and
    `self.root.bind("<Configure>", self._on_root_resize)` bound once, after
    `self._rebuild_wanted = False` (i.e. after every attribute
    `_request_rebuild()` reads already exists).
  - New method `_on_root_resize(self, event)` (placed after
    `_request_rebuild()`): compares `event.width` against
    `RAIL_COLLAPSE_THRESHOLD * self.s` and calls `_request_rebuild()` only on
    an actual collapsed/expanded flip. **Includes a guard the spec/design did
    not have** — see "Deviations from spec or design" below, this was a real
    bug caught during implementation, not a style choice.
  - `_apply_minsize()`: `minw` now derived from `SIDEBAR_RAIL_W` (the new,
    smaller hard floor); the `not grow_only` branch computes its own
    `default_w` from the old `SIDEBAR_W`-based formula, so the window still
    *launches* at today's familiar expanded size even though the floor
    shrank. `grow_only=True` (the UI-scale path) needed no other change.
  - `_build_ui(s)`: re-derives `self._rail_collapsed` from live
    `self.root.winfo_width()` at the top, guarded by `winfo_ismapped()` (the
    very first call, from `__init__`, would otherwise read Tk's unmapped
    placeholder size, not the just-requested geometry). `side`'s width,
    `count_label`'s `.pack()` call (now conditional — the widget is still
    always built), the "Add current game" `Button`'s label/width, and the
    `SettingsItem` construction call now all key off `self._rail_collapsed`.
  - `GameItem.__init__`: new `collapsed=False` parameter, `width` default
    changed from a literal to `None` (resolved internally to
    `SIDEBAR_RAIL_W - 16` or `SIDEBAR_W - 16`). Collapsed branch draws a
    centered `COLLAPSED_BADGE_D` circle plus the profile's uppercased
    initial letter (bold, centered) instead of the left-anchored dot+name.
    `_paint()` needed zero changes, as the spec predicted — it only ever
    `itemconfig`s the stored `shape`/`dot`/`text` ids by fill/text, and the
    same three rules are correct for either shape.
  - `SettingsItem.__init__`/`_paint()`: same `collapsed`/`width=None`
    treatment, plus a badge-background circle (`self.dot`, always `LINE`,
    no running-state semantics — matches design's pixel-level spec) and a
    small `ACCENT` corner dot (`self.update_dot`) as the collapsed-mode
    stand-in for the expanded "Settings · Update" text swap. Unlike
    `GameItem`, `_paint()` *does* need a `self.collapsed` branch here: the
    collapsed letter never text-swaps (always "S"), and the update signal is
    the corner dot's Tk `state` ("normal"/"hidden"), toggled by `itemconfig`,
    not text-swapped — this is called out explicitly in the design's own
    implementation checklist (item 7) even though the spec's prose didn't
    mention it.
  - `_rebuild_list()`: passes `collapsed=self._rail_collapsed` to each
    `GameItem(...)` call.
- `tests/test_ui.py`
  - `WindowResize.test_minsize_matches_todays_default_size` renamed to
    `test_minsize_reflects_the_collapsed_rail_floor`, asserting the
    `SIDEBAR_RAIL_W`-based floor.
  - `WindowResize.test_growing_the_window_expands_content_not_the_sidebar`
    replaced with `test_rail_stays_at_expanded_width_on_a_wide_window` (grows
    to `1000x900`, matching this file's own existing precedent for that
    geometry elsewhere — not the `1400x900` I first tried, which risks
    clamping on a smaller CI display), `test_shrinking_past_the_threshold_collapses_the_rail`,
    and `test_growing_back_past_the_threshold_re_expands_the_rail`.
  - `UIScale.test_minsize_updates_on_every_scale_change`: formula swap
    (`SIDEBAR_W` → `SIDEBAR_RAIL_W`).
  - `UIScale.test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`:
    no assertion change, added a comment noting the constant is now a safe
    upper bound rather than the literal floor (spec's own suggestion).
  - New `RailCollapse(UITestCase)` class: `test_rail_starts_expanded_at_default_launch`,
    `test_default_geometry_still_matches_the_old_expanded_minimum`,
    `test_collapsed_items_still_navigate_by_click`,
    `test_repeated_threshold_crossings_coalesce_to_one_rebuild`,
    `test_a_resize_that_never_crosses_the_threshold_triggers_no_rebuild`,
    `test_add_current_game_button_survives_collapse`.

## Key decisions / tradeoffs
- Kept every pixel constant (`SIDEBAR_RAIL_W`, `COLLAPSED_BADGE_D`,
  `RAIL_COLLAPSE_THRESHOLD`) exactly as spec/design proposed — both
  documents flagged these as open-to-tuning, and nothing in verification
  suggested they need adjusting.
- `SettingsItem`'s collapsed badge circle (`self.dot`) is always `LINE`, with
  no running-state itemconfig in `_paint()` — Settings has no running
  concept, so this circle exists purely so the badge reads as the same
  visual unit `GameItem`'s badge does (matches design's pixel-level code,
  which the spec's own prose didn't spell out).
- The two coalescing tests (`test_repeated_threshold_crossings_coalesce_to_one_rebuild`,
  `test_a_resize_that_never_crosses_the_threshold_triggers_no_rebuild`) use
  synthetic `event_generate("<Configure>", width=..., height=...)` calls on
  `root` rather than real `geometry()` resizes, so the test can assert an
  exact call count without depending on the display's actual size or a real
  resize's asynchronous delivery timing. The other `RailCollapse`/
  `WindowResize` tests use real `root.geometry(...)` calls, matching the
  file's existing convention, since those need the rail's *actual* width to
  change, not just a synthetic event to be dispatched.

## Deviations from spec or design
- **Added an `event.widget is not self.root` guard inside `_on_root_resize`
  that neither `docs/spec.md` nor `docs/design.md` included.** This is a
  correctness fix for a real bug both documents' proposed code would have
  shipped, not a style preference — verified by tracing actual calls during
  development (see below), not by inspection alone.

  Root cause: `root.bind("<Configure>", handler)` is not scoped to root the
  way it looks. Every Tk widget's default `bindtags()` are `(widget's own
  path, widget's class, its *toplevel's* path, "all")` — the toplevel's own
  pathname is the third tag on literally every descendant widget in that
  window. Binding directly on `root` (a `tk.Tk()` instance, which *is* the
  toplevel) therefore fires for every child's own `<Configure>` event too,
  not just root's — this is a well-known Tkinter pitfall distinct from
  `bind_all`, which is *deliberately* global and is what this file already
  uses elsewhere (`root.bind_all("<Button-1>", self._maybe_drop_focus)`) for
  a case that actually wants every widget.

  Without the guard, a local trace during construction alone showed **~100+
  calls** to `_on_root_resize` for child Frames/Canvases (each carrying its
  *own* small width — 64, 108, 200, 440, etc., not root's), only one of
  which actually targeted root. Because `self._rail_collapsed` is a single
  shared flag, these spurious calls with tiny widths (e.g. a 36px-wide
  collapsed "Add current game" Button reporting `event.width=36`) flipped it
  to `True` well before the real widget tree ever finished building, which
  then requested a rebuild mid-construction. That rebuild's `_rebuild_ui()`
  called `_persist()` before `_settings_open`'s corresponding `click_ms`
  widget had ever been built for that instance in some interleavings,
  raising `AttributeError: 'AfkAutoclicker' object has no attribute
  'click_ms'` inside a Tk callback — reproduced directly (not just inferred)
  via `tests.test_ui.UIScale.test_ui_scale_is_persisted_to_disk` and a
  standalone repro script, both showing the exact same traceback and dozens
  of `_on_root_resize` calls with clearly-non-root widths.

  Fix: `_on_root_resize` now returns immediately unless `event.widget is
  self.root`. This is additive only — it does not change the debounce
  design, the threshold, or any other behavior the spec/design describe; it
  makes the handler behave the way both documents already assumed it would.

## Known limitations
- Matches the spec/design's own accepted limitations exactly: two profiles
  sharing a first letter render identical collapsed badges apart from
  running-state color; no tooltip reveals a collapsed item's full name; no
  bespoke `SettingsItem` glyph (uses the same initial-letter mechanism as
  `GameItem`, per the design's own resolution of the spec's open question).
- Did not re-open backlog ticket G#23 (macOS `_dpi_s ~0.75` × 90% UI-scale
  worst case) — not tested pixel-by-pixel at that compound scale locally
  (this environment's Xvfb reports `_dpi_s` at a different value than
  macOS), consistent with the design's own explicit statement that this
  feature does not depend on any particular resolution of that ticket.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-24
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/55c5887c-a42c-438d-b08e-f1ad54920e0e/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Observed: `Ran 267 tests in ~60s` / `OK (skipped=5)`, run twice in this
session with no failures and no flake (the spec's own noted
`Tcl_AsyncDelete` shutdown flake did not reproduce in either run).

Targeted run of just the areas this feature touches:
```
DISPLAY=:99 <venv-python> -m unittest tests.test_ui.RailCollapse tests.test_ui.WindowResize tests.test_ui.UIScale -v
```
Observed: 20/20 pass.

To see the collapse manually: run the app, drag the window narrower than
~661px (at 100% UI scale, DPI factor 1.0) — the sidebar should snap to a
64px icon rail with lettered badges; drag back past that width and it
re-expands with no dead zone.

## Round 2 — closing two test-coverage gaps, correcting spec/design

The reviewer approved feature 3 with no must-fix defects (`docs/test-review.md`,
"Overall verdict: Approve with follow-ups"). This round implements its two
should-fix follow-ups and its documentation correction. No behavior changed —
`afk_clicker.py` was not touched.

### Changes by file
- `tests/test_ui.py`
  - `RailCollapse.test_rail_rederives_on_a_ui_scale_change_with_width_held_fixed`
    (new): covers `_build_ui()`'s re-derivation of `self._rail_collapsed` from
    live geometry (`afk_clicker.py:1815-1817`) on a UI-scale change alone,
    with root's raw pixel width never moving — the case the reviewer's own
    `scale_rederive.py` probe verified by hand (test-review case 13) but that
    no automated test covered. Converts that probe's technique: compute the
    90%/130% steps' thresholds, force a real window width strictly between
    them, then flip the scale with that width held fixed and assert the
    collapsed state flips anyway.

    Went one step further than the probe on isolation: the probe only
    confirmed root's *width* held still across the scale change; it did not
    account for `_apply_ui_scale()` → `_apply_minsize(grow_only=True)`
    possibly changing root's *height* instead. A height change still fires a
    real `<Configure>` for root (carrying the unchanged width, but Tk emits
    the event regardless of which axis moved), which would let
    `_on_root_resize` independently repair `self._rail_collapsed` using the
    already-updated `self.s` — a passing test that actually depends on a code
    path other than `_build_ui()`'s rederivation. The test picks a starting
    height tall enough that `_apply_minsize(grow_only=True)`'s `max(cur_h,
    minh)` never grows it at either scale step, so no `geometry()` call (and
    therefore no `<Configure>`) happens at all across the scale change,
    isolating `_build_ui()`'s own rederivation as the only thing that can
    make the assertion pass. The test then asserts root's *full* geometry
    (both axes) held fixed before asserting the collapse flip — failing
    closed if that isolation assumption ever stops holding, rather than
    silently passing for a reason other than the one it's named for.

    Verified fail-closed by temporarily disabling the `_build_ui()`
    rederivation (`if self.root.winfo_ismapped():` → `if False:`) in a
    throwaway edit and re-running the test: with the original (width-only)
    version of the test, this rederivation-disabled build still passed,
    because the compensating `<Configure>`-driven path above still ran
    (height grew in that draft). That's exactly what motivated holding both
    axes fixed; after the fix, further edits to confirm the same experiment
    against the tightened version were blocked by this session's own
    sandboxing (edits to `afk_clicker.py` are out of scope for this round
    regardless), so the fail-closed claim here rests on tracing
    `_apply_minsize`'s exact `max(cur_w, minw)`/`max(cur_h, minh)` logic
    against the chosen `fixed_w`/`fixed_h`, not a second live sabotage run.
  - `RailCollapse.test_settings_item_collapsed_update_dot_reflects_has_update`
    (new): covers `SettingsItem._paint()`'s collapsed branch
    (`afk_clicker.py:1538-1548`) — the corner `update_dot`'s Tk `state`
    toggling with `has_update`, and the badge letter never text-swapping —
    the case the reviewer's own `collapsed_update_dot.py` probe verified by
    hand (test-review case 15) but that no automated test covered. Collapses
    the rail, asserts the dot starts `"hidden"` with no update pending, then
    calls the existing `self.ui._offer_update(...)` path (matching this
    file's own `UpdateFlow.test_an_offer_marks_the_settings_row_while_a_game_page_is_open`
    convention for triggering `has_update`) and asserts the dot flips to
    `"normal"` with `fill == app.ACCENT`, while the badge letter stays `"S"`
    in both states — so the test can actually distinguish "showing" from
    "not showing," not just confirm the canvas item exists.
- `docs/spec.md` — `_on_root_resize`'s proposed code (§ "Writer 2") now
  includes the `event.widget is not self.root` guard, with a docstring
  paragraph explaining why it's load-bearing (every widget's default
  bindtags include its toplevel's own pathname, so `root.bind(...)` — unlike
  `root.bind_all(...)` — also fires for every descendant's own `<Configure>`)
  and the exact crash it prevents.
- `docs/design.md` — same guard added to its own copy of `_on_root_resize`
  (the "New bound method" section), same reasoning, kept to a short
  docstring addition rather than rewriting the surrounding section.

### Key decisions / tradeoffs
- Used `_offer_update()` rather than the reviewer's probe's own route (poking
  `self.ui._pending` directly and forcing `_rebuild_ui()`) for the second
  test — `_offer_update()` is the real production entry point
  (`afk_clicker.py:2485-2491`) and is already the established convention for
  triggering `has_update` elsewhere in this file (`UpdateFlow`'s own tests),
  so no rebuild is needed to observe the effect: `_offer_update()` calls
  `settings_item.set_state(has_update=True)` on the live item directly.
- Left the `docs/spec.md`/`docs/design.md` edits scoped to the exact code
  block the reviewer flagged, per the round's own instruction to keep the
  correction tight — did not touch either document's surrounding prose,
  the "Test impact" section, or the implementation checklist's one-line
  references to the method name.

### Deviations from spec or design
None — this round is test coverage and documentation corrections only, no
product code changed.

### Known limitations
- The first new test's "fail-closed" property is verified by one completed
  sabotage run against an earlier (width-only) draft of the test (which
  correctly exposed the isolation gap that led to holding both axes fixed),
  plus manual tracing of `_apply_minsize`'s exact growth conditions against
  the final version — not a second live sabotage run against the checked-in
  version, since further edits to `afk_clicker.py` were blocked mid-session
  by this environment's own destructive-action guard (consistent with the
  round's instruction not to touch that file). Anyone with edit access to
  `afk_clicker.py` in this worktree can re-confirm by temporarily reverting
  the `if self.root.winfo_ismapped():` line and re-running just this test.

### How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-24
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/55c5887c-a42c-438d-b08e-f1ad54920e0e/scratchpad/venv/bin/python -m unittest tests.test_ui.RailCollapse -v
```
Observed: 8/8 pass (6 pre-existing + 2 new).

Full suite:
```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/55c5887c-a42c-438d-b08e-f1ad54920e0e/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Observed: test count went from **267 → 269** tests; `Ran 269 tests in
~61.6s` / `OK (skipped=5)`, exit 0.

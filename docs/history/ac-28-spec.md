# Spec: Window minimum height is sized for the pre-tab layout (G#28 / GH#48)

## Summary
`_apply_minsize()`'s hard height floor (and, coupled to it, the app's
default launch height) is `690 * s` — a number tuned by ticket #14 for the
old *single combined page* and never revisited when PR #40 split that page
into tabs. Shrink it to a new, smaller fixed constant (`WINDOW_MIN_H = 560`,
proposed and derived below, not a scaling floor) sized to the tallest actual
pane (Clicking + Eating, Minecraft profile) plus a measured margin — the
binding constraint, since the app has no scrolling anywhere and content
below that pane's fold would otherwise become permanently unreachable, not
merely tight.

## Goals
- Replace the bare `690` literal in `_apply_minsize()` with a single named
  module constant, `WINDOW_MIN_H`, placed with `SIDEBAR_W`/`CONTENT_W`
  (`afk_clicker.py:160-161`), carrying a comment that shows the derivation
  (CODING-GUIDELINES' "every non-obvious constant carries its reason") —
  and stop the four places that currently re-derive the literal `690`
  independently (see "Test impact") from silently drifting out of sync with
  each other the next time this needs tuning.
- Shrink both **the hard floor** (`root.minsize()`'s height) **and the
  default launch height** (`root.geometry()`'s height on first launch) to
  the same new value — see "Why height doesn't get the width axis's
  floor/default split" below for why these two stay coupled here, unlike
  `minw`/`default_w` after feature 3.
- The new value must fit the tallest real pane — Clicking-with-Eating on a
  Minecraft profile — with a small, deliberate margin, not a razor-thin
  fit, at every point on the DPI × UI-scale range this app supports,
  including the documented worst case (`s ≈ 0.675`: low-DPI macOS `0.75`
  times the 90% UI-scale step `0.9`).
- A construction-true test (not a fixed pixel assertion) that actually
  proves the tallest pane's content isn't clipped at the new floor, so a
  future change to that pane's content (a new row, a longer note) that
  breaks this invariant fails a test instead of silently reintroducing
  clipping.

## Non-goals
- **Not a floor that scales with the active tab.** Explicitly rejected by
  the owner: a minimum height that shifts as the user switches tabs risks
  the window visibly jumping. `WINDOW_MIN_H` is one fixed number, exactly
  like `690` was, just smaller.
- **No change to the width floor** (`SIDEBAR_RAIL_W`/`RAIL_COLLAPSE_THRESHOLD`,
  `minw`'s formula) or to `default_w` — feature 3's territory, height-only
  change here. `minw`/`default_w` remain two different numbers for the
  reason feature 3 introduced that split (the collapsed rail); nothing
  here touches that mechanism.
- **No change to `_fill_pane()`, `FILL_TOP_SHARE`, or any pane's spacer
  mechanism** (feature 4's territory). This spec only changes how much
  total height is available before `_fill_pane()` ever runs — feature 4's
  own contract ("absorbs whatever leftover genuinely exists, never more")
  is unaffected and, per its own spec, is a pure no-op exactly at the
  floor regardless of what the floor's number is.
- **No scrolling.** Grep-confirmed (again, as of this change): no
  `Scrollbar`, `yscroll`, `MouseWheel`, or `scrollregion` anywhere in
  `afk_clicker.py`. This spec does not add one — it exists precisely
  because there is no scrolling fallback, so the floor is the only thing
  standing between the tallest pane and genuine clipping.
- **No re-tuning of any other layout constant** (`CONTENT_W`, `ROW_LABEL_W`,
  card padding, font sizes). Only `_apply_minsize()`'s height math and the
  new `WINDOW_MIN_H` constant change.
- **No UI-scale-dependent or platform-dependent branching in the constant
  itself.** One unscaled number, multiplied by `self.s` exactly like `690`
  was — the margin described below is what absorbs cross-platform
  variance, not a conditional.

## Background / current state

**`_apply_minsize()`** (`afk_clicker.py:1806-1834`):
```python
minw, minh = int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * self.s), int(690 * self.s)
self.root.minsize(minw, minh)
if not grow_only:
    default_w = int((SIDEBAR_W + 1 + CONTENT_W) * self.s)
    self.root.geometry(f"{default_w}x{minh}")
    return
cur_w, cur_h = self.root.winfo_width(), self.root.winfo_height()
new_w, new_h = max(cur_w, minw), max(cur_h, minh)
if (new_w, new_h) != (cur_w, cur_h):
    self.root.geometry(f"{new_w}x{new_h}")
```
Feature 3 (PR #41) already decoupled `minw` (the hard floor, derived from
the *collapsed* `SIDEBAR_RAIL_W`) from `default_w` (the first-launch width,
still derived from the *expanded* `SIDEBAR_W`) — two different formulas, on
purpose, because the floor exists to admit a state (the collapsed rail)
that a freshly launched window deliberately does not start in. **Height has
no such second state.** `minh` is used, unchanged, for both `root.minsize()`
and (when `not grow_only`) `root.geometry()` — there is no `default_h`
distinct from `minh` anywhere in the function, and this spec does not
introduce one (see "Why height doesn't get the width axis's floor/default
split").

**Why the number is wrong today.** `690` was tuned by ticket #14
(`docs/history/` predates this story) for the pre-story layout: Hotkey,
Clicking, and Eating all stacked on one page. PR #40 (story #24, feature 2)
split that into two tab bars (`Hotkey | Clicking` on the main page,
`Appearance | Updates` on Settings) without revisiting `690` — each pane
now gets the *entire* leftover height that used to be shared across three
stacked sections, so every pane except the tallest is left with a large
dead band. Feature 4 (PR #42) added top/bottom spacers that redistribute
that dead band around a pane's own content, but redistribution cannot help
*at the floor*, where the whole point is that there's no spare space to
redistribute in the first place — feature 4's own spec explicitly scoped
this out (`docs/history/ac-24-f4-spec.md` Non-goals: "No change to
`_apply_minsize()`'s floor... this feature's own margins are... a no-op
exactly at the floor") and its design doc named it as an open backlog
question (`docs/history/ac-24-f4-design.md` "Open question: window minimum
height").

**Measured today** (`docs/history/ac-24-story.md`'s own end-to-end pass,
and reconfirmed live for this spec — see "Deriving `WINDOW_MIN_H`" below):
at the current `690 * s` floor, the tallest pane (Clicking + Eating,
Minecraft) has ~148-163px of dead space in a ~528px pane; the shortest
(Hotkey, one card) has ~409px empty of 527px, ~78%.

**The binding constraint is the tallest pane, not the smallest.** Grep-
confirmed: no `Scrollbar`/`yscroll`/`MouseWheel`/`scrollregion` anywhere in
`afk_clicker.py`. A floor sized to the *shortest* pane's needs would make
the *tallest* pane's lower rows (Eating's "Hold for" row, on a Minecraft
profile) permanently unreachable — not tight, unreachable, since there is
no scroll fallback and no other way to expose clipped content. The Eating
section is Minecraft-only (`PROFILES[0]["eating"] = True`,
`afk_clicker.py:924-933`; every other/custom profile has no Eating card at
all, `make_profile()`, `afk_clicker.py:948-951`), so "tallest pane" is
profile-dependent, and the new floor must be derived from the Minecraft
case specifically, not from whichever profile happens to be selected by
default.

## Deriving `WINDOW_MIN_H`

**Method used for this spec** (documented so the developer can re-run and
re-verify it, exactly the "throwaway Xvfb probe, not committed" technique
already established by this story's own f3/f4 specs): construct the app
headlessly, call `ui._select("minecraft")` then
`ui._set_content_tab("clicking")` (Eating now showing, the tallest real
pane), resize tall enough that `_fill_pane()`'s clamp never kicks in, zero
both of `self.ui._pane_fills["clicking"]`'s spacers, call
`pane.update_idletasks()`, then measure the pane's own real content span
the same way `_fill_pane()` itself does:
```python
kids = [c for c in pane.winfo_children()
        if c.winfo_ismapped() and c not in (top, bottom)]
natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
           - min(c.winfo_y() for c in kids))
```
and separately measure the fixed overhead above/below the tab content
(title row + note + tab bar + `2 * CONTENT_PAD`) as `pane.winfo_y() + 2 *
int(CONTENT_PAD * s)`.

**Results, this session, this box** (Linux/Xvfb, Segoe UI substituted by
whatever the container's font config resolves it to — not authoritative for
Windows/macOS's real Segoe UI metrics, see caveat below):
- At `s ≈ 1.043` (this box's real, undivided DPI scale): `natural = 383px`,
  `overhead = 137px` → unscaled (`/s`): `natural ≈ 367px`, `overhead ≈
  131px`, candidate floor `≈ 499px`.
- At the documented worst-case compound scale, forced directly
  (`ui._dpi_s = 0.75; ui._apply_ui_scale("90")` → `s ≈ 0.675` — confirmed
  safe: `_dpi_s` is set once in `__init__`, `afk_clicker.py:1664`, and never
  rewritten by `_apply_ui_scale()`/`_build_ui()`/`_rebuild_ui()`, only
  `self.s` is recomputed from it, so this reliably reproduces the
  low-DPI-macOS-times-90% case on any box without real low-DPI hardware):
  `natural = 254px`, `overhead = 90px` → unscaled: `natural ≈ 376px`,
  `overhead ≈ 133px`, candidate floor `≈ 510px`.

Both extremes land within ~11px of each other (~499-510px unscaled),
consistent with — not perfectly exact, per `int()` truncation at each
scale step — the invariant-ratio argument this codebase already relies on
elsewhere (`docs/history/ac-17-f4-spec.md` §1). This also lines up with the
ticket's own rough estimate (`690 - 148 = 542`).

**Proposed constant: `WINDOW_MIN_H = 560`** — roughly 40-60px above the
measured ~500-510px candidate, as a deliberate margin against what this
session's measurement cannot check: real Windows/macOS Segoe UI glyph
metrics (this box substitutes a different font under Xvfb), and any font
hinting/DPI-rounding differences those platforms' own text layout
introduces that this Linux box's numbers don't capture. Not a floor with
zero slack by design — a small amount of breathing room at the very
minimum size is preferable to a fit so exact that a platform-specific
font-metrics difference of a few pixels reintroduces clipping.

**This is a starting point, not a final number** — same open-to-tuning
status this story's own `SIDEBAR_RAIL_W`/`COLLAPSED_BADGE_D`/
`FILL_TOP_SHARE` constants have carried through every prior feature. The
developer should re-run the measurement above (or reuse it directly — the
technique needs no code change to work, only a throwaway script) and the
reviewer should independently re-derive it against the live app rather
than trust this document's own arithmetic, matching this project's
established "verify against the live system" discipline. If CI's own
Windows/macOS runners make a materially different number visible, adjust
`WINDOW_MIN_H` accordingly — the acceptance criteria below are written to
catch a wrong choice mechanically (construction-true, not a hardcoded
pixel value) regardless of which exact number is used.

## Why height doesn't get the width axis's floor/default split

Feature 3 deliberately made `minw` (the hard floor) smaller than `default_w`
(the launch width) because the floor's whole purpose was to admit a *new,
separate visual state* — the collapsed icon rail — that a freshly launched
window is not meant to start in. Decoupling them there was necessary: if
`default_w` had also shrunk, the app would launch collapsed by default,
which nobody asked for.

Height has no equivalent second state. Every window height from the floor
upward already renders every pane the same way — expanded, uncollapsed,
identical layout — `_fill_pane()`'s spacers just absorb more or less
leftover space depending on how tall the window is. There is no "collapsed
vertical mode" this floor exists to gate. More importantly: the dead space
this ticket is about is visible **at the default launch size already**,
because today `default_w`'s height and `minh` are already the same
number — most users never manually resize the window, so the 78%-empty
Hotkey pane the story measured is what a fresh install shows on first
launch, not an edge case reached only by deliberately shrinking. Keeping
`default_h` pinned to the old `690` while only shrinking `minsize()`'s
height would leave the bug fully intact for exactly the audience the
ticket is about. **Both must shrink together, to the same
`WINDOW_MIN_H`**, and no second "default height" constant is introduced —
`_apply_minsize()`'s `if not grow_only` branch keeps using `minh` for
`geometry()`'s height exactly as it does today, just with `minh` computed
from the new constant.

## Proposed approach

1. Add the constant, placed with `SIDEBAR_W`/`CONTENT_W`
   (`afk_clicker.py:160-161`):
   ```python
   SIDEBAR_W = 208
   CONTENT_W = 452
   WINDOW_MIN_H = 560   # the window's hard height floor, and (see
       # _apply_minsize()) today's default launch height too -- they are
       # deliberately the same number, unlike minw/default_w after story
       # #24 feature 3 (docs/spec.md's "Why height doesn't get the width
       # axis's floor/default split", G#28/GH#48). Was 690 (#14, tuned for
       # the old single combined page before PR #40 split it into tabs),
       # which left the tallest real pane (Clicking+Eating, Minecraft) in
       # ~148-163px of dead space it can never use and the shortest
       # (Hotkey) ~78% empty at the floor. Re-derived from the tallest
       # pane's own real, live-measured content span (title+note+tab bar
       # overhead plus Clicking+Eating's own content, ~500-510px unscaled
       # measured at both s≈1 and the documented worst-case compound scale
       # s≈0.675) plus a ~40-60px margin for cross-platform font-metric
       # variance this measurement can't check locally -- see docs/spec.md
       # for the exact method, re-verify before retuning further.
   ```
2. `_apply_minsize()` (`afk_clicker.py:1828`): change
   `int(690 * self.s)` to `int(WINDOW_MIN_H * self.s)`. No other line in
   the function changes — `minh` is already used for both `minsize()` and
   (when `not grow_only`) `geometry()`'s height, which is exactly the
   "both shrink together" behavior this spec wants.
3. Update the function's own docstring (`afk_clicker.py:1806-1825`) to
   name `WINDOW_MIN_H` instead of the bare `690` wherever it's mentioned,
   and to state explicitly (mirroring the existing paragraph about
   `minw`/`default_w`) that height has no equivalent decoupling.

## Affected areas
- `afk_clicker.py`:
  - One new constant, `WINDOW_MIN_H` (with `SIDEBAR_W`/`CONTENT_W`,
    `:160-161`).
  - `_apply_minsize()` (`:1806-1834`): one literal changed, docstring
    updated.
- `tests/test_ui.py` — see "Test impact" below. No other file references
  `690`/`minh`/`_apply_minsize` (grep-confirmed against `test_hotkey.py`,
  `test_chords_slow.py`, `test_updater.py`).
- No data model, schema, `Store`, or `settings.json` changes — window
  geometry has never been persisted (unchanged by this spec).
- No UX-designer pass needed (see "Routing" below).

## Edge cases
- **A window currently smaller than the old floor but larger than the new
  one, when a UI-scale change calls `_apply_minsize(grow_only=True)`**:
  unaffected — `new_h = max(cur_h, minh)` with a smaller `minh` only ever
  makes forced growth *less* likely, never more, exactly the same
  reasoning feature 3 already relied on for `minw` shrinking
  (`docs/history/ac-24-f3-spec.md` §3).
- **A non-Minecraft (no Eating) profile at the new floor**: shorter pane,
  strictly more leftover space than the Minecraft case the floor is
  derived from — `_fill_pane()`'s existing `extra = max(0, ...)` clamp
  absorbs it into spacers exactly as it does today; never the binding
  case.
- **The Hotkey pane (shortest) at the new floor**: still has real leftover
  space after this change (the floor is derived from the *tallest* pane,
  not the shortest) — reduced from ~78% empty, but not zero; `_fill_pane()`
  handles the remainder, unchanged, per feature 4's own contract.
- **A custom (`make_profile()`) game selected at the floor**: same shape as
  the non-Minecraft case above — no Eating card, `eating: False` always
  (`afk_clicker.py:948-951`) — strictly shorter than the Minecraft case.
- **Cross-platform font metrics**: the one edge case this measurement
  cannot fully rule out locally (Xvfb substitutes a different font family
  for "Segoe UI" than Windows' own renderer). Addressed by the margin in
  `WINDOW_MIN_H` above, not by a platform-conditional branch (Non-goals) —
  flagged again under "Open questions" as the one thing CI, not this spec,
  actually settles.
- **A window manager that clamps the requested floor/default geometry to a
  smaller screen** (CI's own ~1024x768 clamp, per this project's own
  established hazard) — irrelevant here specifically because the new
  height is *smaller* than before, strictly reducing (not increasing) the
  chance of hitting that clamp; the acceptance criteria below assert
  against `root.winfo_height()`/`root.minsize()` (what was actually
  granted), never a requested literal, per this project's own established
  discipline.

## Acceptance criteria
- [ ] Given `afk_clicker.WINDOW_MIN_H`, then it is strictly less than the
      old `690` — the floor actually shrank.
- [ ] Given a freshly constructed app (no manual resize), when reading
      `self.root.minsize()[1]` and `self.root.winfo_height()`, then both
      equal `int(WINDOW_MIN_H * s)` and are equal to each other — the hard
      floor and the default launch height are the same, deliberately
      coupled number (contrast with width, where they differ).
- [ ] Given the Minecraft profile selected and the Clicking tab active, at
      the app's own default (floor) window size, when measuring the
      `clicking` pane's real content span the same way `_fill_pane()`
      itself measures it (`natural`, computed live, not a fixed pixel
      value) against the pane's own real `winfo_height()`, then `natural
      <= winfo_height()` — the tallest pane's content is provably not
      clipped at the floor, on whatever platform/DPI/font metrics the test
      actually runs under.
- [ ] Given the same construction-true measurement, when forced to the
      documented worst-case compound scale (`ui._dpi_s = 0.75` then
      `ui._apply_ui_scale("90")`, `s ≈ 0.675`), then the same `natural <=
      winfo_height()` inequality still holds — the floor fits the tallest
      pane at both plausible extremes of the DPI × UI-scale range, not
      just at `s ≈ 1`.
- [ ] Given the full suite (`DISPLAY=:99 <venv>/bin/python -m unittest
      discover -s tests -t .`) after this change, then it passes at the
      current 285-test baseline plus this ticket's new tests, with exactly
      the "Test impact" section's required changes applied and zero other
      existing tests modified. The known
      `QueuedNonResyncedUpdatesSurviveARebuild...` macOS flake and the
      `Tcl_AsyncDelete`-class shutdown flake are pre-existing — re-run
      once, do not chase either.

## Test impact, argued per case

**Required changes — every place that independently re-derives the `690`
literal today:**
- `WindowResize.test_minsize_reflects_the_collapsed_rail_floor`
  (`tests/test_ui.py:843-850`) — `expected = (int((app.SIDEBAR_RAIL_W + 1 +
  app.CONTENT_W) * s), int(690 * s))` → replace `690` with
  `app.WINDOW_MIN_H`.
- `UIScale.test_minsize_updates_on_every_scale_change`
  (`tests/test_ui.py:2539-2551`) — same swap, same line shape.
- `UIScale.test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`
  (`tests/test_ui.py:2568-2600`) — `min_h = int(690 * max_s)` →
  `int(app.WINDOW_MIN_H * max_s)`. Unlike `min_w` a few lines above it
  (deliberately left on the old `SIDEBAR_W`-based formula as an
  intentionally-over-generous upper bound, per that test's own comment),
  `min_h` here is meant to represent the *actual* current floor, not a
  deliberately-inflated one — leaving it at the stale `690` would still
  pass (a bigger, safe-but-wrong margin) but silently keep asserting
  against a number that no longer means what the comment says it means.
  Update it.
- `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping`
  (`tests/test_ui.py:1093-1120`) — the assertions themselves need **no**
  logic change (they're already true-by-construction: `extra = max(0,
  pane.winfo_height() - natural)`, measured live). Its own comment block
  is now stale and should be updated: it currently states "even the
  tallest single pane... has ~148px of genuine, pre-existing leftover at
  the floor... Touching `minh` is explicitly out of scope here" — after
  this ticket, `minh` *has* been touched and the tallest pane's leftover
  at the floor is now ~40-60px (the margin), not ~148px. Reword to say so;
  do not change what's asserted.

**No change required, argued (safe/generous margins get more generous, not
invalidated):**
- `RailCollapse`'s `fixed_h = int(690 * dpi_s *
  app.UI_SCALE_FACTORS["130"]) + 100` (`tests/test_ui.py:992`) — exists
  purely as "tall enough that `_apply_minsize(grow_only=True)` never needs
  to touch the height," per its own comment. A smaller real floor only
  makes this margin more generous, never insufficient. Optional cleanup:
  reference `app.WINDOW_MIN_H` instead of the literal for clarity, not
  required for correctness.
- Every other `WindowResize`/`RailCollapse`/`UIScale` test not named above
  reads `self.root.minsize()`/`winfo_width()`/`winfo_height()` live or
  asserts width-only geometry — grep-confirmed unaffected by a height-only
  constant change.
- No test in `test_hotkey.py`, `test_chords_slow.py`, or `test_updater.py`
  references `690`, `minh`, or `_apply_minsize` (grep-confirmed) — this
  ticket's blast radius stays contained to `test_ui.py`, matching this
  story's own established pattern for every prior feature.

**New tests needed** (a new `WindowMinimumHeight(UITestCase)` class,
`tests/test_ui.py`):
- `test_minimum_height_shrunk_from_the_pre_tab_split_floor` — asserts
  `app.WINDOW_MIN_H < 690`.
- `test_default_launch_height_equals_the_floor` — on a freshly constructed
  `ui`, asserts `self.root.winfo_height() == self.root.minsize()[1] ==
  int(app.WINDOW_MIN_H * self.ui.s)` — locks in "Why height doesn't get
  the width axis's floor/default split" as a regression test, not just
  prose.
- `test_tallest_pane_still_fits_at_the_floor` — `self.ui._select("minecraft")`,
  `self.ui._set_content_tab("clicking")`, `self.root.update()` (default,
  unresized window — i.e. at the floor); zero `self.ui._pane_fills
  ["clicking"]`'s two spacers, `pane.update_idletasks()`, compute `natural`
  the same way `_fill_pane()` does, assert `natural <=
  pane.winfo_height()` — the direct, construction-true proof of "not
  clipped," runnable on every CI platform's own real font metrics, not
  just this session's own Linux measurement.
- `test_tallest_pane_still_fits_at_worst_case_compound_scale` — same
  construction as above, but first `self.ui._dpi_s = 0.75;
  self.ui._apply_ui_scale("90"); self.root.update()` to force `s ≈ 0.675`
  before re-selecting Minecraft/Clicking and re-measuring (spacers/pane
  are recreated by the scale-triggered rebuild, so re-fetch
  `self.ui._pane_fills["clicking"]` after `update()`, not before) — same
  `natural <= pane.winfo_height()` assertion. The one new test technique
  this ticket introduces (no existing test directly assigns `_dpi_s`):
  safe because `_dpi_s` is a plain instance attribute set once in
  `__init__` and never rewritten by any rebuild path (confirmed by
  reading `afk_clicker.py:1664`, `2448`, and every `_build_ui`/
  `_rebuild_ui` call site).

## Open questions
- **The exact `WINDOW_MIN_H` value (560, proposed) is this spec's own
  best estimate from one Linux/Xvfb measurement**, not a cross-platform
  fact. The two new construction-true tests above are written so a wrong
  choice fails loudly and specifically (clipping) on whatever platform
  actually exposes it, rather than requiring anyone to trust this
  document's arithmetic — but if CI's Windows/macOS legs show the margin
  is too thin (or unnecessarily fat), the developer or reviewer should
  adjust the constant directly; this is not a blocking question, just an
  explicitly-flagged best-effort number, same status this story's other
  pixel constants (`SIDEBAR_RAIL_W`, `COLLAPSED_BADGE_D`,
  `FILL_TOP_SHARE`) have carried through review.
- **Should `_apply_minsize()`'s docstring's historical reference to "#14"
  be updated to also cite this ticket (G#28/GH#48) as the second tuning
  pass?** Proceeding under "yes, add a line" (matching how feature 3's own
  docstring update named itself alongside #14) — not a real open question,
  just a style note for the developer.

## Risk / rollback notes
- Smallest possible surface: one new module constant, one changed literal,
  one docstring update, plus test updates that are almost entirely
  mechanical literal swaps (`690` → `app.WINDOW_MIN_H`). No new widget, no
  new mechanism, no new persisted state, no interaction with
  `_fill_pane()`/`_rail_collapsed`/`_request_rebuild()`.
- Revert is: change `WINDOW_MIN_H` back to `690` (or drop the constant and
  restore the bare literal). Every other change in this spec is either a
  test assertion referencing the constant (reverts for free) or a comment.
- The one invariant most worth a reviewer double-checking directly against
  the live app, not just this document's arithmetic: that
  `test_tallest_pane_still_fits_at_the_floor` and its compound-scale
  sibling actually exercise the *Minecraft* profile with *Eating showing*
  — a wrong profile ID or a missed `_set_content_tab("clicking")` call
  would make either test silently measure a shorter, non-binding pane and
  pass for the wrong reason, hiding real clipping. Re-derive `natural`
  independently against the running app rather than trust this spec's own
  numbers, matching this project's established "verify against the live
  system" discipline (`docs/history/ac-24-f3-implementation.md`'s
  corrected trace-ordering claim is the standing precedent for why).

## Routing
**Bugfix, not feature — `workflows/bugfix.md`.** This corrects a constant
that stopped matching reality after a prior change (PR #40's tab split);
nothing net-new is added. **No ux-designer pass needed**: the mechanism,
layout, and every widget involved are already fully designed and shipped
(features 2-4 of story #24) — this is a single numeric retune of an
existing, already-reviewed constant, with no new visual treatment, no new
interaction, and no design decision left open beyond the exact pixel
value, which this spec already settles with a measured, re-verifiable
derivation. The developer can take this directly from this spec.

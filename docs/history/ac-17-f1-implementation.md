# Implementation: Theme data + Quartz shape language (Story #17, Feature 1)

## Summary
Turned the module-level palette constants in `afk_clicker.py` into a `THEMES`
dict holding both the Deepslate (dark) and Quartz (light) color sets, with
`_ACTIVE = THEMES["dark"]` still the only palette read at runtime (Feature 2
wires up OS detection, Feature 3 adds a manual switch — neither is in scope
here). Buttons, the segmented control and the status pill became true pills
via a new `PILL_R = 999` constant that relies on `round_rect`'s existing
`min()` self-clamp; `card()` was rewritten from a bordered `tk.Frame` into a
borderless radius-12 `tk.Canvas` shell hosting the returned `Frame` via
`create_window`, redrawing on `<Configure>` so it tracks `#14`'s resizable
window; `GameItem`'s radius moved from 8px to the same `CARD_R = 12`. Primary
button hover now derives `ACCENT_HI` from `ACCENT` via a new `_lighten()`
helper instead of a hardcoded `"#ffd66b"`/`"#12131a"` pair. No layout,
spacing, font, or behavioral change — this is a restyle only.

## Root cause
N/A — this is a feature build, not a bugfix.

## Changes by file
- `afk_clicker.py`
  - `41-80`: replaced the nine flat palette constants with `_lighten()`,
    `_theme()`, `THEMES = {"dark": ..., "light": ...}`, `_ACTIVE =
    THEMES["dark"]`, the ten derived module globals (now including
    `ACCENT_INK`/`ACCENT_HI`), and two new radius constants `PILL_R = 999` /
    `CARD_R = 12`. Every existing `bg=BG`/`fill=CARD`/etc. call site is
    untouched — only the values those names resolve to changed.
  - `99`: `CARD_INNER_W = CONTENT_W - 2 * CARD_R` (was `CONTENT_W - 2 - 24`,
    the old 1px-border allowance), comment updated to match.
  - `Button.__init__` / `Button._colors`: radius `9 * s` → `PILL_R * s`;
    primary fill/outline/ink now `ACCENT`/`ACCENT_HI`/`ACCENT_INK` instead of
    the hardcoded `"#ffd66b"`/`"#12131a"` literals.
  - `Segmented.__init__` (outer track and selection pill) and
    `Segmented._pill_pts`: `9 * s`/`7 * s` → `PILL_R * s` in all three places,
    kept in sync per the spec's warning that the constructor and
    `_pill_pts` must move together.
  - `StatusPill.__init__`: `12 * s` → `PILL_R * s`.
  - `card()`: complete rewrite. Returns the same `inner` `Frame` callers
    already relied on (`inner.master` is now the shell `Canvas`, which still
    supports `.pack()`/`.pack_forget()` identically, so none of
    `_build_content`'s three call sites needed to change). The shell paints
    its parent's `BG`, is borderless (`outline=""`), and its `<Configure>`
    handler (bound on both `shell` and `inner`) re-measures and redraws the
    `round_rect` shape on every size change.
  - `GameItem.__init__`: radius `8 * s` → `CARD_R * s`.
- `tests/test_ui.py` — additive only, no existing test changed:
  - `Themes` — `THEMES["dark"]`/`["light"]` hold all eleven keys and the
    ticket's exact hex; the ten derived module globals still equal
    `THEMES["dark"]`; `ACCENT_HI` is the pure function's own output, not a
    hand-picked hex; `CARD_INNER_W == CONTENT_W - 2 * CARD_R == 428`.
  - `Lighten` — `_lighten()` at factor 0 (no change), 1 (pure white), and a
    partial blend.
  - `PillAndCardRadii` — `round_rect` monkeypatched to record its `r`
    argument; asserts `Button`/`Segmented` (track + pill)/`StatusPill` all
    pass `PILL_R * s`, and `GameItem`/`card()` both pass `CARD_R * s`
    (and never `PILL_R * s`). `_pill_pts` is exercised directly too, since it
    recomputes the selection pill's corners without going through
    `round_rect` at all.
  - `PrimaryButtonTheme` — hover/rest fill and label ink read `ACCENT`/
    `ACCENT_HI`/`ACCENT_INK`, proving the old hardcoded literals are gone.
  - `CardShell` — the shell `isinstance(..., tk.Canvas)`, `highlightthickness
    == 0`, shape `outline == ""`; `card()` still returns a `Frame`; the
    shape's bounding box grows and stays in sync with the shell's real width
    after `root.geometry(...)` widens the window.
  - `EatingCardCanvas` (a `UITestCase`) — `self.ui.eat_card` is now a
    `tk.Canvas`, and `.pack()`/`.pack_forget()` via `_select` still toggles
    it correctly (non-regression on the `.master`-based show/hide idiom).
  - `CardResize` (a `UITestCase`) — the real hotkey card's shell (reached via
    `self.ui.apply_button.master.master.master`, since no attribute holds it
    directly) widens when `root.geometry(...)` grows the window, and its
    shape's bounding box tracks the new width — the `#14` compatibility case
    the spec calls out explicitly.

## Key decisions / tradeoffs
- Followed `docs/spec.md`'s Decision 1-4 almost verbatim (theme dict shape,
  `PILL_R`/`CARD_R` constants and their call sites, the canvas-based
  `card()`, and the `_colors()` rewrite) — the spec's code samples were
  already complete and matched this codebase's existing conventions
  (`round_rect`'s own clamp, the `Segmented`/`GameItem` canvas-item style),
  so there was nothing to redesign.
- Verified empirically (not just by reading) that `card()`'s initial
  `_redraw()` call — which happens before the canvas is ever mapped — still
  records the exact `CARD_R * s` radius rather than some clamped-down
  transient value: Tk's geometry manager resolves `winfo_width()`
  synchronously enough here that this was never actually a problem, but it
  was checked with a monkeypatched `round_rect` before trusting it (see
  "How to verify locally").
- Added `self.root.update()` right after constructing each lightweight
  test class's own `tk.Tk()` (in `PillAndCardRadii`, `PrimaryButtonTheme`,
  `CardShell`) — without it, creating and destroying many bare `Tk()`
  instances in quick succession left a `ttk::ThemeChanged` idle callback
  pending past `destroy()`, which printed `"can't invoke ... application has
  been destroyed"` to stderr on later tests. Confirmed via `git stash` that
  this warning did not exist on the baseline branch and was introduced by
  the new test classes, not by `card()` or any other production code.

## Deviations from spec
- None in the production code — `afk_clicker.py` matches `docs/spec.md`'s
  Decisions 1-4 exactly, including the exact hex values, `PILL_R`/`CARD_R`
  constants, and the `card()` implementation.
- The spec's own "Acceptance criteria" section cites an 84-test baseline;
  this worktree is stacked on `#14` (already merged into this branch) which
  raised the baseline to 97 tests, OK, 5 skipped — confirmed directly before
  touching any code (see "How to verify locally"). This is a stale number in
  the spec, not a deviation in behavior.
- Per the developer dispatch's contrast corrections, the wrong WCAG numbers
  in `docs/design.md` were not copied into any code comment — the code has
  no contrast-ratio comments at all, so there was nothing to correct there.

## Known limitations
- `THEMES["light"]` is defined but genuinely unread at runtime, per the
  spec's own non-goal — this is intentional, not a gap, and is exercised by
  `Themes.test_light_matches_the_quartz_hex_exactly` so a future feature
  wiring it up has a hex-accuracy regression test already in place.
- The Deepslate card-on-background contrast is the mock's own subtle
  1.1:1-ish raised-flat look (per the orchestrator's corrected figures, not
  the spec's own wrong ones) — this is a defined design tradeoff (see
  `docs/design.md`'s "Design decision on Deepslate card separation"), not an
  oversight, and is unchanged by this implementation.

## How to verify locally
From `/home/dev/projects/.worktrees/afk-clicker/ac-17`:

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```

Result: **120 tests, OK, skipped=7** (baseline was 97/OK/5-skipped before
this feature; the extra 2 skips are `test_updater.LiveRepository`'s two
live-network tests hitting GitHub's rate limit in this sandbox — unrelated
to this change, reproducible by rerunning; every other test, including the
97 pre-existing ones, still passes unchanged).

To see it rendered, build the app headless against a scratch config (never a
real `~/.config` file) and screenshot it under Xvfb:

```python
import os, sys, tempfile, tkinter as tk
sys.path.insert(0, "/home/dev/projects/.worktrees/afk-clicker/ac-17")
import afk_clicker as app

cfg = os.path.join(tempfile.mkdtemp(), "settings.json")
root = tk.Tk()
ui = app.AfkAutoclicker(root, store=app.Store(cfg))
root.update()
ui._select("minecraft", persist=False)
root.update()
```

Screenshots taken this way (Minecraft selected, eating panel visible):
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-deepslate.png`
  — default window size.
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-deepslate-wide.png`
  — `root.geometry("1000x800")`, confirming the content pane and every card
  shell widen together, corners stay rounded, no square corners or stale
  shapes at the wider size.

## Round 2

The orchestrator's review of the round-1 screenshots found the "pills"
rendering as rounded rectangles with an ~8px corner radius instead of true
capsules, and the Eating card's segmented control clipped at the default
window width / floating centred at wider widths. Both are fixed.

### Root cause: `round_rect` was a smoothed spline, not a rounded rectangle

Confirmed by reading `round_rect` (was `afk_clicker.py:775-783`): it built a
12-point polygon whose points sat at the rectangle's literal corners (e.g.
`x2, y1`) and 1-radius-in tangent points, then passed it to
`create_polygon(..., smooth=True, splinesteps=24)`. Tk's canvas smoothing is
a quadratic B-spline that *approximates* its control points rather than
passing through them, so the curve the spline actually draws at each corner
cuts inside that sharp corner point — the drawn radius is always well short
of the `r` argument, and no value of `r` (including `PILL_R = 999`, clamped
to `height / 2`) produces a true semicircle out of this construction. The
round-1 tests (`PillAndCardRadii`) monkeypatched `round_rect` and asserted
the clamped `r` value it was *called with* — which was always correct — never
what the polygon's own points, or the rendered pixels, actually looked like.
`Segmented._pill_pts` (the moving selection highlight, animated via
`coords()` on the same item `round_rect` created) duplicated this exact
formula rather than calling `round_rect`, so it had to be fixed in the same
place, with the same construction.

Verified empirically before changing anything: built the old 12-point list
for a true pill (`r = height / 2`) and measured each point's distance from
its nearest end-cap centre — the corner points sit at `r * sqrt(2)` from
centre, not `r` (see `test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation`'s
docstring for the worked numbers). That control polygon is wrong on its own
terms, before smoothing ever touches it.

### The fix

- `afk_clicker.py`
  - New `import math` (top of file).
  - New `_arc_points(cx, cy, r, a0, a1, steps)`: walks a real quarter circle
    (`steps + 1` points, `a0`→`a1` in degrees, canvas' own down-is-positive
    axis) instead of a spline control point.
  - New `_round_rect_points(x1, y1, x2, y2, r, steps=10)`: composes the four
    corner arcs (top-right, bottom-right, bottom-left, top-left, in that
    order) into one flat point list for a *real* rounded rectangle. The list
    starts at `(x1 + r, y1)` — the same first vertex the old 12-point list
    used — specifically so any caller that only cares about the first vertex
    keeps working unchanged (see `Segmented._pill_pts` below and the
    existing `test_pill_pts_stays_in_sync_with_the_constructors_radius`,
    which passes unmodified). `r <= 0` falls back to a plain 4-corner
    rectangle rather than degenerating through zero-radius arcs.
  - `round_rect(cv, x1, y1, x2, y2, r, **kw)`: unchanged signature and
    "returns one canvas item id" contract; now builds its points via
    `_round_rect_points` and calls `create_polygon(pts, smooth=False, **kw)`
    — a plain, non-smoothed polygon that passes through every point it is
    given, so the drawn radius is the radius asked for. Every call site
    (`Button`, `Segmented`'s track and selection pill, `StatusPill`, `card()`,
    `GameItem`) goes through this one function and needed no changes beyond
    what `round_rect` itself does differently.
  - `Segmented._pill_pts`: replaced its own duplicated 12-point formula with
    a direct call to `_round_rect_points(x1, y1, x2, y2, r)`, so the moving
    selection highlight is built from the exact same real-arc geometry as
    the track it slides inside, and the vertex count `coords()` is given
    always matches what `round_rect` created the item with (both compute
    `r` the same way and use the same `steps` default).
  - Outline continuity: unaffected by construction — a real, closed,
    non-smoothed polygon has no gap or spike at any join; checked visually
    in `f1-pill-zoom.png` (see below) and confirmed no artefact at the
    degenerate case where a true pill's two end-cap arcs meet edge-on
    (`r = height / 2` makes the "straight side" collapse to a single
    duplicate point, which draws as an invisible zero-length segment, not a
    visible defect).
  - Card corners (`CARD_R = 12`, `card()` and `GameItem`) go through the
    same `round_rect`/`_round_rect_points` path, so they now paint a true
    12px radius instead of the softer spline approximation — this is the
    intended mock value already targeted by round 1's constants, just
    correctly reached now. Checked in both screenshots below: no square
    artefacts at the sidebar rows or the content-column cards, at either
    window width.

- Eating card's `Segmented` control (clipped at default width, floated
  centred when wide): two separate, narrower fixes, chosen over a dynamic
  resize-on-`<Configure>` approach (which `card()` already needs for its own
  shell, but would have meant giving `Segmented` the same redraw-on-resize
  machinery just for this one call site) because both root causes were
  static, one-line-each mistakes:
  - **Clipping.** `CARD_INNER_W` (the `Segmented` default `width`) was
    computed as `CONTENT_W - 2 * CARD_R`, silently assuming a full-width
    card's shell is exactly `CONTENT_W` wide. It is not: `_build_content`
    packs `body` inside `self.content` with its own `padx=pad` (`pad = 16 *
    s`) on both sides, which the constant never accounted for, so the
    control was built ~32px wider than the card's actual inner space and
    ran off the right edge. Added `CONTENT_PAD = 16` (naming that magic
    number, which `_build_content`'s own `pad = int(16 * s)` now reads from
    too, so the two can't drift apart again) and corrected the formula to
    `CONTENT_W - 2 * CONTENT_PAD - 2 * CARD_R` (452 → 396, confirmed against
    the live widget tree: the Eating `Segmented`'s actual on-screen width is
    now always a few pixels less than its card's actual inner width, at
    both window sizes tested).
  - **Floating centred at wider widths.** The Eating card's other rows
    (`Row`, `NumBox`) pack with `fill="x"`, which stretches `eat_card_inner`
    to the card's full width as the window widens. The `Segmented` control
    itself packs without `fill`, so pack's default `anchor="center"`
    centred its fixed pixel width inside that now-wider parcel. Added
    `anchor="w"` to its one `.pack()` call — the "Mouse button" `Segmented`
    a few rows up doesn't need the equivalent, since it's packed inside
    `Row.control`, which is itself packed `side="right"` and only ever as
    wide as its own content.

### New tests (`tests/test_ui.py`, `PillAndCardRadii`)

- `test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation` —
  builds a `height = 32`, `r = 16` (a true pill) rectangle directly through
  `round_rect`, then asserts on the drawn shape, not the parameter: the
  item's own `smooth` option is off, every returned coordinate sits within
  1px of the distance `r` from whichever end-cap centre is nearest, and the
  right edge's midpoint literally appears in the coordinate list (the point
  where the cap should read as flat-then-round, not pointed). Confirmed red
  against the pre-fix code: reverted only `afk_clicker.py` via `git stash`
  (dropping back to this branch's pre-round-1, pre-round-2 base) and re-ran
  just this test — `smooth` read `"true"` and the test failed on that
  assertion before ever reaching the distance check; `git stash pop`
  restored both rounds' work immediately after.
- `test_segmented_selection_pill_matches_round_rects_true_capsule` — same
  distance-from-nearest-end-cap-centre check, run against
  `Segmented._pill_pts`'s own return value rather than `round_rect`'s, since
  it is a second, independent construction that has to stay in sync.
  Confirmed red against the *pre-round-2* `_pill_pts` formula specifically
  (not just an older commit, since that formula didn't exist before round 1
  introduced `PILL_R`): re-implemented the old formula inline in a scratch
  interpreter session (not written to any file) and ran the same distance
  check against its output — the four literal corner points came out at
  `21.2px` from centre against an expected `15px` radius, confirming the
  test catches this specific regression.
- `test_card_inner_w_has_no_border_allowance_left` (existing, in `Themes`) —
  updated to assert the corrected formula and the new value, `396` (was
  `428`); this is a deliberate value change, not a loosened assertion.

## Deviations from spec (Round 2)

- None — this round only touches what the orchestrator's round-2 dispatch
  asked for: the pill/capsule geometry and the Eating segmented control's
  width/alignment. `docs/spec.md` and `docs/design.md` are otherwise
  unchanged and still hold.

## Known limitations (Round 2)

- `_round_rect_points`'s `steps=10` per quarter circle is a fixed
  granularity, not scaled by `s` or by `r`. At this app's actual widget
  sizes (radii up to ~29px for the tallest pill) the resulting worst-case
  linear approximation error is well under a pixel, so this was not made
  configurable or scale-aware — a future widget with a much larger radius
  would want to revisit this, not add it speculatively now.

## How to verify locally (Round 2)

From `/home/dev/projects/.worktrees/afk-clicker/ac-17`:

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```

Result: **122 tests, OK, skipped=7** (same 7 skips as round 1 — two of
those are `test_updater.LiveRepository`'s live-network tests hitting
GitHub's rate limit in this sandbox, unrelated to this change — plus the 2
new tests above, both passing).

Screenshots re-taken the same way as round 1 (same paths, overwritten):
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-deepslate.png`
  — default window size; Record/Apply, the status pill, "Add current game" /
  "Check for updates", and both segmented controls now read as true
  capsules; the Eating segmented control now fits fully inside its card
  with a visible margin, no longer clipped at the right edge.
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-deepslate-wide.png`
  — `root.geometry("1000x800")`; the Eating segmented control now stays
  left-aligned inside its (wider) card instead of floating centred.
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-pill-zoom.png`
  — new: a 4x crop of the Record button and the status pill, stacked
  vertically, confirming the capsule ends render as continuous semicircular
  outlines with no gaps or spikes at the joins.

## Round 3

The orchestrator's round-2 screenshot review found the capsules themselves
now correct, but one remaining defect: the sidebar's "Add current game" and
"Check for updates" buttons each sat on a visibly lighter square rectangle
where the canvas showed through past the capsule's rounded corners.

### Root cause

Every canvas that draws a `round_rect` shape hard-coded its own `bg=`
instead of taking it from its actual parent, so the canvas only matched its
surroundings when the hard-coded color happened to equal the parent's real
background — true everywhere by accident except one spot. `Button.__init__`
hard-coded `bg=CARD if not primary else CARD` (a dead conditional: both
branches were `CARD`). Every other `Button` call site happens to sit inside
a `CARD`-background parent, so the mismatch never showed. The two sidebar
buttons are parented on `side` (`bg=BG`), so their canvas painted `CARD`
outside the capsule against a `BG` sidebar — exactly the lighter square in
the screenshot. `docs/design.md` item 3 requires the area outside every
rounded shape to paint the *parent's* background in both themes, so this was
a structural gap, not a one-widget typo — worth auditing every canvas that
calls `round_rect`, not just patching `Button`.

### The fix

Every canvas that draws a `round_rect` shape now takes its own `bg` from
its actual parent (`bg=parent.cget("bg")`) instead of a hard-coded value.
Audited all five (`afk_clicker.py`):

| Canvas | Parent(s) in this build | `bg` before | `bg` after |
|---|---|---|---|
| `Button` (`~822`) | `side` (`BG`) for the two sidebar buttons; `btns` (`CARD`) for Record/Apply | `CARD` (both branches of a dead `if not primary else CARD`) | `parent.cget("bg")` — `BG` in the sidebar, `CARD` in `btns`; conditional removed |
| `Segmented` (`~870`) | `r.control` (`CARD`); `eat_card_inner` (`CARD`) | `CARD` | `parent.cget("bg")` — still `CARD` at both current call sites, now derived rather than coincidental |
| `StatusPill` (`~913`) | `header` (`CARD`) | `BG`, immediately overridden by a manual `self.status.config(bg=CARD)` right after construction | `parent.cget("bg")` — `CARD` directly; the now-redundant `.config(bg=CARD)` workaround removed |
| `card()` shell (`~957`) | `body` (`BG`) | `BG` | `parent.cget("bg")` — still `BG`, now derived rather than coincidental |
| `GameItem` (`~988`) | `list_frame` (`BG`) | `BG` | `parent.cget("bg")` — still `BG`, now derived rather than coincidental |

`StatusPill` turned out to have the same underlying defect as the sidebar
buttons — its constructor also hard-coded the wrong color (`BG` inside a
`CARD` header) — but it was invisible because `AfkAutoclicker.__init__` had
a one-line `self.status.config(bg=CARD)` patched on right after
construction to paper over it for that one call site. That workaround is
now dead code once the constructor gets it right itself, so it was removed
rather than left alongside the real fix.

No other canvas in the app calls `create_polygon` outside `round_rect`
(confirmed via `grep -n create_polygon afk_clicker.py`), so these five are
the complete set.

### New test (`tests/test_ui.py`, `RoundedCanvasBackgrounds`)

`test_every_rounded_canvas_matches_its_parents_background` builds the full
running app (via `UITestCase`'s real `self.root`/`self.ui`), walks the
entire widget tree, and collects every `tk.Canvas` holding at least one
`polygon` item (`round_rect` is the only thing in the app that calls
`create_polygon`, so this generically finds all five without hand-listing
widget classes). It then asserts `canvas.cget("bg") == canvas.master.cget("bg")`
for each one found.

Confirmed red first: ran just this test against the pre-fix code and got
```
[('.!frame2.!frame.!button', '#1c1f23', '#15171a'),
 ('.!frame2.!frame.!button2', '#1c1f23', '#15171a')]
```
— the two sidebar buttons (`CARD` vs. the sidebar's real `BG`), and nothing
else, matching the screenshot exactly. `StatusPill`'s constructor-level
mismatch didn't appear here because the `.config(bg=CARD)` workaround was
still in place at that point in the TDD cycle; it stayed clean afterward
once the constructor and that workaround were both fixed together.

## Deviations from spec (Round 3)

- None — this round only touches what round 3's dispatch asked for: making
  every rounded canvas's `bg` structurally derive from its parent, auditing
  all five call sites rather than special-casing `Button`. `docs/spec.md`
  and `docs/design.md` are otherwise unchanged and still hold.

## Known limitations (Round 3)

- `parent.cget("bg")` assumes every parent passed to these constructors is a
  widget with a `bg`/`background` option (true of every `tk.Frame`/`tk.Canvas`
  parent used anywhere in this codebase today, including the `card()` shell's
  `inner` Frame, which does report `CARD`). A future caller passing some
  other widget type without a `bg` option would need an explicit `bg=`
  argument added at that call site — not speculatively guarded against here,
  since no such caller exists.

## How to verify locally (Round 3)

From `/home/dev/projects/.worktrees/afk-clicker/ac-17`:

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```

Result: **123 tests, OK, skipped=7** (same 7 skips as rounds 1-2, plus the
1 new test above, passing).

Screenshots re-taken the same way as rounds 1-2 (same app-build snippet,
`import -window root` under Xvfb `DISPLAY=:99`, then cropped to the window's
own geometry with ImageMagick `convert`):
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-deepslate.png`
  — default window size, overwritten; sidebar buttons no longer show a
  lighter square behind the capsule.
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f1-sidebar-zoom.png`
  — new: a 4x nearest-neighbor zoom of "Add current game" / "Check for
  updates", cropped from the same capture, confirming the capsule corners
  now blend directly into the sidebar background with no visible rectangle.

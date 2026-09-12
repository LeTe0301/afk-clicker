# Test & Review: Flat minimal restyle (story #24, Feature 5 of 5 — last feature)

## Scope
All acceptance criteria in `docs/spec.md`'s "Acceptance criteria" section, plus
the six extra hands-on checks called out in this cycle's dispatch (`section()`'s
pady coupling, the `_fill_pane` header-height interaction, the accent-bar
stacking-order/design-doc inconsistency, the `assertGreaterEqual` test
deviation, the `RoundedCanvasBackgrounds` re-key, and the `FlatChrome` rewrite's
coverage vs. the old `PillAndCardRadii`). Diff reviewed: `git diff a87d44f..HEAD`
(HEAD `008414d`).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `round_rect`/`_round_rect_points`/`_arc_points`/`CARD_R`/`PILL_R` gone | automated (grep + `hasattr`) | pass | `grep` on `afk_clicker.py` returns nothing; `hasattr(app, name)` is `False` for all five, run live under `:99` |
| 2 | Button/Segmented track/StatusPill/card()/GameItem/SettingsItem shape item is `"rectangle"` | automated | pass | `tests.test_ui.FlatChrome`, all 9 tests green |
| 3 | `CARD_INNER_W == 396` | automated + direct probe | pass | `test_card_inner_w_has_no_border_allowance_left`; `python -c "import afk_clicker as app; print(app.CARD_INNER_W)"` → `396` |
| 4 | `section()` text not `.upper()`'d | automated | pass | `SectionHeader.test_section_text_is_not_uppercased` |
| 5 | `section()` w/o `action_factory`: no reserved right column | automated | pass | `SectionHeader.test_section_with_no_action_has_no_reserved_gap` |
| 6 | `section()` w/ `action_factory`: widget right of label, same row | automated | **fails to actually verify the criterion** — see Findings #1 | `SectionHeader.test_section_action_factory_is_actually_wired` passes, but is not discriminating (see below) |
| 7 | `GameItem`/`SettingsItem` `selected=True` shows an `ACCENT` element, both rail widths | automated + manual pixel-level probe | pass | `RailAccent` (4 tests, both `collapsed=True/False`); scratchpad probe confirmed the bar is genuinely topmost/visible at `s=1` and `s=0.675`, expanded and collapsed (see below) |
| 8 | `SettingsItem` `has_update=True, selected=False` → no bar | automated | pass | `RailAccent.test_settings_item_accent_bar_is_independent_of_has_update` |
| 9 | `GameItem` `selected=True, running=True` → dot + bar both visible, distinct items | automated | pass | `RailAccent.test_running_dot_and_accent_bar_coexist` |
| 10 | `THEMES` `ACCENT`/`OK`/`BAD` byte-identical before/after | automated diff | pass | `git diff a87d44f..HEAD -- afk_clicker.py` shows zero changes to the `THEMES` dict lines |
| 11 | Full suite green, 284 tests | automated, run twice | pass | `DISPLAY=:99 ... -m unittest discover` → `Ran 284 tests ... OK (skipped=5)`; repeated on `:98` → same |
| 12 | `section()`'s hardcoded-pady coupling doesn't drift across a profile-switch cycle | manual probe | pass | see "Hands-on check 1" below |
| 13 | `_fill_pane` self-adjusts to the new 10pt header height, no hardcoded content height | automated (existing `VerticalFill` suite, construction-true) + manual probe | pass | see "Hands-on check 2" below |
| 14 | Accent-bar stacking order actually renders a visible bar (not just `state=normal`) | manual probe (canvas `find_overlapping`) | pass (code); design.md prose wrong — see Findings #3 | see "Hands-on check 3" below |
| 15 | `RoundedCanvasBackgrounds` rewrite still catches a real regression | manual sabotage | pass | see "Hands-on check 5" below |
| 16 | `FlatChrome` (9 tests) covers everything `PillAndCardRadii` (8 tests) did, no net loss | manual mapping | pass, net gain | see "Hands-on check 6" below |
| 17 | Contrast figures in `docs/design.md`/`docs/spec.md` recomputed via real WCAG formula | manual recompute | **spec.md's accent-bar figures correct; design.md's other figures wrong** — see Findings #2 | see "Contrast recompute" below |

## Regression check
Full existing suite run twice, different Xvfb displays:
- `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 284 tests in 68.5s` — `OK (skipped=5)`
- `DISPLAY=:98 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 284 tests in 76.6s` — `OK (skipped=5)`

284 matches the developer's own math (276 baseline + 9 `FlatChrome` − 8 old
`PillAndCardRadii` + 3 `SectionHeader` + 4 `RailAccent` = 284). No
`Tcl_AsyncDelete` flake observed in either run; not chased further per
`backlog.md`. Also ran `FlatChrome`/`SectionHeader`/`RailAccent`/
`RoundedCanvasBackgrounds`/`Themes` in isolation with `-v` — all 23 tests
individually green, no order-dependence.

## Hands-on checks (this cycle's specific asks)

**1. `section()`'s hardcoded-pady coupling.** Built a real `AfkAutoclicker`,
measured `eat_section.winfo_y()`/`winfo_height()` and `eat_card.winfo_y()`
through a Minecraft → Global → Minecraft → Global → Minecraft cycle (5
`_select()` calls total). Every measurement was identical: `y=216 h=21
eat_card_y=243` (gap=6px), on every cycle including the first. `section()`'s
returned `Frame` carries no internal padding beyond the label's own — the
hardcoded `pady=(int(14*s), int(6*s))` re-pack in `_select()` matches
`section()`'s own defaults exactly, so there's no drift. Clean.

**2. `_fill_pane` vs. the 10pt header.** Built the app at a tall window
(900px), read the Hotkey pane's real natural span the same way `_fill_pane`
itself does: `natural=118, available=747, top=314, bottom=315` (sums to
`extra=629` exactly, split ~50/50 per `FILL_TOP_SHARE`). The measurement is
generic over `winfo_y()`/`winfo_height()` of mapped children, so it picked up
the taller `section()` `Frame` (21px, vs. the old bare `Label`'s smaller
height) automatically. No test or code hardcodes a content height anywhere
(confirmed by re-reading `VerticalFill`'s three tests — all construction-true
against measured values). Clean.

**3. Accent-bar stacking order.** `docs/design.md` line 53's prose says the
bar is "rendered *before* (below) `self.shape`" but its own code sample (and
`implementation.md`'s stated reasoning) places `self.accent_bar`'s creation
*after* `self.shape`. Verified with `canvas.find_overlapping()` at points
across the bar's width on a `selected=True` `GameItem`:
```
x=0.5: overlapping=(2,) fills=['#e08a55']       # accent_bar only
x=1.5: overlapping=(1, 2) fills=['#262a30', '#e08a55']  # both; accent_bar (2) topmost, wins
x=2.5: overlapping=(1, 2) fills=['#262a30', '#e08a55']  # same
x=3.0: overlapping=(1,) fills=['#262a30']       # shape only, past the bar
```
The bar (item id 2, created after `self.shape`'s id 1 — Tk's last-created-is-
topmost) is genuinely topmost and fully painted `ACCENT` across its whole
width, at `s=1`, `s=0.675`, and in `collapsed=True` mode alike. **The
developer's reasoning is correct and the code is right; `docs/design.md`'s
prose is the thing that's wrong** — see Findings #3 for the concrete text to
fix.

**5. `RoundedCanvasBackgrounds` re-key sabotage.** Built a real app, ran the
rewritten `_flat_bg_canvases`/mismatch-check logic live: baseline found 12
canvases, 0 mismatches. Then (a) forced a real `GameItem`'s `bg` to `#ff00ff`
— caught immediately (`mismatches` non-empty). Then (b) simulated "someone
reverts one widget back to rounded" by deleting a `Button`'s rectangle shape,
recreating it as a `create_polygon` (a literal regression of the exact kind
this feature removes), and *also* mismatching that same `Button`'s canvas
`bg` — the class-keyed finder still found and flagged it (`('.!button',
'#123456', '#15171a')`), because it keys off `isinstance(widget, Button)`,
not item type. The rewrite protects the same invariant regardless of what
shape a regressed widget draws. Clean.

**6. `FlatChrome` vs. `PillAndCardRadii` coverage mapping.** Old 8 → new 9:
`test_button_shape_uses_pill_radius` → `test_button_shape_is_a_plain_rectangle`
(1:1); the old combined `test_segmented_track_and_selection_pill_use_pill_radius`
plus the two capsule-geometry tests (`test_pill_pts_stays_in_sync_...`,
`test_segmented_selection_pill_matches_round_rects_true_capsule`) are replaced
by `test_segmented_track_shape_is_a_plain_rectangle` (checks the track's own
item type) + `test_segmented_selection_pill_moves_to_the_correct_segment`
(checks `seg.coords(seg.pill)` is exactly a 4-element list, which itself would
fail if the pill were still a polygon — coords() returns 22+ values for the
old arc-walked polygon); `test_round_rect_draws_a_true_capsule_...` is deleted
outright with no replacement, correctly, since it tests a deleted function's
internals; `status_pill`/`game_item`/`card_shell` map 1:1. Net new:
`test_no_widget_calls_round_rect`, `test_card_r_and_pill_r_are_gone` (direct
acceptance-criterion checks), and `test_settings_item_shape_is_a_plain_rectangle`
— `SettingsItem`'s shape was **not** covered by the old `PillAndCardRadii` at
all, so this is a genuine coverage gain, not a like-for-like swap. No loss
found anywhere in the mapping.

## Contrast recompute (WCAG relative-luminance, computed directly from the
live `THEMES` hex values, not copied from either doc)

| Pair | Doc claim | Recomputed | Verdict |
|---|---|---|---|
| `ACCENT` dark on `CARD_HI` dark (accent bar) | 5.45:1 | **5.45:1** | matches |
| `ACCENT` light on `CARD_HI` light (accent bar) | 5.55:1 | **5.55:1** | matches |
| `ACCENT` dark on `BG` dark | 6.79:1 | **6.79:1** | matches |
| `ACCENT` light on `BG` light | 5.21:1 | **5.21:1** | matches |
| `OK` dark on `BG` dark | 8.85:1 | **8.85:1** | matches |
| `OK` light on `BG` light | 4.22:1 | **4.22:1** | matches |
| `MUTED` dark on `BG` dark (section header, design.md) | 5.23:1 | **6.25:1** | **wrong in design.md** |
| `MUTED` light on `BG` light (section header, design.md) | 6.68:1 | **5.22:1** | **wrong in design.md** (values look transposed) |
| `BAD` dark on `CARD` dark (StatusPill dot, design.md) | 7.84:1 | **5.22:1** | **wrong in design.md** |
| `OK` dark on `CARD` dark (design.md) | 7.40:1 | **8.15:1** | **wrong in design.md** |
| `ACCENT` dark on `CARD` dark (design.md) | 5.42:1 | **6.25:1** | **wrong in design.md** |

`spec.md`'s own contrast table (the accent-bar figures, and `ACCENT`/`OK` vs.
`BG`) is fully correct. Every wrong figure lives in `docs/design.md`, and in
every case the actual value still clears the relevant WCAG floor (4.5:1 text,
3:1 non-text) by a comfortable margin, so **no color or contrast decision
needs to change** — this is a documentation-accuracy problem, not a
functional or accessibility one. See Findings #2.

Also recomputed `docs/design.md`'s `int(10 * s)` "rounds to 7pt" claim for
the section header at `s=0.675`: `int(10 * 0.675)` in Python is `6`, not `7`
— `int()` truncates, it does not round. The header is 6pt at worst-case
scale, one point smaller than design.md's own comparison claims (it says the
header ends up "1pt larger" than the collapsed-badge letter's ~7pt; the
header is actually 1pt *smaller*, 6 vs. 7). Still bigger than the *old* 8pt
header's own worst-case size (`int(8*0.675)=5`), so this is still a net
improvement over the pre-feature baseline, and no test asserts a font-size
number — but the design doc's specific arithmetic and comparison are wrong.
See Findings #2.

## Spec coverage
All acceptance criteria are implemented and automated-tested, with one
exception:

- Criterion "the factory's widget sits right of the label, same row —
  verified by a dedicated test": implemented correctly (verified via a
  width-forced probe below), but the dedicated test itself does not actually
  distinguish "right of the label" from "merely packed next to the label" —
  see Findings #1. This is the one criterion I'd call not-actually-verified
  despite a green test.

Every other criterion has a test that would fail if the underlying behavior
regressed (confirmed for several of them via direct sabotage above, not just
inspection).

## Findings (most severe first)

### 1. `test_section_action_factory_is_actually_wired` doesn't actually prove right-alignment — must-fix
- File: `tests/test_ui.py`, `SectionHeader.test_section_action_factory_is_actually_wired`
- Issue: the test builds `section()` directly against a bare `tk.Tk()` root
  with no forced width. A `Frame` with `pack_propagate` left at its default
  (`True`) shrinks to fit its packed children, so when there's no leftover
  width to distribute, `pack(side="right")` and `pack(side="left")` place a
  widget at the *exact same* `winfo_x()` — there's nothing left over for
  `side="right"` to push against. I confirmed this directly: building the
  same row shape with `side="right"` vs. `side="left"` in an unconstrained
  parent produces byte-identical geometry (`btn x: 33` both times). The
  test's `assertGreaterEqual(action.winfo_x(), label.winfo_x() +
  label.winfo_width())` therefore passes identically whether `section()`
  internally does `action_factory(row).pack(side="right")` (as written
  today) or a hypothetical future regression to `.pack(side="left")` — both
  produce the same numbers in this exact fixture.
- Failure scenario: a future edit accidentally changes `section()`'s
  `action_factory(row).pack(side="right")` to `.pack(side="left")` (e.g. a
  copy-paste from a differently-aligned row elsewhere in the file) — this
  test keeps passing, silently, because it was never able to tell the two
  apart in its own fixture. This is the exact "`TabBar.height`-shaped latent
  trap" the test's own docstring says it exists to prevent, just relocated
  from the parameter into the test itself.
- Verified independently that `section()`'s production code is correct when
  actually given room: forcing the row's parent to a fixed width via
  `pack_propagate(False)` (mirroring how every real content pane in this app
  is built) puts the action flush against the row's right edge (`row width:
  500`, `action x: 442, w: 58` → `442+58=500`, zero slack) — so the fix is to
  the test's fixture, not to `afk_clicker.py`. Give the test row genuine
  extra width (e.g. wrap the `section()` call in a `tk.Frame(width=..., 
  ...); .pack_propagate(False)` the way the real panes do) so `side="left"`
  vs `side="right"` are actually distinguishable, then the spec's own
  original `assertGreater` can be restored rather than the current
  `assertGreaterEqual` — the deviation noted in `docs/implementation.md`
  ("adjacent packing, no gap") is a symptom of the fixture bug, not a real
  property of `section()`'s layout.

### 2. `docs/design.md`'s contrast table has five wrong figures — should-fix
- File: `docs/design.md`, lines 24, 28, 84
- Issue: recomputed against the live `THEMES` hex values with the real WCAG
  relative-luminance formula (sanity-checked against white/black = 21:1):
  section-header `MUTED`-on-`BG` is 6.25:1 dark / 5.22:1 light (doc claims
  5.23:1 / 6.68:1 — the two numbers look transposed), and the `StatusPill`
  dot contrast block (line 84) claims `BAD`/`OK`/`ACCENT` on `CARD` dark at
  7.84:1/7.40:1/5.42:1 when the real values are 5.22:1/8.15:1/6.25:1. Every
  one of these still clears its relevant WCAG floor by a healthy margin (all
  ≥5.2:1 against a 4.5:1 text floor or 3:1 non-text floor), so no color
  value needs to change — but `docs/spec.md`'s own risk notes explicitly
  call out "this project's design docs have been wrong about contrast three
  separate times already," and this makes at least a fourth and fifth
  instance, both inside the same document this feature produced.
- Failure scenario: none functional today (thresholds still pass), but the
  next feature that cites these design.md numbers as settled fact (the way
  this feature's own spec cited a prior doc's numbers) inherits wrong
  figures unless corrected now.

### 3. `docs/design.md`'s accent-bar stacking-order prose contradicts its own code sample and the actual (correct) implementation — should-fix
- File: `docs/design.md`, line 53
- Issue: prose says the bar renders "*before* (below) `self.shape`"; the
  same paragraph's own code sample and `docs/implementation.md`'s "Key
  decisions" section both place `self.accent_bar`'s creation *after*
  `self.shape`'s — which is what was actually built, and which I verified
  via `canvas.find_overlapping()` is the *only* ordering that renders a
  visible bar at all (`self.shape` spans `x=1..w-1`; a bar created first
  would have all but its leftmost 1px column painted over once `self.shape`
  is created on top of it). The implementation is correct; the design doc's
  prose sentence is the one place still saying the opposite of what it
  should.
- Failure scenario: none in this diff — flagging so the sentence gets fixed
  before a future reader (or agent) trusts the prose over the code sample
  and "corrects" the implementation to match the wrong prose.

### 4. `docs/design.md`'s `int(10 * s)` rounding claim is wrong — nit
- File: `docs/design.md`, line 28
- Issue: claims `10pt × 0.675 = 6.75pt → rounds to 7pt in Tk (int
  conversion)`. `int()` truncates toward zero; `int(10 * 0.675)` is `6`, not
  `7`, in this Python version (confirmed directly). This also flips the
  doc's own comparison one line later ("1pt larger than [the collapsed
  badge's] ~7pt" — actually 1pt *smaller*, 6 vs 7). Still legible, still
  larger than the pre-feature header's worst-case 5pt, and no test depends
  on the number — nit, not a blocker, but worth a one-line correction given
  the neighboring contrast errors in the same document.

## Follow-ups (non-blocking)
- Consider whether `docs/design.md`'s entire contrast section should be
  regenerated by script (a small helper computing WCAG ratios from `THEMES`
  directly) rather than hand-typed, given the now-repeated pattern of
  transcription/arithmetic errors across multiple features of this story.

## Overall verdict
**Changes requested.** The testing pass itself is clean (284/284, run twice,
every acceptance criterion has a green automated test, all six of this
cycle's hands-on asks check out on the actual running app). The review pass
found one must-fix: acceptance criterion 6 (`section()`'s action slot sits
right of the label) is not actually proven by its own dedicated test, because
the test's fixture gives `pack(side="left")` and `pack(side="right")` no way
to produce different results — a real gap in the one place this spec most
wanted a regression guard. Everything else (findings #2–#4) is
should-fix/nit documentation-accuracy cleanup in `docs/design.md` that
doesn't block this feature's code, but should ideally land in the same
cycle since it's part of this feature's own paper trail. Route back to the
developer for finding #1's fixture fix (and, ideally, #2–#4's doc
corrections) before re-review.

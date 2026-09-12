# Implementation: Flat minimal restyle (story #24, Feature 5 of 5 — last feature)

## Summary
Every rounded-corner shape in the app (`Button`, `Segmented`'s outer track and
selection pill, `StatusPill`, `card()`'s shell, `GameItem`, `SettingsItem`)
now paints a plain `create_rectangle` instead of `round_rect()`; `round_rect()`,
`_round_rect_points()`, `_arc_points()`, `CARD_R`, and `PILL_R` are deleted
outright, with `CARD_R`'s surviving padding role renamed `CARD_PAD = 12`.
`section()` drops `.upper()`, goes 10pt bold (per `docs/design.md`), and gains
an optional right-aligned `action_factory` slot, now returning its header
`Frame` instead of the bare `Label`. `GameItem`/`SettingsItem` gain a left-edge
`accent_bar` canvas item, created once and toggled strictly on `self.selected`
in `_paint()`. No geometry, persisted state, or color-token value changed. The
full suite (276 baseline + 8 net new) passes clean twice in a row under Xvfb.

## Changes by file

- `afk_clicker.py`
  - Deleted `import math` (its only caller, `_arc_points()`, is gone).
  - Deleted `PILL_R`/`CARD_R`; added `CARD_PAD = 12` in `CARD_R`'s place.
    `CARD_INNER_W`'s formula now reads `CARD_PAD` in place of `CARD_R` —
    verified `== 396` unchanged.
  - Deleted `_arc_points()`, `_round_rect_points()`, `round_rect()` — zero
    remaining callers after the swap below.
  - `Button.__init__`: shape call → `create_rectangle(1, 1, w-1, h-1, ...)`.
  - `Segmented.__init__`/`_paint`: outer track and selection pill shape calls
    → `create_rectangle`; `_paint()`'s pill reposition now calls
    `self.coords(self.pill, seg*idx+2, 2, seg*(idx+1)-2, self.h-2)` directly
    instead of through `_pill_pts`, which is deleted (its only caller).
  - `StatusPill.__init__`: shape call → `create_rectangle`.
  - `section(parent, text, s, top=14, action_factory=None)`: now builds a
    `tk.Frame` (`row`), packs it with the same `pady` as before, packs a
    `Label` (sentence case, no more `.upper()`, 10pt bold per
    `docs/design.md` §1) inside it `side="left"`, and — only if
    `action_factory` is given — calls `action_factory(row).pack(side="right")`.
    Returns `row`, not the label; both real call sites
    (`hotkey_pane`'s header, `self.eat_section`) only ever call
    `.pack()`/`.pack_forget()` on the return value, which a `Frame` supports
    identically to the old `Label`.
  - `card()`: `pad = int(CARD_PAD * s)`; shape call → `create_rectangle(0, 0,
    w, h, fill=CARD, outline="")`. Docstring and the `tag_lower` comment
    updated — both previously described rounding that no longer happens.
  - `GameItem.__init__`/`_paint`: shape call → `create_rectangle`; new
    `self.accent_bar = self.create_rectangle(0, 0, bar_w, h, fill=ACCENT,
    outline="", state="hidden")` created once, right after `self.shape`
    (per `docs/spec.md` §3's literal code sample — this ordering matters,
    see "Key decisions"), `bar_w = int(3 * s)`. `_paint()` gains
    `self.itemconfig(self.accent_bar, state="normal" if self.selected else
    "hidden")`.
  - `SettingsItem.__init__`/`_paint`: identical treatment — shape call, new
    `accent_bar` created and toggled the same way, gated strictly on
    `self.selected`, independent of `self.has_update`.
- `tests/test_ui.py`
  - `test_card_inner_w_has_no_border_allowance_left` (`ThemeValues`-adjacent
    global test): formula updated to `app.CARD_PAD` in place of
    `app.CARD_R`; still asserts `== 396`.
  - `PillAndCardRadii` → **`FlatChrome`** (full rewrite, not a touch-up —
    its premise, "every shape call goes through `round_rect`," no longer
    holds): `test_no_widget_calls_round_rect`,
    `test_card_r_and_pill_r_are_gone`, one `test_*_shape_is_a_plain_rectangle`
    per widget (`Button`, `Segmented`'s outer track, `StatusPill`,
    `GameItem`, `SettingsItem`, `card()`'s shell), and
    `test_segmented_selection_pill_moves_to_the_correct_segment` (position
    assertion, replacing the two deleted true-capsule-geometry tests — that
    geometry no longer exists). `test_round_rect_draws_a_true_capsule_...`
    is deleted outright (tested a function this feature removes).
  - `RoundedCanvasBackgrounds`: kept the class name (spec's own "Test
    impact" section refers to it as the thing being rewritten, not
    replaced under a new name) but rewrote `_rounded_canvases` →
    `_flat_bg_canvases`, re-keyed off widget *classes*
    (`Button`/`Segmented`/`StatusPill`/`GameItem`/`SettingsItem`, plus
    `type(widget) is tk.Canvas` — exact type, not `isinstance`, to catch
    only `card()`'s shell, the sole bare `tk.Canvas()` construction in the
    file, grep-confirmed) instead of "any canvas holding a polygon item."
    Same underlying invariant (a full-bleed background canvas's own `bg`
    must match its parent's), same test method purpose, new finder.
  - New `SectionHeader(unittest.TestCase)`: `test_section_text_is_not_uppercased`,
    `test_section_with_no_action_has_no_reserved_gap`,
    `test_section_action_factory_is_actually_wired` — the direct regression
    test against `section()`'s slot mechanism (see "Deviations" for the one
    assertion-strictness change from the spec's own sketch).
  - New `RailAccent(unittest.TestCase)`:
    `test_selected_game_item_shows_the_accent_bar` /
    `test_unselected_game_item_hides_the_accent_bar` (each parametrized over
    `collapsed=True/False` via `subTest`),
    `test_settings_item_accent_bar_is_independent_of_has_update`,
    `test_running_dot_and_accent_bar_coexist`.

## Key decisions / tradeoffs

- **Accent bar creation order.** `docs/design.md`'s prose ("rendered
  *before* (below) `self.shape`... creating the accent bar *after*
  `self.shape` achieves this layering") is internally inconsistent — Tk's
  last-created-is-topmost rule means creating the bar *after* the shape
  puts it *on top of*, not below, the shape. Followed the design's own
  literal code sample instead (`docs/spec.md` §3 and `docs/design.md`'s
  pixel-level spec both place the `accent_bar` creation call directly after
  `self.shape`'s), which is also the only ordering that actually renders a
  visible bar: `self.shape` spans `x=1..w-1`, and the accent bar's leftmost
  column (`x=0..1`) is the only part `self.shape` never covers, so a bar
  created *before* the shape would have ~all of its width painted over.
- **`RoundedCanvasBackgrounds` re-keyed by class, not bbox heuristic.** The
  spec offered two options (widget classes, or "a rectangle's own bbox
  spans its canvas's full width/height"). Went with widget classes: it
  sidesteps `card()`'s shell having no fixed `width` option (its real width
  only exists at pack-time, via `winfo_width()`), which would have forced a
  mapped-widget geometry read the story has repeatedly flagged as a hazard
  (stale-but-plausible on X11, `0`/`1` on Windows). Class-based matching
  needs no `winfo_*` call at all — `cget("bg")` is stable regardless of
  mapped state — and `type(widget) is tk.Canvas` (exact type) cleanly
  isolates `card()`'s shell from the five `tk.Canvas` *subclasses* without
  needing a bbox comparison for it at all.
- **Kept `RoundedCanvasBackgrounds`'s class name.** The spec's own "Test
  impact" section refers to this class by its existing name while
  describing its rewrite ("`RoundedCanvasBackgrounds` (`:2206-2230`) —
  rewritten per..."), never proposing a new name the way it explicitly did
  for `PillAndCardRadii` → `FlatChrome`. Renamed only the now-inaccurate
  internal docstring/method name (`_rounded_canvases` → `_flat_bg_canvases`,
  test method `test_every_rounded_canvas_...` →
  `test_every_flat_bg_canvas_...`), not the class.

## Deviations from spec

- **`test_section_action_factory_is_actually_wired`'s assertion strictness.**
  The spec's own sketch (`docs/spec.md` "New tests needed") uses
  `assertGreater(action.winfo_x(), label.winfo_x() + label.winfo_width())`.
  Run against the real `section()`/`pack()` layout, the action widget's
  `winfo_x()` lands exactly *equal* to `label.winfo_x() + label.winfo_width()`
  (adjacent packing, no gap) — `assertGreater` failed on a correct
  implementation. Changed to `assertGreaterEqual`, which still proves "right
  of the label, same row" (the actual acceptance criterion) without
  demanding a gap the spec never asked `section()` to reserve. Verified by
  running the test against the real implementation, not by assuming the
  spec's sketch was exactly right.
- Everything else matches `docs/spec.md`/`docs/design.md` as written — no
  other deviations.

## Known limitations

- The accent bar's exact thickness (3px at s=1 / 2px at s=0.675) and the
  section header's 10pt size are `docs/design.md`'s own calls, not
  independently re-derived here; visual acceptance against
  `handoff/nvidia-reference/*.png` side-by-side is the story's own
  end-to-end pass, not this feature's.
- `RoundedCanvasBackgrounds`'s class-based finder is a fixed list
  (`Button`, `Segmented`, `StatusPill`, `GameItem`, `SettingsItem`, plus
  `card()`'s bare-`tk.Canvas` shell) that would need a manual update if a
  future widget adds a new full-bleed background canvas — the same
  maintenance shape the spec itself accepted as the tradeoff for dropping
  the now-broken "any polygon" invariant.

## How to verify locally

```
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .
```

Ran twice (once against `:99`, once against `:98`) — both `OK (skipped=5)`,
284 tests (276 baseline + 9 `FlatChrome` − 8 old `PillAndCardRadii` [net +1],
+3 `SectionHeader`, +4 `RailAccent`; `RoundedCanvasBackgrounds` is a
rewrite-in-place with no test-count change).

Spot checks also run directly:
```python
import afk_clicker as app
app.CARD_INNER_W          # 396
hasattr(app, "round_rect")   # False
hasattr(app, "CARD_R")       # False
hasattr(app, "PILL_R")       # False
```

Not independently verified in this session (CI-only): the Windows/macOS legs
of the matrix, and a pixel-level side-by-side against
`handoff/nvidia-reference/*.png` — that comparison is the story's own
closing end-to-end pass per `docs/spec.md`'s final section, not this
feature's job.

## Round 2 (fix round after "changes requested")

`docs/test-review.md`'s verdict was changes-requested: one must-fix in
`tests/test_ui.py`'s `SectionHeader.test_section_action_factory_is_actually_wired`,
plus three should-fix corrections in `docs/design.md`. Production code
(`afk_clicker.py`) was confirmed correct by the reviewer and is untouched in
this round (`git diff afk_clicker.py` is empty throughout).

### Must-fix: the test fixture, not the assertion

**What the old fixture actually proved.** Nothing about alignment. It built
`section()` against a bare `tk.Tk()` root with no forced width. A `Frame`
left at its default `pack_propagate(True)` shrink-wraps to its packed
children's own requested size, so when the root has no leftover width to
distribute, `pack(side="right")` and `pack(side="left")` place the action
widget at the *identical* `winfo_x()` — there's no slack for `side="right"`
to push against. Confirmed directly with a throwaway probe building the same
row shape both ways in an unconstrained parent: both produced `action x: 33`.
`assertGreaterEqual(action.winfo_x(), label.winfo_x() + label.winfo_width())`
therefore passed on equality alone, which it would have done identically
whether `section()` packed the action `side="right"` (as shipped) or a
hypothetical regression to `side="left"` — the exact `TabBar.height`-shaped
trap the test's own docstring says it exists to prevent, just relocated from
the parameter into the test.

**What the new fixture proves.** The test now wraps `section()`'s call in a
`tk.Frame(self.root, width=500, height=50)` with `pack_propagate(False)` —
the same fixed-width-container shape every real content pane in this app
already uses — before building the row inside it. That gives the row genuine
extra width, so `side="right"` and `side="left"` now produce different
`winfo_x()` values. Two assertions:
- `assertGreater(action.winfo_x(), label.winfo_x() + label.winfo_width())` —
  restores the spec's own original assertion (see "Deviations" below).
- `assertEqual(action.winfo_x() + action.winfo_width(), row.winfo_width())` —
  a direct, stronger proof that the action is flush against the row's own
  right edge (i.e. `section()` used `pack(side="right")`, not merely "placed
  somewhere right of the label via some other layout" — a left-packed action
  preceded by a spacer could satisfy the first assertion alone without being
  actually right-aligned).

**Sabotage results, both directions:**
- Shipped code (`action_factory(row).pack(side="right")`, unchanged): test
  passes — `DISPLAY=:99 <venv> -m unittest
  tests.test_ui.SectionHeader.test_section_action_factory_is_actually_wired -v`
  → `OK`.
- Sabotaged (`afk_clicker.py:1350` temporarily edited to
  `action_factory(row).pack(side="left")`, then reverted — `git diff
  afk_clicker.py` confirmed empty afterward): test fails —
  `AssertionError: 37 not greater than 37` (the action lands immediately
  adjacent to the label, zero gap, exactly as `side="left"` should). Restored
  the file from a pre-edit copy and re-diffed against git to confirm
  byte-identical to `008414d`'s version before re-running the suite.

Direct probe numbers (width-constrained container, `row_w=500`,
`label x=0 w=37`): `side="right"` → `action x=451, w=49` (flush,
`451+49=500`); `side="left"` → `action x=37, w=49` (adjacent to the label,
`37+49=86`, nowhere near the right edge). This is what "genuinely
distinguishable" means in the fixture, and it's why both new assertions pass
for the real code and fail for the sabotaged version.

**`assertGreaterEqual` vs. `assertGreater`, revisited.** The prior round
chose `assertGreaterEqual` specifically because, in the *unconstrained*
fixture, the correct implementation produced `action.winfo_x() ==
label.winfo_x() + label.winfo_width()` (adjacent, no gap) — `assertGreater`
literally failed on correct code there, so `assertGreaterEqual` was the only
way to keep the test green without either fixing the fixture or weakening
the claim further. That justification depended entirely on the broken
fixture; it doesn't carry over. In the now-width-constrained fixture, the
correct (`side="right"`) implementation produces a *real* gap (`451 > 37`),
and the sabotaged (`side="left"`) implementation produces the same
zero-gap equality as before (`37 == 37`, i.e. not `>`). `assertGreater` is
therefore the right call now: it passes on the correct code and fails on the
sabotaged code, which is the whole point of a regression test.
`assertGreaterEqual` would still pass on the correct code but would also
have passed if some future change happened to reintroduce a zero-gap
adjacency by coincidence — a weaker guard than the fixture can now support.

### Should-fix: three `docs/design.md` corrections

**1. Contrast table — recomputed every figure, not just the five named.**
Wrote a scratch WCAG relative-luminance calculator (sanity-checked against
white/black = 21:1, matching the reviewer's own check), fed it every unique
color pair referenced anywhere in `docs/design.md` (seven pairs total, found
via `grep` for every `N.NN:1` occurrence in the file, not just the ones the
reviewer's table named), and corrected every wrong occurrence everywhere it
appears in the document (the same wrong numbers were repeated across the
decision rationale, the walkthrough prose, the contrast table, and the
"Summary of design decisions" section — all instances fixed, not just the
table):

| Pair | Old (wrong) doc figure | Corrected figure | WCAG floor | Passes? |
|---|---|---|---|---|
| `MUTED` dark (#9299a3) on `BG` dark (#15171a) | 5.23:1 | **6.25:1** | 4.5:1 text | yes |
| `MUTED` light (#596170) on `BG` light (#e8ebf0) | 6.68:1 | **5.22:1** | 4.5:1 text | yes |
| `ACCENT` dark (#e08a55) on `CARD_HI` dark (#262a30) | 5.45:1 | 5.45:1 (already correct) | 3:1 non-text | yes |
| `ACCENT` light (#2b58cc) on `CARD_HI` light (#eff2f7) | 5.55:1 | 5.55:1 (already correct) | 3:1 non-text | yes |
| `BAD` dark (#f06262) on `CARD` dark (#1c1f23) | 7.84:1 | **5.22:1** | 3:1 non-text | yes |
| `OK` dark (#5cc9a4) on `CARD` dark (#1c1f23) | 7.40:1 | **8.15:1** | 3:1 non-text | yes |
| `ACCENT` dark (#e08a55) on `CARD` dark (#1c1f23) | 5.42:1 | **6.25:1** | 3:1 non-text | yes |

Every corrected figure still clears its WCAG floor by a comfortable margin,
so this is purely a documentation-accuracy fix — no color or contrast
decision changes as a result. Fixed at every line the wrong figures
appeared: `docs/design.md`'s §1 rationale (`MUTED`/`BG` pair), §"StatusPill's
new flat form" contrast block (`BAD`/`OK`/`ACCENT` on `CARD`), the light-theme
walkthrough prose, the "Contrast verification" table, and the "Summary of
design decisions" bullet #5 — five separate locations that all repeated the
original wrong numbers.

**2. Accent-bar stacking-order prose.** `docs/design.md`'s §2 prose said the
bar renders "*before* (below) `self.shape`," which contradicts both its own
code sample two sections later and the shipped implementation (both place
`self.accent_bar`'s creation *after* `self.shape`'s). Corrected the prose to
say *after* (on top of), and added the concrete reason so a future reader
doesn't "fix" it back to the wrong direction: `self.shape` spans `x=1..w-1`,
covering all but the item's leftmost 1px column, so a bar created *before*
the shape would have nearly its entire width painted over by the
shape and would not read as a visible stripe at all. Creation-order-after is
the only ordering that renders a visible bar — this matches
`docs/implementation.md`'s own "Key decisions" section from the prior round,
which already reasoned through this correctly; only the design doc's prose
sentence was wrong.

**3. `int(10 * 0.675)` "rounds to 7pt" claim.** `int()` truncates toward
zero; `int(10 * 0.675)` is `6`, not `7`, confirmed directly
(`python3 -c "print(int(10*0.675))"` → `6`). Corrected in all four places
this claim appeared (§1 rationale, the compound-scale walkthrough section,
the pixel-level spec's code-adjacent note, and "Summary of design decisions"
bullet #7). Stated the consequence honestly rather than softening it: the
section header renders at **6pt**, not 7pt, at the compound worst case
(`s=0.675`), one point smaller than the design doc's own prior comparison
claimed (it said the header ends up "1pt larger" than the collapsed badge's
~7pt; corrected to note the header is actually 1pt *smaller*, 6 vs. 7 —
`int(10.5 * 0.675) = int(7.0875) = 7` for the badge letter, confirmed
directly). This is still bigger than the *old* 8pt header's own worst case
(`int(8 * 0.675) = 5`), so still a net improvement over the pre-feature
baseline, and no test asserts a specific font-size number. 6pt at this
compound worst case is consistent with what the app already ships under open
backlog ticket **G#23** (macOS `_dpi_s` ~0.75 × the 90% UI-scale step already
renders 5–6pt labels elsewhere in this codebase) — not a new defect
introduced by this feature, but the design doc needed to state the real
number rather than the rounded-up one.

### Deviations from spec (round 2)

- None beyond the round-1 deviation already recorded above (`assertGreater`
  → `assertGreaterEqual`), which this round reverses now that the fixture
  supports the stricter assertion — see "`assertGreaterEqual` vs.
  `assertGreater`, revisited" above. No production code changed in this
  round; `git diff afk_clicker.py` is empty from `008414d` through this
  round's commit.

### How to verify locally (round 2)

```
DISPLAY=:99 <venv-python> -m unittest tests.test_ui.SectionHeader -v
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .
DISPLAY=:98 <venv-python> -m unittest discover -s tests -t .
```

Both full-suite runs: `Ran 284 tests ... OK (skipped=5)`. `SectionHeader`
alone: 3/3 green. Sabotage (temporary `afk_clicker.py:1350`
`side="right"` → `side="left"`, reverted before committing): the must-fix
test fails with `37 not greater than 37`, confirming the fixture now
actually discriminates the two states it exists to tell apart.

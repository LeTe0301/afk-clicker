# Test & Review: Row value-column alignment (story #24, Feature 1 of 5)

## Scope
Every acceptance criterion in `docs/spec.md` for Feature 1: the fixed-width
label column in `Row`, the trailing-margin behaviour when a card stretches,
all-four-UI-scale-step fit for the widest control, the "Random jitter" hint
wrap, all 10 `Row` call sites still building cleanly, and the full test
suite. Plus the three specific items called out in the dispatch prompt
(grid/pack interaction, the developer's ratio-invariance deviation note, and
a visual observation about the Hotkey card's buttons).

## Environment note
`DISPLAY=:99` Xvfb was already running; `xdpyinfo` itself failed (not
installed / no `xauth`), but a bare `tkinter.Tk()` connects fine, so this
did not block anything. All commands below ran against the actual worktree
(`/home/dev/projects/.worktrees/afk-clicker/ac-24`), uncommitted, using
`/tmp/claude-1000/.../scratchpad/venv/bin/python`.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `control.winfo_x()` at default size == `int((ROW_LABEL_W+ROW_LABEL_GAP)*s)` | Automated: `RowValueColumn.test_control_sits_at_the_fixed_label_column_offset` | pass | `python -m unittest tests.test_ui.RowValueColumn -v` → ok. Verified non-vacuous: reverted `Row.__init__` in-place to the old `pack`-based version and re-measured with a standalone probe (not the tracked test, since editing the tracked file to run the real suite against it was denied by the sandbox) — old layout gives `control.winfo_x() == 52`, not `152`; new layout gives `152`. |
| 2 | Offset unchanged after resize to 900x760 (stretched card) | Automated: `test_offset_is_unchanged_when_the_card_stretches` | pass | Same run. Non-vacuous check: standalone probe recreating the pre-fix `pack`-based `Row` shows `control.winfo_x()` moves from 52 → 810 on the same resize — i.e. this is exactly the "gulf" the fix closes, and the new test would have caught the regression. |
| 3 | Non-zero trailing margin after stretch (control's right edge < card width) | Automated: `test_extra_width_becomes_trailing_margin_not_a_growing_gap` | pass | Same run. |
| 4 | No overflow at any UI-scale step for the widest control (UI-scale row, `width=220`) | Automated: `test_ui_scale_row_never_overflows_its_card_at_any_scale_step`, plus independent re-derivation | pass | Same run (constant check `372<=396` + rendered check at all 4 steps). Independently re-measured rendered geometry at native `s=1.0423` — right edge 387px inside a 415px card at 100%, matching the developer's own reported numbers exactly. Also independently tested the **untested direction** (see Item 2 below). |
| 5 | "Random jitter" hint `wraplength == int(ROW_LABEL_W*s)`, wraps instead of overlapping | Automated: `test_random_jitter_hint_wraps_instead_of_overlapping_the_control` | pass | Same run. Independently confirmed visually/geometrically: hint `reqheight=32` (2 lines) vs. label `reqheight=19` (1 line), `wraplength=145` at this env's `s`. |
| 6 | Two-line wrap doesn't disturb neighbouring rows | Manual (no existing test covers row-to-row spacing) | pass | Standalone probe: Interval row `y=0,h=34`; Random-jitter row `y=40,h=51` (taller, as expected); Auto-stop row `y=97,h=37` — 6px positive gap between jitter's bottom (91) and auto-stop's top (97), no overlap. |
| 7 | All 10 `Row` call sites build cleanly, Minecraft profile + Settings open, no exception | Automated (existing, unmodified): `Selftest`, `PerGameSettings`, `HotkeyPersistence`, `Themes`-driven rebuilds, `SettingsNavigation`, `UIScale`, etc. | pass | Full-suite run below; zero exceptions, `CapturesCallbackExceptions` assertion in every `tearDown` passed throughout. |
| 8 | Full suite passes at ≥240-test baseline + 5 new tests, zero existing tests modified | Automated: full discovery run, twice | pass | See Regression check below: 245/245, `OK (skipped=5)`, both runs. `git diff --stat -- tests/test_ui.py` confirms only additions (70 insertions, 0 deletions) — no existing test body touched. |

## Regression check
`cd /home/dev/projects/.worktrees/afk-clicker/ac-24 && DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .`

Run 1: `Ran 245 tests in 52.431s` → `OK (skipped=5)`
Run 2: `Ran 245 tests in 52.214s` → `OK (skipped=5)`

Matches the 240-test baseline (confirmed against `main` conceptually via the
developer's own reported baseline; not independently re-run on `main` since
the diff to `tests/test_ui.py` is purely additive, confirmed via `git diff
--stat`) plus exactly the 5 new `RowValueColumn` tests. The known
`Tcl_AsyncDelete`/exit-134 shutdown flake did not appear in either run — not
chased, per instructions. No lint/type-check step exists in this project's
CI (`.github/workflows/ci.yml` runs only the unittest suite on three OSes);
nothing else to run.

No test-technique novelty here worth belabouring: the "walk the widget tree
for a `Segmented`" and "fresh `UITestCase` per test method" techniques are
pre-existing, already-proven patterns in this file (`_appearance_segment`,
`UIScale`), and the new tests reuse them correctly — verified by reading, not
re-derived from scratch.

## Item 1 — `grid` vs `pack` interaction
Confirmed safe. `grid()` is used in exactly two places in the whole file
(`afk_clicker.py:1433,1442`), both inside `Row.__init__`, both gridding
`Row`'s own two direct children (`text`, `self.control`) into `Row` itself
(`self.grid_columnconfigure(0, ...)` at line 1431). Every `Row(...)` instance
is still `.pack()`ed by its parent card (`hk`, `cl`, `eat_card_inner`, `ap`,
`up` — confirmed via `grep`, all 10 call sites unchanged). `row.control`'s
own children (`NumBox`, `Segmented`, `hotkey_label`, `version_label`) are all
`.pack()`ed into `row.control`, a separate container from `Row` itself. So
three distinct containers are involved (`Row` uses grid for its own two
children; the parent card uses pack for the `Row`; `row.control` uses pack
for its own children) and no container ever receives both `grid()` and
`pack()` calls on children within itself. No conflict is possible from any
existing call site, and the shape of the class (only `Row.__init__` can add
children to `self`) makes a future conflict structurally hard to introduce
by accident.

## Item 2 — ratio-invariance deviation, and the untested (smaller-s) direction
Independently reproduced the developer's own numbers exactly: at this
environment's native `_dpi_s = 1.0423`, the "UI scale" row's `Segmented`
right edge sits at 387px inside a 415px card at the 100% step — bit-for-bit
what `docs/implementation.md` reports. The ratio-invariance argument (every
quantity scales by the same `s`, so a check at `s=1` bounds every step)
holds for the tested direction.

For the **untested direction** (macOS `_dpi_s ≈ 0.75`, ticket #23): I
injected `root.tk.call("tk", "scaling", dpi*1.333)` before constructing a
**fresh** `AfkAutoclicker` (this is exactly how `self._dpi_s` is computed at
`afk_clicker.py:1478`, so it's exercising the real code path, not a mock),
with the store's `ui_scale` pre-set to each of 90/100/115/130 so every
measurement is a genuine from-launch floor size, not a residual window left
over from a previous scale. Result — no overflow anywhere, margins actually
still comfortably positive at every combination:

```
dpi_target=0.75  scale=90  s=0.6745  margin=18px
dpi_target=0.75  scale=100 s=0.7494  margin=24px
dpi_target=0.75  scale=115 s=0.8619  margin=23px
dpi_target=0.75  scale=130 s=0.9743  margin=27px
dpi_target=1.0   scale=90  s=0.8993  margin=25px
dpi_target=1.0   scale=100 s=0.9993  margin=30px
dpi_target=1.0   scale=115 s=1.1492  margin=31px
dpi_target=1.0   scale=130 s=1.2990  margin=35px
```

So the developer's reasoning holds independently in the direction they
didn't test too — the smaller-`s` (macOS) case is not tighter, it's actually
the tightest-looking of the low end (18px at 0.75/90%) but still solidly
positive, consistent with the ratio argument (real rendered margin isn't
purely proportional to `s` because `card()`'s own fixed non-scaled chrome
adds a roughly-constant few pixels on top of the scaled arithmetic, which is
why every measured margin is a bit *looser* than the constant-only 24px
figure in the spec, matching the developer's own "looser, not tighter"
finding).

**One real, non-blocking gap surfaced while building the above**: the
`_apply_minsize(grow_only=True)` mechanism (`afk_clicker.py:1558-1579`)
means a window's actual size never shrinks when the UI scale is switched
down mid-session. The spec's own acceptance criterion (and the developer's
test, `test_ui_scale_row_never_overflows_its_card_at_any_scale_step`) calls
`self.ui._apply_ui_scale("90"/"100"/"115"/"130")` in that literal sequence
on one already-built `UITestCase` instance (which starts at the store
default, 100%). Because 90% is asked for *first* and is smaller than the
instance's starting 100% floor, that step's measurement is actually taken
against the still-100%-sized card, not against 90%'s own true (tighter)
floor — the test never actually exercises a fresh 90%-from-launch window.
This mirrors real single-session behavior faithfully (a user switching down
from 100% genuinely keeps the larger window too), so there is no live
defect — confirmed above, the true fresh-launch floor at 90% (and even at
0.75×90%) still holds with real margin. But the test's own implicit claim of
covering "each step" is weaker than it reads for the smallest step
specifically. This is inherited from the spec's own literal phrasing of the
acceptance criterion (`self.ui._apply_ui_scale("90"/...)` in that order), not
a developer deviation — flagging as a **should-fix / follow-up**, not a
blocker: a future pass could build one fresh instance per scale value (same
technique `UIScaleStore` already uses — write `ui_scale` into the settings
file before construction) to genuinely test each step's own floor.

## Item 3 — Hotkey card's Record/Apply buttons
Confirmed via direct measurement at the 900x760 stretched size: `btns`
(`afk_clicker.py:1832-1837`) is packed directly into the Hotkey card `hk`,
not into a `Row`, and its two `Button`s are packed `side="left"`/`side="right"`
with no fixed width — so they span edge-to-edge of the card exactly (`btns`
width == card width == 627px at 900x760; `Record` starts at x=0, `Apply`'s
right edge lands at x=627, both flush to the card's actual edges). This is
**unchanged, pre-existing code** — not present in `git diff`, and explicitly
out of scope per `docs/spec.md`'s own Non-goals ("No new `Row` call sites,
no change to which controls exist"). It is a real, visible inconsistency
once the Rows directly above it hold a fixed value-column offset instead
of also tracking the card's edge, but it is not a regression this feature
introduced and fixing it here would violate this feature's stated scope
(`Row`-only, no other class changes shape or behavior).

**Judgment**: defer, don't fix here. Of the two candidates offered, this
reads as **Feature 5's** territory rather than Feature 4's: it is a purely
horizontal-alignment/chrome question (should a lone button pair span full
card width, or sit in a bounded column like everything above it), not a
vertical-space-fill question, and Feature 5 is explicitly the pass that
touches `Button` styling and card proportions together with the rest of the
chrome. `docs/story.md` does not currently mention this observation anywhere
(checked the Feature 3/Feature 5 rows and the Decisions section) — flagging
it here so it reaches the product-manager for the next cycle; it is not
something this review is positioned to write into `docs/story.md` directly
(that document belongs to product-manager, not reviewer).

## Spec coverage
All acceptance criteria in `docs/spec.md` are implemented and covered by an
executed test (automated for 1-5,7,8 above; manual/geometric for 6, which
has no existing automated-test hook for row-to-row spacing and wasn't asked
to add one). No criterion found unimplemented or untested.

## Findings (most severe first)

### 1. UI-scale-step test doesn't exercise each step's own fresh floor — should-fix
- File: `tests/test_ui.py:812-828` (`test_ui_scale_row_never_overflows_its_card_at_any_scale_step`)
- Issue: iterates `_apply_ui_scale("90","100","115","130")` sequentially on
  one `UITestCase` instance that starts at the store's default 100%.
  `_apply_minsize(grow_only=True)` (`afk_clicker.py:1558-1579`) never shrinks
  the window, so the "90" iteration measures against the residual
  100%-sized card, not 90%'s own tightest floor.
- Failure scenario: if a future change made the 90%-from-fresh-launch case
  specifically too tight (e.g. a wider control added at a size that only
  overflows at the smallest scale factor, launched fresh), this test would
  still pass, because it never actually renders that scenario. Confirmed
  independently (see Item 2) that today's actual fresh-90% floor is fine —
  this is a coverage gap, not a live bug. Inherited from the spec's literal
  acceptance-criterion phrasing, not a test-authoring mistake.
- Non-blocking: recommend a follow-up (not required for this feature) to
  build one fresh app instance per scale value, mirroring
  `UIScaleStore`'s technique of pre-writing `ui_scale` into the settings file
  before construction.

### 2. Hotkey card's Record/Apply buttons span full card width — note for later, not this feature
- File: `afk_clicker.py:1832-1837` (unchanged by this diff)
- Not a defect in Feature 1 — explicitly out of scope per spec Non-goals.
  Recorded here (see Item 3 above) so it isn't lost before Feature 5's spec
  stage.

No must-fix findings. No security-relevant surface in this diff (pure Tk
layout, no I/O, no untrusted input, no new persisted data).

## Follow-ups (non-blocking)
- Rebuild `test_ui_scale_row_never_overflows_its_card_at_any_scale_step` (or
  add a sibling test) using a fresh instance per scale value so the smallest
  step's own floor is genuinely exercised (Finding #1).
- Decide, at Feature 5's spec stage, whether the Hotkey card's Record/Apply
  buttons should gain a bounded/aligned width consistent with the
  now-fixed-column Rows above them (Finding #2 / Item 3).

## Overall verdict
**Approve with follow-ups.** Testing pass is clean (245/245, two runs, zero
existing tests modified) and every acceptance criterion in `docs/spec.md` is
implemented and covered by an executed test. Review pass found no must-fix
issues: the `grid`/`pack` split is genuinely conflict-free, the developer's
ratio-invariance reasoning holds independently in both the tested and the
untested (macOS-direction) case, and the diff is minimal and matches the
file's existing conventions (comment style, constant placement, no new
abstractions, no call-site churn). The two items above are real but
non-blocking: a test-coverage nit for the smallest UI-scale step, and a
pre-existing visual inconsistency (Hotkey buttons) that is correctly out of
this feature's scope and belongs at Feature 5.

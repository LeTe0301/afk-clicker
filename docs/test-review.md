# Test & Review: Content fills the available vertical space (story #24, Feature 4 of 5)

## Scope
Testing + review pass over `feature/ac-24/responsive-layout-icon-restyle` at
HEAD `5f46abd` (base `23e6658`), against `docs/spec.md`'s acceptance criteria,
`docs/design.md`'s `FILL_TOP_SHARE = 0.5` treatment, and `docs/implementation.md`'s
own stated deviations/limitations. Diff: `afk_clicker.py` (+145/-2), new
`VerticalFill` test class in `tests/test_ui.py` (+133).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Floor case: tallest pane's spacers are an exact no-op (≤1px) | Automated + independent probe | **N/A — criterion is false given today's `minh`, correctly documented as a deviation** | See "Floor-case deviation" below |
| 1b | Floor case: split stays symmetric and sums to the real (nonzero) leftover, no clipping | `test_floor_case_still_splits_symmetrically_with_no_clipping` | pass | `unittest tests.test_ui.VerticalFill -v` → ok |
| 2 | Tall window: short tab's spacers > 0, sum == available − natural | `test_short_tab_gains_margin_on_a_tall_window`, `test_top_and_bottom_spacers_sum_to_the_real_leftover_space` | pass | same run, both ok |
| 3 | Per-pane fill: Hotkey's margin > Clicking's | `test_switching_tabs_recomputes_each_panes_own_margin` | pass | same run, ok |
| 4 | Eating toggle recomputes Clicking's margin, no resize | `test_toggling_eating_recomputes_the_clicking_panes_margin` | pass, **and independently confirmed to be a real regression test** | own probe: reverting the explicit `_fill_pane()` call in `_select()` (`afk_clicker.py:2566-2567`) makes this exact test fail (`273 not greater than 273`) |
| 5 | Hidden-tab guard prevents cross-pane writes | `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` | pass, **but does not actually exercise the guard** — see Finding 1 | own probe: removing the `self._content_tab == "clicking"` guard entirely still passes this test |
| 6 | Live resize drag: spacer heights track final size, zero `_rebuild_ui` calls | `test_live_resize_drag_updates_margin_without_a_rebuild` | pass | same run, ok; independently reproduced with a raw 50-step resize drive (see below) |
| 7 | Full suite passes at baseline + new tests, none modified | `discover -s tests -t .` | pass | 276 tests, `OK (skipped=5)`, run twice this session (see Regression check) |

### The five flagged concerns — independently verified, not just read

**1. Floor-case criterion #1 vs. its rewritten test.** Reproduced the
developer's ~148px claim directly against the **base commit `23e6658`**
(before this feature existed at all), not HEAD: built the app from a copy of
`23e6658:afk_clicker.py` in a scratch dir, selected the Minecraft profile,
switched to the Clicking tab at the default (minsize) window, and measured
`clicking_pane.winfo_height()` vs. the real rendered span of its children:

```
window geometry: 689x719+0+0
pane winfo_height: 528
span (max y+h - min y) = 380
pane height - span = 148
```

148px of leftover space at the floor, on the unmodified pre-feature code —
confirms this is genuinely pre-existing, not introduced by this feature.
Cross-checked against `docs/history/ac-14-design.md:47`, which states `minh`
was tuned "to the Minecraft profile's taller eating card" for the old
single-page layout, before Feature 2 (this story) ever split it into
independent tab panes — consistent with the developer's traceability claim.
**Conclusion: the rewrite from "no-op ≤1px" to
`test_floor_case_still_splits_symmetrically_with_no_clipping` is correct; the
spec's own criterion #1 was invalidated by Feature 2, not by this feature.**

**2. Three reference-code bug fixes, each independently verified:**
- **(a) `natural` as rendered span, not `reqheight` sum.** Reproduced the
  exact discrepancy on HEAD's Hotkey pane: `reqsum=109`, `span=115`, `diff=6`
  at `s≈1.043` — matches `section()`'s own `pady=(0, int(6*s))`
  (`afk_clicker.py:1380`, called with `top=0` for Hotkey at
  `afk_clicker.py:2172`) to the pixel. The fix is real and precise, not a
  guess.
- **(b) `pack_propagate(False)` breaking a genuine feedback loop.** Built two
  variants of HEAD's `afk_clicker.py` in scratch dirs — one unmodified, one
  with the four new `pack_propagate(False)` calls commented out — and
  instrumented `_fill_pane` with a call counter. Construction: **3 calls
  with the fix vs. 19 without** (confirms a real, bounded feedback loop at
  startup, matching the developer's "over a dozen calls" claim almost
  exactly). A subsequent 50-step synthetic resize drag produced **exactly 50
  calls in both variants** — no runaway/hang in either case in this
  synthetic scenario, but the fix measurably reduces spurious recomputation
  at construction, which is the concrete case the developer's own comment
  cites.
- **(c) `max(1, ...)` floor because `config(height=0)` is a no-op in Tk.**
  Isolated probe: `Frame(height=100)` → `config(height=0)` → still reports
  `winfo_height()==100`; `config(height=1)` applies immediately. Confirms Tk
  really does treat a literal `0` as "unset," not "0px" — the floor is a
  necessary fix, not cosmetic rounding.

**3. `_select()`'s `before=clicking_bottom` fix.** Reproduced the bug by
reverting just this one line pair to the pre-fix plain `.pack()` calls on a
HEAD copy, then drove `_select("minecraft")` → `_select("global")` →
`_select("minecraft")` cycles and printed `clicking_pane.pack_slaves()`
order each time:
- **With the fix:** `[TOP, other, eat_section, eat_card, BOTTOM]` — stable
  across three repeated cycles.
- **Without the fix:** first Minecraft selection already produces
  `[TOP, other, BOTTOM, eat_section, eat_card]` — the bottom spacer jumps
  above the Eating card on the very first `pack_forget()`→`pack()` cycle,
  exactly as the developer describes, and exactly on the app's own default
  startup path (default game is non-eating, so the very first game switch to
  a Minecraft-profile game hits this).

  This fix is real and is specifically required *by this feature* — the
  bottom spacer is a new widget this feature introduces after Eating for the
  first time, so nothing pre-existing had ever needed a positional pin
  there. Judged as necessary scope, not creep. It changes zero pre-existing
  behavior/value, only pack ordering of widgets this feature itself added
  alongside pre-existing ones.

**4. Feedback-loop termination under continuous resize.** Drove a raw
50-step resize drive (`700→945` in steps of 5, real `root.geometry()` calls
+ `root.update()` each step, no synthetic shortcuts) against HEAD's actual
built app: exactly 50 `_fill_pane` calls for 50 `<Configure>` events, no
multiplication, elapsed 0.083s. `update_idletasks()`-before-measuring plus
`pack_propagate(False)` genuinely terminates; no hang observed.

**5. Trigger 3 (Eating toggle) genuinely fires and refills, on a real
profile.** `_select("minecraft")`/`_select("global")` in the test suite and
in my own probes are real `PROFILES` entries (`afk_clicker.py:923-943`,
`eating: True`/`False` respectively) — not synthetic bypass values. Reverting
the explicit `_fill_pane()` call in `_select()` makes
`test_toggling_eating_recomputes_the_clicking_panes_margin` fail
(`273 not greater than 273`), confirming the test genuinely exercises the
fix rather than passing vacuously.

## Regression check
Full existing suite: `DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .`
Run twice this session:
- Run 1: `Ran 276 tests in 61.150s` — `OK (skipped=5)`
- Run 2: `Ran 276 tests in 61.265s` — `OK (skipped=5)`, exit 0

No `Tcl_AsyncDelete` flake observed in either run. `VerticalFill` run in
isolation: `Ran 7 tests in 0.777s — OK`. No pre-existing test was modified
(confirmed by diff: only new class added to `tests/test_ui.py`).

No defects block approval — proceeding to the review pass.

---

## Spec coverage

| Acceptance criterion | Implemented | Tested | Notes |
|---|---|---|---|
| Floor case: exact no-op ≤1px | No — factually impossible given today's `minh` | Rewritten test covers the invariant this feature *can* own | Verified independently against base commit; correct deviation, well-documented |
| Tall window: short tab gains margin, sum == available−natural | Yes | Yes | True-by-construction assertion, verified |
| Per-pane fill (Hotkey vs Clicking differ) | Yes | Yes | Verified |
| Eating toggle recomputes Clicking's margin, no resize | Yes | Yes | Verified as a genuine regression test (revert-and-fail check) |
| Hidden-tab guard prevents cross-pane writes | Yes (guard exists) | **Weakly** — test passes even with the guard removed | See Finding 1 |
| Live resize, zero `_rebuild_ui` calls | Yes | Yes | Verified with an independent raw resize drive |
| Full suite passes, no existing test modified | Yes | Yes | Confirmed, two runs |

No acceptance criterion is silently unimplemented or unaddressed. One
(floor case #1) required a judgment call the developer made transparently
and I've independently corroborated as correct. One (hidden-tab guard) has
a real but non-blocking test-quality gap (Finding 1).

## Findings (most severe first)

### 1. `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` does not test what its docstring claims — should-fix
- File: `tests/test_ui.py:1096-1106` (test), guard at `afk_clicker.py:2566`
- Issue: the test's own docstring says it must prove "the guard actually
  prevents a cross-pane write, not merely happen to not crash." Empirically
  (see Test cases #5 above), removing the `self._content_tab == "clicking"`
  guard entirely — i.e. always calling `_fill_pane(*self._pane_fills["clicking"])`
  regardless of which tab is active — still passes this test. That's because
  `_fill_pane(pane, top, bottom)` can only ever write to the exact
  `pane`/`top`/`bottom` arguments passed to it; calling it for `"clicking"`
  structurally cannot touch `hotkey_pane`'s spacers no matter what the guard
  does. The guard's real, documented purpose (spec's Empirical grounding,
  `docs/spec.md:284-290`) is to avoid computing *clicking's own* spacers from
  a hidden pane's stale-but-plausible geometry — not to prevent writes to
  other panes. The spec's own acceptance-criterion wording ("prevents
  cross-pane writes") is itself imprecise here, and the developer faithfully
  translated it into a test that is technically true but doesn't regress-test
  the guard.
- Failure scenario: a future refactor that accidentally removes or inverts
  the `self._content_tab == "clicking"` guard would pass the full suite
  clean — this specific hazard class (recomputing a hidden pane's spacers
  from stale geometry) has no automated coverage. The risk is low in
  practice (spec's own edge-case note: staleness self-corrects on the next
  tab switch and is never read while stale), so this is a should-fix, not a
  blocker.
- Suggested direction (not a fix I'm making): assert something that actually
  depends on the guard, e.g. spy on `_fill_pane` call args and assert it's
  never invoked with the clicking pane while Hotkey is active, or assert
  `clicking_pane`'s own spacers are *not* recomputed to a value consistent
  with its true available height while hidden.

## Follow-ups (non-blocking)
- The residual dead band (design.md's own admitted limitation: this halves,
  not eliminates, the empty band) and the `minh` re-tuning question
  (design.md's "Open question: window minimum height") are both already
  correctly filed as backlog-level follow-ups, not this feature's scope.
- Finding 1 above is a test-hardening opportunity, not required before
  merge.

## Overall verdict
**Approve with follow-ups.** The testing pass is clean (276/276 relevant
tests + 7 new, run twice, zero regressions), all acceptance criteria are
either correctly implemented-and-tested or transparently and correctly
deviated-from with independent verification, and all five flagged
higher-risk areas (floor-case claim, three reference-code bug fixes, the
`before=` pack-ordering fix, feedback-loop termination, and the silent
Eating-toggle trigger) held up under direct, hands-on reproduction — not
just re-reading the developer's prose. The one finding (hidden-tab guard's
test not actually exercising the guard) is a should-fix, not a blocker: the
underlying behavior is provably correct today and the risk window is narrow
and self-correcting per the spec's own reasoning.

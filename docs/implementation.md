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

## Round 2 (docs/test-review.md, Defect 1 — blocking)

The round-1 testing pass found the pane-refill reentrancy dismissed as a
test-harness artifact in "Deviations from spec" above was in fact
observable in the live, running app: at `WINDOW_MIN_H = 560`, the Minecraft
+ Clicking pane's spacers could settle on a wrong, permanently-lopsided
split, and in one of the two ordinary click orders (Clicking tab clicked
first on the default Global profile, then Minecraft selected), Tk's packer
outright unmapped the bottom spacer and left the Eating card's "Hold for"
row sliced off the bottom edge of the window — genuine, unreachable content
clipping, not decorative asymmetry, confirmed stable after 2+ real seconds
of continuous event-loop servicing. `_fill_pane()`/`card()` were
respecified as in-scope at the app level by the review; fixed there, not in
the test suite.

### Root cause, fully traced

`eat_card` (the Eating section's `card()` shell/canvas) is built once, at
app-construction time, and its rows never change afterward — only its
*pack state* toggles, via `_select()`'s `eat_card.pack(...)` /
`pack_forget()`. Instrumenting `_fill_pane()` and `card()`'s `_redraw()`
directly against the running app (throwaway probe, not committed) showed
that re-packing an already-built `eat_card` does **not** give it its final
on-screen height synchronously: Tk hands it a placeholder geometry first
(`winfo_height()` well below its real `reqheight`), then `card()`'s own
`shell.bind("<Configure>", _redraw)` handler grows it toward its real
height across several more *idle-queued* steps (observed: ~6 rounds,
`eat_card`'s height stepping 129→141px while `natural` climbed
196→383px). `_select()`/`_set_content_tab()`'s own explicit `_fill_pane()`
call happens once, synchronously, and nothing re-triggered it once those
later idle-queued `_redraw()` steps actually landed — toggling a child's
pack state inside an already-`expand=True`, `pack_propagate(False)` pane
produces no `<Configure>` on the pane itself (the same "Empirical grounding
#2" the code already documents for a different call site), so the pane's
spacers stayed baked to whatever `_fill_pane()` measured *before* the card
finished growing. At the old, much larger `690`-based floor this stale
measurement still summed correctly by luck (enough leftover margin that a
too-small `natural`'s resulting oversized spacers never exceeded the
pane's real height); at `560`, the same staleness produces a genuinely
larger, wrongly-sized `extra` than the pane can actually hold once the
card finishes growing, which is exactly the overflow that made the packer
give up on mapping the bottom spacer.

### Fix chosen, and why

Added an optional `on_settle` callback to `card()`, invoked at the tail of
every `_redraw()` call — i.e. every single time a card's shell actually
finishes resizing to a new real height, including from an idle callback
serviced after whatever caller originally triggered it has already
returned. Wired only for `eat_card`
(`self.eat_card_inner = card(self.clicking_pane, s,
on_settle=self._on_eat_card_settled)`), whose new `_on_eat_card_settled()`
method re-runs `_fill_pane()` for the `clicking` pane, guarded on
`self._pane_fills.get("clicking")` existing yet (it doesn't during
`eat_card`'s own construction-time `_redraw()` call, before
`_build_content()` populates that dict) and on `self._content_tab ==
"clicking"` (the same unmapped-pane guard `_select()`'s own tail already
uses).

This was chosen over the review's other two offered directions:
- **A defensive clamp on `_fill_pane()`'s own math** cannot fix this by
  itself: the overflow isn't caused by a rounding error in how `extra` is
  split, it's caused by `natural` itself being measured too small at
  call time. A clamp operating on that same stale `natural` can only ever
  prevent the *numeric* sum from exceeding `available` — it cannot know
  the eventual, correct height, so it would still bake in a wrong
  (clipped-adjacent or asymmetric) split, just without the packer visibly
  giving up on a spacer. It trades one visible symptom for a quieter,
  still-wrong one.
- **Re-measuring once, after a fixed extra pass**, from inside
  `_select()`/`_set_content_tab()`, was rejected as strictly worse than
  hooking `card()` directly: it would need to guess how many extra
  `update()`/`update_idletasks()` rounds are "enough" (the observed ~6
  rounds is itself empirical, not a guaranteed bound), and it would only
  cover the two call sites that happen to call `_fill_pane()` explicitly
  today, not any future one.
- The chosen fix ties the recompute to the actual event that was silently
  going unheard (the card's own settle), so the invariant "the pane's
  spacers reflect the card's true final height" holds **by construction**,
  not probabilistically: as long as `card()`'s `_redraw()` converges to a
  fixed height (guaranteed here — `eat_card`'s children are static once
  built), the last `on_settle()` call it makes is guaranteed to leave
  `_fill_pane()` holding the correct, final `natural`. This is not an
  unbounded retry: `_on_eat_card_settled()`'s own call to
  `_fill_pane()`'s `pane.update_idletasks()` further drains the remaining
  settle steps within the same synchronous call in every case probed, so
  in practice `_select()`/`_set_content_tab()`'s own explicit call already
  returns fully converged — no residual staleness is left for a future
  frame to paper over.

### Verification — live app, both orders, not the suite

Ran a throwaway script (`screenshot_round2.py`, scratchpad only) that
builds the real app, drives both click orders, services the event loop
continuously for 2 real seconds exactly like the review did, and takes a
screenshot via `import -window <id>` on a private Xvfb display:

- **Order A** (`_select("minecraft")` then `_set_content_tab("clicking")`):
  `natural=383, pane_h=392, top=4, bottom=5`, both spacers mapped, not
  clipped. Screenshot: `round2_orderA.png` — "Hold for" fully visible with
  clean margin below it.
- **Order B** (`_set_content_tab("clicking")` first on Global, then
  `_select("minecraft")` — the branch that produced real clipping before
  this fix): identical result, `natural=383, pane_h=392, top=4, bottom=5`,
  both spacers mapped, not clipped. Screenshot: `round2_orderB.png` —
  pixel-identical layout to order A.

Both screenshots taken after 2 full seconds of continuous `root.update()`
churn, matching how the review caught the original defect. Also
re-confirmed order B no longer unmaps the bottom spacer even *before* that
2-second settle window: `bottom.winfo_ismapped()` is `True` immediately
after `_select("minecraft")` returns.

### Floor value re-checked

The fix changes *when* `_fill_pane()` recomputes, not how much space any
pane's content actually needs, so `WINDOW_MIN_H = 560` itself does not
need to move. Re-ran both derivation measurements against the fixed code,
both orders:
- Native scale (`s ≈ 1.043` on this box): `natural = 383px` — identical to
  the round-1 measurement and to the spec's own number.
- Compound worst case (`ui._dpi_s = 0.75; ui._apply_ui_scale("90")`,
  `s ≈ 0.675`): `natural = 254px`, fits within the pane's `458px` at this
  scale — identical to the round-1/spec measurement, both orders.

No change to the constant.

### Test changes

- `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping`:
  **removed the bounded settling loop added in round 1.** Per the review's
  must-fix #3: the loop is no longer needed — the very first
  `_fill_pane()` call (from `_set_content_tab()`) now already returns
  fully converged, confirmed by 5 back-to-back runs. Its removal, not its
  continued necessity, is the evidence this fix addressed the actual race
  rather than papering over it again.
- Added `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping_reverse_order`
  and `WindowMinimumHeight.test_tallest_pane_still_fits_at_the_floor_reverse_order`:
  order B (`_set_content_tab("clicking")` before `_select("minecraft")`)
  coverage for both the symmetric-split invariant and the floor-fit
  invariant, per the review's must-fix #2. The floor-fit reverse-order test
  additionally asserts both spacers stay mapped, directly targeting the
  packer-gives-up-on-a-widget symptom the review actually observed (a
  `natural <= winfo_height()` check alone would not have caught an
  *unmapped* spacer).
- `card()`'s new `on_settle` parameter required updating
  `ReentrantAppearanceChangeDuringRebuild.test_appearance_change_fired_from_inside_a_rebuild_does_not_crash`'s
  `patched_card` shim (`tests/test_ui.py`) to accept and pass through the
  new keyword — a signature-ripple fix, not a logic change; caught
  immediately by the full suite (`TypeError: ... got an unexpected keyword
  argument 'on_settle'`) before any manual review was needed.

### Verification run

```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
# Ran 291 tests (289 baseline + 2 new reverse-order tests) -- OK (skipped=5), run twice back-to-back.

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.WindowMinimumHeight \
    tests.test_ui.VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping \
    tests.test_ui.VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping_reverse_order -v
# 7/7 green, run 5x back-to-back for determinism.
```

Live-app verification (both click orders, 2-second settle, screenshots) is
described above; no code change is required to re-run it, a throwaway
script suffices (`screenshot_round2.py`, not committed).

### Known limitations (round 2)

- `on_settle` fires on every `_redraw()` for `eat_card`, including ones
  triggered by an ordinary window resize while Minecraft/Clicking is
  showing — each now makes one extra (idempotent) `_fill_pane()` call.
  `_fill_pane()`'s own docstring already documents it as safe to call
  repeatedly, including from a live resize drag; no measurable cost
  observed (full suite runtime unchanged, ~57s before and after).
- The nested `update_idletasks()` recursion this fix relies on to drain
  `eat_card`'s settle steps within one synchronous call is bounded by how
  many idle rounds Tk's own geometry manager needs to converge
  `eat_card`'s height (observed: ~6, on this box) — not by an explicit
  iteration cap. This is the same class of reentrancy `_fill_pane()`'s own
  docstring already documents and tolerates elsewhere; not new risk
  surface introduced by this fix.
- Same cross-platform font-metrics caveat as round 1: verified on
  Linux/Xvfb with a substituted font; the construction-true tests (not a
  fixed pixel value) are what actually catches a platform where the
  numbers differ, on whichever platform's CI run actually exposes it.

## Round 3 (PR #49 review) -- diagnostic only, not a fix

`windows-latest` fails the two reverse-order tests added in round 2
deterministically, on both CI runs against this branch, while Linux never
has in any order probed across three rounds and this box has no Windows
target to reproduce against directly. Per the review's own instruction,
this round adds instrumentation and gathers data -- **it changes no
production code and no assertion's meaning**; nothing here is a candidate
fix.

### What changed

`tests/test_ui.py` only:

- A new module-level diagnostic block (placed right before `FakeMouse`,
  clearly bannered `# --- G#28/GH#48 round-3 diagnostic (PR #49),
  temporary ---` / `# --- end round-3 diagnostic ---` for easy removal in
  round 4 regardless of outcome):
  - `_diag_trace_fill_pane(ui, label)`: a context manager that monkeypatches
    the module-level `app._fill_pane` for its duration. Every call prints,
    to stdout, which pane it targeted, who called it, and the resulting
    state -- `available`/spacer heights/mapped flags/`eat_card`'s own shell
    height and mapped state. "Who called it" is read from the live call
    stack (`traceback.extract_stack()`), not from instrumenting
    `_on_eat_card_settled` directly: `card()`'s `on_settle` parameter is
    captured **by value** into its own closure at app-construction time
    (`UITestCase.setUp()`, before either the test method or this patch
    exist), so patching `ui._on_eat_card_settled` or the class method after
    construction would silently never fire for that already-built closure.
    Patching the *global* `_fill_pane` function works because every call
    site (`_select()`, `_set_content_tab()`, `_on_eat_card_settled()`, and
    each pane's own `<Configure>`-bound lambda) resolves the bare name
    `_fill_pane` from the module's globals at call time, which is exactly
    what monkeypatching `app._fill_pane` rewrites.
  - `_diag_pump_and_report(root, ui, label, rounds=10)`: after the sequence
    under test already returned, drains the event loop 10 more times,
    printing the clicking pane's live natural/extra/spacer state each
    round. This does **not** call `_fill_pane()` itself -- it is a passive
    probe of whether Tk needed more idle passes than the harness's own
    single `root.update()` gave it, not a second mitigation layered on top
    of the one being diagnosed.
- `WindowMinimumHeight.test_tallest_pane_still_fits_at_the_floor_reverse_order`
  and `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping_reverse_order`:
  wrapped their `_select()`/`_set_content_tab()`/`root.update()` sequence in
  `_diag_trace_fill_pane(...)`, added a post-update diagnostic print and a
  `_diag_pump_and_report(...)` call, and **replaced their final
  `self.assertX(...)` calls with equivalent `if not <condition>: print("...
  RESULT: FAIL ...")` checks** -- per the review's explicit instruction, so
  a real failure (Windows) no longer stops the test method before its own
  diagnostic prints are flushed, and so the CI job's overall result no
  longer depends on whichever platform is mid-diagnosis. No other test in
  the suite was touched, and neither test's setup/sequence of calls
  changed -- only how their outcome is reported.

### Why this is safe to read as "the same bug, now narrated"

Re-ran the full suite and both instrumented tests individually on
Linux/Xvfb (this box's only available platform) to confirm the patch
changes no behavior:

- Full suite: `291 tests ... OK (skipped=5)`, run twice back-to-back.
- Both instrumented tests print a clean, fully-converged trace and report
  no `RESULT: FAIL` lines, matching their previous (round-2) green
  behavior on this platform.

The Linux trace is worth reading before the Windows one comes back,
because it's the "this is what convergence looks like when it works"
baseline to diff Windows against. Captured verbatim (call numbering is
completion order, since each wrapper's own print happens after
`update_idletasks()`-triggered reentrant sub-calls have already returned --
not invocation order):

```
DIAG[floor-fit-reverse] call#1 pane=clicking caller=_set_content_tab available=393 top_h=1 bottom_h=1 top_mapped=0 bottom_mapped=0 eat_card_h=130 eat_card_mapped=0
DIAG[floor-fit-reverse] call#2 pane=clicking caller=_set_content_tab available=393 top_h=196 bottom_h=1 top_mapped=1 bottom_mapped=0 eat_card_h=130 eat_card_mapped=0
DIAG[floor-fit-reverse] call#3 pane=clicking caller=_set_content_tab available=393 top_h=98 bottom_h=94 top_mapped=1 bottom_mapped=1 eat_card_h=130 eat_card_mapped=0
DIAG[floor-fit-reverse] call#4 pane=clicking caller=_on_eat_card_settled available=393 top_h=96 bottom_h=94 ... eat_card_h=55  eat_card_mapped=0
DIAG[floor-fit-reverse] call#5 pane=clicking caller=_on_eat_card_settled available=393 top_h=78 bottom_h=94 ... eat_card_h=73  eat_card_mapped=1
DIAG[floor-fit-reverse] call#6 pane=clicking caller=_on_eat_card_settled available=393 top_h=39 bottom_h=94 ... eat_card_h=112 eat_card_mapped=1
DIAG[floor-fit-reverse] call#7 pane=clicking caller=_on_eat_card_settled available=393 top_h=19 bottom_h=94 ... eat_card_h=132 eat_card_mapped=1
DIAG[floor-fit-reverse] call#8 pane=clicking caller=_on_eat_card_settled available=393 top_h=9  bottom_h=94 ... eat_card_h=141 eat_card_mapped=1
DIAG[floor-fit-reverse] call#9 pane=clicking caller=_on_eat_card_settled available=393 top_h=5  bottom_h=1  ... eat_card_h=141 eat_card_mapped=1
DIAG[floor-fit-reverse] call#10 pane=clicking caller=_select              available=393 top_h=5  bottom_h=5  top_mapped=1 bottom_mapped=1 eat_card_h=141 eat_card_mapped=1
DIAG[floor-fit-reverse] post-update natural=383 avail=393 top_h=5 bottom_h=5 top_mapped=1 bottom_mapped=1
DIAG[floor-fit-reverse] pump#0..9  natural=383 avail=393 extra=10 top_h=5 bottom_h=5 (unchanged for all 10 pumps)
```

Reading it: `_set_content_tab("clicking")` alone (on the still-default
Global profile, eat_card not yet packed) produces calls #1-3 -- the
pane's own first layout pass, converging on a provisional, symmetric-ish
split against `eat_card`'s *stale* 130px placeholder height. `_select
("minecraft")` then packs `eat_card`, and within that **one** explicit
`_fill_pane()` call, `pane.update_idletasks()` drains the entire
`card()`-growth cascade reentrantly -- six more `_on_eat_card_settled()`-
triggered recomputes (calls #4-9, `eat_card_h` climbing 55->141 as its real
content lays out) followed by the outer call's own final write (#10) --
before `_select()` ever returns. Ten additional passive `root.update()`
pumps afterward change nothing: the state was already at its fixed point.
This is the same 129->141px / ~6-round cascade round 2's own trace
described, now captured as data instead of paraphrased from a throwaway
probe.

### What this predicts for the Windows trace, and what would falsify it

If Windows converges the same way, the trace should look like the one
above modulo pixel values (larger `eat_card_h`/`natural` from taller Segoe
UI metrics), and no `RESULT: FAIL` lines. If Windows instead reproduces the
reported `77 != 2` / unmapped-bottom-spacer failure, the trace should show
**one of two shapes**, and which one appears matters for round 4:

1. **The cascade stops early** -- e.g. the last printed call is still an
   `_on_eat_card_settled` mid-growth state (`eat_card_h` well below its
   Linux-analogous converged value), with no further calls and no pump
   round ever showing a different number. This would mean
   `pane.update_idletasks()` on Windows does not drain the *entire* pending
   idle queue in one pass the way it does here -- Tk's own idle-round
   granularity differs, or Windows batches `<Configure>` delivery
   differently for a canvas-hosted child -- and the fix's implicit
   assumption ("one explicit call's own `update_idletasks()` fully drains
   the settle cascade") does not hold on that platform. This is the
   "timing, not the constant" theory the review's evidence pattern
   (`extra` computed fresh at assertion time already says `0`, but the
   spacers are stuck at a much larger stale value) already points toward.
2. **The cascade completes and looks converged, but the final `available`
   is smaller than Linux's 393 relative to `natural`** -- i.e. `extra`
   itself is genuinely 0 or negative once the real Windows font metrics are
   in, and `_fill_pane()`'s `max(0, ...)` floor is doing real work. This
   would mean the *margin*, not the *timing*, is the problem on Windows,
   pointing back to the fallback of raising `WINDOW_MIN_H` rather than
   chasing a race.

Only the CI run itself can say which of these it is; no Windows box was
available in this session to run it directly.

### The clamp question -- opinion, not implemented

The review asks whether `_fill_pane()` should additionally clamp so the
spacers can never exceed the pane's real leftover at write time, as a
safety net *alongside* `on_settle` (not instead of it). **I agree with
adding it, with one refinement on how to think about the risk.**

The round-2 objection to a clamp -- "it can't know the eventual correct
height, so it would bake in a wrong split, just without the packer
visibly giving up on a spacer" -- was made against a clamp used *instead
of* the settle callback, where a wrong-but-silent split could persist
indefinitely with nothing left to ever correct it. That risk mostly
evaporates once it's paired with `on_settle`: the settle callback is what
makes the *final* state correct (proven again by this round's own Linux
trace converging to the identical natural/extra every time), and the
clamp would only ever be visibly active for the same brief mistimed
window the settle callback is already designed to close on its own next
firing. In that role it isn't a second source of truth about the correct
split, it's a hard backstop against `_fill_pane()` ever handing the packer
numbers larger than the space that exists -- which is exactly the
mechanism by which round 2's live-app defect (a spacer outright unmapped)
happened in the first place.

The one place I'd push back slightly on "clamp and don't worry about it":
a clamp must not be allowed to make a test (or a person) believe content
actually *fits* when it doesn't. It doesn't introduce that risk here,
specifically because this codebase's own "not clipped" check
(`natural <= pane.winfo_height()`, in every test above) is already
computed directly from live content geometry, never from the spacer
values -- so a clamp on what the spacers themselves get written to would
have zero effect on whether that check can detect real overflow. The
failure mode a clamp actually forecloses is narrower and purely
about `pack()`'s own behavior: Tk unmapping a widget outright when told to
give it a negative/oversized share of a fixed-height master, which is a
`pack()` implementation detail, not a measure of whether the content
itself overflowed. Given the whole severity class here is "content became
unreachable," making that one specific mechanism impossible by construction
seems worth the small added surface, and I'd scope it minimally: clamp
`top_h`/`bottom_h` so their sum can never exceed `max(0, available - <some
floor per spacer, e.g. 1>)`, keeping the existing `max(1, ...)` floor
intact on each side. Not built this round, per the review's own
instruction to only evaluate it here.

### Fallback assessment

Not reached yet -- this round produced no new CI signal to react to
(diagnostics only were pushed; the Windows run this data is meant to
inform hasn't come back as of writing this). If the round-4 CI trace shows
shape 1 above (cascade genuinely stalls on Windows), the clamp-alongside-
`on_settle` change described above is my recommended next step over either
fallback, since it fixes the actual failure mode (unmapped spacer) without
touching `WINDOW_MIN_H` itself. If it shows shape 2 (margin, not timing),
the conservative-floor fallback from the review's own list is the right
next move instead of another timing-side change.

### Verification run

```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
# Ran 291 tests -- OK (skipped=5), run twice back-to-back.

DISPLAY=:99 <venv>/bin/python -m unittest \
    tests.test_ui.WindowMinimumHeight tests.test_ui.VerticalFill -v
# 13/13 ok (both diagnosed tests report "ok" now that their invariants are
# printed rather than asserted); full DIAG[...] trace visible in stdout for
# both instrumented tests, no RESULT: FAIL line on this platform.
```

### Known limitations (round 3)

- This box has no Windows target, so everything above about Windows is a
  prediction to be checked against the next CI run, not a confirmed
  finding.
- The two instrumented tests no longer fail the build on any platform for
  the duration of this diagnostic round (by design, per the review's
  instruction) -- they must not be left in this state past round 4: once
  the Windows trace is read, the diagnostic block should be removed and
  the original `assertX` calls restored (whether or not the underlying
  timing/margin issue is also fixed), so these two tests go back to
  actually gating CI.

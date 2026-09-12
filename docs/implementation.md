# Implementation: Content fills the available vertical space (story #24, Feature 4 of 5)

## Summary
Each of the four tab panes (`hotkey_pane`, `clicking_pane`, `appearance_pane`,
`updates_pane`) now has a top/bottom spacer pair that absorbs its own real
leftover vertical space, split 50/50 (`FILL_TOP_SHARE = 0.5`), recomputed on
live resize, tab switch, and the Clicking pane's Eating toggle. The mechanism
never touches `_request_rebuild()`/`_rebuild_ui()` — confirmed by a dedicated
test that spies on `_rebuild_ui` across a resize drag and asserts zero calls.
Implementing the spec's own literal reference code surfaced three real,
previously-latent Tk/pack bugs (detailed below); all three are fixed, and the
full suite (269 baseline + 7 new) passes clean twice in a row under Xvfb.

## Changes by file

- `afk_clicker.py`
  - `FILL_TOP_SHARE = 0.5` constant, added next to `COLLAPSED_BADGE_D` (the
    other story #24 sidebar/layout constants).
  - `_fill_pane(pane, top_spacer, bottom_spacer)`, a new module-level
    function placed directly after `card()`, mirroring its
    `update_idletasks()`-then-`winfo_exists()` guard shape. Computes
    `available = pane.winfo_height()` and `natural` as the real rendered
    span (bottom edge minus top edge) of the pane's mapped non-spacer
    children, then splits `extra = max(0, available - natural)` per
    `FILL_TOP_SHARE`. See "Key decisions" below for why `natural` is a span
    measurement rather than the spec's literal `sum(winfo_reqheight())`, and
    why spacer heights are floored at `max(1, ...)` rather than allowed to
    reach a literal `0`.
  - `_build_content(s)`: `self._pane_fills = {}` initialized before the two
    panes are built; `hotkey_pane`/`clicking_pane` each get
    `pack_propagate(False)` (see "Key decisions"), a top spacer `Frame`
    before their first `section()`/`card()` call, a bottom spacer `Frame`
    after their last, a `<Configure>` binding to `_fill_pane`, and an entry
    in `self._pane_fills["hotkey"|"clicking"]`.
  - `_build_settings(s)`: identical treatment for `appearance_pane`/
    `updates_pane`, with its own `self._pane_fills = {}` (each build method
    only ever constructs its own two panes, so there is no cross-page
    dict-sharing hazard — see "Key decisions").
  - `_set_content_tab`/`_set_settings_tab`: one explicit
    `_fill_pane(*self._pane_fills[value])` call added at the tail of each,
    for the newly-active pane — belt-and-suspenders alongside the
    `<Configure>` the `.pack()` call above it already fires.
  - `_select()`: the Eating `pack()`/`pack_forget()` block now passes
    `before=clicking_bottom` on both `eat_section.pack()` and
    `eat_card.pack()` (a real, independently-discovered bug fix — see
    "Deviations from spec"), and is immediately followed by a guarded
    `if self._content_tab == "clicking": _fill_pane(*self._pane_fills["clicking"])`
    — the one trigger with no natural `<Configure>` (spec's Empirical
    grounding #2).
- `tests/test_ui.py`
  - New `VerticalFill(UITestCase)` class (inserted after `RailCollapse`,
    before `RowValueColumn`), 7 tests matching spec's "Test impact" list:
    `test_short_tab_gains_margin_on_a_tall_window`,
    `test_top_and_bottom_spacers_sum_to_the_real_leftover_space`,
    `test_floor_case_still_splits_symmetrically_with_no_clipping` (renamed
    from the spec's proposed `test_no_margin_at_the_minimum_window_size` —
    see "Deviations from spec"),
    `test_switching_tabs_recomputes_each_panes_own_margin`,
    `test_toggling_eating_recomputes_the_clicking_panes_margin`,
    `test_hidden_tabs_own_margin_does_not_desync_the_visible_one`,
    `test_live_resize_drag_updates_margin_without_a_rebuild`.
  - No existing test was modified — confirmed by running the full 269-test
    baseline unchanged before writing any new code, then re-running with the
    7 additions on top (276 total, `OK (skipped=5)`, twice in a row).

## Key decisions / tradeoffs

- **`natural` is measured as a rendered span, not a `reqheight` sum.** The
  spec's own literal reference code (`sum(c.winfo_reqheight() ...)`) ignores
  `pack()`'s own `pady` between a pane's *direct* children — e.g.
  `section()`'s trailing `pady=(0, 6)` on Hotkey's label, or
  `eat_section`'s `pady=(14, 6)` when shown. That pady is real space pack
  consumes but no child's own `reqheight` reports it, so the sum-based
  `extra` came out too large by exactly that pady, and the bottom spacer
  was silently clipped by Tk to fit (confirmed empirically: measured
  `extra=638` vs. the pane's true leftover of `632`, a 6px gap that exactly
  matches Hotkey's own section pady). The fix — `max(y+height) - min(y)`
  over the mapped non-spacer children — counts every pixel pack actually
  spends, is translation-invariant in the top spacer's own current height
  (so it needs no "reset to 0 before measuring" step), and needed no call
  site changes.
- **`pack_propagate(False)` on all four panes.** Without it, a spacer
  resizing (the very thing this feature exists to do) changes the pane's
  own *requested* size, which can cascade into a further geometry pass that
  re-fires the pane's own `<Configure>` — a real, observed feedback loop
  during startup alone (over a dozen `_fill_pane` calls with wildly
  fluctuating `available` values before ever touching the window). This
  mirrors `self.content`'s own existing `pack_propagate(False)` at
  `afk_clicker.py:1966`, same reasoning, now extended to the four tab
  panes it contains.
- **Spacer heights are floored at `max(1, ...)`, never a literal `0`.**
  Confirmed empirically: `Frame.config(height=0)` is silently *ignored* by
  Tk (treated as "no explicit height", not "make it 0px") — a widget
  previously at height 100 stays at 100 after `config(height=0)` +
  `update_idletasks()`, while `config(height=1)` (or any other positive
  value) applies immediately and reliably. Configuring a literal `0` would
  leave a spacer permanently stuck at its last nonzero height when
  shrinking back toward the floor. `max(1, ...)` is exactly the "≤1px"
  tolerance the spec's own acceptance criteria and test-impact section
  already asked for, not a new one.

## Deviations from spec

- **`_fill_pane`'s `natural` computation differs from the spec's literal
  code** (span measurement vs. `reqheight` sum) and **spacer heights are
  floored at 1, never written as a literal `0`** — both are bug fixes to
  the spec's own reference implementation, not design changes; the
  mechanism, triggers, non-goals, and `FILL_TOP_SHARE` value are all
  unchanged. See "Key decisions" for the concrete, empirically-confirmed
  failures each one fixes.
- **`_select()`'s Eating `pack()` calls now pass `before=clicking_bottom`.**
  Not mentioned in spec or design. Confirmed empirically (both in an
  isolated probe and against the app's own real widgets) that Tk's
  `pack_forget()` followed by a later plain `pack()` re-adds a widget at
  the *end* of its master's current packing list, not back where it was.
  Since `clicking_bottom` is a spacer that's never forgotten, the first
  eating→non-eating→eating cycle (reachable from app launch, whose default
  selected game is non-eating) would silently re-pack `eat_section`/
  `eat_card` *after* the bottom spacer — putting the spacer above the
  Eating card instead of below it. `before=clicking_bottom` pins them
  immediately ahead of the spacer regardless of forget/repack history.
  Verified directly: `clicking_pane.pack_slaves()` order stays
  `[top, card, label, eating-card, bottom]` across four repeated
  global→minecraft→global→minecraft switches.
- **Acceptance criterion #1 ("floor case is an exact no-op, both spacers
  ≤1px") does not hold, empirically, and is out of this feature's power to
  fix.** `minh = 690 * s` (`_apply_minsize()`) was tuned by an earlier
  ticket (`docs/history/ac-14-design.md:47`) for the *old*, pre-story-#24
  single content page holding Hotkey+Clicking+Eating all stacked together.
  Story #24 Feature 2 split that into independent tab panes but never
  revisited `minh`, so today even the tallest single pane (Clicking+Eating,
  Minecraft profile) has real leftover space at the floor — measured
  directly: pane height 528px, real content span 380px, ~148px of
  genuine, pre-existing (not introduced by this feature) slack, split by
  this feature into two ~74px spacers. This is a fact about the app's
  current floor calibration, not a bug in this feature's own logic — the
  same 148px was already unclaimed dead space below the Eating card
  *before* this feature existed (verified by recomputing the old,
  reqheight-based occupied total against the same pane height). Fixing
  `minh` is explicitly out of scope here (spec's own Non-goals: "No change
  to `_apply_minsize()`'s floor"; design.md's own "Open question: window
  minimum height" already flags this as a separate, deeper product
  question for the backlog). I renamed the corresponding test to
  `test_floor_case_still_splits_symmetrically_with_no_clipping` and
  changed its assertion to check the invariant this feature *is*
  responsible for at the floor — the split is symmetric and sums to the
  real (nonzero) leftover, computed the same way `_fill_pane` computes it
  — rather than asserting a bound that is false given today's `minh`. I
  did not touch `minh` or otherwise try to force the original assertion to
  pass. **This is the one finding I'd most want the reviewer to
  independently re-verify**, per spec's own "Risk / rollback notes"
  instruction to re-derive the floor case directly rather than trust
  prose.

## Known limitations

- The residual dead band design.md already flags (a centered split halves,
  not eliminates, the largest empty band) is unchanged and expected.
- The floor-case slack described above (~148px on the tallest pane) is a
  pre-existing condition this feature does not worsen but also cannot fix
  within its own scope; a follow-up re-tuning `minh` for the post-tab-split
  layout is a candidate for the backlog, per design.md's own "Open
  question."

## How to verify locally

```
DISPLAY=:99 <venv-python> -m unittest tests.test_ui.VerticalFill -v
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .
```

Both were run twice in this session: `VerticalFill` passes 7/7, and the full
suite passes `Ran 276 tests ... OK (skipped=5)` on both runs (no flake
observed this session; the known `Tcl_AsyncDelete` shutdown flake noted in
spec.md is pre-existing and unrelated).

To see the effect directly: launch the app, resize the window taller, and
switch to the Hotkey tab — its single card now sits with visible, roughly
equal empty space above and below it instead of a large dead band below.
Switching games on the Clicking tab to toggle a Minecraft profile (Eating
shown) vs. any other (Eating hidden) visibly changes Clicking's own margin
size, with no window resize involved.

## Round 2: fixing the guard test that proved nothing

The reviewer's should-fix (`docs/test-review.md` Finding 1): the previous
`test_hidden_tabs_own_margin_does_not_desync_the_visible_one` asserted that
Hotkey's own spacers were unchanged after a game switch. That's true, but
vacuous — `_fill_pane(*self._pane_fills["clicking"])` (the guarded call at
`afk_clicker.py:2566-2567`) can only ever write to the exact
pane/top/bottom tuple it's given, so it structurally cannot touch
`hotkey_pane`'s spacers whether the `self._content_tab == "clicking"` guard
is there or not. Removing the guard entirely still passed the old test.

**What the guard actually protects**, per its own comment: reading a hidden
pane's `winfo_height()` is the "unmapped-widget hazard this story has hit
before" — stale-but-plausible on X11, `0`/`1` on Windows, wrong either way
— so a game switch while Clicking is hidden must not recompute *Clicking's
own* margin from that bad geometry.

**Why the new test asserts on the top spacer specifically, not both.**
While designing this I found (via an Xvfb probe, not committed) that
Clicking's *bottom* spacer changes on a profile switch regardless of the
guard: `_select()` re-packs `eat_section`/`eat_card` with
`before=clicking_bottom` (`afk_clicker.py:2551-2557`) to keep pack's
re-add-at-the-end behavior from misordering the Eating card — and that
re-pack alone, independent of `_fill_pane`, can shrink the already-packed
bottom spacer through Tk's ordinary fixed-cavity space allocation (the pane
is `pack_propagate(False)`, so when the newly-shown Eating widgets need
more of the pane's fixed height, something packed after them gives space
back). I verified this directly: with the guard fully intact, toggling
Eating on while Clicking is hidden moved the bottom spacer from 273px to
94px in one probe run, purely from the re-pack — asserting the bottom
spacer stays frozen would have been a *new* false claim, this time failing
even with the guard present. The top spacer is packed before any of that
and is the guard's actual jurisdiction: with the guard doing its job it
cannot move while the pane stays unmapped, on either platform's failure
mode.

**What the new test proves**: it seeds a genuine value for Clicking's top
spacer while Clicking is actually visible (`_set_content_tab("clicking")`),
hides it (`_set_content_tab("hotkey")`), switches to the `minecraft`
profile (toggling Eating inside the now-hidden pane) with Hotkey active,
and asserts the top spacer is byte-for-byte unchanged from its seeded
value. It then switches back to Clicking and asserts the top spacer *has*
changed — proving the guard doesn't leave the pane permanently stale, only
deferred until it's genuinely visible again.

**Sabotage verification, both directions** (`DISPLAY=:99`, venv python,
`unittest tests.test_ui.VerticalFill.test_hidden_tabs_own_margin_does_not_desync_the_visible_one`):
- Guard present (real `afk_clicker.py`): **pass**.
- Guard removed (`if self._content_tab == "clicking":` deleted, the
  `_fill_pane(*self._pane_fills["clicking"])` call left unconditional,
  applied directly to `afk_clicker.py` from a backed-up copy and restored
  from that backup immediately after, verified via `git status`/`git diff`
  to be byte-identical to HEAD afterward): **fails**,
  `AssertionError: 373 != 273` — the top spacer gets silently recomputed
  from the hidden pane's stale geometry, exactly the hazard the guard
  exists to prevent.

I did not conclude the guard is unnecessary — sabotaging it produces a
real, measurable divergence (273 vs. 373 on this platform), so there is a
genuine behavioral difference to protect, not a manufactured one.

Full regression after restoring the guard: `VerticalFill` 7/7 pass, full
suite `Ran 276 tests ... OK (skipped=5)`, exit 0. `afk_clicker.py` is
unmodified in the final diff — only `tests/test_ui.py` changed.

## Round 3: fixing the assertion that assumed geometry() is a guarantee

PR #42 was blocked by a red Windows CI job (base `23e6658` green on all
three platforms, so the failure belongs to this diff):

```
FAIL: tests.test_ui.VerticalFill.test_live_resize_drag_updates_margin_without_a_rebuild
AssertionError: 222 not greater than 249
```

**Why the old assertion was unsound.** The test captured
`before = top.winfo_height()` at the pane's default launch height, drove
`root.geometry()` through four heights (700/850/750/900, scaled by `s`),
then asserted `top.winfo_height() > before`. That assumes every one of
those `geometry()` calls was honoured at its literal requested size.
`root.geometry()` is a *request* to the window manager, not a contract —
on the Windows CI runners the WM clamped the final requested size to
something shorter than the height `before` had been measured at, so the
pane's real leftover space legitimately shrank and the top spacer
legitimately got smaller. The test was asserting a direction the platform
never promised, not a bug in `_fill_pane()`. This exact hazard is called
out by name in this feature's own `docs/spec.md` open questions, and this
same test file already has precedent for it: another test in this suite
(`test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`)
self-skips on Windows for the identical clamped-runner reason.

**The fix.** Rewrote the final assertion to be true-by-construction against
the pane's actually-granted geometry after the drag, following the exact
pattern already used by this test's own two siblings in the same
`VerticalFill` class —
`test_top_and_bottom_spacers_sum_to_the_real_leftover_space` and
`test_floor_case_still_splits_symmetrically_with_no_clipping`: measure
`natural` as the real bottom-minus-top span of the pane's mapped non-spacer
children (winfo_y()/winfo_height()-based, matching how `_fill_pane()`
itself measures it, not a reqheight sum), take
`extra = max(0, pane.winfo_height() - natural)`, and assert
`top.winfo_height() + bottom.winfo_height() == max(2, extra)`. The
`max(2, extra)` floor (not a bare `extra`) matches `_fill_pane()`'s own
`max(1, ...)` floor on each spacer individually — verified against
`afk_clicker.py:1470-1482`: for `extra >= 2`,
`int(extra * FILL_TOP_SHARE) + (extra - int(extra * FILL_TOP_SHARE))`
always sums back to `extra` exactly (`FILL_TOP_SHARE = 0.5`); only when
`extra` is `0` or `1` does the per-spacer `max(1, ...)` floor push the sum
up to `2`. This holds on any platform, any screen, and any WM clamping
behavior, because it never assumes a `geometry()` request was granted at a
particular size — only that whatever size *was* granted is measured
directly.

**What was deliberately kept intact**, per the fix instructions:
- The `self.assertEqual(len(calls), 0)` invariant — that this feature never
  triggers `_rebuild_ui()` — is unchanged. It's platform-independent (the
  rebuild trigger is `RAIL_COLLAPSE_THRESHOLD`, a width comparison,
  untouched by a height-only resize loop) and is the more important
  invariant this test carries.
- The four-iteration `root.geometry()` loop is unchanged: the test still
  drives several genuine `<Configure>` events on a mapped pane, i.e. it's
  still a live-resize-drag test, not reduced to a single `_tall_window()`
  call. The rewrite only changes what's asserted about the *final* state,
  not how that state is reached.

**Verified in this session** (`DISPLAY=:99`, venv python at
`.../scratchpad/venv/bin/python`, working tree at
`/home/dev/projects/.worktrees/afk-clicker/ac-24`):
- The single test passes:
  `unittest tests.test_ui.VerticalFill.test_live_resize_drag_updates_margin_without_a_rebuild`
  → `Ran 1 test ... OK`.
- Full suite regression: `python -m unittest discover -v` from the project
  root → `Ran 276 tests in 70.292s / OK (skipped=5)`, matching the known
  baseline exactly.
- **The clamped-window case itself**, the one that only a constrained CI
  runner exposes and that Linux never naturally hits: a throwaway probe
  script (run from the scratchpad, never added to the tree) reused this
  test's own setup to run the same four-step growth loop, capture `before`
  and the post-loop grown height, and then issue one more `geometry()`
  request for a height *smaller* than `before` — on Xvfb, unlike a real
  WM, that request is honoured outright, which stands in directly for "the
  WM clamped it." Measured output:
  ```
  before: 206  after growth: 316
  after shrink request: 206  vs before: 206
  pane height: 528  natural: 115  extra: 413
  expected sum: 413  actual sum: 413
  old-style assertGreater(after_shrink, before) would assert: False
  ```
  This reproduces the exact failure shape from the Windows CI log: the
  final granted height is not greater than `before`, so the *old*
  assertion would have raised `AssertionError` here too, while the new
  true-by-construction assertion holds (`413 == 413`) regardless of which
  request in the loop actually landed.
- **What only CI can confirm**: that the real Windows WM on the GitHub
  Actions runner reaches this same clamped state on its own during the
  actual four-step drag (rather than the probe's synthetic "request a
  smaller size directly" stand-in), and that the rewritten assertion is
  green there. Xvfb has no window manager to clamp anything by itself
  (`_tall_window()`'s and this test's requests are always honoured
  verbatim on `:99`/`:98`), so the clamping behavior itself is not
  reproducible locally — only the assertion's correctness *given* a
  clamped result is.
- `afk_clicker.py` is unmodified — only `tests/test_ui.py` changed, per
  the fix instructions (product code was never in scope for this round;
  the failure was a test-authoring bug, not a feature bug).

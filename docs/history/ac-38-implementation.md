# Implementation: UI scale follows the window size (G#38 / GH#67)

## Summary
Added a 5th `ui_scale` value, `"auto"` — now `UI_SCALE_DEFAULT` — whose
`self.s` is derived continuously from an area-based "how much of the screen
does the window fill" fraction (`_auto_scale_factor()`), clamped to the same
`[0.9, 1.3]` range the four fixed steps already cover and calibrated so the
app's own default launch geometry on a 1920x1080 screen lands at parity with
today's "100%" step. A live drag in Auto mode recomputes `self.s` and
`root.minsize()` on every `<Configure>` (cheap, no widget churn) but defers
the actual `_rebuild_ui()` to a new `AUTO_SETTLE_MS=150` real-timer debounce
(`_request_auto_settle`/`_on_auto_settle`), not the existing `after_idle`
coalescing `_request_rebuild()` uses — a genuine drag-settle debounce, not
just duplicate-trigger coalescing. Fixed-step (90/100/115/130%) behavior is
byte-for-byte unchanged; every new code path is branch-gated on
`ui_scale == "auto"`.

## Changes by file

### `afk_clicker.py`
- **Constants** (`UI_SCALE_FACTORS` block, ~line 130): `UI_SCALE_DEFAULT`
  changed `"100"` → `"auto"`; added `AUTO_SCALE_MIN`/`AUTO_SCALE_MAX`
  (aliases of `UI_SCALE_FACTORS["90"]`/`["130"]`), `AUTO_REF_SCREEN_W/H`
  (`1920, 1080`), `AUTO_SETTLE_MS = 150`. `AUTO_REFERENCE_FILL` itself is
  defined later, right after `CARD_INNER_W` (~line 250), because its formula
  needs `SIDEBAR_W`/`CONTENT_W`/`WINDOW_MIN_H`, which aren't in scope yet at
  `UI_SCALE_FACTORS`'s own location — same "derived from other constants,
  after they exist" precedent `CARD_INNER_W` itself already sets.
- **`Store.__init__`'s sanitiser** (~line 1387): widened from
  `if self.data["ui_scale"] not in UI_SCALE_FACTORS:` to
  `... and self.data["ui_scale"] != "auto":` — same shape, one more accepted
  literal, no schema version bump.
- **`AfkAutoclicker.__init__`** (~line 2340): caches
  `self._screen_w, self._screen_h = root.winfo_screenwidth(),
  root.winfo_screenheight()` once (same "detected once at startup" policy
  `_dpi_s` documents), then bootstraps `self.s = self._dpi_s * 1.0` when
  `ui_scale == "auto"` (there's no mapped window size yet to derive Auto
  from) — the same value `"100"` always gave for this first `_build_ui()`/
  `_apply_minsize()` call. Added `self._auto_settle_after_id = None` next to
  `_rebuild_after_id`/`_pane_fill_after_id`.
- **New methods** (next to `_apply_minsize`/`_request_rebuild`, ~line 2681):
  - `_auto_scale_factor(width, height)` — the spec's formula verbatim:
    `fill = sqrt(w*h / (screen_w*screen_h))`, `factor = fill /
    AUTO_REFERENCE_FILL`, clamped to `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`.
  - `_request_auto_settle()` / `_on_auto_settle()` — the cancel-and-
    reschedule real-timer debounce (`root.after(AUTO_SETTLE_MS, ...)`),
    handing off into the existing `_request_rebuild()` once it fires.
- **`_apply_ui_scale(value)`** (~line 3423): guard widened to accept
  `"auto"`; branches to `self.s = self._auto_scale_factor(root.winfo_width(),
  root.winfo_height())` instead of the `UI_SCALE_FACTORS[value]` lookup when
  `value == "auto"` — recomputes immediately from the window's current size,
  same persist/`_apply_minsize`/`_request_rebuild()` tail as every other
  value.
- **`_on_root_resize(event)`** (~line 2732): new Auto-mode branch, checked
  via `self.store.data["ui_scale"] == "auto"` (live state, no new mode
  flag). On every qualifying event: recomputes `self.s`,
  `_apply_minsize(grow_only=True)`, and the rail-collapse comparison against
  the just-updated `self.s`; requests the **settled** rebuild
  (`_request_auto_settle()`) instead of the immediate `after_idle` one,
  only if `self.s` or `self._rail_collapsed` actually changed. Fixed-step
  mode falls through to the exact pre-existing code, unchanged.
- **`on_close`** (~line 4707): added `_auto_settle_after_id` to the existing
  after-id cancellation block, same try/except `TclError` shape as
  `_rebuild_after_id`/`_pane_fill_after_id`.
- **Settings > Appearance > "UI scale" `Segmented`** (~line 3251): options
  list gets `("auto", "Auto")` prepended; `width=220` → `width=244` per
  `docs/design.md`'s layout math (`152 + 244 = 396 == CARD_INNER_W`, exactly
  fills the card).

### `tests/test_ui.py`
- **`UIScaleStore`** — the 5 tests `docs/spec.md` named by line number
  updated to expect `"auto"` instead of `"100"`, and renamed to match
  (`..._defaults_to_100` → `..._defaults_to_auto`, etc.).
  `test_known_values_round_trip` now includes `"auto"` in its value tuple.
  `test_a_garbage_on_disk_value_resolves_to_auto_end_to_end`'s
  `ui.s == ui._dpi_s` assertion needed no change: Auto's own bootstrap
  (`self.s = self._dpi_s * 1.0`) gives the identical value the old `"100"`
  default always did, and `restart()` never fires a resize, so nothing here
  recomputes it away from that bootstrap value (confirmed empirically, not
  just reasoned — see "How to verify locally").
- **New `UIScaleAuto(UITestCase)`** class (after `UIScale`, before
  `FontSizeFloorAtWorstCaseScale`) — 10 tests covering every acceptance
  criterion the spec lists as Xvfb-verifiable: calibration-formula parity at
  a forced 1920x1080 screen, the `_apply_ui_scale("auto")` wiring landing
  near `self._dpi_s`, `self.s` strictly increasing with window size (bounded
  to `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`), `minsize()` tracking the live
  scale through every step of a continuous shrink (not just the final
  state), a burst of `<Configure>` events settling to exactly one rebuild
  only after `AUTO_SETTLE_MS` past the *last* event (a second test proves
  the timer genuinely resets per new event, not just coalesces),
  rail-collapse/re-expand under Auto's live `self.s` (with the settled
  rebuild verified, not just the flag), the Settings pane showing 5 options
  with "Auto" first/selected by default, and `on_close()` cancelling a
  pending settle job.
- **`FontSizeFloor`** — added
  `test_continuous_s_values_between_the_fixed_steps_still_floor`, a
  property-style sweep of `fs(base, s)` across `s` from 0.9 to 1.3 in 0.025
  steps and several bases, confirming the floor and the `int(base*s)`
  formula hold for every continuous value Auto can produce, not just the
  four discrete steps — no UI needed, per the spec's own acceptance
  criterion wording.
- **`WindowResize`/`RailCollapse`** — both gained a `setUp()` that pins
  `self.ui._apply_ui_scale("100")` right after construction (see "Deviations
  / necessary test-infrastructure fixes" below for why).
- **`RowValueColumn.test_ui_scale_row_never_overflows_its_card_at_any_scale_step`**
  — the hardcoded constant-level fit check (`152 + 220 <= 396`) and per-step
  loop updated to the real, current control width (`244`) and to include
  `"auto"` alongside the four fixed steps.
- **`UIScale.test_two_real_ui_scale_segmented_clicks_with_no_pump_between_them`**
  — `seg_w` now divides by 5 (was 4), and the two click x-offsets retargeted
  to the actual "100%"/"130%" column positions (index 2 and 4) in the grown
  control. This test's own final assertion only checks the *last* click's
  outcome, so it was passing "by accident" against the wrong first-click
  column before this fix (see below) — worth flagging even though it wasn't
  itself failing.

## Key decisions / tradeoffs
- **`AUTO_REFERENCE_FILL`'s placement is not "next to `UI_SCALE_FACTORS`"
  as the spec's own prose literally suggests**, because it depends on
  constants (`SIDEBAR_W`, `CONTENT_W`, `WINDOW_MIN_H`) that are defined
  later in the file. Placed immediately after `CARD_INNER_W` instead —
  `AUTO_SCALE_MIN`/`MAX`/`AUTO_REF_SCREEN_W/H`/`AUTO_SETTLE_MS` (which have
  no such dependency) stayed next to `UI_SCALE_FACTORS` as the spec
  describes. Called out explicitly since the spec's own text didn't flag
  this ordering constraint.
- **Debounce timer verified with real elapsed time (`pump()`), not just
  event coalescing** — `_request_auto_settle` uses `root.after(...)`, a
  genuine wall-clock timer, so the burst-debounce tests use the existing
  `pump(seconds)` helper (already used throughout the suite for other real
  `after()` timers) rather than a single `root.update()`, which would only
  drain `after_idle` jobs.
- **Two of the new `UIScaleAuto` tests force `self.ui._screen_w/_screen_h`
  to a synthetic 3840x2160 screen** (`test_s_strictly_increases_...`,
  `test_minsize_tracks_the_live_scale_...`) — the same "force the attribute
  directly" technique `FontSizeFloorAtWorstCaseScale` already uses for
  `_dpi_s`. Root cause: those two tests use real `root.geometry()` calls,
  which *are* subject to Tk's own `minsize()` enforcement (unlike
  `event_generate("<Configure>", ...)`'s synthetic events, used by the
  debounce/rail tests, which aren't). This session's actual Xvfb screen
  (1280x1024, discovered empirically — not 1920x1080) is small enough,
  relative to the app's own fixed-pixel minsize floor, that a target Auto
  factor near 0.9 back-solves to a window rectangle Tk silently clamps back
  up before the test ever observes it, and near 1.3 saturates almost
  immediately from the default launch size. Forcing a large synthetic
  screen keeps every back-solved rectangle comfortably clear of the
  minsize floor on both ends, and is also more portable than relying on
  whatever real screen a given CI runner happens to have.

## Deviations from spec / design
- **Test regressions caused by changing `UI_SCALE_DEFAULT`, fixed here, not
  called out by name in `docs/spec.md`'s "Affected areas."** The spec named
  exactly 5 `UIScaleStore` tests as needing updates. In practice, changing
  the *default* from a fixed step to `"auto"` also broke
  `WindowResize.test_rail_stays_at_expanded_width_on_a_wide_window`,
  `WindowResize.test_shrinking_past_the_threshold_collapses_the_rail`,
  `RailCollapse.test_add_current_game_button_survives_collapse`, and
  `RailCollapse.test_settings_item_collapsed_update_dot_reflects_has_update`
  — all four assume (implicitly, via the pre-existing default) that a plain
  `root.geometry()` resize rebuilds the widget tree synchronously (via
  `_request_rebuild()`'s `after_idle`, drained by the very next
  `root.update()`), which only holds for a fixed step; Auto instead defers
  that rebuild to the new `AUTO_SETTLE_MS` timer. These four classes are
  about generic resize/rail-collapse mechanics, not about Auto vs. fixed-step
  differences — per the spec's own non-goal ("No change to... non-Auto
  resize handling... is unchanged"), the correct fix is to pin these two
  test classes to a fixed step in their own `setUp()`, not to rewrite their
  assertions around Auto's debounce. Confirmed via an isolated before/after
  run (default-only change, no Auto wiring yet) that these were the *only*
  four real regressions, not a wider blast radius — documented under "How to
  verify locally."
- **`RowValueColumn`'s and `UIScale`'s own pre-existing tests hardcoded the
  Segmented control's old option count/width (4, `220`).** Growing it to 5
  options/`244` per `docs/design.md` made one test's constant-level check
  stale (fixed, see above) and silently changed which column a second
  test's first click actually landed on (also fixed, see above) — neither
  was named in the spec's "Affected areas," found by running the full suite
  and reading the failure/pass results, not guessed.
- No other deviation. The formula, clamp range, calibration constant,
  debounce mechanism, `_on_root_resize`/`_apply_ui_scale` wiring, and
  Segmented control change all match `docs/spec.md`/`docs/design.md`
  exactly (options order `Auto, 90%, 100%, 115%, 130%`; width 244; no new
  colors/components).

## Known limitations
- **No real window manager in this session (Xvfb, per `docs/spec.md`'s own
  Acceptance criteria split).** The first-launch-on-an-unusual-real-screen
  bootstrap path (a genuine WM-driven post-map `<Configure>` recomputing
  `self.s` away from its `_dpi_s * 1.0` bootstrap) is not exercised here —
  only the Windows/macOS CI legs can verify it. Everything else (continuous
  tracking, live minsize, the settle debounce, rail-collapse under Auto) is
  exercised via `root.geometry()`/`event_generate("<Configure>")` +
  `root.update()`/`pump()`, the same technique the pre-existing
  `WindowResize`/`UIScale` classes already use successfully under Xvfb —
  say so explicitly rather than claiming full coverage from this green
  Linux run alone, per the spec's own instruction.
- `AUTO_SETTLE_MS = 150` is carried unchanged from the spec as an initial
  value, not empirically tuned — this session can't validate perceived drag
  responsiveness on a real OS, only the debounce mechanism's correctness
  (which is tested).
- Everything the spec listed as a Non-goal (macros tab, calibration suite,
  schema version bump, live font-rescale-without-rebuild, mid-session
  DPI/screen re-detection) is untouched, as specified.

## How to verify locally
Environment (this repo's convention: a venv with `pynput` + Xvfb):
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```
**As of round 3**, start Xvfb with a higher client cap than its own
default —  `Xvfb :99 -screen 0 1280x1024x24 -maxclients 2048` — or the
full suite (439 tests) can fail with `Xlib.error.DisplayConnectionError:
... Maximum number of clients reached`, a local-environment capacity
limit unrelated to this round's code (see Round 3's own "Key decisions"
section below). Not needed for running an individual class/test.

### This ticket's own tests
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.UIScaleStore tests.test_ui.UIScaleAuto tests.test_ui.WindowResize tests.test_ui.RailCollapse tests.test_ui.UIScale tests.test_ui.FontSizeFloor tests.test_ui.RowValueColumn -v
# Ran 50 tests, OK
```
Confirmed red before implementing the Auto wiring: changing only
`UI_SCALE_DEFAULT`/the `Store` sanitiser (no `_apply_ui_scale`/
`_on_root_resize` changes yet) reproduced exactly the 5 `UIScaleStore`
failures (6 counted with subTests) named in the spec, and nothing else —
confirming those were the *only* pre-existing tests directly coupled to the
literal `"100"` default. Wiring in the rest of the feature then surfaced the
4 additional `WindowResize`/`RailCollapse` regressions described under
"Deviations" above, fixed by pinning those two classes to a fixed step.

### Full suite result (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 434 tests in 77.841s

OK (skipped=10)
```
434 = the pre-existing 423-test baseline + 11 new tests this cycle (10 in
`UIScaleAuto`, 1 in `FontSizeFloor`). Same skip count as before this change.
Re-ran the full suite and the new timing-sensitive `UIScaleAuto` tests
individually a second time to check for flakiness — stable both times.

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
?? docs/design.md
?? docs/implementation.md
?? docs/spec.md
```
No file outside `afk_clicker.py`/`tests/test_ui.py` was touched by the code
change itself; no scratch file was left in the repo tree.

## Round 2 — macOS/Windows CI regression, PR #89 review response

**Trigger.** PR #89 (this branch, head `cd28343`) got **ANOTHER ROUND** from
an independent critical review: `ubuntu-latest` passed, `macos-latest` and
`windows-latest` each failed 20 tests — a real regression against `main`'s
green baseline, not flakiness. Full review:
https://github.com/LeTe0301/afk-clicker/pull/89#issuecomment-5727152243.
Root-caused by the reviewer to two related gaps and verified independently
here before touching anything (see "Verifying the root cause" below):

- **Gap 1.** `UI_SCALE_DEFAULT` is now `"auto"`, so every fresh install —
  and every `UITestCase` fixture, since no test overrides it — boots in
  Auto mode. A real window manager (macOS WindowServer, Windows) sends a
  post-map root `<Configure>` shortly after construction; Xvfb (used for
  local/Linux verification) has no WM and never generates this event, so
  this path was silently unexercised locally in Round 1. On macOS/Windows
  CI's real WM, that event reports the app's own already-known bootstrap
  geometry back unchanged — but the *screen* those CI runners actually
  have is far from `AUTO_REF_SCREEN_W/H` (1920x1080), so
  `_auto_scale_factor()` still computed a different `self.s` purely from
  the screen-size term and armed a real `AUTO_SETTLE_MS` (150ms) timer from
  this echo alone. That timer later fired `_rebuild_ui()` mid-test (or
  after a *different* test's own teardown), tearing down/rebuilding the
  widget tree out from under a test that never asked for one —
  `TclError: invalid command name` / `bad window path name`, and rebuild-
  coalescing tests observing 2 rebuilds instead of 1.
- **Gap 2.** `on_close()` cancelled a pending `_auto_settle_after_id` only
  once, near the top of teardown, but `_on_root_resize` stayed bound
  through the rest of teardown, including `root.destroy()` itself — a late
  `<Configure>` arriving after that one cancellation (e.g. one
  `root.destroy()` itself can generate) could re-arm a job nothing after
  that point ever cancels again. Same class of hazard this project already
  hit once for `_log_report_after_id` (`afk_clicker.py:3974-3979`'s "belt
  and braces" comment) — a one-shot pre-destroy cancel is not airtight
  against a handler that can still re-arm the job.

**Verifying the root cause.** Reproduced both gaps locally under Xvfb
(which has no WM, so neither occurs *naturally* — both were forced
synthetically, the same "force the attribute directly"/`event_generate`
technique `FontSizeFloorAtWorstCaseScale`/`UIScaleAuto`'s own Round 1 tests
already use):
- Gap 1: forced `self.ui._screen_w/_screen_h` to a value far from
  `AUTO_REF_SCREEN_W/H` (simulating a real CI runner's own virtual
  display), then fired a synthetic `<Configure>` reporting exactly
  `self.ui._auto_bootstrap_wh` (the window's own already-known bootstrap
  geometry) — before any fix, this armed a live `_auto_settle_after_id`
  from the echo alone, confirmed via `self.ui._auto_settle_after_id` being
  non-`None` immediately after.
- Gap 2: hooked `_release_right` (on_close()'s own last call before
  `root.destroy()`, the same "last point before destroy" position
  `UpdateLogPrompt.test_on_close_before_the_startup_idle_job_ever_ran_cancels_it`
  already uses to inspect state right before teardown finishes) to fire a
  synthetic `<Configure>` there — before any fix, this re-armed
  `_auto_settle_after_id` after the earlier cancellation had already run.

**What changed** (`afk_clicker.py`):
- `_apply_minsize()`'s `not grow_only` branch (bootstrap-only, called
  exactly once, from `__init__`) now records the exact `(width, height)`
  it just requested via `root.geometry(...)` into a new
  `self._auto_bootstrap_wh` instance attribute (initialised to `None`
  right before the call, next to the other `__init__` slots).
- `_on_root_resize`'s Auto-mode branch computes
  `is_bootstrap_echo = (event.width, event.height) == self._auto_bootstrap_wh`
  and only calls `_request_auto_settle()` when `(s_changed or
  collapsed_changed) and not is_bootstrap_echo` — `self.s`/`minsize()`/the
  rail-collapse flag still get corrected live for *every* qualifying
  event, echo or not (unchanged from Round 1); only the settle-triggered
  rebuild itself is skipped for an event that reports the bootstrap
  geometry back unchanged. Gated on the event's own *content* (does it
  match the geometry the app already knows about), not on "is this the
  first event this instance has ever seen" — see "Key decisions" below for
  why that distinction mattered.
- `on_close()` now calls `self.root.unbind("<Configure>")` as its very
  first line, before the existing after-id cancellation block runs —
  closes gap 2 outright, matching this project's stated preference (seen
  already on `_rebuild_after_id`'s own comment) for making a hazard
  "impossible outright" rather than re-guarding it.

**Regression tests added** (`tests/test_ui.py`, `UIScaleAuto`, new "round 2"
section after the existing Round 1 tests):
- `test_the_bootstrap_echo_configure_does_not_arm_a_live_settle_timer` —
  gap 1, reproduces the exact scenario above and asserts
  `_auto_settle_after_id is None` after the echo, plus that `self.s` still
  tracked live (only the rebuild was skipped, not the recompute).
- `test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size` —
  proves the fix is scoped to the literal echo, not "skip every event this
  instance ever sees": a real resize to a *different* size still arms the
  settle timer normally.
- `test_a_late_configure_during_teardown_does_not_re_arm_the_settle_timer`
  — gap 2, reproduces the `_release_right`-hook scenario above and asserts
  `_auto_settle_after_id is None` after `on_close()` returns.

**Sabotage-verified** (this project's standing lesson): temporarily
reverted each fix in turn (`is_bootstrap_echo = False` for gap 1; commented
out the new `unbind()` call for gap 2), confirmed the matching new test
failed with the expected assertion message, then restored the fix and
confirmed it passed again. Neither sabotage affected the other gap's test.

## Key decisions / tradeoffs (Round 2)

- **Gated by event content (`(width, height) == self._auto_bootstrap_wh`),
  not by "the first Auto `<Configure>` this instance has ever seen".** The
  latter was tried first and rejected: Xvfb never generates a natural
  bootstrap echo, so under a "first-ever" flag, the *first synthetic event
  any test fires* would be misidentified as the bootstrap echo regardless
  of what it actually represents — breaking existing Round 1 tests whose
  own opening move **is** their real assertion-triggering event
  (`test_a_burst_of_configure_events_settles_to_one_rebuild`,
  `test_the_settle_timer_resets_on_each_new_event_not_just_the_first`,
  `test_on_close_cancels_a_pending_settle_job`, `test_shrinking_past_the_
  threshold_collapses_the_rail_under_auto`, `test_growing_back_past_the_
  threshold_re_expands_the_rail_under_auto` — confirmed by hand-tracing
  each, not guessed). Content-based gating requires zero changes to any
  existing `UIScaleAuto` test: none of them target the literal bootstrap
  pixel size, so none collide with the new suppression. This is also a
  more honest match for what a real WM's bootstrap echo actually *is* — an
  event carrying no new size information, not merely "whichever event
  happened to arrive first."
- **An alternative considered and rejected: route the bootstrap echo
  through `_request_rebuild()`'s existing `after_idle` path (an immediate,
  deterministic rebuild) instead of suppressing it outright.** This would
  have kept the spec's original "self-correct to the real screen shortly
  after first launch" edge-case behavior intact for the echo case too. It
  was rejected because it reintroduces the exact same "first-ever-event"
  ambiguity from a different angle: `event_generate()` in this test suite
  dispatches synchronously (Tk's own `-when now` default), so a burst of
  events fired in a tight loop before any `root.update()` call (exactly
  `test_a_burst_of_configure_events_settles_to_one_rebuild`'s own shape)
  would have its first iteration silently swapped for an immediate
  rebuild — traced through by hand and confirmed this breaks 3 of the 5
  tests the "first-ever" flag approach also broke. Full suppression (no
  rebuild request at all for a literal echo) breaks fewer things and is
  simpler to reason about; the content-based gate closes the gap between
  the two approaches on the tests that do need touching (see "Deviations"
  below for the one real behavior tradeoff this leaves).
- **Full suite re-run twice** (437 tests: the 434-test Round 1 baseline +
  3 new Round 2 tests) to check for flakiness in the new timing-sensitive
  assertions — stable both times, `OK (skipped=10)`.

## Deviations from spec (Round 2)

- **The spec's own "First launch in Auto mode on a screen far from
  1920x1080" edge case** (`docs/spec.md`: "...exactly one settle-triggered
  rebuild happens shortly after first launch, sizing the UI to the real
  screen") **no longer holds automatically for the literal bootstrap
  echo.** With this fix, `self.s` is still corrected internally the moment
  the echo arrives (steps 1-3 of `_on_root_resize`'s Auto branch are
  unconditional), but the widget tree itself (fonts/padding baked in via
  `fs()`) stays at the bootstrap `self._dpi_s * 1.0` value until the *next*
  qualifying `<Configure>` — a real user-driven resize, or an explicit
  Settings > Appearance re-pick (`_apply_ui_scale("auto")`, which computes
  and rebuilds immediately, unaffected by this suppression since it never
  goes through `_on_root_resize`). On a screen at/near 1920x1080 this was
  already a no-op (`factor ≈ 1.0`, nothing to correct); on a screen far
  from it, a user who never resizes the window and never revisits Settings
  will see the bootstrap-default sizing rather than the spec's originally-
  promised self-correction. This is a deliberate, reviewer-endorsed
  tradeoff (the reviewer's own candidate fix 1, "suppress/no-op the very
  first post-launch settle cycle") made to close a real, CI-blocking
  regression without reintroducing a live real-timer hazard at bootstrap
  time; not filed as a new backlog item here since it's this round's own
  known, accepted cost, not an unrelated finding.
- No other deviation from `docs/spec.md`/`docs/design.md`. The core Auto
  formula, calibration constants, debounce mechanism, and Segmented layout
  are untouched, as instructed.

## Known limitations (Round 2)

- **Still Xvfb-only verification.** Exactly as Round 1's own "Known
  limitations" already said: this session has no real window manager, so
  neither gap's *natural* trigger (a genuine WM-generated post-map
  `<Configure>`, or a genuine late WM-generated `<Configure>` during a real
  `root.destroy()`) was observed occurring on its own — both were forced
  synthetically via `event_generate()`/direct attribute assignment, the
  same technique already proven reliable for this file's other Auto tests.
  This proves the fix mechanism itself is correct against the exact
  scenario the reviewer described, and that the sabotage (reverting either
  fix) reproduces the original failure shape locally — but **only this
  round's actual macOS/Windows CI run can confirm the real regression is
  closed**, not this session alone. Say so explicitly rather than
  overclaiming full coverage from a green Linux run.
- The bootstrap-echo suppression tradeoff above (widget tree lagging
  `self.s` until the next real trigger, on a screen far from 1920x1080) is
  carried forward as a known, accepted limitation of this round's fix, not
  silently dropped.

## Round 3 — macOS/Windows CI still failing after round 2, PR #89 review

**Trigger.** Round 2 (commit `4266900`) did not close the regression:
`gh pr checks 89` still showed `macos-latest`/`windows-latest` failing,
`ubuntu-latest` passing — but a **different** ~20-failure signature per
platform than round 1's, confirming round 2's fix was a real but
incomplete step, not a no-op. Investigated from the actual CI logs
(`gh run view 35324387333 --job 105533949800/105533949882 --log`), not
guessed, since this session has no macOS/Windows access.

**Root cause 1 — `_apply_minsize(grow_only=True)`'s own geometry() call
wasn't tracked as a self-requested echo.** Round 2's `is_bootstrap_echo`
compared an incoming `<Configure>` against a *single*, one-time value
(`self._auto_bootstrap_wh`) recorded once at construction. But
`_apply_minsize(grow_only=True)` — called from every qualifying Auto-mode
`<Configure>`, including the very event being processed — can itself
issue a *second* real `root.geometry()` call, whenever the newly
recomputed minsize floor exceeds the window's current real size. A real
window manager's later confirmation of *that* self-requested geometry was
never recognized as an echo (it didn't match the one construction-time
value), so it looked like a genuine external resize and re-armed a live
`AUTO_SETTLE_MS` timer from pure self-correction. Reproduced and
sabotage-verified locally (not just reasoned) via a direct interpreter
trace with an instrumented `_on_root_resize`, forcing `self.s` to a value
whose height floor exceeds the fixture's real bootstrap window: this
produces a real multi-event cascade (`(604,566)` → `(688,712)` →
`(688,806)` in one trace) where an un-fixed round 2 re-arms a *new* settle
timer at each intermediate self-correction.

**Root cause 2 — two of `UIScaleAuto`'s own round-1 tests
(`test_s_strictly_increases_with_increasing_window_size`,
`test_minsize_tracks_the_live_scale_during_a_continuous_shrink`) used real
`root.geometry()` calls sized against a *forced*, unrelated 3840x2160
reference screen.** That forced value was only ever meant as the
`_auto_scale_factor()` calculation's own denominator, but back-solving
*real* window pixel sizes from it (to dodge Tk's own minsize clamp on this
session's small Xvfb screen, round 1's own stated reason) produces window
sizes with no relationship to any *real* screen a CI runner actually has.
On a real WM this collides in two ways: (a) `root.geometry()` requests
that exceed the real screen get silently clamped by the WM, so
`self.ui.s` ends up tracking the *clamped* size against the still-forced
3840x2160 denominator, landing at `AUTO_SCALE_MIN` for every tested
factor from a point onward (observed exactly this in the CI log: `0.9 not
greater than 0.9`, `465 not less than 465`, frozen for every factor from
1.1 up); (b) even where it doesn't get clamped, the resulting real window
change is itself a second `<Configure>` fed back into
`_auto_scale_factor()` against the forced screen, corrupting the intended
value regardless of root cause 1's fix (reproduced this directly:
switching only to `event_generate()` without also decoupling the real
window's own size from the forced screen still froze at the clamp floor,
because `_apply_minsize`'s own grow_only correction — needed since the
*real* window never actually grows to match a synthetic event's fake
width/height — read the real, tiny window's dimensions against the fake
screen).

**Root cause 3 — two more `UIScaleAuto` tests read window/`self.s` state
without waiting for it to actually land.**
`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` called
`_apply_ui_scale("auto")` (which reads `self.root.winfo_width()/height()`
directly) without first confirming the window had actually reached its
intended default launch geometry — a single `root.update()` is not a
synchronization point with a real, out-of-process window manager (Xvfb,
with no WM at all, made this a non-issue in round 1's own local
verification). `UIScaleStore.test_a_garbage_on_disk_value_resolves_to_auto_
end_to_end` asserted `ui.s == ui._dpi_s`, a premise its own docstring
already named as Xvfb-specific ("no window manager... no genuine post-map
`<Configure>` ever recomputes it") — false on a real WM, where Auto's own
first-launch self-correction (docs/spec.md's own named, *intended* edge
case) can legitimately move `self.s` away from the bootstrap value before
this reads it.

**Root cause 4 — the same construction-time self-correction (root cause
3's "intended edge case") was corrupting *unrelated* tests broadly.**
Making `"auto"` the default means every `UITestCase` fixture — not just
`UIScaleAuto`'s own — now boots in Auto mode, and a real WM's own
post-map `<Configure>` landing during a screen far from
`AUTO_REF_SCREEN_W/H` legitimately arms a live 150ms settle timer by
design. On CI, several unrelated failures (`NumBoxFocus`,
`BindAllBoundOnce`, `RowValueColumn`, `SettingsUpdates`, plus
`WindowResize`/`RailCollapse`/`UIScale`'s own hardcoded-geometry
assertions) showed symptoms consistent with a widget-tree rebuild firing
mid-test (`bad window path name`, a Settings label mid-rebuild
(`'S' != 'Settings'`), stale/`18 not greater than 18` measurements) — a
settle-triggered rebuild landing while the test body still held references
into the pre-rebuild tree, or asserted geometry a real WM hadn't finished
granting.

**What changed** (`afk_clicker.py`):
- `_apply_minsize(grow_only=True)` now records `self._auto_bootstrap_wh =
  (new_w, new_h)` whenever *it* issues a `root.geometry()` call too, not
  just the one-time construction call — closes root cause 1. Only ever one
  self-request is in flight at a time (single-threaded event handling), so
  tracking "most recent" is sufficient; no new attribute needed.

**What changed** (`tests/test_ui.py`):
- **`UITestCase`** gains `INITIAL_UI_SCALE` (a class attribute, default
  `None`): when set to a `UI_SCALE_FACTORS` key, `setUp()` pre-seeds
  `settings.json` with it *before* constructing `AfkAutoclicker`, so the
  app boots directly at that fixed step — bypassing Auto's own
  construction-time convergence (and the real-WM round-trip it depends on)
  entirely, rather than switching to it *after* construction (which still
  raced whatever Auto's own bootstrap already put in flight). `WindowResize`,
  `RailCollapse`, and `UIScale` (all three: generic resize/fixed-step
  mechanics predating Auto, per docs/spec.md's own non-goal) set
  `INITIAL_UI_SCALE = "100"`, replacing `WindowResize`/`RailCollapse`'s own
  post-construction `_apply_ui_scale("100")` setUp() pin (root cause 4,
  scoped to these three classes specifically).
- **`UITestCase.setUp()`** also now waits (bounded,
  `AUTO_SETTLE_MS/1000 + 1.0`s, via the existing `pump_until` helper) for
  any `_auto_settle_after_id` armed during construction to fire and clear,
  before the test body starts — so a *genuine* first-launch correction
  (root cause 4's "intended edge case") still happens, but doesn't land
  mid an unrelated test's own body. A no-op for any class using
  `INITIAL_UI_SCALE`, since Auto is never entered there.
- **`UIScaleAuto.test_s_strictly_increases_with_increasing_window_size`
  and `test_minsize_tracks_the_live_scale_during_a_continuous_shrink`**
  switched from real `root.geometry()` calls to synthetic
  `event_generate("<Configure>", ...)` (root cause 2) — the same technique
  every other `UIScaleAuto` test already uses successfully on all three CI
  legs. Also added `_grow_real_window_past_every_tested_floor()` (a single
  real `geometry("720x850")` call, comfortably within any real CI screen
  but past every tested factor's own minsize floor): without it,
  `_apply_minsize`'s own grow_only correction still reads the *real*
  window's small, un-grown size against the *forced* screen, corrupting
  `self.s` regardless of the event-generation switch — reproduced this
  distinct interaction directly (documented in the helper's own
  docstring), not assumed away.
- **`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`**
  (root cause 3) now explicitly (re-)requests the app's own default launch
  geometry and waits (`pump_until`) for `winfo_width()/height()` to
  actually reflect it before calling `_apply_ui_scale("auto")`, rather
  than trusting whatever the window happens to already be at.
- **`UIScaleStore.test_a_garbage_on_disk_value_resolves_to_auto_end_to_end`**
  (root cause 3) drops the WM-dependent `ui.s == ui._dpi_s` assertion,
  keeping only the sanitisation assertion the test is actually named for
  (`ui_scale == "auto"`); docstring updated to explain why.
- **New regression tests** for root cause 1 (`UIScaleAuto`, "round 3"
  section): `test_a_self_triggered_minsize_growth_is_tracked_as_the_new_
  expected_echo` (forces `self.s = AUTO_SCALE_MAX`, calls
  `_apply_minsize(grow_only=True)` directly — the same call
  `_on_root_resize` makes — and confirms a synthetic echo of *that* self-
  request doesn't arm a settle timer) and
  `test_a_genuine_resize_after_a_self_triggered_growth_still_settles`
  (confirms the suppression is scoped to the self-request, not "skip
  everything after the first correction").

**Sabotage-verified** (this project's standing lesson, applied to the new
fix specifically): reverted the one-line `_auto_bootstrap_wh` update in
`_apply_minsize`'s grow_only branch, confirmed
`test_a_self_triggered_minsize_growth_is_tracked_as_the_new_expected_echo`
failed with the expected assertion message (a settle timer got armed from
the self-triggered echo), then restored the fix and confirmed it passed
again — plus re-derived the exact same result via a standalone interpreter
trace before writing the test, cross-checking the test against reality
rather than trusting the test alone.

## Key decisions / tradeoffs (Round 3)

- **`INITIAL_UI_SCALE` pre-seeds the settings file before construction,
  rather than calling `_apply_ui_scale()` after it (round 2's own
  approach for these same three classes).** Mathematically, a post-
  construction `_apply_ui_scale("100")` pin can only grow the window up to
  `_apply_minsize`'s *rail-floor*-derived minimum, never back to the full
  `SIDEBAR_W`-based default `WindowResize`/`RailCollapse`'s own tests
  assert on — so *even with unlimited wait time*, a post-hoc pin cannot
  restore the exact expected default geometry once a real WM's own
  construction-time Auto correction has already moved the window away
  from it. This is a genuine, timing-independent limitation of the
  post-hoc approach, not something a longer `pump_until` could have fixed
  — confirmed by working through the `_apply_minsize` formula, not
  assumed. Constructing directly at the fixed step sidesteps the whole
  category: self.s never leaves its target value in the first place.
- **The local verification environment's Xvfb instance has a hard cap on
  simultaneous X11 clients (`Xlib.error.DisplayConnectionError: ...
  Maximum number of clients reached`) that the existing ~317-test
  `UITestCase` suite already runs close to** — each `AfkAutoclicker`
  instance opens a `pynput.mouse.Controller()` Xlib connection
  (`afk_clicker.py:2407`) that is never explicitly closed (relies on GC;
  this suite explicitly disables automatic GC, per `context.py`'s
  `gc.disable()` and `UITestCase.tearDown()`'s own comment). Verified
  directly: the pre-round-3 baseline (437 tests) passes cleanly on a
  freshly started `Xvfb :99 -screen 0 1280x1024x24`; adding even *one*
  more `UITestCase`-derived test (438) reliably fails with this exact
  error at the same point (`WindowResize.test_shrinking_past_the_
  threshold_collapses_the_rail`'s own `setUp()`); restarting Xvfb with
  `-maxclients 2048` makes the identical 439-test suite (this round's two
  new regression tests included) pass cleanly and repeatably. This
  confirms the failure is a **local verification-environment capacity
  limit**, not a bug in this round's code — and is unrelated to X11 at
  all on macOS/Windows CI, which don't use Xvfb. Documented here rather
  than silently worked around by omitting the two new regression tests,
  since `pynput.mouse.Controller()` never being released is a real,
  pre-existing gap this ticket did not introduce and is out of scope to
  fix here — **flagged as a follow-up for the reviewer/PM**, not
  addressed in this diff. (Also explains why round 1/2's own local runs,
  at 434/437 tests, stayed just under whatever this box's default
  `Xvfb` build's max-clients ceiling is, while this round's 439 needed a
  bump to verify locally — this session's `Xvfb` instance, not the
  project's CI config, which lets `xvfb-run -a` pick its own platform
  default and has passed on `ubuntu-latest` at every round so far.)

## Deviations from spec / design (Round 3)

- No deviation from `docs/spec.md`/`docs/design.md` beyond what rounds 1-2
  already recorded. This round is entirely a test-infrastructure and
  echo-detection robustness fix; the Auto formula, calibration constants,
  debounce mechanism, and Segmented layout are untouched.

## Known limitations (Round 3)

- **Still cannot verify macOS/Windows CI directly.** Every fix in this
  round was verified either by direct, sabotage-verified interpreter
  traces against real production code (root cause 1) or by making the
  affected tests pass reliably, repeatedly, under Xvfb (root causes 2-4) —
  but Xvfb has no window manager, so the *actual* async-WM timing/
  clamping behavior these fixes target is still only ever inferred from
  the CI log evidence, never directly observed locally. This round must
  be verified by pushing and re-checking `gh pr checks 89` — say so
  explicitly rather than claiming the fix closes the regression before
  that run is seen.
- **The `pynput.mouse.Controller()` connection-leak finding above is
  real but out of scope for this ticket** — not fixed here, flagged for a
  separate backlog item if the reviewer/PM agrees it's worth addressing
  (e.g., closing `self.mouse`'s underlying display in `on_close()`).
- Round 2's own known limitation (the bootstrap-echo suppression's
  "widget tree lags `self.s` until the next real trigger, on a screen far
  from 1920x1080" tradeoff) is unchanged by this round and still applies.

## Round 3, follow-up push — first push (commit `e8b2b45`) regressed ubuntu-latest

**Trigger.** Pushing round 3's first commit and re-checking `gh pr checks
89` showed real progress (macOS: 20 → 13 failures; Windows: 20 → 8
failures) but also a brand-new regression: **`ubuntu-latest`, previously
green through rounds 1-2, now failed too** — `Xlib.error.
DisplayConnectionError: ... Maximum number of clients reached`, the exact
same error already investigated and explained under "Key decisions" above
for this session's own local Xvfb. Verified directly on `ubuntu-latest`'s
own CI log (`gh run view ... --job ... --log`), not assumed: this
session's local reproduction (437 tests pass on a freshly started Xvfb;
438 — one more — reliably fails at the same `WindowResize.setUp()` call)
generalises to GitHub's own `xvfb-run -a` default Xvfb build too. This
round's own two new regression tests (net +2 `UITestCase` instances, each
opening one never-closed `pynput.mouse.Controller()` Xlib connection) were
what tipped an already-marginal budget over on `ubuntu-latest`, not just
this session's own sandbox.

**Fix.** Removed both standalone test methods
(`test_a_self_triggered_minsize_growth_is_tracked_as_the_new_expected_echo`,
`test_a_genuine_resize_after_a_self_triggered_growth_still_settles`) and
folded their assertions into the existing, round-2
`test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size`
test instead — net **zero** new `UITestCase` instances, restoring the
suite to exactly 437 tests (round 2's own last-known-green count on
`ubuntu-latest`). Confirmed locally: 437 tests pass cleanly on a fresh,
default-`-maxclients` Xvfb, repeatably.

**Further investigation of the still-failing macOS/Windows tests (same
push).** Re-examined the macOS/Windows CI logs from `e8b2b45` in detail
(not just the pass/fail summary) to find three further, concrete gaps:

- **The two `_wh_for_factor`-based "no-op guard" assertions
  (`assertNotEqual`) in `UIScaleAuto` assumed the fixture starts away
  from `AUTO_SCALE_MIN`/`AUTO_SCALE_MAX`.** On a real, large macOS/Windows
  CI screen, this fixture's own construction can *already* self-correct
  `self.s` all the way to a clamp boundary before any test body runs
  (docs/spec.md's own "first launch" edge case, now observed for real,
  not just reasoned about) — a fixed forced comparison screen can then
  coincidentally land on the *same* clamped value from both sides,
  failing the no-op guard for a real, screen-dependent reason, not
  because the underlying fix regressed.
  `test_the_bootstrap_echo_configure_does_not_arm_a_live_settle_timer`
  now picks whichever clamp extreme is furthest from `self.ui.s`'s own
  *current* value (a huge or a tiny forced screen, chosen dynamically)
  instead of a fixed `1024x768`, guaranteeing divergence regardless of
  where construction already left `self.s`. The self-triggered-growth
  scenario (now folded into `test_a_genuine_resize_still_settles_even_at_
  the_bootstrap_pixel_size`, see above) resets to a known-small real size
  first (`minsize(1, 1)` then `geometry("400x400")`, waited for via
  `pump_until`) rather than assuming room to grow was already there.
- **`_grow_real_window_past_every_tested_floor()` used a single
  `root.update()` after its own `root.geometry("720x850")` call.** Same
  gap as everywhere else in this round: on a real WM this doesn't
  synchronize, so the very first synthetic `<Configure>` the two
  `UIScaleAuto` factor-sweep tests fire could still find the *real*
  window at its small, unconverged construction-time size, reproducing
  exactly the corruption that helper exists to prevent. Switched to
  `pump_until`.
  `test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` gained
  the same class of fix: `root.minsize(1, 1)` before requesting the
  default launch geometry, since this fixture's own construction-time
  self-correction can leave a real `minsize()` floor in effect that
  silently clamps the requested geometry back up before
  `_apply_ui_scale("auto")` ever gets a chance to recompute the right one.
- **`test_shrinking_past_the_threshold_collapses_the_rail_under_auto`/
  `test_growing_back_past_the_threshold_re_expands_the_rail_under_auto`
  waited on the literal requested geometry, then a fixed `AUTO_SETTLE_MS
  + 0.2s` sleep.** Traced a genuine, reproducible mechanism (not just
  theorized): these two tests' own `target_h = int(700 * s)` isn't
  derived from the app's own aspect ratio (a pre-Auto formula, copied
  from `WindowResize`'s equivalent, where it never mattered because
  self.s was fixed) — under Auto, feeding that aspect-inconsistent
  rectangle back into `_auto_scale_factor()`'s own area-based fill
  fraction can pull `self.s` toward `AUTO_SCALE_MAX` regardless of the
  `s` originally used to compute the target, after which
  `_apply_minsize`'s own `grow_only` branch can grow the real window
  *past* what was requested. Reproduced this directly with an
  instrumented trace (`target (613, 729)` computed from `s=1.042`, actual
  landed geometry `(672, 806)` at `s=1.3`). Rewrote both tests to wait on
  the *outcome* they actually assert on (`self.ui._rail_collapsed`, then
  the settled `self.ui.side.winfo_width()` against `self.ui.s` read
  *fresh*, not the `s` captured before the resize) via `pump_until`,
  rather than the literal requested pixel geometry or a fixed sleep — both
  robust to however many self-triggered correction cascades a real WM's
  own timing produces before things settle.

**A further, broader gap found in the same CI logs.** Five *more*
existing, ui_scale-unrelated test classes
(`NumBoxFocus`, `RowValueColumn`, `MinecraftSweepHint`, `SettingsUpdates`,
`BindAllBoundOnce`) were also failing on macOS/Windows, with hardcoded
pixel expectations that assume `self.s` stays near 1.0 (e.g. observed
`140 != 182`, and `182 == int(140 * 1.3)` exactly) — the same class of
regression `WindowResize`/`RailCollapse`/`UIScale` already needed
`INITIAL_UI_SCALE` for, just not caught by round 1/2's own Xvfb-only
verification because this session's own Xvfb screen (1280x1024) happens
to keep Auto's construction-time `self.s` close enough to parity that
these five classes' hardcoded pixel values coincidentally still held.
`docs/spec.md`'s own non-goal ("non-Auto resize handling... unchanged")
applies here exactly as it did for the first three classes — none of
these five are actually about `ui_scale`/Auto. All five now also set
`INITIAL_UI_SCALE = "100"`, the same established, already-proven
mechanism, sidestepping both the stale hardcoded-pixel-value issue and
any construction-time settle/cascade risk at once, for the classes
observed failing. Not claimed exhaustive — a *different* real macOS/
Windows screen size could still expose the same gap in a class this
session's own CI run didn't happen to touch; said so explicitly rather
than implying full coverage.

## Known limitations (Round 3, follow-up push)

- **Still not verified against a fresh CI run as of writing this.** Every
  fix in this follow-up push was verified locally (this session's own
  Xvfb, at `1280x1024`, turns out to reproduce the "self.s reaches a
  clamp boundary during construction" scenario too, once traced through
  properly — useful, but still not a real window manager) or by direct,
  reproducible interpreter traces against real production code. Push and
  re-check `gh pr checks 89` before treating this as closed.
- The five newly-pinned classes were found by reading this specific CI
  run's actual failures, not by an exhaustive audit of every `UITestCase`
  subclass in the file — a residual, honestly-flagged risk that some
  other hardcoded-pixel-assuming class could still surface on a
  differently-sized real screen in a future run.
- All other Round 3 limitations above (macOS/Windows-only verification
  gap, the out-of-scope `pynput.mouse.Controller()` leak, Round 2's own
  widget-tree-lag tradeoff) still apply unchanged.

## Round 3, second follow-up push — `root.minsize()`'s own growth side effect

**Trigger.** Pushed the first follow-up (commit `353448e`) and re-checked
`gh pr checks 89`: real, large progress (`ubuntu-latest` back to green;
macOS 13 → 7 failures; Windows 8 → 1 failure), but not fully closed.
Re-read the new logs in detail rather than declaring victory early.

**Root cause, found by direct experiment, not just log-reading.** All
remaining macOS failures were the exact `AUTO_SCALE_MIN`-floor symptom
`_suppress_self_triggered_real_growth()` was already built to prevent —
meaning that fix's own `root.geometry()` stub wasn't sufficient. Tested
the natural next hypothesis directly in an interpreter:

```python
root.geometry("300x300"); root.update()      # 300 300
root.minsize(500, 500); root.update()        # 500 500 <- !
```

**`root.minsize()` itself silently grows the real window to meet a new
floor — no `root.geometry()` call involved at all**, confirmed
independent of any window manager (this reproduces under Xvfb, which has
none). `_apply_minsize()` calls `root.minsize()` *unconditionally*, every
time it runs — so this side effect alone, entirely separate from its own
explicit `grow_only` `geometry()` call, is enough on its own to trigger a
further real `<Configure>`, which Auto mode feeds straight back into
`_auto_scale_factor()`, which can call `_apply_minsize()` again — a
cascade with no natural end on a real window manager whose own
confirmation timing this suite can't control. Traced one such cascade
directly for the rail-collapse-under-Auto tests: requested `(613, 729)`,
landed at `(672, 806)` after two further self-triggered rounds, each one
a genuine, real `<Configure>` this test never asked for.

**What changed** (`tests/test_ui.py`, `UIScaleAuto`):
- New `_stub_minsize_without_growth_side_effect()`: monkeypatches
  `root.minsize()` to track the requested value in a plain Python dict
  (so a later *query* — e.g.
  `test_minsize_tracks_the_live_scale_during_a_continuous_shrink`'s own
  assertion — still returns the right thing) without ever calling the
  real Tk command, so its growth side effect never fires. Monkeypatch-
  and-restore, this repo's own established style for a seam like this
  (`SaveFailureNotice._break_saves()`/`_fix_saves()`) — no
  `unittest.mock`.
- `_suppress_self_triggered_real_growth()` (renamed from the earlier
  `_grow_real_window_past_every_tested_floor()` — replaced entirely, not
  layered on top) now stubs **both** `root.geometry()` (a flat no-op) and
  `root.minsize()` (via the new shared helper), for
  `test_s_strictly_increases_with_increasing_window_size` and
  `test_minsize_tracks_the_live_scale_during_a_continuous_shrink`, which
  drive Auto entirely through synthetic `<Configure>` events and need no
  real resize at all.
- `test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` now
  calls the same shared helper right after its own deliberate
  `root.geometry()` call lands, so `_apply_ui_scale("auto")`'s own tail
  call to `_apply_minsize()` can't grow the window back away from the
  exact default geometry this test just placed it at.
- `test_shrinking_past_the_threshold_collapses_the_rail_under_auto`/
  `test_growing_back_past_the_threshold_re_expands_the_rail_under_auto`
  (the one test still failing on Windows CI after the first follow-up)
  call the shared helper too, but do **not** stub `root.geometry()` —
  these tests' own single, deliberate `geometry()` call is a real
  premise they still need to exercise; only `_apply_minsize()`'s own
  *redundant, uncontrolled* follow-on resizes needed to be made
  impossible.

**Verification.** Confirmed the `root.minsize()` growth side effect
directly (above) before writing any fix, not assumed from the log
symptom alone. Full local suite green (437 tests) after all of the
above; `UIScaleAuto` re-run individually multiple times for stability.
Not yet re-checked against `gh pr checks 89` as of writing this section —
say so explicitly per this round's own standing practice.

## Key decisions / tradeoffs (Round 3, second follow-up push)

- **This finding likely explains several earlier rounds' own residual
  failures too, not just the ones named above** — any Auto-mode test that
  triggers a *real* self.s change via a real `root.geometry()`/`<Configure>`
  sequence was implicitly exposed to this same cascade risk, whether or
  not this session's own Xvfb happened to reproduce it. Not retrofitted
  onto every such test speculatively; only the ones this round's actual
  CI evidence named as still failing were changed, per this round's own
  practice of fixing what the evidence shows rather than what might
  theoretically also be affected.
- **Not filed as a production-code bug.** `root.minsize()`'s own growth
  side effect is standard, documented Tk behavior (a `wm minsize` request
  is itself an implicit resize-up if the window is currently smaller) —
  it's a *test*-only hazard here because these tests read/force `self.s`
  through seams (`event_generate`, direct attribute assignment) a real
  user's own resize never exercises in the same rapid, artificial
  sequence. Production code's own real-WM interaction was already
  understood to be asynchronous and eventually-consistent (Round 2/3's
  own `is_bootstrap_echo`/self-requested-geometry tracking exists
  precisely because of it) — this finding sharpens *why* a real WM's
  confirmation can arrive as a multi-step cascade rather than a single
  round trip, but doesn't change the production fix itself.

## Round 3, third follow-up push — the one remaining rail-collapse test, and the near-1920x1080 test

**Trigger.** Pushed the second follow-up (`e5eae07`) and re-checked `gh
pr checks 89`: `ubuntu-latest` stayed green; macOS 7 → 2 failures
(one a one-off, not-previously-seen `UpdateLogPrompt` clipboard flake —
passed clean on every one of this round's three earlier CI runs, so
treated as pre-existing CI flakiness, not a regression this diff caused,
and not chased further given the evidence); Windows 8 → 1 → still 1,
the exact same `test_shrinking_past_the_threshold_collapses_the_rail_
under_auto` failure (`208 != 83`) as the previous push, meaning the
`root.minsize()`-side-effect stub from the second follow-up wasn't
sufficient for this specific test either.

**Root cause.** `_stub_minsize_without_growth_side_effect()` only
neutralises `root.minsize()`'s own growth side effect — but
`_apply_minsize()` also makes its own **explicit** `root.geometry()` call
in its `grow_only` branch (a second, independent source of exactly the
same self-triggered cascade), and this rail-collapse test's own single,
deliberate `root.geometry()` call goes through that very same
`self.root.geometry` attribute. There's no way to stub "only the other
caller's" use of the same method.

**Fix.** New `_suppress_apply_minsize_side_effects()`: monkeypatches
`self.ui._apply_minsize` itself to a no-op for the rest of the test.
`_apply_minsize()` is only ever called from `_on_root_resize()` (this
fixture's own auto-mode handling), `__init__()`, and `_apply_ui_scale()`
— none reachable once a test is already running — and neither
`self._rail_collapsed` nor the settled rebuild these two tests actually
assert on depend on it (both come from `_on_root_resize()`'s own
`self.s`/collapsed-flag bookkeeping, and `_rebuild_ui()`'s own direct use
of `self.s`). No-opping it removes both of its side effects (the
`minsize()` call and its own explicit `geometry()` growth call) at once,
while leaving the test's own deliberate `root.geometry()` call — the real
premise it exercises — untouched. Applied to both
`test_shrinking_past_the_threshold_collapses_the_rail_under_auto` and
`test_growing_back_past_the_threshold_re_expands_the_rail_under_auto`,
replacing their earlier `_stub_minsize_without_growth_side_effect()` call.

**`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`
rewritten, not further patched.** This was the other still-failing test
(2 macOS failures = 1 flake + this one). Across this round's three pushes
it was fixed three separate ways — `pump_until` on the literal requested
geometry, resetting `minsize()` first, then suppressing `_apply_minsize`'s
own side effects — and still landed away from the requested default
geometry on macOS CI every single time, an async real-WM round trip this
suite has no way to bound with certainty from here. Re-read the test's
own docstring rather than trying a fourth timing fix: *"The wiring, not
just the formula: `_apply_ui_scale('auto')` must actually use it"* — the
test is about the wiring, not about reproducing a literal on-screen
resize (which `_apply_minsize()`'s own unconditional bootstrap call in
`__init__`, exercised by every other `UITestCase`-based test already, is
what actually requests). Rewritten to force
`self.root.winfo_width`/`winfo_height` directly to the app's own default
launch dimensions — the same "force the attribute/method directly"
technique `FontSizeFloorAtWorstCaseScale` already uses for `_dpi_s` —
instead of requesting a real resize and hoping it lands. This fully
decouples the test from real-WM timing while still exercising exactly
what its own docstring says it verifies.

**Verification.** Full local suite green (437 tests) after both changes;
`UIScaleAuto` re-run individually for stability. Not yet re-checked
against `gh pr checks 89` as of writing this section.

## Deviations from spec / design (Round 3, third follow-up push)

- **`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` no
  longer exercises a real window resize at all**, a narrowing from the
  spec's own acceptance criterion wording ("the window at its default
  launch geometry"), which literally describes a real geometry, not a
  forced attribute. Judged acceptable because: (a) the *real* geometry
  request this test's premise depends on is `_apply_minsize()`'s own
  unconditional `__init__`-time call, already exercised (and asserted on
  indirectly) by every other `UITestCase`-based test in the file, so
  nothing about that mechanism goes untested; (b) three different attempts
  to make the literal real-resize version reliable on macOS CI within
  this round all failed for reasons rooted in real-WM async timing this
  test suite cannot control, not in the code under test; (c) the
  acceptance criterion's own explanatory clause in `docs/spec.md`
  ("Given `ui_scale == auto` and the window at its default launch
  geometry... self.s is within a small tolerance of `self._dpi_s * 1.0`")
  is really asking whether `_apply_ui_scale("auto")` reads the window's
  current size and applies the formula correctly — exactly what the
  rewritten test still verifies, just without the flaky real-resize
  precondition. Flagged explicitly rather than silently narrowed.

## Round 3, fourth follow-up push — two more root causes, and where this round stops

**Trigger.** Pushed the third follow-up (`fa8d004`) and re-checked `gh pr
checks 89`: `ubuntu-latest` still green. macOS 2 → 2, but a *different*
pair: the winfo-forcing rewrite of `test_ui_scale_auto_is_near_parity_
on_a_near_1920x1080_screen` still failed the same way, and a new,
previously-never-seen `test_the_settle_timer_resets_on_each_new_event_
not_just_the_first` failure appeared (an existing, untouched-by-this-
round test). Windows: still the one
`test_shrinking_past_the_threshold_collapses_the_rail_under_auto`
failure, same `208 != 83`.

**`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`, actual
root cause found.** The winfo-forcing rewrite computes `self.s`
correctly and synchronously in plain Python, matching the earlier
assumption — but the test still called `self.root.update()` immediately
afterward, "to be safe." That single `update()` can drain a real,
still-in-flight `<Configure>` this fixture's own construction left
queued (this round's own recurring theme, now confirmed to also apply
*after* `UITestCase.setUp()`'s own wait, not just during it), firing
`_on_root_resize()` and silently overwriting the carefully-computed
`self.s` with one read from the *real* window's own current size. Fixed
by removing that `root.update()` call entirely — nothing about reading
`self.ui.s` right after a synchronous Python computation needs the event
loop pumped, and not pumping it removes the only way a stray queued
event could still reach `_on_root_resize()` before the assertion.

**`test_the_settle_timer_resets_on_each_new_event_not_just_the_first`**
is pre-existing (round 1/2), untouched by any round-3 commit, and had
never failed in any of this round's five earlier CI runs across both
platforms before this one. Its own assertions depend on three chained,
fixed-duration `pump()` calls (`AUTO_SETTLE_MS * 0.6` three times) rather
than a condition-based `pump_until` — exactly the pattern this round
replaced everywhere else it touched for this same reason. Treated as
CI-load flakiness in an untouched test, not a regression from this
diff — noted for the reviewer rather than fixed here, since touching a
test with no CI evidence tying it to this ticket's own changes would be
scope creep beyond what the evidence supports.

**`test_shrinking_past_the_threshold_collapses_the_rail_under_auto`,
narrowed but not fully closed.** Despite `_suppress_apply_minsize_side_
effects()` (the third follow-up's own fix) removing `_apply_minsize()`'s
two side effects entirely, this test still fails identically. Traced as
far as: the collapse *flag* update is unconditional in `_on_root_resize()`
(runs regardless of `is_bootstrap_echo`), matching the fact that
`self.assertTrue(self.ui._rail_collapsed)` never fails — but the
*settled rebuild* is gated behind `not is_bootstrap_echo`, matching the
fact that `self.ui.side` never updates. The only way both symptoms
co-occur is if the event this test's own `root.geometry()` call produces
is itself being recognized as a bootstrap echo — but hand-checked the
arithmetic (`target_w`/`target_h` vs. `_auto_bootstrap_wh`'s own known
formula) and found no exact-match collision under the values this test
computes. Applied the two lowest-risk, well-justified improvements found
during this investigation — `root.minsize(1, 1)` reset before suppressing
`_apply_minsize()` (closes a real, if unconfirmed, risk: a stale
construction-time floor could otherwise silently clamp this test's own
`geometry()` request) and a more generous `pump_until` timeout (3.0s →
5.0s, in case this is genuinely a slow-settling-on-a-loaded-runner issue
rather than a suppressed rebuild) — but **could not fully confirm or
close this one from this session**, with no real Windows access to
instrument further. Documented here as an open item rather than claimed
fixed.

**Where this round stops.** Five pushes into round 3:
`ubuntu-latest` has stayed green since the second push; macOS is down to
one pre-existing, untouched, apparently-flaky test with no CI evidence
connecting it to this diff; Windows has one remaining, real,
not-yet-fully-explained failure in `test_shrinking_past_the_threshold_
collapses_the_rail_under_auto`. This is reported honestly as **not fully
green**, not as closed — per this session's own standing instruction to
push and verify via `gh pr checks 89` rather than claim success before
seeing it, and per the point in a bugfix cycle where further guessing
without real macOS/Windows access stops being productive use of local
Xvfb-only verification. The next step is a fresh pair of eyes (the
reviewer's own testing pass, or a session with real Windows access) on
specifically `test_shrinking_past_the_threshold_collapses_the_rail_
under_auto`'s own remaining failure.

## Round 3, sixth push — pushed, re-checked, still one failure per platform

Pushed the fifth follow-up (`f18164d`) and re-checked `gh pr checks 89`
one final time this session: `ubuntu-latest` green (confirmed green
across every push since the second follow-up).
`test_the_settle_timer_resets_on_each_new_event_not_just_the_first` did
**not** recur on macOS this run — consistent with the "pre-existing,
untouched, CI-load flake" read above, not a regression.

`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` **still
failed on macOS with the identical `0.9 != 0.7506955224494027`
result**, despite the winfo-forcing rewrite (which computes `self.s`
purely synchronously from two monkeypatched methods, with no
`root.update()` call anywhere in the test) locally passing deterministically,
5/5 repeated runs. This is now a genuinely unexplained result from this
session's own vantage point: the calibration formula guarantees
`_auto_scale_factor(default_w, default_h)` against the forced
`(1920, 1080)` screen equals `self.ui._dpi_s` exactly (confirmed by
`test_calibration_lands_at_parity_on_a_1920x1080_screen`'s own passing
assertion, unmodified, in the very same class), so a value pinned at
`AUTO_SCALE_MIN` can only mean `self.root.winfo_width()`/`winfo_height()`,
as called from `_apply_ui_scale()`, are not returning the monkeypatched
`default_w`/`default_h` on this platform — a discrepancy this session
could not reproduce or further diagnose without real macOS access.

`test_shrinking_past_the_threshold_collapses_the_rail_under_auto` also
still failed on Windows, identically (`208 != 83`), after the
`root.minsize(1, 1)` reset and the widened `pump_until` timeout.

**Final status of this bugfix cycle, reported honestly:** `ubuntu-latest`
green; two failures remain, one per platform
(`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` on
macOS, `test_shrinking_past_the_threshold_collapses_the_rail_under_auto`
on Windows), down from ~20 per platform at the start of this round. Both
remaining failures are in `UIScaleAuto`, both were investigated at length
across multiple pushes with concrete, verified partial fixes (each push's
own root-cause analysis narrowed the failure count and changed the
specific symptom, confirming real progress, not just re-shuffling), and
both are now genuinely resistant to further progress from Linux-only,
Xvfb-based local verification. Recommended next step: a reviewer/session
with real macOS and/or Windows access to instrument these two specific
tests directly (e.g., a temporary print of `self.root.winfo_width()`'s
actual return value right before the failing assertion, to confirm or
rule out the monkeypatch-not-taking-effect hypothesis above).

## Round 4 — reviewer testing pass (BLOCKED), Defects 1 and 3 fixed

**Trigger.** `docs/test-review.md`'s round-3 re-test verdict was **BLOCKED**,
not accept-and-document: the round-3 macOS failure
(`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`) was
root-caused to a real, confirmed production bug (Defect 1), and one of
round 3's own two regression tests for the self-triggered-echo mechanism
(`test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size`)
was found to be tautological, with zero discriminating power (Defect 3).
The Windows failure (Defect 2) was left as "investigate further, possibly
entangled with Defect 1" — this round's own instruction was to fix
Defects 1 and 3 first, push, and check whether Defect 2 (Windows) survives
independently before spending an extra CI round on instrumentation.

**Defect 1 — `_auto_scale_factor()`'s clamp bounds were DPI-absolute, not
DPI-relative.** Verified the reviewer's repro directly against real code
before touching anything (`docs/test-review.md`'s exact values:
`self._dpi_s = 0.7506955224494027`, screen forced to
`AUTO_REF_SCREEN_W/H`, default launch geometry scaled by `_dpi_s`) —
reproduced `self.ui.s == 0.9` instead of the expected `0.7506955224494027`
bit for bit.

**Root cause, and why the "obvious" fix (multiplying the whole clamped
result by `self._dpi_s`) is wrong.** `width`/`height` passed into
`_auto_scale_factor()` are always *real* window pixel dimensions, and the
window's own real geometry is always sized off `self.s` (which is itself
`self._dpi_s * something` — see `_apply_minsize()`'s `not grow_only`
branch and every fixed step's `self.s = self._dpi_s * UI_SCALE_FACTORS[value]`).
So `self._dpi_s` is already baked into the raw `fill / AUTO_REFERENCE_FILL`
ratio for any window sized the way this app actually sizes windows — the
bug was never a *missing* multiplication, only that the **clamp bounds**
(`[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`) were the plain literals instead of
`self._dpi_s * [AUTO_SCALE_MIN, AUTO_SCALE_MAX]`. Verified this
concretely, not just reasoned, before picking a fix: multiplying the
clamped raw factor by `self._dpi_s` a second time (the reviewer's own
"option 1") double-counts it and gives `0.9 * 0.7506955224494027 ≈ 0.676`
against the macOS repro's own expected `0.7506955224494027` — confirmed
this fails via `test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`
(a pre-existing, spec-required test) regressing under that approach.
Scaling the **bounds** instead (`lo, hi = self._dpi_s * AUTO_SCALE_MIN,
self._dpi_s * AUTO_SCALE_MAX`, leaving the raw factor itself untouched)
reproduces the exact expected parity value and keeps every pre-existing
Auto test green.

**What changed** (`afk_clicker.py`):
- `_auto_scale_factor()` (`~line 2707`): the clamp is now
  `min(self._dpi_s * AUTO_SCALE_MAX, max(self._dpi_s * AUTO_SCALE_MIN, factor))`
  instead of the raw `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]` literals. Docstring
  rewritten to explain both why the raw factor already carries
  `self._dpi_s` (for real window geometry) and why the bounds — not the
  factor — needed to become DPI-relative, including the rejected
  "multiply again" alternative and why it double-counts.

**New regression test** (`tests/test_ui.py`, `UIScaleAuto`):
`test_auto_is_not_floored_at_the_raw_clamp_on_a_low_dpi_display` — forces
`self.ui._dpi_s = 0.75` (macOS CI's own observed class of value, an
ordinary non-Retina headless-VM number, well under `AUTO_SCALE_MIN = 0.9`),
same "force the attribute directly" technique
`FontSizeFloorAtWorstCaseScale` already uses for `_dpi_s`, and asserts
`self.ui.s` is *not* floored at the raw `0.9` and instead lands near
`self._dpi_s`. Confirmed red before the fix (`0.9 == 0.9 within 2 places`,
reproducing the exact macOS CI symptom), green after. This closes the
coverage gap round 1's own test-review (Finding 1) originally flagged and
that let the bug ship three rounds in a row.

**Sabotage-verified**: reverted the clamp bounds to the raw
`[AUTO_SCALE_MIN, AUTO_SCALE_MAX]` literals, confirmed the new test failed
with the exact pre-fix symptom, restored the fix, confirmed green again;
`git diff --stat` empty before and after the revert/restore cycle.

**Test-only fallout from correcting the clamp range.** Two existing tests
asserted values that were only ever correct because the old, buggy clamp
happened to coincide with `self._dpi_s ≈ 1.04` (this session's own Xvfb
box) landing close to the raw `[0.9, 1.3]` bounds — neither is a spec/
design change, both are the same class of "test asserted a stale literal
that a legitimate range widening invalidated" fix already used elsewhere
in this cycle (see `RowValueColumn`/`UIScale` fixes in the original
Changes-by-file section above):
- `test_calibration_lands_at_parity_on_a_1920x1080_screen` now forces
  `self.ui._dpi_s = 1.0` explicitly, isolating the calibration constant
  itself (`factor == 1.0` at the reference screen) from whatever `_dpi_s`
  the test box happens to report — the clamp bounds are now `_dpi_s`-
  dependent, so this pure-formula check needs `_dpi_s` pinned to stay
  meaningful regardless of the run environment, the same "independent of
  the real screen this suite happens to run under" principle its own
  docstring already states, extended to `_dpi_s`.
- `test_s_strictly_increases_with_increasing_window_size`'s bounds check
  (`self.ui.s` between `AUTO_SCALE_MIN`/`AUTO_SCALE_MAX`) now compares
  against `self.ui._dpi_s * AUTO_SCALE_MIN/MAX` instead of the raw
  literals — the correct range post-fix.
- `test_growing_back_past_the_threshold_re_expands_the_rail_under_auto`'s
  `grown_w = threshold + 200` margin was only ever enough to clear the
  rail-collapse threshold because the *buggy* clamp ceiling (`1.3`) was
  lower than the *correct* one (`self._dpi_s * 1.3 ≈ 1.355` on this box) --
  growing the window also grows `self.s` (this test's own `target_h` isn't
  aspect-consistent, the same round-3-documented quirk as its shrinking
  sibling), so a margin that cleared the old, lower ceiling no longer
  clears the corrected, higher one. Replaced with a margin computed off
  the worst case `self.s` can ever reach post-fix
  (`self._dpi_s * AUTO_SCALE_MAX`), robust regardless of where `self.s`
  actually lands mid-grow.

**Defect 3 — `test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size`
had no discriminating power.** Confirmed the reviewer's sabotage findings
independently before rewriting anything: the old test read
`self.ui._auto_bootstrap_wh` back *after* calling
`self.ui._apply_minsize(grow_only=True)`, then fed that same value into
its own synthetic `<Configure>` — by construction, always an echo of
itself, regardless of whether the tracking under test actually worked.

**Fix**, following the reviewer's own suggested approach: compute the
expected grown `(width, height)` independently, from the same formula
`_apply_minsize()`'s own grow_only branch uses
(`max(cur_w, minw), max(cur_h, minh)`), *before* calling it — then assert
`self.ui._auto_bootstrap_wh` matches that independently-computed value
(a real, discriminating check on its own), and use the independently-
computed value, not the attribute read-back, to fire the synthetic echo.

**A second, real bug this rewrite surfaced in the test's own setup, not
just its assertion.** Making the pre-existing `self.root.geometry("400x400")`
reset actually *land* at 400x400 (a precondition the old, tautological
test never actually verified) exposed that resetting the real window while
Auto mode's own live `_on_root_resize()`/`_apply_minsize()` tracking is
active is itself an uncontrolled self-triggered growth cascade: a real
`<Configure>` reporting 400x400 recomputes a small `self.s` from the
real screen, whose own minsize floor then exceeds 400, growing again,
recomputing `self.s` again, converging back at the clamp ceiling rather
than ever actually settling at 400x400 — traced directly, reproducibly
landing at exactly `self._dpi_s * AUTO_SCALE_MAX`'s own `minw`/`minh`
(`(700, 840)` on this session's own box) instead of `(400, 400)`. This is
almost certainly why the *old* test's own explicit
`self.ui._apply_minsize(grow_only=True)` call was silently a no-op in
every prior round (the window was already bigger than the floor from this
leftover cascade by the time that call ran, so its own `if` branch never
fired) — the deepest root of Defect 3, not just the read-back-after-write
ordering bug the reviewer named.

Fixed by suppressing both `self.ui._apply_minsize` *and*
`self.ui._request_auto_settle` (monkeypatch-and-restore, this repo's own
established style for a seam like this) for the 400x400 reset only —
`_apply_minsize` suppression breaks the growth chain so the real window
actually lands at 400x400; `_request_auto_settle` suppression prevents a
stray settle job from `self.s`'s own live recompute (unconditional on
`_apply_minsize` doing anything) leaking into the mechanism-under-test
phase that follows. A new assertion (`self.ui._auto_settle_after_id is
None` right after the reset) confirms the reset itself left no stray job
behind, before the test's own real assertions begin.

**Sabotage-verified** (this round's own fix, independently of the
reviewer's original round-3 sabotage): reverted `_apply_minsize()`'s
grow_only branch's `self._auto_bootstrap_wh = (new_w, new_h)` line,
confirmed the rewritten test now correctly **fails**
(`(688, 646) != (672, 806)`) — the exact regression Defect 3 said this
test was supposed to catch and didn't — restored the fix, confirmed green
again.

**Verification.**
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.UIScaleAuto -v
# Ran 14 tests, OK (13 existing + 1 new)
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
# Ran 438 tests in ~79s, OK (skipped=10)
```
Full suite run twice for stability; both clean. 438 = round 3's own
437-test baseline + 1 new test this round
(`test_auto_is_not_floored_at_the_raw_clamp_on_a_low_dpi_display`).
`git diff --stat` confirms only `afk_clicker.py`/`tests/test_ui.py`
touched, matching this cycle's established scope.

**Defect 2 (Windows).** Not yet investigated this round — per the
dispatch's own instruction, Defect 1's fix is pushed first and `gh pr
checks 89` checked before spending effort on Defect 2's instrumentation,
since Defect 1's clamp-range fix changes what `self.s` values Auto-mode
tests (including the still-failing Windows one) can actually reach, which
may shift or resolve that failure's own behavior. See the next section
for the result of that check and, if still failing, the follow-up.

## Round 4, first push — real CI surfaced a low-DPI-specific test gap Defect 1's own fix opened up

**Trigger.** Pushed Defects 1/3's fix (commit `5132a10`) and checked `gh pr
checks 89`: **all three platforms failed**, including `ubuntu-latest`
(previously green since round 3's second follow-up) — a real, different
failure shape per platform, not the same two lingering failures as before.
Investigated each from the actual CI logs
(`gh run view 35341495153 --job <id> --log`), not guessed.

**`ubuntu-latest`: `test_updater.SwapScriptLogLifecycle` (6 failures),
unrelated to `test_ui.py`.** Root cause, read directly from the log:
`Xlib.error.DisplayConnectionError: ... Maximum number of clients
reached` — the exact, already-documented (round 3's own "Key decisions")
Xvfb client-connection-budget ceiling. This round's Defect 1 regression
test added one net-new `UIScaleAuto`-derived `UITestCase` instance (438
total), and round 3's own local reproduction already established that
438 (one more than the 437 round 3 settled on) reliably tips
`ubuntu-latest`'s default `xvfb-run -a` build over budget. Not a new bug —
the same capacity ceiling round 3's "follow-up push" hit and fixed the
same way.

**`macos-latest`: 8 failures, a mix of a genuinely fixed test and new
ones Defect 1's own correction opened up.**
`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` — the
*original* target of this whole round — is **not** in the new failure
list, confirming Defect 1's fix closed the bug it was meant to close. The
8 new failures are a different, previously-masked gap: several
`UIScaleAuto` tests use a fixed list of raw factor literals (e.g. `1.0,
1.1, 1.2, 1.28`) as targets for `_wh_for_factor()`, comparing/expecting
distinct `self.ui.s` values at each step. Before Defect 1's fix, the
clamp ceiling was the flat literal `1.3` regardless of DPI, comfortably
above every tested factor, so none of them ever saturated. After the fix,
the ceiling is `self._dpi_s * 1.3` — on macOS CI's own observed low
`_dpi_s` (~0.75, `0.75*1.3 ≈ 0.976`), several of the tested factors (`1.0`
through `1.28`) now all exceed that ceiling and clamp to the *same* value,
breaking tests that expected them to stay distinct/monotonic. This is a
test-literal problem, not a regression in the fix itself: confirmed by
reproducing the exact symptom locally with `self.ui._dpi_s` forced to
macOS's own observed value, then confirming each fix below resolves it
under the same forced value.
- `test_s_strictly_increases_with_increasing_window_size`,
  `test_minsize_tracks_the_live_scale_during_a_continuous_shrink`: every
  raw factor literal passed to `_wh_for_factor()` is now scaled by
  `self.ui._dpi_s` first (`self.ui._dpi_s * factor`), keeping each one
  proportionally inside `(self._dpi_s * 0.9, self._dpi_s * 1.3)`
  regardless of what `_dpi_s` the box/CI runner reports — the same
  principle as the production fix itself, applied to the test inputs.
- `test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size`'s
  own trailing "genuine resize after a self-triggered growth still
  settles" check used a fixed `_wh_for_factor(1.15)` — on macOS's low
  `_dpi_s` this could clamp to the exact same ceiling `self.ui.s` was
  already at from the growth step earlier in the same test, making the
  event a silent no-op. Replaced with the same "pick whichever clamp
  extreme is furthest from `self.ui.s`'s own current value" technique
  `test_the_bootstrap_echo_configure_does_not_arm_a_live_settle_timer`
  already uses, guaranteeing divergence regardless of where prior steps
  left `self.s`.
- `WindowMinimumHeight.test_default_launch_height_equals_the_floor`
  (`465 != 418`) — a **different, non-`UIScaleAuto`** class, and a
  genuinely new exposure, not a test-literal issue. This test reads
  `self.ui.s`/`self.root.winfo_height()` and assumes they stay in
  lockstep — an assumption a real WM's own construction-time Auto
  self-correction can legitimately break when the correction is
  *downward* (`_apply_minsize()`'s `grow_only` branch never shrinks an
  already-larger real window, so a lower corrected `self.s` leaves the
  real window's height stale relative to `self.ui.s`, exactly round 2's
  own documented, accepted widget-tree-lag tradeoff). Before Defect 1's
  fix, the buggy clamp only ever pushed `self.s` *upward* (toward
  `AUTO_SCALE_MIN`, which was numerically *higher* than a very low real
  `_dpi_s`), which coincidentally kept this test passing by growing the
  real window to match; the corrected clamp can now push `self.s`
  downward too, exposing the lockstep assumption for the first time. Same
  fix as `WindowResize`/`RailCollapse`/five other classes already needed
  in round 3: added `INITIAL_UI_SCALE = "100"` (this class tests generic,
  non-Auto height-floor mechanics, per `docs/spec.md`'s own non-goal).
- `test_the_settle_timer_resets_on_each_new_event_not_just_the_first`
  also failed (`1 != 0`), but at the *first* `pump()` check, before the
  second event even fires — the identical shape to round 3's own
  documented pre-existing, untouched, CI-load-dependent flake (chained
  fixed-duration `pump()` calls rather than a condition-based wait). Not
  touched here, same reasoning round 3 gave: no CI evidence ties this
  specific failure shape to this diff's own changes, so fixing it would
  be scope creep beyond what the evidence supports.

**`windows-latest`: unchanged, still exactly the one pre-existing
Defect 2 failure** (`test_shrinking_past_the_threshold_collapses_the_rail_
under_auto`), same symptom as before. Confirms Defect 1's fix did not
resolve Defect 2 — they are independent, not entangled, contrary to the
"worth checking first" possibility the dispatch flagged. Defect 2 is
still open, unchanged from `docs/test-review.md`'s own description.

**Fix for the `ubuntu-latest` Xvfb-budget regression.** Folded the new
Defect 1 regression assertions into the existing
`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen` (a second
phase within the same test/fixture: re-forces `self.ui._dpi_s` to the
low-DPI value and re-stubs `winfo_width`/`winfo_height` for the new
default geometry, then re-applies `_apply_ui_scale("auto")` and asserts
both the "not floored at the raw clamp" and "lands near `_dpi_s`"
conditions) rather than a standalone new test method — net **zero** new
`UITestCase` instances, restoring `UIScaleAuto` to 13 tests and the full
suite to 437, matching round 3's own last-known-green `ubuntu-latest`
count. Same technique, same reasoning, as round 3's own "follow-up push"
section.

**Verification.** Re-ran the full local suite twice (437 tests,
`OK (skipped=10)`, stable). Re-sabotage-verified Defect 1's fix against
the *folded* test (reverted the DPI-relative clamp bounds, confirmed the
folded test still correctly fails with the exact pre-fix symptom,
restored, confirmed green). Locally simulated macOS CI's own low
`_dpi_s` (forcing `self.ui._dpi_s = 0.7506955224494027`, the exact
observed value) against each of the three fixed tests individually,
confirming each now passes under that forced value — the closest this
session can get to reproducing the real macOS symptom without macOS
access itself.

Pushed this fix; see the next section for the result.

## Deviations from spec / design (Round 4)

No deviation from `docs/spec.md`/`docs/design.md`. Defect 1's fix is a
correction to `_auto_scale_factor()`'s own implementation to match
`docs/spec.md` §2's own prose ("clamped to the same range the fixed steps
already cover") — the fixed steps' real range is DPI-relative
(`self._dpi_s * [0.9, 1.3]`), and the corrected clamp now actually
delivers that, closing the gap between the spec's prose and its literal
constant definitions (`AUTO_SCALE_MIN`/`MAX` themselves are unchanged,
still `UI_SCALE_FACTORS["90"]`/`["130"]` — only where/how they're applied
changed). Defect 3's fix, the `ubuntu-latest` test-count fold, the
DPI-scaled test-literal fixes, and `WindowMinimumHeight`'s
`INITIAL_UI_SCALE` addition are all test-only, no further production-code
change beyond Defect 1's own fix.

Pushed this fix (commit `05bbb83`); `gh pr checks 89` result: `ubuntu-latest`
and `macos-latest` both green. `macos-latest` did show one failure
(`test_the_settle_timer_resets_on_each_new_event_not_just_the_first`) on
the *next* push below, matching round 3's own already-documented
pre-existing, CI-load-dependent flake — not touched, per that same
established reasoning. `windows-latest` still failed, identically
(`208 != 83`), confirming Defect 2 is independent of Defect 1, not
entangled — the "worth checking first" possibility the dispatch flagged
did not pan out.

## Round 4 — Defect 2 (Windows), root-caused and fixed via instrumentation

**Approach**, per the dispatch's own suggested next step and the
reviewer's recommendation: added temporary, env-var-gated
instrumentation to `_on_root_resize()`'s Auto branch (`afk_clicker.py`,
inert unless `AFK_DEBUG_AUTO_RESIZE` is set — a no-op everywhere else),
and set that var only for the one failing test
(`test_shrinking_past_the_threshold_collapses_the_rail_under_auto`),
printing `is_bootstrap_echo`/`self._auto_bootstrap_wh`/`(event.width,
event.height)`/`s_changed`/`collapsed_changed`/`self.s`/`rail_collapsed`
for every qualifying event. Pushed (commit `11dd695`) and pulled the real
values from `gh run view ... --log`.

**What the real Windows values showed**, and why the hand-analysis
across three rounds never found it: both `<Configure>` events this
test's own resize produced showed **`s_changed=False`,
`collapsed_changed=False`, `self.s` already pinned at the clamp ceiling
(`1.3000051981014935 ≈ self._dpi_s * AUTO_SCALE_MAX` with
`self._dpi_s ≈ 1.0`), and `rail_collapsed=True`** — for *both* events,
not just an echo being misclassified as suspected in every prior round's
own theory. This ruled out the is_bootstrap-echo-misclassification
hypothesis every prior round centered on (`is_bootstrap_echo=False` for
both events) and pointed to something upstream of this test's own resize
entirely.

**Root cause.** On a real Windows CI screen, construction's own bootstrap
`<Configure>` (the genuine "first launch on an unusual screen" self-
correction `docs/spec.md` itself names as intended behavior) already
pushes `self.s` to the clamp ceiling and flips `self._rail_collapsed` to
`True` — correctly, live, per round 2's own design (steps 1-3 of
`_on_root_resize()`'s Auto branch are unconditional). Because that
particular event is a genuine bootstrap echo, the settled **rebuild**
is (also correctly, by round 2's own design) suppressed for it — so
`self.ui.side` stays at its construction-time, *expanded* rendered
width, out of sync with the now-already-collapsed `self.s`/flag (round
2's own named, accepted "widget tree lags self.s" tradeoff). This
test computed its own `target_w`/`target_h` **relative to whatever
`self.ui.s` already was** at test-body start, without verifying that
value was still a *pre-collapse* baseline — on Windows CI, it wasn't.
Compounded by round 3's own already-documented aspect-inconsistency
(`target_h = int(700 * s)` isn't derived from the app's real aspect
ratio, which independently pulls `self.s` back toward the same ceiling
regardless of the nominal target): the test's own computed target
geometry, fed through `_auto_scale_factor()` against the real Windows
screen, landed at the *exact same* `self.s`/collapsed state already in
effect — `s_changed`/`collapsed_changed` both `False`, so no settle ever
got requested, and `self.ui.side` was left showing the stale, expanded
width forever. This is a genuinely different root cause than every
earlier round's own working theory (an echo misclassification) — the
event was never being misclassified; it just never represented a change
from an already-diverged starting point.

**Fix** (`tests/test_ui.py`, both `test_shrinking_past_the_threshold_
collapses_the_rail_under_auto` and its `test_growing_back_past_the_
threshold_re_expands_the_rail_under_auto` sibling, which has the
identical exposure in its own initial shrink-to-collapse phase even
though it wasn't the one observed failing — likely because its later
grow step already uses round 4's own `worst_case_threshold`-based
margin, which happens to be robust to a saturated starting `self.s`):
force a known, un-collapsed baseline (`self.ui.s = self.ui._dpi_s * 1.0`,
`self.ui._rail_collapsed = False`) and a synchronous `self.ui._rebuild_ui()`
right after suppressing `_apply_minsize()`'s side effects, so the real
widget tree is verified in sync with a known starting `self.s`/flag
before computing the test's own shrink/grow target — regardless of
whatever state a real WM's own construction-time correction already left
things in.

**Verification.** Reproduced Defect 2 directly and confirmed the fix
closes it, without waiting on another CI round: forced
`self.ui.s = self.ui._dpi_s * AUTO_SCALE_MAX` and
`self.ui._rail_collapsed = True` immediately after `setUp()` (simulating
the exact Windows CI pre-condition), then ran the *old* test body by
hand — reproduced the identical failure shape locally
(`216 != 86`, the same class of mismatch as CI's own `208 != 83`) — then
ran the *new*, fixed test body under the identical forced pre-condition
and confirmed it passes. Did the same for the grow sibling. Removed the
throwaway `AFK_DEBUG_AUTO_RESIZE` instrumentation from both
`afk_clicker.py` and the test once the values were captured. Full local
suite: 437 tests, `OK (skipped=10)`, run twice for stability.

## Deviations from spec / design (Round 4, Defect 2)

No deviation from `docs/spec.md`/`docs/design.md`. Test-only fix; no
further production-code change beyond Defect 1's own fix (the
instrumentation added to `_on_root_resize()` was removed in the same
round, before this diff's final state).

## Known limitations (Round 4)

- `WindowMinimumHeight`'s newly-added `INITIAL_UI_SCALE = "100"` fix was
  found from this specific CI run's actual failures, not from an
  exhaustive re-audit of every `UITestCase` subclass for the same
  self.s-vs-geometry lockstep assumption — round 3's own "not claimed
  exhaustive" caveat still applies; a different real screen/DPI
  combination could still expose the same gap in a class this session's
  CI runs haven't touched.
- Defect 2's fix is scoped to the two rail-collapse-under-Auto tests
  that read/depend on `self.ui.s`/`self.ui._rail_collapsed`'s starting
  value without first verifying it against the actual rendered widget
  tree — the same class of vulnerability (trusting post-construction
  state on a real WM without confirming sync) could in principle affect
  a different `UIScaleAuto` test this session's own CI runs haven't
  exercised on an unusual-enough real screen; not claimed exhaustive.
- All prior rounds' known limitations (macOS/Windows-only verification
  gap for the genuine WM bootstrap path, the out-of-scope
  `pynput.mouse.Controller()` connection leak, round 2's widget-tree-lag
  tradeoff — now the direct root cause of Defect 2 too, not just a
  documented tradeoff) are unchanged and still apply.
- `test_the_settle_timer_resets_on_each_new_event_not_just_the_first`'s
  own pre-existing, CI-load-dependent flake (round 3's own finding)
  recurred once more this round on macOS, still with no evidence tying
  it to this diff's own changes — not fixed here, same reasoning as
  every prior round.

## Round 4 status — all three CI legs green

Pushed the Defect 2 fix (commit `20ce68c`) and re-checked `gh pr checks
89`: `ubuntu-latest`, `macos-latest`, and `windows-latest` **all pass**
(`gh pr checks 89` exit code 0). This closes all three defects
`docs/test-review.md`'s round-3 re-test verdict named (Defect 1 — the
DPI-absolute clamp; Defect 3 — the tautological echo-tracking test;
Defect 2 — the Windows rail-collapse failure, root-caused this round via
real-CI instrumentation rather than left as accept-and-document). Full
local suite (`DISPLAY=:99 <venv>/bin/python -m unittest discover -s
tests -t .`): 437 tests, `OK (skipped=10)`, run repeatedly for stability
across every push this round. `git diff --stat` against `f18164d`
(round 3's own last commit) confirms only `afk_clicker.py`/
`tests/test_ui.py` touched across all of round 4's four commits — no
scope creep beyond the three named defects and their real-CI fallout.

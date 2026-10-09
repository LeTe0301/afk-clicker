# Test & Review: UI scale follows the window size — G#38/GH#67 (Round 4 re-test + full independent review)

## Scope

Re-tests PR #89 at HEAD `20ce68c` (round 4, four commits since round 3's BLOCKED
verdict: `5132a10`, `05bbb83`, `11dd695`, `20ce68c`), which claims to close all
three defects the round-3 re-test (`docs/test-review.md`'s prior content,
superseded by this file) found: Defect 1 (DPI-absolute clamp bounds), Defect 2
(Windows rail-collapse failure), Defect 3 (tautological echo-tracking test).
Since this is the first round whose testing pass came back clean, this file also
carries the **first full independent review pass** of the entire PR #89 diff
(`git diff main...HEAD`, all four rounds), not just round 4's slice — spec
coverage, correctness, security, simplicity, cross-platform reasoning.

## Environment

Fresh venv (`pynput` only extra dependency) built in the session scratchpad
against `Xvfb :99 -screen 0 1280x1024x24 -maxclients 2048` (already running,
matching the documented client-cap workaround). `DISPLAY=:99 <venv>/bin/python`.

**CI state, confirmed directly, not trusted from the developer's claim:**
```
gh pr checks 89
test (macos-latest)   pass  2m48s
test (ubuntu-latest)  pass  1m56s
test (windows-latest) pass  4m0s
gh run view 35344464391 --json headSha → "20ce68c866b1d37ba21e55f8f6bd9ae4381ef150"
```
The passing run's `headSha` matches `git rev-parse HEAD` exactly — this is the
latest commit's run, not a stale one.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Fresh `Store`, no `settings.json` → `ui_scale == "auto"` | Automated (`UIScaleStore.test_a_fresh_store_defaults_to_auto`) | pass | full-suite run below |
| 2 | On-disk `"auto"`/`"90"`/`"100"`/`"115"`/`"130"` round-trips | Automated (`test_known_values_round_trip`) | pass | full-suite run below |
| 3 | Garbage on-disk value → resolves to `"auto"` | Automated (`test_garbage_values_fall_back_to_auto`, `test_a_missing_ui_scale_key_defaults_to_auto`, `test_a_garbage_on_disk_value_resolves_to_auto_end_to_end`) | pass | full-suite run below |
| 4 | Settings pane shows 5 options, "Auto" selected by default | Automated (`UIScaleAuto.test_settings_shows_auto_selected_by_default`) | pass | full-suite run below |
| 5 | `self.s` near `self._dpi_s * 1.0` at default geometry on a ~1920x1080 screen | Automated (`test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`) | pass | full-suite run below; independently re-derived the formula math (see Findings/Defect-1 re-derivation) |
| 6 | `self.ui.s` strictly increases and stays within the (DPI-relative) clamp during a resize sequence | Automated (`test_s_strictly_increases_with_increasing_window_size`) | pass | full-suite run below |
| 7 | `root.minsize()` tracks live `self.s` through a continuous shrink | Automated (`test_minsize_tracks_the_live_scale_during_a_continuous_shrink`) | pass | full-suite run below |
| 8 | Burst of `<Configure>` within `AUTO_SETTLE_MS` → exactly one rebuild, only after the last event + settle | Automated (`test_a_burst_of_configure_events_settles_to_one_rebuild`, `test_the_settle_timer_resets_on_each_new_event_not_just_the_first`) | pass | full-suite run below |
| 9 | Rail collapses/re-expands under Auto's live `self.s`, settled rebuild reflects it | Automated (`test_shrinking_past_the_threshold_collapses_the_rail_under_auto`, `test_growing_back_past_the_threshold_re_expands_the_rail_under_auto`) | pass | full-suite run below; independently reproduced Defect 2's failure shape and confirmed the fix (see Sabotage verification) |
| 10 | Fixed-step (90/100/115/130%) behavior unchanged | Automated (`UIScale` class, 8 tests) | pass | full-suite run below |
| 11 | Continuous `s` between fixed steps still respects `FONT_SIZE_FLOOR` | Automated (`FontSizeFloor.test_continuous_s_values_between_the_fixed_steps_still_floor`) | pass | full-suite run below |
| 12 | Genuine WM-driven post-map bootstrap `<Configure>` (first-launch-on-unusual-screen path) | Not verifiable under Xvfb, spec explicitly scopes to real-WM CI | deferred to CI, confirmed green on all 3 legs above | `gh pr checks 89` |
| — | Defect 1 fix (`_auto_scale_factor`'s DPI-relative clamp bounds, `afk_clicker.py:2707-2741`) | Sabotage: reverted `lo, hi = self._dpi_s * AUTO_SCALE_MIN, self._dpi_s * AUTO_SCALE_MAX` → raw literals | **correctly fails** | 2 tests fail with the exact pre-fix symptom (`0.9 == 0.9 within 2 places`, settle-timer-not-armed) — see below |
| — | Defect 2 fix (rail-collapse tests' known-baseline reset, `tests/test_ui.py:4269-4339`) | Sabotage: replaced the round-4 reset with a simulated diverged Windows-CI precondition (`self.ui.s = dpi_s*AUTO_SCALE_MAX`, `_rail_collapsed = True`) | **correctly fails** | `216 != 86` locally — same class of mismatch as the real Windows CI failure (`208 != 83`) — see below |
| — | Defect 3 fix (independently-computed expected geometry, `tests/test_ui.py:4448-4529`) | Sabotage: reverted `_apply_minsize`'s `self._auto_bootstrap_wh = (new_w, new_h)` tracking line | **correctly fails** | `(688, 646) != (672, 806)` — see below |

## Regression check
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 437 tests in 77.925s
OK (skipped=10)
```
Run twice for stability (77.9s and 77.5s), both clean, matching
`docs/implementation.md`'s own reported count exactly. Also ran the full
`UIScaleStore`/`UIScaleAuto`/`UIScale`/`WindowResize`/`RailCollapse`/
`FontSizeFloor`/`RowValueColumn`/`WindowMinimumHeight` set individually with
`-v` (59 tests) to see every name explicitly — all pass, none skipped.
No type-check/lint step exists in this project (`.github/workflows/ci.yml`'s
only job is `unittest discover`, confirmed unchanged from round 1's finding).

## Sabotage verification (this session, independent of prior rounds' own)

1. **Defect 1** — `afk_clicker.py:2740`, reverted
   `lo, hi = self._dpi_s * AUTO_SCALE_MIN, self._dpi_s * AUTO_SCALE_MAX` back to
   `lo, hi = AUTO_SCALE_MIN, AUTO_SCALE_MAX`. Ran `UIScaleAuto` (13 tests):
   2 failures, both with the exact pre-fix symptom —
   `test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size`
   (`AssertionError: unexpectedly None : a genuine, non-echo resize failed to
   arm the settle timer`) and
   `test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen`
   (`AssertionError: 0.9 == 0.9 within 2 places : Auto must not pin self.s at
   the raw, DPI-absolute clamp floor on a low-DPI display`). Restored;
   `git diff --stat` clean before and after; re-ran, green.

2. **Defect 3** — `afk_clicker.py:2692`, reverted the grow_only branch's
   `self._auto_bootstrap_wh = (new_w, new_h)` line. Ran
   `test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size` alone:
   **fails** — `AssertionError: Tuples differ: (688, 646) != (672, 806)`
   (`_apply_minsize()'s own geometry() call wasn't tracked as the new expected
   self-requested echo`). This is the exact regression Defect 3 said the old
   test couldn't catch — now it does. Restored; `git diff --stat` clean;
   re-ran, green.

3. **Defect 2** — patched
   `test_shrinking_past_the_threshold_collapses_the_rail_under_auto`
   (`tests/test_ui.py:4319-4322`) to replace round 4's known-baseline reset
   (`self.ui.s = self.ui._dpi_s * 1.0; self.ui._rail_collapsed = False;
   self.ui._rebuild_ui()`) with a simulated Windows-CI precondition
   (`self.ui.s = self.ui._dpi_s * app.AUTO_SCALE_MAX; self.ui._rail_collapsed =
   True`) — i.e. ran the *pre-round-4* test logic under the *actual diverged
   starting state* round 4's own root-cause narrative describes (which Xvfb
   can't produce naturally, so this simulates it directly). Result:
   **fails** — `AssertionError: 216 != 86` on `self.ui.side.winfo_width()`,
   the same class of stale-widget-tree mismatch as the real Windows CI failure
   (`208 != 83`). This independently confirms round 4's root-cause story (a
   pre-diverged `self.s`/`_rail_collapsed` at test-body start makes the test's
   own resize target compute to the *same* state, so `s_changed`/
   `collapsed_changed` are both `False` and no settle ever gets requested) and
   confirms the known-baseline reset is what actually fixes it, not something
   coincidental. Restored the original test file from a pre-edit backup;
   `git diff --stat tests/test_ui.py` clean afterward; re-ran `UIScaleAuto`,
   green.

## Independent re-derivation of Defect 1's math (dispatch item 1)

Not trusted from the developer's "multiply-after double-counts" claim —
worked through the algebra directly. At bootstrap, `self.s = self._dpi_s * 1.0`
and `_apply_minsize()`'s non-grow_only branch sets
`default_w = int((SIDEBAR_W+1+CONTENT_W) * self.s)`,
`default_h = int(WINDOW_MIN_H * self.s)`. Feeding those into
`_auto_scale_factor`:

```
fill = sqrt(default_w * default_h / (screen_w * screen_h))
     = dpi_s * sqrt((SIDEBAR_W+1+CONTENT_W) * WINDOW_MIN_H / (screen_w * screen_h))
```

On the reference screen (`screen_w, screen_h = AUTO_REF_SCREEN_W/H`), the
square-root term is `AUTO_REFERENCE_FILL` by its own definition
(`afk_clicker.py:250-262`), so `fill = dpi_s * AUTO_REFERENCE_FILL` and
`factor = fill / AUTO_REFERENCE_FILL = dpi_s` — **exactly**, independent of
what `dpi_s` is. This confirms: (a) the raw, unclamped factor already carries
`self._dpi_s` for any window sized the way this app actually sizes windows
(real width/height are always `self.s`-derived, and `self.s` is always
`dpi_s * something`), so multiplying the clamped result by `dpi_s` a second
time is provably wrong — it would give `dpi_s²` at parity, not `dpi_s`; (b)
the clamp *bounds* must scale by `dpi_s` to keep the *unclamped* case
(computed above) inside the valid range at every `dpi_s`, i.e.
`[dpi_s*AUTO_SCALE_MIN, dpi_s*AUTO_SCALE_MAX]` — which is also, by
construction, identical to the fixed steps' own actual `self.s` range
(`dpi_s * UI_SCALE_FACTORS[value]` for `value` in `{0.9, 1.0, 1.15, 1.3}`).
Scaling the bounds, not the factor, is the mathematically correct fix, and it
is what `afk_clicker.py:2740` does. Confirmed.

## Spec coverage

All acceptance criteria in `docs/spec.md` lines 125-136 map to a passing
automated test (see Test cases table above) except line 136's own named
exception (the genuine WM-mapping bootstrap path), which is explicitly and
correctly deferred to the green macOS/Windows CI legs, matching the spec's
own instruction to say so rather than claim full Linux-only coverage. No
acceptance criterion is unimplemented or untested.

**One real spec/code divergence, not fixed by round 4 despite being flagged
twice:** `docs/spec.md` §2's literal pseudocode (line 47: `return
min(AUTO_SCALE_MAX, max(AUTO_SCALE_MIN, factor))`) and its "Given Auto mode...
`self.ui.s`... stays within `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`" acceptance
criterion (line 130) both describe the **raw, DPI-absolute** clamp — the exact
bug Defect 1 fixed. `docs/spec.md` was not touched by any round-4 commit
(`git diff main...HEAD` only touches `afk_clicker.py`/`tests/test_ui.py`), so
the spec's own text is now inconsistent with the (correct) shipped behavior.
Round 3's own test-review already recommended this be corrected ("docs/spec.md
itself needs a one-paragraph correction since its formula (§2) and its prose
... currently disagree") — see Findings below.

## Findings (most severe first)

### 1. `docs/spec.md` §2 formula and AC line 130 still describe the pre-fix, DPI-absolute clamp — should-fix
- File: `docs/spec.md:47`, `:130`
- Issue: the spec's own pseudocode clamps the raw factor to
  `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]` (the literal `0.9`/`1.3`), and AC line 130
  asserts `self.ui.s` "stays within `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`" — both
  now contradict the corrected, shipped implementation
  (`afk_clicker.py:2740`), which clamps to `self._dpi_s * [AUTO_SCALE_MIN,
  AUTO_SCALE_MAX]`. On this session's own test box (`_dpi_s ≈ 1.04`), the real
  ceiling (`≈1.355`) already exceeds the spec's literal `1.3` bound.
- Failure scenario: not a runtime bug — the code is correct and well-tested.
  The risk is process/documentation: a future contributor reading
  `docs/spec.md` in isolation (the normal handoff artifact for this pipeline)
  would implement or extend Auto mode against the *wrong* formula, silently
  reintroducing Defect 1's exact class of bug. This was named as a fix-along
  requirement by round 3's own test-review and still wasn't done two rounds
  later.
- Not a blocker for this PR: the running code, its tests, and CI are all
  correct; this is a documentation-debt gap in the spec artifact itself, not
  a functional defect. Recommend a one-paragraph correction to
  `docs/spec.md` §2 and AC line 130 (in this PR or as a fast, immediate
  follow-up) so the spec stops contradicting the code it's meant to describe.

### 2. `test_the_settle_timer_resets_on_each_new_event_not_just_the_first` uses brittle fixed-duration `pump()` chains — should-fix (non-blocking)
- File: `tests/test_ui.py:4243-4267` (approx.)
- Issue: three chained fixed-duration `pump(AUTO_SETTLE_MS/1000 * 0.6)` calls
  rather than a condition-based `pump_until` — exactly the flakiness pattern
  round 3 diagnosed and fixed everywhere else it touched in this same class
  (the rail-collapse tests were rewritten specifically to wait on outcomes,
  not fixed sleeps, for this reason). This test recurred as a flake on macOS
  CI multiple times across rounds 3-4 with no fix applied.
- Failure scenario: under CI load (a busier shared runner), the first
  `pump()` window can elapse without leaving enough slack before the timer
  genuinely fires, producing an intermittent, non-deterministic CI failure
  unrelated to any real regression — exactly what was observed and treated as
  a known flake each time.
- Not a blocker: this run's own CI (the actual merge-gate) passed clean on
  all three legs, the flake has no evidence tying it to any of this PR's own
  code changes (it tests pre-existing debounce-reset mechanics untouched
  since round 1), and converting it now would be exactly the "scope creep
  beyond what the evidence supports" round 3 itself declined to do. Worth a
  quick, low-risk follow-up (swap the three fixed `pump()` calls for
  `pump_until`-based waits on the rebuild-call-count condition, the same
  fix already proven on its rail-collapse siblings) to stop the recurring
  noise, but does not block this PR.

## Follow-ups (non-blocking)
- `docs/spec.md` §2 / AC line 130 correction (Finding 1).
- `test_the_settle_timer_resets_on_each_new_event_not_just_the_first`
  hardening (Finding 2).
- The `pynput.mouse.Controller()` Xlib-connection leak (round 3's own
  finding, `afk_clicker.py:2407`-ish) — real, pre-existing, correctly flagged
  as out of scope for this ticket; worth its own backlog item if not already
  filed.
- Round 2's "widget tree lags `self.s` until the next real trigger, on a
  screen far from 1920x1080" tradeoff (the bootstrap-echo suppression's own
  accepted cost) remains a known, documented limitation — no action needed,
  just confirming it's still accurately described in `docs/implementation.md`.

## Correctness / security / simplicity review

- **Correctness**: `_auto_scale_factor`'s DPI-relative clamp is
  mathematically verified correct (see re-derivation above), and its
  `_on_root_resize`/`_apply_minsize` echo-tracking (rounds 2-3) correctly
  handles both the one-time construction echo and any later self-triggered
  `grow_only` echo, gated on event *content* rather than event *order* — a
  deliberate, well-reasoned choice (avoids misclassifying a real first-ever
  resize as the bootstrap echo). No off-by-ones, unhandled branches, or race
  conditions found in the production diff; `on_close()`'s `<Configure>`
  unbind-before-cancel ordering correctly closes the late-re-arm hazard.
- **Security**: no externally-supplied input crosses a new trust boundary —
  `ui_scale`'s on-disk sanitisation reuses the pre-existing `Store.__init__`
  shape (widened by one literal, `"auto"`), and all new arithmetic operates
  on trusted, locally-computed window/screen dimensions. No injection,
  authz/authn, secrets, or unvalidated-external-input concerns apply to this
  diff.
- **Simplicity/scope**: `git diff main...HEAD --stat` confirms only
  `afk_clicker.py`/`tests/test_ui.py` touched across all four rounds — no
  drive-by refactors, no scope creep. The new production surface (`_auto_
  scale_factor`, `_request_auto_settle`/`_on_auto_settle`, the `_on_root_
  resize`/`_apply_ui_scale`/`_apply_minsize` branches) is proportionate to
  what `docs/spec.md`/`docs/design.md` actually asked for; no unnecessary
  abstraction. The test suite's own growth is deliberately controlled (new
  defect coverage repeatedly folded into existing tests rather than adding
  standalone methods, specifically to stay under Xvfb's per-runner
  connection budget on `ubuntu-latest`) — a real, well-documented constraint,
  not padding. No leftover debug code: `AFK_DEBUG_AUTO_RESIZE` instrumentation
  added in `11dd695` was fully removed in `20ce68c` (confirmed: no `print(`
  additions remain anywhere in the diff).
- **Cross-platform reasoning**: round 4's Defect 2 fix is Windows-specific in
  origin but implemented as a platform-agnostic test-only change (forcing a
  known baseline before computing the resize target) — correctly scoped, no
  platform-conditional code introduced in production. All three CI legs
  (Linux/Xvfb, macOS, Windows) are green on the current HEAD.

## Overall verdict

**Approve, with two non-blocking follow-ups** (Findings 1-2 above, neither a
bug nor an uncovered acceptance criterion — a spec-documentation drift and a
pre-existing, unrelated test flake).

All three defects from the round-3 re-test are independently confirmed fixed,
each via a real sabotage-revert-and-watch-it-fail check performed this
session (not trusted from `docs/implementation.md`'s own claims): Defect 1's
fix is mathematically re-derived and correct; Defect 2's new root-cause story
is independently reproduced and its fix confirmed to close it; Defect 3's
rewritten test is confirmed to have real discriminating power now. CI is
independently confirmed green on the exact HEAD commit, all three legs. The
full local suite (437 tests) passes cleanly, twice, with no regressions
found anywhere in the existing suite. Spec-to-code traceability is complete —
every acceptance criterion maps to a passing test, with the one named,
spec-scoped exception (genuine WM bootstrap path) correctly deferred to and
confirmed by real CI. No security, correctness, or scope issues found in the
diff. Hand back to the product-manager agent for the next iteration.

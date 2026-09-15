# Test & Review: Warn when the Minecraft interval minus jitter drops below 650 ms (G#22/GH#33)

## Scope
Every acceptance criterion in `docs/spec.md` (including the "Orchestrator
correction" section's added criteria) plus `docs/design.md`'s copy/colour/
contrast decisions, against the actual `git diff` on branch
`feature/ac-22/minecraft-interval-sweep-warning` (`afk_clicker.py`,
`tests/test_ui.py`; base `b5b12a1`). Nothing in `docs/implementation.md` was
taken at face value — every claim (line numbers, test count, sabotage
results, contrast figures) was independently re-derived this session.

Env: pynput 1.7.7 venv at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`,
Xvfb `:99` already running, confirmed no other `unittest`/Tk process active
before starting. All probes/sabotage this session ran from in-process
scratchpad scripts with in-process monkeypatches only — no on-disk repo file
was ever touched by them; `git status --short` before and after this session
is identical (only the developer's own `afk_clicker.py`/`tests/test_ui.py`
changes plus the three untracked pipeline docs). The one scratch worktree
used to re-derive the pre-diff baseline (`baseline-worktree` at `b5b12a1`)
was removed with `git worktree remove` before this document was written.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | 650 ms/0 jitter (Minecraft): no hint | `tests.test_ui.MinecraftSweepHint.test_no_hint_at_650_with_zero_jitter`, re-run; also re-derived live (not via the test file) | pass | `-v` run: `ok`; live probe: `650/0 (>=650, no hint expected): None` |
| 2 | 649 ms/0 jitter: MUTED, names "Java" | `test_muted_hint_at_649` | pass | `ok`; `app.SWEEP_HINT_MUTED == "Java sweeps may miss"` (contains "Java") |
| 3 | 600/50 → effective 550, MUTED (`>=550` inclusive) | `test_muted_hint_at_550_boundary_is_inclusive`; independently re-run live | pass | `ok`; live: `600/50 eff=550 (MUTED expected): ('Java sweeps may miss', '#9299a3')` |
| 4 | 600/51 → effective 549, BAD | `test_bad_hint_at_549`; independently re-run live | pass | `ok`; live: `600/51 eff=549 (BAD expected): ('Java sweeps likely fail', '#f06262')` |
| 5 | 500/0, BAD | `test_bad_hint_at_500` | pass | `ok` |
| 6 | 100/500 → floored at 50, BAD, never negative/garbage | `test_bad_hint_floored_at_50_never_negative_or_garbage`; independently re-run live | pass | `ok`; live: `100/500 eff=floor(50) (BAD expected, no negative): ('Java sweeps likely fail', '#f06262')` |
| 7 | Global profile: never a hint, any numbers | `test_global_profile_never_shows_hint_at_any_numbers` | pass | `ok` |
| 8 | Custom ("add current game") profile: never a hint | `test_custom_profile_never_shows_hint_at_any_numbers` | pass | `ok` |
| 9 | Blank/invalid Interval text falls back to profile default, no crash/garbage | `test_empty_interval_field_falls_back_to_profile_default`, `test_invalid_interval_text_falls_back_to_profile_default` | pass | `ok`/`ok` |
| 10 | Hint disappears live on the very keystroke that fixes it, no focus-out/Enter/profile switch needed | `test_hint_disappears_live_on_the_very_keystroke_that_fixes_it` | pass | `ok` |
| 11 | Minecraft → Global → Minecraft: hidden on Global, correctly restored on return | `test_hint_hidden_on_global_and_restored_on_return_to_minecraft`; independently re-run live with intermediate prints | pass | `ok`; live: BAD hint hidden immediately after `_select("global")` returns (before any `root.update()`), restored correctly after `_select("minecraft")` + one `root.update()` (see Findings, item n/a — this is a real, expected Tk mapping-needs-an-event-loop-pass characteristic, not a bug: every real Tk callback path already goes through at least one event-loop turn before a human could see it) |
| 12 | `_request_pane_fill("clicking")` fires only on an actual visibility transition, not every keystroke | `test_pane_fill_requested_only_on_visibility_transition` | pass | `ok` |
| 13 | Hint wraps at the same `wraplength` as every other row hint, doesn't overlap the control | `test_hint_wraps_at_the_same_wraplength_and_does_not_overlap_the_control` | pass | `ok` |
| 14 | Existing static hints (jitter, auto-stop) unaffected; `Row`'s additive capability in isolation | `test_existing_static_hints_are_unaffected`, `test_row_mutable_hint_is_additive_and_starts_hidden`, `test_row_without_mutable_hint_has_no_hint_label`, plus the full `RowValueColumn` class | pass | `ok` ×3 + `RowValueColumn` 5/5 `ok` |
| 15 | Theme change, UI-scale change, and opening+closing Settings each complete with no exception, hint state correct after (Orchestrator correction) | `test_survives_theme_change_while_hint_visible`, `test_survives_ui_scale_change_while_hint_visible`, `test_survives_opening_and_closing_settings_while_hint_visible` | pass | `ok` ×3 |
| 16 | First-ever build with Minecraft already the saved selection at startup (Orchestrator correction) | `test_survives_startup_with_minecraft_already_the_saved_selection` (real disk-persisted `restart()`) | pass | `ok` |
| 17 | **(a) Bookkeeping-flag-after-rebuild scrutiny point** — does `_paint_sweep_hint()` actually pack the hint on the *fresh* Interval row after a theme rebuild, independent of `self._sweep_hint_visible`'s stale value? | Live probe: set 600/51 (BAD), record old row/label, `_apply_appearance("light")`, inspect `winfo_ismapped()`/`winfo_manager()` on the new row's label directly (not the bookkeeping flag) | pass | `row replaced: True`; `old label destroyed: True`; `new label winfo_ismapped: 1 winfo_manager: pack`; colour correctly re-themed to light's `#cc3527` (not stale dark `#f06262`) |
| 18 | **(b) `_content_tab == "clicking"` guard scrutiny point** — values/profile changed while Hotkey tab is active, then switch to Clicking via `_set_content_tab` (pack/unpack only, no rebuild, no explicit repaint call): is the hint correct on arrival? | Live probe: stay on default Hotkey tab, `_select("minecraft")`, set 600/51, confirm the hint label is already packed with correct text while `clicking_pane` itself is unmapped, then `_set_content_tab("clicking")` and re-check | pass | Before switching: `hint state ... pack Java sweeps likely fail` while `clicking_pane manager (should be empty/hidden):` (blank); after switching: `hint on arrival: ('Java sweeps likely fail', '#cc3527')` — correct without any extra repaint, because `_paint_sweep_hint()`'s `set_hint`/`clear_hint` call is unconditional and only the *pane-fill* call is tab-guarded (unlike G#21's `_paint_save_notice`, whose whole repaint was tab-guarded) |
| 19 | **(c) Profile-switch timing scrutiny point** — `_persist()`'s early return while `self._loading`; when exactly does the hint clear/restore? | Live probe: BAD on Minecraft, `_select("global")`, check immediately vs. after `root.update()`; `_select("minecraft")` back, same | pass | Hint reads `None` immediately after `_select("global")` returns (already correct, no update needed for *this* direction) and after update; restoring to Minecraft reads `None` immediately after the call returns but correct BAD state after one `root.update()` — a genuine Tk/X11 mapping characteristic (an X server map takes an event-loop turn to reflect in `winfo_ismapped()`), not a functional bug: every real user action already goes through the event loop before it's visible |
| 20 | **(d) `Row` change — existing static hints render identically** | `RowValueColumn` (5 tests) + `test_existing_static_hints_are_unaffected`, plus a direct read of the `Row.__init__` diff | pass | 5/5 `ok`; diff shows the static `hint=` branch is byte-identical to before this change — only a new, separate `elif mutable_hint:` branch was added |
| 21 | **(e) macOS/PR-#78 rule — no new test reaches a real `apply_hotkey()`/`HotkeyWatcher`/`capture_hotkey` without a stub** | `grep` the new `MinecraftSweepHint` class for `HotkeyWatcher`\|`apply_hotkey`\|`capture_hotkey`\|`kb\.`\|`Listener` | pass | Zero hits — the class only uses `UITestCase.setUp()`'s existing construction path (which already goes through one ordinary `apply_hotkey()` call, unchanged by this diff), never a second, separately-driven one |
| 22 | **(f) Copy, colours, thresholds exactly as spec/design** | Live probe reading `app.SWEEP_HINT_MUTED`/`BAD`, `app.THEMES["dark"/"light"]["MUTED"/"BAD"/"CARD"]` directly, plus independent WCAG contrast recomputation from the literal hex values | pass | Copy: `"Java sweeps may miss"` / `"Java sweeps likely fail"` (both name "Java", both verbatim from `docs/design.md`). Colours: dark `MUTED #9299a3`/`BAD #f06262`, light `MUTED #596170`/`BAD #cc3527`, `CARD` `#1c1f23`/`#ffffff` — all match `THEMES` exactly. Contrast, recomputed independently (not copied from `docs/design.md`'s own figures): MUTED dark **5.76:1**, MUTED light **6.23:1**, BAD dark **5.22:1**, BAD light **5.11:1** — matches design.md's own "Orchestrator correction" figures exactly, all clear the 4.5:1 AA-small-text floor |
| 23 | Sabotage-verify the `_rebuilding` gate independently (not trusting the developer's own reported traceback) | Reverted `_note_sweep_hint` to always paint (no gate), replayed the *exact* crash mechanism traced by reading the code first (Settings opened — `interval_row` never rebuilt while Settings is open — then closed via `_select(current, persist=False)`, which rebuilds a *second* time and its leading `_persist()` touches the still-stale, now-destroyed `interval_row`) | pass (fails as expected) | First attempt (a bare `_apply_appearance("light")` with Settings never opened) did **not** crash — expected once traced: that path always goes through the content branch, which rebuilds `interval_row` fresh, so nothing is ever stale there. The open→close path did crash: `TclError('invalid command name ".!frame2.!frame3.!frame.!frame3.!canvas.!frame.!row.!frame.!label2"')` — confirms the gate is load-bearing, and pins down the *exact* mechanism (not just that a crash occurs somewhere) |
| 24 | Confirm the gate holds against the real, unsabotaged code for the same repro | Live probe: real code, BAD hint, open Settings, close via `_select(current, persist=False)` | pass | No crash; hint after the open/close sequence reads `('Java sweeps likely fail', '#f06262')` — correct |
| 25 | **Full suite regression** | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | `Ran 410 tests in 72.567s` / `OK (skipped=10)` — matches the developer's own report exactly |
| 26 | Baseline re-derivation (not trusting the developer's "388 baseline" claim) | Checked out `b5b12a1` (pre-diff) into a scratch `git worktree`, ran the same full suite there, then removed the worktree | pass | `Ran 388 tests in 68.639s` / `OK (skipped=10)` — 410 = 388 + 22 new tests this cycle, independently confirmed, not assumed |
| 27 | No file outside the declared scope touched | `git status --short`, `git diff --stat` | pass | Exactly `afk_clicker.py` (+125/-4) and `tests/test_ui.py` (+237/-1, purely additive — one new class inserted, zero existing lines changed) modified; the three untracked `docs/*.md` pipeline artifacts are this cycle's own spec/design/implementation docs |

## Regression check
Full suite: 410/410, `OK (skipped=10)`, independently re-run (not taken on
the developer's word), and the pre-diff baseline independently re-derived
against `b5b12a1` in a throwaway worktree (388/388, `OK (skipped=10)`,
removed afterward) rather than trusted at face value. 410 = 388 + 22,
matching `docs/implementation.md`'s own accounting exactly. The only console
noise (`ResourceWarning`s from `tests/test_updater.py`'s unclosed temp
files, and the harmless `invalid command name "..._drain_ui" (after
script)` line during teardown) is pre-existing, confirmed present at the
same baseline commit too — not a regression introduced by this diff.

## Spec coverage
Every acceptance criterion in `docs/spec.md`'s "Acceptance criteria" list,
plus both criteria the "Orchestrator correction" section adds (survives
theme/scale/Settings-open-close without exception; correct on a first-ever
build with Minecraft as the saved selection), is covered by an automated
test, and every one of those tests was re-run and passed this session (test
cases 1-16 above). The six scrutiny points the dispatch specifically asked
to look hardest at — (a) bookkeeping flag after rebuild, (b) the
`_content_tab == "clicking"` guard, (c) profile-switch timing under
`_loading`, (d) the `Row` change's non-effect on existing static hints, (e)
the PR #78 macOS hotkey-stub rule, (f) copy/colour/threshold exactness — were
each independently re-derived live against the real, unmodified app (test
cases 17-22), not inferred from reading the diff alone. No acceptance
criterion was found unimplemented or untested.

## Findings (most severe first)

No must-fix. No should-fix. One nit:

### 1. `docs/implementation.md`'s line-number citations for `_persist()`/`_note_sweep_hint()` — nit
- File: `docs/implementation.md` ("Changes by file" section, e.g. "`_persist()` (~line 3510-3524)")
- Issue: the actual hook line in `_persist()` is `afk_clicker.py:3517` (`self._note_sweep_hint(profile, values)`), and `_note_sweep_hint`/`_paint_sweep_hint` themselves span roughly `3513-3567` — close to, but not exactly, the cited ranges (all prefixed "~" by the developer, i.e. already flagged as approximate).
- Failure scenario: none — this is documentation precision only, already hedged with "~", and does not affect behavior, tests, or the next reader's ability to find the code (the method names are unambiguous and grep-able). Not worth a revision cycle on its own.

## Follow-ups (non-blocking)
- None beyond the nit above.

## Overall verdict
**Approve.**

Testing pass: every acceptance criterion in `docs/spec.md` (including the
"Orchestrator correction" section's two added criteria) has a passing,
independently-re-run automated test, and the six scrutiny points this
dispatch called out by name were each verified live against the real,
un-sabotaged app this session — not inferred from the diff or taken from
`docs/implementation.md`'s own account. Most notably: (a) the Interval row's
hint is proven, by directly inspecting `winfo_ismapped()`/`winfo_manager()`
on the *new* widget after a real theme rebuild, to be repainted correctly
regardless of the `_sweep_hint_visible` bookkeeping flag's stale value —
because `_paint_sweep_hint()`'s `set_hint`/`clear_hint` call is unconditional
and only the *pane-fill* trigger is gated by the visibility-transition flag;
(b) the `_content_tab == "clicking"` guard only gates the pane-fill call, not
the widget mutation itself, so switching from Hotkey to Clicking never needs
(and never gets) an explicit repaint, unlike G#21's `_paint_save_notice`
which needed one; (c) `_persist()`'s `self._loading` gate correctly
clears/restores the hint across a Minecraft→Global→Minecraft switch, modulo
an ordinary Tk/X11 event-loop-turn characteristic that also applies to every
other live-reading field in this app; (d) the `Row` change is confirmed
byte-identical for every existing static `hint=` call site by reading the
diff and re-running `RowValueColumn`; (e) the new test class never reaches a
real `apply_hotkey()`/`HotkeyWatcher` a second time, confirmed by grep; (f)
copy, colours, and both thresholds (550/650, inclusive/exclusive exactly as
specified) match, and the WCAG contrast figures were independently
recomputed from the literal `THEMES` hex values rather than copied from
`docs/design.md`, landing on the exact same numbers design's own
"Orchestrator correction" already corrected to. The `_rebuilding` gate was
independently sabotage-verified against the *actual* crash mechanism (traced
by reading `_build_ui()`/`_select()`/`_rebuild_ui()` first, not by copying
the developer's repro) — a naive single-rebuild sabotage attempt correctly
did *not* crash, and the real open-Settings-then-close-it double-rebuild
did, with the identical `TclError` shape `docs/implementation.md` reports.

Full suite: 410/410, `OK (skipped=10)`, matching the developer's report
exactly, and the 388-test pre-diff baseline was independently re-derived
(not trusted) via a throwaway `git worktree` at `b5b12a1`, removed after use.
`git status --short` is unchanged by this session's own probes: only the
developer's two files plus the three untracked pipeline docs are present.

Review pass: no must-fix, no should-fix, one documentation nit
(approximate line-number citations in `docs/implementation.md`, already
self-hedged with "~" and not affecting behavior). No security issue (no new
external input, no new parsing, no secrets), no threading violation, no
naming/shadowing collision, no scope creep (diff is exactly the two files
`docs/spec.md`'s "Affected areas" names, and the test file's diff is purely
additive), no unnecessary abstraction (the `_note_*`/`_paint_*` split
directly reuses G#21/PR #78's own established precedent rather than
inventing a new mechanism), nothing on `docs/ROADMAP.md` touched or implied
by this diff, and no settings-schema change (confirmed: `min_sweep_ms` lives
only on the in-memory `PROFILES`/`make_profile()` shapes, never persisted).

This build cycle is done — hands back to product-manager for the next
iteration.

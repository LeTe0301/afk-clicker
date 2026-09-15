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

---

## Round 2 (PR #80 round-2 diff, `git diff df1d136 HEAD`)

### Scope
Round 2's own diff only: `afk_clicker.py` (Row's `mutable_hint`/`set_hint`/
`restore_hint` rework, the jitter-row rewiring, the new `self._settings_open`
guard in `_paint_sweep_hint`), `tests/test_ui.py` (the `MinecraftSweepHint`
rewrite for the jitter row + the new `WindowMinimumHeight` floor test),
`README.md` (one new German sentence). Checked against `docs/design.md`
Revision 2 + its "Orchestrator correction" (binding: placement in the jitter
row's hint slot, `INK` bold for 550-649 ms, `BAD` bold for <550 ms, a floor
test) and `docs/implementation.md`'s "Round 2" section, which was treated as
a claim to re-derive, not a fact to trust.

Env: same venv/Xvfb `:99` as round 1. All probes/sabotage ran from
in-process scratchpad scripts (never touching a repo file); `git status
--short` was clean before and after every probe in this round.

### Testing pass

**Full suite, independently re-run:**
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 414 tests in 73.277s
OK (skipped=10)
```
Matches `docs/implementation.md`'s claimed "414 OK (skipped=10)" exactly.

**This round's own test classes:**
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.MinecraftSweepHint tests.test_ui.WindowMinimumHeight -v
Ran 31 tests in 3.364s
OK
```
25 `MinecraftSweepHint` + 6 `WindowMinimumHeight`, all green — matches the
developer's per-class counts.

| # | Scrutiny point (from dispatch) | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | (a) Floor test asserts the pane fits at `WINDOW_MIN_H` with Minecraft+Eating visible and the worst-case band shown, at 90%/130% | Read `tests/test_ui.py:1170-1206`; ran it; then **independently sabotaged** `app.SWEEP_HINT_BAD` to 12x its real length and re-ran, both via the test's own `_apply_ui_scale()`-mid-test technique and via a corrected `self.ui.store.data["ui_scale"]=...; self.restart()` technique that actually reaches the true per-scale floor | **fails to guard** — see Findings #1 | Row half fails as the developer reports (`178 not <= 48`, `232 not <= 62`); **pane half never fails, at either scale, via either technique** (`PANE_OK=True` throughout) — the "natural" measurement is fed each card-canvas's post-layout *allocated* height, not its own `winfo_reqheight()`; when content overflows, Tk's own `pack()` silently shrinks the Eating card's canvas (confirmed live: baseline 125px allocated == 125px required; under sabotage, 56px allocated vs. 125px required, a stable 69px of real content quietly clipped) rather than ever letting `natural > pane.winfo_height()` |
| 2 | (a) Could INK ("may miss") ever wrap worse than BAD ("likely fail"), making BAD not the true worst case? | Measured both strings' pixel width with `tkinter.font.Font(family="Segoe UI", size=int(8*s), weight="bold").measure(...)` against the row's real `wraplength` at 90%/130% | **yes, already tighter in this environment** | At scale 90: `wraplen=131`, `INK_width=123` (8px to spare), `BAD_width=120` (11px to spare) — INK is the *tighter* fit here despite being 3 characters shorter, because of where its words break. At scale 130 both measure identically (171px). The floor test never sets an INK-band scenario at all (only `click_ms=500` → BAD) |
| 3 | (b) `_settings_open` guard: root cause and completeness | Live probe: BAD band active, opened Settings (`jitter_row` torn down), monkeypatched `_paint_sweep_hint` back to the unguarded round-1-shape body, called `on_close()` | **root cause confirmed exactly as claimed** | Without the guard: `TclError: invalid command name ".!frame2.!frame3.!frame.!frame3.!canvas.!frame.!row2.!frame.!label2"` on `on_close()`'s own unconditional `_persist()` call with Settings open. With the real (guarded) code: no exception |
| 4 | (b) Band changes while Settings is open, then Settings closes — is the hint correct after? | Live probe: Minecraft/BAD → open Settings → `_select("global")` (sidebar still live) while Settings open → close Settings (`_rebuild_ui()`) → check jitter hint; and the reverse (Global → open Settings → `_select("minecraft")` with default 650/0) | pass | Global case: hint reads the static text (`'spreads the rhythm so it is not exact'`, `MUTED`, regular) immediately after close — no stale BAD survives. Reverse case: `_sweep_hint_pending` is `None` while Settings is still open (correctly recorded, not painted), and the rebuilt jitter row shows the static text after close — no crash, no stale state |
| 5 | (c) `restore_hint()`/`set_hint()` read the *current* theme's colours | Live probe: Minecraft, cycled static → INK (649) → BAD (500) in dark, then `_apply_appearance("light")` and re-cycled BAD → INK (649) → static (650) | pass | Dark: static `#9299a3`==`MUTED`, INK `#e4e7ea`==`INK`, BAD `#f06262`==`BAD`. Light: BAD `#cc3527`==`BAD`, INK `#161a22`==`INK`, static `#596170`==`MUTED`. All six read live, all match `THEMES` exactly |
| 6 | (d) Other rows' static hints unchanged; jitter's own static appearance unchanged when no band active | `tests.test_ui.RowValueColumn` (all 5) | pass | `Ran 5 tests ... OK`, including `test_random_jitter_hint_wraps_instead_of_overlapping_the_control` (same text/colour/wrap geometry as before this round) |
| 7 | (e) No remaining `clear_hint()` caller | `grep -n clear_hint afk_clicker.py tests/test_ui.py` | pass | Two hits, both inside docstrings/comments explaining *why* it was removed (`afk_clicker.py:2230`, `:3610`) — zero call sites |
| 8 | (f) README sentence accuracy | Read `README.md:75`; live-probed the actual font weight at each band (`650`→regular, `649`→bold, `500`→bold) | **inaccurate** — see Findings #2 | The sentence reads (translated) "...gives way to a warning below 650 ms, and becomes **bold from 550 ms**..." — implying the 550-649 ms band is plain and only <550 ms is bold. Live probe: `649 -> font={Segoe UI} 8 bold` — the 550-649 ms band is already bold; only the no-band static text (regular) differs from *both* bands |
| 9 | (g) No test reaches a real `apply_hotkey()`/`capture_hotkey`/`HotkeyWatcher` without a stub | `sed -n '1803,2076p' tests/test_ui.py \| grep -n "apply_hotkey\|capture_hotkey\|HotkeyWatcher"` (the `MinecraftSweepHint` class's own line range) | pass | Zero hits — the class only goes through `UITestCase.setUp()`'s existing, already-stubbed construction path |
| 10 | Independent WCAG contrast recomputation (Orchestrator correction to Revision 2's INK figures) | Recomputed from literal `THEMES` hex values (`#e4e7ea`/`#1c1f23`, `#161a22`/`#ffffff`, plus the unchanged BAD/MUTED pairs) with the WCAG relative-luminance formula | pass | INK dark **13.32:1**, INK light **17.43:1**, BAD dark **5.22:1**, BAD light **5.11:1**, MUTED dark **5.76:1**, MUTED light **6.23:1** — matches the design doc's corrected table exactly; all clear the relevant AA floor |

The suite passes and every specific scrutiny point was checked live — no test
*fails* this round, so this is not a blocked testing pass. Two of the checks
above (#1/#2 and #8) surfaced real defects in what the passing tests actually
prove and in the README's accuracy; these are review-pass findings, carried
into "Findings" below.

### Regression check
414/414 (`OK, skipped=10`), independently re-run; 414 = round 1's 410 + 4 new
tests this round (`test_survives_theme_change_while_ink_band_visible`,
`test_interval_row_has_no_hint_capability_anymore`,
`test_jitter_hint_defaults_to_the_static_text_with_no_band`,
`test_sweep_hint_height_floor_minecraft_with_eating`), matching
`docs/implementation.md`'s own accounting. No new `ResourceWarning`/teardown
noise beyond round 1's already-investigated baseline.

### Spec coverage
Every `docs/design.md` Revision 2 / Orchestrator-correction decision has a
corresponding test that runs and passes (placement in the jitter row,
INK-bold/BAD-bold colours, copy unchanged, `_settings_open` no-crash
guarantee). Decision D's own acceptance line — **"the natural height must
never exceed available height at the floor on any platform or scale step. A
violation blocks CI"** — is the one criterion whose test does not actually
enforce what it claims; see Finding #1. This is exactly the kind of
"criterion nobody tested" gap this review pass exists to catch, even though
the test itself is present, named correctly, and green.

### Findings (most severe first)

#### 1. The new floor test's pane-level assertion cannot detect the very Windows/macOS clipping risk it was added to guard — MUST-FIX
- File: `tests/test_ui.py:1191-1197` (the `assertLessEqual(natural, pane.winfo_height())` half of `test_sweep_hint_height_floor_minecraft_with_eating`, `tests/test_ui.py:1170`)
- What's wrong: `natural` is computed from each direct child's `winfo_y()`/`winfo_height()` — its *post-layout allocated* size — not its `winfo_reqheight()`. When the pane genuinely runs short of room, Tk's own `pack()` silently shrinks whichever card is packed last (here, the Eating card's canvas) below its real content need, rather than ever pushing `natural` past `pane.winfo_height()`. Confirmed live: baseline eating-canvas allocated height (125px) equals its required height (125px, no shrink); under a sabotaged, 12x-length `SWEEP_HINT_BAD`, the eating canvas is squeezed to 56px allocated while still reporting 125px required — 69px of real Eating-card content silently clipped — and yet `natural` (406) still comes in one pixel under `pane.winfo_height()` (407), so the assertion passes regardless. This holds under the test's own `_apply_ui_scale()`-mid-test technique *and* under a corrected fresh-`restart()`-at-the-persisted-scale technique that actually reaches the genuine 90%/130% floor (`root_h` 581/840, matching `int(WINDOW_MIN_H * s)` exactly) — so it isn't a byproduct of the test's own scale-application method, it's structural.
- Separately, and compounding it: the test calls `self.ui._apply_ui_scale(scale)` directly on the window `setUp()` already built at ~100% scale. `_apply_minsize(grow_only=True)` (`afk_clicker.py:2553-2586`) never shrinks a window — by design, per its own docstring — so the 90% subTest never actually reaches the true 90%-scale floor; the window stays at its ~100%-scale height (measured: `root_h=646` before and after `_apply_ui_scale("90")` in this environment, vs. the true 90%-scale floor of 581), handing the pane ~65px of slack that would not exist on a real fresh 90%-scale launch. This exact anti-pattern, and its fix, is already documented in this same file: `tests/test_ui.py:1734-1751` (`test_ui_scale_row_never_overflows_its_card_at_any_scale_step`'s own comment — "A fresh instance per step, NOT `_apply_ui_scale()` on one window... That passes for the wrong reason, and exactly where the fit is tightest"). The new floor test does not follow this established precedent.
- Third, independently: the design's own premise that BAD is the worst-case band is unverified and, measured in this environment, false at the 90% step. `tkinter.font.Font(family="Segoe UI", size=int(8*0.938), weight="bold").measure(...)` gives INK ("Java sweeps may miss") 123px against a 131px wraplength (8px to spare) vs. BAD ("Java sweeps likely fail") at 120px (11px to spare) — INK is the *tighter* fit despite fewer characters, because of where its words break. The floor test only ever forces `click_ms=500` (BAD); it never exercises the INK band at all.
- Concrete failure scenario: ship a future copy tweak, translation, or a font-metric difference on real Windows Segoe UI that makes either band's text taller/wider than assumed here. The row-height comparison half of this same test (`warning_h <= static_h`) would (and did, under sabotage) catch it — that part is real and works. But the specific acceptance criterion this round added expressly to close PR #80 round 1's lens-7 BLOCKER — "assert the Clicking pane's natural height ≤ available at WINDOW_MIN_H... with the worst-case warning shown" — is not actually being checked by anything in this diff. A regression that grows the Eating card's own clipped content, or that grows the INK band specifically, would land on Windows CI exactly as before this round's fix, and this test would stay green throughout.
- Fix shape (developer's call): either (a) measure `natural` from `winfo_reqheight()`-based, unclipped sizes (or drop `pack_propagate(False)` assumptions and directly sum children's requested heights) so a genuine overflow is visible even when Tk's packer absorbs it elsewhere, (b) build the floor-test scenario via `self.ui.store.data["ui_scale"] = scale; self.ui.store.save(); ui = self.restart()` (the established fix for the same anti-pattern this file already documents), and (c) assert the row-height invariant (`warning_h <= static_h`) for the INK band as well as BAD, since BAD is not established to be the worst case.

#### 2. README's new sentence misstates when the warning becomes bold — SHOULD-FIX
- File: `README.md:75`
- What's wrong: "...weicht dieser Text einer Warnung, sobald Intervall minus Jitter unter 650 ms sinkt, und wird ab 550 ms fett hervorgehoben..." reads as "the text gives way to a (plain) warning below 650 ms, and only becomes bold from 550 ms down." Live probe shows the 550-649 ms band ("Java sweeps may miss") is *already* `{Segoe UI} 8 bold` — the same weight as the <550 ms band. Only the no-band static text ("spreads the rhythm so it is not exact") is regular weight; both warning bands are bold.
- Failure scenario: a user reading the README concludes the 550-649 ms warning is plain text and only takes the bold escalation seriously below 550 ms, when in fact both bands already render identically bold and are distinguished only by colour (`INK` vs `BAD`). Not a functional bug, and the "Java"-naming and 650/550 threshold numbers themselves are correct — only the bold-weight claim is wrong.
- Fix shape: reword to something like "...wird ab 650 ms fett hervorgehoben und wechselt ab 550 ms zusätzlich auf eine auffälligere Farbe..." (becomes bold from 650 ms down, and additionally switches to a more urgent colour from 550 ms), or simply drop the "ab 550 ms" clause's implication that boldness starts there.

### Follow-ups (non-blocking)
- None beyond Finding #2 above (already listed as should-fix, not a separate follow-up).

### Overall verdict
**Changes requested.**

Testing pass is clean: the full suite (414/414, `OK skipped=10`) and every
named test class pass, matching `docs/implementation.md`'s claims exactly,
and every specific scrutiny point in the dispatch ((b) through (g)) checked
out live with no surprises. That is why this proceeded to a review pass
rather than stopping at "blocked."

The review pass found one must-fix: the new
`test_sweep_hint_height_floor_minecraft_with_eating` (`tests/test_ui.py:1170`)
does not actually verify the floor invariant Decision D asked for — its
pane-level assertion cannot fail even under a 12x-inflated sabotage of the
warning text, because Tk's own `pack()` silently absorbs overflow by
shrinking the Eating card's canvas below its own required height rather than
ever exceeding the pane's fixed height, and separately the test's `_apply_ui_
scale()`-mid-test technique (not `restart()`-at-a-persisted-scale) means the
90% step never reaches the genuine 90%-scale floor in the first place. The
design's assumption that BAD is the taller/worse band is also unverified and
measured false, in this environment, at the 90% scale step. This is
precisely the class of "criterion present, named, green — but not actually
tested" gap this pipeline's review pass exists to catch, on the one
acceptance criterion (Decision D) that exists specifically to close PR #80
round 1's own height-floor BLOCKER — so it must go back to the developer
rather than be waved through as a nit. One should-fix (the README's bold-
threshold misstatement) rides along, cheap to fix in the same pass.

Routes back to the developer with: (1) make the floor test's pane assertion
actually capable of failing under a genuine overflow (measure unclipped
required heights, and/or use `restart()` at the persisted scale the way
`tests/test_ui.py:1734-1751` already established), (2) add the same
row-height/floor coverage for the INK band, not only BAD, since BAD is not
shown to be the worst case, and (3) fix `README.md:75`'s bold-threshold
claim.

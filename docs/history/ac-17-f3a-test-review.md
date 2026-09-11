# Test & Review: Tab navigation + Settings tab (story #17, Feature 3a) — Round 2

**Round 1 summary (for context, not re-litigated below):** Round 1 tested the
`_build_ui()`/`_rebuild_ui()` rebuild mechanism, the Settings sidebar
destination, the Appearance `Segmented`, and `settings.json["appearance"]`
persistence against `docs/spec.md`; all 22 new tests plus the full existing
suite passed, but a manual probe of rapid/overlapping Appearance changes
found an uncaught `TclError` (Defect 1: two `after_idle(self._rebuild_ui)`
jobs queued before either ran let `card()`'s `_redraw()` reentrantly service
the second one mid-rebuild via `update_idletasks()`), plus a Round-8 coverage
gap (reverting the `_set_status` fresh-lookup indirection at all 6 call
sites left the suite green) and a non-blocking UX concern (the sidebar's
three rows read as one stack of buttons). Because Defect 1 blocked, the
ten-round review pass was never run against the diff — this is the first
time it happens, below.

## Scope
Round 2 testing pass: verify the developer's Round-2 fixes (coalescing via
`_rebuild_after_id`, `card()`'s `shell.winfo_exists()` guards, `on_close()`
cancelling a pending idle rebuild, the `CapturesCallbackExceptions` mixin,
the sidebar divider) actually close Round 1's three findings, then — since
this is the first clean testing pass on this diff — the full ten-round
`docs/REVIEW-PROTOCOL.md` walk over the entire 3a diff (`git diff main` in
`/home/dev/projects/.worktrees/afk-clicker/ac-17`, branch at `main` a8ef647,
uncommitted), focused per dispatch on Round 3 (threading/Tk-safety) and
Round 8 (tests).

**Worktree left exactly as found.** Every in-memory edit made for the
Round-8 revert checks below was restored from a `diff`-verified
byte-identical backup before moving to the next check; final `git diff
--stat main` matches the pre-review baseline exactly (`afk_clicker.py | 353
+++...`, `tests/test_ui.py | 603 +++...`, confirmed via `git status --short`
and `git diff --stat main` run both before and after this session).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Full existing suite (211 tests, incl. Round 1's 22 + Round 2's 5 new) | automated | pass | `unittest discover -s tests -t .` → `Ran 211 tests ... OK (skipped=5)`, run 3× this session (baseline, post-guard-revert-restore, final) |
| 2 | Reviewer's own Round-1 probes re-run clean, incl. `probe3c` (the one raw-Tcl-print `on_close`-races-idle-rebuild case, now fixed) | manual probe, re-run | pass | `probe1_running_rapid.py`, `probe2_queued_callbacks.py`, `probe3_misc.py` — all clean, `PROBE3c PASS` now (previously a known, documented raw Tcl print) |
| 3 | 5 rapid `_apply_appearance()` calls before any drain no longer raise | automated + manual | pass | `OverlappingAppearanceChanges` (4 tests); `probe1_running_rapid.py` |
| 4 | Appearance change injected **during** an in-progress `_rebuild_ui()` (a trace firing mid-rebuild) | manual probe, monkeypatched `_build_content`/`card()` reentrant injection | **FAIL — crashes with the exact Defect-1 `TclError` shape, coalescing/guards notwithstanding** | `probe4_break_coalescing.py::probe_a` (soft form, passes) vs. `probe5_reentrant_card.py` (hard form, fails) — see Findings #1 |
| 5 | `_show_settings()`/`_select()` inline while an idle rebuild is pending, then a second appearance change | manual probe | pass | `probe4_break_coalescing.py::probe_b` |
| 6 | 50-step seeded fuzz (appearance/select/settings/start/stop/pump interleavings): no callback exception, ≤1 live worker, bounded `after info`, pill matches `running` | automated probe, fixed seed | pass | `probe4_break_coalescing.py::probe_c` (seed=12345) |
| 7 | `CapturesCallbackExceptions` actually catches Defect 1, not by luck | automated, revert-run-restore | pass — confirmed via `tearDown`'s `_assert_no_callback_exceptions()` failing with the exact recorded `_tkinter.TclError: bad window path name` traceback, not a different assertion | see "Round-8 revert checks" below |
| 8 | No escape hatch exists for a test that legitimately expects a callback exception; no existing test needs one | code read | pass (observation, not a defect) | `tests/test_ui.py:36-61`; grepped every `_callback_exceptions`/`report_callback_exception` use, none resets/expects one |
| 9 | Round 8: revert `winfo_exists()` guards alone, keep coalescing | automated, revert-run-restore | **full suite stays green — nothing catches the revert** | see "Round-8 revert checks" below; Findings #2 |
| 10 | Round 8: revert coalescing alone, keep guards | automated, revert-run-restore | 3 `OverlappingAppearanceChanges` tests correctly fail, via the recorded callback exception | see "Round-8 revert checks" below |
| 11 | Round 8: revert `on_close()`'s idle-rebuild cancel alone | automated, revert-run-restore | exactly 1 test fails (`test_on_close_between_an_appearance_change_and_its_idle_rebuild`), clean `AssertionError`, no crash | see "Round-8 revert checks" below |
| 12 | Sidebar order: Add current game, Check for updates, divider, Settings, version | manual, screenshot | pass | `f3-settings-dark.png` (viewed this session) |

## Round-8 revert checks (detail)

All three done via in-memory `Edit`, `diff`-verified byte-identical restore
before the next check (`afk_clicker.py.r2backup` in the scratchpad); final
state confirmed identical to the pre-review file.

**(a) `card()`'s `_redraw()` `winfo_exists()` guards removed alone**
(`afk_clicker.py:1291-1304`), coalescing left intact:
`unittest discover` → **211 tests, OK, skipped=5 — no failure.** `probe1`
(the original 5-rapid-clicks Defect-1 repro) also still passes clean. This
guard has **zero test coverage** in the committed suite — see Findings #2.

**(b) Coalescing removed alone** (`_apply_appearance()`'s
`if self._rebuild_after_id is None:` at `afk_clicker.py:1792` made
unconditional; `_rebuild_ui()`'s cancel-at-top block at `afk_clicker.py:
1629-1634` deleted), guards left intact: **3 tests fail** —
`test_five_rapid_appearance_changes_coalesce_into_exactly_one_rebuild`,
`test_two_rapid_appearance_changes_before_the_idle_rebuild_drains`,
`test_two_real_segmented_clicks_with_no_pump_between_them` — all failing via
`tearDown → _assert_no_callback_exceptions()` recording the actual
`_tkinter.TclError: bad window path name ...` raised from inside
`_build_content()`'s `Row(hk, ...)`/`Row(ap, ...)` construction against an
already-destroyed parent. Confirms the mixin catches the real crash, not a
side effect. `test_on_close_between_an_appearance_change_and_its_idle_rebuild`
is unaffected (correctly — it targets `on_close()`'s cancel, not
coalescing).

**(c) `on_close()`'s `_rebuild_after_id` cancel removed alone**
(`afk_clicker.py:2279-2284`): **exactly 1 test fails** —
`test_on_close_between_an_appearance_change_and_its_idle_rebuild` —
`AssertionError: 'after#1077' unexpectedly found in ('after#1077',) :
on_close() left the pending idle rebuild scheduled`. Clean assertion
failure, no crash, no other test affected.

All three reverts were restored and the tree confirmed byte-identical to
the session-start state before moving on; `git diff --stat main` after
restore matches the developer's reported baseline exactly.

## Regression check
`DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .` →
**211 tests, OK, skipped=5** — matches the developer's reported figure, run
3 times this session (clean each time, including after each revert was
restored). No flakiness observed.

---
The sections below are the ten-round review pass — the testing pass above
found no *blocking* defect (Findings #1 below is a demonstrated-but-not-
currently-reachable gap, not a regression the testing pass itself failed on
— see Findings), so per protocol the review proceeds.

## Spec coverage
Every `docs/spec.md` acceptance criterion is implemented and covered by an
automated test (unchanged from Round 1's mapping — Round 2 added no new
acceptance criteria, only fixed the three Round-1 findings). Verified this
session: full suite green, no criterion's covering test removed or weakened
by the Round-2 diff.

## Findings (most severe first)

### 1. The coalescing invariant ("at most one rebuild is ever in flight or pending," `afk_clicker.py:1614-1627`) is false under reentrancy — a rebuild scheduled *during* an in-progress rebuild reproduces Defect 1's exact crash — should-fix, not currently reachable
- File: `afk_clicker.py:1792-1793` (`_apply_appearance`'s schedule guard) and `afk_clicker.py:1629-1634` (`_rebuild_ui`'s absorb-at-top)
- Issue: `_rebuild_ui()` clears `self._rebuild_after_id` to `None` at its own
  top, *before* it finishes running. If anything calls `_apply_appearance()`
  again while that same `_rebuild_ui()` call is still on the stack (still
  mid-`_build_content()`/`_build_settings()`), the guard at
  `afk_clicker.py:1792` sees `None` and schedules a **fresh**
  `after_idle(self._rebuild_ui)` job. A later `card()` call in the *same*,
  still-running outer rebuild then calls `inner.update_idletasks()`
  (`afk_clicker.py:1297`), which reentrantly services that fresh idle job —
  running a second `_rebuild_ui()` that destroys every widget the first,
  still-in-progress rebuild is holding local references to. The first
  rebuild's next widget-construction call then raises `_tkinter.TclError:
  bad window path name` against an already-destroyed parent — reproduced
  with `probe5_reentrant_card.py` (full traceback captured, crash site
  `afk_clicker.py:1671`, `Row(hk, "Toggle", s)` against a destroyed `hk`
  card). Confirmed with the guards from Round 2's fix (b) present and
  active — the guards protect `card()`'s own `_redraw()` body, not the
  *caller* (`_build_content()`) that keeps referencing already-destroyed
  local widgets after the reentrant rebuild tears the tree down out from
  under it, so removing/keeping the guards changes only *where* the
  `TclError` is raised (inside `_redraw()`'s own `shell.winfo_width()` vs. a
  later `Row(...)` constructor), not *whether* it's raised.
- Failure scenario: any future code path that calls `_apply_appearance()`
  (or otherwise schedules another `after_idle(self._rebuild_ui)`-shaped job)
  synchronously from within `_build_ui()`/`_build_content()`/
  `_build_settings()`'s own call stack — e.g. a future "Reset to defaults"
  control, a keyboard shortcut that sets Appearance programmatically, or any
  other synchronous internal caller — silently reintroduces Defect 1's
  exact crash, and the current suite would not catch it (no test drives
  this shape).
- **Why not a blocker today:** the *only* current caller of
  `_apply_appearance()` is the `appearance_var` trace, fired by a real
  `<Button-1>` on the Appearance `Segmented`. Real X11 button events are
  window events, not idle events — Tcl's `update idletasks` (what
  `card()`'s `_redraw()` calls) explicitly does not service window/mouse
  events, only already-queued idle callbacks. So no live mouse click can
  land inside this window today; only a test/monkeypatch driving
  `_apply_appearance()` directly, or a future feature adding a second
  synchronous internal caller, can reach it. Given that, this is a
  should-fix (the documented invariant is provably narrower than its own
  docstring/`docs/implementation.md` "Round 2" section claims, and the fix
  is one small addition away — e.g. a `self._rebuilding` reentrancy flag
  checked by `_apply_appearance()`, or having `_rebuild_ui()` set
  `_rebuild_after_id` back to a sentinel while it runs), not a blocker.

### 2. `card()`'s `winfo_exists()` guards (`afk_clicker.py:1291-1304`) have zero test coverage — should-fix
- File: `afk_clicker.py:1291-1304`; `docs/implementation.md`'s "Round 2" §
  "Fix, two layers, both requested" describes these as "(b) Robust
  `<Configure>` handler ... defense in depth on top of (a)."
- Issue: removing both guard lines (restoring `_redraw()` to its pre-Round-2
  body) and running the full 211-test suite produces **no failure** — `Ran
  211 tests ... OK (skipped=5)`, confirmed this session. `docs/
  REVIEW-PROTOCOL.md` Round 8's own question — "Does the test actually fail
  if you revert the fix? Say whether you checked" — the answer, checked,
  is: it does not. Coalescing alone (fix (a)) already prevents the specific
  repro shapes the committed tests drive (`OverlappingAppearanceChanges`'s 4
  tests all queue their extra Appearance change *before* `root.update()`
  ever runs, so the guard's own reentrancy branch is never exercised by
  the suite as it stands).
- Failure scenario: a future change that weakens coalescing (or the
  Findings #1 reentrancy gap actually getting triggered by some future
  caller) would rely on these guards as the second line of defense, but
  nothing in the suite proves they still work — a regression here would
  only surface as the Findings #1 crash shape, not a targeted, fast-failing
  guard test.
- Suggested fix: a test that reaches `_redraw()` after its own `shell` is
  already destroyed (e.g. calling `_redraw()` directly, or `card()`'s
  returned `inner`, on a widget torn down out from under it) and asserts no
  exception, independent of the coalescing path.

### 3. README.md's "Aussehen" (Appearance) section is now stale — should-fix
- File: `README.md:82-87`
- Issue: this section (pre-existing, not touched by this diff) states — in
  German — "the window picks up the system's light/dark mode at startup...
  the choice is read once at start, not tracked live" (*"Die Wahl wird
  einmal beim Start gelesen, nicht laufend nachgeführt"*). That described
  the pre-3a behavior accurately; 3a adds a live, in-app Settings →
  Appearance control (System/Light/Dark) that changes the theme instantly,
  no restart, which this section does not mention at all — it still reads
  as if the only way to change the theme is to change the OS setting and
  restart the app.
- Failure scenario: a user reads the README, concludes there's no in-app
  way to force light/dark regardless of the OS, and never discovers the new
  Settings page — the shipped feature is real but undocumented in the one
  place a user would look.
- Note: `docs/spec.md`'s own "Affected areas" scoped this feature to
  `afk_clicker.py` only, so this isn't a scope violation by the developer —
  it's a genuine Round 9 ("did behaviour change without the README
  changing?") gap that the spec's own scoping didn't route to anyone.
  Flagging for the product-manager to route (a small README update, not
  code) rather than treating as part of 3a's own diff.

## Ten-round protocol walk

- **Round 1 — Ticket fidelity: PASS.** Diff stays entirely inside
  `afk_clicker.py`/`tests/test_ui.py` (+ `docs/design.md` updated to match
  Round 2's corrected sidebar order); no drive-by changes found reading the
  full diff. Branch `feature/ac-17/themes-follow-system-settings-tab`
  matches the `feature/{ab}-{ticket}/{description}` shape (`ac` = afk-
  clicker, ticket 17 = story #17).
- **Round 2 — Correctness: CONCERN.** Findings #1 above — a concrete,
  reproduced failing case (not speculation: exact repro, exact traceback,
  exact crash site), but gated behind a call path nothing in the current
  code or any real user interaction reaches. See Findings #1 for the full
  reachability argument.
- **Round 3 — Threading and Tk safety: PASS.** Every new/moved line
  touching Tk runs on the main thread. `_set_status` (`afk_clicker.py:
  2037-2048`) resolves `self.status` fresh only when `_drain_ui()` (main
  thread) actually calls it, matching the existing `_offer_update`/
  `_set_update_state`/`_mark_running` pattern — the worker thread only ever
  calls `self._ui(self._set_status, ...)`, which queues, never touches Tk
  directly. `QueuedStatusSurvivesARebuild` exercises the real narrow window
  (queue swapped, `self.status` not yet reassigned) end-to-end through a
  real worker thread and passes. The one new one-shot `after_idle` job
  (`_rebuild_after_id`) is cancelled in `on_close()` (`afk_clicker.py:
  2279-2284`, confirmed by revert check (c) above) and absorbed by
  `_rebuild_ui()` itself. No new repeating `after()` job introduced. No
  second worker can exist (`start()`/`stop()` untouched beyond the
  `_set_status` rename). Findings #1's reentrancy gap is same-thread
  event-loop reentrancy, not a cross-thread Tk-safety violation in this
  round's specific sense — filed under Round 2/8 instead.
- **Round 4 — Naming and shadowing: PASS.** `SettingsItem`,
  `resolve_appearance`, `_build_ui`, `_rebuild_ui`, `_build_settings`,
  `_apply_appearance`, `_show_settings`, `_set_status` — none shadow an
  import, builtin, or existing class/method.
- **Round 5 — Untrusted input: PASS.** The new `appearance` sanitiser
  (`afk_clicker.py:827-833`) validates the value's shape (`in ("system",
  "light", "dark")`), not merely `try/except`s a parse — matches
  `CODING-GUIDELINES.md`'s explicit "validate, don't wrap" rule and the
  existing `"games"` filter's own pattern. Covered by
  `AppearanceStore::test_garbage_values_fall_back_to_system` (`"sepia"`,
  `None`, `42`).
- **Round 6 — Tech stack conformance: PASS.** No new dependency — pure
  stdlib `tkinter`/`queue`, matching `TECHSTACK.md`. No build-flag-relevant
  import added.
- **Round 7 — Cross-platform behaviour: PASS — no platform-specific code
  touched.** `resolve_appearance()`/`_apply_appearance()` are
  platform-agnostic; `detect_os_theme()`'s own OS branches (Feature 2) are
  unchanged by this diff.
- **Round 8 — Tests: CONCERN.** See Findings #2 (guards untested) above.
  Everything else checked out: `test_five_rapid_appearance_changes_
  coalesce_into_exactly_one_rebuild`'s call-counting and
  `test_two_real_segmented_clicks_with_no_pump_between_them`'s real
  `event_generate` clicks assert the actual coalescing property, not an
  XTEST-double-delivery harness artifact (`TECHSTACK.md`'s specific
  warning) — no exact-fire-count-across-synthetic-presses pattern here.
  `QueuedStatusSurvivesARebuild`'s `StatusPill.__init__`/`time.monotonic`
  monkeypatching is elaborate but the only way to deterministically hit an
  inherently racy window without flakiness — acceptable, though it is the
  single most fragile test in the new set (breaks silently if
  `StatusPill.__init__`'s signature changes) — noted as a nit, not a
  should-fix. `CapturesCallbackExceptions` genuinely catches Defect 1 via
  its actual recorded exception (confirmed, revert check (b) above), has no
  escape hatch, and no existing test needs one or was made flaky by it
  (211/211 green, 3 repeated runs this session).
- **Round 9 — Comments and documentation: CONCERN.** See Findings #3
  (README stale) above. Code comments themselves are thorough and
  "why"-focused throughout the diff (`_rebuild_ui()`'s docstring,
  `_apply_appearance()`'s trace-ordering explanation, `_drain_ui`'s fix
  comment, `on_close()`'s cancel comment) — no noise/restated-code comments
  found. `docs/design.md` was correctly updated to match Round 2's
  corrected sidebar order.
- **Round 10 — Roadmap and release readiness: PASS.** Does not move or
  contradict any `ROADMAP.md` item. The "Settings schema version" item's
  own warning (a versioned migration must run before the `"games"` shape
  filter) does not apply — this change is additive-only (one new defaulted
  key, no shape change to an existing key), and the new sanitiser is placed
  immediately after the existing `"games"` filter, same spot/spirit,
  confirmed by direct code read (`afk_clicker.py:820-833`). Versioning:
  no version bump in this diff (pre-1.0.0, that's expected to happen at
  commit time, not implementation time).

## Follow-ups (non-blocking)
- Findings #1: add a reentrancy guard (or narrow the docstring's claimed
  invariant to match what's actually enforced) so a future synchronous
  caller of `_apply_appearance()` can't silently reintroduce Defect 1.
- Findings #2: a direct test for `card()`'s `winfo_exists()` guards,
  independent of the coalescing path.
- Findings #3: update `README.md`'s "Aussehen" section to describe the new
  in-app Settings → Appearance control (likely folded into 3b's spec, or a
  small standalone doc fix — product-manager's call).
- `QueuedStatusSurvivesARebuild`'s monkeypatch-heavy construction (noted
  under Round 8) — no action needed now, just flagged as the most
  maintenance-sensitive test in the new set.

## Overall verdict
**Approve with follow-ups.** Testing pass is clean (211/211, all three
Round-1 findings confirmably fixed and verified via revert-run-restore, no
regression). The ten-round review found no blocker: Findings #1 is a real,
reproduced correctness gap in the coalescing invariant, but is not
reachable through any current code path or real user interaction, and
Findings #2/#3 are test-coverage and documentation gaps, not functional
defects. None of the three rises to must-fix. Recommend routing all three
as follow-ups (Findings #1 ideally in the same area next time it's
touched, given how cheap a reentrancy guard would be; #2 as a small test
addition; #3 to the product-manager for a docs-only fix or folding into
3b).

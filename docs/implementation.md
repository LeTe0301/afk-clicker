# Implementation: G#39/GH#69 — close the residual macOS race in QueuedNonResyncedUpdatesSurviveARebuild

## Summary
Extended the "Round 2" fix (PR #58, G#30/GH#53) for the one flaky test
`tests/test_ui.py::QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`
to also close a gap Round 2 could not reach: a real `_poll_games()` scan
already started (and possibly still in flight) by `setUp()`'s own app
construction, before the test body's `self.ui._poll_games = lambda: None`
stub ever exists to block it. Test-only change, `tests/test_ui.py` only —
no production code (`afk_clicker.py`) touched, matching the spec's
"Proposed approach". A throwaway macOS diagnostic patch (deliverable B) was
also produced, verified to apply cleanly and run, but is **not** part of the
working tree — it lives only at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/f462b60e-d499-494f-ac9e-fb9b46949dd0/scratchpad/ac39-diag.patch`.

## Root cause

**Established from reading the code (verified against the actual line
numbers in this session, not assumed from the spec):**

- `afk_clicker.py:3131` — `self._timers["poll_games"] = self.root.after(5000, self._poll_games)`.
  This line runs inside `_poll_games()` itself, immediately after starting
  the scan thread (`afk_clicker.py:3129-3130`), on *every* call — including
  the very first one, from `__init__` → `_build_ui()`'s tail
  (`afk_clicker.py:2287`). The `after()` id is stored in `self._timers`,
  the same dict `on_close()` (`afk_clicker.py:3446-3451`) and `_rebuild_ui()`
  (`afk_clicker.py:2362-2367`) already know how to cancel — there is no
  separate `_poll_after`-style attribute; `self._timers["poll_games"]` is
  the one and only place the id lives.
- `UITestCase.setUp()` (`tests/test_ui.py:69-83`) builds a fresh
  `app.AfkAutoclicker` per test, which runs `_poll_games()` once via
  `_build_ui()`'s tail — starting a real scan thread and arming the timer
  above — then calls `self.settle()` (`tests/test_ui.py:100-121`), whose
  loop calls plain `self.root.update()` (not `update_idletasks()`), which
  *does* service due timer events. `settle()`'s own docstring already
  records that a cold `osascript` start on a loaded macOS runner can take
  close to 5s — long enough for the periodic timer to fire a **second** real
  scan while `settle()` is still waiting, all still inside `setUp()`, before
  the test body (and its `_poll_games` stub) exists.
- `settle()` returns as soon as `_seen_running` first exists
  (`tests/test_ui.py:165-167` in the pre-fix file), not once no scan is in
  flight — so a late-started second scan can still be running, unjoined,
  when the test body begins.
- The test body's `self.ui._ui(...)` (`afk_clicker.py:3167-3175`) is a plain,
  thread-safe `self._ui_queue.put(...)` requiring no Tk event-loop cycle to
  land. If the in-flight scan's own `self._ui(self._mark_running, ...)` call
  (`afk_clicker.py:3119`) lands between the test's manual queue-put and its
  trailing `_drain_ui()`, `_mark_running`'s unconditional
  `self._seen_running = running_ids` (`afk_clicker.py:3140`) clobbers
  `target` with the runner's real window state — reproducing the exact
  observed `AssertionError: ... 'minecraft' ...` without ever touching the
  `_ui_queue`-swap bug the test nominally guards.
- Nothing neutralizes this before the assertion: the cancel-timers-then-join-
  poll-thread sequence only exists in `on_close()`
  (`afk_clicker.py:3446-3484`), called from `tearDown()`, which runs *after*
  the test method's own assertion has already passed or failed.

This fully matches spec's **H1**. H2 (`update_idletasks()` servicing the
timer) is ruled out on inspection: `_redraw()`'s `inner.update_idletasks()`
(`afk_clicker.py:1554`) only reentrantly drains *idle* jobs per Tcl
semantics, not the `after(5000, ...)` timer event — verified by reading
`afk_clicker.py:2304-2325`'s own note, not just cited from the spec.

**Not established from code alone — now has macOS evidence, and it's
negative-in-isolation (Round 2, PR #71):** whether this mechanism is actually
the trigger behind the real G#39/GH#69 macOS recurrences remains
**unconfirmed**. The diagnostic draft PR (#71, run 34942811672) looped this
exact test 40x in isolation on macOS: 0/40 failures, no poll thread ever
alive at a manual queue-put, no periodic `_poll_games` firing inside the
target test, every real scan finishing well under 0.5s (max 0.481s, median
0.162s) — nowhere near the ~5s stall H1 requires. That is absence of the
triggering condition *in an isolated loop*, not evidence against the
mechanism itself (the historical failures happened inside a loaded
full-suite run, a materially different timing profile) — see "Round 2" below
for how this changed the fix's framing and wording throughout.

## Reuse audit (what `on_close()`/`_rebuild_ui()` already do, reused as-is)
- **Timer cancellation pattern** — `on_close()` (`afk_clicker.py:3446-3451`)
  and `_rebuild_ui()` (`afk_clicker.py:2362-2367`) both do
  `for job in self._timers.values(): try: self.root.after_cancel(job) except tk.TclError: pass`
  then `self._timers = {}`. The fix pops just `"poll_games"` (the one entry
  relevant here, since the test still wants `_rebuild_ui()`'s own timer
  cancellation — line 2362-2367 — to run normally when it destroys/rebuilds
  the tree a moment later) and applies the identical cancel-with-`TclError`-
  guard pattern, rather than inventing a new one.
- **Bounded thread join** — `on_close()`
  (`afk_clicker.py:3481-3484`) joins `self._poll_thread` with `timeout=2.0`
  if it's alive, with a comment explaining the bound (a stuck
  `Xlib.display.Display()` connection, observed roughly 1 scan in a couple
  hundred). The fix reuses the same "check `is_alive()` first, then bounded
  `join()`" shape, but **not** the same 2.0s bound — see "Round 2" below for
  why the bound was widened to 5.0s and paired with a loud failure instead of
  a silent proceed-anyway.
- **`getattr(..., None)` defensiveness** — spec's edge-case note ("can't
  happen for this test class, but guard anyway") matched with
  `getattr(self.ui, "_poll_thread", None)`, same style as `on_close()`'s own
  `getattr(self, "_timers", {})` at `afk_clicker.py:3446`.

No new mechanism was introduced; the fix is a straight reuse of
`on_close()`'s own cancel/join sequence, run earlier and narrower (just the
one timer key, just before the manual queue-put) instead of at teardown.

## Sibling tests audited (same class / neighbouring classes)
Grepped `tests/test_ui.py` for every `_mark_running`/`_seen_running` use:
- `test_error_and_stopped_updates_survive_a_rebuild` (same class, line
  ~3780) — queues `_set_status`, not `_mark_running`, and asserts on
  `self.ui.status`'s text, which `_mark_running` never touches. Not exposed
  to this race; left untouched.
- Two direct, synchronous `self.ui._mark_running({"minecraft"})` calls
  elsewhere in the file (around line 196-210, a different test class) call
  the method directly rather than queuing it through `_rebuild_ui()`/
  `_drain_ui()`, so there is no queue-landing race to close. Left untouched.
- No other test in the file both (a) queues a `_mark_running` result via
  `self.ui._ui(...)` and (b) asserts on `_seen_running` after a
  `_rebuild_ui()`/`_drain_ui()` pair. Only the one target test shares the
  exact mechanism; it is the only one changed.

## Changes by file
- `tests/test_ui.py` —
  `QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`:
  - Before the manual `self.ui._ui(self.ui._mark_running, target)` call
    (still inside the existing `self.ui._poll_games = lambda: None`
    try/finally block), added: pop and `after_cancel` any armed
    `self.ui._timers["poll_games"]`, join `self.ui._poll_thread` if alive
    (bounded `timeout=2.0`), then one extra `self.ui._drain_ui()` to discard
    whatever that joined scan put on the queue.
  - Extended the test's inline comment with a "Round 3 (G#39/GH#69,
    macOS-only recurrence)" paragraph recording this round's finding,
    following the same convention as the existing "Round 2" paragraph.
  - No other test method, class, or file changed.

## Key decisions / tradeoffs
- **Drain once more, not zero or twice** — per the spec's step 3: a bare
  join without a following drain would leave the joined scan's (harmless,
  pre-critical-section) `_mark_running` call sitting in the queue, where it
  would land during the test's own trailing `_drain_ui()` instead — right
  back to a real, if narrower, race. Draining immediately after the join,
  before the manual put, removes it deterministically.
- **Pop only `"poll_games"` from `self.ui._timers`, not the whole dict** —
  `_rebuild_ui()`'s own cancel-everything sweep (`afk_clicker.py:2362-2367`)
  runs a few lines later in the same test body and would double-cancel an
  already-`None` key harmlessly either way, but popping just the one key
  documents precisely which exposure this fix closes, rather than
  reimplementing `_rebuild_ui()`'s broader cleanup redundantly.
- **Why not touch `afk_clicker.py`** — same reasoning as G#30/PR #58: the
  periodic re-poll and `_mark_running`'s last-write-wins semantics are
  correct, intended production behavior. The gap is entirely this one test's
  continued exposure to a scan it has no business waiting on.

## Deviations from spec

**What was not done in this pass: the macOS CI evidence-gathering step
(the draft PR off `main` with print-based diagnostics).** The spec's
acceptance criteria gate the fix's *merge* on that CI evidence
(`Given the draft-PR diagnostic run on macOS CI ... H1 is confirmed`), but
this developer pass was explicitly scoped to "implement the fix and write
docs/implementation.md; don't commit/push" — opening a branch, pushing it,
and opening a draft PR requires exactly the actions I was told not to take.
Rather than silently skip the requirement or silently push anyway, I:
1. Built and verified deliverable B (the diagnostic patch) exactly as
   specified, as a standalone artifact ready for whoever does have push
   authority to apply it to a throwaway branch and open the draft PR.
2. Left `backlog.md`'s G#39/GH#69 entry unmarked (still `- [ ]`) rather than
   closing it — the spec's own "Affected areas" note says it should move to
   closed "once the fix lands," and this fix has not landed (it is not even
   committed yet, per instruction).
3. Recorded H1 as "established from code, not yet confirmed on macOS" above,
   rather than treating it as settled.

This is a deviation from the letter of the evidence plan's "one push," not
from its intent — the intent (don't guess at product/ops actions requiring
push access) is preserved by leaving that step to the next stage.

Everything else follows the spec's "Proposed approach" exactly (steps 1-4;
step 5's docstring update done as the "Round 3" paragraph above).

## Local race-class demonstration (spec's "Evidence plan", locally verifiable part)
Performed in a disposable `git clone` under the scratchpad
(`.../scratchpad/racedemo`, deleted afterward — never touched the real
working tree), checked out at this branch's tip, **not** using an arbitrary
unrelated thread but the *actual* tracked mechanism the fix addresses
(`self.ui._poll_thread` / `self.ui._timers["poll_games"]`):

1. Monkeypatched `app.detect_running` to sleep 20ms then return `set()`.
2. Called `self.ui._poll_games()` directly inside the test body (simulating
   H1 step 2: the periodic reschedule having fired a second real scan while
   `settle()` was still waiting) — this starts a real, tracked
   `self.ui._poll_thread` and arms `self.ui._timers["poll_games"]`, exactly
   as `setUp()` would on a slow macOS runner.
3. Restored `detect_running`, then ran the **unfixed** test body (existing
   `_poll_games` stub only) — **8/8 runs failed**, all with the exact
   historical `AssertionError: ... 'minecraft' ...` message, proving the
   test's exposure to a real, tracked scan already in flight from `setUp()`,
   not merely to an arbitrary late writer.
4. Applied this fix's cancel/join/drain sequence on top of the same demo
   (same slow-`detect_running` + direct `_poll_games()` call) — **8/8 runs
   passed**.
5. Deleted the scratch clone entirely; the real working tree was never
   touched by this demo (confirmed via `git status`/`git diff` before and
   after).

An earlier, cruder version of this demo (an arbitrary unrelated background
thread landing `self.ui._ui(self.ui._mark_running, set())` after a fixed
sleep, per the spec's literal suggested technique) was also tried first and
also reproduced the general "any late writer wins" vulnerability class
(3/3 red on the unfixed test) — kept only as a note here since the
tracked-mechanism version above is the one that actually exercises what
this fix closes.

## Sabotage acceptance test
In the real working tree, temporarily reintroduced the historical bug:
```python
self._timers = {}
self._ui_queue = queue.SimpleQueue()  # SABOTAGE (ac-39 acceptance test)
```
inserted at `afk_clicker.py:2367` (immediately after `self._timers = {}` in
`_rebuild_ui()`, the same spot `ac-30`'s own sabotage used — verified by
reading the surrounding lines first, not assumed from the spec's citation).
Ran the **fixed** test 5 times:
```
AssertionError: Items in the second set but not the first:
'minecraft' : a queued _mark_running() scan result should survive a
rebuild, not be silently dropped by the old _ui_queue swap
FAILED (failures=1)
```
5/5 failed, identically, with the original message — the fix does not blind
the guard. Reverted with `git checkout -- afk_clicker.py` immediately after;
confirmed `git diff` showed `afk_clicker.py` clean (only `tests/test_ui.py`
modified) before continuing.

## Local verification
Venv: `/tmp/claude-1000/-home-dev-projects-afk-clicker/f462b60e-d499-494f-ac9e-fb9b46949dd0/scratchpad/devvenv`.
Xvfb `:99` (pre-existing, confirmed via `pgrep -a Xvfb`); no second Tk
process was ever run concurrently on `:99` (the race demo's own gate lived
entirely inside the one test process, no induced load on a shared display
was needed).

- Baseline (before any change): `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 314 tests ... OK (skipped=10)`, matching the expected baseline exactly.
- Fixed test, 20x back-to-back:
  `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`
  → 20/20 passed.
- Sabotage, 5x: see above — 5/5 failed with the original assertion message; reverted.
- Full suite after the real fix: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 314 tests ... OK (skipped=10)` — identical to baseline, no regression.
- No lint/type-check step exists in this project (`.github/workflows/ci.yml` runs only `unittest discover`); none was skipped.

## Deliverable B — throwaway macOS diagnostic patch
File: `/tmp/claude-1000/-home-dev-projects-afk-clicker/f462b60e-d499-494f-ac9e-fb9b46949dd0/scratchpad/ac39-diag.patch`
(unified diff, **not applied to this working tree**).

- Verified `git apply --check` succeeds against a fresh clone checked out at
  `main`/`hotfix/ac-39` tip `d008e88` (both branches point at the same
  commit, confirmed via `git branch -a --contains d008e88`).
- Verified the patch actually applies (`git apply`, no `--check`) in that
  same disposable clone and that
  `tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild` (both tests)
  passes once on Linux/Xvfb with `AC39_DIAG=1` set.
- Contents:
  - `tests/test_ui.py`: adds a module-level `AC39_DIAG` env-gated
    `_ac39_log()` helper (stderr, `[ac39] <monotonic-time> <thread-name> <msg>`
    format) that is a complete no-op unless `AC39_DIAG=1`. When enabled, it
    monkeypatches `app.AfkAutoclicker._poll_games` and `._mark_running` at
    import time to log entry (tagging the 0th call "initial" and every
    later one "periodic" via a per-instance counter), plus a small watcher
    thread per scan that joins it and logs the scan thread's finish time —
    all test-file-only, `afk_clicker.py` untouched, as the spec required.
    Also logs `settle()`'s return value/time, and, inside the target test
    method itself, the manual queue-put, `_rebuild_ui()`'s return, the final
    drain's resulting `_seen_running`, and the assertion passing.
  - `.github/workflows/ci.yml`: adds one new step, `ac-39 diagnostic loop
    (macOS only, temporary)`, gated `if: runner.os == 'macOS'`, capped at
    `timeout-minutes: 20`, running the target test class 40x in a bash loop
    with `AC39_DIAG=1`, `|| fail=$((fail+1))` per iteration so one failure
    doesn't lose later iterations' logs, printing a final `N/40 failed`
    count. Placed before the existing "Run the test suite (Windows / macOS)"
    step so its timing isn't perturbed by the full suite.
- This patch is meant to be applied to a **new throwaway branch cut from
  `main`** (never from `hotfix/ac-39/...` itself) for a draft PR that is
  opened, read, and closed unmerged — per the spec's evidence plan. It was
  not applied or pushed anywhere by this developer pass (no push access
  exercised, per instruction); that step is left to whoever runs the next
  stage of this pipeline.

## Known limitations
- The bounded 5.0s join (Round 2; was 2.0s in Round 1 of this fix) can still
  time out on a genuinely stuck scan; unlike Round 1, this now fails the test
  loudly instead of proceeding into the race — see "Round 2" below.
- H1 (a slow macOS `osascript` stall arms a still-running poller) is
  code-established and sabotage-verified as a real, closed race path, but
  is **not confirmed** as G#39's actual real-world trigger — PR #71's
  isolated-loop evidence is negative (0/40, see "Round 2"). A recurrence of
  G#39 with this fix in place means H1 was not the (only) cause.

## How to verify locally
```
cd /home/dev/projects/afk-clicker
export DISPLAY=:99   # or any free Xvfb display
<venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild -v
<venv>/bin/python -m unittest discover -s tests -t .

# Sabotage (in a throwaway copy or via git checkout -- afterward, never left in the real tree):
# insert `self._ui_queue = queue.SimpleQueue()` right after `self._timers = {}`
# in afk_clicker.py's _rebuild_ui() (~line 2367), run the target test 3-5x (fails every time),
# then `git checkout -- afk_clicker.py`.

# Diagnostic patch (deliverable B), against a fresh clone at d008e88:
git clone <repo> /tmp/diagcheck && cd /tmp/diagcheck && git checkout d008e88
git apply --check /path/to/ac39-diag.patch   # confirms clean apply
git apply /path/to/ac39-diag.patch
AC39_DIAG=1 DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild -v
```
Run in this session: all of the above (baseline, 20x fixed-test loop, 5x
sabotage, full suite, and the diagnostic patch's apply-check + one Linux run)
— see "Local verification" and "Deliverable B" sections for actual output.

## Round 2 (PR #70 review / PR #71 macOS evidence)

**What changed the framing:** the reviewer's testing pass (`docs/test-review.md`)
confirmed the code change itself is correct and sabotage-verified — two
independently-designed sabotages (the `_ui_queue` swap, and a separate
"discard queued closures without executing them" variant) both still fail
5/5, and an independent race-class reproduction (old critical section red,
new one green, 10/10 each, against a real injected in-flight `_poll_thread`)
confirmed the mechanism directly. The blocker (Finding #1, "changes
requested") was that the spec's own AC3 required macOS CI to confirm H1
before shipping, and the diagnostic evidence that came in (draft PR #71, run
34942811672) was negative in isolation: 0/40 failures, no poll thread ever
alive at a manual queue-put, no periodic `_poll_games` firing inside the
target test, max scan 0.481s / median 0.162s — nowhere near the ~5s stall H1
needs. The orchestrator revised `docs/spec.md`'s acceptance criteria in
response (struck AC3, replaced with: ship as a defensive closure with H1
explicitly hedged everywhere, fail loudly instead of silently racing on a
timeout, keep G#39 open as "mitigated, trigger unconfirmed").

**Changes made this round, all in `tests/test_ui.py` plus docs:**
1. **Hedged wording** in the test's inline comment (added a "Round 4 (PR #70
   review / PR #71 macOS evidence, hedge)" paragraph — the "Round 3" text
   itself was also softened from stating the mechanism as fact ("the
   periodic timer fires a SECOND real scan") to conditional phrasing ("IF
   that first scan takes long enough ... could fire"), plus the new
   paragraph spells out PR #71's numbers and states H1 as "likely but
   UNCONFIRMED"), in `docs/implementation.md` (this file — see the "Root
   cause" and "Known limitations" sections above), and in `backlog.md`'s
   G#39 entry (now says "Mitigated (PR #70), trigger unconfirmed", stays
   `- [ ]` open, and states explicitly that a recurrence with the fix in
   place means H1 was not the (only) cause).
2. **Loud failure on a timed-out join.** Previously: `poll_thread.join(timeout=2.0)`
   then proceed regardless of whether the thread was still alive (silently
   walking into the very race this fix exists to close, in the rare case the
   bound is hit). Now: `poll_thread.join(timeout=5.0)`, and if
   `poll_thread.is_alive()` afterward, `self.fail("real game poller still
   running after 5s; cannot isolate the queued update from a real scan
   landing later -- see G#39")` before ever reaching the manual queue-put.
   **Bound choice, decided and justified (per the coordinator's ask,
   `self.fail` vs. a longer wait-then-fail):** widened from `on_close()`'s
   2.0s to 5.0s, matching `settle()`'s own docstring, which documents a
   *legitimately slow, not stuck*, cold `osascript` start taking close to 5s
   on a loaded macOS runner — the same real-world timing profile this whole
   investigation is about. `on_close()`'s shorter 2.0s bound optimizes for a
   fast app shutdown and is content to abandon a still-running scan
   (nothing downstream depends on it finishing); this test's whole point is
   the opposite — it needs the poller genuinely silenced, not merely
   bounded-then-ignored — so a bound that would routinely time out on the
   very stall this fix is meant to tolerate would turn "generous enough to
   let a slow-but-real scan land" into "reliably fails on exactly the
   scenario H1 describes," which is worse than the race it replaces.
   *Correction from the round 2 re-review:* the ~5s cold start is the
   **first** scan's worst case, and `settle()` has already absorbed it by
   the time this join runs; the thread joined here is usually a later,
   warm periodic scan (PR #71: all under 0.5s). So 5.0s is a generous
   margin that in practice only trips on a genuinely stuck scan, not a
   routinely slow one. `fail`
   over `skip`: a skip would hide a genuinely stuck poller from CI's summary
   the same way a proceed-anyway silently hides it from the assertion;
   `self.fail` with a message naming the condition is the only outcome that
   surfaces the problem and lets a future recurrence say plainly whether a
   still-running poller (H1) was the trigger, rather than reproducing the
   same ambiguous `'minecraft'`-missing assertion with no diagnosis.
3. Re-verified everything the sabotage/regression criteria require, plus a
   new sabotage of the loud-fail path itself (see below).

### Re-verification (Round 2)
All run against the real working tree, `DISPLAY=:99`, same venv as before.
- Sabotage (`_ui_queue = queue.SimpleQueue()` reinserted at
  `afk_clicker.py:2367`), fixed test x5: **5/5 failed**, identical
  `AssertionError: ... 'minecraft' ...` message (confirmed it was the
  original assertion, not the new loud-fail message) — reverted via
  `git checkout -- afk_clicker.py`, confirmed clean.
- Fixed test, 20x back-to-back: **20/20 passed**.
- Full suite: `Ran 314 tests ... OK (skipped=10)` — identical to baseline,
  no regression.
- **New: sabotage of the loud-fail path itself.** Temporarily replaced
  `self.ui._poll_thread` (right before the neutralization block) with a
  freshly-started thread that sleeps 8.0s — deliberately longer than the new
  5.0s bound, simulating a genuinely stuck (not just slow) scan. Ran the
  test once:
  ```
  AssertionError: real game poller still running after 5s; cannot isolate
  the queued update from a real scan landing later -- see G#39
  FAILED (failures=1)
  ```
  The new message appeared exactly as designed (test took ~7.3s, consistent
  with the 5.0s join bound plus setup/teardown overhead). Reverted the
  injected sabotage immediately after; re-ran the class once more to confirm
  it was back to a clean `OK` before re-running the full suite.

### Changes by file (Round 2)
- `tests/test_ui.py` —
  `QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`:
  softened the "Round 3" comment's factual claims to conditional phrasing,
  added a "Round 4" comment paragraph recording PR #71's hedge, and changed
  `poll_thread.join(timeout=2.0)` (proceed regardless) to
  `poll_thread.join(timeout=5.0)` followed by `self.fail(...)` if still
  alive.
- `docs/implementation.md` — this file: hedged the "Root cause" and "Known
  limitations" sections, updated the "Reuse audit" bounded-join bullet, added
  this "Round 2" section.
- `backlog.md` — G#39/GH#69 entry: added a "Mitigated (PR #70), trigger
  unconfirmed" paragraph; left the checkbox `- [ ]` (still open), per the
  coordinator's explicit instruction.
- `docs/spec.md` — updated by the orchestrator before this round started
  (not by me); AC3 struck through and replaced, per the diff already present
  in the file when this round began.

### How to verify locally (Round 2)
```
cd /home/dev/projects/afk-clicker
export DISPLAY=:99
<venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild -v   # both ok
<venv>/bin/python -m unittest discover -s tests -t .                                     # full suite, unchanged baseline

# Sabotage (revert after): insert `self._ui_queue = queue.SimpleQueue()` after
# `self._timers = {}` in afk_clicker.py's _rebuild_ui() (~line 2367); run the
# target test 3-5x (fails every time, original assertion); git checkout -- afk_clicker.py

# Loud-fail sabotage (revert after): inside the target test, right before the
# `try:` block, replace self.ui._poll_thread with a thread that sleeps longer
# than 5.0s and .start()s it; run the test once (fails with the new "real game
# poller still running after 5s" message, not the original assertion).
```
Run in this session: all of the above — see "Re-verification (Round 2)"
above for actual output.

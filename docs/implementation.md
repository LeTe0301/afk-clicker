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

**Not established from code alone (awaiting macOS CI evidence):** whether
this is actually the trigger on the real macOS runs that produced G#39/GH#69,
as opposed to some other timing quirk. The spec's own evidence plan (a
throwaway draft PR off `main` with print-based diagnostics, opened, read, and
closed unmerged) is the only way to confirm this on the real hardware — see
"What was not done in this pass" below for why that step was not executed
here.

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
  hundred). The fix reuses the exact same `timeout=2.0` bound and the same
  "check `is_alive()` first" guard, per the spec's own citation.
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
- The bounded 2.0s join can still time out on the documented
  ~1-in-a-couple-hundred stuck-`Display()` case; per the spec's own edge
  case, this fix reduces exposure from "unbounded" to "at most 2s of
  continued real risk," it does not eliminate it outright.
- H1 remains code-established but macOS-CI-unconfirmed until the draft-PR
  diagnostic step (deliverable B) is actually run — see "Deviations from
  spec" above.

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

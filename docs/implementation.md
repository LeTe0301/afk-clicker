# Implementation: G#30/GH#53 — macOS flake in QueuedNonResyncedUpdatesSurviveARebuild

## Summary
Fixed the macOS-only flake in
`tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`
by removing the one genuinely non-deterministic input the test was
unintentionally depending on: a real, unmocked `detect_running()` OS scan
that `_rebuild_ui()` legitimately (and correctly) triggers as a side effect.
No production code (`afk_clicker.py`) changed — this is a test-only fix.
`tests/test_ui.py` is the only file touched.

## Root cause
**Established, from reading the code (not from a macOS reproduction — see
"What is inference vs. established" below):**

The test's sequence is:
```python
self.ui._ui(self.ui._mark_running, target)   # (A) queue a fake scan result
self.ui._rebuild_ui()                         # (B) tear down + rebuild
self.ui._drain_ui()                           # (D) test's own drain
self.assertEqual(self.ui._seen_running, target, ...)
```

`_rebuild_ui()` calls `_build_ui()`, whose own tail (`afk_clicker.py:2140-2143`)
does exactly this, unconditionally, on every rebuild:
```python
self._drain_ui()      # drains (A) -- this part is deterministic and correct
self._poll_games()    # starts a NEW background thread, unrelated to (A)
```

`_poll_games()` (`afk_clicker.py:2950-2990`) spawns a real
`threading.Thread` that calls `detect_running(profiles)` — a genuine OS
scan (an Xlib tree walk on Linux, an `osascript` subprocess on macOS,
per `_window_titles()` at `afk_clicker.py:1104-1159`) — and then does
`self._ui(self._mark_running, running)` with whatever it actually finds.
This class never mocks `detect_running` (unlike
`PollGamesScanDoesNotHoldSelfWhileBlocked`, which already does, at
`tests/test_ui.py:275-330` in the pre-fix file), so on any platform this is
a real scan of the CI runner's real windows.

For the assertion to fail with "'minecraft' missing" (the actual observed
`AssertionError`, an `assertEqual`-on-sets diff, not a raised exception), the
value that ends up in `self.ui._seen_running` must be a genuine, different
*set* — not merely absent. `_mark_running` only ever gets there by actually
running to completion (it unconditionally does `self._seen_running =
running_ids` partway through its own body). The only second source of a
`_mark_running(running_ids)` call anywhere in this sequence is the new scan
thread `_poll_games()` just started. If that thread's real scan finishes and
its queued `_mark_running(real_running_ids)` call gets drained — by the
test's own `self.ui._drain_ui()` call (D), there being no other drain path
in between (no `root.update()` runs between (A) and (D), and
`_rebuild_ui()`'s own `_rebuilding`/`_rebuild_after_id` guards already rule
out a second, reentrant `_rebuild_ui()` interleaving here, per the reasoning
already recorded in `docs/history/ac-24-f3-implementation.md`'s "The third
macOS failure" section) — before the assertion runs, `real_running_ids`
(which never contains "minecraft" on a CI runner) overwrites the test's
`target`. That reads exactly like "queued update silently dropped" in the
assertion, without being the historical `_ui_queue`-swap bug this test
exists to guard (which is still fixed, and stays fixed — nothing here
touches that code path).

This is why it is macOS-only and immune to any change that isn't to this
exact scan/rebuild interaction: `docs/history/ac-24-f3-implementation.md`
already investigated (without macOS access) whether a *second, uninvited*
`_rebuild_ui()` call could interleave here, concluded no such path exists
given the existing reentrancy guards, and flagged this exact test as
possibly fixed "by a different, more general mechanism" by that round's
`<Configure>`-binding-timing fix — explicitly unconfirmed. G#30's four
recurrences (including three *after* that fix had already landed) confirm
that theory did not hold, and point at the mechanism above instead: not an
extra rebuild, but the rebuild's own, entirely legitimate, second
`_poll_games()` scan.

## Changes by file
- `tests/test_ui.py` —
  `QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`:
  monkeypatches `app.detect_running` to a deterministic
  `lambda profiles: target` for the duration of the test (restored in a
  `finally`, matching the existing convention already used by
  `PollGamesScanDoesNotHoldSelfWhileBlocked.test_scan_only_holds_profiles_not_self_during_detect_running`
  a few classes above it in the same file). Added a comment recording the
  race and why the fix is safe. No other test in the file touches
  `detect_running`'s mocking convention differently.

## Key decisions / tradeoffs
- **Why stub the result to equal `target`, not to something fast-but-empty:**
  the goal is to make the assertion's outcome independent of *which* scan
  wins the race, not to make one side win reliably (which would just trade
  one flake for another, or for a fast, deterministic wrong answer). If
  `_rebuild_ui()`'s own second scan's `_mark_running` call lands before the
  assertion, it now lands the *same* value the test already queued, so the
  observed `self.ui._seen_running` is identical either way. Critically, this
  does not weaken what the test guards: a genuinely dropped queue entry (the
  old `_ui_queue`-swap bug) still produces a visibly different
  `_seen_running` (whatever it was before this test ran, per `old_seen`) and
  still fails the assertion exactly as before.
- **Why not add a `pump_until`/wait instead:** the suggested direction in
  the ticket raised this, but it does not fit here after tracing the actual
  dependency — there is no `root.update()` between the queue-put and the
  drain for anything to be waited *for*; the second scan's result is not
  something this test should ever want to wait for landing, since it is
  real, non-deterministic OS data this test has no business depending on
  either way. Waiting for it would just turn an intermittent flake into a
  reliable failure (or a reliable pass that depends on real window state on
  the runner, which is worse, not better).
- **Why not touch `afk_clicker.py`:** `_rebuild_ui()` re-triggering
  `_poll_games()` on every rebuild is correct, intended production behavior
  (a rebuild — e.g. an Appearance change — should re-check what's currently
  running, same as construction does). The bug is entirely in this one
  test's exposure to that real scan, not in the production code path.
- **Scope of the monkeypatch:** the whole test body, restored in `finally`,
  not narrowed to just the `_rebuild_ui()` call — this also covers the
  thread `_poll_games()` starts, which can still be running (and calling
  `detect_running`) after `_rebuild_ui()` itself has returned.

## Deviations from spec
None. The ticket explicitly left "which of the suggested directions
actually fits" open pending verification, and asked for the real dependency
to be traced rather than assumed — this is exactly what the root-cause
section above does, and the fix follows from that tracing rather than from
applying `pump_until` by default.

## Known limitations / what is inference vs. established
- **Established (from local reproduction on Linux/Xvfb, this session):**
  the code path traced above — `_rebuild_ui()` → `_build_ui()`'s tail →
  `_drain_ui()` then unconditional `_poll_games()` → a real,
  never-mocked `detect_running()` call on a new background thread whose
  result lands via `self._ui(self._mark_running, ...)` — exists exactly as
  described, and is exercised by every run of this test, on every platform.
  The fix removes that real scan deterministically and the full suite
  (293 tests, Linux/Xvfb) still passes, including the GC regression guard
  (`GcAutomaticCollectionStaysDisabled`) and `tearDownModule`'s
  off-main-thread error count.
- **Inference, not established (this box has never reproduced the failure,
  and cannot generate a real macOS `osascript` scan to confirm the exact
  race window):** that this specific second-scan race, rather than some
  other macOS-Tk-build-specific quirk in `update_idletasks()` (raised as an
  open possibility in `docs/history/ac-24-f3-implementation.md` but never
  confirmed either way), is the actual mechanism. It is the strongest
  candidate that survives elimination against the established, linear code
  path — no other route was found by which the *original* queued value
  could be lost between the queue-put and the drain — and it is the only
  candidate consistent with the failure being macOS-only (a real subprocess
  scan on a shared, often-loaded CI runner is a materially different
  timing profile than Linux's in-process Xlib walk) and with three of the
  four recurrences changing no code that could plausibly matter otherwise.
  If G#30 recurs after this fix on a future CI run, that would falsify this
  root cause and point at the `update_idletasks()` alternative instead —
  worth flagging explicitly rather than treating this fix as certain.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-30
Xvfb :50 -screen 0 1600x1000x24 &     # or any free display
export DISPLAY=:50
<venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild -v
<venv>/bin/python -m unittest discover -s tests -t . -v   # full suite
```
Run in this session: both commands above, from this worktree, against
`/tmp/claude-1000/.../scratchpad/venv/bin/python` on `DISPLAY=:50`.
`QueuedNonResyncedUpdatesSurviveARebuild` — both tests `ok`. Full suite —
`Ran 293 tests ... OK (skipped=5)`, identical to a `git stash` run of the
same suite against the pre-fix file (confirming no regression and that the
one pre-existing, unrelated `invalid command name "..._drain_ui"` Tcl
teardown warning already present on `test_error_and_stopped_updates_survive_a_rebuild`
predates this change). **What only macOS CI can confirm:** whether the
actual G#30/GH#53 flake stops recurring — this fix cannot be verified
against the real failure from this (Linux-only) box.

## Round 2 (PR #58 review) — the stub's value collision, and why

**The finding, confirmed:** Round 1's fix stubbed `detect_running` to return
`target` (`{"minecraft"}`) — the exact same set this test manually queues.
The review reintroduced the historical bug this test exists to catch (the
`_ui_queue` swap back at `_rebuild_ui()`, dropping the manually-queued
`_mark_running(target)` call before it can drain) and ran the test 3 times.
It passed all 3. I reproduced this myself, in a scratchpad copy, before
changing anything: same sabotage, same 3/3 pass.

**Root cause of the collision:** `_build_ui()`'s tail still unconditionally
calls `self._poll_games()` after its own `_drain_ui()`, same as before —
Round 1 only ever stubbed *what that second scan returns*, not whether it
runs. With the sabotage in place, the manual queue-put is dropped by the
swap, but the second scan's own `self._ui(self._mark_running, ...)` call is
not — it lands on the fresh, post-swap queue and gets drained by this test's
own trailing `_drain_ui()` call. Because Round 1 stubbed `detect_running` to
return the same value the test queues, that second scan's (illegitimate)
landing is indistinguishable from the manual one's (correct) landing —
`self._seen_running` ends up `{"minecraft"}` either way, so the assertion
cannot tell a genuinely dropped entry from a forged stand-in.

**Why the review's literal suggested value doesn't work either — checked,
not assumed:** the review proposed stubbing to a value distinguishable from
`target` (e.g. `old_seen`). I tried this first, in a scratchpad copy, before
picking a different fix: `app.detect_running = lambda profiles: old_seen`.
Run against the *unmodified, correct* code (no sabotage), this failed 5/5 —
not flaky, reliably wrong. Cause: `threading.Thread.start()` does not return
until the new thread signals (via an internal `Event`) that it has actually
begun running, which in CPython's GIL scheduling hands the new thread a
window to run first. With `detect_running` stubbed to an instant lambda
(no real Xlib/`osascript` call to block on and yield the GIL back), the
second scan's thread reliably finishes and puts its `_mark_running(old_seen)`
call onto the queue *before* this test's own `self.ui._drain_ui()` line
executes — every run, not merely as a race. So any distinguishable stub
value makes the second scan reliably overwrite the correctly-landed `target`
with something else, failing the test on entirely correct code. This is the
opposite failure mode from the one under review (a false failure instead of
a false pass), but it is just as disqualifying, so I did not implement the
literal suggestion.

**The actual fix:** disable `_poll_games()` itself for the duration of the
test (`self.ui._poll_games = lambda: None`, restored in `finally`), instead
of stubbing what it would return. This removes the confound outright — no
second scan, real or stubbed, ever starts during this test, so the only
`_mark_running` call that can possibly land is the one this test queues
itself. A genuinely dropped entry now has nothing to hide behind, because
there is nothing else in flight to produce a coincidentally-matching (or
coincidentally-different) result.

**My own sabotage run, against this fix:** in a fresh scratchpad copy of
this worktree, reintroduced the exact same `_ui_queue = queue.SimpleQueue()`
swap at `_rebuild_ui()` (`afk_clicker.py:2224` in that copy, same spot as
the original bug), and ran
`test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands` 3
times:

```
AssertionError: Items in the second set but not the first:
'minecraft' : a queued _mark_running() scan result should survive a
rebuild, not be silently dropped by the old _ui_queue swap
FAILED (failures=1)
```

All 3 runs failed, identically. Restored `afk_clicker.py` via
`git checkout --` in that scratchpad copy immediately after, confirmed
`git diff` was clean there, and deleted the scratchpad copy — the real
worktree's `afk_clicker.py` was never touched by any sabotage run.

**Non-fragility, re-confirmed:** ran
`QueuedNonResyncedUpdatesSurviveARebuild` (both tests) 5 times back-to-back
against the real, unmodified worktree — `OK` every time — then the full
suite once — `Ran 293 tests ... OK (skipped=5)`.

**Comment correction:** the test's own inline comment previously claimed
"whichever scan's result lands first, the observed `self._seen_running` is
identical" as the safety property — true of the stubbed-value approach, but
that was exactly the property masking the sabotage. Replaced with a comment
recording this round's finding directly (see `tests/test_ui.py`, the
"Round 2 (G#30 PR review)" paragraph) — the property this test now
guarantees is "no second scan runs at all", not "both scans agree".

### Changes by file (Round 2)
- `tests/test_ui.py` — `test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`:
  replaced the `detect_running` stub with `self.ui._poll_games = lambda:
  None` for the duration of the test body, restored in `finally`. Comment
  rewritten to describe the actual mechanism and this round's finding
  instead of the Round 1 claim it falsified.

### How to verify locally (Round 2)
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-30
export DISPLAY=:150   # or any free Xvfb display
<venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild -v
<venv>/bin/python -m unittest discover -s tests -t .

# Sabotage (in a throwaway copy, never the real worktree):
cp -r . /tmp/scratch-copy && cd /tmp/scratch-copy
sed -i 's/self\._timers = {}\n/self._timers = {}\n            self._ui_queue = queue.SimpleQueue()  # SABOTAGE\n/' afk_clicker.py   # or edit by hand at _rebuild_ui()'s destroy-loop, matching afk_clicker.py:2218-2222
<venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands -v   # FAILs
git checkout -- afk_clicker.py   # restore, then delete the copy
```
Run in this session: exactly this (5x non-sabotaged, 3x sabotaged, full
suite once) — see the round-2 section above for the actual output.

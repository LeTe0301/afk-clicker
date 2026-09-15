# Spec: G#39/GH#69 — close the residual macOS race in QueuedNonResyncedUpdatesSurviveARebuild

## Summary
PR #58's fix (stubbing `_poll_games` to a no-op for the duration of the test) only blocks a
*new* rescan from starting during the test body; it does nothing about a scan that was already
started (and may still be in flight) by `setUp()`'s own app construction before the stub takes
effect — that's the gap this bugfix needs to actually close.

## Goals
- Identify, with file:line evidence, every remaining writer of `self.ui._seen_running`/the
  `_ui_queue` that can land between the test's manual `_mark_running(target)` queue-put and its
  final `_drain_ui()`/assertion, beyond the one PR #58 already closed.
- Get real evidence from macOS CI (the only place this reproduces) in the fewest possible pushes,
  given the token can't re-run a job (`actions:write` missing).
- Fix the actual mechanism (product race vs. remaining test exposure), sabotage-verified against
  the historical `_ui_queue`-swap bug this test guards.

## Non-goals
- Any other flake in the suite (`test_holding_does_not_repeat`/G#32, the interpreter-shutdown
  abort/G#27, etc.) — untouched.
- Unrelated cleanup/refactor of `_poll_games()`, `_rebuild_ui()`, or the UI test harness beyond
  what this fix requires.
- Making `_seen_running` merge/reconcile results across concurrent scans — out of scope; the
  fix's job is to make this *test* hermetic, not to change production polling semantics.

## Background / current state

### The test and what it guards
`tests/test_ui.py:3801` `QueuedNonResyncedUpdatesSurviveARebuild.
test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands` exists to prove a
`_mark_running()` scan result queued just before `_rebuild_ui()` is not silently dropped by the
old `_ui_queue`-swap bug (fixed for good: `_ui_queue` is now created exactly once, in `__init__`
at `afk_clicker.py:1965`, and `_rebuild_ui()` — `afk_clicker.py:2289`+ — never re-creates it,
per its own docstring at `afk_clicker.py:2334`). Current body (`tests/test_ui.py:3822-3843`):
```python
original_poll_games = self.ui._poll_games
self.ui._poll_games = lambda: None
try:
    self.ui._ui(self.ui._mark_running, target)
    self.ui._rebuild_ui()
    self.ui._drain_ui()
    self.assertEqual(self.ui._seen_running, target, ...)
finally:
    self.ui._poll_games = original_poll_games
```

### PR #58's fix and why it's incomplete (`docs/history/ac-30-implementation.md`)
Root cause established there: `_build_ui()`'s tail (`afk_clicker.py:2287`, reached from inside
`_rebuild_ui()`) unconditionally calls `self._poll_games()` again on every rebuild, starting a
*real* `detect_running()` scan (Xlib walk on Linux, `osascript` subprocess on macOS) whose result
can land, via a plain `self._ui(self._mark_running, ...)` call, before the test's own trailing
`_drain_ui()`. Round 1 stubbed `detect_running`'s return value (dead end: collided with sabotage,
made it invisible). Round 2 (the shipped fix) instead disables `self.ui._poll_games` itself for
the test's duration — closing *that one call site* (the rebuild-triggered rescan).

**What Round 2 did not close:** `_poll_games()` has a second, independent trigger —
`afk_clicker.py:3131`: `self._timers["poll_games"] = self.root.after(5000, self._poll_games)`,
a self-rescheduling 5-second timer, set up on every call including the very first one, from
`__init__`. This line does an attribute lookup of `self._poll_games` **at the moment the
currently-running real call reaches it** — it captures a bound-method value that Tk holds
directly. Reassigning `self.ui._poll_games = lambda: None` later, inside the test body, has no
effect on a timer that already captured the *original* method before the test ever ran.

### Why this is exploitable specifically here
1. `UITestCase.setUp()` (`tests/test_ui.py:69-83`) builds a brand-new `app.AfkAutoclicker` for
   *every* test method, which runs `_build_ui()`'s tail once from `__init__`
   (`afk_clicker.py:2287`) — this is the first, real `_poll_games()` call, starting scan thread A
   and arming the 5000ms timer described above.
2. `setUp()` then calls `self.settle()` (`tests/test_ui.py:100-121`), whose own docstring records
   **prior, observed evidence** that a cold `osascript` start on a loaded macOS runner can take
   close to (previously: over) 5 seconds — this is exactly why the ceiling was raised from 5s to
   15s (PR #30 review round 1). If scan A takes ≳5s, the periodic timer becomes due *while
   `settle()` is still polling* (`settle()`'s loop calls plain `self.root.update()`, which does
   service due timer events, unlike `update_idletasks()` — see `afk_clicker.py:2304-2325`'s own
   note that `update_idletasks()` only reentrantly services *idle* jobs, not timers). That fires a
   **second** real scan (thread B) and reschedules the timer again — all still inside `setUp()`,
   before the test body (and its `_poll_games` stub) ever runs.
3. `settle()` returns as soon as `_seen_running` **first** exists (`tests/test_ui.py:114-119`) —
   i.e., as soon as *any* scan lands — not once no scan is in flight. So thread B (started late,
   because scan A was slow) can still be running, unjoined, when the test body begins.
4. The test body's own `self.ui._ui(...)`/`_rebuild_ui()`/`_drain_ui()` sequence never calls
   `self.root.update()` — but that's irrelevant to thread B: `self._ui(...)`
   (`afk_clicker.py:3170-3175`) is a plain, thread-safe `self._ui_queue.put((fn, args))`, requiring
   no Tk event-loop cycle to land. If thread B's scan finishes and calls
   `self._ui(self._mark_running, real_running)` (`afk_clicker.py:3119`) at any real-world instant
   between the test's manual queue-put and its final `_drain_ui()`, it lands on the *same*
   never-swapped queue, and `_mark_running`'s unconditional last-write-wins assignment
   (`afk_clicker.py:3139-3140`, `self._seen_running = running_ids`) silently clobbers `target`
   with the runner's real (never-"minecraft") window state — reproducing the exact observed
   failure (`AssertionError: ... 'minecraft' ... second set but not the first`) without ever
   touching the `_ui_queue`-swap bug the test nominally guards.
5. Nothing cancels timer/joins thread A or B before the assertion: that cleanup
   (`afk_clicker.py:3446-3482`, cancelling `self._timers` and joining `self._poll_thread`, bounded
   2.0s) only happens in `on_close()`, called from `tearDown()` — which runs *after* the test
   method's own assertion has already passed or failed.

This is a genuinely broader exposure than the one PR #58 fixed: *any* `_mark_running` call
already in flight from construction — not just one newly started during the rebuild — can win
the race, and PR #58's stub cannot reach it because it was never able to (the timer already
captured the real method before the stub existed).

## Root-cause hypotheses, ranked

**H1 (primary, well-evidenced from code alone).** A scan started during `setUp()` (either the
initial one, or a periodic reschedule fired while `settle()` was still waiting out an unusually
slow initial scan) is still in flight when the test body runs, and its late, thread-safe
`_ui_queue.put()` landing overwrites the test's manually-queued value. Fully explained by the
code path above — `afk_clicker.py:1965,2287,3091-3140,3170-3175`; `tests/test_ui.py:69-121`.
Locally testable on Linux/Xvfb *as a mechanism* (see "Evidence" below) but the actual trigger
(a near-5s `osascript` stall) is macOS-only and cannot be induced on this box (Linux's
`detect_running` path is an in-process Xlib walk, not a subprocess, and the project's own test
convention already rules out inducing load via a second Tk process on a shared display).

**H2 (considered, lower probability).** `card()`'s `_redraw()` reentrant `inner.update_idletasks()`
(`afk_clicker.py:1554`, discussed at length at `afk_clicker.py:2304-2325`) services *other queued
idle jobs* mid-rebuild. Per Tcl semantics, `update idletasks` only drains idle events, not the
5000ms timer event `_poll_games` uses — so this mechanism, real as it is (it's what Defect 1 in
`docs/history/ac-17-f3a-test-review.md` exploited), cannot itself fire the periodic poll timer.
Ruled out as the direct cause of *this* flake; not otherwise touched by this fix.

**H3 (considered, ruled out).** GC-driven off-main-thread finalization
(`docs/history/ac-27-r3-implementation.md`'s mechanism). That bug manifests as a fatal Tcl abort
or a benign `RuntimeError`, not a clean `assertEqual` set-mismatch with well-formed data — doesn't
match the observed symptom. Not revisited here.

`docs/history/ac-30-implementation.md`'s own "Known limitations" section explicitly named this
possibility in advance: *"If G#30 recurs after this fix on a future CI run, that would falsify
this root cause and point at the `update_idletasks()` alternative instead."* G#39 is that
recurrence; per H2 above, `update_idletasks()` is not actually implicated — the real gap is the
periodic timer/in-flight-thread exposure (H1), a narrower and more specific finding than the
doc's own speculative fallback.

## Evidence plan (macOS CI, one push)

**Locally verifiable now (Linux/Xvfb), before spending a CI push:** the general vulnerability
class — "any `_mark_running` call landing between the manual queue-put and the drain wins,
regardless of source" — can be demonstrated deterministically in a throwaway scratchpad copy by
starting a plain background thread inside the test that calls
`self.ui._ui(self.ui._mark_running, {"other"})` after a short `time.sleep()` timed between the two
`_ui()` calls, with `_poll_games` still stubbed as today. This proves the test's exposure is to
*any* late writer, not specifically to `_poll_games`'s own rebuild-time call (already proven by
PR #58) — it does **not** prove H1's specific claim that the periodic timer is the real-world
trigger on macOS, since that requires genuine `osascript` timing variance this box cannot produce.

**What only macOS CI can confirm, and how to get it in one push:** open a **draft PR** from a new
throwaway branch cut from `main` (not from `hotfix/ac-39/...` itself, so the diagnostic commit
never has to be untangled from the real fix's history) containing exactly one temporary,
clearly-labeled commit that:
- Adds `print(time.monotonic(), threading.current_thread().name, ...)` diagnostics, test-file-only
  (`tests/test_ui.py`), at: `_poll_games` entry (tag initial vs. periodic via a counter),
  `_mark_running` entry (value + thread name), `settle()`'s return, and the test method's own
  three key points (manual queue-put, `_rebuild_ui()` return, final `_drain_ui()`/assertion).
- Loops just
  `QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`
  30-50x in a temporary CI step, `|| true` per iteration so one failure doesn't abort the loop and
  lose later iterations' logs.

Rationale for a **draft PR**, not `workflow_dispatch`: triggering a new Actions run via
`workflow_dispatch` (API or `gh workflow run`) requires `actions:write`, the same permission this
token already lacks for re-runs. `pull_request` does not — opening a draft PR is a plain git/PR
operation and reliably triggers `ci.yml`'s existing macOS leg with no workflow edits needed.
Inspect the macOS job's log for the diagnostic output (specifically: did a second `_poll_games`
invocation fire inside `setUp()`, and did any `_mark_running` call land with a thread name other
than the main thread's, after the manual queue-put print but before the assertion print). Once
read, close the draft PR **without merging** and delete the branch — the instrumentation must
never reach `main` or the `hotfix/ac-39` branch.

## Proposed approach

Assuming H1 confirms (or absent contrary CI evidence — the code-level case is already strong):
fix `tests/test_ui.py`'s one test method to neutralize a scan that may already be in flight from
`setUp()`, not just future ones:

1. Before the manual queue-put, cancel the periodic timer if one is armed:
   `job = self.ui._timers.pop("poll_games", None); job and self.ui.root.after_cancel(job)`
   (mirrors `on_close()`'s own cancellation pattern, `afk_clicker.py:3446-3450`) — stops any
   *future* reschedule from firing during the test, closing the gap the existing
   `self.ui._poll_games = lambda: None` stub cannot reach.
2. Join `self.ui._poll_thread` if it's alive, bounded (`timeout=2.0`, matching `on_close()`'s own
   convention at `afk_clicker.py:3479-3484`) — guarantees any scan already started by `setUp()`
   has actually finished (not merely "started long enough ago that it's probably done") before
   the manual queue-put.
3. Drain once more after that join (`self.ui._drain_ui()`), discarding whatever the joined scan
   put on the queue, so a real, harmless landing from *before* the test's own critical section
   can't be mistaken for — or collide with — the test's manually-queued value.
4. Only then do the existing `self.ui._ui(self.ui._mark_running, target)` /
   `self.ui._rebuild_ui()` / `self.ui._drain_ui()` / assertion sequence, with the existing
   `self.ui._poll_games = lambda: None` stub still in place for the duration (still needed to
   block the rebuild's own rescan, per PR #58).
5. Update the test's docstring/inline comment to record this round's finding (the current comment
   at `tests/test_ui.py:3801-3821` already documents Round 1 and Round 2; this becomes "Round 3 /
   G#39").

This is a **test-only fix**, same category as PR #58: the periodic re-poll and the
last-write-wins `_mark_running` semantics are correct, intended production behavior (a live
"what's running now" indicator should reflect the latest real scan) — the bug is entirely in this
one test's continued exposure to a scan it has no business waiting on, not in `afk_clicker.py`.

**Sabotage acceptance test (must run before considering this closed):** in a throwaway copy,
reintroduce the historical bug by adding `self._ui_queue = queue.SimpleQueue()` back into
`_rebuild_ui()`, right after `self._timers = {}` at `afk_clicker.py:2367` (same spot `ac-30`'s own
sabotage used). Run the fixed test 3-5x: it must fail every time with the same
`AssertionError: ... 'minecraft' ...` message, proving the fix still catches a genuinely dropped
queue entry and doesn't just make a coincidentally-matching value structurally guaranteed. Then
restore `afk_clicker.py` (`git checkout --`) and confirm `git diff` is clean before deleting the
scratch copy.

## Affected areas
- `tests/test_ui.py` — one test method
  (`QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`)
  plus its docstring comment. No production code (`afk_clicker.py`) change expected, pending the
  evidence plan not overturning H1.
- `backlog.md` — the existing G#39/GH#69 entry (lines ~102-115) should be updated to closed/fixed
  with the actual mechanism once the fix lands (matches how G#30 was closed there).
- A throwaway diagnostic branch + draft PR (never merged) for the evidence-gathering step only —
  no lasting footprint on `main` or `hotfix/ac-39/...`.

## Edge cases
- **Scan A itself is the one still in flight** (not just a periodic-timer-triggered scan B) — the
  join in step 2 above covers this too; the fix doesn't care which invocation is still running,
  only that none is by the time the manual queue-put happens.
- **`self.ui._poll_thread` doesn't exist yet** — can't happen for this test class: `setUp()`
  always runs `__init__` → `_build_ui()`'s tail → `_poll_games()` once, so the attribute is always
  set by the time the test body runs; still guard with `getattr(self.ui, "_poll_thread", None)`
  defensively rather than assuming.
- **The bounded 2.0s join times out** (the documented ~1-in-a-couple-hundred stuck-`Display()`
  case) — proceed anyway, same as `on_close()` does; this fix reduces the exposure window from
  "unbounded" to "at most 2s of continued real risk," it does not (and per the existing stuck-scan
  precedent, cannot) eliminate it outright.
- **Windows/Linux CI legs** — `detect_running`'s path differs (Xlib on Linux, presumably
  `EnumWindows` or similar on Windows), but the exploited mechanism (a real scan racing a queued
  fake one) is platform-agnostic in principle; this fix removes the exposure on every platform,
  not just macOS, even though only macOS has ever actually hit the 5s window.

## Acceptance criteria
- [ ] Given the fixed test, when run 20x back-to-back on Linux/Xvfb (this box), then it passes
      every time (no regression vs. today's local-passing baseline).
- [ ] Given the sabotage (`_ui_queue` swap reintroduced in `_rebuild_ui()`), when the fixed test is
      run 3-5x, then it fails every time with the original `'minecraft'`-missing assertion —
      proving the fix does not blind the guard.
- [ ] Given the draft-PR diagnostic run on macOS CI, when its log is inspected, then it either (a)
      shows a second `_poll_games`/`_mark_running` invocation landing inside the exposure window
      confirming H1, or (b) shows no such invocation, in which case H1 is not confirmed and the fix
      direction must be revisited before merging (do not ship the test change speculatively against
      contrary evidence).
- [ ] The full existing suite still passes on Linux/Xvfb after the change (no regression to any
      other test in `QueuedNonResyncedUpdatesSurviveARebuild` or elsewhere).
- [ ] No instrumentation/diagnostic code reaches `main` or the `hotfix/ac-39/...` branch — the
      draft PR is closed unmerged and its branch deleted once its log has been read.

## Open questions
None that block starting: the diagnostic-branch-off-`main` approach and the draft-PR (not
`workflow_dispatch`) choice are both proceeding under a stated assumption (see "Evidence plan")
rather than sitting open — reasonable defaults, adjustable if the developer/reviewer stage hits
something contrary once macOS CI evidence is in hand.

## Risk / rollback notes
Test-only change; if the join/cancel sequence itself introduces a new problem (e.g. joining a
thread that's genuinely stuck past 2.0s on a slow runner, delaying the test slightly), it's a pure
revert of the one test method — `afk_clicker.py` is untouched under the current hypothesis, so
there's no production rollback surface. If macOS CI evidence contradicts H1, the fallback is to
keep investigating rather than ship this specific fix (see acceptance criterion 3b) — don't merge
a test change whose own justifying evidence turned out negative.

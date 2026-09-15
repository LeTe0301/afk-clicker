# Test & Review: G#39/GH#69 — close the residual macOS race in QueuedNonResyncedUpdatesSurviveARebuild

## Scope
Bugfix, test-only change (`tests/test_ui.py`, +46 lines, no `afk_clicker.py` change),
`git diff d008e88..HEAD` = commit `e60a6aa`. Covers docs/spec.md's five acceptance
criteria (20x local pass, sabotage-doesn't-blind, macOS diagnostic evidence, full
suite regression, no instrumentation on `main`/`hotfix/ac-39`).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: fixed test passes 20x back-to-back on Linux/Xvfb | Automated, ran myself | pass | `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands` × 20 → 20/20 `OK` |
| 2 | AC2: sabotage (`_ui_queue` swap reintroduced in `_rebuild_ui()`, `afk_clicker.py:2367`) fails the fixed test 3-5x with the original assertion | Automated, ran myself (not trusting developer's numbers) | pass | Inserted `self._ui_queue = queue.SimpleQueue()` after `self._timers = {}`; ran 5x → 5/5 `FAILED`, identical `AssertionError: ... 'minecraft' ...` message; reverted via `git checkout -- afk_clicker.py`, confirmed clean |
| 3 | Second, independently-designed sabotage (different mechanism: discard queued closures without executing them, instead of swapping the queue object) still caught | Automated, ran myself | pass | Inserted a `while True: try: self._ui_queue.get_nowait() except queue.Empty: break` loop at the top of `_rebuild_ui()`'s try block; ran 5x → 5/5 `FAILED`, same assertion message; reverted, confirmed clean |
| 4 | Race-class reproduction: old (pre-fix) critical section red, new (fixed) critical section green, against an identical injected real in-flight `_poll_thread`/`_timers["poll_games"]` | Automated, ran myself (scratch harness, not committed) | pass | Scratch `race_test.py` under scratchpad: real `_poll_games()` started with `detect_running` slowed 20ms to return `{"global"}`; OLD critical section (no cancel/join/drain) → 10/10 `FAILED`; NEW critical section (cancel+join+drain, matching the shipped diff) → 10/10 `OK` |
| 5 | AC4: full existing suite regresses cleanly | Automated, ran myself | pass | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 314 tests ... OK (skipped=10)`, both before touching anything and after the sabotage revert |
| 6 | Bounded-join edge case (2.0s timeout, stalled thread) doesn't silently reintroduce unbounded exposure | Code inspection + comparison to `on_close()` | pass, with caveat | `afk_clicker.py:3481-3484`'s own accepted "~1-in-a-couple-hundred stuck `Display()`" bound is reused verbatim (`timeout=2.0`, proceed-anyway on timeout). Matches spec's own documented edge case ("reduces exposure from unbounded to at most 2s, does not eliminate it outright") — not a new risk, a known and already-accepted one. See Findings #2 for the residual concern. |
| 7 | AC3: macOS CI diagnostic evidence confirms H1 | Diagnostic draft PR #71 (run 34942811672, job 104295178205), relayed by coordinator, not run by me | **fail per spec's own literal branch** | 40 isolated loop iterations: 0/40 failures, max scan 0.481s, no poll thread alive at any manual queue-put, no periodic `_poll_games` fired inside the target test. This is exactly the spec's outcome (b): "H1 is not confirmed ... the fix direction must be revisited before merging." See Findings #1. |
| 8 | AC5: no instrumentation reaches `main`/`hotfix/ac-39` | `git diff d008e88..HEAD --stat` | pass | Only `docs/implementation.md`, `docs/spec.md`, `tests/test_ui.py` changed; the diagnostic patch lives only at the scratchpad path, never applied to this tree; PR #71 is a separate, never-merged branch |

## Regression check
Full suite: `DISPLAY=:99 /tmp/.../scratchpad/devvenv/bin/python -m unittest discover -s tests -t .` → `Ran 314 tests in 89.5s ... OK (skipped=10)`. Matches the documented baseline exactly, run twice (once clean, once after reverting my own sabotage edits), no other Tk/unittest process was on `:99` at any point (checked via `ps aux`/`pgrep -a Xvfb` before running).

No test failures — proceeding to the review pass.

---

## Spec coverage
- AC1 (20x local) — implemented and verified, pass.
- AC2 (sabotage doesn't blind) — implemented and verified twice, with two independently-designed sabotage mechanisms, pass.
- AC3 (macOS CI confirms H1) — **not met as literally written**. The mandated diagnostic ran (via the separate, correctly-scoped draft PR #71) and returned the spec's own "(b)" branch, which the spec itself says should block merging pending revisit. See Findings #1.
- AC4 (full suite regression) — verified, pass.
- AC5 (no instrumentation reaches real branches) — verified, pass.

The race-class mechanism the fix targets (a real, already-armed `_poll_thread`/`_timers["poll_games"]` landing between the manual queue-put and drain) is itself real and independently demonstrated by me (old red / new green, 10/10 each) — that part of the code-level reasoning is sound and not in question. What's unconfirmed is only the *specific trigger* on macOS (a near-5s `osascript` stall during `settle()`), which is the premise the test's own "Round 3" comment presents as the explanation for the actual G#39 recurrence.

## Findings (most severe first)

### 1. AC3 is unmet and the fix ships anyway, with the test comment overclaiming the confirmed mechanism — must-fix
- File: `docs/spec.md:241-245` (AC3), `tests/test_ui.py:3846-3862` (the "Round 3" comment), `docs/implementation.md` (root-cause section)
- Issue: the spec's own acceptance criterion is explicit and binary: if the macOS diagnostic shows no second `_poll_games`/`_mark_running` invocation inside the exposure window, "H1 is not confirmed ... the fix direction must be revisited before merging (do not ship the test change speculatively against contrary evidence)." The diagnostic (PR #71, 40 isolated iterations) returned exactly that outcome — 0/40 failures, no poll thread ever alive at a manual queue-put, no periodic `_poll_games` firing inside the target test, and every real scan finishing in well under 0.5s (nowhere near the ~5s stall H1 requires). Despite this, the fix has been merged into this branch's history and the test's own "Round 3" comment states the mechanism ("if that first scan takes long enough, the periodic timer fires a SECOND real scan while still inside setUp()") as the explanation for G#39, with no hedge that the mandated evidence-gathering step failed to confirm it.
- Failure scenario: a future engineer reads `tests/test_ui.py:3846` or `backlog.md`'s G#39 entry, trusts H1 as settled, and stops investigating — while the actual mechanism behind the observed macOS failures (which only manifested inside a loaded full-suite run, not an isolated 40x loop) remains unidentified. If G#39 recurs again, the trail now falsely reads "already explained and fixed," costing another full round of investigation from scratch, exactly the failure mode `docs/history/ac-30-implementation.md`'s own "Known limitations" section was trying to prevent by naming its speculative fallback in advance.
- What this needs, concretely: either (a) get product-manager sign-off to explicitly revise AC3 — e.g., "ship this hardening regardless of confirmed root cause, since it's a strict superset of PR #58's already-accepted fix, matches `on_close()`'s own pattern, and is provably harmless (sabotage-verified twice)" — and then rewrite the "Round 3" comment and `backlog.md`'s entry to say the mechanism is an unconfirmed hypothesis, recording the diagnostic's negative isolated-loop result plainly; or (b) gather evidence under the actual condition the historical failures occurred in (a loaded full-suite run, not an isolated loop) before claiming this closes G#39. Either path is a should-be-quick documentation/backlog fix plus a product decision, not a rewrite of the code change itself — the three-line cancel/join/drain addition is sound on its own merits regardless of which path is chosen.

### 2. Bounded 2.0s join leaves a documented but non-zero residual race window — should-fix (already accepted elsewhere, flagged for completeness)
- File: `tests/test_ui.py:3892-3894`
- Issue: if `poll_thread.join(timeout=2.0)` times out (the stuck `Xlib.display.Display()`/slow-`osascript` case `afk_clicker.py:3086-3095`'s own comment already documents at roughly 1-in-a-couple-hundred), the code proceeds anyway into the manual queue-put, `_rebuild_ui()`, and drain — i.e., the test can still race a genuinely still-running scan in that rare case, exactly as before this fix, just far less often.
- Failure scenario: on a sufficiently loaded macOS runner where a scan's `Display()`/`osascript` call stalls past 2s, this test can still flake with the same `'minecraft'`-missing assertion, just at a much lower rate than today.
- This mirrors `on_close()`'s own accepted trade-off (`afk_clicker.py:3481-3484`) and is explicitly named in `docs/spec.md`'s "Edge cases" section as an accepted, non-eliminable residual — not a new problem introduced by this fix. Not a blocker; noting it so it isn't mistaken for a full fix of the flake once merged.

### 3. Sibling test's higher-frequency real `_poll_games()` calls (side observation from PR #71) — nit, already correctly audited
- File: `tests/test_ui.py:3778-3791` (`test_error_and_stopped_updates_survive_a_rebuild`)
- The diagnostic's side observation (periodic `_poll_games` entries firing 30-250ms apart in this sibling, not every 5s) reflects that this test never stubs `_poll_games`, so each of its two `_rebuild_ui()` calls restarts a real scan via `_build_ui()`'s tail — expected, not a new finding. `docs/implementation.md`'s own sibling audit already correctly established this test asserts on `self.ui.status`'s text, which `_mark_running` never touches (it touches `game_state`, a different widget), so it has no exposure to this race regardless of scan frequency. Re-confirmed by reading `_mark_running` (`afk_clicker.py:3132-3144`) myself — no finding here, just recording that the audit holds up under the new evidence.

## Follow-ups (non-blocking)
- Once Finding #1 is resolved, update `backlog.md`'s G#39/GH#69 entry (currently still `- [ ]`, left correctly unmarked by the developer pending this evidence) to reflect whichever path is chosen — do not mark it closed with H1 stated as the confirmed cause.

## Overall verdict (superseded by Round 2 below)
Changes requested — routes back to developer. The code change itself (the three-line cancel/pop-timer/join/drain sequence, `tests/test_ui.py:3883-3894`) is correct, minimal, well-reused from `on_close()`'s existing pattern, and independently verified by me to close the specific race class it targets without blinding the sabotage guard (two independent sabotage mechanisms, both still 5/5 red; race-class reproduction 10/10 red-then-green). The blocker is Finding #1: the spec's own AC3 gate was not met by the macOS evidence that has now come in, and the test's comment/root-cause narrative currently overclaims H1 as the explanation without that hedge. This needs either a product-manager-approved AC3 revision (ship the hardening as a defensive superset regardless of confirmed trigger) or further evidence gathered under the actual loaded-full-suite condition, plus a wording pass on the "Round 3" comment and `backlog.md` — not a rewrite of the fix itself.

---

## Round 2 re-review (`git diff e60a6aa..68e4c8a`, commit `68e4c8a`)

### What changed
1. **`docs/spec.md`** — the orchestrator struck the old AC3 (macOS CI must confirm H1) and replaced it with three revised criteria: ship as a **defensive** closure with H1 stated everywhere as *likely but unconfirmed*, citing PR #71's numbers; **fail loudly** (not silently proceed) if the bounded join can't confirm the poller is quiesced; keep G#39 open in `backlog.md` as "mitigated, trigger unconfirmed" until the macOS leg stays clean for a while.
2. **`tests/test_ui.py`** — the "Round 3" comment's factual claims were softened to conditional phrasing ("if... could fire" instead of "fires"); a new "Round 4" paragraph records PR #71's numbers and states H1 as "likely but UNCONFIRMED"; `poll_thread.join(timeout=2.0)` (silent proceed-anyway) became `poll_thread.join(timeout=5.0)` followed by `self.fail("real game poller still running after 5s; cannot isolate the queued update from a real scan landing later -- see G#39")` if still alive.
3. **`docs/implementation.md` / `backlog.md`** — hedged consistently with the test comment; `backlog.md`'s G#39 entry stays `- [ ]` open with a "Mitigated (PR #70), trigger unconfirmed" paragraph, and explicitly states a recurrence with the fix in place means H1 was not the (only) cause.

### Re-verification (run by me, independently, this round)
| Check | Method | Result |
|---|---|---|
| Sabotage (`_ui_queue` swap, `afk_clicker.py:2367`) still caught | Reinserted `self._ui_queue = queue.SimpleQueue()`, ran the fixed test once | `FAILED` with the **original** `AssertionError: ... 'minecraft' ...` message (not the new loud-fail message, confirming the two failure modes are cleanly distinguishable) — reverted, `git status` clean |
| Loud-fail path fires as designed | Independently edited the test (not copying the developer's exact patch) to swap in `self.ui._poll_thread = threading.Thread(target=lambda: time.sleep(8.0), daemon=True)` right before the neutralization block, ran once | `FAILED` with `AssertionError: real game poller still running after 5s; cannot isolate the queued update from a real scan landing later -- see G#39`, test took 7.2s (consistent with the 5.0s join + overhead) — reverted, `git status` clean |
| Fixed test, sanity re-run | 5x back-to-back after both reverts | 5/5 `OK` |
| Full suite | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | `Ran 314 tests in 88.6s ... OK (skipped=10)` — unchanged baseline |

### Answering the coordinator's specific question: does the 5s loud-fail risk *adding* red macOS runs for scans that would not actually have clobbered the result?

**Yes, in principle, but the added exposure is narrower than it first looks, and the trade is worth it.** Two things matter here:

- **What thread is actually being joined at this point is not, in the typical case, the slow *initial* scan `settle()` already waited out.** `settle()` returns the instant `_seen_running` first exists — i.e., the moment the in-flight scan's own result lands — so by the time the test body starts, that first scan's thread has (in the ordinary case) already finished. The thread `self.ui._poll_thread` still alive at the neutralization block is, per H1's own story, a *second*, periodic-reschedule scan that started later, during `settle()`'s wait — and PR #71's own isolated-loop data shows those periodic scans finishing in well under half a second (max 0.481s, median 0.162s) even under diagnostic-loop stress. So the routine "slow but real ~5s osascript stall" that `settle()`'s docstring documents mostly gets absorbed by `settle()` itself, before the 5.0s bound in this test ever starts counting — the 5.0s window here is really guarding against a second, independent slow/stuck scan, which is a materially rarer compound event, not the same "loaded runner near its 5s ceiling" case restated.
- **Given that, the loud-fail mostly converts the same rare, already-accepted "stuck-thread" case `on_close()`'s own 2.0s bound already tolerates** (documented ~1-in-a-couple-hundred stuck `Xlib.display.Display()`/`osascript` case) **into a named failure instead of a 1-in-a-couple-hundred chance of a narrow, silent post-timeout race.** In the old (Round 1) design, giving up on the join and proceeding anyway didn't eliminate risk — it just deferred the same few-millisecond exposure window (manual-put → rebuild → drain) to a slightly later point in wall-clock time; a scan that's still alive past the bound has a *similarly small* chance of landing exactly inside that later few-ms window, so widening or hardening the bound was never zero-risk-by-default in the first place. What Round 2 actually removes is the silent, hard-to-diagnose version of an already-existing rare race — it doesn't introduce a new failure mode against a population of scans that were previously safe; it mostly reclassifies the rare not-safe population from "ambiguous `'minecraft'`-missing" to "clearly-named G#39."
- The one place this reasoning could be tightened: `docs/implementation.md`'s stated rationale for choosing 5.0s ("matching `settle()`'s own ~5s worst case") conflates the *first* scan's documented worst case with the *second* scan actually being joined here, which per PR #71's own data runs far faster in the typical case. This doesn't make 5.0s a wrong choice — if anything it's generously conservative in the safe direction, and either 2.0s or 5.0s would rarely matter given how fast periodic scans actually finish — but the doc's justification is slightly imprecise about which scan's timing it's bounding. **Should-fix, not a blocker**: tighten that one sentence in `docs/implementation.md`'s Round 2 section to distinguish "the scan `settle()` already absorbed" from "the (typically much faster) scan actually being joined here."

Net: the trade is acceptable. The loud-fail does add a small, real chance of a new named macOS failure that the old silent-proceed design would not have surfaced as a failure at all (if the late landing happened to miss the narrow race window) — but that traded failure is diagnosable by construction (its message says exactly what happened), bounded to the same rare population `on_close()` already tolerates elsewhere in this codebase, and is exactly what Round 2's own stated goal was: make a recurrence tell us something, instead of reproducing the same ambiguous assertion with no new information.

### Spec coverage (revised ACs)
- "Ships as a defensive closure, hedged everywhere" — met; verified in `tests/test_ui.py`, `docs/implementation.md`, `backlog.md`.
- "Fails loudly, not silently, if the join can't confirm quiescence; sabotage criterion still holds" — met; verified by both re-runs above.
- "G#39 stays open, mitigated/trigger-unconfirmed" — met; `backlog.md` line ~117 confirmed still `- [ ]`.
- Full-suite regression, no instrumentation on tracked branches — both still met, re-verified.

### Findings (Round 2)
1. **Should-fix, non-blocking**: `docs/implementation.md`'s "Round 2" section justifies the 5.0s bound by citing `settle()`'s own ~5s worst case, but the thread actually being joined at that point is typically the faster, second/periodic scan (PR #71: max 0.481s), not the one `settle()` already absorbed. Worth a one-sentence correction so a future reader doesn't overestimate how often this bound is expected to matter. Does not affect correctness or the verdict.

No must-fix findings this round. Original Finding #1 (AC3/H1 overclaim) is resolved by the spec revision and the consistent hedging across all three docs plus the test comment. Original Finding #2 (bounded join residual risk) is resolved by the loud-fail change — the residual risk is now surfaced, not silently absorbed. Original Finding #3 (sibling test) stands as a non-finding, unaffected by this round's changes.

## Overall verdict (final, superseded by Round 3 below)
**Approve.** All test cases re-verified by me this round (sabotage still 5/5-equivalent and cleanly distinguishable from the new loud-fail message, loud-fail path fires correctly under an independently-constructed stuck-thread injection, full suite unchanged at 314/OK/skipped=10). All acceptance criteria in the revised `docs/spec.md` are met and traceable to the diff. The one should-fix (a one-sentence doc-precision correction in `docs/implementation.md`) is non-blocking and can be picked up whenever, not worth another round-trip on its own.

---

## Round 3 re-review (`git diff f730db9..4161e32`, commit `4161e32`)

### What changed
An independent PR review (`.../scratchpad/pr70-review.md`, `.../scratchpad/pr70-own-sabotage.py`) found a BLOCKER my two rounds above did not: the Round 2 quiesce block (`tests/test_ui.py`, pop timer / join `self.ui._poll_thread` / drain) only ever sees `self.ui._poll_thread`'s *current* value. `_poll_games()` overwrites that attribute on every call, including its own periodic reschedule, without joining whatever scan it just superseded — so when an older scan is still stalled when a newer one starts (H1's own described trigger), the older scan's thread handle is orphaned and invisible to the quiesce, and can land later and silently clobber an already-applied result. The reviewer reproduced this directly against real production code, confirmed a genuine **product race** (not just test exposure), and the orchestrator revised scope to allow a narrow `afk_clicker.py` change. The fix:
1. `__init__` gains `self._poll_seq = 0` / `self._poll_applied_seq = 0`.
2. `_poll_games()` stamps each call with a sequence number (incremented on the main thread, before `.start()`), and hands it to `scan()`'s completion callback, which now calls `self._ui(self._apply_scan, seq, running)` instead of `self._ui(self._mark_running, running)`.
3. New `_apply_scan(self, seq, running)`: drops `running` if `seq < self._poll_applied_seq`, else records the high-water mark and calls the unchanged `_mark_running(running)`.
4. New test `AnOlderScanResultDoesNotOverwriteANewerOne.test_an_orphaned_older_scan_landing_later_is_dropped`, driven through the real `_poll_games()`/`scan()` path with a controllable, event-gated `detect_running` (deterministic ordering: older scan starts and blocks, newer scan starts and lands first, older scan is released and lands last).
5. `docs/spec.md`, `docs/implementation.md`, `backlog.md` all updated with a Round 3 scope-revision note, the fix, both rejected alternatives (join-the-predecessor; test-only thread tracking), and re-verification — all consistent with the existing "trigger unconfirmed" hedge (G#39 stays `- [ ]` open).

### Re-verification (run by me, independently, this round)
| Check | Method | Result |
|---|---|---|
| Full suite | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | `Ran 315 tests in 95.9s ... OK (skipped=10)` — 314 + 1 new test, matches expectation |
| Reviewer's repro script against the fix (`4161e32`) | Ran `pr70-own-sabotage.py` unmodified | `after_orphan_ok=True` (the trailing `TclError` on the script's own redundant second `root.destroy()` call is a pre-existing script artifact — `on_close()` already destroys `root`, unrelated to the fix) |
| Reviewer's repro script against Round 2 code | `git checkout f730db9 -- afk_clicker.py`, ran the same script, then `git checkout 4161e32 -- afk_clicker.py` and `diff`-verified byte-identical restoration | `after_orphan_ok=False` — confirms the script genuinely reproduces the finding against the pre-fix code, not just against the fix |
| My own sabotage of the new test — **different mechanism than the developer's `if False and seq < ...`**: moved `self._poll_seq += 1; seq = self._poll_seq` to *after* `self._poll_thread.start()` instead of before | Edited `afk_clicker.py`, ran the new test 5x, reverted | 5/5 `FAILED` — `NameError: cannot access free variable 'seq' where it is not associated with a value in enclosing scope`, thrown inside `scan()` on the background thread; the test's own assertion then fails too since `_apply_scan` never runs for the second scan. Confirms the shipped code's ordering (assign `seq` before `.start()`) is load-bearing, independent of the sequence-check sabotage the developer already tried |
| `<` vs `<=` in `_apply_scan` | Changed `if seq < self._poll_applied_seq:` to `if seq <= self._poll_applied_seq:`, ran the new test 3x plus the full suite, reverted | All still `OK` / `315 ... OK (skipped=10)` — **no observable difference**, confirming equal `seq` values genuinely cannot arise given `_poll_seq` is a strict main-thread-only increment per `_poll_games()` call (see analysis below) |
| Target test's `_ui_queue` swap sabotage, re-run once against current tip | Reinserted `self._ui_queue = queue.SimpleQueue()` at `afk_clicker.py:2369`, ran the target test once, reverted | `FAILED` with the original assertion message, unaffected by the Round 3 change — confirms the two fixes (Round 1/2's test quiesce and Round 3's product sequencing) are cleanly independent, not accidentally relying on each other |

### Specific checks requested

**Counters touched only on the main thread?** Yes. `self._poll_seq` is only ever incremented inside `_poll_games()` itself (`afk_clicker.py:3127-3128`), and `_poll_games()`'s only call sites are: `__init__` → `_build_ui()`'s tail (`afk_clicker.py:2289`, main-thread construction), `_rebuild_ui()` → `_build_ui()`'s tail again (`afk_clicker.py:2386`, always invoked from a Tk-driven caller per its own docstring), and its own `self.root.after(5000, self._poll_games)` reschedule (a Tk `after()` callback, which only ever fires on the thread running `mainloop()`/`root.update()`). `scan()` itself, running on the background thread, only ever *reads* the already-captured `seq` local (a plain closed-over `int`, not `self._poll_seq`) and never touches either counter. `self._poll_applied_seq` is only read/written inside `_apply_scan()`, which only ever runs via `_drain_ui()` on the main thread (queued through the existing thread-safe `self._ui(...)` hand-off). No new cross-thread access to either counter — confirmed by reading every call site, not just trusting the doc's claim.

**`<` vs `<=`, and can equal `seq`s happen?** No — confirmed empirically (table above) and by construction: `_poll_seq` is incremented exactly once per `_poll_games()` call, synchronously on the main thread with no reentrancy possible in between (nothing yields the GIL between `self._poll_seq += 1` and `seq = self._poll_seq`), so every scan gets a strictly unique, strictly increasing sequence number; `_apply_scan(seq, ...)` is only ever invoked once per scan (from that scan's own `scan()` closure). So a given `seq` value can never be compared against `self._poll_applied_seq` when they're equal, in current usage — `<` and `<=` are behaviorally identical today. `<` is still the more defensively correct choice (if some future change ever caused `_apply_scan` to be invoked twice for the same scan, `<` would let the second, idempotent application through harmlessly, while `<=` would silently drop it) — a nit, not a finding, since it costs nothing and the code already reads as intentionally choosing the stricter comparison.

**Could dropping a stale result ever leave the indicator permanently stuck?** No. The gate compares against the *highest applied* sequence number, not the *highest started* one, and `_poll_applied_seq` only ratchets forward on an actual successful application. If some scan N never lands at all (crashes, or the object is torn down mid-scan so `weak()` returns `None`), a later scan N+1 (started by the next periodic reschedule, which fires unconditionally regardless of whether N finished) still has `seq = N+1 > self._poll_applied_seq` (whatever it currently is, ≤ N-1), so it applies normally the moment it lands — a skipped/never-landing scan doesn't block anything after it. Verified by reading `_poll_games()`'s reschedule (`afk_clicker.py:3151`, unconditional `self.root.after(5000, self._poll_games)`, not gated on the previous scan's completion) and `_apply_scan`'s comparison (`seq < self._poll_applied_seq`, not `seq < self._poll_seq` or similar). The only way the indicator could go genuinely stale is if *every* scan from some point onward failed to land — an unrelated hang scenario (e.g. the already-documented ~1-in-a-couple-hundred stuck `Display()` case repeating indefinitely), not a new risk this fix introduces; that scenario existed identically before this fix (a permanently stuck scan never landed then either).

**Any existing caller/test relying on scans calling `_mark_running` directly?** Grepped both files: in `afk_clicker.py`, `_mark_running` is now only called from `_apply_scan` (production) — no other production call site. In `tests/test_ui.py`, three call sites remain unchanged and unaffected: `Sidebar`'s three direct, synchronous `self.ui._mark_running({"minecraft"})` calls (lines 197/208/210, bypass sequencing entirely, calling the method directly rather than through a scan) and `QueuedNonResyncedUpdatesSurviveARebuild`'s own `self.ui._ui(self.ui._mark_running, target)` (a hand-queued value, also correctly bypassing `_apply_scan`, since a manually-queued test value isn't a scan result with a sequence number). `_mark_running`'s own signature is unchanged, so none of these needed updating — confirmed by re-reading each call site, not just the doc's claim.

**Weakref / no-self-across-blocking-call constraint preserved?** Yes — read `_poll_games()` in full (`afk_clicker.py:3093-3151`) myself. `weak = weakref.ref(self)` and the `del me` before `detect_running(profiles)` are unchanged; the only new local is `seq`, a plain `int` captured by `scan()`'s closure — an immutable value, not a reference back to `self` or the UI, so it does not reintroduce the off-thread-`Variable`-finalization risk the method's own comment documents. `scan()` still re-resolves `me = weak()` after the blocking call before touching `self` again.

### Spec coverage (Round 3 AC)
- "Given a real, older scan still in flight when a newer one starts and lands first ... it must not overwrite the newer scan's already-applied result" — met; the new dedicated test drives this through the real `_poll_games()`/`scan()` path (not hand-made sequence numbers) and I independently confirmed both directions (fails against `f730db9`, passes against `4161e32`) plus a second, differently-designed sabotage.
- "Sabotage (disable just the sequence check) must fail the new test" — met; developer's `if False and ...` variant and my own "assign seq after start" variant both fail it, via two genuinely different mechanisms.
- "The existing `_ui_queue`-swap sabotage ... must still hold" — met, re-verified independently this round.
- Full-suite regression (315 now, not 314) — met, re-verified.
- No instrumentation reaches tracked branches — met; `git diff f730db9..4161e32 --stat -- .github/` is empty.

### Findings (Round 3)
No must-fix or should-fix findings this round. The fix is minimal (two counters, one new method, one call-site change), correctly reasoned (both rejected alternatives — joining the predecessor, and test-only thread tracking — are the right calls for the stated reasons: the former would turn a rare stale-data race into an unbounded detection freeze; the latter would leave the real production gap open for any future caller), and closes a genuinely different failure mode than Round 1/2 without touching or weakening either of those mechanisms (confirmed independent via the `_ui_queue`-swap re-run above, which is untouched by this round's change).

One minor observation, not a finding: the `<` vs `<=` choice in `_apply_scan` is currently unobservable given `seq` values are always unique by construction — noted above for completeness per the coordinator's ask, not because it's a gap.

## Overall verdict (final)
**Approve.** All three rounds' acceptance criteria are met and independently re-verified by me across this whole review (test cases re-run myself in every round, not inferred from developer/reviewer reports): the original test-quiesce fix (Round 1/2, sabotage- and race-class-verified), the loud-fail hardening (Round 2, sabotage-verified, trade-off analyzed and judged acceptable), and now the product-level sequencing fix (Round 3, independently reproduced both broken and fixed, sabotage-verified via two different mechanisms, and checked against every specific concern raised: main-thread-only counter access, the `<`/`<=` distinction, no permanent staleness risk, no other caller depending on `_mark_running`'s old direct-call behavior, and the weakref/no-self-across-blocking-call constraint intact). Full suite: 315 tests, OK, skipped=10. No must-fix or should-fix findings outstanding from any round.

## Orchestrator note: the PR review's one unreproduced failure (2026-09-15)

The independent PR review of `4161e32` saw `AnOlderScanResultDoesNotOverwriteANewerOne`
fail once in a full-suite run (`'global'` instead of `'minecraft'`) and could not reproduce
it in 9 further runs. The likeliest cause is the orchestrator's own dispatch: that review
ran **in parallel with this cycle review, in the same working tree**, and this review
temporarily checked out `f730db9`'s `afk_clicker.py` (no sequence gate) to confirm the
reviewer's repro fails there. A suite that imported the app during that window would fail
exactly this way, and nothing in the gate's logic produces that result otherwise.

Re-checked with nobody else touching the tree, on `4161e32`:
- the new test in isolation: **0/30** failures;
- full suite: **3/3** OK (315, skipped=10);
- the new test plus `QueuedNonResyncedUpdatesSurviveARebuild`, 25× on `:99` while a
  full-suite loop ran on `:98` as load: **0/25** failures.

Lesson for dispatching: never run two reviewers that apply sabotage or check out old files
against the same working tree at the same time.

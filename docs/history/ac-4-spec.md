# Spec: G#4 / GH#6 — macOS CI click-interval timing, second investigation

## Summary
Re-investigated the long-open "click interval measures 25-40% slow on the macOS CI runner" ticket with no real Mac available anywhere in this pipeline; found no new lead and no safe code change to make on a guess, so this closes as **accept and document** (no code change, no ux-designer/developer cycle) — the same outcome the 2026-09-09 investigation reached, now with a stronger evidentiary basis recorded so nobody re-opens it without new information.

## Goals
- Determine, as far as the evidence in this repo and this pipeline allows, whether G#4/GH#6 is (a) a real product bug in the click loop, (b) a CI-environment artifact, or (c) a test-tolerance problem — and record the finding where the next person who touches this code will actually see it.
- Leave a durable trail (code comment + backlog entry) that states the finding and what would change the conclusion, so this ticket doesn't get silently re-investigated from scratch in six months with no new information.

## Non-goals
- No change to `_sleep()`'s polling granularity, the click loop, or the test harness's `pump()` cadence — the 2026-09-09 cycle already tried loosening `pump()`'s cadence on a GIL-contention theory and it made the measured overshoot *worse* (0.251 s -> 0.283 s), so there is no untried, evidence-backed code change to make here.
- No loosening of `test_interval_is_honoured`'s/`test_jitter_widens_the_spread`'s assertion bounds. A bound loosened until it stops failing stops asking the question — the 2026-09-09 commit message already made this call explicitly and nothing found this cycle changes it.
- No attempt to acquire or provision a real Mac — out of scope for this cycle; noted under Open questions as the one thing that would actually resolve the remaining ambiguity.
- No re-litigating G#38/G#40 or any other open macOS ticket — this spec is scoped to G#4/GH#6 only.

## Background / current state

**The ticket, verbatim (backlog.md:156):** "G#4 / GH#6 — github: true — The click interval measures 25-40% slow on the macOS CI runner. Needs a real Mac." Flagged in the backlog's own "next up" notes (backlog.md:569-571, 614-615, 674-675) each time as "Investigation only; may end in 'accept and document' rather than a code fix."

**This is not the first pass.** Commit `d93a55f` (2026-09-09, "Fix the Windows rule; skip and file the macOS timing question") already ran this investigation once:
- Tried a GIL-contention fix first (widened `pump()`'s own poll interval from 10 ms to 25 ms, see `tests/test_ui.py:130-141`'s docstring). It didn't help: median gap went from 0.251 s to 0.283 s for a configured 200 ms interval — worse, not better.
- Concluded attribution was unresolved between "the click loop is genuinely slow on macOS" and "the runner can't schedule a Python thread that tightly," and — deliberately, per that commit's own message — did not loosen the assertion bound to make the failure go away, because a loosened bound stops asking the question.
- Skipped both timing tests (`test_interval_is_honoured`, `test_jitter_widens_the_spread`) on `darwin` via `unittest.skipIf` (`tests/test_ui.py:535-537`), filed GH#6 (body: `gh api repos/LeTe0301/afk-clicker/issues/6`, still open, zero comments since filing), and left the finding in a code comment (`tests/test_ui.py:528-534`).

**GH#6's own body already lists the same two live hypotheses this cycle started from**, unresolved: `_sleep`'s 20 ms poll granularity not being honoured by Darwin's timer, or a shared runner that simply can't schedule a Python thread that tightly. No comments or updates have landed on the issue since 2026-09-09.

**The relevant code, unchanged since the 2026-09-09 cycle:**
- `AfkAutoclicker.loop()` (`afk_clicker.py:4465-4517`) — reads `click_ms`/`jitter_ms` off `self.settings` every pass, calls `self.mouse.click(button)` (line 4515), then `self._sleep(interval)` (line 4516).
- `AfkAutoclicker._sleep()` (`afk_clicker.py:4450-4455`) — an interruptible sleep: `while self.running and time.monotonic() < deadline: time.sleep(min(0.02, ...))`. Identical on every platform; nothing branches on `sys.platform`.
- `self.mouse` is `pynput.mouse.Controller()` in production (`afk_clicker.py:44`, constructed at `afk_clicker.py:285` inside `selftest()`, and via `Controller()` elsewhere) — but **not in the timing tests**. `tests/test_ui.py:24-38`'s `FakeMouse.click()` just does `self.clicks.append((button, time.monotonic()))`; `ClickLoop.setUp` (`tests/test_ui.py:496-499`) replaces `self.ui.mouse` with a `FakeMouse()` before every test in the class. This matters: **the measured 25-40% overshoot cannot be attributed to pynput's macOS click backend (Quartz/`CGEventPost`)** — no real OS call happens anywhere in the timing loop being measured. What's actually being measured is purely Python-level: the worker thread's `_sleep()` polling loop, racing against the main thread's `pump()` (`tests/test_ui.py:130-141`, `root.update()` + `time.sleep(0.025)`) for the GIL.
- `test_interval_is_honoured`/`test_jitter_widens_the_spread` (`tests/test_ui.py:539-568`) — both `@darwin_timing`-skipped (`tests/test_ui.py:535-537`).

## What this cycle added

1. **Confirmed `FakeMouse` is in play** for both skipped tests (see above) — this was not called out explicitly in the 2026-09-09 investigation's comment, and it rules out one entire class of explanation (macOS click-injection overhead) that would otherwise have been a plausible next hypothesis to chase.
2. **Confirmed via `gh api` that GH#6 has had zero activity** since it was filed — no new data, no comment, still open, same two hypotheses.
3. **Confirmed via `gh run list`/`gh run view`** that this repo's own current CI (run `35316492692`, 2026-09-18) shows `macos-latest`'s job taking ~130 s against `ubuntu-latest`'s ~114 s for the same suite — a real but modest (~15%) overhead on this repo's own CI today, not the 25-40% at issue (that number is per-interval jitter inside one test class, not overall job wall-clock, so this is only weak corroborating signal, not a direct measurement — the timing tests are skipped on darwin so no fresh per-interval numbers exist to compare against the 2026-09-09 ones).
4. **Searched for external corroboration.** GitHub's own `actions/runner-images` repo has numerous long-running, acknowledged issues (#1336, #10098, #11509, #11760, #12512, and a 2026-10-01 incident thread) reporting `macos-latest`/`macos-14`/`macos-15` runners running 2-10x slower than expected, independent of any particular workload, spanning well past 2026-09-09 — i.e. this is a known, ongoing, industry-wide characteristic of GitHub's macOS runners, not something specific to this project.

## Conclusion

**Most likely explanation: (b) a CI-environment artifact**, not (a) a real bug in the click loop and not (c) a simple test-tolerance problem to widen away. Reasoning:
- `_sleep()` is identical, unbranched code on every platform, and Linux lands within 0.1 ms of the 200 ms target across 16 consecutive runs on that same code (per the 2026-09-09 finding) — so the mechanism isn't in this file.
- The thing being measured is pure Python thread-scheduling precision (`FakeMouse`, no real OS call) — ruling out the macOS click-injection-overhead hypothesis.
- The one thing that was tried as a fix (loosening the test's own polling cadence) made it worse, ruling out "the test's own instrumentation is too tight" as the whole story.
- GitHub's own runner-images repository documents this exact class of problem — unattributed, ongoing, macOS-specific CI performance degradation — independent of any specific project's code, for the entire period spanning both this ticket's original filing and today.

This does **not** reach full certainty. It remains possible that real macOS hardware is inherently ~25-40% coarser than Linux at this specific granularity (CPython thread scheduling / Mach vs. Linux `futex` wakeup latency is a real, documented difference in general, independent of GitHub's runners specifically) — which would make this a genuine (if minor) platform characteristic rather than a pure CI artifact, though even then it would not be a *bug* in this app's code, and there is still no safe code change to make on a guess either way. Resolving that last bit of ambiguity needs a real Mac, which this pipeline does not have (see Open questions).

## Affected areas
- `tests/test_ui.py:528-537` — comment above `darwin_timing` expanded with this cycle's findings (done as part of this dispatch, see below). No test logic, assertion, or skip condition changed.
- `backlog.md:156` — G#4/GH#6's line updated to reflect the closed, accept-and-document status and point at the expanded comment (done as part of this dispatch, see below).
- No changes to `afk_clicker.py`, no schema/API changes, no UI changes. **ux-designer and developer have nothing to do for this cycle.**

## Edge cases
Not applicable — no code changes. (If this is ever revisited: any future fix attempt should re-confirm `FakeMouse` is still what's measured, since swapping in a real mouse backend for the timing tests would change what's being attributed.)

## Acceptance criteria
- [x] `tests/test_ui.py`'s `darwin_timing` comment documents: the `FakeMouse`-no-real-OS-call finding, the prior failed GIL-contention fix attempt, Linux's precision on identical code, and the GitHub runner-images corroboration — so a future reader has the full chain without re-deriving it.
- [x] `backlog.md:156` reflects the closed/accept-and-document outcome, dated, with a one-line pointer to the expanded comment rather than duplicating the full finding.
- [ ] GH#6 and its linked Gitea issue (`admin/afk-clicker#4`) get a closing comment recording this finding, referencing this commit — **left to the orchestrator to do** (per this dispatch's instructions, product-manager does not close external trackers unilaterally).

## Open questions
- **The one thing that would fully resolve this: a real Mac.** Not available anywhere in this pipeline (stated as a hard constraint for this dispatch). If one ever becomes available, the concrete next step is: run `tests/test_ui.py::ClickLoop::test_interval_is_honoured` and `test_jitter_widens_the_spread` directly on it (temporarily removing `@darwin_timing`) and compare the median gap to the 200 ms target. A precise result there (like Linux's 0.1 ms) would confirm this was purely a CI-runner artifact and the skip could arguably be narrowed to "known-throttled CI only" rather than "all darwin"; a genuinely 25-40%-slow result on real hardware would reopen this as a real, if likely unfixable-in-this-codebase, platform characteristic to document more prominently (e.g. in a user-facing macOS caveat) rather than a click-loop bug. **This is an explicit open question for Leo, not a decision made here** — proceeding under the assumption that, absent a real Mac, "accept and document" is the right resting state, per the ticket's own framing ("may end in accept and document") and the lack of any new lead this cycle turned up.
- Whether to also narrow the skip condition (e.g. skip only when a `CI` env var is set, so a hypothetical future run on someone's real Mac locally wouldn't silently skip) was considered and rejected as unnecessary scope — nothing in this ticket asks for that, and it would be speculative tuning of a skip condition for a scenario (a contributor running the suite locally on real macOS hardware) that hasn't come up.

## Risk / rollback notes
- Zero production code changed — zero behavioral risk. The two comment/doc edits are trivially revertible (`git revert` or `git checkout -- tests/test_ui.py backlog.md`).
- Leaving the two tests skipped on darwin means macOS CI still provides zero coverage of interval/jitter timing — an accepted, pre-existing gap (unchanged from 2026-09-09), not something this cycle worsens or improves.

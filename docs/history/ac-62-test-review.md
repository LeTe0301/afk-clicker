# Test & Review: Reuse the Xlib connection in detect_running() (G#62) — fresh review, round 3

## Scope
Fresh testing + review pass against the current diff, after the developer's
second fix round responding to the prior `docs/test-review.md`'s CHANGES
REQUESTED verdict (Finding 1: the fallback rescue block's `walk(fallback.
screen().root)` and `fallback.close()` were unguarded). This is **not** a
re-review of that prior verdict — the prior document was read for context
only and is overwritten by this one. Branch
`feature/ac-62/reuse-xlib-connection-detect-running`, nothing committed yet.

## Test cases (round-3 scope + re-confirmation of everything already approved)

| # | Criterion / case (docs/spec.md) | Method | Result | Evidence |
|---|---|---|---|---|
| Finding 1 fix (a) | Fallback's own `.screen()`/`walk()` call also raises → still returns `[]`, does not raise out of `_window_titles()`, dead fallback best-effort-closed | automated, sabotage-verified | **PASS** | `WindowTitlesReusesXlibConnection.test_returns_an_empty_list_when_the_fallbacks_own_screen_fails` — ran it myself, `ok`. **Sabotage-verified independently**: reverted `afk_clicker.py:2109-2124` to the pre-fix `try: walk(fallback.screen().root) finally: fallback.close()` shape, reran → failed red with `RuntimeError: fallback screen() also broken` propagating straight out of `_window_titles()`, exactly as the prior review's repro described; restored the fix, reran → green, `md5sum` of `afk_clicker.py` identical before/after (`c70d7a42e4b52d9e84dc4ae65475b097`). |
| Finding 1 fix (b) | Fallback's own `.close()` call raises after a successful walk → the already-found titles are still returned, not discarded by a bare `finally` | automated, sabotage-verified | **PASS** | `test_returns_the_titles_it_found_when_the_fallbacks_own_close_fails` — ran it myself, `ok`. Same sabotage round-trip as above (one combined revert covers both sub-cases since both live in the same block): reverted → failed red with `RuntimeError: close also broken` propagating out even though `walk()` had already populated `titles = ["Fallback Game"]`; restored → green. |
| 1 | Second call reuses the first connection (count stays 1) | automated | **PASS** (re-confirmed) | `test_second_call_reuses_the_first_connection` — ran it myself, `ok` |
| 2 | Shared connection raises on use → falls back, returns usable list, does not raise (retry succeeds) | automated | **PASS** (re-confirmed) | `test_falls_back_to_a_fresh_connection_when_the_shared_one_raises` — ran it myself, `ok` |
| 2b | Shared connection raises on use → retry's own `Display()` open also fails → returns `[]`, does not raise | automated | **PASS** (re-confirmed, prior round's own fix) | `test_returns_an_empty_list_when_the_retry_itself_also_fails` — ran it myself, `ok` |
| 2c | Fallback's own `.screen()`/`walk()` raises / fallback's own `.close()` raises | automated, sabotage-verified | **PASS** (this round's fix — see Finding 1 fix rows above) | covered above |
| 3 | Reconnects after a discarded failure instead of staying permanently broken | automated | **PASS** (re-confirmed) | `test_reconnects_after_a_discarded_failure_instead_of_staying_broken` — ran it myself, `ok` |
| 4 | Opening a connection never blocks a concurrent call (crux lock-scope guarantee) | automated | **PASS** (re-confirmed; diff shows this code path untouched this round) | `test_opening_a_new_connection_never_blocks_a_concurrent_call` — ran it myself, `ok` |
| 5 | `_poll_games()`'s sequence-number/stale-result-dropping (G#39) unaffected | automated | **PASS** | `PollGamesScanDoesNotHoldSelfWhileBlocked` — ran it myself, `ok`. `_poll_games()`/`_apply_scan()` do not appear anywhere in `git diff`. |
| 6 | `foreground_title()` unchanged, same shared-connection path | code inspection | **PASS** | Untouched by the diff (`git diff afk_clicker.py` shows no hunk near it); calls the same `_window_titles()`. |
| 7 | `on_close()` clears the shared connection; doesn't raise even if `.close()` raises | automated | **PASS** | `OnCloseClosesTheSharedXlibConnection`'s two tests — ran them myself, both `ok`. |
| 8 | win32/darwin branches byte-for-byte unchanged | diff review | **PASS** | `git diff afk_clicker.py \| grep '^@@'` shows exactly 4 hunks: the module-level `_x11_display`/lock addition (`:2001`), the X11 branch's connection-reuse rewrite (`:2037`, `:2054`), and `on_close()`'s new block (`:6270`). The win32 (2026-2043) and darwin (2045-2051) blocks have zero changed lines. |
| 9 | No bare `time.sleep()` for race-sensitive sync; sabotage-verified | diff review | **PASS** | Unchanged from prior rounds; crux test still uses `threading.Event`. |

## Independent close read of the entire X11 branch, end to end (task item 4)
Read `afk_clicker.py:2053-2125` in full, not just the two blocks flagged in
the last two rounds, tracing every statement that can raise:

- `from Xlib import display as xdisplay` — import, pre-existing, relies on
  the caller's own outer `except Exception` (unchanged non-goal, not a new
  gap).
- `disp = xdisplay.Display()` on first-ever cold start (`disp is None`) —
  unguarded, but this is the *initial* open, not a "shared connection raises
  on use" case; `docs/spec.md`'s non-goals section is explicit that
  reconnect/fallback logic lives inside `_window_titles()` under the
  existing caller-level safety net, not that every `Display()` call gets its
  own internal fallback. This is identical to the pre-G#62 behaviour (the
  original code's single `disp = xdisplay.Display()` was equally unguarded)
  — not a regression, not in scope for acceptance criterion #2 (which is
  specifically about a connection that already raises *on use*, after having
  been successfully opened).
- The install race block (`:2062-2071`, under the lock) — only risky call is
  `disp.close()`, already guarded.
- `with _x11_display_lock: walk(disp.screen().root)` (`:2088-2089`) —
  `walk()` is self-guarding (its own top-level `try/except Exception: pass`
  at every recursion depth means it never raises once entered); the only
  thing that can escape is `disp.screen()`/`.root` evaluation, caught by the
  enclosing `except Exception:` at `:2091`.
- Discard-and-close of the dead shared connection (`:2095-2101`) — both the
  lock block and `disp.close()` are safe/guarded.
- `fallback = xdisplay.Display()` (`:2102-2108`) — guarded, returns `[]` on
  failure (prior round's fix).
- `walk(fallback.screen().root)` (`:2109-2120`) — now guarded, returns `[]`
  and best-effort-closes `fallback` on failure (this round's fix).
- `fallback.close()` on the success path (`:2121-2124`) — now its own
  guarded `try/except: pass` instead of a bare `finally` (this round's fix).

No further unguarded exception path out of `_window_titles()`'s X11 branch
remains. The one intentionally-unguarded call (the very first cold-start
`Display()` open) is a documented non-goal, not a third occurrence of the
same bug class — it was never in scope for acceptance criterion #2, and
fixing it would mean adding fallback logic to a call that has no prior
connection to fall back from (there would be nothing to retry with that
isn't already a fresh `Display()` call).

## Regression check
Full existing suite:
```
DISPLAY=:99 CI=true /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .
```
**`Ran 557 tests in 125.093s` / `OK (skipped=10)`, exit 0.** Matches the
developer's reported count exactly (555 from the already-approved baseline
+ 2 new tests this round). No `ResourceWarning` for an unclosed X11/Xlib
socket anywhere in this run — only pre-existing, unrelated
`test_ui.py`/`test_updater.py` file-handle `ResourceWarning`s, and
pre-existing `invalid command name "..._poll_games"/"..._drain_ui"`
Tk-teardown noise (also present in isolated targeted reruns below,
confirming it predates this change and isn't a new regression).

The box's shared `:99` Xvfb did not need a second display this round — no
hang, no client-cap pressure observed.

Targeted reruns, all green:
```
DISPLAY=:99 .../python -m unittest tests.test_ui.WindowTitlesReusesXlibConnection -v
```
→ 7 tests, `ok`.
```
DISPLAY=:99 .../python -m unittest tests.test_ui.PollGamesScanDoesNotHoldSelfWhileBlocked tests.test_ui.OnCloseClosesTheSharedXlibConnection -v
```
→ 3 tests, `ok`.

## Scope discipline (task item 3)
`git diff --stat`: `afk_clicker.py | 90 +++++++++++++-` / `tests/test_ui.py
| 366 +++++++++++++++++++++++++++++++++++++++++++++++++++++++` — only these
two files.

`git diff afk_clicker.py | grep '^@@'` → exactly 4 hunks, all inside: the new
module-level `_x11_display`/`_x11_display_lock` pair + comment (`:2001`),
the X11 branch's connection-reuse rewrite (`:2037`, `:2054`), and
`on_close()`'s new cleanup block (`:6270`). Nothing touches the lock-scope
crux design, G#39's sequence-number guard, the win32/darwin branches, or
`on_close()`'s existing join/cleanup ordering beyond the one new block this
ticket's own spec called for.

`git diff tests/test_ui.py | grep '^@@'` → exactly 2 hunks: the
platform-guarded `Xlib.display` import (`:20`) and the appended test classes
after `PollGamesScanDoesNotHoldSelfWhileBlocked` (`:759`). No existing test
was modified.

## Defects found
None. Both sub-cases from the prior review's Finding 1 are genuinely fixed,
independently sabotage-verified above. The independent end-to-end re-read of
the entire X11 branch (task item 4) found no further unguarded exception
path; the one call left unguarded by design (the very first cold-start
`Display()` open) is a documented spec non-goal, not a recurrence of the bug
class.

## Spec coverage
All nine of `docs/spec.md`'s acceptance criteria are implemented and covered
by a passing, independently-run (and, where race/failure-shaped, sabotage-
verified) automated test, or by direct code/diff inspection where the
criterion itself calls for that (win32/darwin byte-for-byte, no bare
`sleep`). Acceptance criterion #2 ("falls back to a fresh one-shot
connection for that call and does not raise out of `_window_titles()`") is
now fully covered across all of its realistic sub-cases: retry `Display()`
open failing (prior round), and the fallback's own `.screen()`/`walk()` or
`.close()` failing (this round).

## Findings
None at must-fix or should-fix severity.

### Nit (non-blocking)
- `afk_clicker.py:2109-2120` and the walk/except block immediately above it
  (`:2087-2101`) now share a visually similar "guard, discard, fall back"
  shape repeated twice (once for the shared connection, once for the
  fallback) — a small, legitimate duplication given the two cases are
  genuinely different objects (a long-lived shared connection vs. a
  call-scoped throwaway one) and the project's own minimal-diff convention
  already prefers this over introducing a shared helper for two call sites.
  Not worth a follow-up ticket; noted only for completeness.

## Follow-ups (non-blocking)
None.

## Overall verdict
**Approve.** The developer's second fix round correctly and verifiably
closed the prior review's Finding 1 — both named sub-cases (fallback's own
`.screen()`/`walk()` raising, fallback's own `.close()` raising after a
successful walk) are now guarded exactly in the pattern the rest of the
function already uses, and I independently reran and sabotage-verified both
new tests myself (revert → red with the exact named error → restore,
`md5sum`-confirmed byte-identical → green). The full suite is green at
557/557 with no Xlib-related `ResourceWarning`. My own independent,
end-to-end close read of the entire X11 branch (not just the two
previously-flagged blocks) found no further unguarded exception path — the
one remaining unguarded `Display()` call (the very first cold-start open) is
a documented spec non-goal, not a third instance of the same bug class.
Scope discipline confirmed: the diff touches only `afk_clicker.py`'s
`_window_titles()` X11 branch and `on_close()`, plus additive-only test
changes in `tests/test_ui.py` — nothing from prior rounds (lock-scope crux,
G#39's guarantees, win32/darwin, import/skip guarding, Defect 1's earlier
fix) moved. No must-fix or should-fix findings. Ready to hand back to the
product-manager/orchestrator for commit and the next iteration.

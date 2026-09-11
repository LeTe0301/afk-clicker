# Implementation: focus-test races on macOS (ac-19)

## Summary
`NumBoxFocus.test_starting_from_a_background_thread_drops_focus` polled Tk
state with a fixed `self.pump(0.1)` after joining a background thread, betting
that `_drain_ui`'s 40 ms timer would win the GIL against the click-loop thread
within 100 ms on a shared runner. Replaced the fixed pump with a new
`UITestCase.pump_until(predicate, timeout)` helper that pumps in 20 ms steps
until the condition holds or ~3 s pass, mirroring the wait-for-signal shape
`11f1d94` already established for `settle()`.

## Root cause
`start()` queues `self._ui(self.root.focus_set)`, which only takes effect
inside a `root.update()` call once `_drain_ui`'s `root.after(40, ...)` timer
fires — and `start()` also spawns the click-loop worker thread, which
competes for the GIL. A fixed 100 ms pump assumed enough of those ticks would
land in that window; on a loaded shared macOS runner that assumption didn't
hold (PR #21's two macOS runs passed, main's push run on the identical tree
failed).

## Changes by file
- `tests/test_ui.py`
  - Added `UITestCase.pump_until(predicate, timeout=3.0)` next to `pump`
    (around line 88): pumps in 20 ms steps until `predicate()` is true or the
    timeout elapses, then returns either way so the caller's own assertion
    still reports a genuine regression.
  - `NumBoxFocus.test_starting_from_a_background_thread_drops_focus`
    (line ~505): replaced `self.pump(0.1)  # let _drain_ui's 40 ms tick land`
    with `self.pump_until(lambda: self.root.focus_get() is not
    self.ui.click_ms.entry)`.

## Key decisions / tradeoffs
- Reused the existing wait-for-signal pattern (`settle()`, added in `11f1d94`)
  rather than inventing a second one — `pump_until` is the generalized form
  the review comment in `11f1d94` and this ticket's prompt both point at:
  `settle()` waits for one fixed condition (`hasattr(self.ui,
  "_seen_running")`), `pump_until` takes an arbitrary predicate so each
  caller can wait for its own signal.
- `pump_until` does not fail on timeout itself (unlike `settle`, which calls
  `self.fail(...)`) — it just stops pumping, so the existing
  `assertNotEqual`/`assertEqual` calls right after it still produce a normal,
  readable assertion failure on a genuine regression. `settle()` fails eagerly
  because there is no separate assertion after it to do that job.

## Siblings checked
Grepped `tests/` for a fixed `pump(...)`/`sleep(...)` immediately after
starting a thread or a call that goes through `_ui()`, followed by an
assertion on Tk state the queued call produces:

- `tests/test_ui.py:482-489` (`NumBoxFocus.test_starting_from_a_background_
  thread_drops_focus`) — the one fixed above.
- `tests/test_ui.py:588-598` (`HotkeyPersistence.test_capture_refuses_
  without_permission`) — superficially the same shape (`threading.Thread`,
  `join`, `pump`, assertion), but not a race: with
  `macos_input_permitted` patched to `False`, `capture_hotkey()` only queues
  `_ui(self._hotkey_error, ...)`, which touches the hotkey label, never
  `self.ui.hotkey`. The assertion (`self.ui.hotkey is None`) holds regardless
  of whether `_drain_ui` has run by the time it executes, so there's nothing
  here for `_drain_ui`'s timing to race. Left as-is.
- `tests/test_hotkey.py` — no `pump`/`sleep`/`Thread(target=...)` usage at
  all; not applicable.
- `tests/test_chords_slow.py` — uses `time.sleep` around real synthetic key
  presses via `pynput`/`HotkeyWatcher`, not Tk's `_ui`/`_drain_ui` queue, and
  is explicitly timing-sensitive on purpose (real key press/release/settle
  windows). Left as-is per the prompt.
- `tests/test_updater.py` — no `pump`/`sleep`/`Thread(target=...)` usage.
- The `ClickLoop` tests' `self.pump(seconds)` calls after `self.ui.start()`
  (e.g. `run_for`) also go through `_ui(self.root.focus_set)`, but nothing
  they assert on depends on that specific queued call landing — they assert
  on `FakeMouse` state populated directly by the worker thread, not on Tk
  focus/label state drained via `_drain_ui`. Not the same race; left as-is.
- `ClickLoop.test_interval_is_honoured` / `test_jitter_widens_the_spread` are
  the timing-on-purpose tests skipped on darwin (issue #6); left alone per
  the prompt.

## Deviations from spec
None. Implemented as directed: reused the `11f1d94` wait-for-signal shape via
a new `pump_until` helper beside `pump`, applied it to the one racy test, and
audited the rest of `tests/` for the same shape without finding another
instance.

## Known limitations
None identified. `pump_until`'s 3 s timeout is generous enough to absorb
runner load without meaningfully slowing a passing run (the condition it
polls for typically lands within one or two 40 ms `_drain_ui` ticks).

## How to verify locally
From the worktree root (`/home/dev/projects/.worktrees/afk-clicker/ac-19`),
with an X display available (Xvfb on `:99` here):

1. Full suite:
   `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`
   → `Ran 97 tests ... OK (skipped=7)`.
2. Proof the old fixed-pump version was racy and the new one isn't: patch
   `AfkAutoclicker._drain_ui` in memory so its reschedule uses `root.after(150,
   ...)` instead of `40`, construct a UI, run the old test body's logic
   (fixed `pump(0.1)`) and the new body's logic (`pump_until`) against it —
   the old body's focus assertion fails under the slowdown, the new body's
   passes. Verified interactively in this session; not committed as a repo
   file per the "no scratch files" rule.
3. Proof the fixed test still catches the regression: patch
   `AfkAutoclicker.start` to a copy of itself with the
   `self._ui(self.root.focus_set)` line removed, then run
   `tests.test_ui.NumBoxFocus.test_starting_from_a_background_thread_drops_focus`
   directly — it fails (`AssertionError: <Entry> == <Entry>`) after ~3.1 s,
   i.e. only once `pump_until`'s timeout is exhausted, not a false pass.
4. Flake check:
   `for i in $(seq 1 30); do DISPLAY=:99 <venv>/bin/python -m unittest
   tests.test_ui.NumBoxFocus.test_starting_from_a_background_thread_drops_focus;
   done` → 30/30 `OK`.

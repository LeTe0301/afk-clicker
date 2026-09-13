# Implementation: Fix the flaky `test_holding_does_not_repeat` (G#32/GH#55)

## Summary

`tests.test_chords_slow.Firing.test_holding_does_not_repeat` was flaky
because of a race in how the test drives synthetic input, not a bug in
`HotkeyWatcher`. Caught it failing in the act with instrumentation, traced it
to pynput's own double-delivery of every synthetic key transition when a
`Controller` and a `Listener` share a process, and fixed it by having the
test wait for an independent listener to go quiet between actions instead of
sleeping a fixed duration. No production code changed.

## Root cause

**This is a test-harness artifact, confirmed not reachable from a real
keyboard, not a product bug.** Evidence:

- `pynput`'s X11 `Controller._handle()` (`pynput/keyboard/_xorg.py:271-272`)
  sends the XTEST fake-input event to the X server **and then**
  synchronously calls `self._emit('_on_fake_event', key, is_press)`, which
  notifies every `Listener` in the same process directly, in-process,
  immediately. The **same** listener also gets the transition a second time,
  asynchronously, whenever the real X server round-trip actually arrives
  (`ListenerMixin._handle_message`, fed by the listener's own background
  thread reading the X record extension stream). This double-notification is
  a documented pynput characteristic for this exact situation (a `Controller`
  and `Listener` coexisting in one process) — it is not specific to Xvfb, and
  it is already called out in this test file's own module docstring ("XTEST
  under Xvfb delivers every synthetic press and release exactly twice").
- The second (real round-trip) copy is delivered on the listener's own
  background thread and has no delivery-time guarantee. Under CPU pressure
  (confirmed directly on the box this was diagnosed on — `uptime` showed a
  sustained load average around 40 on 10 cores from unrelated jobs) that
  thread can be starved for anywhere from tens of milliseconds to multiple
  seconds, so the delayed duplicate of an *earlier* action can arrive after a
  *later* action's own immediate copy has already changed watcher state.
- Caught this exact interleaving with instrumentation wrapping
  `HotkeyWatcher._press`/`_release` (scratch script, not committed): the
  delayed duplicate of the test's own "auto-repeat" press (the second
  `controller.press(kb.Key.f7)` call, sent while `f7` is already held) landed
  *after* the real `controller.release(kb.Key.f7)` call had already
  re-armed the watcher (because `f6` was still logically held at that point).
  `HotkeyWatcher` correctly saw a complete chord again and fired a second
  time — exactly the reported `AssertionError: 2 != 1`. Sample of the actual
  captured event sequence (timestamps relative to test start, columns are
  `armed before -> armed after`, `keys before -> keys after`):
  ```
  PRESS  f7  t=1.064   False->True   keys:[f6,f7]->[f6]   <- real release, chord breaks, re-arm
  PRESS  f7  t=1.0641  True->False   keys:[f6]->[f6,f7]    <- FIRE #2: stale duplicate of the
                                                                repeat-press, arriving late, re-
                                                                completes the chord while f6 is
                                                                still down
  ```
- Confirmed there is no in-process `keyboard.Controller` anywhere in shipped
  code (`afk_clicker.py:41` only imports `pynput.mouse.Controller` for the
  click simulation). `HotkeyWatcher`'s listener, in production, only ever
  receives the real X round-trip copy of a genuine hardware key event — the
  `_on_fake_event` fast path this bug depends on is never invoked outside a
  test that constructs its own `keyboard.Controller`. There is therefore no
  way for a real user's keyboard to trigger the interleaving above.
- `HotkeyWatcher.DEBOUNCE_S` (0.25s) already exists specifically to absorb
  genuine hardware auto-repeat duplicate events, per its own comment. Raising
  it to also cover a multi-hundred-millisecond-to-multi-second test-only
  delivery race would weaken real debounce behavior for legitimate rapid
  re-presses in production to paper over a test artifact — not done.

Given all of the above, the fix belongs in the test, not in
`afk_clicker.py`, and does not touch `HotkeyWatcher`'s debounce/re-arm logic.

## Changes by file

- `tests/test_chords_slow.py` — `Firing.test_holding_does_not_repeat`
  rewritten to wait for an independent `kb.Listener` to go quiet (200ms of no
  press/release activity, capped at a 3s timeout per wait) between each
  synthetic action, instead of a fixed `time.sleep(0.5)`/`time.sleep(0.4)`.
  This gives both copies of one action (the immediate in-process one and the
  delayed real-round-trip one) a chance to land before the next action is
  sent, closing the race described above. Added a `try`/`finally` around the
  action sequence so the extra probe listener and the watcher's own listener
  are always stopped, matching the existing `finally` in `fires()` earlier in
  the same file. No other test in the file was touched.

## Key decisions / tradeoffs

- **Fixed the test's synchronization instead of raising `DEBOUNCE_S`.**
  Confirmed (see "Root cause") that the double-delivery this races against
  cannot happen from a real keyboard in the shipped app, so widening
  production debounce would be tuning real behavior around a test-only
  condition — the opposite of what the ticket asked for if this turned out
  to be a product bug, and not applicable since it isn't one.
- **Wait for quiet on an independent listener, not for raw per-key delivery
  counts to reach an expected number.** Tried first: wait until each key
  transition had been observed twice (matching the documented "delivered
  exactly twice" behavior) before proceeding. This measurably improved the
  failure rate but did not eliminate it — under sustained heavy load, the
  listener thread can be starved long enough that X11's own detectable
  autorepeat fires a large burst of extra, legitimate press-only events for
  a still-held key (confirmed directly: bursts of 30+ consecutive raw press
  events for `f7` with no interleaved release, arriving all at once when a
  starved thread finally got scheduled), which broke the assumption that
  "exactly two" is the right count to wait for. Waiting for actual quiet
  (no events at all for a stretch) absorbs both the ordinary double-delivery
  and these autorepeat bursts without needing to predict how many raw events
  a given action will produce.
- **A second, independent `kb.Listener` drives the wait, not the
  `HotkeyWatcher` under test.** Keeps the synchronization mechanism entirely
  outside the code being verified — the test does not need to reach into
  `HotkeyWatcher`'s internals (no monkeypatching of `_press`/`_release`) to
  know when it's safe to proceed. This mirrors the file's own existing
  `fires()`/`pump_until` philosophy in `test_ui.py`: poll observed state with
  a bounded timeout instead of sleeping a duration and hoping.
- **Bounded every wait (`timeout=3.0`) and let it fall through rather than
  fail.** Matches `test_ui.py`'s own `pump_until` convention ("returns
  without failing if the predicate never becomes true, so the caller's own
  assertion still reports the regression") — if quiescence genuinely never
  arrives, `self.assertEqual(len(hits), 1)` still catches a real problem.

## Deviations from spec

None. The ticket's own instructions anticipated exactly this outcome
("if it turns out to be a product bug... report it plainly and stop" /
implicitly, the reverse: fix the test if it's a test bug) and asked for the
before/after rate either way; both are below.

## Known limitations

- The fix cannot give an absolute guarantee under arbitrarily severe host
  starvation — if the listener thread is starved for longer than the 3s
  timeout on `settle()`, the test proceeds anyway and could still race. This
  was not observed in ~90 combined measurement runs (see below), including
  under the same heavily loaded box the diagnosis was done on, and 3s is
  already generous relative to the worst delay actually measured (~2s, once).
- The underlying pynput double-delivery behavior itself is unchanged (by
  design — it lives in a third-party library and is harmless in production,
  see "Root cause"); this fix only changes how the test *waits* around it.

## Measurements

All runs on this box (`uptime` showing a sustained load average of
~38-44 on 10 cores from unrelated long-running jobs throughout), via the
real test runner, not a standalone script:

```
DISPLAY=:98 AFK_SLOW_TESTS=1 <venv-python> -m unittest \
    tests.test_chords_slow.Firing.test_holding_does_not_repeat
```
run in a loop.

- **Before** (unmodified `tests/test_chords_slow.py`, current `main`
  85dd1e6): 2/20 failures in one back-to-back batch (10%), all
  `AssertionError: 2 != 1`. Exploratory instrumented runs earlier in this
  session (a standalone script replicating the same sequence, not part of
  the committed diff) saw materially higher rates on the same box — up to
  7/20 (35%) — consistent with the ticket's own 33-50% baseline; the exact
  rate visibly depends on how busy the box's other jobs are at the moment,
  which is why two back-to-back measurements here differ.
- **After** (this fix): 0/20, then a second back-to-back batch of 0/20 —
  40/40 passing. An exploratory version of the same technique (before it was
  written into the actual test file) was also run for 60 back-to-back
  iterations with 0 failures.
- Full `tests.test_chords_slow` class (all 5 methods, `AFK_SLOW_TESTS=1`):
  `Ran 5 tests in 67.643s — OK`.
- Full fast suite (`python -m unittest discover -s tests -t .`, no
  `AFK_SLOW_TESTS`): `Ran 292 tests in 85.958s — OK (skipped=5)` — no
  regressions from this change (it only touches one slow-suite test method).

## How to verify locally

```
cd /home/dev/projects/.worktrees/afk-clicker/ac-32
PYBIN=<venv-python with pynput>

# the fixed test, once
DISPLAY=:98 AFK_SLOW_TESTS=1 "$PYBIN" -m unittest \
    tests.test_chords_slow.Firing.test_holding_does_not_repeat -v

# repeat to confirm the flake is gone (adjust the display/loop count as needed)
for i in $(seq 1 20); do
  DISPLAY=:98 AFK_SLOW_TESTS=1 "$PYBIN" -m unittest \
      tests.test_chords_slow.Firing.test_holding_does_not_repeat || echo "FAIL $i"
done

# full slow suite
DISPLAY=:98 AFK_SLOW_TESTS=1 "$PYBIN" -m unittest tests.test_chords_slow -v

# full fast suite (no AFK_SLOW_TESTS)
DISPLAY=:98 "$PYBIN" -m unittest discover -s tests -t .
```

Use a display nothing else is using, and do not run two of these
Xvfb-driving processes against the same display concurrently.

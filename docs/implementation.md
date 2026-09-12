# Implementation: Fix the test suite's intermittent interpreter-shutdown abort (G#27/GH#46)

## Summary

Found and fixed three concrete, previously-unknown reference leaks in
`afk_clicker.py` that keep a closed `AfkAutoclicker`/its Tk interpreter
reachable past `on_close()`: `root.bind_all()`'s own Tcl command (never
released — `destroy()` does not cover it), every un-removed `trace_add()`
surviving a rebuild (an existing, more narrowly-scoped backlog item), and an
item left in `self._ui_queue` by `on_close()`'s own `self.stop()` call after
the drain timer that would otherwise empty it is cancelled. Also hardened
`_poll_games()`'s scan thread, which held `self` for the full duration of a
`detect_running()` call that can itself stall (confirmed directly: roughly 1
scan in a couple hundred gets stuck opening its Xlib connection) — it now
holds only the plain `profiles` list across that call, and the thread is
tracked and joined (bounded, 2s) by `on_close()` instead of being fire-and-
forget. All four fixes are real, individually confirmed (each demonstrated to
leave a live Python reference to a closed UI, each shown fixed by
`gc.get_referrers()`/`_tclCommands` inspection before and after).

**This does not fully resolve the reported symptom.** After all four fixes, a
full-suite run still reports the same off-main-thread `Variable.__del__`
(the always-caught `RuntimeError: main thread is not in main loop` variant)
at roughly the same frequency as before the fix — traced to a real,
reproducible interaction described in "Known limitations" below, not yet
root-caused. Whether the *fatal* abort this ticket was filed for is the same
mechanism escalating, or a different one, could not be determined: 20
back-to-back full-suite runs of unmodified `main`, and 20 more of this
branch, in the sandboxed environment this investigation ran in, produced
zero `exit 134` aborts on either side — only the benign variant, which *is*
directly, reliably reproducible every run. See "Measurements" below for the
full account of what was and was not reproducible here, and why the
before/after abort-rate comparison the ticket asked for could not be made.

## Root cause

The originally-hypothesized cause — "several tests start real worker threads
and join them with a timeout" (the sites named in the ticket) — was
investigated and is **not** the primary mechanism. Every one of those sites
either already converges well inside its timeout in practice, or (for the
one genuine case found, `_poll_games()`) held a reference for reasons
unrelated to the join timeout itself (see below).

The actual, confirmed mechanism: **something keeps the Tcl interpreter
(`root.tk`) reachable past `on_close()`/`root.destroy()`.** `_tkinter.tkapp`
is confirmed (`gc.is_tracked()`) to not participate in Python's cyclic
garbage collector, so as long as *anything* still holds a real reference
into that interpreter — a still-registered Tcl command, a widget, a
Variable — the whole object graph the interpreter reaches (every widget,
every Variable, this whole UI) survives too, and Python's own refcounting
can never free a graph that includes a non-GC-tracked node with a live
reference back into it. Eventually, *something* frees the last reference —
often the main thread (an ordinary, always-caught `RuntimeError`), but
sometimes a background thread that happens to be running Python bytecode at
that moment, which is how a `Variable.__del__` runs off the main thread and
can hit the "wrong thread" Tcl-level panic instead of a catchable exception.

Three concrete, confirmed leaks were found and fixed (see "Changes by
file"): `bind_all()`'s own command, every un-removed variable trace
surviving a rebuild, and an undrained `_ui_queue` item. `_poll_games()`'s
scan thread was a fourth, related issue: not a permanent leak by itself, but
a thread that legitimately holds `self` for however long `detect_running()`
takes — which is normally sub-millisecond, but can itself stall
indefinitely (confirmed directly via instrumentation: one scan out of a
couple hundred gets stuck inside `Xlib.display.Display()`'s connection
setup) or simply race `on_close()`'s own teardown under load.

A fifth, real, reproducible leak (see "Known limitations") was found but not
resolved: a preceding test that goes through `UITestCase.restart()` reliably
causes a *later* test's `GameItem`/`SettingsItem`/`Button` widgets to survive
a clean, otherwise-verified-correct `on_close()`. This is very likely the
dominant remaining contributor to the reported flakiness, but its exact
mechanism was not identified within this investigation's time budget.

## Changes by file

- `afk_clicker.py`
  - `import weakref` added.
  - `AfkAutoclicker.__init__`: `root.bind_all("<Button-1>", ...)`'s return
    value (the Tcl command name) is now kept as `self._button1_all_funcid`.
    `bind_all()` registers with `needcleanup=0` (unlike a plain `bind()`),
    so `destroy()` never releases it on its own.
  - `AfkAutoclicker.__init__`: added `self._poll_thread = None`.
  - `AfkAutoclicker._rebuild_ui()`: calls the new `self._forget_traces()`
    after destroying the outgoing widget tree and before building the next
    one, so a rebuild's own superseded `Segmented`/`TabBar` traces (and the
    five `AfkAutoclicker`-level ones, all recreated fresh per rebuild) are
    released before becoming unreachable from `self`.
  - `AfkAutoclicker._poll_games()`: `scan()` now resolves `self` through a
    `weakref.ref`, drops it (`del me`) before the blocking
    `detect_running()` call, and only re-resolves it afterward to deliver
    the result. The thread is now assigned to `self._poll_thread` (was
    fire-and-forget).
  - `AfkAutoclicker._forget_traces()` (new): walks `vars(self)` for every
    `tkinter.Variable` (or NumBox-style `.var` one level down) and clears
    everything `trace_info()` reports on it, regardless of which widget
    registered it. Called from both `_rebuild_ui()` and `on_close()`.
  - `AfkAutoclicker.on_close()`: joins `self._poll_thread` (bounded, 2.0s,
    matching the existing `self.worker` pattern) before proceeding;
    `unbind_all("<Button-1>")` + `deletecommand(self._button1_all_funcid)`;
    calls `self._forget_traces()`; drains (discards, does not run) any item
    left in `self._ui_queue`.

- `tests/test_ui.py`
  - `import gc`, `import weakref` added.
  - New `PollGamesScanDoesNotHoldSelfWhileBlocked` test class: mocks
    `detect_running` to block, then inspects `scan()`'s own stack frame
    (via `sys._getframe`) while it is paused inside the mock, asserting
    `"me"` (the strong reference) is absent from its locals and `"profiles"`
    is present. Fails on the pre-fix `scan()`, passes on the fix. Chosen
    over a whole-object `gc.collect()`/`weakref` check specifically because
    that approach is the one shown, in this same investigation, to be
    subject to the unresolved interaction in "Known limitations" — this
    test verifies the exact code change directly instead.

- `backlog.md`
  - Marked the existing "`Segmented` never calls `trace_remove`" item
    partially resolved by `_forget_traces()`, with the still-open mid-life
    window (a rebuild-superseded widget's trace before the *next*
    rebuild/close) called out explicitly.
  - Rewrote the "test suite intermittently aborts" item with everything
    fixed, everything ruled out, and the exact minimal repro for the
    still-open residual (see "Known limitations").

## Key decisions / tradeoffs

- **`_forget_traces()` walks `vars(self)` generically instead of tracking
  each `trace_add()` call site by hand.** The existing backlog item this
  overlaps with is itself evidence that hand-tracking drifts (`Segmented`'s
  trace was simply never paired with a `trace_remove()`). Walking every
  Variable this UI can reach and clearing whatever `trace_info()` reports on
  it is correct for every current trace site and stays correct as new
  `Segmented`/`NumBox`/`TabBar` controls get added, at the cost of one
  `isinstance`/`getattr` sweep of `self.__dict__` per rebuild and close —
  negligible next to a full widget-tree rebuild.
- **`_poll_games()`'s fix holds `profiles` (a plain list of dicts), not a
  weakref-resolved `self`, across the actual blocking call.** A weakref
  alone does not help here: once `scan()` dereferences it into a strong
  local, that local is alive for the entire duration of whatever call it is
  passed into (this was verified directly — an earlier attempt that kept
  `weak` but resolved it into `me` and passed `me.profiles`/`me._ui` around
  the blocking call still failed the same way `self` did). Extracting the
  one thing the blocking call actually needs, and re-resolving the weakref
  only after it returns, is what actually removes `self` from the picture
  during the stall.
- **`on_close()` discards, rather than runs, whatever is left in
  `_ui_queue`.** Running it would mean invoking a queued UI callback
  (`_set_status`, `_mark_running`, ...) against widgets that are about to be
  destroyed or already are; discarding is both simpler and matches the
  intent (there is no user left to see the update).
- **Kept the regression test unit-level (inspecting `scan()`'s own frame)
  rather than whole-object.** A whole-object version (construct a UI with a
  deliberately-blocked scan, `on_close()` it, weakref-check it is collected)
  is a more end-to-end test of the same property, and was tried first — but
  it is the same shape of check shown, in this investigation, to be
  sensitive to the unresolved interaction in "Known limitations" (it fails
  intermittently depending on what test happens to run before it in the
  full suite, for reasons unrelated to `_poll_games` at all, confirmed by
  reproducing the same failure with the scan-thread mock removed from the
  UI-construction side entirely). Shipping a test with that failure mode
  would be the same mistake this whole ticket exists to fix. The frame-
  inspection version tests the exact code change without going through
  `on_close()`'s much larger, separately-verified cleanup at all.

## Deviations from spec

None from the ticket's stated scope (test-suite abort investigation and
fix), but the outcome deviates from what a from a clean "found it and fixed
it" ticket would look like — see "Known limitations," which is the direct,
honest report the ticket itself asked for in that event ("If the rate drops
but is not zero, say so plainly").

## Known limitations

- **The dominant remaining contributor to the reported flakiness was found
  but not root-caused.** Minimal, reliable repro:
  ```
  DISPLAY=:99 <venv-python> -m unittest \
      tests.test_ui.PerGameSettings.test_survives_a_restart \
      tests.test_ui.PollGamesScanDoesNotHoldSelfWhileBlocked
  ```
  (Any test using `UITestCase.restart()`, followed by any test that
  constructs a second `AfkAutoclicker` and closes it, reproduces the same
  way — this pairing is just the smallest one found.) Under this ordering,
  a subsequent `AfkAutoclicker`'s `GameItem`/`SettingsItem`/`Button` widgets
  survive a completely ordinary `on_close()` — confirmed via
  `widget._tclCommands is None` and `widget.children == {}` (i.e. Tcl-level
  cleanup, the thing this ticket's fixes target, is not the gap) — and
  `gc.collect()` reports 0 objects collected even retried over a 2-second
  window. `gc.get_referrers()` on the surviving objects shows no external
  anchor, which is *consistent with* (not proven to be) a reference held by
  `_tkinter.tkapp` itself, confirmed via `gc.is_tracked()` to not
  participate in cyclic GC — such a reference would be invisible to
  graph-based diagnosis by construction. Ruled out as the cause: `bind_all`,
  `trace_add`, and `_ui_queue` (all confirmed independently fixed and
  verified via the same inspection technique in the simple, non-`restart()`
  case). This is the most likely next thing to investigate for whoever
  picks this up — see the rewritten backlog.md item.
- **The fatal `exit 134` abort could not be reproduced on demand in this
  environment, before or after the fix.** 20 back-to-back full-suite runs
  of unmodified `main`, and 20 more of this branch (same script, same
  Xvfb display, same venv), both produced zero aborts — only the benign,
  always-caught `RuntimeError` variant, which *is* reliably reproducible
  (roughly 55 of ~284 tests trigger it, every run, on both branches). This
  means the before/after abort-*rate* comparison the ticket asked for could
  not actually be made: there is no measured rate to compare on either
  side, in this environment. What can be reported is that the specific,
  documented mechanism ("a Tk `Variable.__del__` running off the main
  thread") is real, 100% reproducible, and only partially addressed.
- **`_forget_traces()` does not close the original backlog item's own
  window** (a rebuild-superseded widget's dangling trace misfiring if
  something writes to the variable *between* that rebuild and the next
  rebuild/close) — only the "these traces keep the whole UI reachable past
  close" consequence this ticket cares about. See the updated backlog.md
  item for the distinction.

## How to verify locally

```
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .   # full suite, should be OK
DISPLAY=:99 <venv-python> -m unittest tests.test_ui.PollGamesScanDoesNotHoldSelfWhileBlocked -v
```

To see the fixed leaks directly (before/after), construct an
`AfkAutoclicker`, take a `weakref.ref()` of it, call `on_close()`, drop the
UI/root, `gc.collect()`, and check the weakref — clean (`None`) on this
branch for a plain construct-and-close; still alive on `main`. To see the
still-open residual, run the two-test command under "Known limitations."

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

## Round 2 — macOS abort, PR #47 review response

**Trigger.** PR #47 (this branch, head `8e3c934`) was DO-NOT-MERGE'd by an
independent review: macOS CI aborted the interpreter (`Tcl_FindHashEntry on
deleted table`, exit 134) inside
`tests.test_ui.AfterJobsAreNotDuplicated.test_timer_count_does_not_grow_between_rebuilds`,
a test `main` passes cleanly on the same runner/image. Ubuntu and Windows
were green. Full review: `pr47-review.md` (supplied alongside this round's
task; not committed to the repo). The review localized the difference to
`on_close()`'s new, unconditional synchronous Tcl-teardown work — the
`bind_all` funcid's `unbind_all()`+`deletecommand()` pair, and the
`_forget_traces()` sweep — neither of which `main`'s `on_close()` does at
all, and confirmed the crashing test does **zero** rebuilds (so
`_rebuild_ui()`'s own, separate call to `_forget_traces()` is not
implicated by this failure).

**What changed.** Removed both Tcl-touching operations from `on_close()`
only:

- The `unbind_all("<Button-1>")` + `deletecommand(self._button1_all_funcid)`
  pair. Since nothing else used `_button1_all_funcid` once `on_close()` no
  longer releases it, the capture at the `bind_all()` call site
  (`AfkAutoclicker.__init__`) was reverted too, back to `main`'s plain
  `root.bind_all("<Button-1>", self._maybe_drop_focus)` with no return
  value kept.
- The `self._forget_traces()` call inside `on_close()`.

**What was kept, unconditionally, because it is not Tcl-teardown work and
the review did not implicate it:**

- `_poll_games()`'s weakref fix (`scan()` holds a plain `profiles` list, not
  `self`, across the blocking `detect_running()` call) and the bounded
  `self._poll_thread.join(timeout=2.0)` in `on_close()` — pure Python, has
  its own regression test (`PollGamesScanDoesNotHoldSelfWhileBlocked`),
  still passing.
- The `_ui_queue` drain at the end of `on_close()` — pure Python
  (`queue.SimpleQueue.get_nowait()`/discard), no Tcl call.
- `_rebuild_ui()`'s own call to `self._forget_traces()`. This is the same
  function, called from a different site, and the review's own account
  says the multi-rebuild test that exercises it three times in one test's
  lifetime (`test_exactly_three_after_jobs_survive_three_rebuilds`) passed
  clean on the same macOS CI run that produced the abort — i.e. this call
  site was already exercised on macOS, on this exact commit, without
  incident. Reverting it too would have thrown away a working,
  already-macOS-verified fix for no evidenced reason; on_close()'s call
  site (new, untested on macOS before this CI run, immediately preceded by
  a batch of `after_cancel()` calls and immediately followed by
  `root.destroy()`) is the one this round removes.

**Mechanical reasoning about the panic (asked for explicitly; offered as
reasoning, not as something I can prove without macOS access).**
`Tcl_FindHashEntry on deleted table` is Tcl finding a stale pointer into a
hash table structure that no longer exists — a C-level panic, not a Python
exception, so the existing `try/except tk.TclError` around `deletecommand()`
was never going to catch it regardless of what surrounds it. Both
`deletecommand()` (interpreter-wide command table) and `trace_remove()`
(per-`Variable` trace list) touch a Tcl hash table, so either operation
*could* be the one that eventually surfaces this message if some other
in-flight Tcl/Cocoa event is what actually corrupts or frees the table
first. I lean towards the `bind_all` `deletecommand()` as the more likely
proximate trigger, for one specific reason I can actually point to rather
than a guess: `deletecommand()` deletes a *generic Tcl command object* —
exactly the kind of object Tk/Aqua's Cocoa-runloop-backed event dispatch
looks up by name when servicing a still-in-flight native event (e.g. a
`CFRunLoopTimer` backing one of the `after()` jobs cancelled a few lines
above, whose Tcl-level cancellation does not guarantee the already-queued
native OS event is also revoked in time on Aqua — a mismatch between
Tcl-level and Cocoa-level cancellation that has no equivalent on X11's
plain socket-based event loop, which is consistent with this being
observed only on macOS across 62+ combined runs everywhere else).
`trace_remove()`'s target (a `Variable`'s trace list) is not something
Tk's own event dispatch looks up by name during ordinary event servicing,
so it is less obviously positioned to explain a panic phrased in terms of
command/table lookup specifically. **This is a lean, not a proof** — I do
not have a macOS box, cannot single-step the Tcl runtime, and the review's
own reasoning (Round 3) reached the same place: only macOS CI, or a macOS
debugger, can settle which specific operation (or their combination, or
something else timing-adjacent entirely) is the actual cause. Given that,
and given the token cost of a wrong guess (a full CI cycle per attempt), I
did not attempt a "keep one operation, add a guard" fix — removing both
from `on_close()` is the only change here I can defend without macOS
access.

**What is now unfixed and tracked (not silently dropped).** Two of the
three originally-confirmed reference leaks from Round 1 are back on
`backlog.md`, open:

- **`bind_all()`'s own Tcl command** (`needcleanup=0`) is no longer released
  by `on_close()`. This is the same leak the round-1 investigation
  originally confirmed via `gc.get_referrers()`/`_tclCommands` inspection —
  real, and now unfixed again.
- **The *last* generation's variable traces.** `_forget_traces()` itself is
  still defined and still called from `_rebuild_ui()`, so every rebuild
  still releases the *outgoing* generation's traces — that part of the
  original leak (traces accumulating across N rebuilds) stays fixed. What
  is no longer covered is the *final* generation: the set of traces live on
  whatever widgets exist at the moment the app actually closes is never
  swept by anything now, since `on_close()` no longer calls
  `_forget_traces()`. This is a narrower regression than "the whole fix is
  gone," but it is real, and it is what was partly covering the standing
  `backlog.md` item "`Segmented` never calls `trace_remove`" — that item's
  note has been updated to say so (see `backlog.md`).
- The `_poll_games()` fix and the `_ui_queue` drain remain fully in place
  and are not affected by this round.

**Verification.** Full suite: `DISPLAY=:99 <venv-python> -m unittest
discover -s tests -t .` → `Ran 285 tests in 56.836s — OK (skipped=5)` (same
benign, always-caught off-main-thread `RuntimeError` pattern documented
above, unchanged in kind or rate). `AfterJobsAreNotDuplicated` (the
crashing class) run 5x back-to-back → clean every time. Regression test
`PollGamesScanDoesNotHoldSelfWhileBlocked` → still passes. All run on
Linux/Xvfb; macOS CI, on the next push, is the only environment that can
actually confirm the abort is gone, per the constraint this round started
from.

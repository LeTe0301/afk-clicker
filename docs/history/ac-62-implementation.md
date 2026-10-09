# Implementation: Reuse the Xlib connection in detect_running() (G#62)

## Summary
`_window_titles()`'s X11 branch now shares one lazily-(re)connected,
module-level `Xlib.display.Display` connection (`_x11_display`, guarded by
`_x11_display_lock`) across calls instead of opening and closing a fresh one
every single call. Opening a new connection always happens *outside* the
lock; the lock only ever guards installing a just-opened connection and the
tree walk itself, per `docs/spec.md`'s own load-bearing constraint. Any
exception using the shared connection discards it and falls back, for that
one call only, to the exact pre-change open-walk-close-throwaway behaviour.
`on_close()` gets one new guarded cleanup block, mirroring the existing
`self.mouse`/`self.keyboard` precedent (G#53/GH#95).

## Root cause
N/A — this is a performance/robustness change, not a bugfix.

## Changes by file

### `afk_clicker.py`
- **`_x11_display` / `_x11_display_lock`** (new module-level names, right
  before `def _window_titles()`, ~`:2004`) — `None` and `threading.Lock()`.
  Module-level, not instance-level, per `docs/spec.md`'s own reasoning:
  `_window_titles()`/`detect_running()`/`foreground_title()` are free
  functions with no `AfkAutoclicker` reference threaded through any of them.
- **`_window_titles()`'s X11 branch** (the final, unconditional branch after
  the `win32`/`darwin` checks) — rewritten to:
  1. Read `_x11_display` without the lock.
  2. If `None`, open a new `Display()` **outside** `_x11_display_lock` (the
     one call known to stall unboundedly), then under the lock
     double-checked-install it — or, if another thread's open already won,
     close the redundant one and use the winner's.
  3. Walk the connection's tree **under** the lock.
  4. On any exception from step 3, discard the shared connection (`_x11_
     display = None` if it's still the one that failed, best-effort
     `.close()`) and fall back, for this call only, to a brand-new throwaway
     open-walk-close — byte-for-byte the pre-change behaviour, just scoped to
     one call instead of every call.
  The `win32` and `darwin` branches above it are untouched — confirmed by
  `git diff` showing no lines changed in either (see "How to verify
  locally").
- **`on_close()`** (right after the existing `self.mouse = None` /
  `self.keyboard = None` lines, G#53/GH#95's own spot) — new block: if
  `_x11_display is not None`, best-effort `.close()` it and set it back to
  `None`. Same reasoning as its mouse/keyboard precedent: cheap insurance
  against Xvfb's already-marginal max-clients ceiling in a test suite
  sharing one process across ~150+ UI-building test classes.

### `tests/test_ui.py`
- **`import Xlib.display`** (top of file, inside the existing `if app is not
  None:` block, next to the `tkinter`/`tkfont` imports) — the only seam
  available to intercept `_window_titles()`'s connection opens: `xdisplay` is
  a name local to `_window_titles()`'s own `from Xlib import display as
  xdisplay`, re-resolved fresh every call, so there is nothing on `app` to
  monkeypatch directly. Patching the real `Xlib.display.Display` class
  (already a transitive pynput dependency, so no new dependency) is the
  same technique this suite already uses for `app.sys.platform`/`app._run_
  theme_command` etc. in `DetectOsTheme` — monkeypatch-and-restore, no
  `unittest.mock`.
- **`_FakeX11Window` / `_FakeX11Screen`** (new module-level helpers, right
  after `PollGamesScanDoesNotHoldSelfWhileBlocked`) — minimal stand-ins so
  `walk()` terminates immediately with no titles and no real X server.
- **`WindowTitlesReusesXlibConnection`** (new `unittest.TestCase`) — four
  tests, each monkeypatching `Xlib.display.Display` and saving/restoring
  `app._x11_display` (closing whatever real connection a concurrently
  running UI test may have already installed there, rather than leaking
  it):
  - `test_second_call_reuses_the_first_connection` — two calls, asserts
    `Display()` construction count stays at 1.
  - `test_falls_back_to_a_fresh_connection_when_the_shared_one_raises` — the
    shared connection's `.screen()` raises on its second use; asserts the
    call still returns a usable (empty) list, closes the dead connection,
    and leaves `_x11_display` as `None`.
  - `test_reconnects_after_a_discarded_failure_instead_of_staying_broken` —
    one more call after the above discard opens exactly one new connection
    rather than staying permanently broken.
  - `test_opening_a_new_connection_never_blocks_a_concurrent_call` — the
    acceptance criteria's crux test. Thread A's `Display()` construction
    blocks on a `threading.Event` (never a `sleep`); thread B's call, started
    only once thread A is confirmed stuck inside its own open, must still
    finish within a bounded `Event.wait(2)` — proving the open never happens
    under `_x11_display_lock`. **Sabotage-verified**: temporarily moved the
    open back under the lock (the exact regression this test exists to
    catch) and confirmed this test — and only this test among the four —
    failed red, then restored the real fix and confirmed all four pass
    again (see "How to verify locally" for the exact commands).
- **`OnCloseClosesTheSharedXlibConnection`** (new `UITestCase` subclass,
  mirroring `OnCloseDropsControllerReferences`'s own style) — two tests:
  closes and clears a fake shared connection via a real `on_close()` call,
  and confirms `on_close()` itself does not raise even when the connection's
  own `.close()` raises.

## Key decisions / tradeoffs
- Followed `docs/spec.md`'s proposed approach exactly — module-level lock,
  open-outside/walk-inside the lock, double-checked install, one-call
  fallback on failure, `on_close()` mirroring the mouse/keyboard precedent.
  No deviations.
- Read G#39's full saga (`backlog.md`, `docs/history/ac-30-implementation.md`,
  the `ac-39-*` docs) before touching this call path, per the spec's explicit
  instruction — the no-join-on-supersede design in `_poll_games()` and the
  reason connection-opening must never happen under the lock both trace back
  to that history, and neither was touched here.
- Reused `walk()`'s existing per-node `try/except` unchanged; the only new
  `try/except` wraps the top-level `disp.screen().root` access (and the
  install/discard bookkeeping around it), since that's the only point in
  this call path that can raise from a dead shared connection without
  already being swallowed per-node.

## Deviations from spec
- None.

## Fix-only round (responding to `docs/test-review.md`'s BLOCKED verdict)

### Defect 1 — fallback `Display()` retry was unguarded (`afk_clicker.py:2102`)
The `except Exception:` branch that discards a dead shared connection and
falls back to a one-shot connection called `fallback = xdisplay.Display()`
with no try/except, unlike every other `Display()`-adjacent operation in the
function. If that retry itself also failed — the reviewer's named realistic
case, "X server restart," where an immediate reconnect is likely to fail for
the same reason — the exception propagated straight out of `_window_titles()`,
violating `docs/spec.md`'s acceptance criterion #2 ("does not raise out of
`_window_titles()`").

Fix: wrapped `fallback = xdisplay.Display()` in its own `try/except`
(`afk_clicker.py:2102-2108`); on failure it now `return []` — the same
degrade-to-empty-result contract `detect_running()`/`foreground_title()`'s
own outer `except Exception` already provides, not a new error shape.

Added `tests/test_ui.py`'s
`WindowTitlesReusesXlibConnection.test_returns_an_empty_list_when_the_retry_itself_also_fails`
— the sub-case the review flagged as untested (the shipped
`test_falls_back_to_a_fresh_connection_when_the_shared_one_raises` only
covered the retry *succeeding*). **Sabotage-verified**: temporarily removed
the new `try/except` around the fallback open, re-ran the new test, confirmed
it failed red with the exact `RuntimeError` chain the review's own repro
described (`"cannot open display: maximum clients reached"` during handling
of the original `"connection reset"`), then restored the fix and confirmed it
and the other three existing tests in that class all pass again.

### Defect 2 — `tests/test_ui.py`'s new `Xlib.display` import broke collection on non-Linux legs
`import Xlib.display` sat inside the existing `if app is not None:` guard,
but `python-xlib` is a Linux-only transitive pynput dependency
(`Requires-Dist: python-xlib>=0.17; "linux" in sys_platform`), `ci.yml` never
installs it on `windows-latest`/`macos-latest`, and `app is not None` is true
on those platforms regardless of `DISPLAY` (`tests/context.py`'s `HEADLESS`
check is itself Linux-only). The import would raise `ModuleNotFoundError` at
module-import time on those two required CI legs, failing collection of the
entire `test_ui.py` file.

Fix, two parts (guarding the import alone was not sufficient — see below):
1. **`tests/test_ui.py:23-29`** — moved `import Xlib.display` out of the
   `app is not None` block into its own `if app is not None and
   sys.platform.startswith("linux"):` guard.
2. **`tests/test_ui.py:790-793`** — added
   `@unittest.skipUnless(sys.platform.startswith("linux"), ...)` directly on
   `WindowTitlesReusesXlibConnection`, matching the existing
   `needs_input_permission`/`darwin_timing` `unittest.skipIf`-on-class/method
   precedent already in this file. Guarding the import alone would stop the
   `ModuleNotFoundError` at collection time, but `WindowTitlesReusesXlibConnection`'s
   `setUp()`/`tearDown()` reference the bare name `Xlib.display.Display` at
   *run* time — without the import, that name would not exist in the module's
   globals on Windows/macOS, trading a collection-time `ModuleNotFoundError`
   for a run-time `NameError` in the same class. `OnCloseClosesTheSharedXlibConnection`
   needed no such guard: it never references `Xlib` directly, only the
   generic `app._x11_display is not None` check `on_close()` already performs
   unconditionally (`afk_clicker.py:6329`), so it is platform-agnostic as-is.

**Verification caveat, stated plainly per the review's own disclosure
standard:** this fix is verified by inspection of pynput's package metadata
and `ci.yml`'s install step, the same evidence level the reviewer used — no
Windows/macOS runner is available in this sandbox either, so it has not been
verified by actually running a Windows/macOS CI leg.

### Full suite re-run after both fixes
```
DISPLAY=:99 CI=true /home/dev/.venvs/afk-clicker-test/bin/python \
  -m unittest discover -s tests -t .
```
`Ran 555 tests in 122.490s` / `OK (skipped=10)`, exit code 0 (554 from the
original cycle + the 1 new Defect-1 test). No `ResourceWarning` for an
unclosed X11 socket anywhere in the run (the symptom the reviewer caught live
under resource pressure last round).

Targeted run of just the touched classes also green:
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest \
  tests.test_ui.WindowTitlesReusesXlibConnection \
  tests.test_ui.OnCloseClosesTheSharedXlibConnection -v
```
→ 7 tests, `OK`.

Did not re-run the crux lock-scope sabotage test (`test_opening_a_new_
connection_never_blocks_a_concurrent_call`'s own verification) or re-litigate
anything the review marked clean — per the task instructions, only Defects 1
and 2 were in scope this round.

## Known limitations
- The new tests save/restore `app._x11_display` around each test (closing
  whatever real connection a concurrently-finishing earlier test's own
  background scan thread may have installed, to avoid leaking it), but a
  genuinely concurrent background scan thread from another test class could
  in principle still read/write the same module global while one of these
  tests has it monkeypatched to a fake. This mirrors a pre-existing
  characteristic of this suite's shared global/background-thread model
  (e.g. lingering `_poll_thread`s are already an accepted, documented
  property elsewhere) rather than a new hazard this change introduces, and
  the full suite run below shows no flakiness from it.
- Per spec's own non-goal: a connection that stays technically open but
  silently returns garbage on every per-node call (never raising) is not
  detected — not an observed failure mode, explicitly out of scope.

## How to verify locally
```
cd /home/dev/projects/afk-clicker

# New tests only
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest \
  tests.test_ui.WindowTitlesReusesXlibConnection \
  tests.test_ui.OnCloseClosesTheSharedXlibConnection -v

# Full suite (what CI runs, minus the opt-in slow chord suite)
DISPLAY=:99 CI=true /home/dev/.venvs/afk-clicker-test/bin/python \
  -m unittest discover -s tests -t .
```
Ran both during this cycle: the targeted run shows all 6 new tests passing;
the full suite shows `Ran 554 tests ... OK (skipped=10)`, exit code 0.

Win32/darwin branches untouched, verified by inspection of `git diff
afk_clicker.py` — every changed line sits inside the X11 branch of `_window_
titles()` or inside `on_close()`; the two lines of comment immediately above
the X11 branch (unrelated context) are the only other touched lines nearby.

Sabotage verification for the concurrency test (already run once during this
cycle, not left in the tree): moving the `xdisplay.Display()` open call back
under `_x11_display_lock` in `_window_titles()` makes
`WindowTitlesReusesXlibConnection.test_opening_a_new_connection_never_
blocks_a_concurrent_call` fail with "thread B blocked on thread A's
still-stuck connection open"; reverting restores a clean pass.

## Second fix-only round (responding to `docs/test-review.md`'s CHANGES REQUESTED verdict)

### Finding 1 — fallback rescue block only guarded `Display()`, not `.screen()`/`walk()` or `.close()` (`afk_clicker.py:2102-2114`)
The previous round's fix guarded `fallback = xdisplay.Display()` but left
`walk(fallback.screen().root)` unguarded and `fallback.close()` in a bare
`finally` (which overrides a good `titles` result if `.close()` itself
raises). Both are the identical correlated-failure window named in
`docs/spec.md`'s edge case ("X server restart, socket reset") just one call
later than the sub-case the prior round fixed — the reviewer reproduced both
raising straight out of `_window_titles()` against the running code,
violating acceptance criterion #2 verbatim.

Fix (`afk_clicker.py:2109-2122`): replaced the bare `try/finally` with the
same "guard each resource-adjacent operation, degrade to `[]` on failure"
shape the rest of the function already uses — `walk(fallback.screen()
.root)` now sits in its own `try/except Exception`, and on failure
best-effort-closes `fallback` (mirroring the existing `disp.close()` guard a
few lines above) before `return []`. On success, `fallback.close()` is
guarded by its own `try/except Exception: pass` instead of a bare `finally`,
so a `.close()` failure can no longer discard an already-successful
`titles` result:

```python
titles = []
try:
    walk(fallback.screen().root)
except Exception:
    # Fallback's own screen()/walk() also broke (same correlated-
    # failure window as the Display() open above) -- degrade
    # instead of propagating.
    try:
        fallback.close()
    except Exception:
        pass
    return []
try:
    fallback.close()
except Exception:
    pass
return titles
```

Added two tests to `tests/test_ui.py`'s `WindowTitlesReusesXlibConnection`,
both exactly the sub-cases the review named as untested:
- `test_returns_an_empty_list_when_the_fallbacks_own_screen_fails` — shared
  connection's `.screen()` raises, then the fallback's own freshly-opened
  `.screen()` also raises; asserts `_window_titles()` still returns `[]`
  rather than raising.
- `test_returns_the_titles_it_found_when_the_fallbacks_own_close_fails` —
  shared connection's `.screen()` raises, fallback's `walk()` succeeds and
  finds a real title (`_NamedWindow`/`_NamedScreen`, local to this test,
  since the existing shared `_FakeX11Window` always returns no name), then
  the fallback's own `.close()` raises; asserts the already-found title
  (`["Fallback Game"]`) still comes back rather than being discarded by the
  old bare `finally`.

**Sabotage-verified** both: reverted `afk_clicker.py` to the prior round's
exact `try: walk(...) finally: fallback.close()` shape, re-ran both new
tests — both failed red with the exact `RuntimeError`s the review's repro
named (`"fallback screen() also broken"` propagating out of
`_window_titles()`; `"close also broken"` propagating out even though
`walk()` had already run) — then restored the fix (`md5sum` byte-identical
confirmed) and re-ran: both green.

Full suite re-run after the fix:
```
DISPLAY=:99 CI=true /home/dev/.venvs/afk-clicker-test/bin/python \
  -m unittest discover -s tests -t .
```
`Ran 557 tests in 123.937s` / `OK (skipped=10)`, exit code 0 (555 from the
already-approved baseline + 2 new tests this round). Only pre-existing,
unrelated `ResourceWarning`s present (`test_updater.py`/`test_ui.py` file
handles), none for an unclosed X11/Xlib socket.

Targeted rerun, also green:
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest \
  tests.test_ui.WindowTitlesReusesXlibConnection -v
```
→ 7 tests, `OK`.

Per the task's scope instruction, nothing else was touched or re-litigated
this round (lock-scope crux, G#39, on_close ordering, win32/darwin,
import/skip guarding) — only Finding 1.

# Implementation: G#31/GH#54 — PR #52 follow-ups (comment correction + regression guard)

## Summary
Two follow-ups from the in-depth review of PR #52 (the GC-teardown fix for
the intermittent `Tcl_AsyncDelete` abort). Task 1 corrects the factually
wrong "only two places build and close a real UI" claim in
`tests/context.py` and `docs/history/ac-27-r3-implementation.md`. Task 2
adds a two-part regression guard so `gc.disable()` (or the mechanism it
protects) cannot be silently removed without a test failing — a direct
check (`gc.isenabled()`) plus an independent, stronger check that counts
the actual off-main-thread `Variable.__del__` symptom via
`sys.unraisablehook`, checked in `tearDownModule()`.

## Root cause
Not a bugfix — no production behavior changed. `afk_clicker.py` untouched.

## Task 1 — the "two places" claim, verified and corrected

The claim ("only two test classes build and close a real
`AfkAutoclicker`/`tk.Tk()`") is wrong. I enumerated every `tk.Tk()`
construction site in `tests/test_ui.py` (the only test module that touches
Tk at all — confirmed by grep across `tests/*.py`) and classified each by
its enclosing class:

**Already covered (call `gc.collect()` in their own `tearDown()`):**
- `UITestCase` (base class shared by 35 subclasses, e.g. `Sidebar`,
  `PerGameSettings`, `ClickLoop`, ...)
- `AppearanceThemeSwitch`

**Not covered — build and close a real UI without ever calling
`gc.collect()` (harmless today only because `gc.disable()` is
process-wide):**
- `PollGamesScanDoesNotHoldSelfWhileBlocked` (`tests/test_ui.py:274`) —
  builds a real `AfkAutoclicker`, closes via bare `root.destroy()`.
- `SetActiveThemeWidgets` (`tests/test_ui.py:1963`), via its `_build()`
  helper — builds a real `AfkAutoclicker`, closes via `addCleanup`.
- `StartupHonoursSavedAppearance` (`tests/test_ui.py:3783`) — builds a real
  `AfkAutoclicker` twice (once per test method), closes via `try/finally`.
- `CardShell` (`tests/test_ui.py:2413`) — bare `tk.Tk()`, no
  `AfkAutoclicker`, closed via `tearDown()`'s `root.destroy()`.
- `FillPaneOverflow` (`tests/test_ui.py:1391`) — bare `tk.Tk()`, no
  `AfkAutoclicker`.
- `SectionHeader` (`tests/test_ui.py:2291`) — bare `tk.Tk()`, no
  `AfkAutoclicker`.
- `FlatChrome` (`tests/test_ui.py:2248`) — bare `tk.Tk()`, no
  `AfkAutoclicker`.
- `RailAccent` (`tests/test_ui.py:2343`) — bare `tk.Tk()`, no
  `AfkAutoclicker`.
- `PrimaryButtonTheme` (`tests/test_ui.py:2390`) — bare `tk.Tk()`, no
  `AfkAutoclicker`.

That's 2 covered + 9 uncovered = 11 distinct classes that build and destroy
a real Tcl interpreter, not 2. The four the review named
(`PollGamesScanDoesNotHoldSelfWhileBlocked`, `SetActiveThemeWidgets`,
`StartupHonoursSavedAppearance`, `CardShell`) all checked out; I found four
more beyond that list (`FillPaneOverflow`, `SectionHeader`, `RailAccent`,
`PrimaryButtonTheme`) that build a bare `tk.Tk()` without an
`AfkAutoclicker` but still build and destroy a real interpreter, which is
the actual unit the mechanism (`gc.disable()`, a process-wide flag) cares
about — not specifically whether it's wrapped in `AfkAutoclicker`.

Corrected in two places, matching this repo's existing "Correction (...)"
convention for historical docs (see `docs/history/ac-24-f3-implementation.md`,
`ac-24-f3-spec.md`, `ac-17-f3a-implementation.md` for precedent — a
correction paragraph is appended in place rather than rewriting what was
actually written at the time):
- `tests/context.py` — reworded the comment to say `UITestCase.tearDown()`/
  `AppearanceThemeSwitch.tearDown()` are "the two places that happen to
  call `gc.collect()`", not the only two places a UI is built and closed,
  and named the other classes with a pointer to this doc.
- `docs/history/ac-27-r3-implementation.md` — added a "Correction (G#31/GH#54,
  PR #52 follow-up)" paragraph directly under the original wrong claim
  (Round 3, "What shipped"), listing the full set of classes found.

## Task 2 — regression guard

**What I chose:** two independent checks, not one.

1. **Direct check** — `GcAutomaticCollectionStaysDisabled` (new
   `unittest.TestCase` in `tests/test_ui.py`, placed right after
   `PollGamesScanDoesNotHoldSelfWhileBlocked` since both relate to the same
   G#27/GH#46 mechanism): asserts `gc.isenabled() is False`. Cheap
   (0.000s), deterministic, headless-safe (no display needed), and fails
   immediately the moment `gc.disable()` is removed or something calls
   `gc.enable()`.

2. **Stronger, independent check** — `tests/context.py` installs a
   `sys.unraisablehook` wrapper (alongside `gc.disable()`, at import time,
   chaining to the previous hook so default stderr reporting is
   unaffected) that increments a module-level counter
   (`context.MAIN_THREAD_UNRAISABLE_COUNT`) whenever an unraisable
   exception's message matches `"main thread is not in main loop"`. This is
   exactly the symptom the whole fix exists to prevent:
   `tkinter.Variable.__del__` (`/usr/lib/python3.11/tkinter/__init__.py:410`)
   has no internal `try`/`except` around its Tcl call, so a call from a
   non-main thread raises `RuntimeError`, which — since it happens inside
   `__del__` — becomes an unraisable exception routed through
   `sys.unraisablehook` rather than propagating normally. `tests/test_ui.py`'s
   new `tearDownModule()` asserts the counter is still 0 once the whole
   module has finished, and reports the count in its failure message if
   not.

   I checked this is not the theoretical "GC only" case: `afk_clicker.py`'s
   `_ui()` (`afk_clicker.py:3025-3032`) already documents and guards
   against every *legitimate* code path that could touch Tk off-thread
   (worker threads never call `root.after()` or read a `StringVar`
   directly), so this message, if it ever fires during a test run, has no
   other explanation in this codebase besides the exact GC-finalization
   race this ticket's mechanism controls.

   Why a counter + `tearDownModule()` rather than per-test: the symptom is
   process-wide — any test's worker thread can trip it, at any point in the
   run, independent of which test happens to be executing — so there is no
   single test to attach the assertion to. `tearDownModule()` is
   unittest's own guaranteed once-per-module hook, not dependent on test
   discovery order (unlike, e.g., naming a test to sort last
   alphabetically, which I considered and rejected as fragile).

   Considered and rejected: re-running the whole suite as a subprocess and
   grepping captured stderr for the count, mirroring the manual measurement
   technique from `docs/history/ac-27-r3-implementation.md`'s Round 3. This
   would work but roughly doubles the suite's wall-clock cost (spawns a
   second full run inside a "test") for no benefit over the in-process
   `sys.unraisablehook` counter, which observes the exact same events for
   free.

**Sabotage, to prove property 1 ("must actually fail")**: commented out
`gc.disable()` in `tests/context.py` and re-ran both checks.

- `python -m unittest tests.test_ui.GcAutomaticCollectionStaysDisabled -v`
  → `FAIL`: `AssertionError: True is not false : automatic GC is enabled...`
  — immediate, direct.
- `python -m unittest tests.test_ui -v` (full module) →
  `tearDownModule (tests.test_ui) ... ERROR` /
  `AssertionError: 71 off-main-thread Variable.__del__ RuntimeError(s)
  ('main thread is not in main loop') occurred during this run...` — the
  independent counter-based check also fires, and with a count (71) in the
  same range the original investigation measured (~55-57/285) for the
  unmodified-mechanism case, confirming it isn't a fluke.

Restored `tests/context.py` immediately after (confirmed via `diff` against
the intended committed version, and by re-running the direct test clean).

**Non-fragility, property 2**: ran the full suite 3 times back-to-back with
the mechanism intact — `293 tests ... OK (skipped=5)` every time, no
`RuntimeError` printed, no `tearDownModule` failure. (Baseline before this
change, same branch: 292 tests, same result — the +1 is the new
`GcAutomaticCollectionStaysDisabled` test.)

## Changes by file
- `tests/context.py` — corrected the `gc.disable()` comment (Task 1); added
  `MAIN_THREAD_UNRAISABLE_COUNT` and the `sys.unraisablehook` wrapper
  (Task 2).
- `tests/test_ui.py` — added `from . import context`; added
  `GcAutomaticCollectionStaysDisabled` test class; added `tearDownModule()`.
- `docs/history/ac-27-r3-implementation.md` — added a "Correction
  (G#31/GH#54, PR #52 follow-up)" paragraph under the original "two
  places" claim.

## Key decisions / tradeoffs
- Left `backlog.md`'s own "two places" wording alone — on inspection it
  only names the two `gc.collect()` call sites (which is true), not a claim
  that only two classes build/close a UI. No correction needed there.
- Placed the new test class in `test_ui.py` rather than a new file: it's
  small, thematically tied to the existing G#27/GH#46 tests in that module,
  and matches the existing convention of colocating GC-mechanism tests with
  the rest of the UI suite (`PollGamesScanDoesNotHoldSelfWhileBlocked` is
  already there for the same reason).
- The `sys.unraisablehook` wrapper chains to whatever hook was previously
  installed (`_previous_unraisablehook`, captured before overwriting)
  rather than replacing it outright, so any other unraisable-exception
  reporting (default: printing to stderr) keeps working exactly as before.

## Deviations from spec
None. Test-harness and documentation only; `afk_clicker.py` untouched;
`tests/test_chords_slow.py` untouched.

## Known limitations
- The counter-based guard (`MAIN_THREAD_UNRAISABLE_COUNT`) only observes
  events during the `tests.test_ui` module's own run, since it's checked in
  that module's `tearDownModule()`. If a future test module builds a Tk
  interpreter, it would need its own `tearDownModule()` check (or one could
  be added at the top-level `tests/__init__.py` instead) — not needed today
  since `test_ui.py` is the only module that touches Tk (confirmed by
  grep).
- The "two places" correction lists the classes found as of this review;
  it is not meant to be re-verified automatically — that's exactly what the
  new regression guard is for (it doesn't depend on this list staying
  accurate, since `gc.disable()` is process-wide).

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-31
VENV=<venv-python>   # e.g. the scratchpad venv with pynput installed
DISPLAY=:99 $VENV -m unittest discover -s tests -t .
# Expect: Ran 293 tests ... OK (skipped=5), no "RuntimeError: main thread
# is not in main loop" printed.

# Direct guard only:
DISPLAY=:99 $VENV -m unittest tests.test_ui.GcAutomaticCollectionStaysDisabled -v

# Sabotage (proves the guard actually fails):
sed -i 's/^gc\.disable()$/# gc.disable()/' tests/context.py
DISPLAY=:99 $VENV -m unittest tests.test_ui.GcAutomaticCollectionStaysDisabled -v   # FAILs
DISPLAY=:99 $VENV -m unittest tests.test_ui -v 2>&1 | tail -20                      # tearDownModule ERRORs, count > 0
git checkout -- tests/context.py   # restore
```

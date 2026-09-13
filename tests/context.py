"""
Shared setup for the test suite.

pynput resolves its backend at import time and raises without a display, so on
Linux the whole suite needs an X server -- CI runs it under xvfb-run. Importing
this module first also puts the project root on the path so the tests work from
any working directory.
"""
import gc
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# G#27/GH#46: test_ui.py builds and destroys roughly 140 separate tk.Tk()
# interpreters in this one process. A tkinter.Variable that outlives a
# test's on_close() (a real, still-open leak -- see
# docs/implementation.md's "Known limitations") only gets finalised
# whenever the interpreter-wide cyclic GC next runs, on whatever thread
# happens to be executing Python bytecode at that moment. If that thread is
# one of this app's own worker threads (the click loop, the hotkey
# listener), Variable.__del__ calls into Tcl from off the main thread and
# _tkinter's threading check rejects it -- "RuntimeError: main thread is
# not in main loop" (caught and printed by tkinter itself, ~55 times per
# full run), or, rarely, a fatal Tcl_AsyncDelete abort. Python's automatic
# collector runs on allocation-count thresholds it hits on whatever thread
# is running at the time, not on a schedule this suite controls, so leaving
# it enabled means it can and does fire mid-test, on a worker thread,
# before that test's own tearDown ever runs -- confirmed directly: adding
# an explicit gc.collect() only to UITestCase.tearDown() (still the
# main/test-running thread) left the RuntimeError count unchanged at
# ~55/run, because most occurrences happen before any tearDown() call, not
# after one. Disabling automatic collection here and collecting explicitly
# in UITestCase.tearDown() and AppearanceThemeSwitch.tearDown() -- the two
# places that happen to call gc.collect() -- keeps every collection that
# does happen on the thread that actually owns the interpreter, confirmed
# to collapse the count to 0/285 across repeated full-suite runs.
# Several *other* test classes in test_ui.py also build and close a real
# tk.Tk()/AfkAutoclicker without ever calling gc.collect() themselves (e.g.
# CardShell, SetActiveThemeWidgets, StartupHonoursSavedAppearance,
# PollGamesScanDoesNotHoldSelfWhileBlocked -- see G#31's review of this
# ticket for the fuller list) -- that is fine and does not need fixing:
# gc.disable() below is process-wide, so the fix's safety never depended on
# which class leaks or how many places explicitly collect. Scoped to the
# test suite only: the production app never creates more than one Tk() per
# process, so this leak pattern does not occur there, and disabling the
# app's own GC was never proposed or needed.
gc.disable()

# G#31/GH#54: guard against the above being silently undone (removing
# gc.disable(), re-enabling collection, or adding a new UI-building test
# class without a teardown collect). Without this, the abort would just
# start happening again -- intermittently, on CI only, which is exactly
# what made it take five attempts to characterise the first time (see
# docs/history/ac-27-r3-implementation.md). GcAutomaticCollectionStaysDisabled
# in test_ui.py checks the direct case (gc.isenabled()). This counter backs
# a second, independent check (test_ui.py's tearDownModule()): it tallies
# every unraisable exception whose message matches the exact symptom this
# fix exists to prevent, process-wide, for the life of the suite -- so a
# regression is caught even if something re-enables collection without
# touching the isenabled() flag checked above (e.g. a stray gc.enable()
# call inside a test).
MAIN_THREAD_UNRAISABLE_COUNT = 0
_previous_unraisablehook = sys.unraisablehook


def _count_main_thread_unraisable(unraisable):
    global MAIN_THREAD_UNRAISABLE_COUNT
    if "main thread is not in main loop" in str(unraisable.exc_value):
        MAIN_THREAD_UNRAISABLE_COUNT += 1
    _previous_unraisablehook(unraisable)


sys.unraisablehook = _count_main_thread_unraisable

# Only X11 needs DISPLAY. Windows and macOS have a window server either way,
# and treating them as headless would skip the entire suite there.
HEADLESS = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")

# Fail closed. A suite that skips everything and exits 0 is worse than no
# suite: it reports "OK (skipped=57)" and a pipeline believes it. On CI a
# missing display is a broken job, not a reason to pass.
if HEADLESS and os.environ.get("CI"):
    raise RuntimeError(
        "No X display on CI. pynput cannot import without one and the suite "
        "would skip every test while exiting 0. Run it under xvfb-run.")

needs_display = unittest.skipIf(HEADLESS, "no X display; run under xvfb-run")

if not HEADLESS:
    import afk_clicker as app
    from pynput import keyboard as kb
else:                                   # keep collection working without X
    app = kb = None


def record(key):
    return app._record(key)


def hotkey(mods, keys):
    return app.Hotkey(mods, [app._record(k) for k in keys])

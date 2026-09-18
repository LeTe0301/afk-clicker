"""The window: per-game settings, persistence, detection and the click loop."""
import gc
import json
import os
import subprocess
import sys
import threading
import tempfile
import time
import traceback
import types
import unittest
import urllib.parse
import weakref

from . import context
from .context import app, kb, needs_display, hotkey

if app is not None:
    import tkinter as tk
    from tkinter import font as tkfont


class FakeMouse:
    """Records what the loop asked for instead of moving a real pointer."""

    def __init__(self):
        self.clicks = []
        self.pressed = []

    def click(self, button):
        self.clicks.append((button, time.monotonic()))

    def press(self, button):
        self.pressed.append(("press", button))

    def release(self, button):
        self.pressed.append(("release", button))


class CapturesCallbackExceptions:
    """Mixed into a TestCase: fails the test if Tk's own dispatcher ever had
    to fall back to report_callback_exception -- an uncaught exception
    inside a bound command, a variable trace, an after()/after_idle() job,
    or a <Configure> handler. Tk's default report_callback_exception just
    prints "Exception in Tkinter callback" plus the traceback to stderr and
    otherwise carries on, so a test that never looks at stderr can pass
    clean next to a real, swallowed crash -- exactly how
    docs/history/ac-17-f3a-test-review.md's Defect 1 escaped the suite the first time. See
    docs/history/ac-17-f3a-implementation.md "Round 2" for why this replaces a raw
    redirect_stderr: it only ever catches genuine Tk callback exceptions,
    never unrelated stderr noise."""

    def _capture_callback_exceptions(self, root):
        self._callback_exceptions = []
        root.report_callback_exception = \
            lambda exc, val, tb: self._callback_exceptions.append((exc, val, tb))

    def _assert_no_callback_exceptions(self):
        if not self._callback_exceptions:
            return
        exc, val, tb = self._callback_exceptions[0]
        formatted = "".join(traceback.format_exception(exc, val, tb))
        self.fail(
            f"{len(self._callback_exceptions)} uncaught Tkinter callback "
            f"exception(s) during the test; first:\n{formatted}")


@needs_display
class UITestCase(CapturesCallbackExceptions, unittest.TestCase):
    # G#38/GH#67 round 3 (PR #89 review, macOS/Windows CI regression): a
    # subclass whose own tests assume a plain geometry() call/scale change
    # moves self.s by a known, fixed amount (WindowResize/RailCollapse/
    # UIScale -- generic resize/fixed-step mechanics that predate Auto,
    # per docs/spec.md's own non-goal "non-Auto resize handling...
    # unchanged") sets this to a UI_SCALE_FACTORS key to construct
    # self.ui directly at that step, bypassing Auto's own construction-time
    # convergence (and the real-WM round-trip it depends on) entirely --
    # not just switching to it *after* construction, which still races a
    # real window manager's own async confirmation of whatever Auto's
    # bootstrap already put in flight. Left None (the default) for every
    # other class, which keeps exercising the real fresh-install default.
    INITIAL_UI_SCALE = None

    def setUp(self):
        self.config = os.path.join(tempfile.mkdtemp(), "settings.json")
        if self.INITIAL_UI_SCALE is not None:
            with open(self.config, "w") as fh:
                json.dump({"ui_scale": self.INITIAL_UI_SCALE}, fh)
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.settle()
        # G#38/GH#67 round 3: on a real window manager, construction can
        # still arm a genuine Auto-mode settle timer (self.s correcting to
        # the real screen, docs/spec.md's own "first launch on an unusual
        # screen" edge case) -- settle() above already gives that real WM
        # plenty of wall-clock time to deliver its own post-map
        # <Configure>, so if a settle job got armed from it, wait for it to
        # actually fire and finish here rather than mid a test body. Every
        # fresh fixture shares this exposure now, not just UIScaleAuto's
        # own tests, since UI_SCALE_DEFAULT is "auto" -- this is what was
        # tearing down/rebuilding other, unrelated tests' widget trees out
        # from under them on PR #89's macOS/Windows CI legs. A no-op for
        # any class using INITIAL_UI_SCALE above, since Auto is never
        # entered there at all.
        if self.ui._auto_settle_after_id is not None:
            self.pump_until(lambda: self.ui._auto_settle_after_id is None,
                             timeout=app.AUTO_SETTLE_MS / 1000 + 1.0)
        # Under Xvfb with no window manager, a freshly created tk.Tk() never
        # actually owns X input focus, so focus_set() alone produces no
        # <FocusIn>/<FocusOut> and focus_get() reads None no matter what.
        # This one-time focus_force() makes the toplevel genuinely own input
        # focus so every focus_set()-based assertion below observes something
        # -- the app itself keeps using focus_set(), never focus_force().
        self.root.focus_force()

    def tearDown(self):
        # G#27/GH#46: pairs with context.py's gc.disable() -- see the
        # comment there for the full mechanism and measurements. With
        # automatic collection off for the whole suite, this explicit
        # collect() is the only place a Variable orphaned by this test's
        # on_close() gets finalised, and it always runs on the
        # main/test-running thread, which is exactly what avoids the
        # off-thread Variable.__del__ ("RuntimeError: main thread is not
        # in main loop", or, rarely, a fatal Tcl_AsyncDelete abort).
        try:
            self.ui.on_close()
        except tk.TclError:
            pass
        gc.collect()
        self._assert_no_callback_exceptions()

    def settle(self, timeout=15.0):
        """
        Wait for the startup game scan to land.

        _poll_games runs on a thread during construction and hands its result
        to the UI queue; _drain_ui's 40 ms timer then delivers it inside
        whatever root.update() happens to run next -- including one inside a
        test, after that test has set the state it is about to assert on.
        Pinning _seen_running addressed a different assertion and left this.

        _seen_running only exists once _mark_running has run, so it is the
        signal to wait for rather than a sleep long enough to hope.

        The 15s ceiling (not 5s) exists for a slow macOS CI runner: the scan
        shells out to osascript, and a cold `osascript` start on a loaded
        shared runner was observed timing out setUp() at 5s (PR #30 review
        round 1, PerGameSettings::test_survives_a_restart). Costs nothing
        when the scan is fast -- this returns the instant _seen_running
        appears, it never waits out the full ceiling on a normal run.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if hasattr(self.ui, "_seen_running"):
                return
            time.sleep(0.02)
        self.fail("the startup game scan never landed")

    def pump(self, seconds):
        """
        Run Tk's loop -- after() work, including the snapshot, only runs here.

        The sleep is 25 ms rather than 10: a tighter loop spends most of its
        time holding the GIL inside root.update(), which starves the clicking
        thread and shows up as an interval that looks slower than it is.
        """
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.025)

    def pump_until(self, predicate, timeout=3.0):
        """
        Pump in small steps until `predicate()` is true, instead of a fixed
        sleep long enough to hope.

        Anything that reaches Tk through _ui() -- a background thread's
        start(), a capture thread's result -- only lands inside a
        root.update() call, on _drain_ui's 40 ms timer. A fixed pump()
        assumes that timer wins the GIL against whatever else is running
        within the window given; on a loaded shared runner it sometimes
        doesn't. Returns without failing if the predicate never becomes
        true, so the caller's own assertion still reports the regression.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(0.02)

    def restart(self):
        self.ui.on_close()
        self.root = tk.Tk()
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        return self.ui

    def _appearance_segment(self, var=None):
        """The Appearance Segmented control on the (already open) Settings
        page -- shared by SettingsNavigation and OverlappingAppearanceChanges
        (docs/history/ac-17-f3a-pr30-review.md's Finding #4: was a byte-identical
        duplicate in each). `var` defaults to `self.ui.appearance_var`;
        pass `self.ui.ui_scale_var` (or any other Segmented-bound var on the
        page) to locate a different control without a second copy of this
        walk (docs/history/ac-17-f4-implementation.md Finding #1)."""
        if var is None:
            var = self.ui.appearance_var
        def walk(widget):
            if isinstance(widget, app.Segmented) and widget.var is var:
                return widget
            for child in widget.winfo_children():
                found = walk(child)
                if found is not None:
                    return found
            return None
        found = walk(self.ui.content)
        self.assertIsNotNone(found, "no matching Segmented control found")
        return found


class Sidebar(UITestCase):
    def test_lists_the_builtin_profiles(self):
        self.assertEqual(set(self.ui.items), {"minecraft", "global"})

    def test_running_dot_and_follow(self):
        self.ui._seen_running = set()
        self.ui._mark_running({"minecraft"})
        self.root.update()
        self.assertTrue(self.ui.items["minecraft"].running)
        self.assertFalse(self.ui.items["global"].running)
        self.assertEqual(self.ui.current, "minecraft")
        self.assertEqual(self.ui.game_state.cget("text"), "running")

    def test_a_hand_picked_profile_is_not_overridden(self):
        # Following the game once is helpful; doing it every five seconds
        # would fight the user.
        self.ui._seen_running = set()
        self.ui._mark_running({"minecraft"})
        self.ui._select("global")
        self.ui._mark_running({"minecraft"})
        self.assertEqual(self.ui.current, "global")


class PerGameSettings(UITestCase):
    def test_defaults_differ_per_profile(self):
        self.ui._select("minecraft")
        self.assertEqual(self.ui.click_ms.var.get(), "650")
        self.ui._select("global")
        self.assertEqual(self.ui.click_ms.var.get(), "250")

    def test_eating_panel_is_minecraft_only(self):
        self.ui._select("minecraft")
        self.assertNotEqual(self.ui.eat_card.winfo_manager(), "")
        self.ui._select("global")
        self.assertEqual(self.ui.eat_card.winfo_manager(), "")
        self.assertEqual(self.ui.eat_mode.get(), "off")

    def test_values_are_kept_apart(self):
        self.ui._select("minecraft")
        self.ui.click_ms.var.set("444")
        self.pump(0.2)
        self.ui._select("global")
        self.ui.click_ms.var.set("120")
        self.pump(0.2)
        self.ui._select("minecraft")
        self.assertEqual(self.ui.click_ms.var.get(), "444")
        self.ui._select("global")
        self.assertEqual(self.ui.click_ms.var.get(), "120")

    def test_survives_a_restart(self):
        self.ui._select("minecraft")
        self.ui.click_ms.var.set("444")
        self.pump(0.2)
        ui = self.restart()
        ui._select("minecraft")
        self.assertEqual(ui.click_ms.var.get(), "444")

    def test_integral_values_do_not_gain_a_decimal_point(self):
        # Values round-trip through float() on save; "510.0" in a field reads
        # like a bug.
        self.ui._select("minecraft")
        self.pump(0.2)
        ui = self.restart()
        ui._select("minecraft")
        self.assertEqual(ui.click_ms.var.get(), "650")


class AddedGames(UITestCase):
    def test_added_game_persists(self):
        self.ui._add_game("Some Other Game")
        self.assertIn("custom:some other game", self.ui.items)
        self.assertEqual(self.ui.current, "custom:some other game")
        self.ui.click_ms.var.set("77")
        self.pump(0.2)
        ui = self.restart()
        self.assertIn("custom:some other game", ui.items)
        ui._select("custom:some other game")
        self.assertEqual(ui.click_ms.var.get(), "77")

    def test_no_window_is_reported(self):
        self.ui._add_game(None)
        self.assertEqual(self.ui.game_state.cget("text"), "no window found")


class PollGamesScanDoesNotHoldSelfWhileBlocked(unittest.TestCase):
    def test_scan_only_holds_profiles_not_self_during_detect_running(self):
        # _poll_games()'s scan() thread used to close over self directly.
        # detect_running() -> _window_titles() opens a fresh Xlib connection
        # every call, and that connection setup can genuinely stall (seen in
        # this suite: one scan out of every couple hundred, stuck inside
        # Xlib.display.Display() itself -- see docs/implementation.md). A
        # scan still in flight kept the whole AfkAutoclicker -- and every
        # tkinter.Variable it owns -- reachable for as long as that thread
        # had not returned, however long that turned out to be. Whichever
        # thread eventually dropped that reference (or merely ran a GC pass
        # while still holding it) was not necessarily the main one, which
        # is how a stale Variable gets finalized off the main thread and
        # aborts the interpreter ("Tcl_AsyncDelete: async handler deleted
        # by the wrong thread").
        #
        # This checks the fix directly, at the point scan()'s own frame is
        # paused inside the (mocked, blocking) detect_running() call, by
        # inspecting that frame's locals -- rather than going through
        # AfkAutoclicker.on_close() and a whole-object gc.collect(), which
        # docs/implementation.md's "Known limitations" section explains is
        # its own, separate source of non-determinism in this suite (traced
        # to a real, reproducible interaction with unrelated preceding
        # tests, not to this fix) and not something a reliable regression
        # test can be built on right now.
        entered = threading.Event()
        release = threading.Event()
        seen_locals = {}

        def fake_detect_running(profiles):
            frame = sys._getframe(1)   # scan()'s own frame, still on the stack
            seen_locals.update(frame.f_locals)
            entered.set()
            release.wait(5)
            return set()

        original = app.detect_running
        app.detect_running = fake_detect_running
        config = os.path.join(tempfile.mkdtemp(), "settings.json")
        root = tk.Tk()
        try:
            ui = app.AfkAutoclicker(root, store=app.Store(config))
            root.update()
            self.assertTrue(entered.wait(5), "scan thread never reached detect_running")
            self.assertNotIn(
                "me", seen_locals,
                "scan() must not hold a strong ref to the UI while "
                "detect_running() blocks")
            self.assertIn("profiles", seen_locals)
        finally:
            release.set()
            app.detect_running = original
            try:
                root.destroy()
            except tk.TclError:
                pass


class GcAutomaticCollectionStaysDisabled(unittest.TestCase):
    """G#31/GH#54: nothing else in this suite fails if someone removes
    context.py's gc.disable() or otherwise re-enables automatic collection.
    The abort that mechanism prevents would just start happening again --
    intermittently, on CI only, which is exactly what made it take five
    attempts to characterise the first time (docs/history/
    ac-27-r3-implementation.md's Round 3). This is the direct half of the
    guard: the one process-wide flag the whole fix rests on. tearDownModule()
    below is the independent half -- it fails if the actual symptom (an
    off-main-thread Variable.__del__ RuntimeError) is ever observed anywhere
    in this module's run, not just if this flag gets flipped back on."""

    def test_automatic_collection_is_disabled_for_the_whole_suite(self):
        self.assertFalse(
            gc.isenabled(),
            "automatic GC is enabled -- context.py's gc.disable() was "
            "removed, or something re-enabled collection. This reintroduces "
            "an intermittent, CI-only interpreter abort; see "
            "docs/history/ac-27-r3-implementation.md's Round 3.")


class CorruptConfig(UITestCase):
    def test_damaged_file_is_not_fatal(self):
        with open(self.config, "w") as fh:
            fh.write("{ this is not json")
        self.assertIsInstance(app.Store(self.config).data.get("games"), dict)


class StoreSaveResult(unittest.TestCase):
    """G#21/GH#32 item 4: Store.save() used to swallow every OSError with a
    bare `except OSError: pass`, returning None either way -- every one of
    its five call sites had no way to tell a successful write from a
    silently failed one. Now it returns True/False; nothing about the
    on-disk write itself (still atomic via os.replace, still starts from
    defaults on a corrupt file) changes. No UI/Tk fixture needed here --
    Store has no knowledge of the UI, and this only exercises its own
    return value (tests/test_ui.py:DetectOsTheme's monkeypatch-and-restore
    style, no unittest.mock)."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "settings.json")

    def test_a_successful_save_returns_true(self):
        store = app.Store(self.path)
        self.assertTrue(store.save())
        with open(self.path, encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertEqual(on_disk["appearance"], "system")

    def test_a_failed_save_returns_false_and_does_not_raise(self):
        store = app.Store(self.path)
        original_replace = app.os.replace

        def raising_replace(*a, **kw):
            raise OSError("read-only filesystem")

        app.os.replace = raising_replace
        try:
            self.assertFalse(store.save())
        finally:
            app.os.replace = original_replace

    def test_put_game_returns_saves_own_result(self):
        store = app.Store(self.path)
        self.assertTrue(store.put_game("global", {"click_ms": 700}))

        def raising_replace(*a, **kw):
            raise OSError("nope")

        original_replace = app.os.replace
        app.os.replace = raising_replace
        try:
            self.assertFalse(store.put_game("global", {"click_ms": 800}))
        finally:
            app.os.replace = original_replace


class StoreMigration(UITestCase):
    """
    The old 510 ms default auto-saved itself the first time Minecraft was
    ever detected -- see the migration comment in Store.__init__ -- so a
    stored 510 is not evidence anyone chose it on purpose. These tests write
    the raw settings file directly and load a fresh Store; the UI built by
    setUp is not exercised.
    """

    def _write(self, data):
        with open(self.config, "w") as fh:
            json.dump(data, fh)

    def test_the_old_default_is_migrated(self):
        self._write({"games": {"minecraft": {"click_ms": 510}}})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"]["minecraft"]["click_ms"], 650)

    def test_a_tuned_value_is_left_alone(self):
        for click_ms in (600, 700, 510.5):
            with self.subTest(click_ms=click_ms):
                self._write({"games": {"minecraft": {"click_ms": click_ms}}})
                store = app.Store(self.config)
                self.assertEqual(
                    store.data["games"]["minecraft"]["click_ms"], click_ms)

    def test_only_the_minecraft_profile_is_touched(self):
        self._write({"games": {
            "global": {"click_ms": 510},
            "custom:some other game": {"click_ms": 510},
        }})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"]["global"]["click_ms"], 510)
        self.assertEqual(
            store.data["games"]["custom:some other game"]["click_ms"], 510)

    def test_a_missing_games_key_starts_from_defaults(self):
        self._write({"hotkey": None, "selected": None})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"], {})

    def test_a_corrupt_file_starts_from_defaults(self):
        with open(self.config, "w") as fh:
            fh.write("{ this is not json")
        store = app.Store(self.config)
        self.assertEqual(store.data["games"], {})

    def test_a_null_minecraft_entry_does_not_crash_the_load(self):
        self._write({"games": {"minecraft": None}})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"].get("minecraft", {}), {})

    def test_a_non_dict_games_value_does_not_crash_the_load(self):
        self._write({"games": "oops"})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"], {})

    def test_a_list_minecraft_entry_does_not_crash_the_load(self):
        self._write({"games": {"minecraft": []}})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"].get("minecraft", {}), {})

    def test_a_string_click_ms_is_not_mistaken_for_the_old_default(self):
        # "510" is not the int/float 510 -- an exact-match migration must
        # leave it alone rather than coerce-and-compare.
        self._write({"games": {"minecraft": {"click_ms": "510"}}})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"]["minecraft"]["click_ms"], "510")

    def test_the_migration_is_a_no_op_on_the_next_load(self):
        # load, save, load again -- once the corrected value has been
        # written back the same way the old default was, a second load
        # finds 650 already on disk and the equality check no-ops.
        self._write({"games": {"minecraft": {"click_ms": 510}}})
        store = app.Store(self.config)
        self.assertEqual(store.data["games"]["minecraft"]["click_ms"], 650)
        store.save()
        on_disk = json.load(open(self.config))
        self.assertEqual(on_disk["games"]["minecraft"]["click_ms"], 650)
        store2 = app.Store(self.config)
        self.assertEqual(store2.data["games"]["minecraft"]["click_ms"], 650)


class ClickLoop(UITestCase):
    def setUp(self):
        super().setUp()
        self.ui.mouse = FakeMouse()
        self.ui._select("global")

    def run_for(self, seconds):
        self.ui.mouse.clicks.clear()
        self.ui.mouse.pressed.clear()
        self.pump(0.3)                      # let the snapshot catch up
        self.ui.start()
        self.pump(seconds)
        self.ui.stop()
        self.pump(0.3)
        return list(self.ui.mouse.clicks)

    def test_each_mouse_button(self):
        self.ui.click_ms.var.set("100")
        for name in ("left", "right", "middle"):
            with self.subTest(button=name):
                self.ui.button_name.set(name)
                clicks = self.run_for(0.6)
                self.assertTrue(clicks)
                # The enum is imported as MouseButton but is still named
                # Button, so compare the member rather than its repr.
                self.assertIs(clicks[0][0], getattr(app.MouseButton, name))

    def _gaps(self, seconds):
        clicks = self.run_for(seconds)
        gaps = [b[1] - a[1] for a, b in zip(clicks, clicks[1:])]
        self.assertTrue(gaps, "no clicks were produced")
        return gaps

    # Timing on the macOS runner does not hold: measured medians of 0.251 s
    # and 0.283 s for a 200 ms interval across two runs, while Linux sits at
    # 0.2001 s over 16 consecutive runs. Skipped there with the investigation
    # tracked, rather than weakened everywhere -- a bound loosened until it
    # stops failing stops asking the question. See issue #6.
    #
    # Investigated a second time 2026-09-18, no new lead found, closed again
    # as accept-and-document (backlog.md, G#4/GH#6):
    #   - self.ui.mouse is FakeMouse here (see its class above), which never
    #     makes a real OS call. So this overshoot cannot be pynput's macOS
    #     click backend (Quartz/CGEventPost) -- it's pure Python-level
    #     thread-scheduling precision (_sleep()'s worker thread racing this
    #     test's own pump() for the GIL), on identical, unbranched code.
    #   - The 2026-09-09 cycle already tried loosening pump()'s own cadence
    #     on a GIL-contention theory (see pump()'s docstring above); that
    #     made the median *worse* (0.251 -> 0.283 s), ruling out "the test's
    #     own polling is too tight" as the mechanism.
    #   - GitHub's own actions/runner-images repo has many long-running,
    #     acknowledged macos-latest performance-degradation reports (2-10x
    #     slower than expected, unrelated to any specific workload), ongoing
    #     well past this ticket's filing -- consistent with a throttled/
    #     oversubscribed shared runner rather than a defect in this loop.
    # None of this rules out real macOS hardware also being ~25-40% coarser
    # than Linux at this granularity -- that needs an actual Mac, which this
    # project has never had access to. No further lead to chase from the code
    # or CI logs alone, and no safe code change to make on a guess.
    darwin_timing = unittest.skipIf(
        __import__("sys").platform == "darwin",
        "macOS runner timing unattributed -- see issue #6")

    @darwin_timing
    def test_interval_is_honoured(self):
        self.ui.button_name.set("left")
        self.ui.click_ms.var.set("200")
        self.ui.jitter_ms.var.set("0")
        gaps = sorted(self._gaps(1.6))
        # The median, not the mean. A shared runner throws in the occasional
        # long gap, which drags a mean far enough that the bound has to be
        # loosened until a systematically slow loop fits inside it too. The
        # median ignores those spikes, so it can stay tight enough to catch
        # one: 0.27 s (35% slow) fails this, 0.2 s with a few stalls does not.
        median = gaps[len(gaps) // 2]
        self.assertLess(abs(median - 0.2), 0.035,
                        f"median gap {median:.3f}s for a 200 ms interval")

    @darwin_timing
    def test_jitter_widens_the_spread(self):
        # Relative, not absolute. A shared CI runner adds scheduling delays of
        # its own -- macOS showed a 100 ms spread with jitter switched off --
        # so an absolute steadiness bound measures the runner, not the code.
        # What must hold is that jitter spreads the interval noticeably more
        # than the machine's own noise does.
        self.ui.button_name.set("left")
        self.ui.click_ms.var.set("200")
        self.ui.jitter_ms.var.set("0")
        steady = max(g := self._gaps(1.6)) - min(g)
        self.ui.jitter_ms.var.set("80")
        jittered = max(g := self._gaps(1.6)) - min(g)
        self.assertGreater(jittered, steady + 0.04,
                           f"jitter spread {jittered:.3f}s vs steady {steady:.3f}s")

    def test_auto_stop(self):
        self.ui.click_ms.var.set("100")
        self.ui.autostop_min.var.set(str(1.5 / 60))
        self.pump(0.3)
        self.ui.start()
        started = time.monotonic()
        while self.ui.running and time.monotonic() - started < 6:
            self.root.update()
            time.sleep(0.05)
        self.assertFalse(self.ui.running)
        self.assertLess(time.monotonic() - started, 3.5)

    def test_auto_stop_zero_means_never(self):
        self.ui.click_ms.var.set("100")
        self.ui.autostop_min.var.set("0")
        self.pump(0.3)
        self.ui.start()
        self.pump(1.0)
        self.assertTrue(self.ui.running)
        self.ui.stop()
        self.pump(0.2)

    def test_eating_pause_only_applies_to_the_left_button(self):
        self.ui._select("minecraft")
        self.ui.eat_mode.set("pause")
        self.ui.eat_every.var.set("5")
        self.ui.eat_hold.var.set("0.5")
        self.ui.click_ms.var.set("100")
        self.ui.button_name.set("right")
        self.run_for(6.0)
        self.assertFalse(self.ui.mouse.pressed)

    def test_the_right_button_is_always_released(self):
        self.ui._select("minecraft")
        self.ui.eat_mode.set("pause")
        self.ui.eat_every.var.set("5")
        self.ui.eat_hold.var.set("0.5")
        self.ui.click_ms.var.set("100")
        self.ui.button_name.set("left")
        self.run_for(7.0)
        pressed = self.ui.mouse.pressed
        self.assertTrue(any(p[0] == "press" for p in pressed))
        self.assertEqual(pressed.count(("press", app.MouseButton.right)),
                         pressed.count(("release", app.MouseButton.right)))


class NumericClamping(UITestCase):
    """`_num` is the only thing standing between a typo and the click loop."""

    def test_below_the_floor_is_clamped(self):
        self.ui._select("global")
        self.ui.click_ms.var.set("1")
        # 50 ms is the floor; without the clamp this returns 1 and the loop
        # spins at a thousand clicks a second.
        self.assertEqual(self.ui._num(self.ui.click_ms, 250, 50), 50)

    def test_garbage_falls_back(self):
        for text in ("", "abc", "-", "1.2.3", "  "):
            with self.subTest(text=text):
                self.ui.click_ms.var.set(text)
                self.assertEqual(self.ui._num(self.ui.click_ms, 250, 50), 250)

    def test_a_sane_value_is_left_alone(self):
        self.ui.click_ms.var.set("510")
        self.assertEqual(self.ui._num(self.ui.click_ms, 250, 50), 510)

    def test_the_clamp_reaches_the_loop(self):
        self.ui._select("global")
        self.ui.mouse = FakeMouse()
        self.ui.click_ms.var.set("1")
        self.pump(0.4)
        self.ui.start()
        self.pump(0.6)
        self.ui.stop()
        self.pump(0.3)
        clicks = self.ui.mouse.clicks
        # 0.6 s at the 50 ms floor is around a dozen clicks; unclamped it
        # would be hundreds.
        self.assertLess(len(clicks), 40, f"{len(clicks)} clicks -- floor not applied")


class ButtonRelease(UITestCase):
    """`loop()` releases the right button in a `finally`. Prove it matters."""

    def test_stopping_in_hold_mode_releases_the_right_button(self):
        # "Hold RMB" is the path the finally actually guards: the button is
        # pressed once and never released inside the loop body, so stopping
        # breaks straight out and only the finally can let go. In game a stuck
        # right button means blocking forever.
        self.ui._select("minecraft")
        self.ui.mouse = FakeMouse()
        self.ui.eat_mode.set("hold")
        self.ui.click_ms.var.set("100")
        self.pump(0.4)
        self.ui.start()
        self.pump(0.8)
        self.assertIn(("press", app.MouseButton.right), self.ui.mouse.pressed)
        self.ui.stop()
        self.pump(1.0)
        self.assertEqual(
            self.ui.mouse.pressed.count(("press", app.MouseButton.right)),
            self.ui.mouse.pressed.count(("release", app.MouseButton.right)),
            "the right button was left held down after stopping")
        self.assertFalse(self.ui.right_held)

    def test_an_exception_in_the_loop_still_releases(self):
        # The other half of the finally's job. A raising mouse leaves the loop
        # through the exception path, where nothing else can clean up.
        self.ui._select("minecraft")

        class ExplodingMouse(FakeMouse):
            def click(self, button):
                raise RuntimeError("boom")

        self.ui.mouse = ExplodingMouse()
        self.ui.eat_mode.set("hold")
        self.ui.click_ms.var.set("100")
        self.pump(0.4)
        self.ui.start()
        self.pump(1.2)
        self.assertFalse(self.ui.right_held, "right button left held after a crash")
        self.assertEqual(
            self.ui.mouse.pressed.count(("press", app.MouseButton.right)),
            self.ui.mouse.pressed.count(("release", app.MouseButton.right)))
        self.ui.stop()
        self.pump(0.2)


class InstallWorker(UITestCase):
    """
    `_install_worker` end to end, not just the module-level helpers it calls.

    AC1/AC2/AC4/AC6 are written at the level of "the install path" / "the
    user" -- the wired-up AfkAutoclicker flow -- so a test that only calls
    download_and_stage directly cannot cover the fail-closed branch or the
    truncated status line the user actually sees. `_install_worker` is called
    directly rather than through a thread: it never touches Tk except via
    self._ui(), so calling it inline on the test thread is safe, and it makes
    the assertions below deterministic instead of racing a background thread.
    """

    def _drain(self):
        # _install_worker only ever queues UI updates through self._ui();
        # _drain_ui() is what turns those into real widget state. It is
        # normally reached via the 40 ms timer started in __init__ -- call it
        # directly here rather than waiting on the clock.
        self.ui._drain_ui()

    def _button_text(self):
        return self.ui.update_button.itemcget(self.ui.update_button.label, "text")

    def test_a_release_without_checksums_is_refused_and_nothing_is_downloaded(self):
        # AC4: a release that publishes no SHA256SUMS is refused, fail
        # closed, and download_and_stage is never reached -- not just
        # pick_checksums(release) is None at the unit level.
        calls = []
        original = app.download_and_stage
        app.download_and_stage = lambda *a, **k: calls.append((a, k))
        try:
            # update_button now lives on the Settings page (Feature 3b) --
            # open it first so it exists for _drain() to touch.
            self.ui._show_settings()
            self.root.update()
            release = {"assets": [
                {"name": "Clickwork-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
            self.ui._pending = ("v9.9.9", release["assets"][0], release)
            self.ui._install_worker()
            self._drain()
        finally:
            app.download_and_stage = original
        self.assertEqual(calls, [], "download_and_stage was called despite no SHA256SUMS")
        self.assertIn("SHA256SUMS", self._button_text())
        self.assertTrue(self.ui.update_button._enabled, "the button was left disabled after a refusal")

    def test_a_checksum_error_reaches_the_status_line_with_its_meaning_intact(self):
        # AC6, driven through the real worker rather than by calling
        # download_and_stage directly -- this is the path that would have
        # caught the truncated "is not listed" message before it shipped.
        # The network is mocked (fetch_checksums, download_and_stage); this
        # test never reaches GitHub.
        def fake_fetch(asset, timeout=30):
            return {}

        def fake_stage(asset, checksums, on_progress=None):
            raise app.ChecksumError(
                f"checksum: not in {app.CHECKSUM_ASSET}: {asset['name']}")

        original_fetch, original_stage = app.fetch_checksums, app.download_and_stage
        app.fetch_checksums, app.download_and_stage = fake_fetch, fake_stage
        try:
            # update_button now lives on the Settings page (Feature 3b) --
            # open it first so it exists for _drain() to touch.
            self.ui._show_settings()
            self.root.update()
            release = {"assets": [
                {"name": "SHA256SUMS", "browser_download_url": "x"},
                {"name": "Clickwork-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
            self.ui._pending = ("v9.9.9", release["assets"][1], release)
            self.ui._install_worker()
            self._drain()
        finally:
            app.fetch_checksums, app.download_and_stage = original_fetch, original_stage
        shown = self._button_text().lower()
        self.assertIn("checksum", shown,
                       f"status line {shown!r} does not read as a checksum failure")
        self.assertTrue(self.ui.update_button._enabled, "the button was left disabled after a refusal")

    def _install_worker_with_tag(self, tag):
        """Drives _install_worker() all the way to its write_swap_script()
        call with checksums/staging faked out, capturing the
        target_version it was actually called with -- the network is
        mocked (fetch_checksums, download_and_stage, write_swap_script);
        this never reaches GitHub or writes a real script to disk."""
        calls = []

        def fake_write_swap_script(staged, target, relaunch, log_path, target_version=None):
            calls.append(target_version)
            return "/tmp/does-not-exist-fake-script"

        original_fetch = app.fetch_checksums
        original_stage = app.download_and_stage
        original_write = app.write_swap_script
        app.fetch_checksums = lambda asset, timeout=30: {"x": "y"}
        app.download_and_stage = lambda asset, checksums, on_progress=None: "/tmp/fake-staged"
        app.write_swap_script = fake_write_swap_script
        try:
            release = {"assets": [
                {"name": "SHA256SUMS", "browser_download_url": "x"},
                {"name": "Clickwork-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
            self.ui._pending = (tag, release["assets"][1], release)
            self.ui._install_worker()
        finally:
            app.fetch_checksums = original_fetch
            app.download_and_stage = original_stage
            app.write_swap_script = original_write
        return calls

    def test_a_shell_metacharacter_tag_never_reaches_write_swap_script(self):
        # Security review, PR #72: tag_name is untrusted network input
        # (GitHub API), and before this fix flowed straight into the
        # generated update script as target_version -- proven live that a
        # tag of '$(touch .../PWNED)' survives the .sh path's own
        # single-`\"`-escaping (POSIX double quotes don't stop $()/
        # backtick command substitution) and executes on relaunch. Every
        # shape tried here must come out as target_version=None (write_
        # swap_script's own existing "version unknown" default), never
        # the raw tag.
        dangerous_tags = [
            '$(touch /tmp/afk-clicker-test-pwned)',
            'v1.0.0`touch /tmp/x`',
            'v1.0.0"; touch /tmp/x; "',
            'v1.0.0 && touch /tmp/x',
            'v1.0.0 | touch /tmp/x',
        ]
        for tag in dangerous_tags:
            with self.subTest(tag=tag):
                calls = self._install_worker_with_tag(tag)
                self.assertEqual(calls, [None],
                                 f"dangerous tag {tag!r} reached write_swap_script unrejected")

    def test_an_oversized_tag_never_reaches_write_swap_script(self):
        calls = self._install_worker_with_tag("v" + "9" * 40 + ".0.0")
        self.assertEqual(calls, [None])

    def test_a_normal_release_tag_still_reaches_write_swap_script_unchanged(self):
        # The fix must not turn every real release into "version unknown".
        calls = self._install_worker_with_tag("v0.7.0")
        self.assertEqual(calls, ["v0.7.0"])


class NumBoxFocus(UITestCase):
    """A field keeps eating keystrokes until something explicitly drops focus."""

    # G#38/GH#67 round 3 (PR #89 review): unrelated to ui_scale, but a
    # fresh fixture now boots in Auto mode by default -- on a real window
    # manager, Auto's own construction-time self-correction to the real
    # screen (docs/spec.md's own "first launch" edge case) can still land
    # mid this class's own focus assertions. Pinned the same way
    # WindowResize/RailCollapse/UIScale already are.
    INITIAL_UI_SCALE = "100"

    def focus_and_settle(self, numbox):
        # focus_set()/event_generate() are no-ops on a widget inside an
        # unmapped ancestor (docs/spec.md's "Test impact", finding 1/2) --
        # every NumBox this class exercises lives in the Clicking pane,
        # while Hotkey is the default-active tab (story #24 feature 2), so
        # a real user has to click Clicking first before any entry inside
        # it can take real keyboard focus. Switching the tab directly
        # (rather than a real TabBar click) is enough here: the pane-
        # visibility contract itself is covered separately by
        # TabBarNavigation.
        self.ui._set_content_tab("clicking")
        self.root.update()
        # _set_content_tab("clicking") maps the Clicking pane for the first
        # time, and a single root.update() does not reliably wait out the X
        # server's MapNotify round trip -- focus_set() on a widget that
        # isn't yet viewable is DROPPED by Tk, not queued, so calling it too
        # early silently loses the focus request with no error. Both waits
        # below fail closed: if the widget never becomes viewable, or never
        # actually takes focus, within the timeout, the assertEqual still
        # reports a genuine regression.
        self.pump_until(lambda: numbox.entry.winfo_viewable(), timeout=1.0)
        # Pumping the loop while waiting above gives this Xvfb's other Tk-
        # owning client (this suite's own stress-test harness runs a second
        # Tk process against the same shared, window-manager-less display)
        # a window in which the real X input-focus ownership setUp's own
        # focus_force() granted (see its comment) can be silently dropped --
        # self.root.focus_get() simply reads None afterwards, with no event
        # this process can observe. focus_set() cannot reacquire that: it
        # only moves focus *within* an app that already owns it. Calling
        # focus_force() on the *entry itself* both reacquires real ownership
        # and targets the right widget in one step -- forcing it onto root
        # first and then focus_set()-ing the entry is not equivalent: if
        # root still happens to hold real focus (ownership was never lost,
        # only the entry-level record), forcing root again is a no-op at
        # the X level, no fresh FocusIn ever fires, and the entry never
        # gets forwarded to. A single force can still lose a race to the
        # other client re-stealing focus in the same narrow window, so this
        # retries rather than asserting on one attempt -- each attempt is
        # cheap and the loop exits the instant one lands.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            numbox.entry.focus_force()
            self.pump_until(lambda: self.root.focus_get() == numbox.entry, timeout=0.5)
            if self.root.focus_get() == numbox.entry:
                break
        self.assertEqual(self.root.focus_get(), numbox.entry,
                         "setup failed to focus the entry")

    def _find_segmented_for(self, variable):
        def walk(widget):
            if isinstance(widget, app.Segmented) and widget.var is variable:
                return widget
            for child in widget.winfo_children():
                found = walk(child)
                if found is not None:
                    return found
            return None
        found = walk(self.ui.content)
        self.assertIsNotNone(found, "no matching Segmented control found")
        return found

    def test_click_elsewhere_drops_focus(self):
        self.focus_and_settle(self.ui.click_ms)
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), app.ACCENT)
        self.ui.count_label.event_generate("<Button-1>", x=1, y=1)
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), app.LINE)

    def test_click_the_entry_itself_keeps_it_focused(self):
        self.focus_and_settle(self.ui.click_ms)
        self.ui.click_ms.entry.event_generate("<Button-1>", x=2, y=2)
        self.root.update()
        self.assertIsInstance(self.root.focus_get(), tk.Entry)

    def test_click_a_different_numbox_switches_focus(self):
        self.focus_and_settle(self.ui.click_ms)
        self.ui.jitter_ms.entry.event_generate("<Button-1>", x=2, y=2)
        self.root.update()
        self.assertEqual(self.root.focus_get(), self.ui.jitter_ms.entry)

    def test_enter_blurs_without_reverting_the_value(self):
        self.focus_and_settle(self.ui.click_ms)
        self.ui.click_ms.var.set("321")
        self.ui.click_ms.entry.event_generate("<Return>")
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), app.LINE)
        self.assertEqual(self.ui.click_ms.var.get(), "321")

    def test_escape_blurs_without_reverting_the_value(self):
        self.focus_and_settle(self.ui.click_ms)
        self.ui.click_ms.var.set("321")
        self.ui.click_ms.entry.event_generate("<Escape>")
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), app.LINE)
        self.assertEqual(self.ui.click_ms.var.get(), "321")

    def test_tab_still_moves_focus(self):
        # Non-regression: not a pinned order, just proof traversal survives.
        self.focus_and_settle(self.ui.click_ms)
        self.ui.click_ms.entry.event_generate("<Tab>")
        self.root.update()
        self.assertIsNotNone(self.root.focus_get())

    def test_a_segmented_control_still_changes_its_variable(self):
        seg = self._find_segmented_for(self.ui.button_name)
        self.focus_and_settle(self.ui.click_ms)
        self.ui.button_name.set("left")
        # Third segment ("middle") of three, spanning seg.w wide.
        seg.event_generate("<Button-1>", x=seg.w - 2, y=int(seg.h / 2))
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.button_name.get(), "middle")

    def test_a_game_item_still_selects(self):
        self.focus_and_settle(self.ui.click_ms)
        item = self.ui.items["minecraft"]
        item.event_generate("<Button-1>", x=5, y=5)
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.current, "minecraft")

    def _find_add_game_button(self):
        def walk(widget):
            if isinstance(widget, app.Button) and widget.command == self.ui.add_current_game:
                return widget
            for child in widget.winfo_children():
                found = walk(child)
                if found is not None:
                    return found
            return None
        found = walk(self.ui.side)
        self.assertIsNotNone(found, "no matching Button found for add_current_game")
        return found

    def test_a_button_still_runs_its_command(self):
        # "Add current game" is packed into the sidebar (self.side), a
        # sibling of the Hotkey/Clicking tab toggle rather than a child of
        # it, so it stays viewable while the Clicking pane is shown. Found
        # by its bound command rather than its label -- the label reads "+"
        # instead while the rail is collapsed.
        button = self._find_add_game_button()
        original_command = button.command
        clicked = []
        button.command = lambda: clicked.append(1)
        try:
            self.focus_and_settle(self.ui.click_ms)
            self.pump_until(lambda: button.winfo_viewable(), timeout=1.0)
            self.assertTrue(button.winfo_viewable(), "the button never became viewable")
            button.event_generate("<Button-1>", x=2, y=2)
            self.root.update()
            self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
            self.assertEqual(clicked, [1])
        finally:
            button.command = original_command

    def test_starting_from_a_background_thread_drops_focus(self):
        # The real hotkey callback runs on the pynput listener thread, never
        # the Tk main thread -- prove the same is true here.
        self.ui.mouse = FakeMouse()
        self.focus_and_settle(self.ui.click_ms)
        worker = threading.Thread(target=self.ui.start, daemon=True)
        worker.start()
        worker.join(timeout=2)
        self.pump_until(
            lambda: self.root.focus_get() is not self.ui.click_ms.entry)
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), app.LINE)
        self.ui.stop()
        self.pump(0.2)


class WindowResize(UITestCase):
    # G#38/GH#67: UI_SCALE_DEFAULT is now "auto", but this class tests
    # generic resize mechanics that predate Auto and assume self.s stays
    # fixed across a plain geometry() call -- Auto's own continuous-
    # tracking/debounce behavior gets its own dedicated tests (UIScaleAuto,
    # below), not a rewrite of every pre-existing resize test. Round 3 (PR
    # #89 review): constructed directly at this step (UITestCase.setUp()'s
    # INITIAL_UI_SCALE), not switched to it after the fact -- a post-hoc
    # _apply_ui_scale("100") call still raced a real window manager's own
    # async confirmation of whatever Auto's construction-time bootstrap had
    # already put in flight, on macOS/Windows CI.
    INITIAL_UI_SCALE = "100"

    def test_both_axes_are_resizable(self):
        self.assertEqual(self.root.resizable(), (1, 1))

    def test_minsize_reflects_the_collapsed_rail_floor(self):
        # Story #24 feature 3: minsize (the hard floor) and the default
        # launch size are no longer the same number -- the floor is now
        # derived from the collapsed rail width, not the expanded one, so
        # the window can actually be dragged down to admit a collapsed rail.
        s = self.ui.s
        expected = (int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s),
                    int(app.WINDOW_MIN_H * s))
        self.assertEqual(self.root.minsize(), expected)

    def test_rail_stays_at_expanded_width_on_a_wide_window(self):
        content_before = self.ui.content.winfo_width()
        side_before = self.ui.side.winfo_width()
        self.root.geometry("1000x900")
        self.root.update()
        self.assertGreater(self.ui.content.winfo_width(), content_before)
        self.assertEqual(self.ui.side.winfo_width(), side_before)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_W * self.ui.s))

    def test_shrinking_past_the_threshold_collapses_the_rail(self):
        # Between the new (collapsed-rail) floor and the collapse threshold.
        s = self.ui.s
        threshold = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        floor = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s)
        target_w = (threshold + floor) // 2
        self.root.geometry(f"{target_w}x{int(700 * s)}")
        self.root.update()
        self.assertTrue(self.ui._rail_collapsed)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_RAIL_W * s))

    def test_growing_back_past_the_threshold_re_expands_the_rail(self):
        s = self.ui.s
        threshold = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        floor = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s)
        target_w = (threshold + floor) // 2
        self.root.geometry(f"{target_w}x{int(700 * s)}")
        self.root.update()
        self.assertTrue(self.ui._rail_collapsed)
        self.root.geometry(f"{threshold + 200}x{int(700 * s)}")
        self.root.update()
        self.assertFalse(self.ui._rail_collapsed)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_W * s))

    def test_shrinking_below_minsize_is_clamped(self):
        self.root.geometry("50x50")
        self.root.update()
        minw, minh = self.root.minsize()
        self.assertGreaterEqual(self.root.winfo_width(), minw)
        self.assertGreaterEqual(self.root.winfo_height(), minh)


class WindowMinimumHeight(UITestCase):
    """G#28/GH#48: the height floor was tuned by #14 for the old single
    combined page and never revisited when PR #40 split it into tabs,
    leaving the tallest pane (Clicking+Eating, Minecraft) sitting in
    ~148-163px of dead space it could never reach anyway (no scrolling
    anywhere in this app) while the shortest pane (Hotkey) sat ~78% empty.
    WINDOW_MIN_H replaces the bare 690 literal with a smaller, named
    constant re-derived from the tallest pane's own real content span --
    these tests prove it both shrank and still fits that pane, construction-
    true, rather than trusting a hardcoded pixel value.

    G#38/GH#67 round 4 (PR #89 review, real macOS CI): generic, non-Auto
    mechanics (docs/spec.md's own non-goal), same reasoning as WindowResize's
    own INITIAL_UI_SCALE above -- test_default_launch_height_equals_the_floor
    reads self.ui.s and self.root.winfo_height() and assumes they stay in
    lockstep, which a real WM's own construction-time Auto self-correction
    can legitimately break: a downward correction (self.s ends up lower than
    the bootstrap value) never shrinks the already-larger real window
    (_apply_minsize()'s grow_only never shrinks), leaving self.ui.s and the
    real window's height genuinely, correctly out of sync until the next
    trigger (round 2's own documented, accepted widget-tree-lag tradeoff) --
    observed for real on macOS CI once Defect 1's fix let the clamp actually
    reach below the bootstrap value instead of always clamping upward."""
    INITIAL_UI_SCALE = "100"

    def test_minimum_height_shrunk_from_the_pre_tab_split_floor(self):
        self.assertLess(app.WINDOW_MIN_H, 690)

    def test_default_launch_height_equals_the_floor(self):
        # Unlike minw/default_w (story #24 feature 3, which deliberately
        # decoupled them for the collapsed rail), height has no equivalent
        # second state -- the hard floor and the freshly-launched default
        # are the same coupled number (docs/spec.md's "Why height doesn't
        # get the width axis's floor/default split", G#28/GH#48).
        expected = int(app.WINDOW_MIN_H * self.ui.s)
        self.assertEqual(self.root.winfo_height(), expected)
        self.assertEqual(self.root.minsize()[1], expected)

    def test_tallest_pane_still_fits_at_the_floor(self):
        # Default (unresized) window state -- i.e. at the floor -- with the
        # tallest real pane showing (Clicking+Eating, Minecraft; Eating is
        # Minecraft-only, afk_clicker.py's PROFILES[0]).
        self.ui._select("minecraft")
        self.ui._set_content_tab("clicking")
        self.root.update()
        pane, top, bottom = self.ui._pane_fills["clicking"]
        # No "zero the spacers first" step: _fill_pane()'s own docstring
        # (afk_clicker.py) establishes this span measurement is already
        # translation-invariant in the spacers' current height (they're
        # excluded from `kids` by identity) -- and, confirmed by probing
        # this pane directly, Tk silently ignores config(height=0) on a
        # plain Frame here anyway, so a reset step would be a no-op.
        pane.update_idletasks()
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        self.assertLessEqual(natural, pane.winfo_height())

    def test_tallest_pane_still_fits_at_the_floor_reverse_order(self):
        # Round 2 of G#28/GH#48 (docs/test-review.md Defect 1): the sibling
        # test above only ever exercises _select() before _set_content_tab()
        # ("order A"). The reverse -- clicking the Clicking tab first while
        # still on the default Global profile (no Eating card packed at
        # all), THEN selecting Minecraft -- is the branch inside _select()
        # (afk_clicker.py's eat_section/eat_card pack() calls) that used to
        # leave the pane's own _fill_pane() call reading the Eating card's
        # canvas before its <Configure>-triggered redraw had grown it to
        # its real height, oversizing `extra` enough that Tk's packer
        # unmapped the bottom spacer outright -- genuine, permanent content
        # clipping, not mere asymmetry. Asserts both "not clipped" (natural
        # fits) and "not left unmapped" (the packer never gave up on a
        # spacer), the two symptoms the live-app review actually observed.
        # Round 3 (PR #49, docs/implementation.md) instrumented this test to
        # trace Windows CI's deterministic failure instead of re-guessing;
        # round 4 acted on that trace (WINDOW_MIN_H raised from 560 to 620,
        # plus _fill_pane()'s own clamp/recovery hardening) and restores the
        # real assertions below.
        self.ui._set_content_tab("clicking")
        self.ui._select("minecraft")
        self.root.update()
        pane, top, bottom = self.ui._pane_fills["clicking"]
        pane.update_idletasks()
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        self.assertLessEqual(natural, pane.winfo_height())
        self.assertTrue(top.winfo_ismapped())
        self.assertTrue(bottom.winfo_ismapped())

    def test_tallest_pane_still_fits_at_worst_case_compound_scale(self):
        # The documented worst case: low-DPI macOS (0.75) times the 90%
        # UI-scale step (0.9), s ~ 0.675. Safe to force directly -- _dpi_s
        # is a plain instance attribute set once in __init__ and never
        # rewritten by any rebuild path.
        self.ui._dpi_s = 0.75
        self.ui._apply_ui_scale("90")
        self.root.update()
        self.ui._select("minecraft")
        self.ui._set_content_tab("clicking")
        self.root.update()
        # Spacers/pane are recreated by the scale-triggered rebuild -- must
        # re-fetch after update(), not reuse a reference from before it.
        # No zero-spacers step here either -- see the sibling test above.
        pane, top, bottom = self.ui._pane_fills["clicking"]
        pane.update_idletasks()
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        self.assertLessEqual(natural, pane.winfo_height())

    def test_sweep_hint_height_floor_minecraft_with_eating(self):
        # G#22/GH#33 PR #80 round 2 review (docs/test-review.md "Round 2",
        # lens 7 BLOCKER, carried to round 3): this test's first shape
        # measured `natural` the same way the sibling floor tests above do
        # -- each mapped non-spacer child's *allocated* winfo_y()/
        # winfo_height(). That's blind to the exact clipping it exists to
        # catch: when the pane genuinely runs short, pack() silently
        # shrinks whichever card is packed last (the Eating card's canvas
        # here) below its own required size to absorb the overflow, rather
        # than ever letting the allocated span exceed the pane's fixed
        # height -- confirmed live: baseline Eating canvas 125px allocated
        # == 125px required; under a 12x-inflated SWEEP_HINT_BAD, 56px
        # allocated vs. still-125px required, 69px of real content silently
        # clipped, invisible to that measurement. This version instead sums
        # each mapped non-spacer child's own winfo_reqheight() plus its pack
        # pady (read via pack_info(), the same accounting _fill_pane()'s own
        # docstring in afk_clicker.py insists on for exactly this reason --
        # a reqheight-only sum silently drops real pack()-consumed pady)
        # against the pane's available height. Verified this stays
        # discriminating: sabotaging either SWEEP_HINT_BAD or
        # SWEEP_HINT_MUTED to 12x its real length makes this assertion fail
        # at both 90% and 130% (for the sabotaged band only), while the real,
        # unsabotaged code passes at both scale steps and both bands.
        #
        # Also unlike the sibling tests: a fresh instance per scale step, at
        # the persisted scale, not `_apply_ui_scale()` on the one window
        # `setUp()` already built --
        # RowValueColumn.test_ui_scale_row_never_overflows_its_card_at_any_scale_step's
        # own comment explains why: `_apply_minsize(grow_only=True)` never
        # shrinks, so a mid-test scale-down would leave the window (and this
        # pane's available height) at the larger, ~100%-scale size, passing
        # for the wrong reason exactly where the fit is tightest. The
        # window's own height is asserted against `WINDOW_MIN_H` at each
        # step to prove the true floor was actually reached, not assumed.
        #
        # And both warning bands, not only BAD: measured live at 90% scale,
        # INK ("Java sweeps may miss") is the *tighter* fit against the
        # row's wraplength (123px used of 131px) than BAD ("Java sweeps
        # likely fail", 120px used) despite being three characters shorter,
        # purely because of where its words break -- BAD is not established
        # to be the worse case, so this test no longer assumes it is.
        def _pady_total(widget):
            pady = widget.pack_info().get("pady", 0)
            if isinstance(pady, (tuple, list)):
                return int(pady[0]) + int(pady[1])
            return 2 * int(pady)

        def _required_natural(pane, top, bottom):
            kids = [c for c in pane.winfo_children()
                    if c.winfo_ismapped() and c not in (top, bottom)]
            return sum(c.winfo_reqheight() + _pady_total(c) for c in kids)

        for scale in ("90", "130"):
            with self.subTest(scale=scale):
                self.ui.store.data["ui_scale"] = scale
                self.ui.store.save()
                ui = self.restart()

                # Prove this subTest actually reached the genuine floor at
                # this scale step, rather than the pre-restart window size.
                expected_h = int(app.WINDOW_MIN_H * ui.s)
                self.assertEqual(self.root.winfo_height(), expected_h)
                self.assertEqual(self.root.minsize()[1], expected_h)

                for band, click_ms in (("bad", "500"), ("ink", "649")):
                    with self.subTest(scale=scale, band=band):
                        ui._select("minecraft")
                        ui._set_content_tab("clicking")
                        self.root.update()
                        ui.click_ms.var.set(click_ms)
                        ui.jitter_ms.var.set("0")
                        self.root.update()

                        pane, top, bottom = ui._pane_fills["clicking"]
                        pane.update_idletasks()
                        natural = _required_natural(pane, top, bottom)
                        self.assertLessEqual(natural, pane.winfo_height())

                        warning_h = ui.jitter_row.winfo_reqheight()

                        # Same values, no band: back to the static
                        # descriptive hint at the same scale -- the row
                        # must not have grown to show the warning.
                        ui.click_ms.var.set("650")
                        ui.jitter_ms.var.set("0")
                        self.root.update()
                        static_h = ui.jitter_row.winfo_reqheight()
                        self.assertLessEqual(warning_h, static_h)


class RailCollapse(UITestCase):
    """The sidebar collapsing to an icon-only rail below a width threshold
    (story #24 feature 3) -- purely visual, debounced on threshold-crossing
    through the existing _request_rebuild()/_rebuild_ui() coalescing."""

    # G#38/GH#67: same reasoning as WindowResize's own INITIAL_UI_SCALE
    # above -- this class's collapse-threshold tests assume a plain
    # geometry() call rebuilds the rail immediately (via
    # _request_rebuild()'s after_idle, drained by the next root.update()),
    # which only holds for a fixed step; Auto mode instead defers that
    # rebuild to AUTO_SETTLE_MS's settle timer. Constructed directly at
    # "100" (round 3: not switched to it post-construction, see
    # WindowResize's own comment for why that still raced a real WM) so
    # this class keeps testing rail-collapse mechanics, not Auto's own
    # debounce (which UIScaleAuto below tests directly).
    INITIAL_UI_SCALE = "100"

    def test_rail_starts_expanded_at_default_launch(self):
        # The single most important regression this feature exists to
        # prevent: the app must not launch pre-collapsed.
        s = self.ui.s
        self.assertIs(self.ui._rail_collapsed, False)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_W * s))
        item = self.ui.items["global"]
        profile = self.ui.by_id["global"]
        self.assertEqual(item.itemcget(item.text, "text"), profile["name"])

    def test_default_geometry_still_matches_the_old_expanded_minimum(self):
        s = self.ui.s
        self.assertEqual(self.root.winfo_width(),
                         int((app.SIDEBAR_W + 1 + app.CONTENT_W) * s))
        self.assertLess(self.root.minsize()[0], self.root.winfo_width())

    def test_collapsed_items_still_navigate_by_click(self):
        s = self.ui.s
        target_w = int((app.RAIL_COLLAPSE_THRESHOLD * s) - 50)
        self.root.geometry(f"{target_w}x{int(700 * s)}")
        self.root.update()
        self.assertTrue(self.ui._rail_collapsed)

        item = self.ui.items["minecraft"]
        item.event_generate("<Button-1>", x=5, y=5)
        self.root.update()
        self.assertEqual(self.ui.current, "minecraft")

        self.ui.settings_item.event_generate("<Button-1>", x=5, y=5)
        self.root.update()
        self.assertTrue(self.ui._settings_open)

    def test_repeated_threshold_crossings_coalesce_to_one_rebuild(self):
        s = self.ui.s
        threshold_px = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        below, above = threshold_px - 50, threshold_px + 50
        calls = []
        original = self.ui._rebuild_ui
        def spy():
            calls.append(1)
            original()
        self.ui._rebuild_ui = spy
        for w in (below, above, below, above, below):
            self.root.event_generate("<Configure>", width=w, height=int(700 * s))
        self.root.update()
        self.assertLessEqual(len(calls), 1)

    def test_a_resize_that_never_crosses_the_threshold_triggers_no_rebuild(self):
        s = self.ui.s
        threshold_px = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        calls = []
        original = self.ui._rebuild_ui
        def spy():
            calls.append(1)
            original()
        self.ui._rebuild_ui = spy
        for w in (threshold_px + 10, threshold_px + 20, threshold_px + 30):
            self.root.event_generate("<Configure>", width=w, height=int(700 * s))
        self.root.update()
        self.assertEqual(len(calls), 0)

    def test_add_current_game_button_survives_collapse(self):
        s = self.ui.s
        target_w = int((app.RAIL_COLLAPSE_THRESHOLD * s) - 50)
        self.root.geometry(f"{target_w}x{int(700 * s)}")
        self.root.update()
        self.assertTrue(self.ui._rail_collapsed)
        buttons = [w for w in self.ui.side.winfo_children() if isinstance(w, app.Button)]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].itemcget(buttons[0].label, "text"), "+")

    def test_rail_rederives_on_a_ui_scale_change_with_width_held_fixed(self):
        # docs/spec.md's own "Edge cases": a UI-scale change moves the
        # threshold's *pixel* value (RAIL_COLLAPSE_THRESHOLD * s) without
        # root's raw width ever moving, so _rail_collapsed must be
        # re-derived from current geometry in _build_ui() itself, not only
        # from the <Configure> handler. Pick a real window width strictly
        # between the 90% and 130% steps' thresholds, hold it there, and
        # flip only the scale.
        dpi_s = self.ui._dpi_s
        threshold_90 = int(app.RAIL_COLLAPSE_THRESHOLD * dpi_s
                            * app.UI_SCALE_FACTORS["90"])
        threshold_130 = int(app.RAIL_COLLAPSE_THRESHOLD * dpi_s
                             * app.UI_SCALE_FACTORS["130"])
        fixed_w = (threshold_90 + threshold_130) // 2
        # Tall enough that _apply_minsize(grow_only=True) never needs to
        # touch the height at either scale step either -- if it did, the
        # resulting geometry() call would still fire a <Configure> for root
        # carrying the (unchanged) width, and _on_root_resize would
        # independently repair _rail_collapsed using the already-updated
        # self.s. That would make this test pass for the wrong reason: it
        # would confirm the app ends up correct, not that _build_ui()'s own
        # rederivation is what did it. Holding both axes still isolates the
        # rederivation this test exists to cover.
        fixed_h = int(690 * dpi_s * app.UI_SCALE_FACTORS["130"]) + 100

        self.ui._apply_ui_scale("90")
        self.root.update()
        self.root.geometry(f"{fixed_w}x{fixed_h}")
        self.root.update()
        self.assertFalse(self.ui._rail_collapsed)

        before_w = self.root.winfo_width()
        self.ui._apply_ui_scale("130")
        self.root.update()
        # Fail closed: assert the geometry this test relies on to isolate
        # the rederivation actually held, rather than let a collapse flip
        # pass for the wrong reason (the window itself drifting past the
        # new threshold instead of _build_ui()'s rederivation doing its job).
        # Width only, not height (PR #41 round 3): RAIL_COLLAPSE_THRESHOLD
        # and _build_ui()'s rederivation are width-only properties -- height
        # plays no role in the collapse decision anywhere in this feature.
        # A legitimate, expected _apply_minsize(grow_only=True) height-only
        # adjustment between UI-scale steps is orthogonal to what this test
        # proves and must not fail it; real per-platform window-manager/DPI
        # rounding on that axis was observed to overshoot the previous flat
        # +100px height headroom by wildly different, unpredictable amounts
        # on Windows and macOS (no principled bigger constant exists), while
        # width -- the one axis this test actually needs held still -- is
        # exactly what fixed_w/fixed_h above were chosen to keep put.
        self.assertEqual(
            self.root.winfo_width(), before_w,
            "root's width moved during the scale change -- this test no "
            "longer isolates a scale-only rederivation")
        self.assertTrue(self.ui._rail_collapsed)
        self.assertEqual(self.ui.side.winfo_width(),
                         int(app.SIDEBAR_RAIL_W * self.ui.s))

    def test_settings_item_collapsed_update_dot_reflects_has_update(self):
        # design's SettingsItem checklist item 7: while collapsed, the
        # badge letter never text-swaps to "Settings · Update" the way the
        # expanded row does -- the small ACCENT corner dot is the whole
        # signal instead (SettingsItem._paint()'s collapsed branch).
        # Assert both states so the test can actually distinguish "showing"
        # from "not showing", not just confirm the dot item exists.
        s = self.ui.s
        target_w = int((app.RAIL_COLLAPSE_THRESHOLD * s) - 50)
        self.root.geometry(f"{target_w}x{int(700 * s)}")
        self.root.update()
        self.assertTrue(self.ui._rail_collapsed)

        item = self.ui.settings_item
        self.assertFalse(item.has_update)
        self.assertEqual(item.itemcget(item.update_dot, "state"), "hidden")
        self.assertEqual(item.itemcget(item.text, "text"), "S")

        self.ui._offer_update("v9.9.9")
        self.assertTrue(self.ui._rail_collapsed)
        self.assertEqual(item.itemcget(item.update_dot, "state"), "normal")
        self.assertEqual(item.itemcget(item.update_dot, "fill"), app.ACCENT)
        self.assertEqual(
            item.itemcget(item.text, "text"), "S",
            "collapsed mode must never text-swap -- the corner dot is the "
            "only signal")


class VerticalFill(UITestCase):
    """Each tab pane's own top/bottom spacer pair (story #24 feature 4,
    docs/spec.md): absorbs a pane's leftover vertical space so a short tab
    no longer leaves a large dead band below its last card. `self.ui.
    _pane_fills["hotkey"/"clicking"/"appearance"/"updates"]` is `(pane,
    top_spacer, bottom_spacer)`, populated by _build_content()/
    _build_settings()."""

    def _tall_window(self, height=900):
        s = self.ui.s
        default_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * s)
        self.root.geometry(f"{default_w}x{int(height * s)}")
        self.root.update()

    def test_short_tab_gains_margin_on_a_tall_window(self):
        # Hotkey (one card) is the default active tab -- the shortest pane,
        # and the one with the most leftover space to absorb. G#37/GH#66
        # (FILL_TOP_SHARE=0.0): content hugs the tab bar, so the top spacer
        # sits at its unavoidable 1px max(1, ...) floor and the pane's
        # entire real leftover space collects in the bottom spacer instead
        # -- proof the dead band is being consumed now lives in `bottom`,
        # not `top`.
        self._tall_window()
        pane, top, bottom = self.ui._pane_fills["hotkey"]
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        extra = max(0, pane.winfo_height() - natural)
        self.assertLessEqual(top.winfo_height(), 1)
        self.assertGreaterEqual(bottom.winfo_height(), extra - 1)

    def test_top_and_bottom_spacers_sum_to_the_real_leftover_space(self):
        # True-by-construction: measured the same way _fill_pane() itself
        # measures -- the real bottom-minus-top edge span of the content
        # block, not a reqheight sum (a plain reqheight sum silently drops
        # any pack()-level pady between direct children, e.g. section()'s
        # own trailing pady on this very pane) -- not a fixed pixel
        # comparison (this story's own established discipline: a flat
        # constant already cost a round on a different feature).
        self._tall_window()
        pane, top, bottom = self.ui._pane_fills["hotkey"]
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        self.assertEqual(top.winfo_height() + bottom.winfo_height(),
                         pane.winfo_height() - natural)

    def test_floor_case_still_fits_with_no_clipping(self):
        # Deviation from docs/spec.md's acceptance criterion #1 (see
        # docs/implementation.md): that criterion assumed minh (690 * s,
        # tuned by docs/history/ac-14-design.md for the OLD single page
        # holding Hotkey+Clicking+Eating all stacked together) would leave
        # ~0px extra for the tallest PANE today. Story #24 feature 2 split
        # that one page into independent tabs without revisiting minh, so
        # even the tallest single pane (Clicking+Eating, Minecraft) had
        # ~148px of genuine, pre-existing leftover at the floor -- verified
        # directly against this app's own widgets (Xvfb probe, not
        # committed). Touching minh was explicitly out of scope for this
        # feature (Non-goals; docs/design.md's own "Open question: window
        # minimum height") but was later addressed by G#28/GH#48, which
        # shrank WINDOW_MIN_H so the tallest pane's leftover at the floor is
        # now the deliberate ~40-60px margin from that ticket's own
        # derivation, not ~148px. What this test actually proves is the
        # invariant this feature IS responsible for at the floor:
        # _fill_pane() absorbs whatever leftover genuinely exists -- never
        # more, so never clipping -- computed the same way _fill_pane()
        # itself computes it (true by construction, not a fixed pixel
        # bound).
        #
        # G#37/GH#66 (FILL_TOP_SHARE=0.0): renamed from
        # "..._splits_symmetrically_with_no_clipping" and the split-ratio
        # assertion replaced -- this box's own floor leftover for the
        # tallest pane (Clicking+Eating, Minecraft) measures ~70px here,
        # well outside the extra-in-{0,1} range docs/spec.md's floor-
        # invariant proof worked through (that proof used the Windows-CI-
        # tuned boundary value, not this platform's actual floor slack), so
        # a real, non-floored top/bottom pair is exercised: top pinned to
        # its 1px floor, bottom absorbing the rest, same sum-fits-exactly
        # invariant as before, no longer a symmetric split.
        self.ui._select("minecraft")
        self.ui._set_content_tab("clicking")
        self.root.update()
        pane, top, bottom = self.ui._pane_fills["clicking"]
        # No settling loop needed (round 2 of G#28/GH#48 -- see
        # docs/implementation.md's round-2 section): the reentrancy this
        # test used to paper over with a bounded retry loop is now closed
        # at the app level -- card()'s on_settle callback re-triggers
        # _fill_pane() for the clicking pane every time the Eating card's
        # own shell actually finishes resizing (_on_eat_card_settled()),
        # so by the time _select()/_set_content_tab()'s own explicit
        # _fill_pane() call returns, the pane's own update_idletasks() has
        # already drained every intermediate settle step and the spacers
        # already reflect the card's true final height -- one direct
        # assertion, exactly like this test asserted before G#28/GH#48
        # ever touched it.
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        extra = max(0, pane.winfo_height() - natural)
        self.assertEqual(top.winfo_height() + bottom.winfo_height(), max(2, extra))
        self.assertLessEqual(top.winfo_height(), 1)
        self.assertGreaterEqual(bottom.winfo_height(), extra - 1)

    def test_floor_case_still_fits_with_no_clipping_reverse_order(self):
        # Same invariant as the sibling test above, reverse order: the
        # Clicking tab clicked first while still on the default Global
        # profile (no Eating card packed yet), THEN Minecraft selected --
        # the branch inside _select() (afk_clicker.py's eat_section/
        # eat_card pack() calls) that docs/test-review.md's Defect 1 found
        # producing real, unmapped-spacer clipping before round 2 of
        # G#28/GH#48. No settling loop here either, for the same reason.
        # Round 3 (PR #49, docs/implementation.md) instrumented this test to
        # trace Windows CI's deterministic failure (77 != 2 observed)
        # instead of re-guessing; round 4 acted on that trace (WINDOW_MIN_H
        # raised from 560 to 620, plus _fill_pane()'s own clamp/recovery
        # hardening) and restores the real assertions below.
        #
        # G#37/GH#66: same rename/assertion swap as the sibling test above.
        self.ui._set_content_tab("clicking")
        self.ui._select("minecraft")
        self.root.update()
        pane, top, bottom = self.ui._pane_fills["clicking"]
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        extra = max(0, pane.winfo_height() - natural)
        self.assertEqual(top.winfo_height() + bottom.winfo_height(), max(2, extra))
        self.assertLessEqual(top.winfo_height(), 1)
        self.assertGreaterEqual(bottom.winfo_height(), extra - 1)
        self.assertTrue(top.winfo_ismapped())
        self.assertTrue(bottom.winfo_ismapped())

    def test_switching_tabs_recomputes_each_panes_own_margin(self):
        # Fill is computed per pane, not per page: Clicking's own content is
        # taller than Hotkey's, so its leftover -- and therefore its
        # margin -- must be smaller. G#37/GH#66 (FILL_TOP_SHARE=0.0): the
        # top spacer is pinned to its 1px floor on every pane regardless of
        # content height, so the margin that actually varies now lives in
        # the bottom spacer -- read that instead. Assertion direction is
        # unchanged: Hotkey's own leftover is still bigger than Clicking's.
        self._tall_window()
        _, _, hotkey_bottom = self.ui._pane_fills["hotkey"]
        hotkey_margin = hotkey_bottom.winfo_height()
        self.ui._set_content_tab("clicking")
        self.root.update()
        _, _, clicking_bottom = self.ui._pane_fills["clicking"]
        clicking_margin = clicking_bottom.winfo_height()
        self.assertGreater(hotkey_margin, clicking_margin)

    def test_toggling_eating_recomputes_the_clicking_panes_margin(self):
        # The one case with no natural <Configure> trigger (Empirical
        # grounding #2): toggling eat_section/eat_card's own pack state
        # never fires a <Configure> on clicking_pane, so only _select()'s
        # own explicit, guarded call can ever recompute this. G#37/GH#66
        # (FILL_TOP_SHARE=0.0): the top spacer is pinned to its 1px floor
        # either way, so read the bottom spacer instead -- same direction
        # (without_eating > with_eating).
        self._tall_window()
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui._select("minecraft")   # Eating shows -- margin shrinks
        self.root.update()
        _, _, bottom = self.ui._pane_fills["clicking"]
        with_eating = bottom.winfo_height()
        self.ui._select("global")      # Eating hides -- margin grows
        self.root.update()
        without_eating = bottom.winfo_height()
        self.assertGreater(without_eating, with_eating)

    def test_hidden_tabs_own_margin_does_not_desync_the_visible_one(self):
        # The self._content_tab == "clicking" guard in _select()
        # (afk_clicker.py:2936) exists to stop a game switch from
        # recomputing Clicking's OWN margin off the pane's geometry while
        # it's unmapped -- stale-but-plausible on X11, 0/1 on Windows, wrong
        # either way.
        #
        # G#37/GH#66 (FILL_TOP_SHARE=0.0) breaks this test's prior
        # geometry-inference technique structurally: the top spacer is
        # pinned to its 1px floor regardless of whether the guard fires, so
        # an assertEqual/assertNotEqual against a seeded top value can never
        # discriminate guard-present from guard-removed. The bottom spacer
        # was already known (docs/history/ac-24-f4-implementation.md,
        # "Round 2") to move for an unrelated reason -- _select()'s own
        # `eat_section.pack(before=clicking_bottom)` re-pack, which runs
        # whether or not the fill guard fires -- so it was never a safe
        # signal either, even under the old split.
        #
        # Replacement: spy directly on self.ui._request_pane_fill instead
        # of inferring from geometry -- this tests the guard's own actual
        # condition (does it ask for a "clicking" fill while the pane is
        # hidden?) and is immune to FILL_TOP_SHARE's value entirely.
        self._tall_window()
        self.ui._set_content_tab("hotkey")
        self.root.update()
        self.assertFalse(self.ui._pane_fills["clicking"][0].winfo_ismapped())

        calls = []
        original = self.ui._request_pane_fill
        self.ui._request_pane_fill = lambda key: (calls.append(key), original(key))[1]
        self.ui._select("minecraft")   # toggles Eating on inside the hidden pane
        self.root.update()
        self.assertNotIn("clicking", calls)   # guard suppressed the request entirely

        self.ui._set_content_tab("clicking")
        self.root.update()
        self.assertIn("clicking", calls)      # and it isn't stuck stale forever

    def test_live_resize_drag_updates_margin_without_a_rebuild(self):
        # Proves this feature never touches _request_rebuild()/
        # _rebuild_ui()'s coalescing machinery: several real resizes (each
        # firing a genuine <Configure> on the mapped Hotkey pane) update the
        # spacer heights, but never trigger a rebuild.
        #
        # The margin assertion is checked true-by-construction against the
        # pane's own actually-granted geometry after the drag, the same way
        # test_top_and_bottom_spacers_sum_to_the_real_leftover_space and
        # test_floor_case_still_fits_with_no_clipping above measure it --
        # not directionally against a "before" baseline.
        # geometry() is a request, not a guarantee: on Windows CI's
        # constrained runners the WM clamped the final requested height
        # below the height "before" was captured at, so the spacer
        # legitimately shrank and an assertGreater(after, before) failed for
        # a reason that had nothing to do with this feature. The resize
        # loop itself still fires several genuine <Configure> events on a
        # mapped pane -- this is still a live-resize-drag test -- it is
        # only the final assertion that no longer assumes any one of those
        # requests landed at its literal requested size.
        s = self.ui.s
        default_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * s)
        calls = []
        original = self.ui._rebuild_ui
        def spy():
            calls.append(1)
            original()
        self.ui._rebuild_ui = spy
        pane, top, bottom = self.ui._pane_fills["hotkey"]
        for h in (700, 850, 750, 900):
            self.root.geometry(f"{default_w}x{int(h * s)}")
            self.root.update()
        kids = [c for c in pane.winfo_children()
                if c.winfo_ismapped() and c not in (top, bottom)]
        natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
                   - min(c.winfo_y() for c in kids))
        extra = max(0, pane.winfo_height() - natural)
        self.assertEqual(top.winfo_height() + bottom.winfo_height(),
                         max(2, extra))
        self.assertEqual(len(calls), 0)


@needs_display
class FillPaneOverflow(CapturesCallbackExceptions, unittest.TestCase):
    """G#28/GH#48 round 4: the Windows CI trace (docs/implementation.md's
    round-4 section) showed a spacer pack() gives up on mapping never gets
    reconsidered afterward -- its winfo_height() stayed frozen at its last
    mapped value across nine further _fill_pane() calls and ten passive
    event-loop pumps, real content overflow long since resolved. Confirmed
    directly against plain Tk (not this app, and not reproducible on this
    box's own Linux/Xvfb packer, which -- unlike whatever Windows' own did
    in the trace -- already reconsiders a dropped sibling on its own the
    next time *any* other sibling's geometry changes) that pack()'s own
    overflow decision, once made, is never guaranteed to be revisited
    without an explicit fresh pack() call. This test targets that
    explicit-recovery mechanism directly and in isolation, independent of
    whatever incidental relayout a given platform's packer happens to also
    do on its own."""

    def setUp(self):
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.root.geometry("300x500")
        self.pane = tk.Frame(self.root, height=368, width=200, bg=app.BG)
        self.pane.pack_propagate(False)
        self.pane.pack()
        self.top = tk.Frame(self.pane, bg=app.BG, height=0)
        self.top.pack(fill="x")
        self.content = tk.Frame(self.pane, height=200, width=100, bg=app.BG)
        self.content.pack(fill="x")
        self.bottom = tk.Frame(self.pane, bg=app.BG, height=0)
        self.bottom.pack(fill="x")
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self._assert_no_callback_exceptions()

    def test_a_spacer_pack_already_gave_up_on_is_recovered_once_room_exists(self):
        # bottom starts unmapped for whatever reason (pack_forget() here
        # stands in for pack's own overflow decision -- the trigger doesn't
        # matter, only that it starts unmapped) while the pane has genuine
        # leftover space (avail=368, content=200, extra=168) -- room enough
        # for both spacers many times over. _fill_pane() must bring it back
        # rather than leaving it stuck exactly where an earlier
        # config()-only write (no pack()) left it (confirmed against the
        # *unfixed* function: config() alone never remaps an already-
        # unmapped slave -- only a fresh pack() call does).
        self.bottom.pack_forget()
        self.root.update()
        self.assertFalse(self.bottom.winfo_ismapped())
        app._fill_pane(self.pane, self.top, self.bottom)
        self.root.update()
        self.assertTrue(self.bottom.winfo_ismapped())
        self.assertGreater(self.bottom.winfo_height(), 0)


class RowValueColumn(UITestCase):
    """Row's fixed-width label column (docs/history/ac-24-f1-spec.md):
    the control always starts at the same offset from the row's left edge,
    regardless of how wide a stretched card gets, so the label-to-control
    gap does not grow the way it did with the old pack-based Row -- extra
    width becomes trailing margin after the control instead."""

    # G#38/GH#67 round 3 (PR #89 review): same reasoning as NumBoxFocus's
    # own INITIAL_UI_SCALE above -- test_ui_scale_row_never_overflows_
    # its_card_at_any_scale_step below already restarts per scale step of
    # its own, unaffected by this fixture's initial construction step.
    INITIAL_UI_SCALE = "100"

    def _right_edge(self, widget, ancestor):
        """widget's right edge, in pixels from ancestor's own left edge.

        winfo_x() alone is only relative to a widget's *immediate* parent,
        which is not `ancestor` for a control several frames deep (control
        frame -> Row -> card inner) -- winfo_rootx() gives an absolute
        screen position that both share, so the difference is the offset
        that actually matters here.
        """
        return (widget.winfo_rootx() + widget.winfo_width()) - ancestor.winfo_rootx()

    def test_control_sits_at_the_fixed_label_column_offset(self):
        control = self.ui.click_ms.master
        expected = int((app.ROW_LABEL_W + app.ROW_LABEL_GAP) * self.ui.s)
        self.assertEqual(control.winfo_x(), expected)

    def test_offset_is_unchanged_when_the_card_stretches(self):
        control = self.ui.click_ms.master
        before = control.winfo_x()
        # Not the ticket's literal 1200x820 -- both dimensions risk being
        # clamped by the window manager on the ~1024x768 CI runners. 900x760
        # is comfortably under both bounds and comfortably above the default
        # minsize width, so content genuinely stretches.
        self.root.geometry("900x760")
        self.root.update()
        # click_ms's Clicking pane is hidden by default (story #24 feature
        # 2); a hidden pane's geometry does not track a live resize (spec's
        # "Test impact" finding 4), so without switching to it this
        # assertion would still pass but for a hollow reason -- it would
        # never actually observe the resize. Switch to the pane that owns
        # `control` so the resize is genuinely applied before measuring.
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.assertEqual(control.winfo_x(), before)

    def test_extra_width_becomes_trailing_margin_not_a_growing_gap(self):
        control = self.ui.click_ms.master
        card = control.master.master
        self.root.geometry("900x760")
        self.root.update()
        # Same reasoning as above: measure while the Clicking pane is
        # actually visible and has actually received the resize.
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.assertLess(control.winfo_x() + control.winfo_width(),
                        card.winfo_width())

    def test_ui_scale_row_never_overflows_its_card_at_any_scale_step(self):
        # Constant-level check first (docs/history/ac-24-f1-spec.md's fit-check
        # argument): the widest explicit control in the file (width=244
        # since G#38/GH#67 added a 5th "Auto" option, the "UI scale" row)
        # plus the fixed label column must fit inside CARD_INNER_W,
        # independent of any rendering: 152 + 244 = 396 <= 396 (docs/design.md's
        # own layout math -- exactly fills the card, no overflow).
        self.assertLessEqual(
            app.ROW_LABEL_W + app.ROW_LABEL_GAP + 244, app.CARD_INNER_W)
        for value in ("auto", "90", "100", "115", "130"):
            with self.subTest(value=value):
                # A fresh instance per step, NOT _apply_ui_scale() on one
                # window. _apply_minsize(grow_only=True) never shrinks, so
                # stepping down from 100% to 90% leaves the window -- and
                # therefore the card -- at the larger size, and the control
                # is measured against a card wider than 90% would ever
                # actually build. That passes for the wrong reason, and
                # exactly where the fit is tightest. Restarting makes each
                # step size its own window from the store in __init__.
                self.ui.store.data["ui_scale"] = value
                self.ui.store.save()
                ui = self.restart()
                ui._show_settings()
                self.root.update()
                seg = self._appearance_segment(ui.ui_scale_var)
                card = seg.master.master.master
                self.assertLessEqual(self._right_edge(seg, card), card.winfo_width())

    def test_random_jitter_hint_wraps_instead_of_overlapping_the_control(self):
        row = self.ui.jitter_ms.master.master
        text = row.grid_slaves(row=0, column=0)[0]
        _label, hint = text.winfo_children()
        self.assertEqual(hint.cget("wraplength"), int(app.ROW_LABEL_W * self.ui.s))

        # That it actually wrapped: the jitter hint is the only one long enough
        # to need two lines at this scale, so it stands taller than one that
        # fits on a single line. Comparing two heights measured the same way
        # survives a font change, where the previous assertion did not -- that
        # one compared the hint's requested WIDTH (text plus the Label's own
        # padx and border) against wraplength (a text-only limit), two
        # different quantities whose order the font decides: it passed here on
        # DejaVu Sans at 144 <= 145 and failed on Windows' Segoe UI at 141 > 140.
        #
        # Scope of that claim, deliberately narrow (PR #37 review): this holds
        # at the scale the test runs at, not at every UI-scale step. Font size
        # is int(8 * s) and truncates in whole points while wraplength scales
        # continuously, so "only the jitter hint wraps" is not scale-invariant
        # -- at _dpi_s ~0.75 (macOS, #35) and the 90% step it does not wrap at
        # all. Anything that sweeps this assertion across scale steps has to
        # establish the premise per step rather than assume it.
        short = self.ui.autostop_min.master.master
        _short_label, short_hint = short.grid_slaves(
            row=0, column=0)[0].winfo_children()
        self.root.update()
        self.assertGreater(hint.winfo_reqheight(), short_hint.winfo_reqheight())

        # And the thing this test is actually named for, which it never
        # previously checked: the wrapped hint must not run into the control.
        # jitter_ms's Clicking pane is hidden by default (story #24 feature
        # 2); winfo_rootx() on an unmapped widget is Tk's placeholder (0 on
        # Windows), not a real screen position, so switch to the pane that
        # owns both widgets before measuring -- same reasoning as
        # test_offset_is_unchanged_when_the_card_stretches above.
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.assertLessEqual(
            hint.winfo_rootx() + hint.winfo_width(),
            self.ui.jitter_ms.winfo_rootx())


class MinecraftSweepHint(UITestCase):
    """G#22/GH#33 (docs/spec.md, docs/design.md): a conditional warning,
    Minecraft-profile-only, that replaces the jitter row's own static hint
    when click_ms - jitter_ms (floored at 50) drops below DEFAULT_CLICK_MS
    (INK bold, 550-649) or MIN_SWEEP_BAD_MS (BAD bold, <550) -- round 2
    (docs/design.md Revision 2, Decision A2) moved the warning out from
    under the Interval row into the jitter row's already-reserved hint
    slot, height-neutral by construction. Read-only display -- never
    blocks or clamps click_ms/jitter_ms."""

    # G#38/GH#67 round 3 (PR #89 review): same reasoning as NumBoxFocus's
    # own INITIAL_UI_SCALE.
    INITIAL_UI_SCALE = "100"

    STATIC_HINT = "spreads the rhythm so it is not exact"

    def _set_interval(self, click_ms, jitter_ms, profile="minecraft"):
        self.ui._set_content_tab("clicking")
        self.ui._select(profile)
        self.root.update()
        self.ui.click_ms.var.set(str(click_ms))
        self.ui.jitter_ms.var.set(str(jitter_ms))
        self.root.update()

    def _hint(self):
        label = self.ui.jitter_row.hint_label
        return (label.cget("text"), label.cget("fg"),
                "bold" in label.cget("font"))

    def _static(self):
        return (self.STATIC_HINT, app.MUTED, False)

    # ---- profile-conditionality (data-driven "min_sweep_ms" key) ----

    def test_profile_key_is_data_driven(self):
        self.assertEqual(self.ui.by_id["minecraft"]["min_sweep_ms"],
                          app.DEFAULT_CLICK_MS)
        self.assertIsNone(self.ui.by_id["global"]["min_sweep_ms"])
        self.ui._add_game("Some Other Game")
        self.assertIsNone(
            self.ui.by_id["custom:some other game"]["min_sweep_ms"])

    # ---- thresholds, both boundaries ----

    def test_no_band_at_650_with_zero_jitter_shows_static_text(self):
        self._set_interval(650, 0)
        self.assertEqual(self._hint(), self._static())

    def test_ink_bold_band_at_649(self):
        self._set_interval(649, 0)
        self.assertEqual(self._hint(), (app.SWEEP_HINT_MUTED, app.INK, True))

    def test_ink_bold_band_at_550_boundary_is_inclusive(self):
        self._set_interval(600, 50)   # effective 550
        self.assertEqual(self._hint(), (app.SWEEP_HINT_MUTED, app.INK, True))

    def test_bad_bold_band_at_549(self):
        self._set_interval(600, 51)   # effective 549
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    def test_bad_bold_band_at_500(self):
        self._set_interval(500, 0)
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    def test_bad_bold_band_floored_at_50_never_negative_or_garbage(self):
        self._set_interval(100, 500)   # effective floored at 50
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    # ---- Global/custom never show it ----

    def test_global_profile_never_shows_the_band_at_any_numbers(self):
        self.ui._set_content_tab("clicking")
        self.ui._select("global")
        self.root.update()
        for click_ms, jitter_ms in ((650, 0), (500, 0), (100, 500)):
            with self.subTest(click_ms=click_ms, jitter_ms=jitter_ms):
                self.ui.click_ms.var.set(str(click_ms))
                self.ui.jitter_ms.var.set(str(jitter_ms))
                self.root.update()
                self.assertEqual(self._hint(), self._static())

    def test_custom_profile_never_shows_the_band_at_any_numbers(self):
        self.ui._set_content_tab("clicking")
        self.ui._add_game("Some Other Game")
        self.root.update()
        for click_ms, jitter_ms in ((650, 0), (500, 0), (100, 500)):
            with self.subTest(click_ms=click_ms, jitter_ms=jitter_ms):
                self.ui.click_ms.var.set(str(click_ms))
                self.ui.jitter_ms.var.set(str(jitter_ms))
                self.root.update()
                self.assertEqual(self._hint(), self._static())

    # ---- invalid/empty text falls back the same way _num() always does ----

    def test_empty_interval_field_falls_back_to_profile_default(self):
        self._set_interval(500, 0)   # BAD, so a real transition happens below
        self.ui.click_ms.var.set("")
        self.root.update()
        # _num()'s fallback is profile["defaults"]["click_ms"] == 650, so
        # effective = max(50, 650 - 0) = 650 -> static text, not a
        # crash/garbage value.
        self.assertEqual(self._hint(), self._static())

    def test_invalid_interval_text_falls_back_to_profile_default(self):
        self._set_interval(500, 0)
        self.ui.click_ms.var.set("not a number")
        self.root.update()
        self.assertEqual(self._hint(), self._static())

    # ---- live updates, no focus-out needed ----

    def test_band_clears_live_on_the_very_keystroke_that_fixes_it(self):
        self._set_interval(600, 51)   # BAD
        self.assertNotEqual(self._hint(), self._static())
        self.ui.click_ms.var.set("650")
        self.ui.jitter_ms.var.set("0")
        self.root.update()
        self.assertEqual(self._hint(), self._static())

    # ---- profile switch away and back ----

    def test_band_restored_to_static_on_global_and_reshown_on_return_to_minecraft(self):
        self._set_interval(600, 51)   # BAD
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))
        self.ui._select("global")
        self.root.update()
        self.assertEqual(self._hint(), self._static())
        self.ui._select("minecraft")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    # ---- pane fill on an actual band transition, not every keystroke ----

    def test_pane_fill_requested_only_on_band_transition(self):
        # No root.update() anywhere in this test, deliberately: a real
        # geometry change also fires the Clicking pane's own <Configure>-
        # bound _request_pane_fill("clicking") (afk_clicker.py:~2950),
        # which is real, correct, *unrelated* app behaviour this test isn't
        # about -- update() is what lets that reactive call land. var.set()
        # fires its "write" trace, and therefore _persist()/
        # _note_sweep_hint()/_paint_sweep_hint(), synchronously and in-line,
        # so the spy below sees exactly this feature's own calls and
        # nothing from the wider event loop.
        self._set_interval(650, 0)   # static text, baseline
        calls = []
        original = self.ui._request_pane_fill
        self.ui._request_pane_fill = \
            lambda key: (calls.append(key), original(key))[1]

        self.ui.click_ms.var.set("640")   # static -> INK band: a transition
        self.assertEqual(calls.count("clicking"), 1)

        calls.clear()
        self.ui.jitter_ms.var.set("100")  # still active, INK -> BAD: no transition
        self.assertEqual(calls.count("clicking"), 0)

        calls.clear()
        self.ui.click_ms.var.set("650")   # effective 550 (jitter still 100): still active
        self.assertEqual(calls.count("clicking"), 0)

        calls.clear()
        self.ui.jitter_ms.var.set("0")    # effective 650: active -> static, a transition
        self.assertEqual(calls.count("clicking"), 1)

    # ---- no-crash-and-still-correct: rebuild triggers (orchestrator correction) ----

    def test_survives_theme_change_while_bad_band_visible(self):
        self._set_interval(600, 51)   # BAD
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))
        self.ui._apply_appearance("dark")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    def test_survives_theme_change_while_ink_band_visible(self):
        # The orchestrator correction's own concern: INK (unlike BAD) has a
        # genuinely different value per theme (#e4e7ea dark / #161a22
        # light), so this is the one that would silently pass if the paint
        # ever captured a stale colour instead of re-reading the module
        # global fresh.
        self._set_interval(649, 0)   # INK bold
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_MUTED, app.INK, True))
        self.ui._apply_appearance("dark")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_MUTED, app.INK, True))

    def test_survives_ui_scale_change_while_band_visible(self):
        self._set_interval(600, 51)   # BAD
        self.ui._apply_ui_scale("130")
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    def test_survives_opening_and_closing_settings_while_band_visible(self):
        self._set_interval(600, 51)   # BAD
        self.ui._show_settings()
        self.root.update()
        # Same close mechanism as docs/history/ac-21-implementation.md
        # Round 2's own regression tests.
        self.ui._select(self.ui.current, persist=False)
        self.root.update()
        self.assertEqual(self._hint(), (app.SWEEP_HINT_BAD, app.BAD, True))

    def test_survives_startup_with_minecraft_already_the_saved_selection(self):
        self._set_interval(600, 51)   # BAD, and persists "selected": "minecraft"
        ui = self.restart()
        ui._set_content_tab("clicking")
        self.root.update()
        label = ui.jitter_row.hint_label
        self.assertTrue(label.winfo_ismapped())
        self.assertEqual(label.cget("text"), app.SWEEP_HINT_BAD)
        self.assertEqual(label.cget("fg"), app.BAD)
        self.assertIn("bold", label.cget("font"))

    # ---- geometry: same wrap/no-overlap property as the jitter precedent ----

    def test_hint_wraps_at_the_same_wraplength_and_does_not_overlap_the_control(self):
        self._set_interval(500, 0)   # BAD, visible
        row = self.ui.jitter_row
        text = row.grid_slaves(row=0, column=0)[0]
        _label, hint = text.winfo_children()
        self.assertIs(hint, row.hint_label)
        self.assertEqual(hint.cget("wraplength"), int(app.ROW_LABEL_W * self.ui.s))
        self.root.update()
        self.assertLessEqual(
            hint.winfo_rootx() + hint.winfo_width(),
            self.ui.jitter_ms.winfo_rootx())

    # ---- Interval row lost the mutable-hint capability nothing uses now ----

    def test_interval_row_has_no_hint_capability_anymore(self):
        self.assertIsNone(self.ui.interval_row.hint_label)
        text = self.ui.interval_row.grid_slaves(row=0, column=0)[0]
        self.assertEqual(len(text.winfo_children()), 1)   # just the main label

    # ---- Row's additive mutable-hint capability, and existing static hints ----

    def test_existing_static_hints_are_unaffected(self):
        autostop_text = self.ui.autostop_min.master.master.grid_slaves(
            row=0, column=0)[0].winfo_children()[1]
        self.assertEqual(autostop_text.cget("text"), "0 means never")
        self.assertEqual(autostop_text.cget("fg"), app.MUTED)

    def test_jitter_hint_defaults_to_the_static_text_with_no_band(self):
        self._set_interval(650, 0)   # no band
        self.assertEqual(self._hint(), self._static())

    def test_row_mutable_hint_is_additive_and_restorable(self):
        row = app.Row(self.root, "Test", 1.0, hint="default text",
                      mutable_hint=True)
        row.pack()
        self.root.update()
        self.assertIsNotNone(row.hint_label)
        self.assertTrue(row.hint_label.winfo_ismapped())
        self.assertEqual(row.hint_label.cget("text"), "default text")
        self.assertEqual(row.hint_label.cget("fg"), app.MUTED)
        self.assertNotIn("bold", row.hint_label.cget("font"))

        row.set_hint("warning!", app.BAD, bold=True)
        self.root.update()
        self.assertEqual(row.hint_label.cget("text"), "warning!")
        self.assertEqual(row.hint_label.cget("fg"), app.BAD)
        self.assertIn("bold", row.hint_label.cget("font"))

        row.restore_hint()
        self.root.update()
        self.assertEqual(row.hint_label.cget("text"), "default text")
        self.assertEqual(row.hint_label.cget("fg"), app.MUTED)
        self.assertNotIn("bold", row.hint_label.cget("font"))

    def test_row_without_mutable_hint_has_no_hint_label(self):
        row = app.Row(self.root, "Test", 1.0)
        self.assertIsNone(row.hint_label)


class TabBarNavigation(UITestCase):
    """The horizontal tab bar (story #24 feature 2, docs/spec.md): TabBar
    itself, and the pane-visibility contract on both the game page
    (Hotkey | Clicking) and Settings (Appearance | Updates)."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def _tab_bar(self, variable):
        def walk(widget):
            if isinstance(widget, app.TabBar) and widget.var is variable:
                return widget
            for child in widget.winfo_children():
                found = walk(child)
                if found is not None:
                    return found
            return None
        found = walk(self.ui.content)
        self.assertIsNotNone(found, "no matching TabBar found")
        return found

    def _click_tab(self, bar, value):
        """A real <Button-1> at the tab's own measured x-range, per the
        spec's acceptance criteria -- not a hand-picked pixel constant."""
        for tab_value, _label, x1, x2, _tid in bar._tabs:
            if tab_value == value:
                bar.event_generate("<Button-1>", x=int((x1 + x2) / 2), y=2)
                return
        self.fail(f"TabBar has no tab {value!r}")

    def test_hotkey_is_the_default_active_tab_on_a_fresh_game_page(self):
        self.assertEqual(self.ui._content_tab, "hotkey")
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "")

    def test_clicking_the_clicking_tab_shows_only_the_clicking_pane(self):
        bar = self._tab_bar(self.ui.content_tab_var)
        self._click_tab(bar, "clicking")
        self.root.update()
        self.assertEqual(self.ui.content_tab_var.get(), "clicking")
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "")

    def test_calling_the_setter_directly_also_moves_the_tab_indicator(self):
        # Regression: _set_content_tab used to move the pane but never wrote
        # content_tab_var back, so a direct call (anything other than a real
        # tab click) desynced the underline from the visible pane -- it
        # only "worked" via the click path, where the var's own write trace
        # is what calls this method in the first place. Calling the setter
        # directly, with a value that DIFFERS from what the var already
        # holds, is the one direction the click-driven tests above never
        # exercise.
        self.assertEqual(self.ui.content_tab_var.get(), "hotkey")
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "")
        self.assertEqual(self.ui.content_tab_var.get(), "clicking",
                         "the tab indicator did not follow a direct setter call")

    def test_both_content_panes_widgets_exist_no_matter_which_is_packed(self):
        # Hotkey pane is the one currently packed...
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "pack")
        self.assertTrue(hasattr(self.ui, "hotkey_label"))
        self.assertTrue(hasattr(self.ui, "apply_button"))
        # ...but Clicking-pane widgets exist and hold their values too, even
        # while hidden -- built unconditionally, only unpacked.
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "")
        self.assertTrue(self.ui.click_ms.var.get(),
                        "click_ms should already hold this game's value, "
                        "even while its pane is hidden")
        self.assertTrue(hasattr(self.ui, "jitter_ms"))
        self.assertTrue(hasattr(self.ui, "button_name"))

    def test_appearance_is_the_default_active_settings_tab(self):
        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self.ui._settings_tab, "appearance")
        self.assertEqual(self.ui.appearance_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.updates_pane.winfo_manager(), "")
        self.assertTrue(hasattr(self.ui, "update_button"),
                        "update_button should exist once Settings is open, "
                        "regardless of which Settings tab is showing")

    def test_clicking_updates_shows_only_that_pane(self):
        self.ui._show_settings()
        self.root.update()
        bar = self._tab_bar(self.ui.settings_tab_var)
        self._click_tab(bar, "updates")
        self.root.update()
        self.assertEqual(self.ui.settings_tab_var.get(), "updates")
        self.assertEqual(self.ui.updates_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.appearance_pane.winfo_manager(), "")

    def test_calling_the_settings_setter_directly_also_moves_the_indicator(self):
        # Same regression/direction as the content-tab version above, for
        # _set_settings_tab.
        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self.ui.settings_tab_var.get(), "appearance")
        self.ui._set_settings_tab("updates")
        self.root.update()
        self.assertEqual(self.ui.updates_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.appearance_pane.winfo_manager(), "")
        self.assertEqual(self.ui.settings_tab_var.get(), "updates",
                         "the tab indicator did not follow a direct setter call")

    def test_the_updater_still_reflects_state_while_its_tab_is_active(self):
        self.ui._show_settings()
        self.root.update()
        self.ui._set_settings_tab("updates")
        self.root.update()
        self.ui._set_update_state("Custom status", False, app.BAD)
        self.assertEqual(
            self.ui.update_button.itemcget(self.ui.update_button.label, "text"),
            "Custom status")
        self.assertFalse(self.ui.update_button._enabled)

    def test_eating_stays_conditional_inside_the_clicking_pane(self):
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui._select("minecraft")
        self.root.update()
        self.assertEqual(self.ui.eat_card.winfo_manager(), "pack")
        self.ui._select("global")
        self.root.update()
        self.assertEqual(self.ui.eat_card.winfo_manager(), "")

    def test_active_content_tab_survives_a_rebuild(self):
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertEqual(self.ui._content_tab, "clicking")
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "")

    def test_active_settings_tab_survives_a_rebuild(self):
        self.ui._show_settings()
        self.root.update()
        self.ui._set_settings_tab("updates")
        self.root.update()
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertEqual(self.ui._settings_tab, "updates")
        self.assertEqual(self.ui.updates_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.appearance_pane.winfo_manager(), "")

    def test_active_content_tab_survives_a_ui_scale_rebuild(self):
        # Same invariant as test_active_content_tab_survives_a_rebuild, but
        # via _apply_ui_scale()'s own caller of the shared _request_rebuild()
        # path -- a different trigger than Appearance, still the same
        # after_idle(self._rebuild_ui) mechanism (docs/spec.md §4).
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui._apply_ui_scale("115")
        self.root.update()
        self.assertEqual(self.ui._content_tab, "clicking")
        self.assertEqual(self.ui.clicking_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.hotkey_pane.winfo_manager(), "")

    def test_active_settings_tab_survives_a_ui_scale_rebuild(self):
        self.ui._show_settings()
        self.root.update()
        self.ui._set_settings_tab("updates")
        self.root.update()
        self.ui._apply_ui_scale("115")
        self.root.update()
        self.assertEqual(self.ui._settings_tab, "updates")
        self.assertEqual(self.ui.updates_pane.winfo_manager(), "pack")
        self.assertEqual(self.ui.appearance_pane.winfo_manager(), "")

    def test_a_running_clicker_is_unaffected_by_a_tab_switch(self):
        # _sync_settings()'s 200ms poll feeds the live click-worker thread
        # from Clicking-pane widgets unconditionally (docs/spec.md) -- a tab
        # switch while it is running must not interrupt it. This is the
        # single highest-risk invariant this feature could break, so the
        # test genuinely switches tabs -- both directions -- while the
        # clicker is running, rather than re-affirming the tab it is
        # already on: a call that leaves _content_tab unchanged is a no-op
        # and proves nothing (a prior round of this test did exactly that
        # and passed identically with the assertion deleted).
        self.ui.mouse = FakeMouse()
        self.ui._select("global")
        self.ui.click_ms.var.set("100")
        self.pump(0.3)
        self.ui.start()
        self.pump(0.4)
        self.assertTrue(self.ui.mouse.clicks,
                        "no clicks were produced before any tab switch")

        # hotkey -> clicking, while running.
        self.assertEqual(self.ui._content_tab, "hotkey")
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui.mouse.clicks.clear()
        self.pump(0.4)
        self.assertTrue(self.ui.running)
        self.assertTrue(self.ui.mouse.clicks,
                        "the click worker stopped producing clicks after switching to Clicking")

        # clicking -> hotkey, while still running.
        self.ui._set_content_tab("hotkey")
        self.root.update()
        self.ui.mouse.clicks.clear()
        self.pump(0.4)
        self.assertTrue(self.ui.running)
        self.assertTrue(self.ui.mouse.clicks,
                        "the click worker stopped producing clicks after switching back to Hotkey")

        self.ui.stop()
        self.pump(0.2)
        self.assertFalse(self.ui.running)


@needs_display
class Selftest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertEqual(app.selftest(), 0)

    def test_selftest_fails_when_icon_asset_missing(self):
        # selftest() must actually walk the same _load_app_icon() path
        # AfkAutoclicker.__init__ uses -- a broken --add-data destination
        # (simulated here by pointing _asset_dir() at a dir with no
        # icon-*.png files) has to fail selftest() in CI, not just at
        # first real launch of the frozen build.
        real_asset_dir = app._asset_dir
        empty_dir = tempfile.mkdtemp()   # exists, but has no icon-*.png
        app._asset_dir = lambda: empty_dir
        try:
            with self.assertRaises(tk.TclError):
                app.selftest()
        finally:
            app._asset_dir = real_asset_dir


@needs_display
class AssetDir(unittest.TestCase):
    """_asset_dir() unfrozen: next to afk_clicker.py, per is_frozen()==False."""

    def test_unfrozen_resolves_next_to_the_module(self):
        expected = os.path.join(
            os.path.dirname(os.path.abspath(app.__file__)), "assets")
        self.assertEqual(app._asset_dir(), expected)


class AppIcon(UITestCase):
    """root.iconphoto(), wired near root.title() in AfkAutoclicker.__init__."""

    def test_icon_images_are_loaded_non_empty(self):
        self.assertTrue(self.ui._icon_imgs)
        for img in self.ui._icon_imgs:
            self.assertGreater(img.width(), 0)
            self.assertGreater(img.height(), 0)

    def test_icon_reference_survives_a_rebuild(self):
        # _rebuild_ui() only tears down root's *children* (see its own
        # docstring); the icon is loaded once in __init__, outside
        # _build_ui()/_rebuild_ui(), so the same list object -- not a
        # fresh one built from scratch -- must still be on self afterwards,
        # and the PhotoImage objects inside it must still be alive (a
        # dropped reference blanks the icon silently rather than raising).
        before = self.ui._icon_imgs
        self.ui._apply_appearance("light")      # runs synchronously
        self.root.update()
        self.assertIs(self.ui._icon_imgs, before)
        for img in self.ui._icon_imgs:
            self.assertGreater(img.width(), 0)
            self.assertGreater(img.height(), 0)


@needs_display
class AppIconMissingAsset(unittest.TestCase):
    """A packaging bug (an asset missing from the checkout), not bad user
    input -- must raise at startup, not silently start with a blank icon
    (docs/CODING-GUIDELINES.md's input-validation section: fail visibly)."""

    def setUp(self):
        self._real_asset_dir = app._asset_dir
        self._empty_dir = tempfile.mkdtemp()   # exists, but has no icon-*.png

    def tearDown(self):
        app._asset_dir = self._real_asset_dir

    def test_missing_png_raises_instead_of_starting_blank(self):
        app._asset_dir = lambda: self._empty_dir
        config = os.path.join(tempfile.mkdtemp(), "settings.json")
        root = tk.Tk()
        try:
            with self.assertRaises(tk.TclError):
                app.AfkAutoclicker(root, store=app.Store(config))
        finally:
            root.destroy()


class HotkeyPersistence(UITestCase):
    # Applying a hotkey starts a pynput listener. Without macOS Accessibility
    # permission that aborts the process with SIGTRAP rather than raising, so
    # the app checks first and these tests follow the same signal -- the
    # permission, not the platform, decides whether a listener can exist.
    # Skipped on macOS outright, not merely when permission is missing.
    # AXIsProcessTrusted reports trusted on the CI runner and the CoreGraphics
    # event tap aborts the process anyway -- "Trace/BPT trap: 5", exit 133,
    # which no except clause can catch and which takes the whole suite with it.
    # So the permission check is necessary but not sufficient, and what else is
    # involved is unattributed. Tracked in issue #7 rather than guessed at.
    needs_input_permission = unittest.skipIf(
        app is not None and app.sys.platform == "darwin",
        "starting a listener aborts the process on macOS -- see issue #7")

    @needs_input_permission
    def test_restored_and_armed_after_restart(self):
        self.ui.hotkey = hotkey({"ctrl"}, [kb.Key.f6, kb.Key.f7])
        self.ui.apply_hotkey()
        self.root.update()
        ui = self.restart()
        self.assertIsNotNone(ui.registered_hotkey)
        self.assertEqual(ui.registered_hotkey.label(), "Ctrl + F6 + F7")
        self.assertTrue(ui.hk_listener.running)

    @needs_input_permission
    def test_a_corrupt_hotkey_starts_clean(self):
        self.ui.hotkey = hotkey(set(), [kb.Key.f6])
        self.ui.apply_hotkey()
        self.ui.on_close()
        with open(self.config) as f:
            data = json.load(f)
        data["hotkey"] = {"keys": "garbage"}
        with open(self.config, "w") as f:
            json.dump(data, f)
        self.root = tk.Tk()
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.assertIsNone(self.ui.registered_hotkey)

    def test_nothing_is_saved_when_no_hotkey_was_applied(self):
        self.ui.on_close()
        with open(self.config) as f:
            self.assertIsNone(json.load(f).get("hotkey"))

    def test_no_listener_is_started_without_permission(self):
        # The guard, exercised directly rather than only on a Mac. Applying
        # must keep the combination and the label so that granting the
        # permission and pressing Apply again works without re-recording.
        original = app.macos_input_permitted
        app.macos_input_permitted = lambda: False
        try:
            self.ui.hotkey = hotkey({"ctrl"}, [kb.Key.f6])
            self.ui.apply_hotkey()
            self.root.update()
            self.assertIsNone(self.ui.hk_listener, "a listener was started anyway")
            self.assertIsNone(self.ui.registered_hotkey,
                              "no listener is running, so registered_hotkey must not claim one")
            self.assertEqual(self.ui.hotkey.label(), "Ctrl + F6",
                             "the recorded combination must survive so a second Apply works")
        finally:
            app.macos_input_permitted = original

    @needs_input_permission
    def test_registered_hotkey_cleared_on_second_apply_without_permission(self):
        # G#8's exact bug lived here: a *first* Apply with no prior listener
        # trivially left registered_hotkey at its already-None default, which
        # made "don't touch it" look sufficient. A *second* Apply -- after an
        # earlier successful Apply had started a real listener and set
        # registered_hotkey -- must also end with registered_hotkey None,
        # even though hk_listener is already correctly stopped/cleared a few
        # lines above the permission check.
        self.ui.hotkey = hotkey({"ctrl"}, [kb.Key.f6])
        self.ui.apply_hotkey()
        self.root.update()
        self.assertIsNotNone(self.ui.registered_hotkey, "setup: first Apply should register")
        self.assertIsNotNone(self.ui.hk_listener, "setup: first Apply should start a listener")

        original = app.macos_input_permitted
        app.macos_input_permitted = lambda: False
        try:
            self.ui.apply_hotkey()
            self.root.update()
            self.assertIsNone(self.ui.hk_listener, "the old listener must be stopped")
            self.assertIsNone(self.ui.registered_hotkey,
                              "no listener is running any more, so registered_hotkey must not "
                              "keep claiming the one from the earlier successful Apply")
            self.assertEqual(self.ui.hotkey.label(), "Ctrl + F6",
                             "the recorded combination must survive so a third Apply works")
        finally:
            app.macos_input_permitted = original

    def test_capture_refuses_without_permission(self):
        # On a worker with a deadline, never inline: capture_hotkey() blocks in
        # listener.join() waiting for a key that never comes, so without the
        # guard an inline call hangs the whole suite instead of failing it.
        original = app.macos_input_permitted
        app.macos_input_permitted = lambda: False
        worker = threading.Thread(target=self.ui.capture_hotkey, daemon=True)
        try:
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(),
                             "capture_hotkey opened a listener instead of refusing")
            self.pump(0.2)
            self.assertIsNone(self.ui.hotkey)
        finally:
            app.macos_input_permitted = original


@needs_display
class Themes(unittest.TestCase):
    """THEMES holds both palettes; the app still ships Deepslate only."""

    DARK_HEX = {"BG": "#15171a", "CARD": "#1c1f23", "CARD_HI": "#262a30",
                "LINE": "#3a4048", "INK": "#e4e7ea", "MUTED": "#9299a3",
                "ACCENT": "#e08a55", "ACCENT_INK": "#1a0f08",
                "OK": "#5cc9a4", "BAD": "#f06262"}
    LIGHT_HEX = {"BG": "#e8ebf0", "CARD": "#ffffff", "CARD_HI": "#eff2f7",
                 "LINE": "#d3d8e0", "INK": "#161a22", "MUTED": "#596170",
                 "ACCENT": "#2b58cc", "ACCENT_INK": "#ffffff",
                 "OK": "#0f7f4c", "BAD": "#cc3527"}
    KEYS = {"BG", "CARD", "CARD_HI", "LINE", "INK", "MUTED", "ACCENT",
            "ACCENT_INK", "ACCENT_HI", "OK", "BAD"}

    def test_dark_and_light_both_hold_every_key(self):
        self.assertEqual(set(app.THEMES["dark"]), self.KEYS)
        self.assertEqual(set(app.THEMES["light"]), self.KEYS)

    def test_dark_matches_the_deepslate_hex_exactly(self):
        for name, hexval in self.DARK_HEX.items():
            with self.subTest(name=name):
                self.assertEqual(app.THEMES["dark"][name], hexval)

    def test_light_matches_the_quartz_hex_exactly(self):
        for name, hexval in self.LIGHT_HEX.items():
            with self.subTest(name=name):
                self.assertEqual(app.THEMES["light"][name], hexval)

    def test_module_globals_still_ship_dark_only(self):
        names = ("BG", "CARD", "CARD_HI", "LINE", "INK", "MUTED", "ACCENT",
                 "ACCENT_INK", "ACCENT_HI", "OK", "BAD")
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(getattr(app, name), app.THEMES["dark"][name])

    def test_accent_hi_is_computed_not_a_fourth_hand_picked_hex(self):
        # Not in the ticket at all -- if it were hand-picked, this equality
        # with the pure function's own output would be a coincidence.
        self.assertEqual(app.THEMES["dark"]["ACCENT_HI"],
                         app._lighten(app.THEMES["dark"]["ACCENT"], 0.18))
        self.assertEqual(app.THEMES["light"]["ACCENT_HI"],
                         app._lighten(app.THEMES["light"]["ACCENT"], 0.18))

    def test_card_inner_w_has_no_border_allowance_left(self):
        # A full-width card's shell sits inside body's own CONTENT_PAD inset
        # before the card's own CARD_PAD padding starts -- a control sized
        # off CONTENT_W alone, skipping that body inset, overruns the card.
        self.assertEqual(app.CARD_INNER_W,
                         app.CONTENT_W - 2 * app.CONTENT_PAD - 2 * app.CARD_PAD)
        self.assertEqual(app.CARD_INNER_W, 396)


@needs_display
class Lighten(unittest.TestCase):
    """The pure helper behind ACCENT_HI -- no theme or canvas involved."""

    def test_factor_zero_is_unchanged(self):
        self.assertEqual(app._lighten("#e08a55", 0.0), "#e08a55")

    def test_factor_one_is_pure_white(self):
        self.assertEqual(app._lighten("#123456", 1.0), "#ffffff")

    def test_a_partial_factor_blends_toward_white(self):
        lightened = app._lighten("#000000", 0.5)
        r, g, b = (int(lightened[i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(all(0 < c < 255 for c in (r, g, b)))

    def test_out_of_range_factor_above_one_clamps_to_white(self):
        # PR #28 review concern: an unclamped factor=2.0 walked r/g/b past
        # 255, producing a 9-character string like "#17e17e17e" instead of
        # raising or saturating -- Feature 3 will give this a second caller,
        # so a bad input from there must not corrupt a widget's fill string.
        self.assertEqual(app._lighten("#808080", 2.0), "#ffffff")

    def test_out_of_range_factor_below_zero_clamps_to_unchanged(self):
        self.assertEqual(app._lighten("#123456", -1.0), "#123456")

    def test_non_hex_color_raises_value_error(self):
        for bad in ("purple", "#12345", "#1234567", "123456", "#gggggg", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    app._lighten(bad, 0.5)


class FontSizeFloor(unittest.TestCase):
    """G#23/GH#35: the pure fs(base, s) helper behind the macOS font-size
    floor -- no theme or canvas involved, same shape as Lighten's own
    pure-helper tests above. macOS reports tk scaling ~0.75 (_dpi_s), which
    can compound with the 90% UI-scale step to s ~= 0.675 -- the worst case
    docs/spec.md's Acceptance criteria enumerates."""

    def test_mac_100_percent_already_shipping_case_is_unchanged(self):
        self.assertEqual(app.fs(8, 0.75), 6)

    def test_mac_90_percent_worst_case_is_floored(self):
        # The ticket's own reported case: int(8 * 0.675) == 5 today
        # (illegible); fs() floors it to 6.
        self.assertEqual(app.fs(8, 0.675), 6)

    def test_an_unaffected_base_at_worst_case_scale_is_a_no_op(self):
        # 9.5 * 0.675 = 6.4125 -> int() already gives 6; fs() changes
        # nothing here.
        self.assertEqual(app.fs(9.5, 0.675), 6)

    def test_windows_linux_100_percent_is_unchanged(self):
        self.assertEqual(app.fs(8, 1.0), 8)

    def test_windows_linux_90_percent_is_unchanged(self):
        self.assertEqual(app.fs(8, 0.9), 7)

    def test_mac_115_percent_floor_is_a_no_op(self):
        self.assertEqual(app.fs(8, 0.8625), 6)

    def test_mac_130_percent_floor_is_a_no_op(self):
        self.assertEqual(app.fs(8, 0.975), 7)

    def test_continuous_s_values_between_the_fixed_steps_still_floor(self):
        # G#38/GH#67: Auto produces continuous s values, not just the four
        # discrete UI_SCALE_FACTORS keys -- fs() is already a pure function
        # of (base, s) for any float s (docs/spec.md §6, and the
        # FONT_SIZE_FLOOR comment at afk_clicker.py that anticipates this
        # exact ticket); this is a property-style check across a dense
        # sweep of in-between values, no UI needed.
        s = 0.9
        while s <= 1.3:
            for base in (6, 7, 8, 9, 9.5, 10, 12):
                with self.subTest(s=round(s, 3), base=base):
                    value = app.fs(base, s)
                    self.assertGreaterEqual(value, app.FONT_SIZE_FLOOR)
                    self.assertEqual(value, max(app.FONT_SIZE_FLOOR, int(base * s)))
            s += 0.025


@needs_display
class SetActiveThemeUnknownName(unittest.TestCase):
    """detect_os_theme() only ever produces "dark"/"light", so this branch
    is unreachable from detection itself -- it only fires if a caller
    (Feature 3's override, or a test) passes a typo/garbage name."""

    def test_unknown_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            app.set_active_theme("solarized")


@needs_display
class SetActiveThemeWidgets(unittest.TestCase):
    """set_active_theme has to reach every place a palette color was
    captured, not just the eleven module globals -- every widget built from
    them at construction time too. Sampling the root window, a card shell,
    a primary button's fill and a NumBox's focus-ring wrap is enough: the
    only place any of the eleven THEMES colors are captured anywhere in this
    file is those bare module globals, read at widget-construction time (no
    default argument, class attribute, or module-level dict/tuple bakes one
    in independently -- confirmed by grep, see docs/history/ac-17-f2-implementation.md)."""

    def setUp(self):
        self.config = os.path.join(tempfile.mkdtemp(), "settings.json")

    def tearDown(self):
        # Unconditional: no later test in the suite may inherit Quartz.
        app.set_active_theme("dark")

    def _build(self):
        root = tk.Tk()
        ui = app.AfkAutoclicker(root, store=app.Store(self.config))
        root.update()

        def _cleanup():
            try:
                ui.on_close()
            except tk.TclError:
                pass
        self.addCleanup(_cleanup)
        return ui

    def _assert_matches(self, ui, palette):
        self.assertEqual(ui.root.cget("bg"), palette["BG"])
        self.assertEqual(ui.eat_card_inner.cget("bg"), palette["CARD"])
        # apply_button starts disabled (set_enabled(False) right after
        # construction, afk_clicker.py:1331), which paints CARD regardless
        # of its primary flag -- enable it to sample its actual primary fill.
        ui.apply_button.set_enabled(True)
        self.assertEqual(
            ui.apply_button.itemcget(ui.apply_button.shape, "fill"),
            palette["ACCENT"])
        self.assertEqual(ui.click_ms.wrap.cget("bg"), palette["LINE"])

    def test_light_theme_reaches_every_sampled_widget(self):
        app.set_active_theme("light")
        self._assert_matches(self._build(), app.THEMES["light"])

    def test_dark_is_restored_after_light(self):
        app.set_active_theme("light")
        self._build()
        app.set_active_theme("dark")
        self._assert_matches(self._build(), app.THEMES["dark"])

    def test_no_theme_call_at_all_still_defaults_to_dark(self):
        # Today's unchanged default: proves this feature adds a new path
        # without disturbing the old one.
        self._assert_matches(self._build(), app.THEMES["dark"])


@needs_display
class DetectOsTheme(unittest.TestCase):
    """detect_os_theme()'s three platform branches and their documented
    failure modes, exercised entirely through the three injectable seams
    (tests/test_hotkey.py:290-316's monkeypatch-and-restore style, no
    unittest.mock anywhere in this suite)."""

    def setUp(self):
        self._platform = app.sys.platform
        self._run_theme_command = app._run_theme_command
        self._read_windows_theme_registry = app._read_windows_theme_registry

    def tearDown(self):
        app.sys.platform = self._platform
        app._run_theme_command = self._run_theme_command
        app._read_windows_theme_registry = self._read_windows_theme_registry

    # -- Windows: winreg via the _read_windows_theme_registry seam --

    def test_windows_registry_value_0_is_dark(self):
        app.sys.platform = "win32"
        app._read_windows_theme_registry = lambda: 0
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_windows_registry_value_1_is_light(self):
        app.sys.platform = "win32"
        app._read_windows_theme_registry = lambda: 1
        self.assertEqual(app.detect_os_theme(), "light")

    def test_windows_registry_garbage_value_is_dark(self):
        app.sys.platform = "win32"
        app._read_windows_theme_registry = lambda: 2
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_windows_registry_missing_key_is_dark(self):
        # FileNotFoundError is an OSError -- older Windows / never-opened
        # Personalization settings.
        app.sys.platform = "win32"
        def raise_missing():
            raise FileNotFoundError("key/value missing")
        app._read_windows_theme_registry = raise_missing
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_windows_registry_unexpected_oserror_is_dark(self):
        app.sys.platform = "win32"
        def raise_oserror():
            raise PermissionError("access denied")
        app._read_windows_theme_registry = raise_oserror
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_windows_registry_any_other_exception_is_dark(self):
        app.sys.platform = "win32"
        def raise_generic():
            raise RuntimeError("unexpected winreg failure")
        app._read_windows_theme_registry = raise_generic
        self.assertEqual(app.detect_os_theme(), "dark")

    # -- macOS: `defaults` via the _run_theme_command seam --

    def test_macos_clean_exit_0_is_dark_regardless_of_stdout(self):
        # detect_os_theme's macOS branch never reads _run_theme_command's
        # stdout at all -- per Apple's own convention (see the comment in
        # detect_os_theme), AppleInterfaceStyle exists, with any value,
        # only in dark mode, so exit status alone decides. stdout is left
        # empty here on purpose, to not imply parsing that doesn't happen.
        app.sys.platform = "darwin"
        app._run_theme_command = lambda args: types.SimpleNamespace(stdout="")
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_macos_key_absent_nonzero_exit_is_light(self):
        # Apple's own convention: no key at all in light mode, so the "clean
        # nonzero exit" CalledProcessError *is* a successful detection.
        app.sys.platform = "darwin"
        def raise_called_process_error(args):
            raise subprocess.CalledProcessError(1, args)
        app._run_theme_command = raise_called_process_error
        self.assertEqual(app.detect_os_theme(), "light")

    def test_macos_defaults_binary_missing_is_dark(self):
        app.sys.platform = "darwin"
        def raise_missing(args):
            raise FileNotFoundError("no defaults binary")
        app._run_theme_command = raise_missing
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_macos_timeout_is_dark(self):
        app.sys.platform = "darwin"
        def raise_timeout(args):
            raise subprocess.TimeoutExpired(args, app._THEME_DETECT_TIMEOUT)
        app._run_theme_command = raise_timeout
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_macos_non_utf8_output_is_dark(self):
        # subprocess.run(text=True) raises UnicodeDecodeError on an invalid
        # byte before _run_theme_command ever returns; the outer catch must
        # not let that escape detect_os_theme().
        app.sys.platform = "darwin"
        def raise_decode(args):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
        app._run_theme_command = raise_decode
        self.assertEqual(app.detect_os_theme(), "dark")

    # -- Linux: gsettings color-scheme, then gtk-theme, via the same seam --

    def test_linux_prefer_dark_short_circuits_before_the_fallback(self):
        app.sys.platform = "linux"
        calls = []
        def fake(args):
            calls.append(args)
            return types.SimpleNamespace(stdout="'prefer-dark'\n")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "dark")
        self.assertEqual(len(calls), 1, "gtk-theme fallback should not run")

    def test_linux_prefer_light(self):
        app.sys.platform = "linux"
        app._run_theme_command = (
            lambda args: types.SimpleNamespace(stdout="'prefer-light'\n"))
        self.assertEqual(app.detect_os_theme(), "light")

    def test_linux_default_falls_through_to_dark_gtk_theme(self):
        app.sys.platform = "linux"
        def fake(args):
            if "color-scheme" in args:
                return types.SimpleNamespace(stdout="'default'\n")
            return types.SimpleNamespace(stdout="'Yaru-dark'\n")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_linux_default_falls_through_to_light_gtk_theme(self):
        app.sys.platform = "linux"
        def fake(args):
            if "color-scheme" in args:
                return types.SimpleNamespace(stdout="'default'\n")
            return types.SimpleNamespace(stdout="'Adwaita'\n")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "light")

    def test_linux_gtk_theme_fallback_known_limitation_dark_theme_without_dark_in_name(self):
        # Documents a known limitation, doesn't assert desired behaviour:
        # "Dracula" is a real, actively-distributed dark GTK theme, but the
        # substring heuristic has no way to know that without "dark" in its
        # name, so it (wrongly) returns "light" here. See the comment above
        # _detect_linux_theme's `return "dark" if "dark" in name else
        # "light"` line -- this pins the current, imperfect behaviour so a
        # future change to the heuristic is a deliberate choice, not an
        # accidental regression this test would silently paper over.
        app.sys.platform = "linux"
        def fake(args):
            if "color-scheme" in args:
                return types.SimpleNamespace(stdout="'default'\n")
            return types.SimpleNamespace(stdout="'Dracula'\n")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "light")

    def test_linux_first_call_raises_second_call_names_dark_case_insensitive(self):
        app.sys.platform = "linux"
        def fake(args):
            if "color-scheme" in args:
                raise FileNotFoundError("no gsettings/schema")
            return types.SimpleNamespace(stdout="'HighContrastDark'\n")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_linux_both_calls_raise_is_dark(self):
        app.sys.platform = "linux"
        def fake(args):
            raise FileNotFoundError("no gsettings")
        app._run_theme_command = fake
        self.assertEqual(app.detect_os_theme(), "dark")

    def test_linux_both_calls_empty_output_is_dark(self):
        app.sys.platform = "linux"
        app._run_theme_command = lambda args: types.SimpleNamespace(stdout="")
        self.assertEqual(app.detect_os_theme(), "dark")

    # -- Anything else --

    def test_unrecognized_platform_is_dark(self):
        app.sys.platform = "sunos5"
        self.assertEqual(app.detect_os_theme(), "dark")


@needs_display
class RunThemeCommandSeam(unittest.TestCase):
    """_run_theme_command itself, invoking a real subprocess -- the seam
    tests above only ever simulate this function, they never exercise its
    own argv/timeout/decoding plumbing for real."""

    def test_real_invocation_captures_stdout(self):
        result = app._run_theme_command([sys.executable, "-c", "print('hello')"])
        self.assertEqual(result.stdout.strip(), "hello")

    def test_invalid_utf8_byte_in_output_does_not_raise(self):
        # A stray non-UTF-8 byte must not turn into an uncaught
        # UnicodeDecodeError -- errors="replace" turns it into U+FFFD, which
        # the normal "unrecognized value" fallthrough already handles,
        # rather than adding a third failure mode needing its own catch.
        result = app._run_theme_command(
            [sys.executable, "-c",
             "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"])
        self.assertIn("�", result.stdout)


@needs_display
class FlatChrome(unittest.TestCase):
    """Story #24 feature 5: round_rect() is gone outright, and every widget
    that used to draw a pill/rounded-card shape now paints a plain
    create_rectangle -- checked per widget, same granularity the old
    radius-recording assertions had, just against shape kind instead of a
    now-nonexistent radius argument."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_no_widget_calls_round_rect(self):
        self.assertFalse(hasattr(app, "round_rect"))

    def test_card_r_and_pill_r_are_gone(self):
        self.assertFalse(hasattr(app, "CARD_R"))
        self.assertFalse(hasattr(app, "PILL_R"))

    def test_button_shape_is_a_plain_rectangle(self):
        btn = app.Button(self.root, "Go", lambda: None, 1.0)
        self.assertEqual(btn.type(btn.shape), "rectangle")

    def test_segmented_track_shape_is_a_plain_rectangle(self):
        var = tk.StringVar(value="a")
        seg = app.Segmented(self.root, [("a", "A"), ("b", "B")], var, 1.0)
        track = seg.find_all()[0]     # the outer track is the first item
                                       # created, before the selection pill
        self.assertEqual(seg.type(track), "rectangle")

    def test_segmented_selection_pill_moves_to_the_correct_segment(self):
        # Replaces the old capsule-geometry assertions: position, not
        # capsule shape, which no longer exists.
        var = tk.StringVar(value="a")
        seg = app.Segmented(self.root, [("a", "A"), ("b", "B")], var, 1.0)
        seg.var.set("b")
        self.root.update()
        seg_w = seg.w / len(seg.options)
        expected = [seg_w * 1 + 2, 2, seg_w * 2 - 2, seg.h - 2]
        self.assertEqual(seg.coords(seg.pill), expected)

    def test_status_pill_shape_is_a_plain_rectangle(self):
        pill = app.StatusPill(self.root, 1.0)
        self.assertEqual(pill.type(pill.shape), "rectangle")

    def test_game_item_shape_is_a_plain_rectangle(self):
        item = app.GameItem(self.root, {"id": "x", "name": "X"}, lambda gid: None, 1.0)
        self.assertEqual(item.type(item.shape), "rectangle")

    def test_settings_item_shape_is_a_plain_rectangle(self):
        item = app.SettingsItem(self.root, lambda: None, 1.0)
        self.assertEqual(item.type(item.shape), "rectangle")

    def test_card_shell_shape_is_a_plain_rectangle(self):
        inner = app.card(self.root, 1.0)
        shell = inner.master
        shell.update_idletasks()
        types = [shell.type(i) for i in shell.find_all()]
        self.assertIn("rectangle", types)
        self.assertNotIn("polygon", types)


@needs_display
class SectionHeader(unittest.TestCase):
    """section() drops .upper() and gains an optional right-aligned
    action_factory slot -- both real, tested mechanisms even though no
    production call site passes action_factory today (this story's own
    TabBar.height precedent: an accepted-but-ignored parameter is a latent
    trap, so the slot gets direct coverage regardless of callers)."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_section_text_is_not_uppercased(self):
        row = app.section(self.root, "Mixed Case", 1.0)
        label = row.winfo_children()[0]
        self.assertEqual(label.cget("text"), "Mixed Case")

    def test_section_with_no_action_has_no_reserved_gap(self):
        row = app.section(self.root, "Test", 1.0)
        label = row.winfo_children()[0]
        row.update_idletasks()
        self.assertEqual(row.winfo_reqwidth(), label.winfo_reqwidth())

    def test_section_action_factory_is_actually_wired(self):
        # A bare tk.Tk() root shrink-wraps to its packed children's own
        # requested size, so with no forced width there's no leftover space
        # for pack(side="right") to push against -- side="right" and
        # side="left" land the action widget at the *same* winfo_x() in an
        # unconstrained parent (confirmed directly: 33 both ways). A fixed-
        # width, pack_propagate(False) container -- the same shape every
        # real content pane in this app already uses -- gives the row real
        # slack, so "packed at the right edge" and "packed adjacent to the
        # label" actually produce different numbers.
        container = tk.Frame(self.root, width=500, height=50)
        container.pack_propagate(False)
        container.pack()
        row = app.section(container, "Test", 1.0,
                          action_factory=lambda r: tk.Button(r, text="Do"))
        row.update_idletasks()
        label, action = row.winfo_children()
        # Right of the label, with a genuine gap now that one can exist.
        self.assertGreater(action.winfo_x(), label.winfo_x() + label.winfo_width())
        # Flush against the row's own right edge -- the direct proof that
        # section() used pack(side="right"), not merely "somewhere right of
        # the label" (which a left-packed-after-some-spacer layout could
        # also satisfy).
        self.assertEqual(action.winfo_x() + action.winfo_width(), row.winfo_width())


@needs_display
class RailAccent(unittest.TestCase):
    """The rail's active item gets the one sparing-accent home it was
    missing (docs/spec.md): a left-edge accent bar, toggled strictly on
    `selected`, independent of any other per-item signal."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_selected_game_item_shows_the_accent_bar(self):
        for collapsed in (False, True):
            with self.subTest(collapsed=collapsed):
                item = app.GameItem(self.root, {"id": "x", "name": "X"},
                                    lambda gid: None, 1.0, collapsed=collapsed)
                item.set_state(selected=True)
                self.assertEqual(item.itemcget(item.accent_bar, "state"), "normal")

    def test_unselected_game_item_hides_the_accent_bar(self):
        for collapsed in (False, True):
            with self.subTest(collapsed=collapsed):
                item = app.GameItem(self.root, {"id": "x", "name": "X"},
                                    lambda gid: None, 1.0, collapsed=collapsed)
                item.set_state(selected=False)
                self.assertEqual(item.itemcget(item.accent_bar, "state"), "hidden")

    def test_settings_item_accent_bar_is_independent_of_has_update(self):
        item = app.SettingsItem(self.root, lambda: None, 1.0,
                                has_update=True, collapsed=False)
        item.set_state(selected=False)
        self.assertEqual(item.itemcget(item.accent_bar, "state"), "hidden")

        item.set_state(selected=True, has_update=False)
        self.assertEqual(item.itemcget(item.accent_bar, "state"), "normal")

    def test_running_dot_and_accent_bar_coexist(self):
        item = app.GameItem(self.root, {"id": "x", "name": "X"},
                            lambda gid: None, 1.0)
        item.set_state(selected=True, running=True)
        self.assertEqual(item.itemcget(item.accent_bar, "state"), "normal")
        self.assertEqual(item.itemcget(item.dot, "fill"), app.OK)
        self.assertNotEqual(item.accent_bar, item.dot)


@needs_display
class PrimaryButtonTheme(unittest.TestCase):
    """The old hardcoded '#ffd66b'/'#12131a' literals are gone."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_rest_uses_accent_and_accent_ink(self):
        b = app.Button(self.root, "Go", lambda: None, 1.0, primary=True)
        self.assertEqual(b.itemcget(b.shape, "fill"), app.ACCENT)
        self.assertEqual(b.itemcget(b.label, "fill"), app.ACCENT_INK)

    def test_hover_uses_accent_hi_and_accent_ink(self):
        b = app.Button(self.root, "Go", lambda: None, 1.0, primary=True)
        b._paint(hover=True)
        self.assertEqual(b.itemcget(b.shape, "fill"), app.ACCENT_HI)
        self.assertEqual(b.itemcget(b.label, "fill"), app.ACCENT_INK)


@needs_display
class CardShell(CapturesCallbackExceptions, unittest.TestCase):
    """card() becomes a borderless canvas hosting the returned Frame."""

    def setUp(self):
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.root.geometry("500x400")
        self.parent = tk.Frame(self.root, bg=app.BG)
        self.parent.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self._assert_no_callback_exceptions()

    def test_shell_is_a_borderless_canvas(self):
        inner = app.card(self.parent, 1.0)
        shell = inner.master
        self.assertIsInstance(shell, tk.Canvas)
        self.assertEqual(int(shell.cget("highlightthickness")), 0)
        shape = shell.find_all()[0]
        self.assertEqual(shell.itemcget(shape, "outline"), "")

    def test_callers_still_get_a_packable_frame_back(self):
        inner = app.card(self.parent, 1.0)
        self.assertIsInstance(inner, tk.Frame)

    def test_shell_redraws_when_the_content_pane_widens(self):
        inner = app.card(self.parent, 1.0)
        tk.Label(inner, text="hello", bg=app.CARD).pack()
        shell = inner.master
        self.root.update()
        before = shell.bbox(shell.find_all()[0])

        self.root.geometry("900x700")
        self.root.update()
        after = shell.bbox(shell.find_all()[0])

        self.assertGreater(after[2] - after[0], before[2] - before[0])
        # The shape's own bounding box must track the shell's real size, not
        # go stale or clip -- a `<Configure>` storm or a redraw that only
        # fires once would leave this mismatched.
        self.assertAlmostEqual(after[2] - after[0], shell.winfo_width(), delta=2)

    def test_redraw_bails_out_once_its_shell_is_destroyed(self):
        """docs/history/ac-17-f3a-test-review.md Finding #2: card()'s two winfo_exists()
        guards (afk_clicker.py's _redraw()) had zero direct test coverage --
        removing both lines still left the full suite green, since
        coalescing alone already prevented the shapes the other tests
        drive. Captures the real _redraw closure card() binds to
        <Configure> by intercepting tk.Canvas.bind while card() runs (not
        by changing card() itself -- the closure is otherwise private), then
        dispatches it through Tk's own callback machinery (after_idle) once
        its shell is already destroyed -- a late/stale callback firing
        against a torn-down widget, the exact shape the guard exists for."""
        captured = []
        original_bind = tk.Canvas.bind

        def capturing_bind(canvas_self, sequence=None, func=None, add=None):
            if sequence == "<Configure>" and func is not None and not captured:
                captured.append(func)
            return original_bind(canvas_self, sequence, func, add)

        tk.Canvas.bind = capturing_bind
        try:
            inner = app.card(self.parent, 1.0)
        finally:
            tk.Canvas.bind = original_bind
        self.assertEqual(len(captured), 1, "card()'s _redraw was not captured")
        redraw = captured[0]

        shell = inner.master
        shell.destroy()
        self.root.update()

        # A genuine Tk-dispatched callback (not a bare Python call, which
        # would just raise straight into this test) -- exactly how a late/
        # stale <Configure> event would actually reach _redraw() for real.
        self.root.after_idle(redraw)
        self.root.update()

        self._assert_no_callback_exceptions()


class EatingCardCanvas(UITestCase):
    """Non-regression: `.pack()/.pack_forget()` on `eat_card` still works
    now that it is a Canvas shell rather than a bordered Frame."""

    def test_eat_card_is_now_a_canvas(self):
        self.assertIsInstance(self.ui.eat_card, tk.Canvas)

    def test_show_and_hide_still_toggle_the_manager(self):
        self.ui._select("minecraft")
        self.assertEqual(self.ui.eat_card.winfo_manager(), "pack")
        self.ui._select("global")
        self.assertEqual(self.ui.eat_card.winfo_manager(), "")
        self.ui._select("minecraft")
        self.assertEqual(self.ui.eat_card.winfo_manager(), "pack")


class CardResize(UITestCase):
    """A real card in the running app tracks #14's resizable window."""

    def _hotkey_card_shell(self):
        # apply_button -> btns -> hk (the inner Frame `card()` returned) ->
        # the shell Canvas. No attribute holds the shell directly, since
        # `_build_content`'s call sites only keep the returned inner Frame.
        return self.ui.apply_button.master.master.master

    def test_the_hotkey_cards_shell_widens_with_the_content_pane(self):
        shell = self._hotkey_card_shell()
        self.assertIsInstance(shell, tk.Canvas)
        before = shell.winfo_width()

        self.root.geometry("1000x900")
        self.root.update()

        self.assertGreater(shell.winfo_width(), before)
        bbox = shell.bbox(shell.find_all()[0])
        self.assertAlmostEqual(bbox[2] - bbox[0], shell.winfo_width(), delta=2)


class RoundedCanvasBackgrounds(UITestCase):
    """Every canvas that draws a full-bleed flat background shape must paint
    its parent's own background outside that shape -- otherwise the shape's
    inset edges (the 1px outline-stroke margin most of these use) sit on a
    mismatched square (docs/history/ac-17-f1-design.md item 3, originally
    about round_rect()'s corners; the same invariant holds for a flat
    inset rectangle). Story #24 feature 5 deleted round_rect() and its
    single create_polygon call, so keying this off item type ("any canvas
    holding a polygon") no longer finds anything.

    Re-keying off "any canvas holding a create_rectangle item" instead
    would misfire the other way: TabBar's own active-tab underline
    (afk_clicker.py, a 2px-tall create_rectangle) and Segmented's selection
    pill are both legitimate small rectangles that were never meant to
    cover their canvas edge-to-edge. Keying off the widget *classes* that
    draw a full-bleed background shape -- the six named in docs/spec.md's
    mechanical swap list, plus card()'s shell (the only bare tk.Canvas()
    construction anywhere in the file, grep-confirmed, so `type(widget) is
    tk.Canvas` -- exact type, not isinstance/subclass -- uniquely finds it
    without also matching Button/Segmented/etc, which are all tk.Canvas
    subclasses) -- avoids both traps."""

    _FLAT_BG_CLASSES = (app.Button, app.Segmented, app.StatusPill,
                        app.GameItem, app.SettingsItem)

    def _flat_bg_canvases(self, widget):
        found = []
        if isinstance(widget, self._FLAT_BG_CLASSES) or type(widget) is tk.Canvas:
            found.append(widget)
        for child in widget.winfo_children():
            found.extend(self._flat_bg_canvases(child))
        return found

    def test_every_flat_bg_canvas_matches_its_parents_background(self):
        canvases = self._flat_bg_canvases(self.root)
        self.assertTrue(canvases, "setup failed to find any flat-bg canvas")
        mismatches = [(str(cv), cv.cget("bg"), cv.master.cget("bg"))
                     for cv in canvases if cv.cget("bg") != cv.master.cget("bg")]
        self.assertEqual(mismatches, [],
            "canvas bg must match its parent's bg, or the area outside the "
            "shape's own inset paints a visible mismatched rectangle")


class AppearanceStore(UITestCase):
    """Store.__init__'s new "appearance" key -- same sanitiser shape/spirit
    as the existing "games" filter (StoreMigration above)."""

    def _write(self, data):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_a_fresh_store_defaults_to_system(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.assertEqual(app.Store(path).data["appearance"], "system")

    def test_known_values_round_trip(self):
        for value in ("system", "light", "dark"):
            with self.subTest(value=value):
                path = self._write({"appearance": value})
                self.assertEqual(app.Store(path).data["appearance"], value)

    def test_garbage_values_fall_back_to_system(self):
        for value in ("sepia", None, 42):
            with self.subTest(value=value):
                path = self._write({"appearance": value})
                self.assertEqual(app.Store(path).data["appearance"], "system")

    def test_a_missing_appearance_key_defaults_to_system(self):
        path = self._write({"games": {}, "hotkey": None, "selected": None})
        self.assertEqual(app.Store(path).data["appearance"], "system")


@needs_display
class AppearanceThemeSwitch(CapturesCallbackExceptions, unittest.TestCase):
    """Picking a segment rebuilds the window with the matching palette --
    sampling the same widgets Feature 2's test_light_theme_reaches_every_
    sampled_widget samples, using the post-rebuild references."""

    def setUp(self):
        self.config = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()

    def tearDown(self):
        # See UITestCase.tearDown()'s comment (G#27/GH#46): this class
        # builds and closes its own UI the same way, so it needs the same
        # main-thread collection to avoid leaving Variable finalisation for
        # a later test's worker thread.
        try:
            self.ui.on_close()
        except tk.TclError:
            pass
        gc.collect()
        self._assert_no_callback_exceptions()
        # Unconditional: no later test in the suite may inherit Quartz.
        app.set_active_theme("dark")

    def _assert_matches(self, palette):
        self.assertEqual(self.ui.root.cget("bg"), palette["BG"])
        self.assertEqual(self.ui.eat_card_inner.cget("bg"), palette["CARD"])
        self.ui.apply_button.set_enabled(True)
        self.assertEqual(
            self.ui.apply_button.itemcget(self.ui.apply_button.shape, "fill"),
            palette["ACCENT"])
        self.assertEqual(self.ui.click_ms.wrap.cget("bg"), palette["LINE"])

    def test_switching_to_light_and_back_repaints_the_rebuilt_widgets(self):
        old_click_ms = self.ui.click_ms
        old_apply_button = self.ui.apply_button

        self.ui._apply_appearance("light")
        self.root.update()
        # Proves the rebuild actually replaced the widgets, not that stale
        # references happen to still resolve.
        self.assertIsNot(self.ui.click_ms, old_click_ms)
        self.assertIsNot(self.ui.apply_button, old_apply_button)
        self._assert_matches(app.THEMES["light"])

        self.ui._apply_appearance("dark")
        self.root.update()
        self._assert_matches(app.THEMES["dark"])

    def test_appearance_is_persisted_to_disk(self):
        self.ui._apply_appearance("light")
        self.root.update()
        on_disk = json.load(open(self.config, encoding="utf-8"))
        self.assertEqual(on_disk["appearance"], "light")


class UIScaleStore(UITestCase):
    """Store.__init__'s new "ui_scale" key -- same sanitiser shape/spirit as
    "appearance" (AppearanceStore, above)."""

    def _write(self, data):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_a_fresh_store_defaults_to_auto(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.assertEqual(app.Store(path).data["ui_scale"], "auto")

    def test_known_values_round_trip(self):
        for value in ("auto", "90", "100", "115", "130"):
            with self.subTest(value=value):
                path = self._write({"ui_scale": value})
                self.assertEqual(app.Store(path).data["ui_scale"], value)

    def test_garbage_values_fall_back_to_auto(self):
        for value in ("120", None, 42):
            with self.subTest(value=value):
                path = self._write({"ui_scale": value})
                self.assertEqual(app.Store(path).data["ui_scale"], "auto")

    def test_a_missing_ui_scale_key_defaults_to_auto(self):
        path = self._write({"games": {}, "hotkey": None, "selected": None})
        self.assertEqual(app.Store(path).data["ui_scale"], "auto")

    def test_a_garbage_on_disk_value_resolves_to_auto_end_to_end(self):
        # Same technique as AppearanceStore.test_a_missing_appearance_key_
        # defaults_to_system -- write directly into the test's own
        # settings.json -- but goes one step further, all the way through a
        # fresh AfkAutoclicker (self.restart()), per docs/history/ac-17-f4-spec.md's
        # acceptance criterion: a garbage stored "ui_scale" must sanitize to
        # "auto". G#38/GH#67: Auto's own bootstrap (docs/spec.md §3) sets
        # self.s = self._dpi_s * 1.0 for the very first _build_ui()/
        # _apply_minsize() call -- the same no-op-1.0-factor value "100"
        # always gave here -- but round 3 (PR #89 review) dropped this
        # test's own follow-on "ui.s == ui._dpi_s" assertion: that only
        # holds when nothing ever recomputes self.s away from the
        # bootstrap value before this reads it, which is only true when
        # there is no real window manager to deliver a post-map
        # <Configure> at all (this session's own Xvfb) -- on a real WM
        # (macOS/Windows CI), restart()'s own single root.update() can
        # already have let a genuine one land and legitimately correct
        # self.s to the real screen, which is Auto working as designed
        # (docs/spec.md's Edge cases), not a sanitisation failure. The
        # sanitisation this test is actually named for is the assertion
        # below, which is WM-independent.
        with open(self.config, "w") as fh:
            json.dump({"games": {}, "hotkey": None, "selected": None,
                       "ui_scale": "120"}, fh)
        ui = self.restart()
        self.assertEqual(ui.store.data["ui_scale"], "auto")


class SaveFailureNotice(UITestCase):
    """G#21/GH#32 item 4 (docs/spec.md, docs/design.md): Store.save() now
    reports success/failure instead of swallowing every OSError silently,
    and AfkAutoclicker surfaces a single, non-repeating, non-blocking
    notice in Settings -> Appearance the first time a save actually fails,
    clearing it the next time one succeeds. Every save is simulated by
    monkeypatching app.os.replace to raise OSError (this repo's monkeypatch-
    -and-restore style, no unittest.mock, no real filesystem permission
    bits -- tests/test_ui.py:StoreSaveResult uses the same seam)."""

    def _break_saves(self):
        original_replace = app.os.replace

        def raising_replace(*a, **kw):
            raise OSError("read-only filesystem")

        app.os.replace = raising_replace
        return original_replace

    def _fix_saves(self, original_replace):
        app.os.replace = original_replace

    def test_notice_appears_in_the_appearance_pane_on_a_failed_save(self):
        self.ui._show_settings()
        self.root.update()
        original = self._break_saves()
        try:
            self.ui._apply_appearance("light")
            self.root.update()
        finally:
            self._fix_saves(original)
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped())
        self.assertEqual(
            self.ui.save_failed_label.cget("text"),
            "Couldn't save settings — changes won't be kept after closing")

    def test_no_repaint_on_a_second_consecutive_failure(self):
        # Tests the property _note_save() exists for (docs/CODING-
        # GUIDELINES.md "Tests": test the property, not the plumbing), not
        # the widget: a run of keystroke-driven failures while a directory
        # stays read-only must not repaint after the first one.
        calls = {"n": 0}
        original_paint = self.ui._paint_save_notice

        def counting_paint():
            calls["n"] += 1
            original_paint()

        self.ui._paint_save_notice = counting_paint
        try:
            self.ui._note_save(False)
            self.ui._note_save(False)
            self.ui._note_save(False)
        finally:
            self.ui._paint_save_notice = original_paint
        self.assertEqual(calls["n"], 1,
                         "a second/third consecutive failure repainted the notice")

    def test_notice_clears_once_a_save_succeeds_again(self):
        self.ui._show_settings()
        self.root.update()
        original = self._break_saves()
        try:
            self.ui._apply_appearance("light")
            self.root.update()
        finally:
            self._fix_saves(original)
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped())

        self.ui._apply_appearance("dark")   # a real save, now unpatched
        self.root.update()
        self.assertFalse(self.ui.save_failed_label.winfo_ismapped())

    def test_notice_survives_a_rebuild_triggered_by_the_failing_save_itself(self):
        # docs/spec.md's own edge case: _apply_appearance's failed save is
        # what triggers _request_rebuild()/_rebuild_ui() -- the notice must
        # still be showing in the freshly-rebuilt Appearance pane once that
        # same rebuild finishes, not just before it started.
        self.ui._show_settings()
        self.root.update()
        old_label = self.ui.save_failed_label
        original = self._break_saves()
        try:
            self.ui._apply_appearance("light")   # queues after_idle(self._rebuild_ui)
            self.root.update()                   # runs the queued rebuild
        finally:
            self._fix_saves(original)
        self.assertFalse(old_label.winfo_exists(),
                         "test needs the rebuild to actually have run")
        self.assertTrue(self.ui._settings_open)
        self.assertEqual(self.ui._settings_tab, "appearance")
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped(),
                        "the notice must survive the rebuild its own failure caused")

    def test_notice_is_not_shown_while_a_different_settings_tab_is_active(self):
        self.ui._show_settings()
        self.ui._set_settings_tab("updates")
        self.root.update()
        original = self._break_saves()
        try:
            self.ui._apply_appearance("light")
            self.root.update()
        finally:
            self._fix_saves(original)
        self.assertFalse(self.ui.save_failed_label.winfo_ismapped())
        self.ui._set_settings_tab("appearance")
        self.root.update()
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped(),
                        "opening Appearance later must still show the remembered failure")

    def test_no_crash_the_first_time_settings_is_ever_opened_after_a_save_already_failed(self):
        # test-review.md round 1, Defect 1, Path A: no Settings pane has
        # ever been built this session, so self.save_failed_label does not
        # exist yet. _show_settings() sets self._settings_open = True and
        # then calls _rebuild_ui(), whose own leading self._persist() call
        # (flushing any in-progress field edit) fails here -- before
        # _build_settings() (reached later in the same _rebuild_ui() call)
        # ever creates the label. Must not raise, and the notice must be
        # visible in the freshly-built Appearance pane once _show_settings()
        # returns.
        original = self._break_saves()
        try:
            self.ui._show_settings()
            self.root.update()
        finally:
            self._fix_saves(original)
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped())

    def test_no_crash_reopening_settings_after_a_save_fails_while_settings_is_closed(self):
        # test-review.md round 1, Defect 1, Path B: Settings is opened once
        # (creating the label), then closed -- the close rebuilds without a
        # Settings pane, destroying that label, but self.save_failed_label
        # still points at the now-dead widget. A save then fails while
        # Settings stays closed, and reopening Settings must not touch the
        # destroyed widget via the same leading _persist() flush.
        self.ui._show_settings()
        self.root.update()
        old_label = self.ui.save_failed_label
        self.ui._select(self.ui.current, persist=False)   # closes Settings
        self.root.update()
        self.assertFalse(old_label.winfo_exists(),
                         "test needs closing Settings to actually destroy the label")
        original = self._break_saves()
        try:
            self.ui._show_settings()
            self.root.update()
        finally:
            self._fix_saves(original)
        self.assertTrue(self.ui.save_failed_label.winfo_ismapped())

    def test_every_save_call_site_can_trigger_the_notice(self):
        # docs/spec.md acceptance criterion: all five of Store.save()'s call
        # sites route through _note_save() -- verified by triggering a
        # failure via each in turn.
        self.ui._show_settings()
        self.root.update()

        def via_apply_appearance():
            self.ui._apply_appearance("light")

        def via_apply_ui_scale():
            self.ui._apply_ui_scale("115")

        def via_select_persist():
            self.ui._select("minecraft", persist=True)

        def via_persist():
            self.ui._select("minecraft", persist=False)
            self.ui._persist()

        def via_apply_hotkey():
            # HotkeyPersistence's class comment explains why: apply_hotkey()
            # only reaches _note_save() after a real HotkeyWatcher.start()
            # returns, and starting a real listener aborts the process on
            # macOS regardless of permission. Stub the class for this call
            # only, so the save is exercised on every platform without ever
            # starting a real listener.
            original_watcher = app.HotkeyWatcher

            class _StubHotkeyWatcher:
                def __init__(self, hotkey, callback):
                    pass

                def start(self):
                    pass

                def stop(self):
                    pass

            app.HotkeyWatcher = _StubHotkeyWatcher
            try:
                self.ui.hotkey = hotkey({"ctrl"}, [kb.Key.f9])
                self.ui.apply_hotkey()
            finally:
                app.HotkeyWatcher = original_watcher

        triggers = [via_apply_appearance, via_apply_ui_scale, via_select_persist,
                   via_persist, via_apply_hotkey]
        for trigger in triggers:
            with self.subTest(trigger=trigger.__name__):
                self.ui._save_failed = False
                self.ui._paint_save_notice()
                original = self._break_saves()
                try:
                    trigger()
                    self.root.update()
                finally:
                    self._fix_saves(original)
                self.assertTrue(
                    self.ui._save_failed,
                    f"{trigger.__name__} did not route its save through _note_save()")


class UIScale(UITestCase):
    """The Settings page's second Appearance-card Row (docs/history/ac-17-f4-spec.md, story
    #17 Feature 4): self.s becomes DPI x the chosen step, applied through
    the same in-place rebuild mechanism Feature 3 built for Appearance --
    structurally parallel to AppearanceThemeSwitch/WindowResize above."""

    # G#38/GH#67 round 3 (PR #89 review): same reasoning as WindowResize's
    # own INITIAL_UI_SCALE -- every test below drives self.s through
    # explicit _apply_ui_scale() calls of its own, so Auto being the
    # ambient construction-time default is purely incidental here, not
    # something these fixed-step tests want to exercise; leaving it in
    # Auto let a real window manager's own construction-time correction
    # (and its resulting geometry() round-trip) interfere with a test's own
    # subsequent _apply_ui_scale()/geometry() calls on macOS/Windows CI.
    INITIAL_UI_SCALE = "100"

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_each_step_multiplies_the_dpi_factor(self):
        for value in ("90", "100", "115", "130"):
            with self.subTest(value=value):
                self.ui._apply_ui_scale(value)
                self.root.update()
                self.assertEqual(self.ui.s,
                                 self.ui._dpi_s * app.UI_SCALE_FACTORS[value])

    def test_a_sampled_widget_and_font_scale_with_it(self):
        # _appearance_segment() needs appearance_var to already exist, which
        # only happens once Settings has been built -- same precondition
        # every other test using it already meets (SettingsNavigation,
        # OverlappingAppearanceChanges).
        self.ui._show_settings()
        self.root.update()
        self.ui._apply_ui_scale("130")
        self.root.update()
        # The header StatusPill, rebuilt fresh -- Canvas widths round-trip
        # through cget() as the same int the constructor was given.
        self.assertEqual(int(self.ui.status.cget("width")), int(250 * self.ui.s))
        # The Theme Segmented's own text item font, same control
        # _appearance_segment() already locates for the Appearance tests --
        # re-fetched after the scale change since the rebuild replaced it.
        seg = self._appearance_segment()
        self.assertEqual(seg.itemcget(seg.texts[0], "font"),
                         f"{{Segoe UI}} {int(9 * self.ui.s)}")

    def test_minsize_updates_on_every_scale_change(self):
        for value in ("90", "115", "130", "100"):
            with self.subTest(value=value):
                self.ui._apply_ui_scale(value)
                self.root.update()
                # The floor is always SIDEBAR_RAIL_W-based (story #24
                # feature 3) -- this test runs at default (expanded, never
                # manually resized) window state throughout, proving the
                # floor is a property of self.s alone, not of whatever the
                # rail currently looks like.
                expected = (int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * self.ui.s),
                           int(app.WINDOW_MIN_H * self.ui.s))
                self.assertEqual(self.root.minsize(), expected)

    def test_a_bigger_step_grows_the_window_to_the_new_minimum(self):
        self.ui._apply_ui_scale("130")
        self.root.update()
        minw, minh = self.root.minsize()
        self.assertGreaterEqual(self.root.winfo_width(), minw)
        self.assertGreaterEqual(self.root.winfo_height(), minh)

    def test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change(self):
        # Matches WindowResize's own geometry-reading pattern (line ~746),
        # but derives the "manually enlarged" size from the biggest step's
        # own minsize (plus margin) rather than a hardcoded literal -- must
        # exceed every step's minsize, including 130%'s, on any DPI this
        # suite runs under (docs/history/ac-17-f4-spec.md's own invariant-ratio argument,
        # §1: a bigger step's minsize is a strictly bigger floor).
        #
        # Uses the SIDEBAR_W-based (expanded) formula, not the real
        # SIDEBAR_RAIL_W-based floor _apply_minsize() now computes (story
        # #24 feature 3) -- that only makes min_w a safe (if now
        # over-generous) upper bound to enlarge past, never the literal
        # floor being asserted here.
        max_s = self.ui._dpi_s * app.UI_SCALE_FACTORS["130"]
        min_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * max_s)
        min_h = int(app.WINDOW_MIN_H * max_s)
        big_w = min_w + 200
        big_h = min_h + 200
        self.root.geometry(f"{big_w}x{big_h}")
        self.root.update()
        # A window manager can clamp a geometry request to the screen it
        # actually has rather than granting it outright -- observed on the
        # Windows and macOS CI runners' own (smaller) displays. The
        # "manually enlarged" size is therefore whatever was actually
        # granted, not what was asked for.
        actual_w, actual_h = self.root.winfo_width(), self.root.winfo_height()
        if actual_w < min_w or actual_h < min_h:
            # The runner's screen won't grant a size above 130%'s own
            # minsize, so the "never shrunk below the user's size" premise
            # cannot hold here -- there is no manually-enlarged size left
            # to shrink from. Skipping is honest here; asserting on the
            # request rather than the grant is what made this test fail on
            # the Windows and macOS runners in the first place.
            self.skipTest(
                "WM clamped the enlarged geometry to at or below 130%'s "
                "minsize on this screen -- nothing to test")
        for value in ("130", "90"):
            with self.subTest(value=value):
                self.ui._apply_ui_scale(value)
                self.root.update()
                self.assertEqual(self.root.winfo_width(), actual_w)
                self.assertEqual(self.root.winfo_height(), actual_h)

    def test_a_scale_choice_survives_a_restart_with_no_settings_visit(self):
        self.ui._apply_ui_scale("90")
        self.root.update()
        expected_s = self.ui._dpi_s * app.UI_SCALE_FACTORS["90"]
        ui = self.restart()
        # self.ui.s reflects the persisted choice without ever opening
        # Settings -- computed straight from self.store.data in __init__.
        self.assertEqual(ui.s, expected_s)
        # ui_scale_var itself is only built once Settings is opened (same
        # as appearance_var, see SettingsNavigation's own tests) -- confirm
        # it then reflects the same persisted choice.
        ui._show_settings()
        self.root.update()
        self.assertEqual(ui.ui_scale_var.get(), "90")

    def test_ui_scale_is_persisted_to_disk(self):
        self.ui._apply_ui_scale("115")
        self.root.update()
        on_disk = json.load(open(self.config, encoding="utf-8"))
        self.assertEqual(on_disk["ui_scale"], "115")

    def test_two_real_ui_scale_segmented_clicks_with_no_pump_between_them(self):
        # docs/history/ac-17-f4-implementation.md Finding #1: every other test in this class
        # calls self.ui._apply_ui_scale(value) directly, so neither write
        # trace registered on ui_scale_var (Segmented's own repaint trace,
        # and _apply_ui_scale itself) is ever invoked by a real click --
        # including the one whose *registration order* docs/history/ac-17-f4-spec.md §2
        # flags as a TclError hazard (afk_clicker.py:1901-1926). Mirrors
        # Theme's own real-click regression test,
        # test_two_real_segmented_clicks_with_no_pump_between_them
        # (line ~2309): two back-to-back <Button-1> events with no
        # root.update() between them, then one pump. G#38/GH#67 grew this
        # control from 4 options to 5 ("Auto" prepended), so seg_w now
        # divides by 5; "100%" and "130%" are options index 2 and 4.
        self.ui._show_settings()
        self.root.update()
        seg = self._appearance_segment(self.ui.ui_scale_var)
        seg_w = seg.w / 5
        seg.event_generate("<Button-1>", x=int(seg_w * 2.5), y=int(seg.h / 2))  # "100%"
        seg.event_generate("<Button-1>", x=int(seg_w * 4.5), y=int(seg.h / 2))  # "130%"
        self.root.update()
        self.assertEqual(self.ui.ui_scale_var.get(), "130")
        self.assertEqual(self.ui.s, self.ui._dpi_s * app.UI_SCALE_FACTORS["130"])


class UIScaleAuto(UITestCase):
    """G#38/GH#67: Auto mode's continuous self.s, live minsize/rail
    tracking, and settle-debounced rebuild -- structurally parallel to
    WindowResize/RailCollapse above, but exercising Auto's continuously
    changing self.s instead of a scale pinned to a fixed step. Runs
    against the new fresh-install default (UI_SCALE_DEFAULT == "auto", see
    UIScaleStore above) -- no explicit _apply_ui_scale() call needed to
    reach Auto mode.

    Only the mechanics this Xvfb suite can actually exercise are tested
    here (root.geometry()/event_generate("<Configure>") + root.update(),
    the same technique WindowResize/RailCollapse already use successfully
    under Xvfb) -- a genuine WM-driven post-map <Configure> on first
    launch (the "parity on a real 1920x1080 screen" bootstrap path) is not
    reproducible without a real window manager and is left to the
    Windows/macOS CI legs, per docs/spec.md's own Acceptance criteria."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def _wh_for_factor(self, target_factor):
        """Back-solves a (width, height) pair, at the app's own default
        aspect ratio, that makes self.ui._auto_scale_factor(width, height)
        land at target_factor -- avoids hardcoding pixel literals tuned to
        one particular screen size, since the real Xvfb/CI screen size
        varies (this session's own is not 1920x1080)."""
        aspect = (app.SIDEBAR_W + 1 + app.CONTENT_W) / app.WINDOW_MIN_H
        fill = target_factor * app.AUTO_REFERENCE_FILL
        area = (fill ** 2) * self.ui._screen_w * self.ui._screen_h
        width = int((area * aspect) ** 0.5)
        height = int((area / aspect) ** 0.5)
        return width, height

    def test_calibration_lands_at_parity_on_a_1920x1080_screen(self):
        # The formula itself, independent of the real screen this suite
        # happens to run under (forced the same way
        # FontSizeFloorAtWorstCaseScale forces self.ui._dpi_s directly) --
        # docs/spec.md §2's calibration: the app's own default launch
        # geometry on a 1920x1080 screen must land at factor == 1.0.
        # Round 4 (PR #89 review, Defect 1): _auto_scale_factor() now
        # multiplies the clamped raw fill-ratio by self._dpi_s (DPI-relative,
        # like every fixed step), so this pure-formula check also forces
        # self._dpi_s = 1.0 to isolate the calibration constant itself from
        # whatever DPI this box happens to report.
        self.ui._dpi_s = 1.0
        self.ui._screen_w, self.ui._screen_h = app.AUTO_REF_SCREEN_W, app.AUTO_REF_SCREEN_H
        default_w = app.SIDEBAR_W + 1 + app.CONTENT_W
        default_h = app.WINDOW_MIN_H
        factor = self.ui._auto_scale_factor(default_w, default_h)
        self.assertAlmostEqual(factor, 1.0, places=9)

    def test_ui_scale_auto_is_near_parity_on_a_near_1920x1080_screen(self):
        # The wiring, not just the formula: _apply_ui_scale("auto") must
        # actually use it. self.s lands within a small tolerance of
        # self._dpi_s * 1.0, per the acceptance criterion's own wording.
        self.ui._screen_w, self.ui._screen_h = app.AUTO_REF_SCREEN_W, app.AUTO_REF_SCREEN_H
        # Round 3 (PR #89 review), second follow-up: forces
        # winfo_width()/winfo_height() directly -- the same "force the
        # attribute/method directly" technique FontSizeFloorAtWorstCaseScale
        # already uses for _dpi_s -- rather than requesting a real
        # root.geometry() and hoping it lands there. Tried three
        # progressively more careful real-resize attempts across this
        # round (waiting via pump_until, resetting minsize() first,
        # suppressing _apply_minsize()'s own side effects) and this
        # specific test still landed away from the requested default
        # geometry on macOS CI every time -- an async real-WM round trip
        # this suite has no way to bound with certainty. This test's own
        # docstring says what it's actually about: the *wiring*
        # (_apply_ui_scale("auto") must call _auto_scale_factor() with
        # the window's current size and use the result), not reproducing
        # a literal on-screen resize -- which _apply_minsize()'s own
        # bootstrap call (__init__, unconditionally run, exercised by
        # every other UITestCase-based test already) is what actually
        # requests the real default geometry in the first place.
        default_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * self.ui._dpi_s)
        default_h = int(app.WINDOW_MIN_H * self.ui._dpi_s)
        original_winfo_width = self.root.winfo_width
        original_winfo_height = self.root.winfo_height
        self.root.winfo_width = lambda: default_w
        self.root.winfo_height = lambda: default_h
        self.addCleanup(lambda: setattr(self.root, "winfo_width", original_winfo_width))
        self.addCleanup(lambda: setattr(self.root, "winfo_height", original_winfo_height))
        # No root.update() here, deliberately: _apply_ui_scale("auto")
        # computes self.s synchronously, in plain Python, from the
        # winfo_width()/winfo_height() stubs above -- nothing about that
        # needs the event loop pumped. Pumping it here risks processing a
        # real, still-in-flight <Configure> this fixture's own
        # construction left queued (this round's own recurring theme: a
        # real window manager's own confirmation can arrive later than
        # any single synchronization point this suite controls), which
        # would fire _on_root_resize() and overwrite self.s with a value
        # computed from the *real* window's own current size, not the
        # stubbed one this test is actually about.
        self.ui._apply_ui_scale("auto")
        self.assertAlmostEqual(self.ui.s, self.ui._dpi_s,
                               delta=max(self.ui._dpi_s * 0.02, 0.01))

        # Round 4 (PR #89 review, Defect 1), folded into this test rather
        # than a standalone method -- see docs/implementation.md's own
        # "Round 3, follow-up push" precedent for why this suite's own
        # UITestCase count is deliberately not grown further (each instance
        # opens its own never-released pynput.mouse.Controller() Xlib
        # connection, and ubuntu-latest's default Xvfb build's own
        # max-clients budget is already marginal). Every fixed step's
        # self.s is self._dpi_s * UI_SCALE_FACTORS[value] -- DPI-*relative*.
        # Auto's own clamp must land in that same DPI-relative range, not
        # the raw [AUTO_SCALE_MIN, AUTO_SCALE_MAX] literal. Re-forces
        # self.ui._dpi_s to macOS CI's own observed value (~0.75, an
        # ordinary non-Retina headless-VM number, well under
        # AUTO_SCALE_MIN=0.9) -- the same "force the attribute directly"
        # technique FontSizeFloorAtWorstCaseScale already uses for _dpi_s --
        # and re-derives default_w/h and re-applies the winfo_width/height
        # stubs for the new _dpi_s (the addCleanup calls above already
        # restore the originals once, so re-stubbing here just overwrites
        # them again with the same lambda pattern for this second phase).
        # Before the fix, self.ui.s pins at the raw 0.9 floor here --
        # *larger* than even the fixed "100%" step would give on this same
        # hardware (_dpi_s * 1.0 ~= 0.75), unreachable-below no matter the
        # window/screen ratio. This is the exact coverage gap round 1's own
        # test-review (Finding 1) flagged and that let the bug ship three
        # rounds in a row (docs/test-review.md, Defect 1).
        self.ui._dpi_s = 0.75
        low_dpi_default_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * self.ui._dpi_s)
        low_dpi_default_h = int(app.WINDOW_MIN_H * self.ui._dpi_s)
        self.root.winfo_width = lambda: low_dpi_default_w
        self.root.winfo_height = lambda: low_dpi_default_h
        self.ui._apply_ui_scale("auto")
        self.assertNotAlmostEqual(self.ui.s, app.AUTO_SCALE_MIN, places=2,
                                  msg="Auto must not pin self.s at the raw, "
                                      "DPI-absolute clamp floor on a low-DPI display")
        self.assertAlmostEqual(self.ui.s, self.ui._dpi_s,
                               delta=max(self.ui._dpi_s * 0.02, 0.01))

    def _stub_minsize_without_growth_side_effect(self):
        """Round 3 (PR #89 review): monkeypatch-and-restore (this repo's
        own established style for a seam like this -- see
        SaveFailureNotice._break_saves()/_fix_saves() -- no unittest.mock).

        Confirmed directly, not assumed: a bare root.minsize(500, 500) on
        a fresh 300x300 Tk() window grows the *real* window to 500x500 on
        its own -- no root.geometry() call involved at all. _apply_minsize()
        calls root.minsize() unconditionally, every time self.s changes,
        so this side effect alone (independent of its own explicit
        grow_only geometry() call) is enough to trigger a further real
        <Configure>, which Auto mode feeds straight back into
        _auto_scale_factor(), which can then call _apply_minsize() again --
        a cascade with no natural end on a real window manager whose own
        confirmation timing this suite can't control (traced one such
        cascade directly: requested (613, 729), landed at (672, 806) after
        two further self-triggered rounds).

        Tracked here in a plain Python dict instead, so a later
        root.minsize() *query* -- which every caller of this helper still
        depends on -- returns whatever was last "set", without the real Tk
        command's growth side effect ever firing."""
        original_minsize = self.root.minsize
        tracked_minsize = original_minsize()

        def minsize_stub(width=None, height=None):
            nonlocal tracked_minsize
            if width is None:
                return tracked_minsize
            tracked_minsize = (width, height)
            return None

        self.root.minsize = minsize_stub
        self.addCleanup(lambda: setattr(self.root, "minsize", original_minsize))

    def _suppress_apply_minsize_side_effects(self):
        """Round 3 (PR #89 review), second follow-up: for a test that
        needs its *own* single, deliberate root.geometry() call to be a
        real resize (unlike test_s_strictly_increases_with_increasing_
        window_size/test_minsize_tracks_the_live_scale_during_a_
        continuous_shrink above, which drive self.s entirely through
        synthetic events and need no real resize at all),
        _stub_minsize_without_growth_side_effect() alone isn't enough:
        _apply_minsize()'s own explicit grow_only root.geometry() call
        (separate from root.minsize()'s own growth side effect) is a
        second, independent source of the exact same self-triggered
        cascade, and it goes through the very same self.root.geometry
        this test's own call does -- there's no way to stub just the
        *other* caller's use of it.

        _apply_minsize() is only ever called from _on_root_resize() (via
        this fixture's own auto-mode resize handling) and __init__()/
        _apply_ui_scale() (neither reachable once a test is already
        running) -- self._rail_collapsed and the settled rebuild this
        test actually cares about don't depend on it at all (both come
        from _on_root_resize()'s own self.s/collapsed-flag bookkeeping,
        and _rebuild_ui()'s own use of self.s directly). No-opping it here
        removes both of its side effects at once, for the rest of this
        test only, while leaving this test's own explicit
        root.geometry() call -- the real premise it exercises -- alone."""
        original_apply_minsize = self.ui._apply_minsize
        self.ui._apply_minsize = lambda grow_only=False: None
        self.addCleanup(lambda: setattr(self.ui, "_apply_minsize", original_apply_minsize))

    def _suppress_self_triggered_real_growth(self):
        """Round 3 (PR #89 review): _on_root_resize()'s own
        _apply_minsize(grow_only=True) call -- triggered by every
        synthetic <Configure> below -- finds the *real* window still at
        whatever small size this fixture's construction left it at, below
        the new minsize floor the synthetic event's self.s implies, and
        issues its OWN real root.geometry() growth call (in addition to
        root.minsize()'s own growth side effect, see
        _stub_minsize_without_growth_side_effect() above). Either one's
        resulting real Configure (carrying the *real*, small window's
        dimensions, not the synthetic event's fake ones) recomputes self.s
        a second time against the forced screen, silently overwriting the
        intended value with whatever the tiny real geometry works out to
        (observed: pinned at AUTO_SCALE_MIN for every factor from 1.1 up,
        once minsize's own floor first exceeded the real window's current
        size).

        Both stubbed here (geometry() as a flat no-op, minsize() via the
        shared helper above), so every real resize this test never asked
        for is impossible outright, regardless of what the real screen can
        or can't grant, rather than trying to out-race it (an earlier
        version of this fix grew the real window once, up front, to a size
        comfortably past every tested factor's own floor -- correct in
        principle, but a real macOS CI runner's own screen turned out not
        to be tall enough for it, reproducing the identical symptom
        anyway)."""
        original_geometry = self.root.geometry
        self.root.geometry = lambda *a, **kw: None
        self.addCleanup(lambda: setattr(self.root, "geometry", original_geometry))
        self._stub_minsize_without_growth_side_effect()

    def test_s_strictly_increases_with_increasing_window_size(self):
        # Forced to a screen much larger than the app's own fixed-pixel
        # minsize floor (517x620 unscaled), same "force the attribute
        # directly" technique FontSizeFloorAtWorstCaseScale uses for
        # _dpi_s. Round 3 (PR #89 review): synthetic event_generate(),
        # not a real root.geometry() call, drives the tested factors -- a
        # real geometry() request sized for a *forced* 3840x2160 reference
        # screen routinely exceeds a real CI runner's own actual
        # physical/virtual screen, which a real window manager silently
        # clamps to fit; self.ui.s then tracks whatever *smaller* size the
        # WM actually granted, landing at the clamp floor for every
        # factor, not the intended one. _on_root_resize() only ever reads
        # event.width/event.height, so a synthetic <Configure> (as the
        # debounce/rail tests below already use successfully) drives the
        # exact same code path without requesting any such real resize.
        self.ui._screen_w, self.ui._screen_h = 3840, 2160
        self._suppress_self_triggered_real_growth()
        prev_s = None
        # Round 4 (PR #89 review, Defect 1): _wh_for_factor()'s own
        # "raw factor" input must land inside [self._dpi_s * MIN,
        # self._dpi_s * MAX] post-fix, not the raw [MIN, MAX] literal
        # range -- each base factor here is scaled by self.ui._dpi_s so it
        # stays proportionally within (dpi_s*0.9, dpi_s*1.3) regardless of
        # what _dpi_s this box/CI runner reports. On a real low-DPI screen
        # (macOS CI's own observed ~0.75), several of these base factors
        # used to all clamp to the same DPI-*absolute* ceiling, breaking
        # strict monotonicity for a reason unrelated to the mechanism under
        # test.
        for factor in (0.92, 1.0, 1.1, 1.2, 1.28):
            with self.subTest(factor=factor):
                w, h = self._wh_for_factor(self.ui._dpi_s * factor)
                self.root.event_generate("<Configure>", width=w, height=h)
                self.root.update()
                # self.ui.s is self._dpi_s * clamped_factor -- DPI-relative,
                # like every fixed step -- so the bounds are
                # self._dpi_s * [MIN, MAX], not the raw literals.
                self.assertGreaterEqual(self.ui.s, self.ui._dpi_s * app.AUTO_SCALE_MIN)
                self.assertLessEqual(self.ui.s, self.ui._dpi_s * app.AUTO_SCALE_MAX)
                if prev_s is not None:
                    self.assertGreater(self.ui.s, prev_s)
                prev_s = self.ui.s

    def test_minsize_tracks_the_live_scale_during_a_continuous_shrink(self):
        # Same forced-screen/synthetic-event reasoning as
        # test_s_strictly_increases_with_increasing_window_size above --
        # root.minsize() is a local, synchronous Tk state read (a WM-level
        # *hint*, not a request needing WM confirmation), so it reflects
        # what _apply_minsize() just set regardless of whether any real
        # window ever actually reaches that size.
        self.ui._screen_w, self.ui._screen_h = 3840, 2160
        self._suppress_self_triggered_real_growth()
        # Grow (via a synthetic event, no real geometry() call possible
        # while _suppress_self_triggered_real_growth() is in effect) so
        # there's real room to shrink through in one continuous sequence
        # (docs/spec.md's own named edge case: a naive "only touch self.s
        # at settle" design would have let a single shrink drag overshoot
        # the true live floor).
        # Round 4 (PR #89 review, Defect 1): every raw factor below is
        # scaled by self.ui._dpi_s, same reasoning as
        # test_s_strictly_increases_with_increasing_window_size above --
        # keeps each one proportionally within the post-fix, DPI-relative
        # clamp range regardless of what _dpi_s this box/CI runner reports.
        start_w, start_h = self._wh_for_factor(self.ui._dpi_s * 1.28)
        self.root.event_generate("<Configure>", width=start_w, height=start_h)
        self.root.update()
        prev_minw = None
        for factor in (1.2, 1.1, 1.0, 0.95):
            with self.subTest(factor=factor):
                w, h = self._wh_for_factor(self.ui._dpi_s * factor)
                self.root.event_generate("<Configure>", width=w, height=h)
                self.root.update()
                expected_minw = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * self.ui.s)
                # Live, not stale: minsize() reflects THIS call's own s,
                # not whatever s was in effect before this geometry() call.
                self.assertEqual(self.root.minsize()[0], expected_minw)
                if prev_minw is not None:
                    self.assertLess(expected_minw, prev_minw)
                prev_minw = expected_minw

    def test_a_burst_of_configure_events_settles_to_one_rebuild(self):
        calls = []
        original = self.ui._rebuild_ui
        def spy():
            calls.append(1)
            original()
        self.ui._rebuild_ui = spy
        for factor in (1.0, 1.05, 1.1, 1.15, 1.2):
            w, h = self._wh_for_factor(factor)
            self.root.event_generate("<Configure>", width=w, height=h)
        self.root.update()
        self.assertEqual(len(calls), 0,
                         "rebuilt before the settle window elapsed")
        self.pump(app.AUTO_SETTLE_MS / 1000 + 0.2)
        self.assertEqual(len(calls), 1)

    def test_the_settle_timer_resets_on_each_new_event_not_just_the_first(self):
        # Distinguishes real debounce from mere after_idle-style coalescing
        # (docs/spec.md "The debounce decision"): a second event arriving
        # inside the first event's own settle window must push the
        # deadline out again, not just get folded into the first one.
        calls = []
        original = self.ui._rebuild_ui
        def spy():
            calls.append(1)
            original()
        self.ui._rebuild_ui = spy
        w1, h1 = self._wh_for_factor(1.05)
        self.root.event_generate("<Configure>", width=w1, height=h1)
        self.root.update()
        self.pump(app.AUTO_SETTLE_MS / 1000 * 0.6)   # well within the window
        self.assertEqual(len(calls), 0)
        w2, h2 = self._wh_for_factor(1.15)
        self.root.event_generate("<Configure>", width=w2, height=h2)
        self.root.update()
        self.pump(app.AUTO_SETTLE_MS / 1000 * 0.6)   # would have fired for
            # the FIRST event's own window by now if the timer hadn't reset
        self.assertEqual(len(calls), 0)
        self.pump(app.AUTO_SETTLE_MS / 1000 * 0.6)   # now past the second
                                                       # event's own window
        self.assertEqual(len(calls), 1)

    def test_shrinking_past_the_threshold_collapses_the_rail_under_auto(self):
        # Mirrors WindowResize.test_shrinking_past_the_threshold_collapses_
        # the_rail, but self.s here is Auto's own live, continuously-
        # recomputed value rather than a fixed one -- and the settled
        # rebuild (not just the flag) must reflect it, since Auto defers
        # the actual widget-tree rebuild to AUTO_SETTLE_MS's timer instead
        # of fixed-step mode's immediate after_idle.
        #
        # Round 3 (PR #89 review): this helper's own target_h (fixed
        # "700", not derived from the app's own aspect ratio, same as
        # WindowResize's pre-Auto equivalent) can feed back into Auto's
        # own live self.s at a fill fraction that pulls it toward
        # AUTO_SCALE_MAX -- _apply_minsize()'s own side effects (see
        # _suppress_apply_minsize_side_effects()'s own docstring) can then
        # keep moving the real window past what this test requested, in a
        # cascade with no natural end on a real window manager. Suppressed
        # so this test's own single, deliberate geometry() call below is
        # the last real resize that happens; the flag (and the final
        # self.s-derived assertion, which reads self.ui.s fresh rather
        # than the s captured here) is what the test actually cares about
        # either way. root.minsize() reset to (1, 1) first, before
        # suppressing _apply_minsize() -- once suppressed, nothing ever
        # relaxes whatever floor this fixture's own construction-time
        # self-correction may have already left in place, which could
        # otherwise silently clamp this test's own geometry() request
        # below back up to that stale floor.
        self.root.minsize(1, 1)
        self._suppress_apply_minsize_side_effects()
        # Round 4 (PR #89 review, Defect 2): force a known, un-collapsed
        # baseline before computing the shrink target, and sync the real
        # widget tree to it, rather than trusting whatever self.ui.s/
        # self.ui._rail_collapsed construction already left in place.
        # Root-caused via a throwaway AFK_DEBUG_AUTO_RESIZE instrumented
        # push against real Windows CI (removed once the values below were
        # captured): on a real WM whose own screen makes construction's
        # own bootstrap self-correction land self.s at (or near) the clamp
        # ceiling, the rail is already *logically* collapsed
        # (self._rail_collapsed already True) before this test's own
        # resize -- correctly never rebuilt, per round 2's own "widget
        # tree lags self.s" tradeoff for a bootstrap echo. This test's own
        # target_w/h, computed relative to that already-saturated s
        # (compounded by target_h's own round-3-documented aspect-
        # inconsistency, which independently pulls self.s back toward the
        # same ceiling), can land at the exact same self.s/collapsed state
        # again -- s_changed and collapsed_changed both False, so no
        # settle/rebuild ever gets requested, and self.ui.side is left
        # showing construction's own stale, expanded width forever.
        # Captured directly from Windows CI: both events this test's own
        # resize produced showed self.s already pinned at the ceiling and
        # rail_collapsed already True beforehand.
        self.ui.s = self.ui._dpi_s * 1.0
        self.ui._rail_collapsed = False
        self.ui._rebuild_ui()
        s = self.ui.s
        threshold = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        floor = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s)
        target_w = (threshold + floor) // 2
        target_h = int(700 * s)
        self.root.geometry(f"{target_w}x{target_h}")
        self.pump_until(lambda: self.ui._rail_collapsed)
        self.assertTrue(self.ui._rail_collapsed)
        # A condition-based wait for the settled rebuild, not a fixed
        # AUTO_SETTLE_MS + margin sleep: a cascade of self-triggered
        # minsize corrections (the same one that can move the window past
        # the requested size above) can re-arm the settle timer more than
        # once before it actually fires, on a real window manager whose
        # own confirmation timing this suite can't control.
        self.pump_until(lambda: self.ui.side.winfo_width()
                                 == int(app.SIDEBAR_RAIL_W * self.ui.s), timeout=5.0)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_RAIL_W * self.ui.s))

    def test_growing_back_past_the_threshold_re_expands_the_rail_under_auto(self):
        # Round 3 (PR #89 review): see test_shrinking_past_the_threshold_
        # collapses_the_rail_under_auto's own comment for why this waits
        # on the flag/final-state conditions themselves rather than the
        # literal requested geometry or a fixed sleep, why
        # _apply_minsize()'s own side effects are suppressed, and why
        # root.minsize() is reset first.
        self.root.minsize(1, 1)
        self._suppress_apply_minsize_side_effects()
        # Round 4 (PR #89 review, Defect 2): same known-baseline reset as
        # this test's shrinking sibling -- without it, this test's own
        # initial shrink-to-collapse phase is exposed to the identical
        # pre-saturated-construction risk (a real WM's own screen already
        # landing self.s at the clamp ceiling and the rail already
        # logically collapsed before this test's first resize), even
        # though it wasn't the one observed failing on Windows CI this
        # round -- this test's own later "worst_case_threshold"-based grow
        # margin already happened to be robust to a saturated starting s,
        # which is likely why only its shrinking sibling actually failed.
        self.ui.s = self.ui._dpi_s * 1.0
        self.ui._rail_collapsed = False
        self.ui._rebuild_ui()
        s = self.ui.s
        threshold = int(app.RAIL_COLLAPSE_THRESHOLD * s)
        floor = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s)
        target_w = (threshold + floor) // 2
        target_h = int(700 * s)
        self.root.geometry(f"{target_w}x{target_h}")
        self.pump_until(lambda: self.ui._rail_collapsed)
        self.assertTrue(self.ui._rail_collapsed)
        # Round 4 (PR #89 review, Defect 1): a fixed "+200" margin off the
        # *stale* threshold above isn't enough to guarantee escaping
        # collapse -- growing the window also grows self.s (this test's
        # own target_h isn't aspect-consistent, same round-3-documented
        # quirk as its shrinking sibling), which grows the threshold too.
        # Margin off the worst case self.s can ever reach
        # (self._dpi_s * AUTO_SCALE_MAX, the clamp ceiling) instead, so
        # this clears the threshold regardless of where s lands mid-grow.
        worst_case_threshold = int(app.RAIL_COLLAPSE_THRESHOLD * self.ui._dpi_s * app.AUTO_SCALE_MAX)
        grown_w = worst_case_threshold + 50
        self.root.geometry(f"{grown_w}x{target_h}")
        self.pump_until(lambda: not self.ui._rail_collapsed)
        self.assertFalse(self.ui._rail_collapsed)
        self.pump_until(lambda: self.ui.side.winfo_width()
                                 == int(app.SIDEBAR_W * self.ui.s), timeout=5.0)
        self.assertEqual(self.ui.side.winfo_width(), int(app.SIDEBAR_W * self.ui.s))

    def test_settings_shows_auto_selected_by_default(self):
        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self.ui.ui_scale_var.get(), "auto")
        seg = self._appearance_segment(self.ui.ui_scale_var)
        self.assertEqual(len(seg.options), 5)
        self.assertEqual(seg.options[0][0], "auto")

    def test_on_close_cancels_a_pending_settle_job(self):
        # Same guarantee _rebuild_after_id/_pane_fill_after_id already have
        # (AfterJobsAreNotDuplicated-style) -- a live drag's settle timer
        # must not fire into a destroyed interpreter.
        w, h = self._wh_for_factor(1.1)
        self.root.event_generate("<Configure>", width=w, height=h)
        self.root.update()
        self.assertIsNotNone(self.ui._auto_settle_after_id)
        self.ui.on_close()   # must not raise
        self.assertIsNone(self.ui._auto_settle_after_id)

    # ---------- round 2 (PR #89 review): the macOS/Windows CI regression ----------

    def test_the_bootstrap_echo_configure_does_not_arm_a_live_settle_timer(self):
        # Gap 1: a real window manager's own post-map <Configure> reports
        # exactly self._auto_bootstrap_wh back unchanged -- nothing has
        # actually resized, it's the WM merely confirming the map. On a
        # real screen far from AUTO_REF_SCREEN_W/H (any CI runner's own
        # virtual display), that alone used to still arm a live
        # AUTO_SETTLE_MS timer purely from the screen-size term -- and
        # since UI_SCALE_DEFAULT is now "auto", every fresh UITestCase
        # fixture (not just this class's own tests) boots in Auto mode and
        # hits this path on a real WM. That timer firing later, mid-test
        # (or after a *different* test's own teardown, since 150ms
        # comfortably outlives most test bodies) tore down/rebuilt the
        # widget tree out from under a test that never asked for a
        # rebuild -- PR #89's macOS/Windows CI regression. Forced the same
        # "force the attribute directly" way FontSizeFloorAtWorstCaseScale
        # forces self.ui._dpi_s, then reproduced with the same synthetic-
        # <Configure> technique this class already uses elsewhere.
        w, h = self.ui._auto_bootstrap_wh
        # Round 3 (PR #89 review): picks whichever clamp extreme is
        # furthest from self.ui.s's own *current* value, rather than a
        # fixed 1024x768 -- on a real screen where this fixture's own
        # construction already self-corrected self.s all the way to
        # AUTO_SCALE_MIN or AUTO_SCALE_MAX (a real, observed macOS CI
        # case), a fixed forced screen can land on the *same* clamped
        # value from both sides, tripping the no-op guard below for real,
        # not because the fix stopped working.
        if self.ui.s >= (app.AUTO_SCALE_MIN + app.AUTO_SCALE_MAX) / 2:
            self.ui._screen_w, self.ui._screen_h = 100000, 100000
        else:
            self.ui._screen_w, self.ui._screen_h = 10, 10
        self.assertNotEqual(self.ui._auto_scale_factor(w, h), self.ui.s,
                            "fixture didn't actually diverge self.s -- test is a no-op")
        self.root.event_generate("<Configure>", width=w, height=h)
        self.root.update()
        self.assertIsNone(self.ui._auto_settle_after_id,
                          "the bootstrap echo armed a live settle timer")
        # Only the settle-triggered rebuild is skipped for this one echo --
        # self.s itself still tracks live, exactly like every other event.
        self.assertAlmostEqual(self.ui.s, self.ui._auto_scale_factor(w, h))

    def test_a_genuine_resize_still_settles_even_at_the_bootstrap_pixel_size(self):
        # Round 3 (PR #89 review, folded in here rather than as new test
        # methods -- see docs/implementation.md's own "Key decisions" on
        # why this suite's UITestCase count is deliberately not grown
        # further): round 2's is_bootstrap_echo only ever compared an
        # incoming <Configure> against the ONE geometry recorded at
        # construction -- but _apply_minsize(grow_only=True) (called from
        # every qualifying Auto-mode <Configure>) can itself issue a
        # SECOND real geometry() call, when the newly recomputed minsize
        # floor exceeds the window's current real size. Sabotage-verified
        # against real production code (not just reasoned). Reset to a
        # small, known real size first (minsize(1, 1) clears whatever real
        # floor this fixture's own construction-time self-correction may
        # already have left in effect -- observed on a real, large-screen
        # macOS CI runner reaching self.s == AUTO_SCALE_MAX by
        # construction alone, leaving no room left to grow from) rather
        # than assuming the fresh fixture starts small.
        # Round 4 (PR #89 review): the reset itself, while Auto mode's own
        # live _on_root_resize()/_apply_minsize() tracking is active, is
        # itself a real self-triggered growth cascade -- a real <Configure>
        # reporting 400x400 recomputes a small self.s, whose own minsize
        # floor then exceeds 400, growing again, recomputing self.s again,
        # ... converging back at the clamp ceiling rather than ever
        # settling at 400x400 (traced directly: reproducibly lands at
        # exactly self._dpi_s * AUTO_SCALE_MAX's own minw/minh). Suppressing
        # _apply_minsize() (the same technique
        # _suppress_apply_minsize_side_effects() uses elsewhere in this
        # class) for this reset only breaks that chain -- _on_root_resize()
        # can still recompute self.s live, it just never issues a follow-on
        # geometry() call, so the real window actually lands at 400x400.
        # _request_auto_settle() is suppressed too, not just _apply_minsize():
        # _on_root_resize() arms a settle purely off self.s changing
        # (unconditional on _apply_minsize() itself doing anything), so the
        # 400x400 reset's own live self.s recompute would otherwise leave a
        # stray pending settle job behind that has nothing to do with the
        # echo mechanism this test actually exercises below.
        original_apply_minsize = self.ui._apply_minsize
        original_request_auto_settle = self.ui._request_auto_settle
        self.ui._apply_minsize = lambda grow_only=False: None
        self.ui._request_auto_settle = lambda: None
        self.root.minsize(1, 1)
        self.root.geometry("400x400")
        self.pump_until(lambda: (self.root.winfo_width(), self.root.winfo_height())
                                 == (400, 400))
        self.ui._apply_minsize = original_apply_minsize
        self.ui._request_auto_settle = original_request_auto_settle
        self.assertIsNone(self.ui._auto_settle_after_id,
                          "the 400x400 reset itself left a stray settle job pending")
        self.ui.s = app.AUTO_SCALE_MAX
        # Round 4 (PR #89 review, Defect 3): the expected grown geometry is
        # computed here, independently, from the same formula
        # _apply_minsize()'s own grow_only branch uses (afk_clicker.py's
        # own docstring/source) -- BEFORE calling it -- rather than reading
        # self.ui._auto_bootstrap_wh back *after* the call and feeding that
        # same value into the synthetic event below. The earlier version of
        # this test did exactly that: whatever _auto_bootstrap_wh currently
        # held, updated or stale, was by construction always what got
        # echoed back, so the final assertIsNone(...) could never observe a
        # tracking regression -- confirmed tautological via sabotage
        # (docs/test-review.md's Defect 3): dropping _apply_minsize()'s own
        # self._auto_bootstrap_wh update left this test green.
        minw = int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * self.ui.s)
        minh = int(app.WINDOW_MIN_H * self.ui.s)
        grown_w, grown_h = max(400, minw), max(400, minh)
        self.assertNotEqual((grown_w, grown_h), (400, 400),
                            "fixture didn't actually trigger a self-requested "
                            "growth -- test is a no-op")
        self.ui._apply_minsize(grow_only=True)
        self.assertEqual(self.ui._auto_bootstrap_wh, (grown_w, grown_h),
                         "_apply_minsize()'s own geometry() call wasn't "
                         "tracked as the new expected self-requested echo")
        # A real window manager's own later confirmation of that
        # independently-computed grown size -- not a genuine user resize --
        # must not be mistaken for one, even though the grown rectangle's
        # own aspect ratio differs from the app's (grow_only only ever
        # corrects the axis that actually falls short), so self.s itself
        # still legitimately changes when this echo is processed.
        self.root.event_generate("<Configure>", width=grown_w, height=grown_h)
        self.root.update()
        self.assertIsNone(self.ui._auto_settle_after_id,
                          "a real WM's own confirmation of a self-triggered "
                          "minsize correction armed a live settle timer")

        # The suppression above is keyed on (width, height) matching
        # self._auto_bootstrap_wh, not on "is this the first event" -- a
        # later, real resize away from it (here: shrinking back down, per
        # the original round-2 docstring's own name for this test) must
        # still settle normally, whether or not it also happens to be the
        # self-triggered growth's own most-recently-tracked value above.
        # Proves the fix didn't widen into "skip every event this
        # instance ever sees", and that a genuine resize after a self-
        # triggered growth (round 3's own new gap) still settles too.
        # Round 4 (PR #89 review, Defect 1): a fixed raw factor literal
        # (1.15) isn't guaranteed to actually change self.s post-fix -- on
        # a low-DPI real screen (self._dpi_s * AUTO_SCALE_MAX can be well
        # under 1.15), it can clamp to the exact same ceiling self.s is
        # already at from the growth step above, making this event a
        # silent no-op for s_changed. Picks whichever clamp extreme is
        # furthest from self.ui.s's own current value instead -- same
        # "diverge regardless of where construction/prior steps already
        # left self.s" technique
        # test_the_bootstrap_echo_configure_does_not_arm_a_live_settle_timer
        # already uses.
        dpi_s = self.ui._dpi_s
        low_target = dpi_s * (app.AUTO_SCALE_MIN + 0.02)
        high_target = dpi_s * (app.AUTO_SCALE_MAX - 0.02)
        target_s = (high_target if abs(self.ui.s - low_target) > abs(self.ui.s - high_target)
                    else low_target)
        w, h = self._wh_for_factor(target_s)
        self.root.event_generate("<Configure>", width=w, height=h)
        self.root.update()
        self.assertIsNotNone(self.ui._auto_settle_after_id,
                             "a genuine, non-echo resize failed to arm the settle timer")

    def test_a_late_configure_during_teardown_does_not_re_arm_the_settle_timer(self):
        # Gap 2: on_close() used to cancel a pending _auto_settle_after_id
        # only once, near the top -- but _on_root_resize stayed bound
        # through the rest of teardown, including root.destroy() itself,
        # so a late <Configure> arriving after that one cancellation could
        # re-arm a job nothing after that point ever cancels again, later
        # firing into a destroyed interpreter. Reproduced by hooking
        # _release_right -- on_close()'s own last call before
        # root.destroy() -- the same "last point before destroy" position
        # UpdateLogPrompt.test_on_close_before_the_startup_idle_job_ever_ran_cancels_it
        # already uses to inspect state right before teardown finishes.
        w, h = self._wh_for_factor(1.15)
        original_release = self.ui._release_right
        def patched_release():
            original_release()
            self.root.event_generate("<Configure>", width=w, height=h)
        self.ui._release_right = patched_release
        try:
            self.ui.on_close()   # must not raise
        finally:
            self.ui._release_right = original_release
        self.assertIsNone(self.ui._auto_settle_after_id,
                          "a late <Configure> during teardown re-armed the settle timer")


class FontSizeFloorAtWorstCaseScale(UITestCase):
    """G#23/GH#35: FontSizeFloor above proves fs() itself is correct in
    isolation; this proves a real widget built from one of its "actually
    changes" call sites (afk_clicker.py:2213, the jitter row's mutable
    hint, base 8) actually renders at the floored size rather than the 5pt
    plain int() would give. Reuses WindowMinimumHeight's own
    _dpi_s/_apply_ui_scale simulation pattern (test_ui.py:1148-1168) --
    there is no real Mac available to run this suite on, so this is the
    only local stand-in; docs/spec.md's Risk notes still call for a green
    macOS CI leg as the real verification."""

    def _hint_font_size(self):
        widget = self.ui.jitter_row.hint_label
        return tkfont.Font(font=widget.cget("font")).actual("size")

    def test_worst_case_mac_90_percent_floors_to_six(self):
        # _dpi_s is a plain instance attribute, safe to force directly --
        # never rewritten by any rebuild path (same note as
        # WindowMinimumHeight's own worst-case test).
        self.ui._dpi_s = 0.75
        self.ui._apply_ui_scale("90")
        self.root.update()
        self.assertEqual(self._hint_font_size(), 6)

    def test_mac_100_percent_baseline_is_still_six(self):
        # Proves the floor didn't accidentally shift the already-shipping
        # baseline -- same simulated DPI, the already-accepted scale step.
        self.ui._dpi_s = 0.75
        self.ui._apply_ui_scale("100")
        self.root.update()
        self.assertEqual(self._hint_font_size(), 6)


class SettingsNavigation(UITestCase):
    """The sidebar entry and the content-pane swap between the per-game form
    and the Settings page."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_sidebar_no_longer_holds_the_update_widgets(self):
        # Feature 3b: "Check for updates"/the version label moved into the
        # Settings page's own Updates section -- the sidebar footer is now
        # games -> Add current game -> divider -> Settings only.
        self.assertIsInstance(self.ui.settings_item, app.SettingsItem)
        buttons = [w for w in self.ui.side.winfo_children() if isinstance(w, app.Button)]
        self.assertEqual(len(buttons), 1,
                         "only 'Add current game' should remain a sidebar Button")
        labels = [w for w in self.ui.side.winfo_children() if isinstance(w, tk.Label)]
        self.assertEqual(labels, [self.ui.count_label],
                         "no version label should remain in the sidebar")
        self.assertFalse(hasattr(self.ui, "update_button"),
                         "update_button should not be built until Settings is opened")
        self.assertFalse(hasattr(self.ui, "version_label"),
                         "version_label should not be built until Settings is opened")
        self.assertFalse(self.ui.settings_item.has_update,
                         "a fresh app with no update activity should show no offer")

    def test_games_count_excludes_the_settings_entry(self):
        expected = f"GAMES   {len(self.ui.profiles)}"
        self.assertEqual(self.ui.count_label.cget("text"), expected)
        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self.ui.count_label.cget("text"), expected)
        self.assertNotIn("settings", self.ui.items)

    def test_opening_settings_deselects_every_game_and_selects_settings(self):
        self.ui._select("minecraft")
        self.ui._show_settings()
        self.root.update()
        self.assertTrue(self.ui._settings_open)
        self.assertTrue(self.ui.settings_item.selected)
        for item in self.ui.items.values():
            self.assertFalse(item.selected)
        self.assertEqual(self.ui.current, "minecraft", "leaving is unchanged while Settings is open")

    def test_clicking_a_game_closes_settings(self):
        self.ui._show_settings()
        self.root.update()
        self.ui._select("minecraft")
        self.root.update()
        self.assertFalse(self.ui._settings_open)
        self.assertFalse(self.ui.settings_item.selected)
        self.assertEqual(self.ui.current, "minecraft")

    def test_hotkey_card_is_never_part_of_the_settings_page(self):
        old_hotkey_label = self.ui.hotkey_label
        self.ui._show_settings()
        self.root.update()
        self.assertFalse(old_hotkey_label.winfo_exists(),
                         "hotkey card should have been torn down, not reused")

    def test_a_selected_game_survives_a_rebuild_from_the_game_view(self):
        self.ui._select("minecraft")
        self.root.update()
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertEqual(self.ui.current, "minecraft")
        self.assertFalse(self.ui._settings_open)
        self.assertEqual(self.ui.click_ms.var.get(), "650")

    def test_settings_page_stays_open_across_a_theme_switch_with_the_new_segment_selected(self):
        self.ui._show_settings()
        self.root.update()
        seg = self._appearance_segment()
        seg.event_generate("<Button-1>", x=seg.w - 2, y=int(seg.h / 2))  # "Dark", 3rd of 3
        self.root.update()
        self.assertTrue(self.ui._settings_open)
        self.assertTrue(self.ui.settings_item.selected)
        self.assertEqual(self.ui.appearance_var.get(), "dark")

    def test_hint_text_reflects_the_cached_os_theme(self):
        self.ui._os_theme = "light"

        def find_hint(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label) and \
                        child.cget("text").startswith("System is currently"):
                    return child
                found = find_hint(child)
                if found is not None:
                    return found
            return None

        self.ui._show_settings()
        self.root.update()
        hint = find_hint(self.ui.content)
        self.assertIsNotNone(hint, "no OS-theme hint label found")
        self.assertEqual(hint.cget("text"), "System is currently light")


class SettingsUpdates(UITestCase):
    """Feature 3b: the Updates section on the Settings page, and the
    rebuild-/visibility-safety mechanism (self._update_text, the guarded
    _set_update_state()/_offer_update(), the sidebar's has_update signal)
    that relocating update_button/version_label out of the sidebar makes
    necessary. See docs/history/ac-17-f3b-spec.md §3/§4."""

    # G#38/GH#67 round 3 (PR #89 review): same reasoning as NumBoxFocus's
    # own INITIAL_UI_SCALE.
    INITIAL_UI_SCALE = "100"

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def _button_text(self):
        return self.ui.update_button.itemcget(self.ui.update_button.label, "text")

    def _button_fill(self):
        return self.ui.update_button.itemcget(self.ui.update_button.shape, "fill")

    def test_settings_page_builds_the_updates_section(self):
        self.ui._show_settings()
        self.root.update()
        self.assertIsInstance(self.ui.update_button, app.Button)
        self.assertIsInstance(self.ui.version_label, tk.Label)
        self.assertEqual(self._button_text(), "Check for updates")
        self.assertTrue(self.ui.update_button._enabled)
        self.assertEqual(self.ui.version_label.cget("text"), f"v{app.__version__}")

    def test_every_update_state_renders_on_the_settings_page(self):
        # A non-regression sweep (docs/history/ac-17-f3b-spec.md AC3): every text/enabled/
        # colour combination check_update/_check_worker/install_update/
        # _install_worker can produce today, driven through the same
        # _set_update_state() entry point those methods already call --
        # see afk_clicker.py's own call sites for where each literal comes
        # from. Colour is only ever passed alongside an error/offer state;
        # states that pass no colour leave version_label exactly as it was
        # (unchanged code, docs/history/ac-17-f3b-spec.md §2/§3) -- asserted explicitly below,
        # not assumed.
        self.ui._show_settings()
        self.root.update()
        idle_text = self.ui.version_label.cget("text")
        idle_fg = self.ui.version_label.cget("fg")

        # (state label, enabled, primary) -- no colour, version_label
        # untouched by any of these.
        uncoloured = [
            ("Checking…", False),
            ("No releases published yet", True),
            (f"Up to date · {app.__version__}", True),
        ]
        for text, enabled in uncoloured:
            with self.subTest(state=text):
                self.ui._set_update_state(text, enabled)
                self.assertEqual(self._button_text(), text)
                self.assertEqual(self.ui.update_button._enabled, enabled)
                self.assertEqual(self._button_fill(), app.CARD)
                self.assertEqual(self.ui.version_label.cget("text"), idle_text)
                self.assertEqual(self.ui.version_label.cget("fg"), idle_fg)

        checksum_not_listed = (
            "checksum: not in SHA256SUMS: Clickwork-linux-x86_64.tar.gz"[:40])
        checksum_mismatch = (
            "checksum mismatch: expected abcdef123456…, got 987654fedcba…"[:40])
        coloured = [
            "GitHub unreachable",
            "v9.9.9: no build for this OS",
            checksum_not_listed,
            checksum_mismatch,
            "Install folder is read-only",
            "Update failed: connection reset"[:40],
            "Run `git pull` — not a build",
        ]
        self.assertIn("checksum", checksum_not_listed.lower())
        self.assertIn("checksum", checksum_mismatch.lower())
        for text in coloured:
            with self.subTest(state=text):
                self.ui._set_update_state(text, True, app.BAD)
                self.assertLessEqual(len(text), 40)
                self.assertEqual(self._button_text(), text)
                self.assertTrue(self.ui.update_button._enabled)
                self.assertEqual(self._button_fill(), app.CARD)
                self.assertEqual(self.ui.version_label.cget("text"), text)
                self.assertEqual(self.ui.version_label.cget("fg"), app.BAD)

        # Offer found and downloading, in sequence: _offer_update() sets
        # primary styling + the arrow text; a later no-colour _set_update_
        # state() call (the progress ticks) must overwrite only the text/
        # enabled state and leave that styling underneath.
        self.ui._offer_update("v9.9.9")
        self.assertEqual(self._button_text(), "Install v9.9.9")
        self.assertTrue(self.ui.update_button._enabled)
        self.assertEqual(self._button_fill(), app.ACCENT)
        self.assertEqual(self.ui.version_label.cget("text"), f"v{app.__version__} → v9.9.9")
        self.assertEqual(self.ui.version_label.cget("fg"), app.ACCENT)

        for pct in (0, 45, 100):
            with self.subTest(state=f"Downloading… {pct}%"):
                self.ui._set_update_state(f"Downloading… {pct}%", False)
                self.assertEqual(self._button_text(), f"Downloading… {pct}%")
                self.assertFalse(self.ui.update_button._enabled)
                # version_label keeps the offer's arrow text/colour -- no
                # colour is passed for a progress tick.
                self.assertEqual(self.ui.version_label.cget("text"),
                                 f"v{app.__version__} → v9.9.9")
                self.assertEqual(self.ui.version_label.cget("fg"), app.ACCENT)

        self.ui._set_update_state("Restarting…", False)
        self.assertEqual(self._button_text(), "Restarting…")
        self.assertFalse(self.ui.update_button._enabled)
        self.assertEqual(self.ui.version_label.cget("text"), f"v{app.__version__} → v9.9.9")
        self.assertEqual(self.ui.version_label.cget("fg"), app.ACCENT)

    def test_an_offer_marks_the_settings_row_while_a_game_page_is_open(self):
        # Settings is never opened this session -- proves the off-screen
        # signal path (§3's AttributeError/TclError hazard) is safe.
        self.assertFalse(self.ui._settings_open)
        self.assertFalse(hasattr(self.ui, "update_button"))
        self.ui._pending = ("v9.9.9", {"name": "x"}, {})
        self.ui._offer_update("v9.9.9")
        self.assertTrue(self.ui.settings_item.has_update)

        # Survives a rebuild triggered while Settings is still closed.
        self.ui._apply_appearance("light")
        self.root.update()
        self.assertTrue(self.ui.settings_item.has_update)

        # Survives switching games too -- has_update is rebuilt fresh from
        # self._pending on every _build_ui(), not cleared by _select().
        self.ui._select("minecraft")
        self.root.update()
        self.assertTrue(self.ui.settings_item.has_update)

        # Opening Settings now replays the offer without a second check.
        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self._button_text(), "Install v9.9.9")
        self.assertEqual(self.ui.version_label.cget("text"), f"v{app.__version__} → v9.9.9")
        self.assertEqual(self.ui.version_label.cget("fg"), app.ACCENT)

    def test_downloading_state_survives_a_rebuild_with_settings_open(self):
        self.ui._show_settings()
        self.root.update()
        self.ui._pending = ("v9.9.9", {"name": "x"}, {})
        self.ui._offer_update("v9.9.9")
        # Simulate a progress tick landing from a background thread, the way
        # download_and_stage()'s on_progress callback really calls it --
        # queued via self._ui(), then drained on the main thread, exactly
        # the _drain_ui() contract this spec must not change.
        worker = threading.Thread(
            target=lambda: self.ui._ui(self.ui._set_update_state, "Downloading… 42%", False),
            daemon=True)
        worker.start()
        worker.join(timeout=2)
        self.ui._drain_ui()
        self.assertEqual(self._button_text(), "Downloading… 42%")

        old_button = self.ui.update_button
        self.ui._apply_appearance("light")
        self.root.update()

        self.assertIsNot(self.ui.update_button, old_button,
                         "the rebuild should have replaced the widget, not reused it")
        self.assertEqual(self._button_text(), "Downloading… 42%")
        self.assertFalse(self.ui.update_button._enabled)
        self.assertEqual(self.ui._pending, ("v9.9.9", {"name": "x"}, {}))
        self.assertEqual(self.ui._update_text, ("Downloading… 42%", False, None))

    def test_set_update_state_with_settings_closed_does_not_raise(self):
        self.assertFalse(self.ui._settings_open)
        self.assertFalse(hasattr(self.ui, "update_button"))
        self.ui._set_update_state("Checking…", enabled=False)   # must not raise
        self.assertEqual(self.ui._update_text, ("Checking…", False, None))

        self.ui._show_settings()
        self.root.update()
        self.assertEqual(self._button_text(), "Checking…")
        self.assertFalse(self.ui.update_button._enabled)

    def test_a_fresh_check_supersedes_a_superseded_offer(self):
        # PR #31 review, Round 2 BLOCKER: offer -> a checksum-failure install
        # (retry stays wired to install_update, intended -- unchanged) -> a
        # later check_update() that resolves "up to date". Without check_
        # update() clearing self._pending/the sidebar mark/the button's
        # command first, the stale offer survives the very check that
        # resolves it: the sidebar keeps reading "Settings · Update" right
        # next to a button that reads "Up to date" but is still wired to
        # install_update() against the superseded release.
        self.ui._show_settings()
        self.root.update()
        release = {"assets": [
            {"name": "SHA256SUMS", "browser_download_url": "x"},
            {"name": "Clickwork-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
        self.ui._pending = ("v9.9.9", release["assets"][1], release)
        self.ui._offer_update("v9.9.9")
        self.assertEqual(self.ui.update_button.command, self.ui.install_update)

        def fake_fetch(asset, timeout=30):
            return {}

        def fake_stage(asset, checksums, on_progress=None):
            raise app.ChecksumError(
                f"checksum: not in {app.CHECKSUM_ASSET}: {asset['name']}")

        original_fetch, original_stage = app.fetch_checksums, app.download_and_stage
        app.fetch_checksums, app.download_and_stage = fake_fetch, fake_stage
        try:
            self.ui._install_worker()
            self.ui._drain_ui()
        finally:
            app.fetch_checksums, app.download_and_stage = original_fetch, original_stage

        # Retry stays possible after an install-time failure -- unchanged,
        # intended (docs/implementation.md "Key decisions" / the PR review's
        # own case 3).
        self.assertIsNotNone(self.ui._pending)
        self.assertTrue(self.ui.settings_item.has_update)
        self.assertEqual(self.ui.update_button.command, self.ui.install_update)

        original_latest = app.latest_release
        app.latest_release = lambda timeout=10: {"tag_name": "v0.1.0", "assets": []}
        try:
            self.ui.check_update()
            self.pump_until(lambda: self._button_text() != "Checking…")
        finally:
            app.latest_release = original_latest

        self.assertEqual(self._button_text(), f"Up to date · {app.__version__}")
        self.assertIsNone(self.ui._pending,
                          "a fresh check must clear the superseded offer")
        self.assertFalse(self.ui.settings_item.has_update,
                         "the Settings row must not still claim an update is waiting")
        self.assertEqual(
            self.ui.settings_item.itemcget(self.ui.settings_item.text, "text"), "Settings")
        self.assertEqual(self.ui.update_button.command, self.ui.check_update,
                         "the button must point back at a fresh check, not the stale install")

    def test_offer_lands_through_a_real_worker_thread_with_settings_closed(self):
        # PR #31 review, Round 8 CONCERN: _offer_update was never driven
        # through the real self._ui()/_drain_ui() marshaling from an actual
        # background thread -- production only ever reaches it that way
        # (_check_worker's own self._ui(self._offer_update, tag) call).
        self.assertFalse(self.ui._settings_open)
        self.assertFalse(hasattr(self.ui, "update_button"))
        release = {"tag_name": "v9.9.9",
                  "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}
        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = lambda timeout=10: release
        app.is_newer = lambda tag, current=app.__version__: True
        app.pick_asset = lambda rel: rel["assets"][0]
        try:
            worker = threading.Thread(
                target=self.ui._check_worker, args=(self.ui._check_seq,), daemon=True)
            worker.start()
            worker.join(timeout=2)
            self.pump_until(lambda: self.ui.settings_item.has_update)
        finally:
            app.latest_release, app.is_newer, app.pick_asset = \
                original_latest, original_is_newer, original_pick

        self.assertTrue(self.ui.settings_item.has_update)
        self.assertIsNotNone(self.ui._pending)
        self.assertEqual(self.ui._pending[0], "v9.9.9")

    def test_offer_lands_through_a_real_worker_thread_with_settings_open(self):
        self.ui._show_settings()
        self.root.update()
        release = {"tag_name": "v9.9.9",
                  "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}
        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = lambda timeout=10: release
        app.is_newer = lambda tag, current=app.__version__: True
        app.pick_asset = lambda rel: rel["assets"][0]
        try:
            worker = threading.Thread(
                target=self.ui._check_worker, args=(self.ui._check_seq,), daemon=True)
            worker.start()
            worker.join(timeout=2)
            self.pump_until(lambda: self._button_text() == "Install v9.9.9")
        finally:
            app.latest_release, app.is_newer, app.pick_asset = \
                original_latest, original_is_newer, original_pick

        self.assertEqual(self._button_text(), "Install v9.9.9")
        self.assertTrue(self.ui.settings_item.has_update)
        self.assertIsNotNone(self.ui._pending)
        self.assertEqual(self.ui._pending[0], "v9.9.9")


class AnOlderCheckResultDoesNotOverwriteANewerOne(UITestCase):
    """G#21/GH#32 item 3: two overlapping check_update() calls (unreachable
    today through the one button -- "Checking…" disables it before the
    worker even starts -- but reachable by any direct caller that bypasses
    the button, same as this file's own direct _check_worker() calls a few
    classes up) could previously let an older worker's result land after a
    newer check has already resolved, overwriting self._pending/the offer
    state with a stale release.

    Closed the same way G#39/GH#69 closed the identical shape for
    _poll_games()/_apply_scan() (see AnOlderScanResultDoesNotOverwriteA
    NewerOne below): each check_update() call stamps a monotonically
    increasing sequence number (self._check_seq), and the main-thread gate
    (_apply_check) drops any result whose sequence is older than the
    newest check already started, before ever touching self._pending/
    self._offer_update().

    Drives this through the REAL check_update()/_check_worker() path (not
    hand-made sequence numbers), with a controllable latest_release that
    blocks the first (older) check until explicitly released, so the
    ordering -- older check starts, newer check starts and lands first,
    older check is released and lands last -- is deterministic rather than
    a timing gamble. threading.Thread itself is wrapped (restored in
    finally) purely to get a joinable handle back for each check_update()
    call, since -- unlike _poll_games(), which keeps self._poll_thread --
    check_update() does not stash its own worker thread anywhere."""

    def test_an_orphaned_older_check_landing_later_is_dropped(self):
        entered_first = threading.Event()
        release_first = threading.Event()
        calls = {"n": 0}
        old_release = {"tag_name": "v8.0.0",
                       "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}
        new_release = {"tag_name": "v9.9.9",
                       "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}

        def fake_latest_release(timeout=10):
            calls["n"] += 1
            if calls["n"] == 1:
                entered_first.set()
                release_first.wait(5)
                return old_release
            return new_release

        created = []
        original_thread_cls = app.threading.Thread

        class _TrackingThread(original_thread_cls):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created.append(self)

        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = fake_latest_release
        app.is_newer = lambda tag, current=app.__version__: True
        app.pick_asset = lambda rel: rel["assets"][0]
        app.threading.Thread = _TrackingThread
        try:
            self.ui.check_update()         # starts the older check (seq 1)
            thread_a = created[-1]
            self.assertTrue(
                entered_first.wait(5),
                "older check never reached latest_release")
            self.ui.check_update()         # starts the newer check (seq 2),
                                            # supersedes seq 1 the same way
                                            # a second real click already
                                            # would (check_update()'s own
                                            # self._pending = None)
            thread_b = created[-1]
            self.assertIsNot(
                thread_a, thread_b,
                "test needs check_update() to actually start a second "
                "worker to exercise the overlapping-checks scenario")
            thread_b.join(5)
            self.assertFalse(thread_b.is_alive(),
                              "newer check should finish almost instantly "
                              "(latest_release returns instantly for it)")
            self.ui._drain_ui()
            self.assertIsNotNone(self.ui._pending)
            self.assertEqual(
                self.ui._pending[0], "v9.9.9",
                "the newer check's result should have landed before the "
                "older one is released")
            release_first.set()            # let the orphaned older check finish
            thread_a.join(5)
            self.assertFalse(thread_a.is_alive(),
                              "older check should have finished by now")
            self.ui._drain_ui()
        finally:
            app.latest_release, app.is_newer, app.pick_asset = \
                original_latest, original_is_newer, original_pick
            app.threading.Thread = original_thread_cls
        self.assertEqual(
            self.ui._pending[0], "v9.9.9",
            "an older check landing after a newer one was already applied "
            "must not overwrite it with stale data")


class AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer(UITestCase):
    """test-review.md round 1, Finding 2 (should-fix): _check_worker's four
    non-offer branches (NoReleases/unreachable/not-newer/no-build-for-OS)
    weren't seq-gated the way the offer path (_apply_check) already is --
    an orphaned older worker landing after a newer worker's offer has
    already been applied could still overwrite the button/version-label
    text with a stale "Up to date"/etc. message. Closed with the same
    _check_seq/_apply_check_state gate _apply_check() already uses for the
    offer path.

    Same deterministic-ordering technique as
    AnOlderCheckResultDoesNotOverwriteANewerOne above: the older check's
    latest_release() blocks until explicitly released, and it resolves to
    a NOT-newer release (drives the "Up to date" branch, not an offer),
    while the newer check resolves immediately to a newer release (drives
    a real offer)."""

    def test_an_orphaned_older_up_to_date_result_landing_after_a_newer_offer_is_dropped(self):
        entered_first = threading.Event()
        release_first = threading.Event()
        calls = {"n": 0}
        old_release = {"tag_name": "v1.0.0",
                       "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}
        new_release = {"tag_name": "v9.9.9",
                       "assets": [{"name": "Clickwork-linux-x86_64.tar.gz"}]}

        def fake_latest_release(timeout=10):
            calls["n"] += 1
            if calls["n"] == 1:
                entered_first.set()
                release_first.wait(5)
                return old_release
            return new_release

        def fake_is_newer(tag, current=app.__version__):
            return tag == "v9.9.9"     # only the newer check's release offers

        created = []
        original_thread_cls = app.threading.Thread

        class _TrackingThread(original_thread_cls):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created.append(self)

        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = fake_latest_release
        app.is_newer = fake_is_newer
        app.pick_asset = lambda rel: rel["assets"][0]
        app.threading.Thread = _TrackingThread
        try:
            self.ui.check_update()         # starts the older check (seq 1)
            thread_a = created[-1]
            self.assertTrue(
                entered_first.wait(5),
                "older check never reached latest_release")
            self.ui.check_update()         # starts the newer check (seq 2)
            thread_b = created[-1]
            self.assertIsNot(thread_a, thread_b)
            thread_b.join(5)
            self.assertFalse(thread_b.is_alive())
            self.ui._drain_ui()
            self.assertIsNotNone(self.ui._pending)
            self.assertEqual(self.ui._pending[0], "v9.9.9",
                             "the newer check's offer should have landed "
                             "before the older one is released")
            self.assertTrue(self.ui._update_text[0].startswith("Install"),
                            "the newer offer's button text should be showing")
            release_first.set()            # let the orphaned older check finish
            thread_a.join(5)
            self.assertFalse(thread_a.is_alive())
            self.ui._drain_ui()
        finally:
            app.latest_release, app.is_newer, app.pick_asset = \
                original_latest, original_is_newer, original_pick
            app.threading.Thread = original_thread_cls
        self.assertEqual(
            self.ui._pending[0], "v9.9.9",
            "the orphaned older check's non-offer result must not clear "
            "the newer offer's self._pending")
        self.assertTrue(
            self.ui._update_text[0].startswith("Install"),
            "an orphaned older check's stale 'Up to date' message must not "
            "overwrite a newer, already-applied offer's button text")


class RunningClickerSurvivesRebuild(UITestCase):
    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_worker_running_and_clicks_continue_across_a_rebuild(self):
        self.ui.mouse = FakeMouse()
        self.ui._select("global")
        self.ui.click_ms.var.set("60")
        self.pump(0.3)                          # let the snapshot catch up
        self.ui.start()
        self.pump(0.3)
        old_worker = self.ui.worker
        self.assertTrue(self.ui.running)

        self.ui._apply_appearance("light")      # runs synchronously, main thread
        self.root.update()

        self.assertIs(self.ui.worker, old_worker)
        self.assertTrue(self.ui.worker.is_alive())
        self.assertTrue(self.ui.running)
        self.ui.mouse.clicks.clear()
        self.pump(0.3)
        self.assertTrue(self.ui.mouse.clicks, "no clicks landed after the rebuild")
        self.assertEqual(
            self.ui.status.itemcget(self.ui.status.text, "text"), "RUNNING")

        self.ui.stop()
        self.pump(0.2)

    def test_worker_running_and_clicks_continue_across_a_scale_change(self):
        # Same guarantee as the Appearance test above, docs/history/ac-17-f4-spec.md's own
        # "a running clicker survives a scale-triggered rebuild unharmed" --
        # none of self.worker/self.hk_listener/the click-loop thread's state
        # lives in the destroyed/rebuilt widget tree, so a UI-scale change
        # (a different trigger for the identical _rebuild_ui() path) must
        # leave it exactly as unaffected.
        self.ui.mouse = FakeMouse()
        self.ui._select("global")
        self.ui.click_ms.var.set("60")
        self.pump(0.3)                          # let the snapshot catch up
        self.ui.start()
        self.pump(0.3)
        old_worker = self.ui.worker
        self.assertTrue(self.ui.running)

        self.ui._apply_ui_scale("130")          # runs synchronously, main thread
        self.root.update()

        self.assertIs(self.ui.worker, old_worker)
        self.assertTrue(self.ui.worker.is_alive())
        self.assertTrue(self.ui.running)
        self.ui.mouse.clicks.clear()
        self.pump(0.3)
        self.assertTrue(self.ui.mouse.clicks, "no clicks landed after the rebuild")
        self.assertEqual(
            self.ui.status.itemcget(self.ui.status.text, "text"), "RUNNING")

        self.ui.stop()
        self.pump(0.2)


class HotkeyListenerSurvivesRebuild(UITestCase):
    needs_input_permission = unittest.skipIf(
        app is not None and app.sys.platform == "darwin",
        "starting a listener aborts the process on macOS -- see issue #7")

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    @needs_input_permission
    def test_listener_object_identity_is_unchanged_across_a_rebuild(self):
        self.ui.hotkey = hotkey({"ctrl"}, [kb.Key.f6])
        self.ui.apply_hotkey()
        self.root.update()
        listener = self.ui.hk_listener
        self.assertIsNotNone(listener)

        self.ui._apply_appearance("light")
        self.root.update()

        self.assertIs(self.ui.hk_listener, listener)
        self.assertTrue(self.ui.hk_listener.running)


class AfterJobsAreNotDuplicated(UITestCase):
    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def _after_count(self):
        return len(self.root.tk.call("after", "info"))

    def test_exactly_three_after_jobs_survive_three_rebuilds(self):
        # ui._timers is a dict keyed by chain name ("poll_games", "drain",
        # "sync_settings") -- each self-rescheduling job replaces its own
        # entry every time it fires, rather than appending a fresh id, so
        # its size is always exactly 3 for the app's whole life, not just
        # in the instant right after a rebuild resets it. Checked right
        # after each rebuild here mainly because that is when the *ids*
        # inside it are new, not because the count would otherwise drift.
        for value in ("light", "dark", "light"):
            self.ui._apply_appearance(value)
            self.root.update()          # runs the after_idle-deferred rebuild
            self.assertEqual(len(self.ui._timers), 3)
            self.assertEqual(self._after_count(), 3)

    def test_timer_count_does_not_grow_between_rebuilds(self):
        # Each of the 3 self-rescheduling jobs (_poll_games/_drain_ui/
        # _sync_settings) replaces its own dict entry on every fire instead
        # of appending, so len(_timers) stays 3 no matter how many times
        # they fire with no rebuild at all. On the old list-based
        # self._timers.append(...) code this grows to roughly 30 after
        # about 1s of pumping (the 40ms drain job alone fires ~25 times).
        self.assertEqual(len(self.ui._timers), 3)
        self.pump(1.0)
        self.assertEqual(len(self.ui._timers), 3)


class BindAllBoundOnce(UITestCase):
    # G#38/GH#67 round 3 (PR #89 review): same reasoning as NumBoxFocus's
    # own INITIAL_UI_SCALE.
    INITIAL_UI_SCALE = "100"

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_bind_all_is_never_reissued_by_a_rebuild(self):
        calls = []
        orig_bind_all = self.root.bind_all

        def counting(*a, **kw):
            calls.append((a, kw))
            return orig_bind_all(*a, **kw)
        self.root.bind_all = counting
        try:
            self.ui._apply_appearance("light")
            self.root.update()
            self.ui._apply_appearance("dark")
            self.root.update()
            self.assertEqual(calls, [], "bind_all was called again by a rebuild")
        finally:
            self.root.bind_all = orig_bind_all

    def test_a_click_still_drops_focus_exactly_once_after_two_theme_changes(self):
        self.ui._apply_appearance("light")
        self.root.update()
        self.ui._apply_appearance("dark")
        self.root.update()
        # click_ms lives in the Clicking pane, hidden by default (story #24
        # feature 2) -- a real user has to click that tab before focus_set()
        # on an entry inside it does anything real.
        self.ui._set_content_tab("clicking")
        self.root.update()
        self.ui.click_ms.entry.focus_set()
        self.root.update()
        calls = []
        original = self.ui._maybe_drop_focus
        self.ui.count_label.bind("<Button-1>", lambda e: calls.append(1), add="+")
        self.ui.count_label.event_generate("<Button-1>", x=1, y=1)
        self.root.update()
        self.assertEqual(calls, [1])
        self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)


class DrainUiSurvivesAStaleClosure(UITestCase):
    """The permanent-death bug: a self.status.set bound method captured
    before a rebuild must not permanently kill _drain_ui when it raises
    TclError on the now-destroyed canvas -- the loop must drop the stale
    closure and keep draining, so a later queued update still applies."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_a_later_queued_update_still_applies_after_a_stale_closure(self):
        stale = self.ui.status.set          # bound to the pre-rebuild canvas,
                                             # exactly how the old code used
                                             # to enqueue it
        self.ui._rebuild_ui()
        self.root.update()

        self.ui._ui_queue.put((stale, ("OFF", app.BAD, "")))
        self.ui._ui_queue.put((self.ui._set_status, ("RUNNING", app.OK, "")))

        self.pump_until(
            lambda: self.ui.status.itemcget(self.ui.status.text, "text") == "RUNNING")
        self.assertEqual(
            self.ui.status.itemcget(self.ui.status.text, "text"), "RUNNING")


class OverlappingAppearanceChanges(UITestCase):
    """docs/history/ac-17-f3a-test-review.md Defect 1: two Appearance changes landing before
    the first after_idle(self._rebuild_ui) has run used to raise an
    uncaught TclError -- card()'s _redraw() calls inner.update_idletasks(),
    which reentrantly ran the SECOND already-queued idle rebuild mid-way
    through the first one, tearing down widgets the first rebuild's own
    card() calls were still holding references to. _apply_appearance() now
    coalesces: at most one rebuild is ever pending. CapturesCallbackExceptions
    (via UITestCase) is what actually proves "no crash" here -- Tk prints a
    swallowed callback exception to stderr and otherwise carries on, so an
    assertion on the app's own state alone would not have caught this."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_two_rapid_appearance_changes_before_the_idle_rebuild_drains(self):
        self.ui._apply_appearance("light")
        self.ui._apply_appearance("dark")
        self.root.update()
        self.assertEqual(self.root.cget("bg"), app.THEMES["dark"]["BG"])

    def test_five_rapid_appearance_changes_coalesce_into_exactly_one_rebuild(self):
        calls = []
        original_rebuild = self.ui._rebuild_ui

        def counting():
            calls.append(1)
            return original_rebuild()
        self.ui._rebuild_ui = counting
        try:
            for value in ("light", "dark", "light", "dark", "light"):
                self.ui._apply_appearance(value)
            self.root.update()
        finally:
            self.ui._rebuild_ui = original_rebuild
        self.assertEqual(
            len(calls), 1,
            "5 rapid Appearance picks must coalesce into exactly one rebuild")
        self.assertEqual(self.root.cget("bg"), app.THEMES["light"]["BG"])

    def test_two_real_segmented_clicks_with_no_pump_between_them(self):
        self.ui._show_settings()
        self.root.update()
        seg = self._appearance_segment()
        seg_w = seg.w / 3
        # Real <Button-1> events on the actual control, back to back, no
        # root.update() between them -- a physically plausible fast
        # double-click; see docs/test-review.md's repro #2.
        seg.event_generate("<Button-1>", x=int(seg_w * 1.5), y=int(seg.h / 2))  # "Light"
        seg.event_generate("<Button-1>", x=int(seg_w * 2.5), y=int(seg.h / 2))  # "Dark"
        self.root.update()
        self.assertEqual(self.ui.appearance_var.get(), "dark")
        self.assertEqual(self.root.cget("bg"), app.THEMES["dark"]["BG"])

    def test_on_close_between_an_appearance_change_and_its_idle_rebuild(self):
        self.ui._apply_appearance("light")   # queues after_idle(self._rebuild_ui)
        job_id = self.ui._rebuild_after_id
        self.assertIsNotNone(job_id, "no idle rebuild was actually pending")

        # _release_right() is on_close()'s last call before root.destroy() --
        # hooking it is the last point at which "after info" can still be
        # queried at all, and proves the cancellation happened strictly
        # before destroy(), not just "eventually".
        original_release = self.ui._release_right
        checked = []

        def patched_release():
            original_release()
            checked.append(self.root.tk.call("after", "info"))
        self.ui._release_right = patched_release
        try:
            self.ui.on_close()               # closes before that job ever runs
        finally:
            self.ui._release_right = original_release
        self.assertEqual(len(checked), 1, "the patched _release_right never ran")
        self.assertNotIn(job_id, checked[0],
                         "on_close() left the pending idle rebuild scheduled")

        try:
            self.root.update()               # give the stale idle job a turn
        except tk.TclError:
            pass
        self._assert_no_callback_exceptions()


class OverlappingScaleAndAppearanceChanges(UITestCase):
    """docs/history/ac-17-f4-spec.md §4: a UI-scale change and an Appearance change fired in
    quick succession must coalesce into exactly one rebuild -- the same
    self._rebuilding/_rebuild_wanted/_rebuild_after_id machinery
    OverlappingAppearanceChanges (above) already proves for repeated
    Appearance changes alone, now shared by both callers via
    _request_rebuild(). Generalizes
    test_five_rapid_appearance_changes_coalesce_into_exactly_one_rebuild's
    counting-wrapper technique, interleaving the two kinds of change in
    both orders."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_scale_then_appearance_coalesce_into_one_rebuild(self):
        calls = []
        original_rebuild = self.ui._rebuild_ui

        def counting():
            calls.append(1)
            return original_rebuild()
        self.ui._rebuild_ui = counting
        try:
            self.ui._apply_ui_scale("130")
            self.ui._apply_appearance("light")
            self.root.update()
        finally:
            self.ui._rebuild_ui = original_rebuild
        self.assertEqual(len(calls), 1,
                         "a scale change then an appearance change must "
                         "coalesce into exactly one rebuild")
        self.assertEqual(self.ui.store.data["ui_scale"], "130")
        self.assertEqual(self.ui.s, self.ui._dpi_s * app.UI_SCALE_FACTORS["130"])
        self.assertEqual(self.root.cget("bg"), app.THEMES["light"]["BG"])

    def test_appearance_then_scale_coalesce_into_one_rebuild(self):
        calls = []
        original_rebuild = self.ui._rebuild_ui

        def counting():
            calls.append(1)
            return original_rebuild()
        self.ui._rebuild_ui = counting
        try:
            self.ui._apply_appearance("light")
            self.ui._apply_ui_scale("90")
            self.root.update()
        finally:
            self.ui._rebuild_ui = original_rebuild
        self.assertEqual(len(calls), 1,
                         "an appearance change then a scale change must "
                         "coalesce into exactly one rebuild")
        self.assertEqual(self.ui.store.data["ui_scale"], "90")
        self.assertEqual(self.ui.s, self.ui._dpi_s * app.UI_SCALE_FACTORS["90"])
        self.assertEqual(self.root.cget("bg"), app.THEMES["light"]["BG"])


class ReentrantAppearanceChangeDuringRebuild(UITestCase):
    """docs/history/ac-17-f3a-test-review.md Round 2 review, Finding #1: _rebuild_ui() clears
    self._rebuild_after_id to None at its own top, before its body runs. An
    _apply_appearance() call from *inside* that body (a future synchronous
    internal caller -- not reachable through today's only real caller, a
    <Button-1>-driven trace, but not enforced against either) would see
    None and schedule a fresh after_idle job, which the SAME still-running
    rebuild's own card() calls then reentrantly service via
    update_idletasks() -- reproducing Defect 1's exact crash through a
    different door (probe5_reentrant_card.py). self._rebuilding/
    self._rebuild_wanted close it: while a rebuild is running,
    _apply_appearance() only marks a follow-up wanted; _rebuild_ui()'s own
    finally block schedules exactly one once it has fully finished."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_appearance_change_fired_from_inside_a_rebuild_does_not_crash(self):
        # _build_content() (the default, Settings-closed view) calls card()
        # three times in a row (hotkey, clicking, eating) -- unlike
        # _build_settings()'s single card, this gives a SECOND/THIRD card()
        # call, still inside the SAME still-running rebuild, a chance to
        # reentrantly service a job queued between them. Matches
        # probe5_reentrant_card.py's own shape and its crash site
        # (Row(hk, "Toggle", s), the card right after the injection point).
        rebuild_calls = []
        original_rebuild = self.ui._rebuild_ui

        def counting_rebuild():
            rebuild_calls.append(1)
            return original_rebuild()
        self.ui._rebuild_ui = counting_rebuild

        original_card = app.card
        fired = []

        def patched_card(parent, s, on_settle=None):
            result = original_card(parent, s, on_settle=on_settle)
            if not fired:
                fired.append(1)
                # Simulates a trace/callback re-entering _apply_appearance()
                # WHILE the current _rebuild_ui() call (still inside
                # _build_content(), about to build its next card()) is
                # still on the stack.
                self.ui._apply_appearance("dark")
            return result
        app.card = patched_card

        try:
            self.ui._apply_appearance("light")   # queues the first (only) idle rebuild
            self.pump_until(lambda: len(rebuild_calls) >= 2, timeout=2.0)
        finally:
            app.card = original_card
            self.ui._rebuild_ui = original_rebuild

        self.assertEqual(
            len(rebuild_calls), 2,
            "exactly one follow-up rebuild should run once the in-progress "
            "one finishes, on top of the one 'light' itself queued")
        self.assertEqual(
            self.root.cget("bg"), app.THEMES["dark"]["BG"],
            "final theme should match the last choice ('dark', applied "
            "mid-rebuild), not the one the in-progress rebuild started with")
        self._assert_no_callback_exceptions()


class QueuedNonResyncedUpdatesSurviveARebuild(UITestCase):
    """PR review Finding #2 (docs/implementation.md "Round 4"): _rebuild_ui()
    used to replace self._ui_queue with a fresh queue.SimpleQueue() on every
    rebuild -- documented as harmless because "the next state transition
    re-queues one." True only for RUNNING/OFF, the two states _build_ui()'s
    own tail resyncs from self.running; an ERROR/STOPPED/EATING status, or a
    _mark_running() scan result, queued an instant before a rebuild was
    silently and permanently dropped instead, with no trace it ever
    happened. The swap is gone now -- one queue for the app's whole
    lifetime, same as every other queued callback already resolves its
    target fresh at drain time."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_error_and_stopped_updates_survive_a_rebuild(self):
        for text, color, hint in (
            ("ERROR", app.BAD, "boom"),
            ("STOPPED", app.MUTED, "auto-stop after 5 min"),
        ):
            with self.subTest(text=text):
                self.ui.running = False   # matches loop()'s own finally ordering
                self.ui._ui(self.ui._set_status, text, color, hint)
                self.ui._rebuild_ui()      # queued before this call, not after
                self.ui._drain_ui()        # _rebuild_ui()'s own tail already
                                            # drains it too -- calling again
                                            # here is a harmless no-op on an
                                            # empty queue, matching the
                                            # dispatch's literal "queued,
                                            # then a rebuild, then a drain"
                self.assertEqual(
                    self.ui.status.itemcget(self.ui.status.text, "text"), text,
                    f"a queued {text} update should survive a rebuild, not "
                    "be silently dropped by the old _ui_queue swap")

    def test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands(self):
        # G#30/GH#53 (macOS-only flake): _build_ui()'s own tail -- reached
        # from inside the _rebuild_ui() call below -- unconditionally starts
        # a brand new _poll_games() scan of its own, on a real background
        # thread, same as construction did for setUp()'s settle(). That scan
        # is genuinely real here (detect_running is never mocked in this
        # class): a Xlib tree walk on Linux, an `osascript` subprocess on
        # macOS. If that second, uninvited scan's own self._ui(self.
        # _mark_running, ...) call lands -- via this test's own trailing
        # _drain_ui() below, there being no other drain path between the two
        # -- before the assertion runs, it overwrites self._seen_running
        # with whatever real windows happen to be open on the CI runner,
        # which never includes "minecraft". That is a real race, not a
        # dropped queue entry: _seen_running does get set, just to the
        # second scan's real result instead of this test's queued one,
        # which reads identically to "queued update silently dropped" in
        # the assertion below (a plain set difference) without actually
        # being that historical bug. Nothing in the linear code path between
        # the queue-put and the drain gives the *original* queued value
        # anywhere else to be lost -- no root.update() runs in between for
        # a stray timer to be serviced through, and _rebuild_ui()'s own
        # _rebuilding/_rebuild_after_id guards already rule out a second,
        # reentrant _rebuild_ui() call interleaving here.
        #
        # Round 2 (G#30 PR review): an earlier version of this fix stubbed
        # detect_running to return this test's own target instead of
        # disabling _poll_games() below. That collapsed the race rather than
        # closing it: threading.Thread.start() does not return until the new
        # thread has signalled it has begun (an internal Event), which in
        # practice hands the child the GIL first -- so with detect_running
        # made instant (no real Xlib/osascript call to block on and yield
        # the GIL), the second scan's own self._ui(self._mark_running, ...)
        # call reliably lands before this test's own _drain_ui() below, every
        # time, not merely "if it wins a race". Stubbing it to the SAME value
        # this test queues made that reliable second landing invisible --
        # sabotage (reintroducing the historical _ui_queue swap at
        # _rebuild_ui(), so the manually-queued call below is genuinely
        # dropped) still passed 3/3, because the second scan's forged
        # "minecraft" landed in its place and the assertion cannot tell the
        # two apart. Disabling _poll_games() for the duration of this test
        # instead removes the confound entirely -- no second scan, real or
        # stubbed, ever starts, so nothing but this test's own queued call
        # can land, and a genuinely dropped entry has nothing left to hide
        # behind.
        #
        # Round 3 (G#39/GH#69, macOS-only recurrence): stubbing self.
        # _poll_games only closes the ONE call site above (the rebuild's own
        # rescan) -- it does nothing about a scan already started by setUp()
        # itself. __init__ -> _build_ui()'s tail runs the first, real
        # _poll_games() before this test method (or its stub) ever exists,
        # which both starts a background scan thread AND arms a
        # self-rescheduling 5000ms self.root.after(...) timer
        # (afk_clicker.py:3131) that captured the REAL _poll_games as its
        # callback -- reassigning self.ui._poll_games later has no effect on
        # a timer that already holds the original bound method. On a loaded
        # macOS runner, settle() (tests/test_ui.py's own UITestCase.settle())
        # calls root.update() in a loop while waiting out a slow initial
        # `osascript` scan, and root.update() (unlike update_idletasks())
        # does service due timer events -- so IF that first scan takes long
        # enough, the periodic timer could fire a SECOND real scan while
        # still inside setUp(), before this test body runs, and settle()
        # returns as soon as _seen_running first exists, not once no scan is
        # in flight, so that second scan could still be running, unjoined,
        # when this method starts. Its own self._ui(self._mark_running, ...)
        # call is a plain, thread-safe queue put needing no Tk event-loop
        # cycle to land, so it could clobber this test's manually-queued
        # target between the put below and the final _drain_ui() exactly
        # like the rebuild's own rescan used to (Round 1/2), just from a
        # different, earlier source the _poll_games stub can't reach.
        # Neutralizing it before the manual put -- cancelling any armed
        # timer and joining the real poll thread, same pattern as on_close()
        # (afk_clicker.py:3446-3484) -- closes this for the single most-
        # recently-started scan. It does NOT, on its own, close it for an
        # OLDER scan that a later one has already overwritten
        # self.ui._poll_thread out from under -- see "Round 5" below for why
        # that needed a small production-side fix instead.
        #
        # Round 4 (PR #70 review / PR #71 macOS evidence, hedge): the path
        # above is real and closed regardless -- an independent race-class
        # reproduction (old critical section red, new one green against the
        # same injected in-flight `_poll_thread`) confirms the mechanism, and
        # two independently-designed sabotages (queue-object swap, and
        # discarding queued closures without executing them) both still fail
        # this test 5/5, so the fix does not blind the guard either way.
        # What is NOT confirmed: that this was actually the trigger behind
        # the real G#39 macOS recurrence. A dedicated diagnostic (draft PR
        # #71, run 34942811672) looped this exact test 40x in isolation on
        # macOS and found 0/40 failures, no poll thread ever alive at a
        # manual queue-put, no periodic _poll_games firing inside the test,
        # and every real scan finishing in well under 0.5s (max 0.481s,
        # median 0.162s) -- nowhere near the ~5s stall this hypothesis
        # requires. That is absence of the triggering condition in isolation
        # (the historical failures happened inside a loaded full-suite run,
        # a different timing profile), not evidence against the mechanism
        # itself, but it means H1 -- "a slow macOS osascript stall arms a
        # still-running poller thread" -- is likely but UNCONFIRMED as
        # G#39's actual real-world trigger; see backlog.md's G#39 entry and
        # docs/implementation.md for the same hedge. This fix ships anyway,
        # as a defensive closure of a real, code-established, sabotage-
        # verified race path and a strict superset of PR #58's already-
        # accepted fix -- not as a claimed resolution of G#39 itself. If
        # G#39 recurs with this fix in place, that will mean H1 was not the
        # (only) cause and the investigation needs to resume from the
        # loaded-full-suite condition instead.
        #
        # Round 5 (PR #70 independent review, Finding #1, BLOCKER -- fixed in
        # afk_clicker.py, not here): the neutralization above only ever sees
        # self.ui._poll_thread's CURRENT value. _poll_games()
        # (afk_clicker.py:3093-3151) overwrites that attribute on every call,
        # including its own periodic reschedule, without joining whatever
        # scan it just replaced -- so when an older scan is still stalled
        # when a newer one starts (H1's own described trigger), the older
        # scan's thread handle is gone from anywhere this block can reach.
        # Reproduced directly against real production code by the reviewer
        # (scratchpad's pr70-own-sabotage.py): the orphaned older scan lands
        # its own _mark_running call later, after this test's own assertion
        # would already have run, clobbering the result with stale data and
        # tripping neither the join nor the loud-fail above (nothing here
        # was ever "alive" to check). This is a genuine PRODUCT race, not
        # only a test-exposure gap -- a live "what's running now" indicator
        # really can regress to stale window state -- so it's fixed at the
        # source: _poll_games() now stamps each call with a monotonically
        # increasing sequence number, and a new self._apply_scan(seq,
        # running) gate (afk_clicker.py) drops any scan result older than
        # the newest one already applied, before ever calling
        # _mark_running(). See AnOlderScanResultDoesNotOverwriteANewerOne
        # below for the dedicated regression test, driven through the real
        # _poll_games()/scan() path, and docs/implementation.md's "Round 3"
        # section for the rejected alternatives (joining the predecessor
        # inside _poll_games() itself would let one stuck Xlib.display.
        # Display() connection freeze detection entirely; more test-side
        # thread tracking would leave the real production gap open for any
        # other caller). This block's own join/loud-fail still matters --
        # it closes the single-most-recent-scan case on its own, without
        # having to wait for a slower scan's sequence number to resolve --
        # the two mechanisms are complementary, not redundant.
        old_seen = self.ui._seen_running   # already set by setUp()'s settle()
        target = {"minecraft"}
        self.assertNotEqual(old_seen, target,
                            "test needs a genuinely different value to prove "
                            "the queued call actually landed, not that "
                            "_seen_running just happened to already match")
        original_poll_games = self.ui._poll_games
        self.ui._poll_games = lambda: None
        try:
            # Neutralize a scan already in flight/armed from setUp() (Round
            # 3/G#39) before queuing the manual value below: cancel the
            # periodic timer if one is still armed, join the real poll
            # thread if it's still running, then drain once more so a
            # genuine, harmless landing from before this critical section
            # can't be mistaken for -- or collide with -- the value this
            # test is about to queue itself.
            job = self.ui._timers.pop("poll_games", None)
            if job is not None:
                try:
                    self.ui.root.after_cancel(job)
                except tk.TclError:
                    pass
            poll_thread = getattr(self.ui, "_poll_thread", None)
            if poll_thread is not None and poll_thread.is_alive():
                # Bounded to 5s, not on_close()'s 2.0s (afk_clicker.py:3481-
                # 3484): on_close() optimizes for a fast shutdown and is
                # content to abandon a still-running scan after its shorter
                # bound, since nothing downstream depends on that scan
                # landing. This test's whole point is the opposite -- it
                # needs the poller genuinely silenced before the manual
                # queue-put, not merely bounded-then-ignored -- so it needs
                # to tolerate the legitimately slow (not stuck) osascript
                # stall settle()'s own docstring documents (up to ~5s on a
                # loaded macOS runner) rather than the rarer, truly-stuck
                # Display() case on_close()'s shorter bound guards against.
                # If the thread is STILL alive after that generous a wait,
                # proceeding anyway would silently walk back into the exact
                # race this fix exists to close, with no signal about why --
                # failing loudly here instead means a future recurrence
                # tells us plainly whether a still-running poller (H1) was
                # actually the trigger, rather than reproducing the same
                # ambiguous 'minecraft'-missing assertion with no diagnosis.
                poll_thread.join(timeout=5.0)
                if poll_thread.is_alive():
                    self.fail(
                        "real game poller still running after 5s; cannot "
                        "isolate the queued update from a real scan landing "
                        "later -- see G#39")
            self.ui._drain_ui()
            self.ui._ui(self.ui._mark_running, target)
            self.ui._rebuild_ui()
            self.ui._drain_ui()
            self.assertEqual(
                self.ui._seen_running, target,
                "a queued _mark_running() scan result should survive a "
                "rebuild, not be silently dropped by the old _ui_queue swap")
        finally:
            self.ui._poll_games = original_poll_games


class AnOlderScanResultDoesNotOverwriteANewerOne(UITestCase):
    """G#39/GH#69, PR #70 review Finding #1: _poll_games() unconditionally
    overwrites self._poll_thread on every call (afk_clicker.py:3129-3130),
    including the periodic 5000ms reschedule, without ever joining whatever
    scan it just superseded. If an earlier scan is still stalled when a
    later one starts (H1's own story -- a slow osascript call still running
    when the periodic timer fires again), self._poll_thread only ever
    points at the newer scan; the older one's thread handle is gone from
    anywhere else that could join or check it. When that orphaned older
    scan eventually finishes, its own self._ui(self._mark_running, ...)
    call used to land exactly like a fresh one, silently clobbering
    whatever the newer scan (or, in the flaky test this guards elsewhere,
    a manually queued value) had already set -- with no diagnostic, no
    exception, nothing for QueuedNonResyncedUpdatesSurviveARebuild's own
    quiesce-then-join to catch, because that block only ever sees the
    single most-recently-started thread.

    This is a genuine product race (a live "what's running now" indicator
    can regress to stale data), not just a test-hermeticity gap, so unlike
    every other round of this fix it is closed in afk_clicker.py itself:
    each _poll_games() call stamps its own scan with a monotonically
    increasing sequence number (self._poll_seq), and the main-thread
    handler (_apply_scan) drops any result whose sequence is older than
    the newest one already applied (self._poll_applied_seq), before ever
    calling _mark_running(). A later-started scan's result always wins
    once applied, regardless of which scan's thread actually finishes (or
    lands) first. _mark_running() itself is unchanged -- this test's own
    sibling class still calls it directly via self.ui._ui(...), bypassing
    sequencing entirely, since a hand-queued value isn't a scan result.

    Drives this through the REAL _poll_games()/scan() path (not by calling
    _apply_scan with hand-made sequence numbers), with a controllable
    detect_running that blocks the first (older) scan until explicitly
    released, so the ordering -- older scan starts, newer scan starts and
    lands first, older scan is released and lands last -- is deterministic
    rather than a timing gamble."""

    def test_an_orphaned_older_scan_landing_later_is_dropped(self):
        entered_first = threading.Event()
        release_first = threading.Event()
        calls = {"n": 0}
        old_result = {"global"}
        new_result = {"minecraft"}

        def fake_detect_running(profiles):
            calls["n"] += 1
            if calls["n"] == 1:
                entered_first.set()
                release_first.wait(5)
                return old_result
            return new_result

        original_detect_running = app.detect_running
        app.detect_running = fake_detect_running
        try:
            self.ui._poll_games()          # starts the older scan
            thread_a = self.ui._poll_thread
            self.assertTrue(
                entered_first.wait(5),
                "older scan never reached detect_running")
            self.ui._poll_games()          # starts the newer scan, overwrites
                                            # self.ui._poll_thread -- thread_a's
                                            # handle is now orphaned, exactly
                                            # like the reviewed defect
            thread_b = self.ui._poll_thread
            self.assertIsNot(
                thread_a, thread_b,
                "test needs _poll_games() to actually overwrite _poll_thread "
                "to exercise the orphaned-scan scenario")
            thread_b.join(5)
            self.assertFalse(thread_b.is_alive(),
                              "newer scan should finish almost immediately "
                              "(detect_running returns instantly for it)")
            self.ui._drain_ui()
            self.assertEqual(
                self.ui._seen_running, new_result,
                "the newer scan's result should have landed before the "
                "older one is released")
            release_first.set()            # let the orphaned older scan finish
            thread_a.join(5)
            self.assertFalse(thread_a.is_alive(),
                              "older scan should have finished by now")
            self.ui._drain_ui()
        finally:
            app.detect_running = original_detect_running
        self.assertEqual(
            self.ui._seen_running, new_result,
            "an older scan landing after a newer one was already applied "
            "must not overwrite it with stale data")


class QueuedStatusSurvivesARebuild(UITestCase):
    """Round 8 coverage gap (docs/history/ac-17-f3a-test-review.md): reverting _set_status's
    fresh-lookup indirection at all 6 call sites in start()/stop()/loop()
    left the full suite green, because every existing rebuild test only
    ever lands a RUNNING/OFF update -- exactly what _rebuild_ui()'s own
    boolean resync already writes, so the two implementations are
    indistinguishable there. EATING is never written by the resync, so it
    is the only way to tell "the queued update actually landed" apart from
    "the resync happened to already agree". Goes through loop()'s real
    EATING call site (not a hand-built queue tuple, unlike
    DrainUiSurvivesAStaleClosure above), timed via StatusPill.__init__ to
    land in the exact window _set_status's own docstring names: after
    _rebuild_ui() has already swapped in a fresh _ui_queue, but before
    self.status is reassigned to the new pill."""

    def tearDown(self):
        super().tearDown()
        app.set_active_theme("dark")

    def test_a_queued_eating_update_lands_on_the_post_rebuild_pill(self):
        self.ui.mouse = FakeMouse()
        self.ui._select("global")
        self.ui.button_name.set("left")
        self.ui.eat_mode.set("pause")
        self.ui.eat_every.var.set("5")     # the field's own enforced minimum
        self.ui.eat_hold.var.set("5")
        self.ui._sync_settings()           # settings snapshot the worker reads
        self.ui.running = True
        old_status = self.ui.status

        # Fast-forward the worker's own clock instead of waiting 5 real
        # seconds for eat_every to elapse: every time.monotonic() call
        # inside afk_clicker jumps 1 (fake) second forward, so loop()'s
        # deadlines/intervals stay internally consistent (all computed from
        # the same function) while "eat_every seconds since the last meal"
        # arrives within a handful of calls. real_monotonic is captured
        # before patching so this test's own polling below keeps using the
        # real wall clock -- time.monotonic is one shared module-level
        # function, patching app.time.monotonic changes what plain
        # time.monotonic() resolves to here too.
        real_monotonic = app.time.monotonic
        fake_clock = [0.0]

        def fake_monotonic():
            fake_clock[0] += 1.0
            return fake_clock[0]

        original_init = app.StatusPill.__init__

        def patched_init(pill_self, *a, **kw):
            original_init(pill_self, *a, **kw)
            # Fires from inside _build_ui(), called by _rebuild_ui() AFTER
            # its own self._ui_queue = queue.SimpleQueue() swap but BEFORE
            # self.status is reassigned to this new pill -- the narrow
            # window _set_status's docstring describes. Starting the real
            # worker here, instead of before _rebuild_ui() at all, is what
            # guarantees its self._ui(self._set_status, "EATING", ...) call
            # lands inside that window rather than being dropped by the
            # queue swap.
            worker = threading.Thread(target=self.ui.loop, daemon=True)
            worker.start()
            deadline = real_monotonic() + 2.0
            while real_monotonic() < deadline and not self.ui.right_held:
                time.sleep(0.005)
            self.assertTrue(self.ui.right_held,
                            "worker never reached the EATING branch")
            self.ui.running = False        # let the interruptible _sleep(hold) exit
            worker.join(timeout=2.0)

        app.time.monotonic = fake_monotonic
        app.StatusPill.__init__ = patched_init
        try:
            self.ui._rebuild_ui()
        finally:
            app.StatusPill.__init__ = original_init
            app.time.monotonic = real_monotonic

        self.assertIsNot(self.ui.status, old_status,
                         "the rebuild should have replaced the pill")
        self.pump_until(
            lambda: self.ui.status.itemcget(self.ui.status.text, "text") == "EATING")
        self.assertEqual(
            self.ui.status.itemcget(self.ui.status.text, "text"), "EATING",
            "the queued EATING update did not land on the post-rebuild pill")


@needs_display
class StartupHonoursSavedAppearance(CapturesCallbackExceptions, unittest.TestCase):
    def tearDown(self):
        app.set_active_theme("dark")

    def test_a_saved_light_appearance_opens_already_light_no_settings_visit_needed(self):
        config = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(config, "w") as fh:
            json.dump({"appearance": "light"}, fh)
        store = app.Store(config)
        appearance = store.data["appearance"]
        os_theme = app.detect_os_theme() if appearance == "system" else None
        app.set_active_theme(app.resolve_appearance(appearance, os_theme))
        root = tk.Tk()
        self._capture_callback_exceptions(root)
        ui = app.AfkAutoclicker(root, store=store, os_theme=os_theme)
        root.update()
        try:
            self.assertEqual(root.cget("bg"), app.THEMES["light"]["BG"])
        finally:
            try:
                ui.on_close()
            except tk.TclError:
                pass
        self._assert_no_callback_exceptions()

    def test_system_appearance_detects_at_most_once_including_a_later_repick(self):
        config = os.path.join(tempfile.mkdtemp(), "settings.json")
        store = app.Store(config)          # appearance defaults to "system"
        calls = []
        orig = app.detect_os_theme
        app.detect_os_theme = lambda: (calls.append(1), "light")[1]
        root = ui = None
        try:
            appearance = store.data["appearance"]
            os_theme = app.detect_os_theme() if appearance == "system" else None
            app.set_active_theme(app.resolve_appearance(appearance, os_theme))
            root = tk.Tk()
            self._capture_callback_exceptions(root)
            ui = app.AfkAutoclicker(root, store=store, os_theme=os_theme)
            root.update()
            ui._show_settings()
            root.update()
            ui.appearance_var.set("light")
            root.update()
            ui.appearance_var.set("system")   # re-pick "System" mid-session
            root.update()
            self.assertEqual(len(calls), 1)
        finally:
            app.detect_os_theme = orig
            if ui is not None:
                try:
                    ui.on_close()
                except tk.TclError:
                    pass
        self._assert_no_callback_exceptions()


@needs_display
class UpdateLogPrompt(CapturesCallbackExceptions, unittest.TestCase):
    """The startup dialog G#36/GH#64 adds: a one-off Toplevel offering to
    report a previous in-app update attempt that didn't finish.

    Not built on UITestCase: that class's own setUp() already constructs
    self.ui before a test gets a chance to write update.log, and the
    dialog's own after_idle(self._maybe_offer_log_report) job (scheduled
    from __init__) needs the log to already be there by then."""

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.config = os.path.join(self.workdir, "settings.json")
        self.log_path = os.path.join(self.workdir, "update.log")
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.ui = None

    def tearDown(self):
        if self.ui is not None:
            try:
                self.ui.on_close()
            except tk.TclError:
                pass
        gc.collect()
        self._assert_no_callback_exceptions()

    def _write_log(self, text):
        with open(self.log_path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _build(self):
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        # _maybe_offer_log_report is scheduled via after_idle in __init__;
        # root.update() services pending idle jobs the same way
        # UITestCase.settle() already relies on for the startup game scan.
        self.root.update()

    # ---------- round 3 (test-review.md): the startup idle job itself ----------

    def test_on_close_before_the_startup_idle_job_ever_ran_cancels_it(self):
        # G#36/GH#64 round 3: after_idle(self._maybe_offer_log_report),
        # scheduled at __init__'s own tail, used to have no stored id
        # anywhere -- nothing could ever cancel it. A close reached before
        # this job's first turn left it queued; on macOS CI it later fired
        # against an already-destroyed root (TclError deep inside
        # _fit_log_dialog_to_content -- invisible on Linux/Windows's own
        # idle-flush timing). Mirrors
        # OverlappingAppearanceChanges.test_on_close_between_an_appearance_change_and_its_idle_rebuild's
        # own "after info" technique for _rebuild_after_id.
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        # Deliberately no self.root.update() here -- the whole point is to
        # close before this startup idle job has ever had a turn.
        job_id = self.ui._log_report_after_id
        self.assertIsNotNone(job_id, "no startup idle job was actually pending")

        # _release_right() is on_close()'s last call before root.destroy()
        # -- hooking it is the last point "after info" can still be
        # queried at all, proving the cancellation happened strictly
        # before destroy(), not just "eventually".
        original_release = self.ui._release_right
        checked = []

        def patched_release():
            original_release()
            checked.append(self.root.tk.call("after", "info"))

        self.ui._release_right = patched_release
        try:
            self.ui.on_close()
        finally:
            self.ui._release_right = original_release
        self.assertEqual(len(checked), 1, "the patched _release_right never ran")
        self.assertNotIn(job_id, checked[0],
                         "on_close() left the startup idle job scheduled")

        try:
            self.root.update()   # give the stale job a turn, if it survived
        except tk.TclError:
            pass
        self._assert_no_callback_exceptions()
        self.ui = None   # already closed -- tearDown must not double-close it

    def test_maybe_offer_log_report_swallows_a_tclerror_from_a_torn_down_root(self):
        # Belt-and-braces half of round 3's fix: even though on_close() now
        # cancels the startup idle job before it can fire against a torn-
        # down root (the test above), _maybe_offer_log_report() itself
        # must not let a stray TclError from _show_update_log_dialog()
        # become an uncaught callback exception -- Tk's cancel guarantees
        # around root.destroy() are not being trusted as airtight on every
        # platform. Exercised directly, not by trying to win a real
        # destroy-timing race.
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        self.assertIsNotNone(self.ui._log_dialog)
        self.ui._on_log_dismiss()   # close it, so the next call starts fresh
        self.root.update()
        # A fresh log, so update_log_status() is not "ok" and
        # _maybe_offer_log_report() actually reaches the guarded call
        # below rather than returning before it.
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")

        original_show = self.ui._show_update_log_dialog
        def raise_tclerror(*a, **k):
            raise tk.TclError("bad window path name \".!toplevel.!frame\"")
        self.ui._show_update_log_dialog = raise_tclerror
        try:
            self.ui._maybe_offer_log_report()   # must not raise
        finally:
            self.ui._show_update_log_dialog = original_show
        self._assert_no_callback_exceptions()

    def test_no_dialog_when_no_log_exists(self):
        self._build()
        self.assertIsNone(self.ui._log_dialog)

    def test_no_dialog_for_a_done_log_with_no_version_field(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n"
                        "2026-01-01 00:00:01 done\n")
        self._build()
        self.assertIsNone(self.ui._log_dialog)

    def test_no_dialog_for_a_done_log_with_a_matching_version(self):
        self._write_log(
            f'2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c version="v{app.__version__}"\n'
            "2026-01-01 00:00:01 done\n")
        self._build()
        self.assertIsNone(self.ui._log_dialog)

    def test_dialog_appears_for_an_incomplete_log(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n"
                        "2026-01-01 00:00:01 wait finished after 1 iterations\n")
        self._build()
        self.assertIsNotNone(self.ui._log_dialog)
        self.assertEqual(self.ui._log_dialog.title(), "Update failed")

    def test_dialog_appears_for_a_wrong_version_log(self):
        self._write_log(
            '2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c version="v0.0.1"\n'
            "2026-01-01 00:00:01 done\n")
        self._build()
        self.assertIsNotNone(self.ui._log_dialog)

    def test_escape_dismisses_and_marks_the_log_reported(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        # Under Xvfb (no window manager) a freshly created Toplevel never
        # actually owns X input focus, so a generated <Escape> has nothing
        # to route to without this -- same one-time focus_force() precedent
        # UITestCase.setUp() already uses for the main window.
        self.ui._log_dialog.focus_force()
        self.root.update()
        self.ui._log_dialog.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(self.ui._log_dialog)
        self.assertFalse(os.path.exists(self.log_path))
        self.assertTrue(os.path.exists(self.log_path + ".reported"))

    def test_dismissed_log_does_not_reappear_on_a_later_launch(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        self.ui._on_log_dismiss()
        self.root.update()
        self.ui.on_close()
        self.ui = None       # already closed -- tearDown must not double-close it

        root2 = tk.Tk()
        self._capture_callback_exceptions(root2)
        ui2 = app.AfkAutoclicker(root2, store=app.Store(self.config))
        root2.update()
        try:
            self.assertIsNone(ui2._log_dialog)
        finally:
            try:
                ui2.on_close()
            except tk.TclError:
                pass
        self._assert_no_callback_exceptions()

    def test_checkbox_toggles_redaction_in_the_preview_live(self):
        home = os.path.expanduser("~")
        self._write_log(
            f'2026-01-01 00:00:00 start pid=1 staged="{home}/x" target="{home}/y" '
            'relaunch="c" version="v0.7.0"\n'
            "2026-01-01 00:00:01 copy exit code 1\n")
        self._build()
        ctx = self.ui._log_dialog_ctx

        def preview_text():
            return ctx["preview"].get("1.0", "end")

        # Unchecked by default -> redacted by default.
        self.assertNotIn(home, preview_text())
        self.assertIn("~/x", preview_text())

        ctx["show_paths_var"].set(True)
        self.root.update()
        self.assertIn(f"{home}/x", preview_text())

        ctx["show_paths_var"].set(False)
        self.root.update()
        self.assertNotIn(home, preview_text())

    def test_send_opens_the_browser_with_the_redacted_preview_and_marks_reported(self):
        home = os.path.expanduser("~")
        self._write_log(
            f'2026-01-01 00:00:00 start pid=1 staged="{home}/x" target="{home}/y" '
            'relaunch="c" version="v0.7.0"\n'
            "2026-01-01 00:00:01 copy exit code 1\n")
        self._build()
        ctx = self.ui._log_dialog_ctx
        # "end-1c", not "end": tk.Text.get() always appends one implicit
        # trailing newline beyond whatever was actually inserted.
        preview_text = ctx["preview"].get("1.0", "end-1c")

        calls = []
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: calls.append(url) or True
        try:
            ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open

        self.assertEqual(len(calls), 1)
        url = calls[0]
        self.assertLessEqual(len(url), 2000)
        self.assertNotIn(home, url, "the raw home directory leaked into the sent URL")

        query = url.split("?", 1)[1]
        params = dict(pair.split("=", 1) for pair in query.split("&"))
        decoded_title = urllib.parse.unquote_plus(params["title"])
        decoded_body = urllib.parse.unquote_plus(params["body"])
        self.assertEqual(f"{decoded_title}\n\n{decoded_body}", preview_text)

        self.assertIsNone(self.ui._log_dialog)
        self.assertTrue(os.path.exists(self.log_path + ".reported"))

    def test_send_shows_the_fallback_when_the_browser_cannot_open(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        ctx = self.ui._log_dialog_ctx
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: False
        try:
            ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open

        self.assertIsNotNone(self.ui._log_dialog, "the dialog must stay open on failure")
        self.assertIn("url", ctx)
        self.assertEqual(ctx["fallback_entry"].get(), ctx["url"])
        self.assertFalse(os.path.exists(self.log_path + ".reported"))

    def test_send_shows_the_fallback_when_the_browser_raises(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        ctx = self.ui._log_dialog_ctx
        orig_open = app.webbrowser.open

        def _raise(_url):
            raise RuntimeError("no browser controller")
        app.webbrowser.open = _raise
        try:
            ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open

        self.assertIsNotNone(self.ui._log_dialog)
        self.assertIn("copy_button", ctx)
        self.assertFalse(os.path.exists(self.log_path + ".reported"))

    def test_copy_link_copies_the_fallback_url_to_the_clipboard(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        ctx = self.ui._log_dialog_ctx
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: False
        try:
            ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
            ctx["copy_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open
        self.assertEqual(self.root.clipboard_get(), ctx["url"])

    def test_open_log_folder_does_not_mark_the_log_reported(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        calls = []
        orig_popen = app.subprocess.Popen
        had_startfile = hasattr(app.os, "startfile")
        orig_startfile = getattr(app.os, "startfile", None)
        app.subprocess.Popen = lambda *a, **k: calls.append(("popen",) + a)
        app.os.startfile = lambda path: calls.append(("startfile", path))
        try:
            ctx = self.ui._log_dialog_ctx
            ctx["open_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.subprocess.Popen = orig_popen
            if had_startfile:
                app.os.startfile = orig_startfile
            else:
                del app.os.startfile

        self.assertTrue(calls, "no file-manager call was made")
        self.assertFalse(os.path.exists(self.log_path + ".reported"))
        self.assertIsNotNone(self.ui._log_dialog)

        # The same dialog session can still Dismiss afterward.
        self.ui._on_log_dismiss()
        self.root.update()
        self.assertTrue(os.path.exists(self.log_path + ".reported"))

    # ---------- round 2 (test-review.md): survives a theme/scale rebuild ----------

    def test_appearance_change_preserves_the_open_dialog_and_checkbox_state(self):
        # docs/test-review.md round 2 Defect 1: _rebuild_ui()'s teardown
        # loop destroys every child of root, including this dialog -- a
        # live repro of Settings -> Appearance (or an OS dark/light switch
        # while the app follows "system") while the dialog is still open.
        home = os.path.expanduser("~")
        self._write_log(
            f'2026-01-01 00:00:00 start pid=1 staged="{home}/x" target="{home}/y" '
            'relaunch="c" version="v0.7.0"\n'
            "2026-01-01 00:00:01 copy exit code 1\n")
        self._build()
        old_dialog = self.ui._log_dialog
        old_ctx = self.ui._log_dialog_ctx
        old_ctx["show_paths_var"].set(True)
        self.root.update()

        self.ui._apply_appearance("light")
        self.root.update()

        new_dialog = self.ui._log_dialog
        new_ctx = self.ui._log_dialog_ctx
        self.assertIsNotNone(new_dialog, "the dialog must still exist after a rebuild")
        self.assertEqual(new_dialog.winfo_exists(), 1, "must be a live widget, not a stale reference")
        self.assertIsNot(new_ctx, old_ctx, "a fresh dialog/ctx must have been rebuilt")
        self.assertNotEqual(old_dialog, new_dialog)
        toplevels = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(toplevels), 1,
                         "exactly one dialog Toplevel must exist after the rebuild, "
                         "not a leaked duplicate of the old, destroyed one")
        self.assertTrue(new_ctx["show_paths_var"].get(),
                        "the checked state must survive the rebuild")
        self.assertIn(f"{home}/x", new_ctx["preview"].get("1.0", "end-1c"),
                     "the preview must still show full paths after the rebuild")

        # Toggling the (new, live) checkbox post-rebuild must not raise.
        new_ctx["show_paths_var"].set(False)
        self.root.update()
        self.assertNotIn(home, new_ctx["preview"].get("1.0", "end-1c"))

        # Send still works post-rebuild.
        calls = []
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: calls.append(url) or True
        try:
            new_ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open
        self.assertEqual(len(calls), 1)
        self.assertIsNone(self.ui._log_dialog)
        self.assertTrue(os.path.exists(self.log_path + ".reported"))

    def test_a_stray_reference_to_the_pre_rebuild_ctx_does_not_raise(self):
        # docs/test-review.md round 2 Defect 1's exact repro technique
        # (theme_change_probe2.py): something that kept its own reference
        # to the *pre-rebuild* ctx/Variable (a stale local, a leftover
        # closure) must not raise when it later touches that reference --
        # the whole point of clearing that Variable's traces before the
        # widgets they touch are destroyed (_close_log_dialog()'s own
        # docstring, the ac-27 "trace outlives its widgets" lesson).
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        stale_ctx = self.ui._log_dialog_ctx   # deliberately held past the rebuild

        self.ui._apply_appearance("light")
        self.root.update()

        # The pre-rebuild ToggleCheckbox's own repaint trace is still
        # registered on this stale Variable unless it was explicitly
        # cleared -- setting it must not raise into the now-destroyed
        # widget it used to repaint.
        stale_ctx["show_paths_var"].set(True)
        self.root.update()
        self._assert_no_callback_exceptions()

    def test_ui_scale_change_preserves_the_open_dialog_and_checkbox_state(self):
        home = os.path.expanduser("~")
        self._write_log(
            f'2026-01-01 00:00:00 start pid=1 staged="{home}/x" target="{home}/y" '
            'relaunch="c" version="v0.7.0"\n'
            "2026-01-01 00:00:01 copy exit code 1\n")
        self._build()
        old_ctx = self.ui._log_dialog_ctx
        old_ctx["show_paths_var"].set(True)
        self.root.update()

        self.ui._apply_ui_scale("130")
        self.root.update()

        new_dialog = self.ui._log_dialog
        new_ctx = self.ui._log_dialog_ctx
        self.assertIsNotNone(new_dialog)
        self.assertEqual(new_dialog.winfo_exists(), 1)
        self.assertTrue(new_ctx["show_paths_var"].get())
        self.assertIn(f"{home}/x", new_ctx["preview"].get("1.0", "end-1c"))

    def test_appearance_change_preserves_the_fallback_state_and_url(self):
        self._write_log("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        self._build()
        ctx = self.ui._log_dialog_ctx
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: False
        try:
            ctx["send_button"].event_generate("<Button-1>")
            self.root.update()
        finally:
            app.webbrowser.open = orig_open
        url_before = ctx["url"]
        self.assertFalse(os.path.exists(self.log_path + ".reported"))

        self.ui._apply_appearance("light")
        self.root.update()

        new_dialog = self.ui._log_dialog
        new_ctx = self.ui._log_dialog_ctx
        self.assertIsNotNone(new_dialog, "the dialog must survive the rebuild in the fallback state")
        self.assertEqual(new_dialog.winfo_exists(), 1)
        self.assertEqual(new_ctx.get("url"), url_before, "the fallback URL must be replayed unchanged")
        self.assertIn("fallback_entry", new_ctx, "the fallback layout itself must be replayed")
        self.assertEqual(new_ctx["fallback_entry"].get(), url_before)
        # Never re-run detection / re-trigger "ask once": still not renamed.
        self.assertFalse(os.path.exists(self.log_path + ".reported"))

        # Copy link still works post-rebuild.
        new_ctx["copy_button"].event_generate("<Button-1>")
        self.root.update()
        self.assertEqual(self.root.clipboard_get(), url_before)

    # ---------- round 2 (test-review.md): fallback fits at every scale ----------

    def _assert_fallback_not_clipped(self, ui_scale):
        workdir = tempfile.mkdtemp()
        config = os.path.join(workdir, "settings.json")
        log_path = os.path.join(workdir, "update.log")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n")
        store = app.Store(config)
        store.data["ui_scale"] = ui_scale
        root = tk.Tk()
        self._capture_callback_exceptions(root)
        ui = app.AfkAutoclicker(root, store=store)
        root.update()
        ctx = ui._log_dialog_ctx
        orig_open = app.webbrowser.open
        app.webbrowser.open = lambda url: False
        try:
            ctx["send_button"].event_generate("<Button-1>")
            root.update()
        finally:
            app.webbrowser.open = orig_open

        dialog = ui._log_dialog
        dialog.update_idletasks()
        # "genuinely mapped first": an unmapped/not-yet-drawn widget's
        # winfo_height() is unreliable (and differs across platforms) --
        # this dialog is built, packed and update_idletasks()-flushed by
        # this point, so winfo_ismapped() must already be true.
        self.assertTrue(dialog.winfo_ismapped(), "dialog must be mapped before measuring geometry")
        # A squeezed (clipped) widget is allocated LESS than it asked for
        # -- pack() does not let a child overflow past its container's
        # edge, it silently shrinks it instead (confirmed against
        # docs/history's round-1 code: winfo_height() 25px vs
        # winfo_reqheight() 35px for this exact button at 100% scale).
        # Comparing root-relative bottom-edge coordinates instead would
        # miss this: the squeezed widget's own reported bottom edge never
        # exceeds the window's, only its *content* renders truncated.
        for widget in (ctx["fallback_dismiss_button"], ctx["copy_button"], ctx["fallback_row"]):
            self.assertGreaterEqual(
                widget.winfo_height(), widget.winfo_reqheight(),
                f"fallback content clipped at ui_scale={ui_scale}: "
                f"{widget.winfo_height()}px allocated, {widget.winfo_reqheight()}px needed")
        try:
            ui.on_close()
        except tk.TclError:
            pass
        self._assert_no_callback_exceptions()

    def test_fallback_is_not_clipped_at_90_percent(self):
        self._assert_fallback_not_clipped("90")

    def test_fallback_is_not_clipped_at_100_percent(self):
        self._assert_fallback_not_clipped("100")

    def test_fallback_is_not_clipped_at_115_percent(self):
        self._assert_fallback_not_clipped("115")

    def test_fallback_is_not_clipped_at_130_percent(self):
        self._assert_fallback_not_clipped("130")


def tearDownModule():
    # See GcAutomaticCollectionStaysDisabled above (G#31/GH#54). Checked
    # once per module run, not per-test: the symptom this counts is
    # process-wide -- any test's worker thread can trip it, at any point in
    # the run -- not attributable to whichever test happens to be executing
    # when it fires, so there is no single test to attach this assertion to.
    count = context.MAIN_THREAD_UNRAISABLE_COUNT
    if count:
        raise AssertionError(
            f"{count} off-main-thread Variable.__del__ RuntimeError(s) "
            "('main thread is not in main loop') occurred during this run "
            "-- the G#27/GH#46 abort mechanism is back. See "
            "tests/context.py's gc.disable()/unraisablehook comment and "
            "docs/history/ac-27-r3-implementation.md's Round 3.")


if __name__ == "__main__":
    unittest.main()

"""The window: per-game settings, persistence, detection and the click loop."""
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

from .context import app, kb, needs_display, hotkey

if app is not None:
    import tkinter as tk


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
    def setUp(self):
        self.config = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.root = tk.Tk()
        self._capture_callback_exceptions(self.root)
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.settle()
        # Under Xvfb with no window manager, a freshly created tk.Tk() never
        # actually owns X input focus, so focus_set() alone produces no
        # <FocusIn>/<FocusOut> and focus_get() reads None no matter what.
        # This one-time focus_force() makes the toplevel genuinely own input
        # focus so every focus_set()-based assertion below observes something
        # -- the app itself keeps using focus_set(), never focus_force().
        self.root.focus_force()

    def tearDown(self):
        try:
            self.ui.on_close()
        except tk.TclError:
            pass
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




class CorruptConfig(UITestCase):
    def test_damaged_file_is_not_fatal(self):
        with open(self.config, "w") as fh:
            fh.write("{ this is not json")
        self.assertIsInstance(app.Store(self.config).data.get("games"), dict)


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
    # 0.2001 s over 16 consecutive runs. Whether the click loop is genuinely
    # slow on macOS or the runner cannot schedule a Python thread that tightly
    # is unresolved -- and guessing would mean loosening the bound until it
    # stops asking the question. Skipped there with the investigation tracked,
    # rather than weakened everywhere. See issue #6.
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
                {"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
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
                {"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
            self.ui._pending = ("v9.9.9", release["assets"][1], release)
            self.ui._install_worker()
            self._drain()
        finally:
            app.fetch_checksums, app.download_and_stage = original_fetch, original_stage
        shown = self._button_text().lower()
        self.assertIn("checksum", shown,
                       f"status line {shown!r} does not read as a checksum failure")
        self.assertTrue(self.ui.update_button._enabled, "the button was left disabled after a refusal")


class NumBoxFocus(UITestCase):
    """A field keeps eating keystrokes until something explicitly drops focus."""

    def focus_and_settle(self, numbox):
        numbox.entry.focus_set()
        self.root.update()
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
    def test_both_axes_are_resizable(self):
        self.assertEqual(self.root.resizable(), (1, 1))

    def test_minsize_matches_todays_default_size(self):
        s = self.ui.s
        expected = (int((app.SIDEBAR_W + 1 + app.CONTENT_W) * s), int(690 * s))
        self.assertEqual(self.root.minsize(), expected)

    def test_growing_the_window_expands_content_not_the_sidebar(self):
        content_before = self.ui.content.winfo_width()
        side_before = self.ui.side.winfo_width()
        self.root.geometry("1000x900")
        self.root.update()
        self.assertGreater(self.ui.content.winfo_width(), content_before)
        self.assertEqual(self.ui.side.winfo_width(), side_before)

    def test_shrinking_below_minsize_is_clamped(self):
        self.root.geometry("50x50")
        self.root.update()
        minw, minh = self.root.minsize()
        self.assertGreaterEqual(self.root.winfo_width(), minw)
        self.assertGreaterEqual(self.root.winfo_height(), minh)


class RowValueColumn(UITestCase):
    """Row's fixed-width label column (docs/history/ac-24-f1-spec.md):
    the control always starts at the same offset from the row's left edge,
    regardless of how wide a stretched card gets, so the label-to-control
    gap does not grow the way it did with the old pack-based Row -- extra
    width becomes trailing margin after the control instead."""

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
        self.assertEqual(control.winfo_x(), before)

    def test_extra_width_becomes_trailing_margin_not_a_growing_gap(self):
        control = self.ui.click_ms.master
        card = control.master.master
        self.root.geometry("900x760")
        self.root.update()
        self.assertLess(control.winfo_x() + control.winfo_width(),
                        card.winfo_width())

    def test_ui_scale_row_never_overflows_its_card_at_any_scale_step(self):
        # Constant-level check first (docs/history/ac-24-f1-spec.md's fit-check
        # argument): the widest explicit control in the file (width=220,
        # the "UI scale" row) plus the fixed label column must fit inside
        # CARD_INNER_W, independent of any rendering: 152 + 220 = 372 <= 396.
        self.assertLessEqual(
            app.ROW_LABEL_W + app.ROW_LABEL_GAP + 220, app.CARD_INNER_W)
        for value in ("90", "100", "115", "130"):
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
        self.assertLessEqual(
            hint.winfo_rootx() + hint.winfo_width(),
            self.ui.jitter_ms.winfo_rootx())


@needs_display
class Selftest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertEqual(app.selftest(), 0)




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
        data = json.load(open(self.config))
        data["hotkey"] = {"keys": "garbage"}
        json.dump(data, open(self.config, "w"))
        self.root = tk.Tk()
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.assertIsNone(self.ui.registered_hotkey)

    def test_nothing_is_saved_when_no_hotkey_was_applied(self):
        self.ui.on_close()
        self.assertIsNone(json.load(open(self.config)).get("hotkey"))

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
            self.assertEqual(self.ui.registered_hotkey.label(), "Ctrl + F6")
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
        # before the card's own CARD_R padding starts -- a control sized off
        # CONTENT_W alone, skipping that body inset, overruns the card.
        self.assertEqual(app.CARD_INNER_W,
                         app.CONTENT_W - 2 * app.CONTENT_PAD - 2 * app.CARD_R)
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
class PillAndCardRadii(unittest.TestCase):
    """Buttons/segmented/status become true pills; cards/rows stay at 12px."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.update()
        self.recorded = []
        self._orig_round_rect = app.round_rect

        def _record(cv, x1, y1, x2, y2, r, **kw):
            self.recorded.append(r)
            return self._orig_round_rect(cv, x1, y1, x2, y2, r, **kw)

        app.round_rect = _record

    def tearDown(self):
        app.round_rect = self._orig_round_rect
        self.root.destroy()

    def test_button_shape_uses_pill_radius(self):
        app.Button(self.root, "Go", lambda: None, 1.0)
        self.assertEqual(self.recorded, [app.PILL_R * 1.0])

    def test_segmented_track_and_selection_pill_use_pill_radius(self):
        var = tk.StringVar(value="a")
        app.Segmented(self.root, [("a", "A"), ("b", "B")], var, 1.0)
        # Two round_rect calls at construction: the outer track, then the
        # selection pill -- both must move together or the pill's shape
        # "jumps" when the selected segment changes.
        self.assertEqual(self.recorded, [app.PILL_R * 1.0, app.PILL_R * 1.0])

    def test_pill_pts_stays_in_sync_with_the_constructors_radius(self):
        # _pill_pts recomputes the selection pill's corners on every value
        # change without going through round_rect -- exercised directly so a
        # regression there (still hard-coded at 7) is caught even though it
        # never calls the monkeypatched round_rect above.
        var = tk.StringVar(value="a")
        seg = app.Segmented(self.root, [("a", "A"), ("b", "B")], var, 1.0)
        pts = seg._pill_pts(2, 2, 200, 32)
        half_h = (32 - 2) / 2
        self.assertEqual(pts[0], 2 + half_h, "corner radius is not a true pill")

    def test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation(self):
        # The old construction fed 12 corner *control* points -- including
        # the exact, sharp (x2, y1) corner itself -- to a smoothed spline,
        # which only ever approaches the radius it is asked for and, at
        # r = h/2, still has that sharp point sitting at distance r*sqrt(2)
        # from the nearest end-cap centre, not r. This checks the actual
        # points fed to the canvas, so it fails against that old shape even
        # though its clamped `r` parameter is the correct PILL_R value.
        cv = tk.Canvas(self.root)
        x1, y1, x2, y2 = 0, 0, 60, 32
        r = (y2 - y1) / 2   # a true pill: radius is exactly half the height
        item = app.round_rect(cv, x1, y1, x2, y2, r, fill="black")

        self.assertEqual(cv.itemcget(item, "smooth"), "0",
                         "a smoothed polygon never reaches the radius it is given")

        coords = cv.coords(item)
        pts = list(zip(coords[0::2], coords[1::2]))
        left_c, right_c = (x1 + r, (y1 + y2) / 2), (x2 - r, (y1 + y2) / 2)
        for px, py in pts:
            d_left = ((px - left_c[0]) ** 2 + (py - left_c[1]) ** 2) ** 0.5
            d_right = ((px - right_c[0]) ** 2 + (py - right_c[1]) ** 2) ** 0.5
            self.assertAlmostEqual(min(d_left, d_right), r, delta=1.0,
                                   msg=f"point {(px, py)} is not on either end-cap")

        self.assertIn((x2, (y1 + y2) / 2), pts,
                      "right edge midpoint is not on the outline")

    def test_segmented_selection_pill_matches_round_rects_true_capsule(self):
        # _pill_pts feeds coords() on the very item round_rect created, so
        # its geometry has to stay a true capsule too, not just its own r.
        var = tk.StringVar(value="a")
        seg = app.Segmented(self.root, [("a", "A"), ("b", "B")], var, 1.0)
        x1, y1, x2, y2 = 2, 2, 200, 32
        r = min(app.PILL_R, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = list(zip(*[iter(seg._pill_pts(x1, y1, x2, y2))] * 2))
        left_c, right_c = (x1 + r, (y1 + y2) / 2), (x2 - r, (y1 + y2) / 2)
        for px, py in pts:
            d_left = ((px - left_c[0]) ** 2 + (py - left_c[1]) ** 2) ** 0.5
            d_right = ((px - right_c[0]) ** 2 + (py - right_c[1]) ** 2) ** 0.5
            self.assertAlmostEqual(min(d_left, d_right), r, delta=1.0,
                                   msg=f"point {(px, py)} is not on either end-cap")

    def test_status_pill_shape_uses_pill_radius(self):
        app.StatusPill(self.root, 1.0)
        self.assertEqual(self.recorded, [app.PILL_R * 1.0])

    def test_game_item_shape_uses_card_radius_not_pill_radius(self):
        app.GameItem(self.root, {"id": "x", "name": "X"}, lambda gid: None, 1.0)
        self.assertEqual(self.recorded, [app.CARD_R * 1.0])

    def test_card_shell_shape_uses_card_radius(self):
        app.card(self.root, 1.0)
        self.assertIn(app.CARD_R * 1.0, self.recorded)
        self.assertNotIn(app.PILL_R * 1.0, self.recorded)


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
    """Every canvas that draws a round_rect shape must paint its parent's own
    background outside the rounded shape -- otherwise the shape's corners
    sit on a mismatched square (docs/history/ac-17-f1-design.md item 3). round_rect is the
    only thing in the app that calls create_polygon, so any canvas holding a
    polygon item is one of these and gets checked, with no per-widget-class
    list to keep in sync by hand."""

    def _rounded_canvases(self, widget):
        found = []
        if isinstance(widget, tk.Canvas):
            if any(widget.type(item) == "polygon" for item in widget.find_all()):
                found.append(widget)
        for child in widget.winfo_children():
            found.extend(self._rounded_canvases(child))
        return found

    def test_every_rounded_canvas_matches_its_parents_background(self):
        canvases = self._rounded_canvases(self.root)
        self.assertTrue(canvases, "setup failed to find any rounded canvas")
        mismatches = [(str(cv), cv.cget("bg"), cv.master.cget("bg"))
                     for cv in canvases if cv.cget("bg") != cv.master.cget("bg")]
        self.assertEqual(mismatches, [],
            "canvas bg must match its parent's bg, or the area outside the "
            "rounded shape paints a visible mismatched rectangle")


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
        try:
            self.ui.on_close()
        except tk.TclError:
            pass
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

    def test_a_fresh_store_defaults_to_100(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.assertEqual(app.Store(path).data["ui_scale"], "100")

    def test_known_values_round_trip(self):
        for value in ("90", "100", "115", "130"):
            with self.subTest(value=value):
                path = self._write({"ui_scale": value})
                self.assertEqual(app.Store(path).data["ui_scale"], value)

    def test_garbage_values_fall_back_to_100(self):
        for value in ("120", None, 42):
            with self.subTest(value=value):
                path = self._write({"ui_scale": value})
                self.assertEqual(app.Store(path).data["ui_scale"], "100")

    def test_a_missing_ui_scale_key_defaults_to_100(self):
        path = self._write({"games": {}, "hotkey": None, "selected": None})
        self.assertEqual(app.Store(path).data["ui_scale"], "100")

    def test_a_garbage_on_disk_value_resolves_to_100_end_to_end(self):
        # Same technique as AppearanceStore.test_a_missing_appearance_key_
        # defaults_to_system -- write directly into the test's own
        # settings.json -- but goes one step further, all the way through a
        # fresh AfkAutoclicker (self.restart()), per docs/history/ac-17-f4-spec.md's
        # acceptance criterion: a garbage stored "ui_scale" must sanitize to
        # "100" AND self.ui.s must equal self.ui._dpi_s (the "100" factor is
        # a no-op 1.0 multiplier).
        with open(self.config, "w") as fh:
            json.dump({"games": {}, "hotkey": None, "selected": None,
                       "ui_scale": "120"}, fh)
        ui = self.restart()
        self.assertEqual(ui.store.data["ui_scale"], "100")
        self.assertEqual(ui.s, ui._dpi_s)


class UIScale(UITestCase):
    """The Settings page's second Appearance-card Row (docs/history/ac-17-f4-spec.md, story
    #17 Feature 4): self.s becomes DPI x the chosen step, applied through
    the same in-place rebuild mechanism Feature 3 built for Appearance --
    structurally parallel to AppearanceThemeSwitch/WindowResize above."""

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
                expected = (int((app.SIDEBAR_W + 1 + app.CONTENT_W) * self.ui.s),
                           int(690 * self.ui.s))
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
        max_s = self.ui._dpi_s * app.UI_SCALE_FACTORS["130"]
        min_w = int((app.SIDEBAR_W + 1 + app.CONTENT_W) * max_s)
        min_h = int(690 * max_s)
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
        # root.update() between them, then one pump. This control has 4
        # options, not Theme's 3, so seg_w divides by 4.
        self.ui._show_settings()
        self.root.update()
        seg = self._appearance_segment(self.ui.ui_scale_var)
        seg_w = seg.w / 4
        seg.event_generate("<Button-1>", x=int(seg_w * 1.5), y=int(seg.h / 2))  # "100%"
        seg.event_generate("<Button-1>", x=int(seg_w * 3.5), y=int(seg.h / 2))  # "130%"
        self.root.update()
        self.assertEqual(self.ui.ui_scale_var.get(), "130")
        self.assertEqual(self.ui.s, self.ui._dpi_s * app.UI_SCALE_FACTORS["130"])


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
            "checksum: not in SHA256SUMS: AFK-Farm-Clicker-linux-x86_64.tar.gz"[:40])
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
            {"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz", "browser_download_url": "x"}]}
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
                  "assets": [{"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz"}]}
        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = lambda timeout=10: release
        app.is_newer = lambda tag, current=app.__version__: True
        app.pick_asset = lambda rel: rel["assets"][0]
        try:
            worker = threading.Thread(target=self.ui._check_worker, daemon=True)
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
                  "assets": [{"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz"}]}
        original_latest, original_is_newer, original_pick = \
            app.latest_release, app.is_newer, app.pick_asset
        app.latest_release = lambda timeout=10: release
        app.is_newer = lambda tag, current=app.__version__: True
        app.pick_asset = lambda rel: rel["assets"][0]
        try:
            worker = threading.Thread(target=self.ui._check_worker, daemon=True)
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

        def patched_card(parent, s):
            result = original_card(parent, s)
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
        old_seen = self.ui._seen_running   # already set by setUp()'s settle()
        target = {"minecraft"}
        self.assertNotEqual(old_seen, target,
                            "test needs a genuinely different value to prove "
                            "the queued call actually landed, not that "
                            "_seen_running just happened to already match")
        self.ui._ui(self.ui._mark_running, target)
        self.ui._rebuild_ui()
        self.ui._drain_ui()
        self.assertEqual(
            self.ui._seen_running, target,
            "a queued _mark_running() scan result should survive a rebuild, "
            "not be silently dropped by the old _ui_queue swap")


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


if __name__ == "__main__":
    unittest.main()

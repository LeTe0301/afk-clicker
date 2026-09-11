"""The window: per-game settings, persistence, detection and the click loop."""
import json
import os
import threading
import tempfile
import time
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


@needs_display
class UITestCase(unittest.TestCase):
    def setUp(self):
        self.config = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.root = tk.Tk()
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

    def settle(self, timeout=5.0):
        """
        Wait for the startup game scan to land.

        _poll_games runs on a thread during construction and hands its result
        to the UI queue; _drain_ui's 40 ms timer then delivers it inside
        whatever root.update() happens to run next -- including one inside a
        test, after that test has set the state it is about to assert on.
        Pinning _seen_running addressed a different assertion and left this.

        _seen_running only exists once _mark_running has run, so it is the
        signal to wait for rather than a sleep long enough to hope.
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
        self.assertEqual(self.ui.click_ms.var.get(), "510")
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
        self.assertEqual(ui.click_ms.var.get(), "510")


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

if __name__ == "__main__":
    unittest.main()

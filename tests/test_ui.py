"""The window: per-game settings, persistence, detection and the click loop."""
import json
import os
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

    def tearDown(self):
        try:
            self.ui.on_close()
        except tk.TclError:
            pass

    def pump(self, seconds):
        """Run Tk's loop -- after() work, including the snapshot, only runs here."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

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
        self.ui._mark_running({"minecraft"})
        self.root.update()
        self.assertTrue(self.ui.items["minecraft"].running)
        self.assertFalse(self.ui.items["global"].running)
        self.assertEqual(self.ui.current, "minecraft")
        self.assertEqual(self.ui.game_state.cget("text"), "running")

    def test_a_hand_picked_profile_is_not_overridden(self):
        # Following the game once is helpful; doing it every five seconds
        # would fight the user.
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

    def test_interval_is_honoured(self):
        self.ui.button_name.set("left")
        self.ui.click_ms.var.set("200")
        self.ui.jitter_ms.var.set("0")
        gaps = self._gaps(1.3)
        self.assertLess(abs(sum(gaps) / len(gaps) - 0.2), 0.08)

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


@needs_display
class Selftest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertEqual(app.selftest(), 0)


if __name__ == "__main__":
    unittest.main()

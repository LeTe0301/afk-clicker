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
class CardShell(unittest.TestCase):
    """card() becomes a borderless canvas hosting the returned Frame."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("500x400")
        self.parent = tk.Frame(self.root, bg=app.BG)
        self.parent.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

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
    sit on a mismatched square (docs/design.md item 3). round_rect is the
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


if __name__ == "__main__":
    unittest.main()

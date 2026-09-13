"""
End-to-end hotkey firing, by synthesising real key presses.

Slow -- each case binds a listener, presses keys and waits. Excluded from the
pull-request suite and run before a release; set AFK_SLOW_TESTS=1 to include it.

Harness caveat, measured: XTEST under Xvfb delivers every synthetic press *and*
release exactly twice. Asserting an exact fire count across several presses
would measure that, not the code, so these assert properties instead.
"""
import itertools
import os
import threading
import time
import unittest

from .context import app, kb, needs_display, hotkey, record

SLOW = os.environ.get("AFK_SLOW_TESTS") == "1"
slow_only = unittest.skipUnless(SLOW, "set AFK_SLOW_TESTS=1 to run")

MODKEY = {"ctrl": kb.Key.ctrl, "alt": kb.Key.alt, "shift": kb.Key.shift} if kb else {}


@needs_display
@slow_only
class Firing(unittest.TestCase):
    def fires(self, hk, mods, keys, timeout=1.2):
        hits = []
        watcher = app.HotkeyWatcher(hk, lambda: hits.append(1))
        watcher.start()
        physical = [MODKEY[m] for m in sorted(mods)]
        try:
            for mod in physical:
                kb.Controller().press(mod)
            for key in keys:
                kb.Controller().press(key)
            time.sleep(0.12)
            for key in reversed(keys):
                kb.Controller().release(key)
            for mod in reversed(physical):
                kb.Controller().release(mod)
            time.sleep(timeout)
        finally:
            watcher.stop()
        return len(hits)

    KEYSETS = [
        [kb.Key.f6] if kb else [],
        [kb.KeyCode.from_char("h")] if kb else [],
        [kb.KeyCode.from_char("+")] if kb else [],
        [kb.Key.f6, kb.Key.f7] if kb else [],
        [kb.Key.f6, kb.Key.f7, kb.Key.f8] if kb else [],
        [kb.KeyCode.from_char("ä"), kb.KeyCode.from_char("ö")] if kb else [],
    ]
    MODSETS = [set(), {"ctrl"}, {"shift"}, {"ctrl", "shift"}, {"ctrl", "alt", "shift"}]

    def test_every_chord_fires_once(self):
        for keys in self.KEYSETS:
            for mods in self.MODSETS:
                hk = hotkey(mods, keys)
                with self.subTest(chord=hk.label()):
                    self.assertEqual(self.fires(hk, mods, keys), 1)

    def test_near_misses_stay_silent(self):
        for keys in [k for k in self.KEYSETS if len(k) >= 2]:
            hk = hotkey(set(), keys)
            with self.subTest(chord=hk.label(), case="subset"):
                self.assertEqual(self.fires(hk, set(), keys[:-1]), 0)
            with self.subTest(chord=hk.label(), case="stray modifier"):
                self.assertEqual(self.fires(hk, {"ctrl"}, keys), 0)

    def test_order_does_not_matter(self):
        for keys in [k for k in self.KEYSETS if len(k) >= 2]:
            hk = hotkey(set(), keys)
            for permutation in itertools.permutations(keys):
                with self.subTest(chord=hk.label()):
                    self.assertEqual(self.fires(hk, set(), list(permutation)), 1)

    def test_holding_does_not_repeat(self):
        """
        A fixed sleep between each synthetic action assumes the watcher has
        seen everything about the previous action by the time it elapses.
        It hasn't, reliably: a Controller sharing this process with a
        Listener notifies it twice per key transition (see module
        docstring) -- once synchronously, once via the real X round trip --
        and under load the second copy can lag past a 0.5s sleep, landing
        after the *next* action instead of before it. A stray, delayed
        "press f7" arriving just after "release f7" (while f6 is still
        down) re-completes the chord and fires it again, which looks like
        the debounce/re-arm logic is broken when it is actually a race in
        how the test drives it. Waiting for an independent listener to go
        quiet between actions, instead of sleeping a fixed duration, lets
        both copies of one action land before the next one is sent.
        """
        hk = hotkey(set(), [kb.Key.f6, kb.Key.f7])
        hits = []
        watcher = app.HotkeyWatcher(hk, lambda: hits.append(1))

        quiet_since = [time.monotonic()]

        def mark(_key):
            quiet_since[0] = time.monotonic()

        probe = kb.Listener(on_press=mark, on_release=mark)
        probe.start()
        probe.wait()

        def settle(quiet=0.2, timeout=3.0):
            deadline = time.monotonic() + timeout
            while (time.monotonic() - quiet_since[0] < quiet
                   and time.monotonic() < deadline):
                time.sleep(0.02)

        watcher.start()
        controller = kb.Controller()
        try:
            controller.press(kb.Key.f6)
            controller.press(kb.Key.f7)
            settle()
            controller.press(kb.Key.f7)      # auto-repeat
            settle()
            controller.release(kb.Key.f7)
            settle()
            controller.release(kb.Key.f6)
            settle()
        finally:
            probe.stop()
            watcher.stop()
        self.assertEqual(len(hits), 1)

    def test_debounce_collapses_a_burst_but_not_deliberate_presses(self):
        hk = hotkey(set(), [kb.Key.f6, kb.Key.f7])
        controller = kb.Controller()

        def toggle_times(gap, count):
            hits = []
            watcher = app.HotkeyWatcher(hk, lambda: hits.append(1))
            watcher.start()
            for _ in range(count):
                controller.press(kb.Key.f6)
                controller.press(kb.Key.f7)
                controller.release(kb.Key.f7)
                controller.release(kb.Key.f6)
                time.sleep(gap)
            time.sleep(0.5)
            watcher.stop()
            return len(hits)

        self.assertLessEqual(toggle_times(0.05, 4), 2)     # inside the debounce
        self.assertGreaterEqual(toggle_times(0.45, 3), 3)  # clearly outside it


if __name__ == "__main__":
    unittest.main()

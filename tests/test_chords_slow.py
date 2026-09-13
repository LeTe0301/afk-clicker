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
        A fixed sleep between each synthetic action used to assume the
        watcher had seen everything about the previous action by the time
        it elapsed. It hadn't, reliably: waiting for an independent
        listener to go quiet between actions instead didn't hold up either
        -- widening that quiet gap past DEBOUNCE_S (needed so a broken
        re-arm isn't masked by debounce, see below) just as reliably let a
        *different* stray, delayed duplicate land after a later action and
        re-fire on unmodified, correct code (confirmed directly, repeatably,
        via instrumented runs). Chasing pynput's second, asynchronous copy
        of each transition (delivered on the listener's own background
        thread -- see the module docstring) with a bounded wait is not
        actually bounded; its lag is not reliably capped by any timeout
        short enough to keep this test fast.

        The fix is to stop waiting for that copy at all. pynput's *first*
        copy of a transition is delivered synchronously, in-process, before
        Controller.press()/release() returns: Controller._handle()
        (pynput/keyboard/_xorg.py) calls self._emit(...) right after
        talking to the X server, and NotifierMixin._emit()
        (pynput/_util/__init__.py) calls each registered Listener's
        on_press/on_release directly, in the calling thread. So `hits`
        already reflects HotkeyWatcher's reaction to a press by the time
        the call that sent it returns -- no waiting needed to observe it.

        The only genuinely time-dependent thing being tested is that a
        second matching press, sent while the chord is still held, doesn't
        re-fire -- and that only exercises the code path this test exists
        to catch (self.armed cleared after firing, not just debounce
        suppressing a too-soon repeat) if the gap since the first fire
        exceeds DEBOUNCE_S. DEBOUNCE_S is compared against
        time.monotonic(), not against anything a listener has observed, so
        a plain deterministic sleep is enough to guarantee that -- no
        listener involved, nothing to race.

        Never releasing before either assertion means armed cannot flip
        back True out of turn, so the delayed, asynchronous second copy of
        any of these presses is harmless whenever it eventually turns up:
        with armed already False, extra matching press events change
        nothing, in any order, on any thread.
        """
        hk = hotkey(set(), [kb.Key.f6, kb.Key.f7])
        hits = []
        watcher = app.HotkeyWatcher(hk, lambda: hits.append(1))
        watcher.start()
        controller = kb.Controller()
        try:
            controller.press(kb.Key.f6)
            controller.press(kb.Key.f7)          # fires synchronously
            self.assertEqual(len(hits), 1)

            # Deterministic wall-clock wait, not a listener wait: clears
            # DEBOUNCE_S so the next press exercises re-arm-on-fire rather
            # than being swallowed by debounce regardless of it.
            time.sleep(app.HotkeyWatcher.DEBOUNCE_S + 0.15)

            controller.press(kb.Key.f7)          # still held -- auto-repeat
            self.assertEqual(len(hits), 1)
        finally:
            controller.release(kb.Key.f7)
            controller.release(kb.Key.f6)
            watcher.stop()

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

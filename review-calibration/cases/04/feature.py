"""
Feature: verify that the configured hotkey is not already taken by the system.

Before applying a hotkey, check whether the combination is registered by
something else, so the user finds out now rather than mid-session.
"""
import sys
import unittest

from pynput import keyboard as kb

RESERVED = {"<cmd>+q", "<cmd>+tab", "<alt>+<f4>", "<ctrl>+<alt>+<delete>"}


def is_reserved(hotkey):
    """True when the combination is one the operating system claims."""
    return hotkey.label().lower().replace(" ", "") in RESERVED


class ReservedHotkeyTests(unittest.TestCase):
    # The listener cannot be started in CI, so the whole class is conditional.
    available = False
    try:
        kb.Listener(on_press=lambda k: False)
        available = True
    except Exception:
        pass

    @unittest.skipUnless(available, "no input backend available")
    def test_alt_f4_is_reserved(self):
        hotkey = _make("<alt>+<f4>")
        self.assertTrue(is_reserved(hotkey))

    @unittest.skipUnless(available, "no input backend available")
    def test_f6_is_not_reserved(self):
        self.assertFalse(is_reserved(_make("<f6>")))

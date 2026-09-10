"""
Feature: refuse to start clicking when no window has focus.

Clicking into the desktop does nothing useful and can drop items, so the loop
checks that something is focused before it begins.
"""
import os
import tempfile
import unittest


def focused_window_title(titles):
    """The frontmost title, or None when the desktop has focus."""
    return titles[0] if titles else None


def may_start(titles):
    return focused_window_title(titles) is not None


def session_log_path(name):
    """Where a session log is written. Kept beside the config, never in /."""
    base = os.path.join(tempfile.gettempdir(), "afk-clicker")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, name)


class FocusTests(unittest.TestCase):
    def test_no_focus_refuses(self):
        self.assertFalse(may_start([]))

    def test_focus_allows(self):
        self.assertTrue(may_start(["Minecraft 26.2"]))


class LogPathTests(unittest.TestCase):
    def setUp(self):
        self.name = "session.log"

    def test_log_is_not_written_to_the_root(self):
        path = session_log_path(self.name)
        parent = os.path.dirname(path)
        self.assertNotEqual(parent, os.sep)

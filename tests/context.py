"""
Shared setup for the test suite.

pynput resolves its backend at import time and raises without a display, so on
Linux the whole suite needs an X server -- CI runs it under xvfb-run. Importing
this module first also puts the project root on the path so the tests work from
any working directory.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HEADLESS = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
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

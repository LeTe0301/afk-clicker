"""
Feature: a live click counter in the status pill.

Counts clicks in the running session and shows them next to the state, so you
can tell at a glance whether the farm is still producing.
"""
import threading
import time
import tkinter as tk


class ClickCounter:
    def __init__(self, ui):
        self.ui = ui
        self.count = 0
        self.started = time.monotonic()

    def start(self):
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        while self.ui.running:
            # Read the interval the user configured so the estimate stays right
            # when they change it mid-session.
            interval = float(self.ui.click_ms.var.get()) / 1000.0
            self.count += 1
            rate = self.count / max(1e-6, time.monotonic() - self.started)
            self.ui.status.set("RUNNING", "#35d07f", f"{self.count} clicks · {rate:.1f}/s")
            time.sleep(interval)

    def reset(self):
        # monotonic(), not time(): a clock adjustment mid-session would make
        # the rate meaningless or negative.
        self.count = 0
        self.started = time.monotonic()

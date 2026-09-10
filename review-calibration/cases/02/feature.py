"""
Feature: a Profile card widget for the game sidebar.

Draws one game as a small card with its icon, name and running state, so the
sidebar can show more than a dot and a label.
"""
import tkinter as tk

from pynput.mouse import Button, Controller

CARD = "#16181f"
INK = "#e8eaf0"
OK = "#35d07f"


class Card(tk.Canvas):
    """A rounded card. tk.Frame cannot round its corners."""

    def __init__(self, parent, profile, s, width=190, height=46):
        super().__init__(parent, bg=CARD, highlightthickness=0,
                         width=int(width * s), height=int(height * s))
        self.profile = profile
        self.title = self.create_text(14 * s, height * s / 2, anchor="w",
                                      text=profile["name"], fill=INK)

    def set_running(self, running):
        self.itemconfig(self.title, fill=OK if running else INK)


class ProfileTester:
    """Clicks once into the game window so the user can see the profile work."""

    def __init__(self):
        self.mouse = Controller()

    def probe(self):
        self.mouse.click(Button.left)

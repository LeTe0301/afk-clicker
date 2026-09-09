"""
AFK autoclicker for the drowned/copper reinforcement farm.

Beyond plain autoclicking this handles *eating*, which is mandatory on hard
difficulty: hard is the only difficulty where zombie reinforcements happen, and
it is also the only one where the hunger bar keeps draining your hearts until
you actually die.

Why eating gets its own attack pause instead of just holding right-click:
rotten flesh takes 1.6 s to consume, and a left-click attack cancels an
in-progress eat. An autoclicker attacking every ~0.5 s would restart the eat
forever and you would still starve. So EAT mode stops clicking, holds right
mouse for long enough to finish the food, then resumes.

Requires: pynput, keyboard   ->   pip install pynput keyboard
Prebuilt Windows binaries: see the Releases page.
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

import keyboard
from pynput.mouse import Button, Controller

# ── palette ───────────────────────────────────────────────────────────────
# Two greys, not one: the window sits a shade darker than the cards on it, so
# panels read as raised without needing a drop shadow Tk cannot draw.
BG      = "#0e0f13"
CARD    = "#16181f"
CARD_HI = "#1d202a"      # hover / pressed
LINE    = "#262a35"
INK     = "#e8eaf0"
MUTED   = "#868c9e"
ACCENT  = "#ffc542"
OK      = "#35d07f"
BAD     = "#ff5f56"

# Rotten flesh is 1.6 s; leave headroom so a lagged tick still finishes the eat.
DEFAULT_CLICK_MS = 510      # Rays Works' figure: faster than this breaks the sword sweep
DEFAULT_EAT_EVERY_S = 75    # attacking burns ~1 food point / 20 s; flesh restores 4
DEFAULT_EAT_HOLD_S = 2.0

# One content width for the whole column. Everything -- the status pill, the
# cards, the segmented control -- is measured off this so nothing nests
# inward by a few pixels and breaks the vertical edge the eye follows.
CONTENT_W = 304
CARD_INNER_W = CONTENT_W - 2 - 24        # 1px border each side, 12px padding


def enable_dpi_awareness():
    """
    Without this the window is bilinearly upscaled by Windows on any display
    above 100% scaling -- every label comes out visibly blurry, which is the
    single most dated-looking thing a Tk app can do. Must run before Tk() so
    the very first window is created with the right awareness.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)      # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()       # older Windows
        except Exception:
            pass


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """Tk has no rounded rectangle; a smoothed polygon is the usual stand-in."""
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [
        x1 + r, y1,  x2 - r, y1,  x2, y1,  x2, y1 + r,
        x2, y2 - r,  x2, y2,  x2 - r, y2,  x1 + r, y2,
        x1, y2,  x1, y2 - r,  x1, y1 + r,  x1, y1,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


class Button(tk.Canvas):
    """Canvas button, because tk.Button cannot do rounded corners or hover."""

    def __init__(self, parent, text, command, s, primary=False, width=120, height=34):
        super().__init__(parent, bg=CARD if not primary else CARD, highlightthickness=0,
                         width=int(width * s), height=int(height * s), cursor="hand2")
        self.command = command
        self.primary = primary
        self._enabled = True
        self.s = s
        w, h = int(width * s), int(height * s)
        self.shape = round_rect(self, 1, 1, w - 1, h - 1, 9 * s, fill=CARD, outline=LINE)
        self.label = self.create_text(w / 2, h / 2, text=text, fill=INK,
                                      font=("Segoe UI", int(9.5 * s), "bold"))
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<Button-1>", self._click)
        self._paint()

    def _colors(self, hover):
        if not self._enabled:
            return CARD, LINE, MUTED
        if self.primary:
            return (ACCENT, ACCENT, "#12131a") if not hover else ("#ffd66b", "#ffd66b", "#12131a")
        return (CARD_HI if hover else CARD), LINE, INK

    def _paint(self, hover=False):
        fill, outline, ink = self._colors(hover)
        self.itemconfig(self.shape, fill=fill, outline=outline)
        self.itemconfig(self.label, fill=ink)

    def _click(self, _event):
        if self._enabled:
            self.command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._paint()

    def set_primary(self, primary):
        self.primary = primary
        self._paint()


class Segmented(tk.Canvas):
    """A segmented control -- the modern replacement for a column of radios."""

    def __init__(self, parent, options, variable, s, width=CARD_INNER_W, height=34):
        super().__init__(parent, bg=CARD, highlightthickness=0,
                         width=int(width * s), height=int(height * s), cursor="hand2")
        self.options = options                # [(value, label), ...]
        self.var = variable
        self.s = s
        self.w, self.h = int(width * s), int(height * s)
        round_rect(self, 0, 0, self.w, self.h, 9 * s, fill=BG, outline=LINE)
        seg = self.w / len(options)
        self.pill = round_rect(self, 2, 2, seg - 2, self.h - 2, 7 * s,
                               fill=CARD_HI, outline="")
        self.texts = [
            self.create_text(seg * i + seg / 2, self.h / 2, text=lbl, fill=MUTED,
                             font=("Segoe UI", int(9 * s)))
            for i, (_v, lbl) in enumerate(options)
        ]
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *_a: self._paint())
        self._paint()

    def _click(self, event):
        idx = min(len(self.options) - 1, int(event.x / (self.w / len(self.options))))
        self.var.set(self.options[idx][0])

    def _paint(self):
        values = [v for v, _l in self.options]
        try:
            idx = values.index(self.var.get())
        except ValueError:
            idx = 0
        seg = self.w / len(self.options)
        self.coords(self.pill, *self._pill_pts(seg * idx + 2, 2, seg * (idx + 1) - 2, self.h - 2))
        for i, item in enumerate(self.texts):
            self.itemconfig(item, fill=INK if i == idx else MUTED)

    def _pill_pts(self, x1, y1, x2, y2):
        r = min(7 * self.s, (x2 - x1) / 2, (y2 - y1) / 2)
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class StatusPill(tk.Canvas):
    """The one thing you read from across the room, so it gets real estate."""

    def __init__(self, parent, s, width=CONTENT_W, height=58):
        super().__init__(parent, bg=BG, highlightthickness=0,
                         width=int(width * s), height=int(height * s))
        self.s = s
        w, h = int(width * s), int(height * s)
        self.shape = round_rect(self, 1, 1, w - 1, h - 1, 12 * s, fill=CARD, outline=LINE)
        self.dot = self.create_oval(22 * s, h / 2 - 5 * s, 32 * s, h / 2 + 5 * s,
                                    fill=BAD, outline="")
        self.text = self.create_text(46 * s, h / 2, anchor="w", text="OFF", fill=INK,
                                     font=("Segoe UI", int(14 * s), "bold"))
        self.hint = self.create_text(w - 20 * s, h / 2, anchor="e", text="", fill=MUTED,
                                     font=("Segoe UI", int(8.5 * s)))

    def set(self, text, color, hint=""):
        self.itemconfig(self.text, text=text, fill=color)
        self.itemconfig(self.dot, fill=color)
        self.itemconfig(self.hint, text=hint)


class Field(tk.Frame):
    """Label on the left, right-aligned value, unit suffix -- reads like a spec sheet."""

    def __init__(self, parent, label, default, unit, s):
        super().__init__(parent, bg=CARD)
        self.s = s
        tk.Label(self, text=label, bg=CARD, fg=MUTED, anchor="w",
                 font=("Segoe UI", int(9.5 * s))).pack(side="left")
        tk.Label(self, text=unit, bg=CARD, fg=MUTED, width=4, anchor="w",
                 font=("Segoe UI", int(9 * s))).pack(side="right")
        self.var = tk.StringVar(value=str(default))
        wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        wrap.pack(side="right", padx=(0, int(10 * s)))
        entry = tk.Entry(wrap, textvariable=self.var, width=6, bg=BG, fg=INK,
                         relief="flat", insertbackground=ACCENT, justify="right",
                         font=("Consolas", int(10 * s)), highlightthickness=0)
        entry.pack(ipady=int(4 * s), ipadx=int(5 * s))
        # A focus ring is the cheapest way to make a flat field feel alive.
        entry.bind("<FocusIn>", lambda e: wrap.config(bg=ACCENT))
        entry.bind("<FocusOut>", lambda e: wrap.config(bg=LINE))


def section(parent, text, s):
    tk.Label(parent, text=text.upper(), bg=BG, fg=MUTED, anchor="w",
             font=("Segoe UI", int(8 * s), "bold")).pack(fill="x", pady=(int(14 * s), int(6 * s)))


def card(parent, s):
    f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    f.pack(fill="x")
    inner = tk.Frame(f, bg=CARD)
    inner.pack(fill="x", padx=int(12 * s), pady=int(10 * s))
    return inner


class AfkAutoclicker:
    def __init__(self, root):
        self.root = root
        self.s = s = root.tk.call("tk", "scaling") / 1.333  # 1.0 at 96 dpi

        root.title("AFK Farm Clicker")
        root.config(bg=BG)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.mouse = Controller()
        self.hotkey = None
        self.registered_hotkey = None      # what is actually bound in `keyboard`
        self.running = False
        self.worker = None
        self.capture_thread = None
        self.right_held = False

        pad = int(16 * s)
        body = tk.Frame(root, bg=BG)
        body.pack(padx=pad, pady=pad, fill="both", expand=True)

        tk.Label(body, text="AFK Farm Clicker", bg=BG, fg=INK, anchor="w",
                 font=("Segoe UI", int(15 * s), "bold")).pack(fill="x")
        tk.Label(body, text="Drowned / copper reinforcement farm", bg=BG, fg=MUTED,
                 anchor="w", font=("Segoe UI", int(9 * s))).pack(fill="x", pady=(0, int(12 * s)))

        self.status = StatusPill(body, s)
        self.status.pack()

        section(body, "Hotkey", s)
        hk = card(body, s)
        self.hotkey_label = tk.Label(hk, text="Not set", bg=CARD, fg=MUTED, anchor="w",
                                     font=("Consolas", int(10 * s)), wraplength=int(250 * s))
        self.hotkey_label.pack(fill="x", pady=(0, int(8 * s)))
        row = tk.Frame(hk, bg=CARD)
        row.pack(fill="x")
        self.record_button = Button(row, "Record", self.register_hotkey, s, width=124)
        self.record_button.pack(side="left")
        self.apply_button = Button(row, "Apply", self.apply_hotkey, s, width=124, primary=True)
        self.apply_button.pack(side="right")
        self.apply_button.set_enabled(False)

        section(body, "Clicking", s)
        cl = card(body, s)
        self.click_ms = Field(cl, "Interval", DEFAULT_CLICK_MS, "ms", s)
        self.click_ms.pack(fill="x")

        section(body, "Eating", s)
        ea = card(body, s)
        self.eat_mode = tk.StringVar(value="pause")
        Segmented(ea, [("pause", "Pause & eat"), ("hold", "Hold RMB"), ("off", "Off")],
                  self.eat_mode, s).pack(pady=(0, int(8 * s)))
        self.eat_every = Field(ea, "Eat every", DEFAULT_EAT_EVERY_S, "s", s)
        self.eat_every.pack(fill="x")
        self.eat_hold = Field(ea, "Hold for", DEFAULT_EAT_HOLD_S, "s", s)
        self.eat_hold.pack(fill="x", pady=(int(4 * s), 0))

        tk.Label(body, text="Rotten flesh takes 1.6 s — a click cancels the eat.",
                 bg=BG, fg=MUTED, anchor="w",
                 font=("Segoe UI", int(8 * s))).pack(fill="x", pady=(int(12 * s), 0))

    # ---------- helpers ----------

    def _num(self, field, fallback, minimum):
        """Entry boxes are user-editable, so never trust them at click time."""
        try:
            return max(minimum, float(field.var.get()))
        except (TypeError, ValueError):
            return fallback

    def _ui(self, fn, *args):
        """Tk is not thread-safe; marshal every widget update onto the main loop."""
        self.root.after(0, fn, *args)

    # ---------- hotkey ----------

    def register_hotkey(self):
        if self.capture_thread and self.capture_thread.is_alive():
            return
        self.hotkey_label.config(text="Press any key…  (Esc cancels)", fg=ACCENT)
        self.hotkey = None
        self.capture_thread = threading.Thread(target=self.capture_hotkey, daemon=True)
        self.capture_thread.start()

    def capture_hotkey(self):
        pressed = set()
        while True:
            event = keyboard.read_event(suppress=False)
            if event.event_type == keyboard.KEY_DOWN:
                if event.name == "esc":
                    self._ui(self._show_hotkey, self.registered_hotkey)
                    return
                pressed.add(event.name)
            elif event.event_type == keyboard.KEY_UP:
                pressed.discard(event.name)
                continue

            modifiers = {"ctrl", "shift", "alt"} & pressed
            regular = pressed - {"ctrl", "shift", "alt"}
            if regular:
                key = sorted(regular)[0]
                self.hotkey = "+".join(sorted(modifiers) + [key]) if modifiers else key
                self._ui(self._hotkey_captured)
                return

    def _show_hotkey(self, active):
        self.hotkey_label.config(text=active or "Not set", fg=INK if active else MUTED)

    def _hotkey_captured(self):
        self.hotkey_label.config(text=f"{self.hotkey}   · not applied", fg=ACCENT)
        self.apply_button.set_enabled(True)

    def apply_hotkey(self):
        if not self.hotkey:
            return
        # Without this the old binding stays live and both keys toggle the clicker.
        if self.registered_hotkey:
            try:
                keyboard.remove_hotkey(self.registered_hotkey)
            except (KeyError, ValueError):
                pass
        keyboard.add_hotkey(self.hotkey, self.toggle)
        self.registered_hotkey = self.hotkey
        self.hotkey_label.config(text=self.hotkey, fg=INK)
        self.apply_button.set_enabled(False)
        self.status.set("OFF", BAD, f"{self.hotkey} to toggle")

    # ---------- run control ----------

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        # stop() only clears the flag -- it does not wait for the worker to
        # notice. A quick off/on, or one bounced hotkey press, could therefore
        # start a second worker while the first is still finishing its sleep,
        # and two loops clicking together halve the interval. On this farm that
        # silently breaks the sword sweep instead of just being noisy, so wait
        # for the old thread before arming a new one.
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
            if self.worker.is_alive():
                return                     # refuse rather than double-click
        self.running = True
        self._ui(self.status.set, "RUNNING", OK, self.registered_hotkey or "")
        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self._ui(self.status.set, "OFF", BAD, self.registered_hotkey or "")

    def _sleep(self, seconds):
        """Interruptible sleep, so toggling off reacts immediately."""
        deadline = time.monotonic() + seconds
        while self.running and time.monotonic() < deadline:
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
        return self.running

    def _release_right(self):
        if self.right_held:
            self.mouse.release(Button.right)
            self.right_held = False

    def loop(self):
        try:
            last_meal = time.monotonic()
            while self.running:
                # Re-read every pass, like the numeric fields already are:
                # picking the mode up once meant switching the control did
                # nothing until you toggled the clicker off and on again.
                mode = self.eat_mode.get()
                interval = self._num(self.click_ms, DEFAULT_CLICK_MS, 50) / 1000.0

                if mode == "hold":
                    if not self.right_held:
                        self.mouse.press(Button.right)
                        self.right_held = True
                elif self.right_held:
                    # Left "hold" (or switched to off) -- do not leave the
                    # button down, that keeps blocking/eating forever.
                    self._release_right()

                if mode == "pause":
                    every = self._num(self.eat_every, DEFAULT_EAT_EVERY_S, 5)
                    if time.monotonic() - last_meal >= every:
                        self._ui(self.status.set, "EATING", ACCENT, "clicks paused")
                        hold = self._num(self.eat_hold, DEFAULT_EAT_HOLD_S, 0.5)
                        self.mouse.press(Button.right)
                        self.right_held = True
                        self._sleep(hold)          # no left-clicks here, or the eat cancels
                        self._release_right()
                        last_meal = time.monotonic()
                        if not self.running:
                            break
                        self._ui(self.status.set, "RUNNING", OK, self.registered_hotkey or "")

                self.mouse.click(Button.left)
                if not self._sleep(interval):
                    break
        finally:
            self._release_right()

    def on_close(self):
        self.stop()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)   # let it run its own release first
        self._release_right()          # never leave a mouse button stuck down
        self.root.destroy()


if __name__ == "__main__":
    enable_dpi_awareness()
    root = tk.Tk()
    # Segoe UI is the Windows system face; falling back keeps Linux usable.
    if "Segoe UI" not in tkfont.families():
        root.option_add("*Font", "TkDefaultFont")
    AfkAutoclicker(root)
    root.mainloop()

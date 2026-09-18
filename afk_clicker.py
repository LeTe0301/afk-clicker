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

Requires: pynput   ->   pip install pynput
Prebuilt binaries for Windows, Linux and macOS: see the Releases page.
"""

import hashlib
import json
import os
import platform
import queue
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
import weakref
from tkinter import font as tkfont

from pynput import keyboard as kb
# Imported under a different name: the Tk widget class below is also called
# Button, and the shadowing turned every mouse action into an AttributeError.
from pynput.mouse import Button as MouseButton, Controller

# ── palette ───────────────────────────────────────────────────────────────
# Two named palettes (ticket #17 / mock "Chosen": Deepslate for dark, Quartz
# for light). "light" is unused until #17's OS-detection and Settings-tab
# features land -- kept here, not stubbed, because every value is already
# decided (ticket + theme-board.html's "quartz-pair" entry), so there is
# nothing left to design later, only to wire up.
def _lighten(hex6, factor):
    # Blends a hex color toward white by `factor` (0-1). Used only to derive
    # a primary button's hover fill from its own ACCENT, so a new theme
    # never needs a fourth hand-picked hex just for hovering.
    #
    # An out-of-range factor (e.g. 2.0) used to walk r/g/b past 255 and
    # produce a malformed string like "#17e17e17e" instead of a real color
    # (PR #28 review concern) -- Feature 3 gives this a second caller, so a
    # bad factor from there must not corrupt a widget's fill. Clamped rather
    # than validated: any factor is a meaningful request ("as light as this
    # can go"), so there's nothing to reject. hex6 is the opposite -- a
    # malformed color has no reasonable interpretation, so it's rejected
    # outright rather than silently coerced into a wrong color.
    if not (isinstance(hex6, str) and len(hex6) == 7 and hex6[0] == "#"
            and all(c in "0123456789abcdefABCDEF" for c in hex6[1:])):
        raise ValueError(f"not a #rrggbb hex color: {hex6!r}")
    factor = max(0.0, min(1.0, factor))
    r, g, b = (int(hex6[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (int(c + (255 - c) * factor) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _theme(bg, card, card_hi, line, ink, muted, accent, accent_ink, ok, bad):
    return {"BG": bg, "CARD": card, "CARD_HI": card_hi, "LINE": line,
            "INK": ink, "MUTED": muted, "ACCENT": accent,
            "ACCENT_INK": accent_ink, "ACCENT_HI": _lighten(accent, 0.18),
            "OK": ok, "BAD": bad}


THEMES = {
    "dark": _theme("#15171a", "#1c1f23", "#262a30", "#3a4048", "#e4e7ea",
                   "#9299a3", "#e08a55", "#1a0f08", "#5cc9a4", "#f06262"),
    "light": _theme("#e8ebf0", "#ffffff", "#eff2f7", "#d3d8e0", "#161a22",
                    "#596170", "#2b58cc", "#ffffff", "#0f7f4c", "#cc3527"),
}

_ACTIVE = THEMES["dark"]      # feature 1 ships dark-only; #17 features 2-3 pick this
BG, CARD, CARD_HI, LINE, INK, MUTED = (
    _ACTIVE["BG"], _ACTIVE["CARD"], _ACTIVE["CARD_HI"], _ACTIVE["LINE"],
    _ACTIVE["INK"], _ACTIVE["MUTED"])
ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD = (
    _ACTIVE["ACCENT"], _ACTIVE["ACCENT_INK"], _ACTIVE["ACCENT_HI"],
    _ACTIVE["OK"], _ACTIVE["BAD"])


def set_active_theme(name):
    """Point the module's palette globals at THEMES[name]. Every widget in
    this file reads BG/CARD/... as bare module globals at construction time
    (not as function-default values, see docs/history/ac-17-f2-spec.md background), so
    reassigning them here before any widget is built is sufficient -- no
    widget code changes, no theme reference threaded onto self anywhere.
    Feature 3 reuses this unchanged for its System/Light/Dark override,
    followed by its own widget-tree rebuild.

    An unknown name raises ValueError rather than silently falling back to
    Dark: detect_os_theme() below only ever returns "dark"/"light" by
    construction, so this branch is unreachable from real detection and only
    fires if a caller (Feature 3's override UI, or a test) passes a
    typo/garbage string -- a programming error that should fail loudly
    during development, not silently paint a plausible-but-wrong theme."""
    if name not in THEMES:
        raise ValueError(f"unknown theme {name!r}; expected one of {sorted(THEMES)}")
    global _ACTIVE, BG, CARD, CARD_HI, LINE, INK, MUTED
    global ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD
    _ACTIVE = THEMES[name]
    BG, CARD, CARD_HI, LINE, INK, MUTED = (
        _ACTIVE["BG"], _ACTIVE["CARD"], _ACTIVE["CARD_HI"], _ACTIVE["LINE"],
        _ACTIVE["INK"], _ACTIVE["MUTED"])
    ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD = (
        _ACTIVE["ACCENT"], _ACTIVE["ACCENT_INK"], _ACTIVE["ACCENT_HI"],
        _ACTIVE["OK"], _ACTIVE["BAD"])


# A persisted enum key -> the concrete value it resolves to, same category as
# THEMES above: "ui_scale" in settings.json is one of these four strings, and
# self.s (AfkAutoclicker.__init__) multiplies the DPI factor by the matching
# float. See docs/history/ac-17-f4-spec.md §1 for why 4 explicit percentage steps rather than
# a slider or named sizes.
UI_SCALE_FACTORS = {"90": 0.9, "100": 1.0, "115": 1.15, "130": 1.3}
# G#38/GH#67: "auto" is a 5th valid ui_scale value, not one more key in
# UI_SCALE_FACTORS itself -- it has no single fixed multiplier, self.s is
# derived continuously from the window size instead (_auto_scale_factor()
# below). Now the default for fresh installs; an existing install's
# already-saved fixed step round-trips unchanged (docs/spec.md's Risk notes).
UI_SCALE_DEFAULT = "auto"

# Auto is clamped to the same range the fixed steps already cover -- reusing
# the existing numbers rather than inventing new bounds also prevents a
# shrink/grow feedback runaway (docs/spec.md "The debounce decision").
AUTO_SCALE_MIN = UI_SCALE_FACTORS["90"]
AUTO_SCALE_MAX = UI_SCALE_FACTORS["130"]
# A calibration anchor only, not a hardcoded target screen -- see
# AUTO_REFERENCE_FILL below (defined after WINDOW_MIN_H/CONTENT_PAD exist).
AUTO_REF_SCREEN_W, AUTO_REF_SCREEN_H = 1920, 1080
# The debounce window for Auto's settle-then-rebuild (docs/spec.md "The
# debounce decision") -- an initial value, not empirically tuned (Xvfb can't
# validate perceived responsiveness).
AUTO_SETTLE_MS = 150


# G#23/GH#35: macOS reports tk scaling ~0.75 (its 72-dpi-native convention vs.
# this app's 96-dpi baseline), so self.s can land well under 1.0 even before
# the 90% UI-scale step multiplies it further (worst case _dpi_s * 0.9 ~= 0.675,
# see backlog.md's compound-scale lesson). int() truncates, so an
# already-small base like 8 crosses from 6pt (100%, ships today) to 5pt (90%,
# illegible) purely from that one extra multiply. FONT_SIZE_FLOOR is chosen to
# match the smaller of those two, not raise it: 6 leaves every already-shipping
# size (mac 100%, and every non-mac step -- none of which are under 6 today)
# untouched, and only lifts the newly-broken 90% case up to parity with 100%.
# G#38 (UI scale follows window size) will reuse this unmodified for its own
# continuous-s scaling -- keep it a pure function of (base, s), not tied to
# the four discrete UI_SCALE_FACTORS keys.
FONT_SIZE_FLOOR = 6


def fs(base, s):
    """int(base * s), floored at FONT_SIZE_FLOOR so no label renders
    illegibly small on a low-DPI display. Truncates (matches every existing
    call site's int() today) rather than rounds -- rounding would silently
    change already-shipped sizes at scale steps this ticket isn't about."""
    return max(FONT_SIZE_FLOOR, int(base * s))


def resolve_appearance(value, cached_os_theme=None):
    """"system"/"light"/"dark" -> a THEMES key. cached_os_theme, if given,
    is reused instead of calling detect_os_theme() again -- story.md:
    detection happens once per process, not on every resolution (including
    a mid-session re-pick of "System" in Settings)."""
    if value != "system":
        return value
    return cached_os_theme if cached_os_theme is not None else detect_os_theme()


CARD_PAD = 12      # cards and sidebar rows' own content inset (mock's
                   # --rc / --rb was 12px when this doubled as a corner
                   # radius; story #24 feature 5 dropped rounding, but the
                   # inset itself is still real padding, not radius).

# Rotten flesh is 1.6 s; leave headroom so a lagged tick still finishes the eat.
DEFAULT_CLICK_MS = 650      # 12 ticks (600 ms) is Java's full sword-sweep charge; +1 tick covers click/tick quantisation jitter
DEFAULT_EAT_EVERY_S = 75    # attacking burns ~1 food point / 20 s; flesh restores 4
DEFAULT_EAT_HOLD_S = 2.0

# Below this, click_ms - jitter_ms has dropped to 10 ticks (500 ms) or
# worse -- the ticket's own cited failure case (G#22): 84% charge, 76%
# damage, no sweep. Between this and DEFAULT_CLICK_MS the one-tick
# quantization margin DEFAULT_CLICK_MS banks on is already gone (11
# ticks/550 ms) -- a hit can still often land as a full sweep, but there
# is no margin left, hence a hint rather than nothing, and MUTED rather
# than BAD.
MIN_SWEEP_BAD_MS = 550

# Exact copy (docs/design.md): both name "Java" explicitly, since the app
# cannot tell a Java window from a Bedrock one and an unscoped claim would
# be flatly false for a Bedrock player, who has no sweep cooldown to lose.
SWEEP_HINT_MUTED = "Java sweeps may miss"
SWEEP_HINT_BAD = "Java sweeps likely fail"

# One content width for the whole column. Everything -- the status pill, the
# cards, the segmented control -- is measured off this so nothing nests
# inward by a few pixels and breaks the vertical edge the eye follows.
if sys.platform == "darwin":
    HOTKEY_HELP = "Grant Accessibility permission, then press Apply again"
elif sys.platform.startswith("linux"):
    HOTKEY_HELP = "Needs an X11 session (Wayland blocks global keys)"
else:
    HOTKEY_HELP = "Could not register the hotkey"

SIDEBAR_W = 208
CONTENT_W = 452
WINDOW_MIN_H = 620   # the window's hard height floor, and (see
    # _apply_minsize()) today's default launch height too -- they are
    # deliberately the same number, unlike minw/default_w after story
    # #24 feature 3 (docs/spec.md's "Why height doesn't get the width
    # axis's floor/default split", G#28/GH#48). Was 690 (#14, tuned for
    # the old single combined page before PR #40 split it into tabs),
    # which left the tallest real pane (Clicking+Eating, Minecraft) in
    # ~148-163px of dead space it can never use and the shortest
    # (Hotkey) ~78% empty at the floor.
    #
    # Round 1/2 of this ticket picked 560 from a Linux/Xvfb-only
    # measurement (~500-510px candidate + a ~40-60px margin). Round 4's
    # real Windows CI trace (docs/implementation.md) showed that margin
    # was wrong on the platform that actually needed it: at 560, Windows'
    # own taller Segoe UI metrics left the tallest pane only 1px of real
    # leftover (natural=367 vs avail=368) -- Linux's own substituted font
    # never got closer than ~10px, so this box's own measurement never
    # caught it. 368 = 560 - 192, giving a live-measured Windows overhead
    # (everything in the window but this one pane) of 192px, vs. this
    # box's ~131px -- taller chrome, not just taller pane content, eats
    # the difference. 620 = 192 (Windows overhead) + 367 (Windows
    # natural) + 61 -- the same ~61px margin round 1 targeted, now sized
    # against the platform that actually needs it instead of the one
    # that happened to have slack to spare. Re-verify against a fresh
    # Windows CI trace before retuning further; this box cannot measure
    # Windows' own font metrics directly.
CONTENT_PAD = 16   # _build_content's own outer padx/pady around body
CARD_INNER_W = CONTENT_W - 2 * CONTENT_PAD - 2 * CARD_PAD    # a full-width
    # card's real inner width: body sits CONTENT_PAD in from CONTENT_W on
    # each side before the card's own CARD_PAD padding starts, so a control
    # sized off CONTENT_W alone (skipping the body inset) overruns the card.

# G#38/GH#67: Auto's calibration anchor, derived the same way CARD_INNER_W
# above is derived from other constants -- must come after SIDEBAR_W/
# CONTENT_W/WINDOW_MIN_H exist, so it can't sit next to UI_SCALE_FACTORS
# itself. The app's own existing default launch geometry
# ((SIDEBAR_W+1+CONTENT_W) x WINDOW_MIN_H, unscaled) sitting on a 1920x1080
# screen (AUTO_REF_SCREEN_W/H, the most common desktop resolution, used only
# as the calibration anchor) is defined to yield an Auto factor of ~1.0 --
# i.e. on a typical screen, Auto's very first computed value lands at parity
# with today's "100%" step (docs/spec.md §2).
AUTO_REFERENCE_FILL = (((SIDEBAR_W + 1 + CONTENT_W) * WINDOW_MIN_H
                        / (AUTO_REF_SCREEN_W * AUTO_REF_SCREEN_H)) ** 0.5)

ROW_LABEL_W = 140    # widest existing Row label ("Mouse button"/"Random
    # jitter", ~88px measured @ s=1) plus headroom for font-metric
    # differences on the real target font.
ROW_LABEL_GAP = 12    # breathing room between the label column and the
    # value column that starts right after it.

TAB_HEIGHT = 32       # TabBar's own canvas height (story #24 feature 2)
TAB_GAP = 28          # horizontal gap between adjacent tab labels
TAB_PAD_BOTTOM = 6    # space between text baseline and the underline
TAB_UNDERLINE_H = 2   # active-tab underline thickness

SIDEBAR_RAIL_W = 64   # collapsed rail width (story #24 feature 3) -- room for
    # a centered COLLAPSED_BADGE_D badge plus symmetric margin either side.
    # GameItem/SettingsItem actually paint their collapsed canvas at
    # SIDEBAR_RAIL_W - 16 = 48px wide, not the full 64, so the real margin
    # is (48 - 28) / 2 = 10px each side, narrower than any real game name
    # on purpose.
RAIL_COLLAPSE_THRESHOLD = SIDEBAR_W + 1 + CONTENT_W
    # Collapse exactly at today's old expanded-only minimum width -- the
    # number that used to be the *entire* floor before this feature. Below
    # it, the expanded rail plus a full CONTENT_W no longer both fit; above
    # it, this feature changes nothing about today's behavior.
COLLAPSED_BADGE_D = 28   # collapsed-badge diameter -- big enough to read one
    # capital letter at the smallest UI-scale step (90%). Centered
    # dynamically off the canvas's own w/h, so this needs no separate
    # per-scale fit-check.

FILL_TOP_SHARE = 0.0   # story #24 feature 4: fraction of a pane's own
    # leftover vertical space given to its top spacer, the rest to its
    # bottom spacer. Was 0.5 (centering), which minimized the largest
    # single dead band -- see docs/design.md's "Key design decision" for
    # why every other split leaves a bigger empty band on a single-card
    # pane. G#37/GH#66 (Leo's 2026-09-13 feedback on 0.5.0 screenshots)
    # reverses that call: centering left every pane's content floating
    # mid-page with a large dead band above it, which reads as "broken
    # layout" rather than "balanced". 0.0 pins the top spacer to its
    # unavoidable 1px max(1, ...) floor so content starts right below the
    # tab bar, and pushes all of a pane's leftover space into the bottom
    # spacer instead -- see docs/spec.md's "Why the floor invariant is
    # provably unaffected" for why this does not change WINDOW_MIN_H's
    # own floor behavior.


def selftest():
    """
    CI entry point. A --windowed build has no console, so a missing hidden
    import does not show up as a traceback -- it shows up as "I double-clicked
    it and nothing happened", on the user's machine, after release. Touch every
    lazily-resolved platform backend here so the build fails in CI instead.
    """
    Controller()                                  # pynput mouse backend
    macos_input_permitted()                       # the guard itself must load
    detect_os_theme()                             # real registry/defaults/
                                                    # gsettings backend must
                                                    # load and never raise --
                                                    # the only place this runs
                                                    # against the frozen build

    kb.Listener(on_press=lambda k: False)         # pynput keyboard backend --
                                                   # __init__ only, never
                                                   # started here, so this is
                                                   # safe even without
                                                   # Accessibility permission
                                                   # (see macos_input_permitted's
                                                   # docstring)
    Hotkey({"ctrl"}, [_record(kb.KeyCode.from_char("h"))]).label()
    Hotkey(set(), [_record(kb.Key.f6), _record(kb.Key.f7)]).label()
    icon_root = tk.Tk()                           # Tcl/Tk actually bundled
    _load_app_icon(icon_root)                     # the bundled icon-*.png
                                                    # files actually resolve
                                                    # through --add-data on
                                                    # this platform -- same
                                                    # code path as __init__
    icon_root.destroy()
    # A real temp file, not os.devnull: Store.save() writes to a sibling and
    # os.replace()s it into place, so as root this replaced the /dev/null
    # device node with a regular file.
    with tempfile.TemporaryDirectory() as probe:
        Store(os.path.join(probe, "settings.json")).save()
    config_path()                                 # path logic is sane
    return 0


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


# ── hotkey plumbing ───────────────────────────────────────────────────────
# pynput, not the `keyboard` package. `keyboard` is Windows/Linux only and
# needs root on Linux, which would have made the macOS build pointless: it
# would install cleanly and then never respond to the hotkey at all. pynput
# speaks all three platforms, and its mouse half was already a dependency --
# so this removes a dependency rather than adding one.
#

_MOD_BASES = ("ctrl", "alt", "shift", "cmd")
_MOD_ORDER = {"ctrl": 0, "altgr": 1, "alt": 2, "shift": 3, "cmd": 4}

# Three non-modifier keys, on top of any number of modifiers. Beyond three a
# chord stops being something a keyboard can reliably deliver anyway: most
# membrane boards ghost past two simultaneous keys in the same matrix row.
MAX_CHORD = 3

# X11 hands _record a keysym as "vk" (see _record's docstring above), and the
# X11 protocol reserves keysym values up to 0x1FFFFFFF -- the largest vk any
# of the three backends can produce. Win32 VKs (0-255) and macOS keycodes
# (roughly 0-127) both already fall well inside this, so one bound covers a
# settings file recorded on any platform and read back on any other.
MAX_VK = 0x1FFFFFFF

# A real dead-key/compose keypress (CGEventKeyboardGetUnicodeString on the
# darwin backend, the only one of the three that can hand back more than one
# code point per event) stays at a small handful of code points in practice --
# nothing about real input-method composition approaches this. Generous
# enough not to reject a genuine composed character, far short of an
# adversarial payload like a 200-char string.
MAX_CHAR_LEN = 8


def macos_input_permitted():
    """
    Whether this process is allowed to observe and synthesise input on macOS.

    pynput does not reliably *raise* when Accessibility permission is missing:
    on a machine that has never granted it, creating the CoreGraphics event tap
    can abort the process with SIGTRAP, which no except clause can catch. A CI
    runner reproduced exactly that -- "Trace/BPT trap: 5", exit 133, mid-test.
    A user would see the window vanish.

    AXIsProcessTrusted answers the question without touching the event tap, so
    the unrecoverable crash becomes a message telling them what to grant.
    Returns True wherever the question does not apply. On macOS itself an
    unanswerable question returns False, because the two mistakes do not cost
    the same: a wrong True aborts the process, a wrong False shows a message.
    """
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        path = ctypes.util.find_library("ApplicationServices")
        if not path:
            return False        # same unanswerable question as the except below
        lib = ctypes.cdll.LoadLibrary(path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool   # without this ctypes reads an
                                                          # int; non-zero garbage in the
                                                          # upper bytes reads as trusted
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        # On macOS an unanswerable question must read as "not permitted".
        # Guessing True costs an uncatchable SIGTRAP that takes the window with
        # it; guessing False costs a message the user can act on.
        return False


def _mod_base(key):
    """ctrl_l and ctrl_r are one modifier; AltGr is emphatically not Alt."""
    if not isinstance(key, kb.Key):
        return None
    if key.name == "alt_gr":
        return "altgr"
    base = key.name.split("_")[0]
    return base if base in _MOD_BASES else None


def _record(key):
    """
    Everything we know about one physical key, as a plain tuple.

    All three fields are kept because none of them is reliable alone: a named
    key has no char, a dead key has no char either, and on X11 the vk is the
    keysym, so it changes when Shift is held. Matching on any of the three that
    is present accepts the key however the platform chose to describe it.
    """
    if isinstance(key, kb.Key):
        return (key.name, getattr(key.value, "vk", None), None)
    char = getattr(key, "char", None)
    return (None, getattr(key, "vk", None), char.lower() if char else None)


def _same_key(a, b):
    name_a, vk_a, ch_a = a
    name_b, vk_b, ch_b = b
    if name_a or name_b:
        return name_a == name_b
    if vk_a is not None and vk_b is not None and vk_a == vk_b:
        return True
    return ch_a is not None and ch_a == ch_b


def _key_label(rec):
    name, vk, char = rec
    if name:
        return name.replace("_", " ").title()
    if char:
        # Uppercasing is only safe when it round-trips: "ß".upper() is "SS",
        # and Turkish dotless "ı".upper() is "I" -- a different key.
        upper = char.upper()
        return upper if upper.lower() == char else char
    return f"Key {vk}"


class Hotkey:
    """
    A recorded combination: a set of modifiers plus one to three other keys,
    all held at the same time. Order does not matter -- a chord is a chord.

    Not pynput's GlobalHotKeys. That matches on Listener.canonical(), which
    routes character keys back through the keyboard layout; measured with
    synthesised presses, every named key matched and no character key ever did.
    Matching the raw event instead also means the hotkey fires on the physical
    key you recorded, not on whatever that position means after a layout switch.
    """

    __slots__ = ("mods", "keys")

    def __init__(self, mods, records):
        self.mods = frozenset(mods)
        self.keys = tuple(records[:MAX_CHORD])

    def matches(self, held_mods, held_keys):
        if held_mods != self.mods:
            return False
        return all(any(_same_key(spec, rec) for rec in held_keys)
                   for spec in self.keys)

    def to_json(self):
        return {"mods": sorted(self.mods), "keys": [list(k) for k in self.keys]}

    @classmethod
    def from_json(cls, blob):
        """
        None for anything malformed -- a damaged setting must not block startup.

        Checked rather than wrapped in try/except: {"keys": "nope"} raises
        nothing at all, because iterating a string hands back characters and
        builds a plausible-looking hotkey out of garbage.
        """
        if not isinstance(blob, dict):
            return None
        raw, mods = blob.get("keys"), blob.get("mods", [])
        if not isinstance(raw, (list, tuple)) or not raw:
            return None
        # Reject, do not truncate -- a restored 4-key chord silently trimmed
        # to 3 fires on any 3 of the 4 keys the user actually recorded, which
        # is strictly *easier* to trigger than the saved combination. The
        # same reject-vs-adjust mistake as the modifier filtering below.
        if len(raw) > MAX_CHORD:
            return None
        # Reject, do not filter. Dropping the entries that fail the check
        # silently turned a saved Ctrl+Shift+F6 into an armed, firing Ctrl+F6 --
        # a global hotkey the user never recorded, wearing a plausible label.
        if not isinstance(mods, (list, tuple)):
            return None
        # Types before membership: `m not in _MOD_ORDER` hashes m, so a list or
        # a dict in there raised TypeError straight out of __init__ and the
        # window never opened -- the exact failure this function exists to
        # prevent, reintroduced by the fix for the filtering above.
        if not all(isinstance(m, str) for m in mods):
            return None
        if any(m not in _MOD_ORDER for m in mods):
            return None
        records = []
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or not 1 <= len(entry) <= 3:
                return None
            name, vk, char = (list(entry) + [None, None, None])[:3]
            if not (name is None or isinstance(name, str)):
                return None
            if not (vk is None or isinstance(vk, int)):
                return None
            # isinstance(True, int) is True -- bool is an int subclass, so the
            # check above alone lets a bool vk through to label as "Key True".
            if isinstance(vk, bool):
                return None
            if vk is not None and not (0 <= vk <= MAX_VK):
                return None
            if not (char is None or isinstance(char, str)):
                return None
            # bool("") is False, so an empty char slid through here into a
            # rendered "Key None" label; an unbounded char rendered a 200-char
            # string verbatim into the same label.
            if char is not None and not (1 <= len(char) <= MAX_CHAR_LEN):
                return None
            if name is None and vk is None and char is None:
                return None
            # Shape is not vocabulary: kb.Key is an Enum class, so hasattr
            # says yes to mro, __class__, __init__, _member_map_, __module__
            # -- everything Enum/object supplies, not just real key names.
            if name is not None and name not in kb.Key.__members__:
                return None
            records.append((name, vk, char))
        return cls(list(mods), records)

    def label(self):
        mods = sorted(self.mods, key=lambda m: _MOD_ORDER.get(m, 9))
        parts = ["AltGr" if m == "altgr" else m.title() for m in mods]
        return " + ".join(parts + [_key_label(r) for r in self.keys])


class HotkeyRecorder:
    """
    Collects a chord. Recording ends when every key is let go, so pressing
    Ctrl+Shift+K and releasing records all three -- there is no "done" button
    to reach for while holding a combination down.
    """

    def __init__(self):
        self.mods = set()
        self.records = []
        self._held = []
        self._held_mods = set()
        self.cancelled = False

    def press(self, key):
        if key == kb.Key.esc and not self.records:
            self.cancelled = True
            return False
        mod = _mod_base(key)
        if mod:
            self._held_mods.add(mod)
            self.mods.add(mod)
            return None
        rec = _record(key)
        if not any(_same_key(rec, h) for h in self._held):
            self._held.append(rec)
        if (len(self.records) < MAX_CHORD
                and not any(_same_key(rec, r) for r in self.records)):
            self.records.append(rec)
        return None

    def release(self, key):
        mod = _mod_base(key)
        if mod:
            self._held_mods.discard(mod)
        else:
            rec = _record(key)
            self._held = [h for h in self._held if not _same_key(h, rec)]
        # Everything let go and something was captured -> that was the chord.
        if not self._held and not self._held_mods and self.records:
            return False
        return None

    def result(self):
        if self.cancelled or not self.records:
            return None
        return Hotkey(self.mods, self.records)


class HotkeyWatcher:
    """One listener that owns the held-key state and fires on a full match."""

    # A start/stop toggle nobody needs to flip twice inside a quarter second.
    # Beyond guarding against a fumbled double-tap this absorbs duplicated key
    # events, which X11 emits for auto-repeat when detectable-autorepeat is off
    # (a repeat arrives as release-then-press, i.e. a complete chord again).
    DEBOUNCE_S = 0.25

    def __init__(self, hotkey, callback):
        self.hotkey = hotkey
        self.callback = callback
        self.mods = set()
        self.keys = []
        self.armed = True          # re-arm on release, so holding does not repeat
        self._last_fire = 0.0
        self.listener = kb.Listener(on_press=self._press, on_release=self._release)

    def start(self):
        self.listener.start()
        self.listener.wait()

    def stop(self):
        self.listener.stop()

    @property
    def running(self):
        return self.listener.running

    def _press(self, key):
        mod = _mod_base(key)
        if mod:
            self.mods.add(mod)
        else:
            rec = _record(key)
            if not any(_same_key(rec, h) for h in self.keys):
                self.keys.append(rec)
        if self.armed and self.hotkey.matches(self.mods, self.keys):
            self.armed = False
            now = time.monotonic()
            if now - self._last_fire >= self.DEBOUNCE_S:
                self._last_fire = now
                self.callback()

    def _release(self, key):
        mod = _mod_base(key)
        if mod:
            self.mods.discard(mod)
        else:
            rec = _record(key)
            self.keys = [h for h in self.keys if not _same_key(h, rec)]
        # Re-arm as soon as the chord is no longer complete, so holding it does
        # not retrigger but pressing it again does.
        if not self.hotkey.matches(self.mods, self.keys):
            self.armed = True


# Deliberately below 1.0: the interface and the per-game settings format are
# still moving, and semver reserves 1.0.0 for the point where they stop. Until
# then only the minor and patch parts advance.
__version__ = "0.7.0"
GITHUB_REPO = "LeTe0301/afk-clicker"

# Which release asset belongs to which platform. Keep in step with the
# archive names the build workflow produces.
ASSET_SUFFIX = {
    "win32": "windows-x64.zip",
    "linux": "linux-x86_64.tar.gz",
    "darwin": "macos-arm64.zip",
}


def _version_tuple(tag):
    """'v1.2.0' -> (1, 2, 0). Unparseable parts sort as 0 rather than crash."""
    parts = str(tag).lstrip("vV").split(".")
    out = []
    for part in parts[:4]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def is_newer(tag, current=__version__):
    return _version_tuple(tag) > _version_tuple(current)


def _is_safe_version_tag(tag):
    """True only for a tag shaped exactly like this project's own release
    tags -- "vX.Y.Z", the same MAJOR.MINOR.PATCH shape
    .github/workflows/release.yml's own version check enforces before a
    tag is ever published (that workflow strips a leading "v" first; the
    GitHub API's own tag_name field, read here, keeps it -- release.yml's
    `tag_name: v${{ ... }}`).

    tag_name is untrusted (docs/CODING-GUIDELINES.md "Input validation" --
    it's read from a network response, not typed by this project's own
    release process necessarily matching it) and, via _install_worker,
    flows straight into write_swap_script's target_version, which is
    written verbatim into a generated shell/batch script. Proven live
    (G#36/GH#64 PR #72 security review): a tag_name of
    '$(touch /tmp/x/PWNED)' survived the .sh path's own single-`\"`-escaping
    (POSIX double quotes do not stop $()/backtick command substitution)
    and ran on execution; the .cmd path has no escaping at all. No amount
    of escaping downstream is trustworthy for a string this shape-
    unconstrained -- validating at the source, before it ever reaches
    write_swap_script, and refusing anything that isn't a plain version
    number, is the actual fix, not a better escape."""
    if not isinstance(tag, str) or not (1 <= len(tag) <= 32):
        return False
    body = tag[1:] if tag[:1] in ("v", "V") else tag
    parts = body.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


class NoReleases(Exception):
    """The repository exists but has nothing published yet."""


def latest_release(timeout=10):
    """
    The highest-versioned published release.

    Not /releases/latest. GitHub picks that one by creation time, not by
    version, so re-tagging or a build that finishes out of order makes it point
    at an older release -- observed here reporting v0.1.0 as latest while
    v0.3.0 was published. Sorting the list by parsed version is the only answer
    that cannot be surprised by publish order.
    """
    request = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"Clickwork/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            releases = json.load(response)
    except Exception:
        return None
    if not isinstance(releases, list):
        return None
    usable = [r for r in releases
              if not r.get("draft") and not r.get("prerelease") and r.get("tag_name")]
    if not usable:
        raise NoReleases
    return max(usable, key=lambda r: _version_tuple(r["tag_name"]))


def pick_asset(release):
    """The download for this platform, by the suffix the workflow names it."""
    suffix = ASSET_SUFFIX.get(sys.platform if sys.platform in ASSET_SUFFIX
                              else "linux")
    for asset in (release or {}).get("assets", []):
        if asset.get("name", "").endswith(suffix):
            return asset
    return None


def is_frozen():
    """True inside a PyInstaller build -- only then is there anything to swap."""
    return getattr(sys, "frozen", False)


def _asset_dir():
    """
    Where the icon PNGs live -- inside PyInstaller's extracted bundle
    (sys._MEIPASS, populated by --add-data "assets:assets") when frozen,
    next to this file otherwise. Reuses is_frozen() rather than a second
    inline sys.frozen check.
    """
    if is_frozen():
        return os.path.join(sys._MEIPASS, "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _load_app_icon(root):
    """
    Loads the four bundled icon-*.png files from _asset_dir() and calls
    root.iconphoto(...) -- the one runtime path both AfkAutoclicker.__init__
    and selftest() go through, so a broken --add-data destination on any
    platform fails the same way (and is caught by selftest()) as it would in
    a real launch. A missing/unloadable PNG is a packaging bug, not bad user
    input, so this deliberately does not catch the exception
    (docs/CODING-GUIDELINES.md's input-validation section: fail visibly,
    don't guess) -- it raises rather than starting with a silently blank
    icon. Returns the PhotoImage list; the caller must keep a reference to
    it for as long as root is alive, or Tk silently drops the icon.
    """
    imgs = [
        tk.PhotoImage(master=root,
                      file=os.path.join(_asset_dir(), f"icon-{n}.png"))
        for n in (16, 32, 48, 256)
    ]
    root.iconphoto(True, *imgs)
    return imgs


def install_root():
    """
    The directory the updater replaces.

    On macOS sys.executable sits inside Contents/MacOS, but the thing that has
    to be swapped is the whole .app bundle, or Finder ends up with a half
    updated application.
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    marker = ".app" + os.sep + "Contents" + os.sep + "MacOS"
    if sys.platform == "darwin" and marker in exe_dir:
        return exe_dir[:exe_dir.index(marker) + 4]
    return exe_dir


CHECKSUM_ASSET = "SHA256SUMS"


def pick_checksums(release):
    for asset in (release or {}).get("assets", []):
        if asset.get("name") == CHECKSUM_ASSET:
            return asset
    return None


def fetch_checksums(asset, timeout=30):
    """
    The published digests, as {filename: sha256}.

    sha256sum's format is "<hex>  <name>", two spaces, and a leading "*" on the
    name marks binary mode -- strip it or nothing ever matches.
    """
    request = urllib.request.Request(
        asset["browser_download_url"],
        headers={"User-Agent": f"Clickwork/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            digest = parts[0].lower()
            if all(c in "0123456789abcdef" for c in digest):
                sums[parts[1].lstrip("*").strip()] = digest
    return sums


def file_digest(path, chunk=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


class ChecksumError(Exception):
    """The download does not match what the release published."""


def _safe_names(names, destination):
    """
    Reject any archive entry that would land outside the destination.

    zipfile's own extraction (extractall/extract, both branches below) has
    stripped ".."/"."/drive-letter/absolute-path components before joining
    onto the destination since Python 3.6.2 -- verified by reading the
    installed zipfile._extract_member source on both this sandbox's 3.11.2
    and this project's CI/release-pinned 3.12. The check below is defense
    in depth for zip: real security, not dependent on trusting a name string
    it never gets a chance to misuse.

    tarfile is the one that actually needs this: extractall(filter="data")
    -- the argument that closes the identical hole -- only exists from
    Python 3.12 and is only the default from 3.14. On 3.11 a bare
    extractall() silently restores every hole a crafted archive can hide
    (see _safe_tar_members's own docstring for the verified symlink escape).
    """
    root = os.path.realpath(destination)
    for name in names:
        target = os.path.realpath(os.path.join(root, name))
        if target != root and not target.startswith(root + os.sep):
            raise ChecksumError(f"archive entry escapes the staging directory: {name}")


def _safe_tar_members(members, destination):
    """
    Names plus entry kinds, checked here rather than left to tarfile.

    `extractall(filter="data")` does this from Python 3.12 and is the default
    from 3.14 -- but on 3.11 the argument does not exist, and falling back to a
    plain extractall silently restores every hole. Verified: a symlink to
    /etc/passwd was written to disk. Security that depends on the interpreter
    the user happens to have is not security, so the check is explicit.
    """
    _safe_names([m.name for m in members], destination)
    for member in members:
        if member.issym() or member.islnk():
            raise ChecksumError(f"archive contains a link entry: {member.name}")
        if member.isdev() or member.isfifo():
            raise ChecksumError(f"archive contains a device entry: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise ChecksumError(f"archive contains an unexpected entry: {member.name}")


def download_and_stage(asset, checksums, on_progress=None):
    """
    Fetch the release archive and unpack it into a staging directory.

    Staged next to the installation rather than inside it: the swap script has
    to delete the old contents wholesale, and it must not be deleting the very
    files it is copying from.

    checksums is required, not optional: it is the {filename: sha256} map the
    downloaded archive is verified against before anything is extracted. A
    default of None here would let a future caller skip verification just by
    forgetting the keyword -- the one thing this function exists to enforce.
    """
    workdir = tempfile.mkdtemp(prefix="clickwork-update-")
    archive = os.path.join(workdir, asset["name"])
    request = urllib.request.Request(
        asset["browser_download_url"],
        headers={"User-Agent": f"Clickwork/{__version__}"})
    with urllib.request.urlopen(request, timeout=60) as response, \
            open(archive, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(done / total)

    # Verify before unpacking, not after: extraction is the step that puts
    # attacker-controlled names onto the filesystem.
    #
    # No "if checksums is not None" guard here on purpose: checksums is a
    # required argument (see the docstring above), and a caller that passes
    # None explicitly has a bug, not a request to skip verification. Letting
    # `.get` raise AttributeError surfaces that immediately instead of
    # silently extracting an unverified archive.
    expected = checksums.get(asset["name"])
    if expected is None:
        # The fixed words must come first: the status line keeps only the
        # first 40 characters (afk_clicker.py:_install_worker), and a real
        # asset name ("Clickwork-linux-x86_64.tar.gz") is long enough on
        # its own to push "not listed in SHA256SUMS" past that budget if
        # it leads the message instead of trailing it.
        raise ChecksumError(
            f"checksum: not in {CHECKSUM_ASSET}: {asset['name']}")
    actual = file_digest(archive)
    if actual != expected:
        raise ChecksumError(
            f"checksum mismatch: expected {expected[:12]}…, got {actual[:12]}…")

    staged = os.path.join(workdir, "staged")
    os.makedirs(staged, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            _safe_names(zf.namelist(), staged)
            zf.extractall(staged)
    else:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            _safe_tar_members(members, staged)
            # filter="data" as well where it exists: belt and braces, and it
            # also strips ownership and permission bits we have no use for.
            try:
                tf.extractall(staged, members=members, filter="data")
            except TypeError:
                tf.extractall(staged, members=members)

    # The Linux and macOS archives keep their top-level folder; flatten it so
    # every platform hands the swap script the same shape.
    entries = os.listdir(staged)
    if len(entries) == 1 and os.path.isdir(os.path.join(staged, entries[0])):
        staged = os.path.join(staged, entries[0])
    return staged


def write_swap_script(staged, target, relaunch, log_path, target_version=None):
    """
    A tiny script that waits for this process to exit, replaces the install
    directory and starts the new build. It has to be an external process: a
    program cannot overwrite its own running executable on Windows, and on any
    platform deleting the code you are executing is asking for trouble.

    Also writes a step log to log_path, truncated fresh on every run (G#35/
    GH#63's "shipped update log" goal): a timestamped line for the start of
    the run, the wait finishing, the copy step's exit code, the relaunch
    attempt, and a final "done" line so a future launch of the app can tell
    an update died part-way (no "done") from one that finished. log_path is
    a required argument rather than something this function computes, so a
    caller always controls where it lands -- the real caller uses the
    settings directory (stable, findable at next launch); tests use a temp
    path so they never touch the real one. Its directory is created if
    missing.

    target_version, if given (G#36/GH#64), is the raw release tag ("vX.Y.Z")
    being installed -- recorded as a trailing ` version="..."` on the start
    line so a future launch can tell "the relaunch silently ran the old
    build" (done, but the wrong version) apart from "the copy/relaunch
    genuinely finished" (done, matching version), a distinction a bare
    "done" line can't make on its own. A keyword, default-None parameter,
    not a new required positional: omitting it is a legitimate, meaningful
    state ("version unknown"), and every existing call site keeps writing a
    byte-identical start line with nothing appended.
    """
    version_suffix = f' version="{target_version}"' if target_version else ""
    # The .sh branch's echo line is itself one big double-quoted string
    # (see below), so an unescaped `"` inside version_suffix would close
    # that string early and get silently swallowed by the shell rather
    # than land in the log -- confirmed the hard way (sabotage-verified in
    # tests/test_updater.py: the unescaped version produced `version=v0.7.0`
    # in the actual log, no quotes at all). \" keeps the quotes literal.
    sh_version_suffix = (f' version=\\"{target_version}\\"' if target_version else "")
    pid = os.getpid()
    # Two levels up from the staged tree is the temp working directory that
    # download_and_stage created. Guard it: with a shallow `staged` this walks
    # up to "/" and the script would be written to the filesystem root.
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(staged)))
    if not workdir or os.path.dirname(workdir) == workdir or not os.access(workdir, os.W_OK):
        workdir = tempfile.mkdtemp(prefix="clickwork-update-")
    log_dir = os.path.dirname(os.path.abspath(log_path))
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    if sys.platform == "win32":
        path = os.path.join(workdir, "apply-update.cmd")
        # `timeout /t 1 /nobreak` refuses redirected stdin ("ERROR: Input
        # redirection is not supported") and exits at once when the process
        # tree has no real console (see launch_swap_script) -- with no
        # sleep left in the loop that turns the wait into a tight busy-loop
        # of tasklist calls. `ping -n 2 127.0.0.1 >nul` is the conventional
        # console-free ~1s delay and needs nothing from stdin.
        #
        # %DATE% %TIME% is not delayed expansion -- it is the normal
        # parse-time substitution every %VAR% here already gets. The one
        # line inside a ( ... ) block (the final `done`) is therefore
        # stamped at the moment that whole if-block is parsed, a
        # negligible instant before it executes -- accurate enough for a
        # human-read log, and not worth enabling delayed expansion for
        # (that would make a literal `!` in a path -- Program Files paths
        # never have one, but the fixture below now covers it -- behave
        # differently).
        script = f'''@echo off
set "LOG={log_path}"
> "%LOG%" echo %DATE% %TIME% start pid={pid} staged="{staged}" target="{target}" relaunch="{relaunch}"{version_suffix}
set COUNT=0
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  set /a COUNT+=1
  ping -n 2 127.0.0.1 >nul
  goto wait
)
>> "%LOG%" echo %DATE% %TIME% wait finished after %COUNT% iterations
robocopy "{staged}" "{target}" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul
set RC=%ERRORLEVEL%
>> "%LOG%" echo %DATE% %TIME% copy exit code %RC%
start "" "{relaunch}"
>> "%LOG%" echo %DATE% %TIME% relaunch attempted
if %RC% LSS 8 (
  >> "%LOG%" echo %DATE% %TIME% done
)
'''
    else:
        path = os.path.join(workdir, "apply-update.sh")
        script = f'''#!/bin/sh
LOG="{log_path}"
: > "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') start pid={pid} staged={staged} target={target} relaunch={relaunch}{sh_version_suffix}" >> "$LOG"
COUNT=0
while kill -0 {pid} 2>/dev/null; do
  COUNT=$((COUNT + 1))
  sleep 1
done
echo "$(date '+%Y-%m-%d %H:%M:%S') wait finished after $COUNT iterations" >> "$LOG"
rm -rf "{target}."*  2>/dev/null
find "{target}" -mindepth 1 -delete 2>/dev/null
cp -a "{staged}/." "{target}/"
RC=$?
echo "$(date '+%Y-%m-%d %H:%M:%S') copy exit code $RC" >> "$LOG"
"{relaunch}" &
echo "$(date '+%Y-%m-%d %H:%M:%S') relaunch attempted" >> "$LOG"
if [ "$RC" -eq 0 ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') done" >> "$LOG"
fi
'''
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    if sys.platform != "win32":
        os.chmod(path, 0o755)
    return path


# ── reading the log back: did the last in-app update actually finish? ──────
# G#36/GH#64: everything below is a read-only consumer of the log
# write_swap_script writes above -- no change to the swap mechanism itself,
# and no network anywhere in this section (only Send via GitHub, in the
# dialog code further down, ever opens a browser).

_UPDATE_LOG_TAIL_BYTES = 1024 * 1024   # "Log absurdly large" (docs/spec.md
    # Edge cases): never load more than this, however the file got that big.


def read_update_log(log_path):
    """The decoded text of update.log, or None if it doesn't exist (or
    can't be read at all -- same "not worth crashing over" posture as
    Store.save()).

    Reads at most the last _UPDATE_LOG_TAIL_BYTES bytes via a seek from the
    end, so a corrupted/runaway log (a future script bug looping forever)
    can't make this read the whole file into memory. Decoded as UTF-8 with
    errors="replace": cmd's `echo ... > file` redirection writes bytes in
    the console's OEM code page on Windows (CP437/CP850, not UTF-8), and a
    non-ASCII username can put a byte sequence here that isn't valid UTF-8
    -- this must never raise or hang the startup dialog over an accented
    character, a `\ufffd` in the diagnostic tail is an acceptable trade
    (docs/spec.md Edge cases, "Log unreadable / garbled encoding")."""
    try:
        size = os.path.getsize(log_path)
    except OSError:
        return None
    try:
        with open(log_path, "rb") as fh:
            if size > _UPDATE_LOG_TAIL_BYTES:
                fh.seek(size - _UPDATE_LOG_TAIL_BYTES)
            data = fh.read()
    except OSError:
        return None
    return data.decode("utf-8", errors="replace")


def _extract_target_version(log_text):
    """Pulls the raw tag out of a start line's trailing `version="..."`
    field, or None if the field is absent (either an older-format log that
    predates this feature, or write_swap_script was called without
    target_version). Plain string search, not re: _version_tuple() just
    above already sets the precedent of parsing these ad hoc fields by hand
    rather than reaching for a new regex dependency."""
    marker = 'version="'
    start = log_text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = log_text.find('"', start)
    if end == -1:
        return None
    return log_text[start:end]


def update_log_status(log_path, current_version=__version__):
    """"ok" (nothing to report -- no log, or the last attempt finished and
    landed the expected version), "incomplete" (the log has no trailing
    `done` line -- the update died part-way), or "wrong_version" (the log
    ends with `done`, names a target version, and it doesn't match
    current_version -- the relaunch silently started the old build, a
    failure a bare `done` line can't otherwise reveal).

    An older-format log (`done`, no `version="..."` field at all) is
    treated as "ok", never "wrong_version" -- there is nothing to compare
    against (docs/spec.md "Edge cases", "Older-format logs")."""
    text = read_update_log(log_path)
    if text is None:
        return "ok"
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not lines[-1].strip().endswith("done"):
        return "incomplete"
    target_version = _extract_target_version(text)
    if target_version is None:
        return "ok"
    if _version_tuple(target_version) == _version_tuple(current_version):
        return "ok"
    return "wrong_version"


def _redact_home(text, home=None):
    """Every occurrence of the home directory replaced with `~`, the
    default state of the dialog's preview (docs/spec.md "Preview +
    consent"). Matched case-insensitively on Windows, since Windows paths
    are themselves case-insensitive -- `C:\\Users\\Leo` and
    `c:\\users\\leo` name the same directory. Plain string search, not re,
    same precedent as _extract_target_version above."""
    home = os.path.expanduser("~") if home is None else home
    if not home or not text:
        return text
    if sys.platform != "win32":
        return text.replace(home, "~")
    lower_text, lower_home = text.lower(), home.lower()
    pieces = []
    pos = 0
    idx = lower_text.find(lower_home)
    while idx != -1:
        pieces.append(text[pos:idx])
        pieces.append("~")
        pos = idx + len(home)
        idx = lower_text.find(lower_home, pos)
    pieces.append(text[pos:])
    return "".join(pieces)


GITHUB_ISSUE_URL_CAP = 2000   # docs/spec.md "Issue body": no documented
    # GitHub-specific number exists for the issues/new web-form URL; this is
    # the long-standing cross-browser/cross-OS convention (the legacy IE
    # ~2083-char cap, with headroom).
_ISSUE_LOG_TAIL_CHARS = 4000   # "read at most the log's last 4000 raw
    # characters" before the cap-driven shrink loop below even starts.
_ISSUE_TRUNCATION_MARKER = ("… (truncated — see update.log locally for the "
                            "full file) …")


def build_issue_url(title, body):
    """The plain, prefilled `issues/new` URL build_issue_report's (title,
    body) turns into -- no GitHub API call, no OAuth, just a URL the
    person's own browser opens (docs/spec.md "No GitHub API calls")."""
    query = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{GITHUB_REPO}/issues/new?{query}"


def build_issue_report(current_version, target_version, log_text, redact=True):
    """(title, body) for the prefilled GitHub issue -- the exact text the
    dialog previews and, once turned into a URL by build_issue_url(), the
    exact text `Send via GitHub` submits. redact=True (the dialog's
    default) replaces the home directory with `~` before anything else
    happens, so what's cut for the length cap below is whichever text was
    actually shown.

    The body's log tail shrinks (oldest lines dropped first, a truncation
    marker prefixed) until the *encoded URL* -- title and body together --
    fits GITHUB_ISSUE_URL_CAP; the log's own format is compact enough
    (docs/spec.md "Issue body") that this loop only ever does real work on
    an unexpectedly huge or corrupt log."""
    if target_version:
        title = f"Update from v{current_version} to {target_version} didn't finish"
    else:
        title = f"In-app update didn't finish (v{current_version})"

    text = log_text or ""
    if redact:
        text = _redact_home(text)

    tail = text[-_ISSUE_LOG_TAIL_CHARS:]
    truncated = len(tail) < len(text)
    lines = tail.splitlines()

    def _body(lines_subset, was_truncated):
        content = "\n".join(lines_subset)
        if was_truncated:
            content = f"{_ISSUE_TRUNCATION_MARKER}\n{content}"
        target_line = target_version or "unknown (older log format)"
        return (f"**App version:** {current_version}\n"
                f"**Target version:** {target_line}\n"
                f"**OS:** {platform.platform()} ({sys.platform})\n"
                f"\n"
                f"```\n"
                f"update.log\n"
                f"{content}\n"
                f"```\n")

    body = _body(lines, truncated)
    while len(build_issue_url(title, body)) > GITHUB_ISSUE_URL_CAP and lines:
        lines = lines[1:]           # drop the oldest kept line first
        truncated = True
        body = _body(lines, truncated)
    return title, body


def launch_swap_script(script):
    """
    Launches the swap script written by write_swap_script so it survives
    this process exiting right after -- write_swap_script's own wait loop
    depends on that actually happening. Extracted out of _quit_for_update so
    the Windows acceptance test (tests/test_updater.py) calls this exact
    function instead of a hand-copied mirror that could silently drift from
    what production actually runs.

    G#35/GH#63: on windows-latest CI, the previous flags (DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP, no stdio kwargs) reliably stalled the tree at
    its very first `tasklist /FI ... | find ...` in write_swap_script's wait
    loop -- the update.log written under those flags contained only the
    `start pid=...` line, never `wait finished`, confirming the stall
    happens before a single wait iteration completes. *Why* that pipeline
    hangs without a console is not established (DETACHED_PROCESS does not
    forbid a child from allocating its own console -- that allocation is
    plausibly the flash Leo saw); only that it does, there, and that it
    doesn't under the flags below: CREATE_NO_WINDOW gives the whole tree one
    real, hidden console to share instead, and the same update.log
    completes end to end (wait finished, copy exit code, done) under it.
    Explicit DEVNULL stdio means no handle is left ambiguous either way.
    """
    if sys.platform == "win32":
        subprocess.Popen(
            ["cmd", "/c", script],
            creationflags=0x08000000 | 0x00000200,  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["/bin/sh", script], start_new_session=True)


# ── per-game settings, on disk ────────────────────────────────────────────
# Every game keeps its own clicker configuration, so switching from Minecraft
# to something else does not mean re-typing an interval. Stored as one JSON
# file in the platform's usual config location -- next to the executable would
# break the moment the program lands in Program Files.

APP_DIR_NAME = "AFKFarmClicker"


def config_path():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_DIR_NAME, "settings.json")
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_DIR_NAME}/settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "afk-farm-clicker", "settings.json")


class Store:
    """Load once, save on change. A corrupt file is replaced, never fatal."""

    def __init__(self, path=None):
        self.path = path or config_path()
        self.data = {"games": {}, "hotkey": None, "selected": None,
                     "appearance": "system", "ui_scale": UI_SCALE_DEFAULT}
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.data})
        except (OSError, ValueError):
            pass                      # missing or damaged -> start from defaults

        # The same "corrupt file is replaced, never fatal" contract applies
        # one level down: a valid-JSON-wrong-shape "games" (not a dict, or a
        # per-game entry that isn't one -- null/list/str instead of {}) is as
        # untrustworthy as a damaged file. Nothing above validates that shape,
        # so every reader of self.data["games"] -- this migration, game(),
        # and the profile-defaults merge in _select() -- inherits whatever
        # crashes it inherits. Dropping the offending entries here, once,
        # keeps that guarantee in the one place that already does this kind
        # of filtering instead of pushing an isinstance check onto each
        # reader individually.
        games = self.data.get("games")
        if not isinstance(games, dict):
            games = {}
        self.data["games"] = {gid: g for gid, g in games.items()
                               if isinstance(g, dict)}

        # Same contract, one key: a garbage on-disk "appearance" (wrong type,
        # a typo, an old story.md-draft "theme"-style value, null) is as
        # untrustworthy as a damaged file -- resolve_appearance()/
        # set_active_theme() never see it unvalidated.
        if self.data["appearance"] not in ("system", "light", "dark"):
            self.data["appearance"] = "system"

        # Same contract, one more key: a garbage on-disk "ui_scale" (wrong
        # type, an old/foreign value, a hand-edited "120") is as
        # untrustworthy as a damaged file -- self.s never sees it unvalidated.
        if self.data["ui_scale"] not in UI_SCALE_FACTORS and self.data["ui_scale"] != "auto":
            self.data["ui_scale"] = UI_SCALE_DEFAULT

        # _persist() writes this value to disk automatically the first time
        # Minecraft is ever selected -- including the automatic _select() a
        # window-detection triggers, before a user touches the field -- so a
        # stored 510 (the old default) is that auto-save having happened, not
        # a deliberate choice; any other value is left alone because it is.
        # In-memory only: this does not call save() itself, so the corrected
        # value reaches disk the same way the old default did -- via the next
        # natural _persist() (selecting Minecraft, which happens automatically
        # on detection) -- rather than Store.__init__ taking on a write it
        # has never performed before.
        if self.data["games"].get("minecraft", {}).get("click_ms") == 510:
            self.data["games"]["minecraft"]["click_ms"] = 650

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)     # atomic: never leave a half-written file
            return True
        except OSError:
            return False                   # read-only home is not worth crashing over

    def game(self, game_id):
        return self.data["games"].setdefault(game_id, {})

    def put_game(self, game_id, values):
        self.data["games"][game_id] = values
        return self.save()


# ── game profiles ─────────────────────────────────────────────────────────
# A profile is what the program should look like for one game. Only Minecraft
# carries real tuning here, because that is the only game whose numbers I can
# actually vouch for -- inventing plausible-sounding intervals for other games
# would be worse than offering none. Adding one is a dict: give it window-title
# fragments to recognise, a default interval, and whether the eating panel
# applies.

PROFILES = [
    {
        "id": "minecraft",
        "name": "Minecraft",
        "titles": ("minecraft",),
        "eating": True,
        "note": "650 ms: Java sword full charge is 600 ms (12 ticks), +1 tick margin.",
        "defaults": {"click_ms": 650, "jitter_ms": 0, "autostop_min": 0,
                     "button": "left", "eat_mode": "pause",
                     "eat_every": 75, "eat_hold": 2.0},
        "min_sweep_ms": DEFAULT_CLICK_MS,   # G#22: the only profile whose
                                             # numbers this hint applies to
    },
    {
        "id": "global",
        "name": "Global",
        "titles": (),                 # never auto-detected; the fallback
        "eating": False,
        "note": "Applies when nothing more specific is selected.",
        "defaults": {"click_ms": 250, "jitter_ms": 0, "autostop_min": 0,
                     "button": "left", "eat_mode": "off",
                     "eat_every": 75, "eat_hold": 2.0},
        "min_sweep_ms": None,
    },
]
GENERIC_DEFAULTS = dict(PROFILES[-1]["defaults"])


def make_profile(game_id, name, title_fragment):
    """A game the user added from whatever window was in front."""
    return {"id": game_id, "name": name, "titles": (title_fragment.lower(),),
            "eating": False, "note": "Added from the active window.",
            "defaults": dict(GENERIC_DEFAULTS), "custom": True,
            "min_sweep_ms": None}




_THEME_DETECT_TIMEOUT = 2   # generous for a local registry/gsettings/defaults
                             # call, short enough to never visibly stall the
                             # first frame -- shorter than _window_titles's 5s
                             # because that's a background poll, this blocks
                             # startup once.


def _run_theme_command(args):
    """The command-runner seam: real subprocess in production, swapped out
    wholesale in tests so no real `defaults`/`gsettings` call happens on a
    machine that may not have one. Never shell=True -- args is always a
    list. Only ever invoked from the darwin/linux branches below, so unlike
    the swap-script Popen call (afk_clicker.py:1528-1529) there is no
    Windows console-flash to guard against with creationflags here -- this
    never runs on win32 at all; Windows reads the registry directly instead.
    errors="replace" keeps a stray non-UTF-8 byte from raising
    UnicodeDecodeError: the garbled-but-decodable result then falls through
    the normal "unrecognized value" handling in _detect_linux_theme/
    detect_os_theme, rather than needing a fourth failure mode of its own.
    encoding="utf-8" is explicit rather than left to default: without it,
    text=True decodes with subprocess._text_encoding()'s fallback,
    locale.getencoding(), which is cp1252 on Windows -- a single-byte
    codepage with a glyph for every byte, so it never raises
    UnicodeDecodeError and errors="replace" never fires.
    gsettings/defaults both emit UTF-8 regardless of the host locale, so
    decoding as UTF-8 is correct on every platform this ever runs on
    (darwin/linux only -- see the docstring above)."""
    return subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=_THEME_DETECT_TIMEOUT, check=True)


def _read_windows_theme_registry():
    """The registry-reader seam. winreg only exists on Windows, so the import
    stays lazy and inside this one function -- same reason ctypes.windll is
    imported inside _window_titles's win32 branch, not at module level.
    Any failure here (missing key/value -> FileNotFoundError, or any other
    OSError/PermissionError) is an OSError, which the caller's blanket
    `except Exception` in detect_os_theme already catches -- no separate
    try/except needed in this function itself."""
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
    try:
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value
    finally:
        winreg.CloseKey(key)


def _detect_linux_theme():
    """gsettings color-scheme first (GNOME 42+); gtk-theme name as the
    fallback for older GNOME. A 'default'/unrecognized/failed color-scheme
    falls through to gtk-theme rather than going straight to Dark --
    'default' means "no explicit preference stated", not "detection
    failed", and giving up there would make Light mode unreachable for most
    non-bleeding-edge GNOME desktops, defeating the whole point of the
    fallback."""
    try:
        out = _run_theme_command(["gsettings", "get",
            "org.gnome.desktop.interface", "color-scheme"])
        value = out.stdout.strip().strip("'")
        if value == "prefer-dark":
            return "dark"
        if value == "prefer-light":
            return "light"
        # "default", empty, or anything else unrecognized: fall through.
    except Exception:
        pass   # missing gsettings, missing schema/key (older GNOME), timeout
    try:
        out = _run_theme_command(["gsettings", "get",
            "org.gnome.desktop.interface", "gtk-theme"])
        name = out.stdout.strip().strip("'").lower()
        if not name:
            return "dark"   # exit 0 with nothing to read is the "unparseable
                             # output" case -- fail safe, don't guess.
        # Known limitation: this substring check misclassifies real, popular
        # dark GTK themes whose names don't contain "dark" (e.g. "Dracula",
        # "Nordic" -> "light"). A name list would never be complete, so this
        # is left as-is; Feature 3's Settings-tab override is the intended
        # way for an affected user to correct it, not a growing allow-list
        # here.
        return "dark" if "dark" in name else "light"
    except Exception:
        return "dark"   # chain ends here; no further fallback.


def detect_os_theme():
    """
    Which THEMES key best matches the OS's own light/dark setting, checked
    once at startup (no runtime polling -- ROADMAP.md already flags the
    existing 5s X11 walk as a battery cost, and this is a purely cosmetic
    follow that doesn't need to be live). Never raises: any exception, a
    missing binary/registry value, a timeout, or output that doesn't parse
    all resolve to "dark", because that's what the app already ships today
    -- an undetectable OS is the least-surprising possible regression, never
    a broken or half-themed window.
    """
    try:
        if sys.platform == "win32":
            return "light" if _read_windows_theme_registry() == 1 else "dark"
        if sys.platform == "darwin":
            # Apple's own convention: AppleInterfaceStyle exists (and reads
            # "Dark") only in dark mode; light mode has no key at all, so a
            # clean nonzero exit *is* light, not a failure. Only a launch
            # failure/timeout -- caught by the outer except below -- means
            # "couldn't tell".
            try:
                _run_theme_command(["defaults", "read", "-g",
                                     "AppleInterfaceStyle"])
            except subprocess.CalledProcessError:
                return "light"
            return "dark"
        if sys.platform.startswith("linux"):
            return _detect_linux_theme()
    except Exception:
        pass
    return "dark"


def _window_titles():
    """
    Every visible window title, which is how the game gets recognised.

    Titles rather than process names on purpose: on Windows Minecraft is
    `javaw.exe`, which is also every other Java program on the machine, while
    the window is reliably called "Minecraft <version>".
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        titles = []
        user32 = ctypes.windll.user32
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    titles.append(buf.value)
            return True

        user32.EnumWindows(proto(collect), 0)
        return titles

    if sys.platform == "darwin":
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of every process '
             'whose background only is false'],
            capture_output=True, text=True, timeout=5)
        return [t.strip() for t in out.stdout.split(",") if t.strip()]

    # X11. python-xlib is already installed as a pynput dependency, so this
    # costs nothing extra.
    from Xlib import display as xdisplay
    disp = xdisplay.Display()
    titles = []

    def walk(window, depth=0):
        if depth > 4:
            return
        try:
            name = window.get_wm_name()
            if name:
                titles.append(name if isinstance(name, str) else name.decode("utf-8", "replace"))
            for child in window.query_tree().children:
                walk(child, depth + 1)
        except Exception:
            pass

    walk(disp.screen().root)
    disp.close()
    return titles


def detect_running(profiles):
    """Ids of every profile whose title fragment is currently on screen."""
    try:
        haystack = " | ".join(_window_titles()).lower()
    except Exception:
        return set()
    return {p["id"] for p in profiles
            if p["titles"] and any(f in haystack for f in p["titles"])}


def foreground_title():
    """Best guess at what the user is playing, for 'add this game'."""
    try:
        titles = [t for t in _window_titles() if t and t.strip()]
    except Exception:
        return None
    # The frontmost window is last in X11's tree walk and first from EnumWindows.
    return (titles[0] if sys.platform == "win32" else titles[-1]) if titles else None


class Button(tk.Canvas):
    """Canvas button, because tk.Button cannot do rounded corners or hover."""

    def __init__(self, parent, text, command, s, primary=False, width=120, height=34):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=int(width * s), height=int(height * s), cursor="hand2")
        self.command = command
        self.primary = primary
        self._enabled = True
        self.s = s
        w, h = int(width * s), int(height * s)
        self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=CARD, outline=LINE)
        self.label = self.create_text(w / 2, h / 2, text=text, fill=INK,
                                      font=("Segoe UI", fs(9.5, s), "bold"))
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<Button-1>", self._click)
        self._paint()

    def _colors(self, hover):
        if not self._enabled:
            return CARD, LINE, MUTED
        if self.primary:
            return (ACCENT_HI, ACCENT_HI, ACCENT_INK) if hover else (ACCENT, ACCENT, ACCENT_INK)
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

    def set_text(self, text):
        self.itemconfig(self.label, text=text)


class Segmented(tk.Canvas):
    """A segmented control -- the modern replacement for a column of radios."""

    def __init__(self, parent, options, variable, s, width=CARD_INNER_W, height=34):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=int(width * s), height=int(height * s), cursor="hand2")
        self.options = options                # [(value, label), ...]
        self.var = variable
        self.s = s
        self.w, self.h = int(width * s), int(height * s)
        self.create_rectangle(0, 0, self.w, self.h, fill=BG, outline=LINE)
        seg = self.w / len(options)
        self.pill = self.create_rectangle(2, 2, seg - 2, self.h - 2,
                                          fill=CARD_HI, outline="")
        self.texts = [
            self.create_text(seg * i + seg / 2, self.h / 2, text=lbl, fill=MUTED,
                             font=("Segoe UI", fs(9, s)))
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
        self.coords(self.pill, seg * idx + 2, 2, seg * (idx + 1) - 2, self.h - 2)
        for i, item in enumerate(self.texts):
            self.itemconfig(item, fill=INK if i == idx else MUTED)


class ToggleCheckbox(tk.Canvas):
    """G#36/GH#64's update-log dialog needs a checkbox and this file has
    never had one (docs/design.md "New minimal component") -- every other
    control here (Button, Segmented, TabBar above) is already a plain
    canvas shape rather than a native ttk/tk widget, so this follows the
    same pattern instead of introducing the one native tk.Checkbutton in
    an otherwise fully custom-drawn UI.

    Unchecked: CARD fill, MUTED outline (not LINE -- LINE fails the WCAG
    1.4.11 3:1 floor for a UI component here, MUTED clears it in both
    themes, docs/design.md's contrast table). Checked: CARD_HI fill plus a
    centered checkmark glyph in INK -- dual signaling (fill *and* glyph),
    not fill alone, so the state still reads for a color-blind viewer.
    Hover swaps the unchecked fill to CARD_HI for feedback; the checked
    fill has nowhere further to go without a new color-manipulation helper
    this file doesn't otherwise have, so it stays CARD_HI on hover too --
    a smaller deviation from docs/design.md's "slightly darker shade" than
    inventing a one-off darken() for a single hover microstate."""

    def __init__(self, parent, variable, s, size=16):
        px = int(size * s)
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=px, height=px, cursor="hand2", takefocus=1)
        self.var = variable
        self.px = px
        self.box = self.create_rectangle(1, 1, px - 1, px - 1, fill=CARD, outline=MUTED)
        self.check = self.create_text(px / 2, px / 2, text="✓", fill=INK,
                                      font=("Segoe UI", fs(8, s), "bold"),
                                      state="hidden")
        self.focus_ring = self.create_rectangle(
            0, 0, px, px, outline=ACCENT, width=2, dash=(2, 2), state="hidden")
        self._hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<FocusIn>", lambda e: self.itemconfig(self.focus_ring, state="normal"))
        self.bind("<FocusOut>", lambda e: self.itemconfig(self.focus_ring, state="hidden"))
        self.var.trace_add("write", lambda *_a: self._paint())
        self._paint()

    def _set_hover(self, hover):
        self._hover = hover
        self._paint()

    def _toggle(self, _event=None):
        self.var.set(not self.var.get())
        return "break"

    def _paint(self):
        checked = bool(self.var.get())
        self.itemconfig(self.check, state="normal" if checked else "hidden")
        fill = CARD_HI if (checked or self._hover) else CARD
        self.itemconfig(self.box, fill=fill, outline=MUTED)


class TabBar(tk.Canvas):
    """Left-aligned, natural-width tabs with an active-tab underline -- the
    NVIDIA-reference pattern (handoff/nvidia-reference/*.png), distinct from
    Segmented's equal-width filled-pill selector (see docs/spec.md's 'Why
    Segmented cannot serve as the tab bar' section, story #24 feature 2)."""

    def __init__(self, parent, options, variable, s, height=TAB_HEIGHT):
        self.s = s
        self.options = options                # [(value, label), ...]
        self.var = variable
        # Bold width is the layout width for every tab, active or not, so
        # the active tab going bold never shifts anything else -- all
        # geometry is computed once here, and only fill colors and the
        # underline's position change afterward, in _paint().
        font_size = fs(9.5, s)
        font = ("Segoe UI", font_size, "bold")
        measurer = tkfont.Font(family="Segoe UI", size=font_size, weight="bold")
        gap = int(TAB_GAP * s)
        x = 0
        self._tabs = []                       # [(value, label, x1, x2, text_id), ...]
        for value, label in options:
            w = measurer.measure(label)
            self._tabs.append([value, label, x, x + w, None])
            x += w + gap
        total_w = max(x - gap, 0)
        h = int(height * s)
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=total_w, height=h, cursor="hand2")
        # Full-width separator first (bottom of the pane's z-order), so the
        # active-tab underline -- created last, below -- paints on top of it
        # where their y-ranges overlap; elsewhere the faint LINE divider
        # shows through under every inactive tab.
        self.create_line(0, h - 1, total_w, h - 1, fill=LINE, width=1)
        for tab in self._tabs:
            value, label, x1, x2, _tid = tab
            tab[4] = self.create_text((x1 + x2) / 2, (h - TAB_PAD_BOTTOM * s) / 2,
                                      text=label, font=font)
        underline_h = int(TAB_UNDERLINE_H * s)
        self.underline = self.create_rectangle(0, h - underline_h, 0, h,
                                               fill=ACCENT, outline="")
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *_a: self._paint())
        self._paint()

    def _click(self, event):
        for value, _label, x1, x2, _tid in self._tabs:
            if x1 <= event.x < x2 + int(TAB_GAP * self.s):
                self.var.set(value)
                return

    def _paint(self):
        current = self.var.get()
        h = int(TAB_HEIGHT * self.s)
        for value, _label, x1, x2, text_id in self._tabs:
            self.itemconfig(text_id, fill=INK if value == current else MUTED)
        active = next((t for t in self._tabs if t[0] == current), self._tabs[0])
        _value, _label, x1, x2, _tid = active
        underline_h = int(TAB_UNDERLINE_H * self.s)
        self.coords(self.underline, x1, h - underline_h, x2, h)


class StatusPill(tk.Canvas):
    """The one thing you read from across the room, so it gets real estate."""

    def __init__(self, parent, s, width=CONTENT_W, height=58):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=int(width * s), height=int(height * s))
        self.s = s
        w, h = int(width * s), int(height * s)
        self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=CARD, outline=LINE)
        self.dot = self.create_oval(20 * s, h / 2 - 4.5 * s, 29 * s, h / 2 + 4.5 * s,
                                    fill=BAD, outline="")
        self.text = self.create_text(42 * s, h / 2, anchor="w", text="OFF", fill=INK,
                                     font=("Segoe UI", fs(11.5, s), "bold"))
        self.hint = self.create_text(w - 20 * s, h / 2, anchor="e", text="", fill=MUTED,
                                     font=("Segoe UI", fs(8.5, s)))

    def set(self, text, color, hint=""):
        self.itemconfig(self.text, text=text, fill=color)
        self.itemconfig(self.dot, fill=color)
        self.itemconfig(self.hint, text=hint)


def fmt_num(value):
    """510.0 -> "510". Values round-trip through float() on save, and a field
    that reads back "510.0" after a restart looks like a bug to the user."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def section(parent, text, s, top=14, action_factory=None):
    """A pane's own sub-heading -- sentence case (story #24 feature 5 dropped
    the old upper() + 8pt small-caps treatment once uppercasing stopped
    doing the compensating). `action_factory`, not a pre-built widget: a Tk
    widget's parent is fixed at construction, so a caller can't hand this a
    widget built against some other parent and have it retroactively
    reparent into `row` -- a factory (callable(row) -> widget) lets the
    caller build directly against the real parent. Returns `row` (a Frame)
    rather than the bare label, so existing callers' .pack()/.pack_forget()
    keep working unchanged."""
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(int(top * s), int(6 * s)))
    label = tk.Label(row, text=text, bg=BG, fg=MUTED, anchor="w",
                     font=("Segoe UI", fs(10, s), "bold"))
    label.pack(side="left")
    if action_factory is not None:
        action_factory(row).pack(side="right")
    return row


def card(parent, s, on_settle=None):
    """Borderless flat card: a canvas shell hosting a plain Frame via
    create_window -- the standard Tk technique for placing a real widget
    tree inside a canvas-drawn shape.

    `on_settle`, if given, is called at the tail of every _redraw() --
    i.e. every single time this card's shell actually finishes resizing to
    a new real height, including from an idle callback serviced well after
    whatever caller originally triggered it has already returned (G#28/
    GH#48). This is how a card whose visibility toggles at runtime (the
    Eating card, story #24 feature 4) notifies its owning pane to recompute
    its fill spacers once the card's own height is actually final, instead
    of the pane measuring a `natural` span against content that may still
    be mid-resize -- toggling a child's pack state inside a
    pack_propagate(False) pane produces no <Configure> on the pane itself
    (Empirical grounding #2, _select()'s own comment), so nothing else ever
    re-triggers that recompute once this card's own deferred growth lands.
    Harmless for a card whose content never changes after construction
    (every other call site): _redraw() converges to a fixed height quickly
    and on_settle() calling _fill_pane() again is already idempotent (see
    its own docstring)."""
    pad = int(CARD_PAD * s)        # inset between the shell's own edge and
                                    # inner's content -- CARD_INNER_W's
                                    # formula depends on this exact value.
    shell = tk.Canvas(parent, bg=parent.cget("bg"), highlightthickness=0)
    shell.pack(fill="x")
    inner = tk.Frame(shell, bg=CARD)
    win_id = shell.create_window(pad, pad, window=inner, anchor="nw")
    shape_id = None

    def _redraw(_event=None):
        nonlocal shape_id
        if not shell.winfo_exists():
            return                      # a torn-down card fielding a stale/
                                         # late <Configure> for a tree that
                                         # is already gone -- nothing to redraw
        inner.update_idletasks()
        if not shell.winfo_exists():
            return                      # update_idletasks() can itself run
                                         # another already-queued idle
                                         # callback (e.g. a rebuild) that
                                         # destroys this very card while this
                                         # call is still on the stack -- see
                                         # _rebuild_ui()'s docstring
        w = shell.winfo_width() or (inner.winfo_reqwidth() + 2 * pad)
        h = inner.winfo_reqheight() + 2 * pad
        shell.config(height=h)
        shell.itemconfig(win_id, width=w - 2 * pad)
        if shape_id is not None:
            shell.delete(shape_id)
        shape_id = shell.create_rectangle(0, 0, w, h, fill=CARD, outline="")
        shell.tag_lower(shape_id)      # behind inner, so inner's own content
                                        # paints on top of the shell's fill.
        if on_settle is not None:
            on_settle()

    shell.bind("<Configure>", _redraw)
    inner.bind("<Configure>", _redraw)
    _redraw()
    return inner


def _fill_pane(pane, top_spacer, bottom_spacer):
    """Recompute this pane's own top/bottom margin from its *current* real
    available height vs. its own real content height -- safe to call
    repeatedly, including from a live resize drag (story #24 feature 4).

    Mirrors card()'s own _redraw() above in two ways that are load-bearing,
    not stylistic: update_idletasks() BEFORE reading geometry (a pre-map
    winfo_height() is Tk's `1` placeholder, not the real value), and the
    same two winfo_exists() guards, for the same reason card()'s docstring
    gives: update_idletasks() can itself reentrantly service an
    already-queued idle callback (e.g. a pending _rebuild_ui()) that
    destroys this very pane while this call is still on the stack.

    `natural` is measured as the span (lowest real bottom edge minus
    highest real top edge, both winfo_y()-based) of the pane's mapped
    non-spacer children, not a sum of their own winfo_reqheight() -- a
    plain reqheight sum silently drops any pack()-level pady between direct
    children (e.g. section()'s own label pady, or eat_section's pady when
    shown), which is real space pack actually consumes; measured
    empirically (Xvfb probe, not committed), a reqheight-sum-based
    `natural` undercounted the Hotkey pane by exactly section()'s 6px
    trailing pady, oversizing `extra` and having the excess silently
    absorbed by Tk shrinking the bottom spacer below its own configured
    height. This span measurement needs no "reset spacers to 0 first"
    step -- it excludes the spacers by identity and is translation-
    invariant in the top spacer's own current height (shifting every
    non-spacer child down by the same amount changes neither the span nor
    `pane`'s own externally-set winfo_height(), the latter now genuinely
    independent of any child thanks to pack_propagate(False) on every pane
    -- see _build_content()'s hotkey_pane comment). That independence
    matters here for another, sharper reason: Tk silently IGNORES
    `config(height=0)` on a plain Frame -- treated as "no explicit height"
    rather than "make it 0px" -- confirmed empirically, so a reset-to-0
    step would not even have worked; the floor below (max(1, ...)) is the
    real fix, not merely a rounding nicety.

    G#28/GH#48 round 4 (Windows CI trace, docs/implementation.md): the
    `max(1, ...)` floor on each spacer -- needed so neither is ever handed
    a literal 0 -- can itself push their combined height 1-2px past the
    pane's real leftover (`available - natural`) once that leftover is only
    0 or 1px, which is exactly the margin Windows' own taller font metrics
    left at WINDOW_MIN_H's floor (natural=367 vs avail=368). pack() then
    has more to fit than the pane's fixed height actually has and
    permanently unmaps whichever spacer is last in packing order (bottom).
    The clamp below re-trims the floored pair back down so their sum can
    never exceed the pane's real leftover, closing that overflow by
    construction rather than by timing; _set_spacer_height() below is the
    backstop for the residual case where the pane is genuinely fuller than
    its own floor allows (both spacers already at the 1px floor, nothing
    left to trim) -- a spacer pack() gives up on there does not, on its
    own, ever get reconsidered later (confirmed against the real trace:
    frozen across nine further calls and ten passive event-loop pumps), so
    every call here re-maps one that isn't, instead of trusting it stayed
    mapped from whenever it was last touched."""
    if not pane.winfo_exists():
        return
    pane.update_idletasks()
    if not pane.winfo_exists():
        return
    available = pane.winfo_height()
    kids = [c for c in pane.winfo_children()
            if c.winfo_ismapped() and c not in (top_spacer, bottom_spacer)]
    natural = (max(c.winfo_y() + c.winfo_height() for c in kids)
               - min(c.winfo_y() for c in kids)) if kids else 0
    extra = max(0, available - natural)
    top_h = int(extra * FILL_TOP_SHARE)
    bottom_h = extra - top_h
    # Never write a literal 0 (see docstring): Tk ignores it, which would
    # leave a spacer stuck at its last nonzero height when shrinking back
    # toward the floor. max(1, ...) is exactly the "<=1px" floor the
    # acceptance criteria already call for, not a new tolerance.
    top_h = max(1, top_h)
    bottom_h = max(1, bottom_h)
    # Clamp (see docstring): trim whichever spacer is larger back down
    # until the pair's sum no longer exceeds the real leftover, so pack()
    # is never handed a share bigger than the pane actually has. Loops at
    # most twice -- the floor above can only ever have added 1px to each
    # side -- and stops once both are at the 1px floor with nothing left
    # to give back.
    overflow = (top_h + bottom_h) - extra
    while overflow > 0 and (top_h > 1 or bottom_h > 1):
        if bottom_h >= top_h and bottom_h > 1:
            bottom_h -= 1
        elif top_h > 1:
            top_h -= 1
        else:
            bottom_h -= 1
        overflow -= 1
    _set_spacer_height(top_spacer, top_h)
    _set_spacer_height(bottom_spacer, bottom_h)


def _set_spacer_height(spacer, height):
    """Write a _fill_pane() spacer's height and, if pack() had already
    given up on mapping it, ask it to reconsider now that the request has
    changed (G#28/GH#48 round 4). Tk's packer does not retry an unmapped
    slave on its own once it decides there is no room for it -- confirmed
    against the Windows CI trace, where an unmapped spacer's own
    winfo_height() stayed frozen at its last mapped value across nine
    further _fill_pane() calls and ten passive event-loop pumps -- only a
    fresh pack() call, not a plain config(), makes it reconsidered. Calling
    pack() again with the same fill="x" option every spacer is already
    packed with at construction is safe every time, mapped or not: it does
    not change the spacer's position in the pane's packing order (no
    -before/-after given), and is a geometry-request no-op when nothing
    actually changed."""
    spacer.config(height=height)
    if not spacer.winfo_ismapped():
        spacer.pack(fill="x")


class GameItem(tk.Canvas):
    """One row in the sidebar: a state dot, the name, and a hover/selected fill.

    Story #24 feature 3: `collapsed` decides what's drawn, not how it's
    painted -- expanded draws the dot-and-name pair as always; collapsed
    draws a centered badge (the same create_oval dot, just bigger and
    centered) with the profile's initial letter in place of the name.
    _paint() below needs zero branching for this: it only ever itemconfigs
    self.shape/self.dot/self.text by their stored canvas-item ids, and the
    same fill rules are correct whichever pair those ids point at."""

    def __init__(self, parent, profile, on_click, s, collapsed=False,
                 width=None, height=38):
        if width is None:
            width = SIDEBAR_RAIL_W - 16 if collapsed else SIDEBAR_W - 16
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, cursor="hand2",
                         width=int(width * s), height=int(height * s))
        self.profile = profile
        self.on_click = on_click
        self.collapsed = collapsed
        self.selected = False
        self.running = False
        w, h = int(width * s), int(height * s)
        self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=BG, outline="")
        bar_w = int(3 * s)     # ux-designer's call (docs/design.md #2); floor
                                # is TAB_UNDERLINE_H's own 2px @ s=0.675.
        self.accent_bar = self.create_rectangle(0, 0, bar_w, h, fill=ACCENT,
                                                outline="", state="hidden")
        if collapsed:
            d = COLLAPSED_BADGE_D * s
            cx, cy = w / 2, h / 2
            self.dot = self.create_oval(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2,
                                        fill=LINE, outline="")
            initial = profile["name"][:1].upper() if profile["name"] else "?"
            self.text = self.create_text(cx, cy, anchor="center", text=initial,
                                         fill=MUTED, font=("Segoe UI", fs(10.5, s), "bold"))
        else:
            self.dot = self.create_oval(12 * s, h / 2 - 3.5 * s, 19 * s, h / 2 + 3.5 * s,
                                        fill=LINE, outline="")
            self.text = self.create_text(30 * s, h / 2, anchor="w", text=profile["name"],
                                         fill=MUTED, font=("Segoe UI", fs(9.5, s)))
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<Button-1>", lambda e: self.on_click(self.profile["id"]))
        self._paint()

    def set_state(self, selected=None, running=None):
        if selected is not None:
            self.selected = selected
        if running is not None:
            self.running = running
        self._paint()

    def _paint(self, hover=False):
        fill = CARD_HI if self.selected else (CARD if hover else BG)
        self.itemconfig(self.shape, fill=fill)
        self.itemconfig(self.text, fill=INK if (self.selected or self.running) else MUTED)
        self.itemconfig(self.dot, fill=OK if self.running else LINE)
        self.itemconfig(self.accent_bar, state="normal" if self.selected else "hidden")


class SettingsItem(tk.Canvas):
    """The sidebar's one non-game destination. Structurally a GameItem minus
    the running-state dot -- there is nothing to run -- and with no profile
    behind it: `on_click` takes no id, it just opens Settings.

    Feature 3b's `has_update` is the off-screen signal for a pending update
    found while Settings isn't open (or never opened this session) -- see
    docs/history/ac-17-f3b-spec.md §1. Deliberately text, not a dot: 3a's own design already
    rejected a dot for this row."""

    def __init__(self, parent, on_click, s, has_update=False, collapsed=False,
                 width=None, height=38):
        if width is None:
            width = SIDEBAR_RAIL_W - 16 if collapsed else SIDEBAR_W - 16
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, cursor="hand2",
                         width=int(width * s), height=int(height * s))
        self.on_click = on_click
        self.collapsed = collapsed
        self.selected = False
        self.has_update = has_update
        w, h = int(width * s), int(height * s)
        self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=BG, outline="")
        bar_w = int(3 * s)     # matches GameItem's own accent bar treatment
        self.accent_bar = self.create_rectangle(0, 0, bar_w, h, fill=ACCENT,
                                                outline="", state="hidden")
        if collapsed:
            d = COLLAPSED_BADGE_D * s
            cx, cy = w / 2, h / 2
            # No running state applies to Settings -- self.dot here is the
            # same badge-background primitive GameItem's collapsed dot is,
            # always LINE, never itemconfig'd by _paint(); it exists purely
            # so the badge reads as the same visual unit GameItem's does.
            self.dot = self.create_oval(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2,
                                        fill=LINE, outline="")
            self.text = self.create_text(cx, cy, anchor="center", text="S",
                                         fill=MUTED, font=("Segoe UI", fs(10.5, s), "bold"))
            # The small ACCENT corner dot is the collapsed-mode stand-in for
            # the expanded "Settings · Update" text swap -- always created
            # (state toggled by _paint(), not re-created), same "itemconfig
            # by stored id" discipline every other item here already follows.
            corner_d = 5 * s
            corner_x, corner_y = cx + d / 2 - corner_d / 2 - 2 * s, cy - d / 2 + corner_d / 2 + 2 * s
            self.update_dot = self.create_oval(
                corner_x - corner_d / 2, corner_y - corner_d / 2,
                corner_x + corner_d / 2, corner_y + corner_d / 2,
                fill=ACCENT, outline="", state="normal" if has_update else "hidden")
        else:
            self.dot = None
            self.update_dot = None
            self.text = self.create_text(16 * s, h / 2, anchor="w", text="Settings",
                                         fill=MUTED, font=("Segoe UI", fs(9.5, s)))
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<Button-1>", lambda e: self.on_click())
        self._paint()

    def set_state(self, selected=None, has_update=None):
        if selected is not None:
            self.selected = selected
        if has_update is not None:
            self.has_update = has_update
        self._paint()

    def _paint(self, hover=False):
        fill = CARD_HI if self.selected else (CARD if hover else BG)
        self.itemconfig(self.shape, fill=fill)
        self.itemconfig(self.accent_bar, state="normal" if self.selected else "hidden")
        if self.collapsed:
            # No text swap while collapsed -- the letter stays "S" always,
            # and the update signal is the corner dot's visibility instead
            # (see __init__): this is the collapsed-mode equivalent of the
            # expanded branch's ACCENT text-swap below, not a second signal.
            self.itemconfig(self.text, fill=INK if self.selected else MUTED)
            if self.update_dot is not None:
                self.itemconfig(self.update_dot,
                                state="normal" if self.has_update else "hidden")
        else:
            text = "Settings · Update" if self.has_update else "Settings"
            # ACCENT whenever an update is pending, selected or not -- it's
            # the whole point of the indicator; INK/MUTED only apply once
            # there is nothing to flag.
            colour = ACCENT if self.has_update else (INK if self.selected else MUTED)
            self.itemconfig(self.text, text=text, fill=colour)


class Row(tk.Frame):
    """Label on the left, control on the right -- the NVIDIA settings-table look."""

    def __init__(self, parent, label, s, hint=None, mutable_hint=False):
        super().__init__(parent, bg=CARD)
        # A fixed-width label column via grid, not pack -- the control then
        # starts at a constant offset from the row's left edge regardless of
        # how wide a stretched card gets; leftover width becomes trailing
        # margin after the control (column 1 stays at weight=0) instead of a
        # growing gap before it.
        self.grid_columnconfigure(0, minsize=int((ROW_LABEL_W + ROW_LABEL_GAP) * s))
        text = tk.Frame(self, bg=CARD)
        text.grid(row=0, column=0, sticky="w")
        tk.Label(text, text=label, bg=CARD, fg=INK, anchor="w", justify="left",
                 wraplength=int(ROW_LABEL_W * s),
                 font=("Segoe UI", fs(9.5, s))).pack(fill="x")
        self.hint_label = None
        if mutable_hint:
            # G#22/GH#33 round 2 (docs/design.md Revision 2, Decision A2):
            # only the jitter row needs a hint that can be overridden (the
            # sweep warning) and restored (its own static descriptive text)
            # -- built once, here, so set_hint()/restore_hint() never touch
            # a missing attribute. No other Row call site passes
            # mutable_hint=True; every plain hint= site (auto-stop) falls
            # through to the elif below, byte-for-byte as before this
            # feature ever existed.
            self._hint_size = fs(8, s)
            self._hint_default = hint
            self.hint_label = tk.Label(
                text, bg=CARD, anchor="w", justify="left",
                wraplength=int(ROW_LABEL_W * s), font=("Segoe UI", self._hint_size))
            if hint:
                self.restore_hint()
        elif hint:
            tk.Label(text, text=hint, bg=CARD, fg=MUTED, anchor="w", justify="left",
                     wraplength=int(ROW_LABEL_W * s),
                     font=("Segoe UI", fs(8, s))).pack(fill="x")
        self.control = tk.Frame(self, bg=CARD)
        self.control.grid(row=0, column=1, sticky="w")

    def set_hint(self, text, colour, bold=False):
        """Retext/recolour/reweight the mutable hint this Row opted into via
        mutable_hint=True (G#22/GH#33 round 2). Always packed -- unlike
        round 1's clear_hint(), this hint slot is never hidden, only swapped
        between its static descriptive text and a warning; restore_hint()
        below is the way back."""
        weight = "bold" if bold else "normal"
        self.hint_label.config(text=text, fg=colour,
                                font=("Segoe UI", self._hint_size, weight))
        self.hint_label.pack(fill="x")

    def restore_hint(self):
        """Back to this Row's construction-time static hint, MUTED and
        regular weight. Reads the module-level MUTED global at call time,
        not a value captured at construction, so a theme rebuild's repaint
        (which always runs after set_active_theme() has already reassigned
        it) picks up the new palette rather than a stale one."""
        self.set_hint(self._hint_default, MUTED, bold=False)


class NumBox(tk.Frame):
    """A right-aligned number with its unit, sized to sit in a Row."""

    def __init__(self, parent, default, unit, s, width=6):
        super().__init__(parent, bg=CARD)
        tk.Label(self, text=unit, bg=CARD, fg=MUTED, width=4, anchor="w",
                 font=("Segoe UI", fs(9, s))).pack(side="right")
        self.var = tk.StringVar(value=str(default))
        wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        wrap.pack(side="right", padx=(0, int(8 * s)))
        entry = tk.Entry(wrap, textvariable=self.var, width=width, bg=BG, fg=INK,
                         relief="flat", insertbackground=ACCENT, justify="right",
                         font=("Consolas", fs(10, s)), highlightthickness=0)
        # justify="right" pins the digits to the entry's own right edge, which
        # sits directly against wrap's 1px border -- pack's ipadx can't fix that
        # on one side only, it pads both. This spacer carries the field's own
        # background past the text instead, so the number reads inset rather
        # than crowded against the border. Packed before the entry so pack's
        # right-to-left order puts it outermost.
        tk.Frame(wrap, bg=BG, width=int(6 * s)).pack(side="right", fill="y")
        entry.pack(side="right", ipady=int(4 * s), ipadx=int(5 * s))
        entry.bind("<FocusIn>", lambda e: wrap.config(bg=ACCENT))
        entry.bind("<FocusOut>", lambda e: wrap.config(bg=LINE))

        def _blur(e):
            e.widget.winfo_toplevel().focus_set()
        entry.bind("<Return>", _blur)
        entry.bind("<Escape>", _blur)
        self.wrap = wrap
        self.entry = entry


class AfkAutoclicker:
    def __init__(self, root, store=None, os_theme=None):
        self.root = root
        self.store = store if store is not None else Store()
        # DPI half of self.s, named separately from the combined value below
        # -- a UI-scale change (_apply_ui_scale) recomputes self.s from this
        # unchanged, never re-reads "tk scaling" (docs/history/ac-17-f4-spec.md §2: the DPI
        # half is still detected once, at startup).
        self._dpi_s = root.tk.call("tk", "scaling") / 1.333  # 1.0 at 96 dpi
        # G#38/GH#67: detected once at startup, same "never re-read mid-
        # session" policy _dpi_s itself already documents -- dragging the
        # window to a different-resolution monitor mid-session doesn't
        # re-anchor Auto's reference until restart (docs/spec.md's Edge
        # cases, a named/accepted limitation).
        self._screen_w = root.winfo_screenwidth()
        self._screen_h = root.winfo_screenheight()
        # Auto has no mapped window size to derive from yet at this point in
        # construction (the same chicken-and-egg the <Configure> bind below
        # already avoids) -- bootstrap to the DPI factor alone, same value
        # "100" always gave, for this very first _build_ui()/_apply_minsize()
        # call. The first genuine post-map root <Configure> then recomputes
        # self.s for real against the actual mapped size (docs/spec.md §3).
        if self.store.data["ui_scale"] == "auto":
            self.s = s = self._dpi_s * 1.0
        else:
            self.s = s = self._dpi_s * UI_SCALE_FACTORS[self.store.data["ui_scale"]]
        # Feature 2's detect_os_theme(), if it already ran once in __main__
        # to resolve a saved "system" appearance -- never re-detected from
        # here, only ever read or (once) lazily filled in, see
        # _apply_appearance()/_build_settings().
        self._os_theme = os_theme

        root.title("Clickwork")
        # Loaded once here, not inside _build_ui()/_rebuild_ui(): root itself
        # survives every rebuild (only its children are torn down), so the
        # icon must not be re-created on each one. _load_app_icon() (shared
        # with selftest(), so CI actually exercises this path) keeps the
        # PhotoImage objects alive on self -- Tk drops the icon silently the
        # instant nothing holds a reference to them, a well-known gotcha.
        self._icon_imgs = _load_app_icon(root)
        root.resizable(True, True)
        # Both panes still turn off geometry propagation to hold their tuned
        # widths, so nothing tells the window how tall to start -- without an
        # explicit size the body collapses to zero height and only the header
        # shows. minsize keeps the window from ever being resized below the
        # size the layout was tuned at, so nothing clips.
        self._auto_bootstrap_wh = None   # set by _apply_minsize()'s own
            # not-grow_only branch below, right before it returns -- see
            # _on_root_resize()'s own comment (G#38/GH#67 round 2).
        self._apply_minsize()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Button-1>", self._maybe_drop_focus)  # bound once, here --
            # NOT inside _build_ui(): root itself survives every rebuild
            # (only its *children* are destroyed), and this tag ("all") is
            # interpreter-wide -- it already fires for every widget in every
            # tree, including a rebuilt one and any future tab this grows.
            # Re-issuing it inside _build_ui()/_rebuild_ui() would be a
            # pointless duplicate binding on that same tag for a root that
            # never goes away (see #18).
            #
            # An earlier version (G#27/ac-27, PR #47) kept this call's own
            # funcid and released it explicitly in on_close() via
            # unbind_all()+deletecommand(), reasoning that bind_all()'s
            # needcleanup=0 registration otherwise outlives root.destroy().
            # That reasoning still stands, but the explicit deletecommand()
            # call -- run back-to-back with _forget_traces()'s trace_remove()
            # sweep, right after cancelling a batch of after() jobs and right
            # before root.destroy() -- is the prime suspect (see on_close()'s
            # own comment) for a macOS-only interpreter abort
            # (`Tcl_FindHashEntry on deleted table`) reproduced twice in CI.
            # Reverted here rather than guessed at further; the leak this
            # was fixing is real and is back on backlog.md.

        self.mouse = Controller()
        self.hotkey = None
        self.registered_hotkey = None
        self.hk_listener = None
        self.running = False
        self.worker = None
        self.capture_thread = None
        self._poll_thread = None
        self._poll_seq = 0             # bumped once per _poll_games() call,
        self._poll_applied_seq = 0     # compared in _apply_scan() -- see there
        self._check_seq = 0            # bumped once per check_update() call,
                                        # compared in _apply_check() -- see there
        self.right_held = False
        self.settings = {}
        self._pending = None
        self._save_failed = False      # last self.store.save()/put_game()
                                        # outcome seen by _note_save() -- see
                                        # there
        self._sweep_hint_pending = None    # (text, colour) or None -- the
                                        # jitter row's warning-band state as
                                        # last computed by
                                        # _note_sweep_hint(), painted by
                                        # _paint_sweep_hint() (G#22/GH#33).
                                        # None means "no band active", i.e.
                                        # the row shows its static
                                        # descriptive text, not that the
                                        # hint is hidden -- round 2 moved
                                        # the warning into the jitter row's
                                        # always-shown hint slot (docs/
                                        # design.md Revision 2)
        self._sweep_band_active = False    # whether a warning band was
                                        # actually showing the last time it
                                        # was painted -- used only to detect
                                        # a genuine band-active/inactive
                                        # transition, so
                                        # _request_pane_fill("clicking") is
                                        # not called on every keystroke
        self._log_dialog = None        # the update-log Toplevel (G#36/GH#64),
                                        # if one is currently open -- None
                                        # otherwise. It IS a genuine child of
                                        # root (tk.Toplevel(self.root, ...)),
                                        # so _rebuild_ui()'s own teardown loop
                                        # destroys it along with everything
                                        # else -- round 2 (test-review.md
                                        # Defect 1) found the previous claim
                                        # here ("never rebuilt") was never
                                        # actually tested and is false.
                                        # _rebuild_ui() now captures this
                                        # dialog's restorable state before
                                        # its teardown loop runs and rebuilds
                                        # it, in the new theme/scale, at its
                                        # own tail; on_close() destroys it
                                        # directly if still set.
        self._log_dialog_ctx = None    # that dialog's own state (log path,
                                        # decoded text, target version, the
                                        # "show full paths" Variable, and
                                        # the widgets its handlers touch) --
                                        # a plain dict, not closures, so the
                                        # Send/Dismiss/Open-folder/Copy-link
                                        # handlers below can be ordinary
                                        # bound methods. Replaced wholesale
                                        # by every dialog (re)build, never
                                        # mutated across one.
        self._log_dialog_show_paths_var = None   # the SAME BooleanVar as
                                        # ctx["show_paths_var"] -- stored
                                        # here too, as a direct instance
                                        # attribute, purely so
                                        # _forget_traces()'s existing sweep
                                        # (it walks vars(self) directly, not
                                        # two levels into a dict) finds and
                                        # clears its trace(s) on every
                                        # rebuild. Without this, the ac-27
                                        # lesson repeats: a trace still
                                        # referencing destroyed widgets from
                                        # the outgoing generation is a live
                                        # reference an unrelated .set() call
                                        # (or, eventually, cyclic GC running
                                        # on any thread) can fire into.
        self._log_report_after_id = None   # the one after_idle(self._
                                        # maybe_offer_log_report) job
                                        # scheduled at this __init__'s own
                                        # tail, if it hasn't fired yet --
                                        # None once it has (or once
                                        # on_close() has cancelled it).
                                        # G#39-class bug (round 3,
                                        # test-review.md): this id used to
                                        # go nowhere, so nothing could ever
                                        # cancel that job -- a test whose
                                        # own on_close() ran before this
                                        # idle callback got a turn left it
                                        # queued, and Tk eventually ran it
                                        # against an already-destroyed root
                                        # (invisible on Linux/Windows's
                                        # idle-flush timing, reliably fatal
                                        # on macOS CI: TclError building/
                                        # measuring widgets with nothing
                                        # left to attach them to).
        self._update_text = ("Check for updates", True, None)   # args of the
                                # most recent _set_update_state() call, kept
                                # current whether or not Settings is open --
                                # a plain tuple, not a Tk object, so (like
                                # self._pending) never reset by a rebuild;
                                # replayed onto update_button/version_label
                                # by _build_ui()'s tail. See docs/history/ac-17-f3b-spec.md §3.
        self._ui_queue = queue.SimpleQueue()   # one queue for the app's whole
                                                # lifetime -- never swapped by
                                                # a rebuild (see _rebuild_ui())
        self._loading = False          # suppress saves while filling the form
        self._settings_open = False    # which content-pane body is showing
        self._rail_collapsed = False   # the rail always launches expanded --
                                        # the app's default geometry is always
                                        # >= RAIL_COLLAPSE_THRESHOLD by
                                        # construction (see _apply_minsize()),
                                        # so False is correct on first launch
                                        # without querying anything. Re-derived
                                        # at the top of every _build_ui() call;
                                        # session-only, same precedent as
                                        # self._settings_open below: never
                                        # persisted to settings.json.
        self._content_tab = "hotkey"       # which game-page tab is showing:
                                            # "hotkey" / "clicking" -- a plain
                                            # attribute, same precedent as
                                            # self._settings_open above:
                                            # never persisted to settings.json,
                                            # survives _rebuild_ui() untouched.
        self._settings_tab = "appearance"  # which Settings tab is showing:
                                            # "appearance" / "updates" -- same
                                            # precedent as self._content_tab.
        self._rebuild_after_id = None  # the one after_idle(self._rebuild_ui)
                                        # job currently pending, if any -- see
                                        # _apply_appearance()/_rebuild_ui()
        self._rebuilding = False       # True for the duration of
                                        # _rebuild_ui()'s own body -- see
                                        # _rebuild_ui()/_apply_appearance()
        self._rebuild_wanted = False   # a rebuild was requested while
                                        # _rebuilding was True; _rebuild_ui()
                                        # schedules exactly one follow-up
        self._auto_settle_after_id = None  # the one after(AUTO_SETTLE_MS, ...)
            # job currently pending, if any (G#38/GH#67) -- same
            # single-slot cancel-or-schedule shape as _rebuild_after_id/
            # _pane_fill_after_id above, but a real timed after() rather
            # than after_idle -- see _request_auto_settle()/_on_auto_settle().
        self._pane_fill_after_id = None  # the one after_idle(self._run_pane_fill)
            # job currently pending, if any (G#28/GH#48 round 5) -- see
            # _request_pane_fill()/_run_pane_fill().
        self._pane_fill_key = None     # which pane the pending/running
                                        # deferred pass targets
        self._pane_filling = False     # True for the duration of
                                        # _run_pane_fill()'s own _fill_pane()
                                        # call -- see _request_pane_fill()
        self._pane_fill_wanted = None  # a further pane-fill was requested
                                        # while _pane_filling was True;
                                        # _run_pane_fill() re-arms exactly
                                        # one follow-up for it
        self.profiles = list(PROFILES)
        for saved in self.store.data.get("games", {}).values():
            meta = saved.get("_profile")
            if meta and not any(p["id"] == meta["id"] for p in self.profiles):
                self.profiles.append(make_profile(meta["id"], meta["name"],
                                                  meta["title"]))
        self.by_id = {p["id"]: p for p in self.profiles}
        self.current = self.store.data.get("selected") or "global"
        if self.current not in self.by_id:
            self.current = "global"

        self._build_ui(s)

        self.root.bind("<Configure>", self._on_root_resize)   # bound only
            # AFTER the first _build_ui() call above has fully returned, not
            # before it (story #24 feature 3, PR #41 round 3): a real window
            # manager (macOS's WindowServer, Windows' own) can legitimately
            # reposition/resize the still-unmapped toplevel between Tk()/
            # geometry() and the window actually appearing on screen, firing
            # a genuine, root-targeted <Configure> mid-construction -- one
            # that PASSES _on_root_resize()'s `event.widget is self.root`
            # guard, because it isn't the spurious-descendant-widget case
            # that guard exists to filter (see _on_root_resize()'s own
            # docstring). If that event crosses RAIL_COLLAPSE_THRESHOLD
            # before this bind exists, it calls _request_rebuild(), which
            # schedules after_idle(self._rebuild_ui) -- and the very next
            # card()'s _redraw() (still inside this SAME first _build_ui()
            # call, see card()) reentrantly services that idle job via
            # update_idletasks(), running _rebuild_ui() -> _persist() before
            # attributes _build_ui() itself hasn't assigned yet exist (e.g.
            # self.click_ms, assigned inside the Clicking tab further down
            # this very call) -- AttributeError. Xvfb never reproduces this
            # (no window manager, so no post-map root <Configure> is ever
            # generated during construction), which is why this shipped
            # green on Linux and crashed on macOS CI. Binding here instead
            # of before _build_ui(s) above means no genuine root <Configure>
            # can reach _on_root_resize() until construction has already
            # finished -- the same guarantee _rebuild_ui()'s own
            # self._rebuilding flag gives a rebuild in progress, just for
            # the one call that flag was never wrapped around (see
            # _rebuild_ui()'s docstring: it only wraps its own body, not
            # this first, direct call from here).

        # Registers an OS-level global hotkey listener -- runs once, after
        # the first _build_ui() call, never inside _build_ui()/_rebuild_ui()
        # itself: re-running it on every rebuild would try to register a
        # second listener while self.hk_listener is still running.
        #
        # _build_ui(s) above is a plain synchronous call, so by the time
        # execution reaches here its tail (self._timers/_sync_settings()/
        # _drain_ui()/_poll_games(), defined inside _build_ui() itself) has
        # already run and populated self.settings. A restored hotkey press
        # can therefore never reach loop() against an empty settings
        # snapshot; there is no ordering gap to close. (This became true
        # only when commit 54a3b65 pulled those four lines into _build_ui()'s
        # tail -- an unrelated refactor that closed the gap as a side effect.)
        saved = Hotkey.from_json(self.store.data.get("hotkey") or {})
        if saved is not None:
            self.hotkey = saved
            self.apply_hotkey()

        # G#36/GH#64: checks the *previous* in-app update attempt's log, if
        # any -- runs once, from __init__ only, never from _build_ui()/
        # _rebuild_ui() (a theme/scale rebuild must not re-offer a prompt
        # already dismissed/sent this launch). after_idle so the main
        # window paints first; this never blocks startup and touches no
        # network (only clicking Send via GitHub, inside the dialog itself,
        # ever does). The id is kept (round 3, test-review.md) so on_close()
        # can cancel it -- see self._log_report_after_id's own comment.
        self._log_report_after_id = self.root.after_idle(self._maybe_offer_log_report)

    def _apply_minsize(self, grow_only=False):
        """The tuned-default-size mechanism (#14, retuned by G#28/GH#48):
        establishes/updates root.minsize() from self.s. Called once,
        unconditionally, from __init__ (grow_only=False, the byte-identical
        first-launch behavior the two inline lines this replaces always had
        -- also sets geometry() to that exact size). A UI-scale change calls
        this again with grow_only=True: minsize is always updated (a WM-level
        constraint, safe to change regardless of the window's current
        actual size), but geometry() is only invoked, and only per-axis,
        when the window's current size is now below the new floor -- so a
        smaller step never shrinks a window the user made bigger, and a
        bigger step only grows whichever axis actually falls short (see
        docs/history/ac-17-f4-spec.md §2).

        Story #24 feature 3: minsize (the hard floor) and the default launch
        geometry are no longer the same number *on the width axis*. minw is
        derived from SIDEBAR_RAIL_W -- the collapsed-rail floor -- so the
        window can actually be dragged down far enough to reach
        RAIL_COLLAPSE_THRESHOLD and collapse; the not-grow_only branch's own
        default_w keeps using the old SIDEBAR_W-based formula so the app
        still *launches* at today's familiar expanded size, not immediately
        at the new, smaller floor. Height has no equivalent second state --
        there is no collapsed vertical mode for a floor to admit -- so minh
        stays a single WINDOW_MIN_H-derived number used for both minsize()
        and (when not grow_only) geometry()'s height (see docs/spec.md's
        "Why height doesn't get the width axis's floor/default split",
        G#28/GH#48).

        G#38/GH#67 round 2 (PR #89 review): the not-grow_only branch also
        records the exact (width, height) it just requested, in
        self._auto_bootstrap_wh -- see _on_root_resize()'s own comment for
        why.

        G#38/GH#67 round 3 (PR #89 review, macOS/Windows CI regression):
        the grow_only branch now records its own geometry() request there
        too, not just the original bootstrap one. Round 2 only ever
        compared an incoming <Configure> against the single value recorded
        at construction -- but a live Auto-mode drag can itself call this
        method with grow_only=True and issue a *second* self-requested
        geometry() (when the newly-recomputed minsize floor now exceeds
        the window's current size), and a real window manager's own later
        confirmation of *that* request was never recognized as an echo --
        it reported a genuine-looking size change nothing requested,
        re-arming a live settle timer from self-correction alone. Tracking
        whichever self-requested geometry is most recent (there is only
        ever one in flight at a time -- both branches are called from the
        same single-threaded event handling) closes that gap the same way
        the original bootstrap echo was closed."""
        minw, minh = (int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * self.s),
                      int(WINDOW_MIN_H * self.s))
        self.root.minsize(minw, minh)
        if not grow_only:
            default_w = int((SIDEBAR_W + 1 + CONTENT_W) * self.s)
            self.root.geometry(f"{default_w}x{minh}")
            self._auto_bootstrap_wh = (default_w, minh)
            return
        cur_w, cur_h = self.root.winfo_width(), self.root.winfo_height()
        new_w, new_h = max(cur_w, minw), max(cur_h, minh)
        if (new_w, new_h) != (cur_w, cur_h):
            self.root.geometry(f"{new_w}x{new_h}")
            self._auto_bootstrap_wh = (new_w, new_h)

    def _request_rebuild(self):
        """The coalescing tail shared by _apply_appearance() and
        _apply_ui_scale(): at most one rebuild is ever pending or running,
        see _rebuild_ui()'s own docstring for why a second pending rebuild
        is a real crash, not just wasted work. Extracted, not duplicated,
        so a theme change and a scale change fired in quick succession
        coalesce into exactly one rebuild by construction, the same
        guarantee already proven for repeated Appearance changes alone."""
        if self._rebuilding:
            self._rebuild_wanted = True
        elif self._rebuild_after_id is None:
            self._rebuild_after_id = self.root.after_idle(self._rebuild_ui)

    def _auto_scale_factor(self, width, height):
        """G#38/GH#67: Auto mode's continuous scale -- an area-based "how
        much of the screen does the window fill" fraction (square-rooted so
        it scales roughly linearly with window size, the way the fixed
        percentage steps already do -- doubling both axes, 4x the area,
        yields 2x the factor, not 4x), calibrated against
        AUTO_REFERENCE_FILL so a typical desktop lands at parity with
        today's "100%" step (docs/spec.md §2). Clamped to
        [AUTO_SCALE_MIN, AUTO_SCALE_MAX], the same range the four fixed
        steps already cover -- this is also what prevents a shrink/grow
        feedback runaway."""
        fill = ((width * height) / (self._screen_w * self._screen_h)) ** 0.5
        factor = fill / AUTO_REFERENCE_FILL
        return min(AUTO_SCALE_MAX, max(AUTO_SCALE_MIN, factor))

    def _request_auto_settle(self):
        """Auto mode's drag-settle debounce (docs/spec.md "The debounce
        decision") -- deliberately NOT _request_rebuild()'s after_idle
        coalescing: after_idle fires the next time Tk's event loop is idle,
        which during a live OS-level drag is typically between every single
        native resize callback, not after the drag as a whole settles. This
        mirrors that same single-slot cancel-or-schedule shape
        (_rebuild_after_id/_pane_fill_after_id) but with a real timeout
        instead, cancelled the same way in on_close()."""
        if self._auto_settle_after_id is not None:
            self.root.after_cancel(self._auto_settle_after_id)
        self._auto_settle_after_id = self.root.after(AUTO_SETTLE_MS, self._on_auto_settle)

    def _on_auto_settle(self):
        self._auto_settle_after_id = None
        self._request_rebuild()   # hands off into the existing coalesced-
                                   # rebuild machinery unchanged -- this
                                   # mechanism only changes WHEN a rebuild
                                   # gets requested, never how it's run.

    def _on_root_resize(self, event):
        """Debounce the rail's collapse check, not the collapse itself (story
        #24 feature 3): a live resize drag fires <Configure> continuously,
        but _request_rebuild() must only ever be called on an actual state
        flip -- see docs/spec.md's "The debounce decision."

        event.width is trustworthy unconditionally here (Tk only ever fires
        a real <Configure> for a widget that has actually just been drawn/
        resized -- unlike a bare winfo_width() query, there is no unmapped-
        placeholder risk on an event Tk itself generated), so this needs
        none of _build_ui()'s own winfo_ismapped() guard.

        The `event.widget is not self.root` guard is load-bearing, not
        defensive: every widget's default bindtags include its *toplevel's*
        pathname as the third tag (after its own and its class's), so
        root.bind(...) -- unlike root.bind_all(...) -- fires for every
        descendant's own <Configure> too, not just root's. Confirmed with a
        local trace during development: at construction alone, ~100+ calls
        land here for child Frames/Canvases (each with its own small
        width), only one of which actually targets root.

        G#38/GH#67: in Auto mode (self.store.data["ui_scale"] == "auto",
        checked live so a mode switch mid-drag takes effect on the very
        next event, docs/spec.md's Edge cases), self.s itself is no longer
        constant across a resize -- every qualifying event recomputes it
        and the window's minsize() (both cheap, no widget churn) so neither
        ever lags behind the live drag, then only requests the actual
        widget-tree rebuild (which repaints fonts/padding/rail state) via
        the settled debounce (_request_auto_settle()), not the immediate
        after_idle fixed-step mode uses -- see docs/spec.md §4/§5.

        Round 2 (PR #89 review, macOS/Windows CI): a real window manager
        sends a post-map root <Configure> shortly after construction,
        reporting exactly the geometry _apply_minsize()'s own bootstrap
        call already requested (self._auto_bootstrap_wh) -- nothing has
        actually resized yet, it is the WM merely confirming the map. On a
        real screen that isn't near AUTO_REF_SCREEN_W/H (any CI runner's
        own virtual display), _auto_scale_factor() still computes a
        different self.s purely from the screen-size term, which used to
        arm a real AUTO_SETTLE_MS timer from this echo alone -- every fresh
        UITestCase fixture boots in Auto mode now, and that timer firing
        later, mid-test (or after a *different* test's own teardown, since
        150ms comfortably outlives most test bodies), tore down/rebuilt the
        widget tree out from under a test that never asked for a rebuild.
        self.s/minsize()/the rail-collapse flag still get corrected live
        below regardless (matching every other event) -- only the settle-
        triggered rebuild itself is skipped for this one echo, so a
        genuine subsequent resize (or an explicit Settings > Appearance
        pick, which calls _apply_ui_scale() directly, bypassing this
        method) still settles normally. Compared by (width, height), not
        by "is this the first event" -- a burst of real resizes starting
        from a fresh instance (as several of UIScaleAuto's own tests do,
        with no natural bootstrap echo to consume under Xvfb) must still
        settle exactly like today; only an event reporting the *exact*
        bootstrap geometry back unchanged is ever a candidate.

        Round 3 (PR #89 review, macOS/Windows CI regression): self.
        _auto_bootstrap_wh is no longer only the one-time construction
        value -- _apply_minsize()'s own grow_only branch now updates it
        every time *it* issues a geometry() call too (see its own
        docstring), so a real WM's later confirmation of a self-triggered
        minsize correction is also recognized as an echo, not just the
        original bootstrap map."""
        if event.widget is not self.root:
            return
        if self.store.data["ui_scale"] == "auto":
            is_bootstrap_echo = (event.width, event.height) == self._auto_bootstrap_wh
            new_s = self._auto_scale_factor(event.width, event.height)
            s_changed = new_s != self.s
            self.s = new_s
            self._apply_minsize(grow_only=True)
            collapsed = event.width < int(RAIL_COLLAPSE_THRESHOLD * self.s)
            collapsed_changed = collapsed != self._rail_collapsed
            if collapsed_changed:
                self._rail_collapsed = collapsed
            if (s_changed or collapsed_changed) and not is_bootstrap_echo:
                self._request_auto_settle()
            return
        collapsed = event.width < int(RAIL_COLLAPSE_THRESHOLD * self.s)
        if collapsed != self._rail_collapsed:
            self._rail_collapsed = collapsed
            self._request_rebuild()

    # ---------- widget tree (rebuildable) ----------

    def _build_ui(self, s):
        """
        The rebuildable widget-construction body: header, sidebar, content.

        Called once from __init__ and again, in place, by _rebuild_ui() on
        every Appearance change -- everything here may run twice (or more);
        nothing here may assume it is the first time. One-time root
        configuration and non-Tk state live in __init__ instead, never here.
        """
        # Re-derive self._rail_collapsed from *current* geometry before
        # building anything (story #24 feature 3): self.s can change between
        # builds (a UI-scale pick), and RAIL_COLLAPSE_THRESHOLD * s changes
        # with it -- a window whose raw pixel width never moved can still
        # legitimately flip collapsed/expanded purely because the UI got
        # bigger or smaller around it. winfo_ismapped() guards the very
        # first call (from __init__, before root has ever been drawn):
        # winfo_width() would return Tk's unmapped placeholder there, not
        # the just-requested geometry -- leave self._rail_collapsed at
        # whatever __init__ set (False), always correct on first launch
        # since the default geometry is always >= the threshold.
        if self.root.winfo_ismapped():
            self._rail_collapsed = (
                self.root.winfo_width() < int(RAIL_COLLAPSE_THRESHOLD * s))

        # root itself survives every rebuild (only its children are
        # destroyed), so unlike title/resizable/minsize/geometry/protocol/
        # bind_all -- which are theme-independent and stay one-time in
        # __init__ -- its background IS theme-dependent and must be
        # reapplied here every time, the same way every other widget below
        # picks up BG/CARD/... fresh by being (re)built after set_active_
        # theme() reassigns them.
        self.root.config(bg=BG)

        # ── header ──
        header = tk.Frame(self.root, bg=CARD, height=int(52 * s))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Clickwork", bg=CARD, fg=INK,
                 font=("Segoe UI", fs(12, s), "bold")).pack(side="left",
                                                              padx=int(16 * s))
        self.status = StatusPill(header, s, width=250, height=36)
        self.status.pack(side="right", padx=int(14 * s))

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        # ── sidebar ──
        rail_w = SIDEBAR_RAIL_W if self._rail_collapsed else SIDEBAR_W
        side = self.side = tk.Frame(shell, bg=BG, width=int(rail_w * s))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        # count_label is always built -- only its pack() call is conditional
        # (story #24 feature 3: "always build, only toggle visibility", the
        # same convention Feature 2 established for its own tab panes) --
        # there's no room for "GAMES N" at SIDEBAR_RAIL_W, and _rebuild_list()'s
        # own count_label.config(text=...) call stays legal on an unpacked
        # widget, so it needs no guard either.
        self.count_label = tk.Label(side, text="GAMES", bg=BG, fg=MUTED, anchor="w",
                                    font=("Segoe UI", fs(8, s), "bold"))
        if not self._rail_collapsed:
            self.count_label.pack(fill="x", padx=int(14 * s), pady=(int(14 * s), int(6 * s)))
        self.list_frame = tk.Frame(side, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=int(8 * s))
        self.items = {}
        self._rebuild_list()
        add_label = "+" if self._rail_collapsed else "Add current game"
        Button(side, add_label, self.add_current_game, s,
               width=rail_w - 28).pack(pady=(int(12 * s), int(4 * s)))
        # A thin divider separates the action button above from the Settings
        # entry below -- without it the two rows read as one stack of
        # similar pill buttons instead of "an action" vs. "a navigation
        # destination" (docs/history/ac-17-f3a-test-review.md's UX judgment on 3a). Same LINE
        # color as the sidebar/content divider below, just laid out
        # horizontally here. "Check for updates"/the version string moved
        # into the Settings page's own Updates section in Feature 3b -- this
        # divider now closes off just the one button above it.
        tk.Frame(side, bg=LINE, height=1).pack(fill="x", padx=int(14 * s),
                                               pady=(int(4 * s), int(8 * s)))
        # Not a game -- never added to self.profiles/self.by_id/self.items,
        # so it never counts toward "GAMES N" and is untouched by
        # _rebuild_list()/_mark_running()/_poll_games(). has_update is set
        # fresh from self._pending here so a rebuild that happens while
        # Settings is closed (an Appearance change on a game page, with an
        # offer already pending from an earlier Settings visit) still shows
        # the indicator correctly -- see docs/history/ac-17-f3b-spec.md §1.
        self.settings_item = SettingsItem(side, self._show_settings, s,
                                          has_update=(self._pending is not None),
                                          collapsed=self._rail_collapsed)
        self.settings_item.pack(pady=(0, int(7 * s)))
        self.settings_item.set_state(selected=self._settings_open)

        tk.Frame(shell, bg=LINE, width=1).pack(side="left", fill="y")

        # ── content ──
        self.content = tk.Frame(shell, bg=BG, width=int(CONTENT_W * s))
        self.content.pack(side="left", fill="both", expand=True)
        self.content.pack_propagate(False)

        if self._settings_open:
            self._build_settings(s)
            # update_button/version_label only exist inside this branch
            # (Feature 3b) -- replay whatever state they'd accumulated
            # before the rebuild tore the old widgets down. Two steps, in
            # this order, not one: _offer_update() restores the offer's
            # *styling* (primary, command=install_update) if an offer is
            # outstanding, then self._update_text unconditionally overlays
            # the most recent _set_update_state() text/enabled/colour on
            # top -- reproducing the exact layering the widgets would have
            # accumulated live, without a rebuild (see docs/history/ac-17-f3b-spec.md §3):
            # idle/checking has no offer to restore and the overlay alone
            # is correct; an offer with nothing since is idempotent (the
            # overlay re-applies the same text _offer_update just set); a
            # mid-download or install-error state restores the offer's
            # accent styling underneath, then the overlay corrects the text
            # to "Downloading… N%"/the error, not "Install v{tag}".
            #
            # Snapshot self._update_text BEFORE calling _offer_update():
            # _offer_update() itself always records its own text into self.
            # _update_text (so a *live* offer, with no rebuild involved, is
            # correctly the newest state) -- calling it here, mid-replay,
            # would otherwise clobber a still-current "Downloading… N%"/
            # error tuple with the offer's own text before the overlay line
            # below ever reads it, reverting exactly the state this replay
            # exists to preserve.
            overlay = self._update_text
            if self._pending is not None:
                self._offer_update(self._pending[0])
            self._set_update_state(*overlay)
            # G#21/GH#32 item 4: replay a still-outstanding save-failure
            # notice the same way the update state above just was -- a
            # failed _apply_appearance() save is itself what triggers this
            # rebuild, so self._save_failed can already be True the moment
            # self.save_failed_label exists again.
            self._paint_save_notice()
        else:
            self._build_content(s)
            self._select(self.current, persist=False)
            # G#22/GH#33: replay the jitter row's dynamic hint the same
            # way the settings branch above replays the save-failure notice
            # -- _select()'s own tail _persist() call just recomputed
            # self._sweep_hint_pending but, per _note_sweep_hint()'s own
            # docstring, could not paint it (self._rebuilding is still True
            # here -- see _rebuild_ui()). self.jitter_row is fresh now, so
            # painting is safe.
            self._paint_sweep_hint()

        # The status pill starts hard-coded "OFF" in its own constructor --
        # resync it to the real, unchanged self.running/self.registered_
        # hotkey state (untouched by any of the above).
        if self.running:
            self.status.set("RUNNING", OK,
                            self.registered_hotkey.label() if self.registered_hotkey else "")
        else:
            self.status.set("OFF", BAD,
                            self.registered_hotkey.label() if self.registered_hotkey else "")
        self._timers = {}
        self._sync_settings()
        self._drain_ui()
        self._poll_games()

    def _rebuild_ui(self):
        """
        Tear down every widget under root and build it again in place, so an
        Appearance change (or leaving/entering Settings) repaints/reshapes
        the window without a restart. Never touches self.running/self.worker/
        self.hk_listener/self.registered_hotkey/self.profiles/self.store --
        none of those are Tk objects, and a rebuild must not reset any of
        them (see docs/history/ac-17-f3a-spec.md §2).

        Also absorbs any still-pending after_idle(self._rebuild_ui) job
        scheduled by _apply_appearance(): whichever caller actually runs a
        rebuild first -- an inline call from _show_settings()/_select(), or
        the idle callback itself -- cancels the other right here, so at most
        one rebuild is ever in flight or pending. This matters beyond mere
        waste: card()'s _redraw() (see card(), below) calls
        inner.update_idletasks() while a rebuild is still constructing the
        tree, and update_idletasks() reentrantly runs any OTHER already-
        queued idle callback -- including a second pending _rebuild_ui() --
        before returning. That reentrant rebuild would tear down the first
        rebuild's still-being-built widgets out from under it, and the
        first rebuild's next card() call then raises TclError on the now-
        destroyed shell it was still holding a reference to (see
        docs/history/ac-17-f3a-test-review.md Defect 1 / docs/history/ac-17-f3a-implementation.md "Round 2").

        At most one rebuild is ever actually RUNNING too, not just pending:
        self._rebuilding, set for the duration of the body below, is what
        makes that true. Round 2's fix above only stopped a second rebuild
        from being SCHEDULED while one was pending; it did not stop one from
        being scheduled and then reentrantly serviced while one was already
        *running* -- _apply_appearance() clears self._rebuild_after_id to
        None right here, at the top, before the body runs, so a call to
        _apply_appearance() from *inside* the body (e.g. some future
        synchronous internal caller, mid-_build_content()/_build_settings())
        would see None and schedule a fresh after_idle job, which the SAME
        still-running rebuild's own card() calls would then reentrantly
        service via update_idletasks() -- reproducing the exact Defect 1
        crash through a different door (docs/history/ac-17-f3a-test-review.md Round 2 review,
        Finding #1; probe5_reentrant_card.py). self._rebuilding closes that
        door: _apply_appearance() (and any other rebuild request) checks it
        and, while it is set, only marks self._rebuild_wanted instead of
        scheduling anything; the finally block below schedules exactly one
        follow-up once this call has fully finished, so the outcome (the
        latest choice, eventually rebuilt against) is unchanged -- only the
        timing of the follow-up moves to after this call safely returns.

        self._ui_queue is NOT swapped here (Round 4, PR review Finding #2):
        an earlier version replaced it with a fresh queue.SimpleQueue() on
        every rebuild, reasoned as harmless because "the next state
        transition re-queues one" -- true for RUNNING/OFF (the only two
        states resynced below, via _build_ui()'s tail), false for
        ERROR/STOPPED/EATING, none of which the tail resyncs: a worker's
        self._ui(self._set_status, "ERROR", ...) call landing in the queue
        an instant before a rebuild was silently and permanently dropped,
        leaving the post-rebuild pill reading a plain, misleading OFF. The
        swap was never actually load-bearing: every queued callback
        (_set_status, _offer_update, _set_update_state, _mark_running, ...)
        already resolves its target widget fresh, at drain time, not at
        enqueue time (see _set_status's own docstring), and _drain_ui()
        already drops a TclError from a genuinely stale/destroyed-widget
        closure and keeps draining (see _drain_ui()) -- so nothing here
        actually needed a widget queued against the pre-rebuild tree to be
        thrown away; one queue lives for the app's whole lifetime instead.
        """
        if self._rebuild_after_id is not None:
            try:
                self.root.after_cancel(self._rebuild_after_id)
            except tk.TclError:
                pass
            self._rebuild_after_id = None
        self._rebuilding = True
        try:
            self._persist()                    # flush any in-progress field edit
                                                # before its widget is destroyed
            # G#36/GH#64 round 2 (test-review.md Defect 1): the update-log
            # dialog, if open, is a genuine child of root and would
            # otherwise be silently destroyed by the teardown loop below,
            # leaving self._log_dialog/_log_dialog_ctx as dangling
            # references -- any later write to its "show full paths"
            # Variable then raised an uncaught TclError into a destroyed
            # widget. The app follows the *system* theme, so an OS dark/
            # light switch can trigger this with nobody touching Settings.
            # Captured as plain data (not widgets, not Variables) here,
            # before anything is torn down, and rebuilt at this method's
            # own tail -- never by re-running detection or re-triggering
            # "ask once" (the log's own status/text/target_version are
            # replayed exactly as captured, not looked up again).
            log_dialog_restore = self._capture_log_dialog_restore_state()
            if log_dialog_restore is not None:
                self._close_log_dialog()
            for job in self._timers.values():
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            self._timers = {}
            for w in self.root.winfo_children():
                w.destroy()
            # content_tab_var/settings_tab_var/appearance_var/ui_scale_var/
            # button_name/eat_mode/every NumBox's .var are all recreated
            # fresh in _build_ui() below, same as every other rebuildable
            # widget -- but a Variable is not a widget, so destroy() above
            # never touches the *outgoing* generation's traces (see
            # _forget_traces()'s own docstring). Called here, before they
            # are replaced, so every earlier generation's traces (and
            # everything they keep reachable) are released across however
            # many rebuilds happen. NOTE (G#27/ac-27 round 2, PR #47):
            # on_close() no longer also calls this -- see its own comment --
            # so the *last* generation's traces, still live when the app
            # finally closes, are not released by anything. That residual
            # window is back on backlog.md, open.
            self._forget_traces()
            self._build_ui(self.s)
            if log_dialog_restore is not None:
                self._restore_log_dialog(log_dialog_restore)
        finally:
            self._rebuilding = False
            if self._rebuild_wanted:
                self._rebuild_wanted = False
                self._rebuild_after_id = self.root.after_idle(self._rebuild_ui)

    # ---------- content pane ----------

    def _build_content(self, s):
        pad = int(CONTENT_PAD * s)
        body = tk.Frame(self.content, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        title = tk.Frame(body, bg=BG)
        title.pack(fill="x")
        self.game_title = tk.Label(title, text="", bg=BG, fg=INK, anchor="w",
                                   font=("Segoe UI", fs(14, s), "bold"))
        self.game_title.pack(side="left")
        self.game_state = tk.Label(title, text="", bg=BG, fg=MUTED, anchor="e",
                                   font=("Segoe UI", fs(9, s)))
        self.game_state.pack(side="right")
        self.game_note = tk.Label(body, text="", bg=BG, fg=MUTED, anchor="w",
                                  justify="left", wraplength=int((CONTENT_W - 32) * s),
                                  font=("Segoe UI", fs(8.5, s)))
        self.game_note.pack(fill="x", pady=(int(2 * s), int(12 * s)))

        # ── tab bar (story #24 feature 2): Hotkey | Clicking ──
        self.content_tab_var = tk.StringVar(value=self._content_tab)
        TabBar(body, [("hotkey", "Hotkey"), ("clicking", "Clicking")],
              self.content_tab_var, s).pack(anchor="w", pady=(0, int(12 * s)))
        self.content_tab_var.trace_add("write",
            lambda *_a: self._set_content_tab(self.content_tab_var.get()))

        # Both panes are built in full, always, whichever tab is active --
        # _select()/_persist()/_sync_settings() all read/write Clicking/
        # Eating widgets unconditionally (docs/spec.md's "Cross-references
        # into hidden widgets" section), so lazily building only the active
        # pane would break them the moment a different tab was showing.
        # Build order matters: both panes are built and packed here, in
        # this stacked order, and only hidden by _set_content_tab() at the
        # very end -- card()'s own _redraw() reads real geometry off a
        # still-mapped shell, and pack_forget() afterward does not erase an
        # already-computed width (verified empirically, see docs/spec.md's
        # "Test impact" section).
        self._pane_fills = {}   # story #24 feature 4: {"hotkey": (pane, top,
            # bottom), ...} -- looked up by _run_pane_fill(), reached via
            # _set_content_tab()/_set_settings_tab()/_select()'s own
            # _request_pane_fill() requests (G#28/GH#48 round 5).

        self.hotkey_pane = tk.Frame(body, bg=BG)
        self.hotkey_pane.pack(fill="both", expand=True)
        self.hotkey_pane.pack_propagate(False)   # story #24 feature 4: this
            # pane's own children (including its two spacers, whose whole
            # job is to change size) must never feed back into the pane's
            # own requested size -- it already gets its real size from
            # body's fill=both/expand=True alone (matching self.content's
            # own pack_propagate(False), same reasoning). Without this, a
            # spacer resize can itself change the pane's own reqheight,
            # cascading into a further geometry pass that re-fires this same
            # pane's <Configure> -- a genuine feedback loop, confirmed
            # empirically (Xvfb probe, not committed).
        hotkey_top = tk.Frame(self.hotkey_pane, bg=BG, height=0)
        hotkey_top.pack(fill="x")
        section(self.hotkey_pane, "Hotkey  ·  shared by every game", s, top=0)
        hk = card(self.hotkey_pane, s)
        row = Row(hk, "Toggle", s)
        row.pack(fill="x")
        self.hotkey_label = tk.Label(row.control, text="Not set", bg=CARD, fg=MUTED,
                                     font=("Consolas", fs(10, s)))
        self.hotkey_label.pack(side="right", padx=(0, int(8 * s)))
        btns = tk.Frame(hk, bg=CARD)
        btns.pack(fill="x", pady=(int(8 * s), 0))
        Button(btns, "Record", self.register_hotkey, s, width=124).pack(side="left")
        self.apply_button = Button(btns, "Apply", self.apply_hotkey, s, width=124,
                                   primary=True)
        self.apply_button.pack(side="right")
        self.apply_button.set_enabled(False)
        hotkey_bottom = tk.Frame(self.hotkey_pane, bg=BG, height=0)
        hotkey_bottom.pack(fill="x")
        self._pane_fills["hotkey"] = (self.hotkey_pane, hotkey_top, hotkey_bottom)
        self.hotkey_pane.bind("<Configure>",
            lambda e: self._request_pane_fill("hotkey"))

        self.clicking_pane = tk.Frame(body, bg=BG)
        self.clicking_pane.pack(fill="both", expand=True)
        self.clicking_pane.pack_propagate(False)   # story #24 feature 4 --
            # see hotkey_pane's own comment above for why.
        clicking_top = tk.Frame(self.clicking_pane, bg=BG, height=0)
        clicking_top.pack(fill="x")
        # No "Clicking" section header here -- the tab label above already
        # names the pane (docs/design.md's redundant-header decision).
        cl = card(self.clicking_pane, s)
        self.interval_row = Row(cl, "Interval", s)
        self.interval_row.pack(fill="x")
        self.click_ms = NumBox(self.interval_row.control, DEFAULT_CLICK_MS, "ms", s)
        self.click_ms.pack()
        # G#22/GH#33 round 2: the sweep warning lives in this row's own hint
        # slot now, not a new one under Interval (docs/design.md Revision 2,
        # Decision A2 -- height-neutral, since the warning is always as
        # short or shorter than the static text it temporarily replaces).
        self.jitter_row = Row(cl, "Random jitter", s,
                               hint="spreads the rhythm so it is not exact",
                               mutable_hint=True)
        self.jitter_row.pack(fill="x", pady=(int(6 * s), 0))
        self.jitter_ms = NumBox(self.jitter_row.control, 0, "±ms", s); self.jitter_ms.pack()
        r = Row(cl, "Auto-stop", s, hint="0 means never"); r.pack(fill="x", pady=(int(6 * s), 0))
        self.autostop_min = NumBox(r.control, 0, "min", s); self.autostop_min.pack()
        r = Row(cl, "Mouse button", s); r.pack(fill="x", pady=(int(8 * s), 0))
        self.button_name = tk.StringVar(value="left")
        Segmented(r.control, [("left", "Left"), ("right", "Right"), ("middle", "Mid")],
                  self.button_name, s, width=180).pack()

        # "Eating" is kept -- it is a sub-section within Clicking, not a
        # tab (docs/design.md), still Minecraft-only and conditionally
        # shown by _select() exactly as today.
        self.eat_section = section(self.clicking_pane, "Eating", s)
        self.eat_card_inner = card(self.clicking_pane, s,
                                    on_settle=self._on_eat_card_settled)
        self.eat_card = self.eat_card_inner.master
        self.eat_mode = tk.StringVar(value="off")
        Segmented(self.eat_card_inner,
                  [("pause", "Pause & eat"), ("hold", "Hold RMB"), ("off", "Off")],
                  self.eat_mode, s).pack(anchor="w", pady=(0, int(8 * s)))
        r = Row(self.eat_card_inner, "Eat every", s); r.pack(fill="x")
        self.eat_every = NumBox(r.control, DEFAULT_EAT_EVERY_S, "s", s); self.eat_every.pack()
        r = Row(self.eat_card_inner, "Hold for", s); r.pack(fill="x", pady=(int(6 * s), 0))
        self.eat_hold = NumBox(r.control, DEFAULT_EAT_HOLD_S, "s", s); self.eat_hold.pack()
        clicking_bottom = tk.Frame(self.clicking_pane, bg=BG, height=0)
        clicking_bottom.pack(fill="x")
        self._pane_fills["clicking"] = (self.clicking_pane, clicking_top, clicking_bottom)
        self.clicking_pane.bind("<Configure>",
            lambda e: self._request_pane_fill("clicking"))

        # Any edit belongs to the selected game, so persist as it happens.
        for var in (self.click_ms.var, self.jitter_ms.var, self.autostop_min.var,
                    self.button_name, self.eat_mode, self.eat_every.var,
                    self.eat_hold.var):
            var.trace_add("write", lambda *_a: self._persist())

        self._set_content_tab(self._content_tab)   # hide the inactive pane last

    def _build_settings(self, s):
        """The Settings page: Appearance (3a), Updates (3b) -- structurally
        parallel to _build_content(s), a padded body frame built straight
        into self.content, torn down/rebuilt the same way by _rebuild_ui()'s
        blanket root.winfo_children() teardown, no special casing.

        The Updates section below builds self.update_button/self.version_
        label with the exact constructor shapes they had in the sidebar --
        check_update/_set_update_state/_offer_update need no signature
        changes. Only the idle defaults are set here; the actual current
        state (idle, checking, an offer, downloading, an error) is applied
        right after this returns, by _build_ui()'s tail (docs/history/ac-17-f3b-spec.md §3)."""
        pad = int(CONTENT_PAD * s)
        body = tk.Frame(self.content, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        title = tk.Frame(body, bg=BG)
        title.pack(fill="x")
        tk.Label(title, text="Settings", bg=BG, fg=INK, anchor="w",
                 font=("Segoe UI", fs(14, s), "bold")).pack(side="left")

        # ── tab bar (story #24 feature 2): Appearance | Updates ──
        self.settings_tab_var = tk.StringVar(value=self._settings_tab)
        TabBar(body, [("appearance", "Appearance"), ("updates", "Updates")],
              self.settings_tab_var, s).pack(anchor="w", pady=(int(12 * s), int(12 * s)))
        self.settings_tab_var.trace_add("write",
            lambda *_a: self._set_settings_tab(self.settings_tab_var.get()))

        # Both panes are built in full, always -- update_button/version_
        # label must exist unconditionally whenever Settings is open (the
        # existing `if not self._settings_open` guard in _offer_update()/
        # _set_update_state() already assumes exactly this contract, and
        # this feature does not change either method). See _build_content()'s
        # own comment for why build-then-pack-then-hide is the required order.
        self._pane_fills = {}   # story #24 feature 4 -- see _build_content()'s
            # own comment for the shape and how it's consumed.

        self.appearance_pane = tk.Frame(body, bg=BG)
        self.appearance_pane.pack(fill="both", expand=True)
        self.appearance_pane.pack_propagate(False)   # story #24 feature 4 --
            # see _build_content()'s hotkey_pane comment for why.
        appearance_top = tk.Frame(self.appearance_pane, bg=BG, height=0)
        appearance_top.pack(fill="x")
        # No "Appearance" section header here -- the tab label above
        # already names the pane (docs/design.md's redundant-header decision).
        ap = card(self.appearance_pane, s)
        row = Row(ap, "Theme", s)
        row.pack(fill="x")
        self.appearance_var = tk.StringVar(value=self.store.data["appearance"])
        # 3-option Segmented inside a Row's control area -- same width as the
        # other 3-option control in this file (button_name, "Mouse button"
        # above): ROW_LABEL_W + ROW_LABEL_GAP + 180 = 152 + 180 = 332, well
        # inside CARD_INNER_W (396) since Row's fixed label column now sits
        # ahead of it, not a variable-width label sharing the row.
        Segmented(row.control, [("system", "System"), ("light", "Light"), ("dark", "Dark")],
                  self.appearance_var, s, width=180).pack()

        # Second Row in the same card, below Theme
        # (docs/history/ac-17-f4-spec.md §5) -- 5-option Segmented since
        # G#38/GH#67 added "Auto" as the default, narrower per-option
        # (48.8px) than Theme's own 3-option control (60px/option). 244px
        # is CARD_INNER_W (396) minus Row's fixed ROW_LABEL_W + ROW_LABEL_GAP
        # (152) label column -- the most 5 options can take without
        # overflowing the card (docs/design.md's layout math), at every
        # UI-scale step since every quantity here scales by the same s (the
        # invariant-ratio argument, docs/history/ac-17-f4-spec.md §1).
        row2 = Row(ap, "UI scale", s)
        row2.pack(fill="x", pady=(int(8 * s), 0))
        self.ui_scale_var = tk.StringVar(value=self.store.data["ui_scale"])
        Segmented(row2.control,
                  [("auto", "Auto"), ("90", "90%"), ("100", "100%"),
                   ("115", "115%"), ("130", "130%")],
                  self.ui_scale_var, s, width=244).pack()

        # G#21/GH#32 item 4 (docs/design.md): a single, non-blocking notice
        # for a Store.save() failure. Not packed here -- _paint_save_notice()
        # (called from _build_ui()'s tail, alongside its existing update-
        # state replay) shows/hides it based on self._save_failed, which
        # survives a rebuild since it lives on self, not on this (torn-down-
        # and-rebuilt) pane's own widgets.
        self.save_failed_label = tk.Label(
            ap, text="Couldn't save settings — changes won't be kept after closing",
            bg=CARD, fg=BAD, font=("Segoe UI", fs(9.5, s)),
            wraplength=int(CARD_INNER_W * s), justify="left", anchor="w")

        # Detected at most once per process (docs/history/ac-17-f3a-spec.md §4) -- if nothing
        # has needed the real OS theme yet (appearance started as "light"/
        # "dark", so __main__ never detected it), this is that first need;
        # after this, self._os_theme is cached for the rest of the run.
        if self._os_theme is None:
            self._os_theme = detect_os_theme()
        tk.Label(ap, text=f"System is currently {self._os_theme}", bg=CARD, fg=MUTED,
                 anchor="w", font=("Segoe UI", fs(8, s))).pack(fill="x", pady=(int(6 * s), 0))
        appearance_bottom = tk.Frame(self.appearance_pane, bg=BG, height=0)
        appearance_bottom.pack(fill="x")
        self._pane_fills["appearance"] = (self.appearance_pane, appearance_top, appearance_bottom)
        self.appearance_pane.bind("<Configure>",
            lambda e: self._request_pane_fill("appearance"))

        self.appearance_var.trace_add("write",
            lambda *_a: self._apply_appearance(self.appearance_var.get()))
        # Registered after the Segmented(...) call above, exactly like
        # appearance_var's own trace -- Tcl fires write traces most-
        # recently-registered-first, so this trace (_apply_ui_scale) fires
        # before the Segmented's own built-in repaint trace, not after it.
        # Under the current code this ordering has no observable effect:
        # _apply_ui_scale only ever defers the rebuild via
        # _request_rebuild()/after_idle and never rebuilds synchronously
        # inside the trace (verified empirically -- reversing this
        # registration order and running the full suite still passes; see
        # docs/history/ac-17-f4-implementation.md's fix-pass section). The ordering is kept
        # anyway, matching Theme's, because it is the order that would be
        # required if _apply_ui_scale (or _apply_appearance) ever stopped
        # deferring and rebuilt synchronously instead: getting it backwards
        # in that scenario destroys the Segmented mid-repaint and raises
        # TclError (docs/history/ac-17-f4-spec.md §2, same hazard as Theme's).
        self.ui_scale_var.trace_add("write",
            lambda *_a: self._apply_ui_scale(self.ui_scale_var.get()))

        self.updates_pane = tk.Frame(body, bg=BG)
        self.updates_pane.pack(fill="both", expand=True)
        self.updates_pane.pack_propagate(False)   # story #24 feature 4 --
            # see _build_content()'s hotkey_pane comment for why.
        updates_top = tk.Frame(self.updates_pane, bg=BG, height=0)
        updates_top.pack(fill="x")
        # No "Updates" section header here -- same redundant-header decision
        # as Appearance above.
        up = card(self.updates_pane, s)
        row = Row(up, "Version", s)
        row.pack(fill="x")
        self.version_label = tk.Label(row.control, text=f"v{__version__}", bg=CARD,
                                      fg=MUTED, font=("Consolas", fs(9, s)))
        self.version_label.pack()
        self.update_button = Button(up, "Check for updates", self.check_update, s,
                                    width=CARD_INNER_W)
        self.update_button.pack(pady=(int(8 * s), 0))
        updates_bottom = tk.Frame(self.updates_pane, bg=BG, height=0)
        updates_bottom.pack(fill="x")
        self._pane_fills["updates"] = (self.updates_pane, updates_top, updates_bottom)
        self.updates_pane.bind("<Configure>",
            lambda e: self._request_pane_fill("updates"))

        self._set_settings_tab(self._settings_tab)   # hide the inactive pane last

    def _note_save(self, ok):
        """Every direct caller of self.store.save()/put_game() routes its
        result through here (docs/CODING-GUIDELINES.md "Failure behaviour":
        name a read-only config directory instead of a silent no-op). Only
        acts on a *change* in outcome -- a run of keystroke-driven _persist()
        failures while a directory stays read-only repaints nothing after
        the first one, and a later successful save clears the notice --
        so this never re-announces the same, still-ongoing failure.

        Every one of the five call sites (_apply_appearance, _apply_ui_
        scale, _select's persist branch, _persist()/put_game, apply_hotkey)
        runs on the main thread already -- none of them is reachable from a
        background thread today -- so this touches self.save_failed_label
        directly rather than routing through self._ui()/_drain_ui().

        test-review.md round 1, Defect 1: self._rebuilding is True for the
        exact window where this must NOT touch self.save_failed_label --
        _rebuild_ui()'s own leading self._persist() call runs after the old
        widget tree has been (or is about to be) torn down and before
        _build_ui() has built a fresh one, so the label either doesn't
        exist yet (a session's first-ever _show_settings()) or still points
        at an already-destroyed widget (Settings closed once, then
        reopened after a save failed while it was closed). The outcome is
        still recorded unconditionally -- only the repaint is deferred --
        so _build_ui()'s own tail (which calls _paint_save_notice()
        directly, unconditionally, once the fresh tree -- and, if
        self._settings_open, a fresh self.save_failed_label -- exists)
        picks up exactly this flag and paints correctly."""
        if ok == (not self._save_failed):
            return
        self._save_failed = not ok
        if self._rebuilding:
            return
        self._paint_save_notice()

    def _paint_save_notice(self):
        # Appearance-pane-local, mirroring _set_update_state()'s own
        # if-not-open-remember-and-return pattern: the flag survives
        # regardless of which pane is currently showing (a hotkey apply or a
        # game-field edit can fail to save while sitting on a different
        # tab), and gets painted the next time Appearance is (re)built too,
        # via _build_ui()'s own tail (docs/design.md).
        if not (self._settings_open and self._settings_tab == "appearance"):
            return
        if self._save_failed:
            self.save_failed_label.pack(fill="x", pady=(int(8 * self.s), 0))
        else:
            self.save_failed_label.pack_forget()

    def _apply_appearance(self, value):
        self.store.data["appearance"] = value
        self._note_save(self.store.save())
        resolved = resolve_appearance(value, self._os_theme)
        if value == "system" and self._os_theme is None:
            self._os_theme = resolved   # memoize -- a later System pick this
                                         # session must not call detect_os_theme()
                                         # a second time
        set_active_theme(resolved)
        # Deferred, not called inline: this runs from the Segmented's own
        # "write" trace on appearance_var, and Tcl fires a variable's traces
        # most-recently-added-first -- this one first, then the Segmented's
        # own built-in repaint trace (registered when it was built, in
        # _build_settings). Rebuilding here synchronously would destroy that
        # Segmented canvas out from under its own still-pending repaint,
        # which then raises TclError trying to redraw a widget that no
        # longer exists. after_idle() lets every trace on this click finish
        # against the still-live old tree first; the rebuild itself runs a
        # moment later, once the event has fully unwound.
        #
        # Coalesced: a second (or fifth) Appearance change landing before
        # the first's idle rebuild has run must NOT queue a second
        # after_idle job -- see _rebuild_ui()'s own docstring for why a
        # second pending rebuild is a real crash, not just wasted work. The
        # theme itself is already applied above (set_active_theme(resolved)
        # runs synchronously on every call), so whichever choice was latest
        # when the one pending rebuild finally runs is exactly what it
        # rebuilds against -- nothing further needs to be remembered here.
        #
        # Reentrant call (docs/history/ac-17-f3a-test-review.md Round 2 review, Finding #1):
        # if _apply_appearance() is itself called while a rebuild is
        # already RUNNING (self._rebuilding), self._rebuild_after_id was
        # already cleared to None at that rebuild's own top -- scheduling a
        # fresh after_idle job here would be reentrantly serviced by a
        # LATER card() call's own update_idletasks() in that SAME
        # still-running rebuild, reproducing Defect 1's crash via a
        # different door than Round 2 already closed (not currently
        # reachable -- the only real caller today is a <Button-1>-driven
        # trace, and update_idletasks() never services real window/mouse
        # events -- but made impossible outright rather than left as a
        # documented-but-unenforced invariant). Just mark a follow-up
        # wanted; _rebuild_ui()'s own finally block schedules exactly one
        # once the running rebuild has fully finished. This tail is shared
        # with _apply_ui_scale() via _request_rebuild() -- see its own
        # docstring; the reasoning above still applies unchanged.
        self._request_rebuild()

    def _apply_ui_scale(self, value):
        """Structurally parallel to _apply_appearance(): persist, apply the
        synchronous part of the change (self.s and the window's minsize),
        then request the shared coalesced rebuild. The `value not in
        UI_SCALE_FACTORS and value != "auto"` guard mirrors Store.__init__'s
        own sanitization -- the Segmented this is wired to only ever emits
        one of the five valid keys, but an invalid self.s would be a
        visibly broken window, not just a wrong color, so the same
        belt-and-suspenders defense is cheap insurance here.

        G#38/GH#67: picking "auto" computes self.s from the window's
        *current* size immediately (the window is already mapped -- Settings
        is only reachable post-launch), it does not wait for the next
        resize and does not silently keep whatever self.s a previous fixed
        step left behind (docs/spec.md §3)."""
        if value not in UI_SCALE_FACTORS and value != "auto":
            value = UI_SCALE_DEFAULT
        self.store.data["ui_scale"] = value
        self._note_save(self.store.save())
        if value == "auto":
            self.s = self._auto_scale_factor(self.root.winfo_width(), self.root.winfo_height())
        else:
            self.s = self._dpi_s * UI_SCALE_FACTORS[value]
        self._apply_minsize(grow_only=True)
        self._request_rebuild()

    def _show_settings(self):
        if self._settings_open:
            return
        self._settings_open = True
        self._rebuild_ui()

    def _request_pane_fill(self, key):
        """Coalescing tail for every _fill_pane() call site (G#28/GH#48
        round 5): a single Eating-card growth cascade fires
        _on_eat_card_settled() once per <Configure> its shell receives --
        traced at 14 calls for one pane build on Windows CI -- and every
        one of those is a full measure-and-write pass over the pane. Worse
        than the wasted work itself: each pass is real Tk/Python churn on
        the allocation scale GH#46's own trace shows triggering a worker-
        thread GC that finalizes a leaked Variable off the main thread and
        aborts Tcl (ubuntu CI). Only the LAST call in a burst ever matters
        -- every earlier one measures a `natural` a later call in the same
        burst immediately supersedes -- so every call site below (the tab-
        switch tails, _select()'s own tail, every pane's <Configure>-bound
        lambda, and on_settle) requests a deferred pass here instead of
        calling _fill_pane() directly, and repeated requests for the same
        burst collapse into the one pass that actually runs.

        Mirrors _request_rebuild()/_rebuild_ui()'s own _rebuilding/
        _rebuild_wanted pair exactly, and for the same reason: a deferred
        pass must still land LAST, not merely once. If _run_pane_fill() is
        already executing (self._pane_filling) when another request lands
        -- e.g. from a further growth step _fill_pane()'s own
        update_idletasks() reentrantly drains while the deferred pass is
        already mid-measurement -- this re-arms exactly one follow-up pass
        instead of running inline (which would reproduce the very
        reentrancy _rebuild_ui()'s docstring warns about) or being
        silently dropped (which would reintroduce the stale-`natural` race
        round 2 fixed)."""
        if self._pane_filling:
            self._pane_fill_wanted = key
            return
        self._pane_fill_key = key
        if self._pane_fill_after_id is None:
            self._pane_fill_after_id = self.root.after_idle(self._run_pane_fill)

    def _run_pane_fill(self):
        """The one deferred pass _request_pane_fill() above schedules.
        Re-arms itself, via _request_pane_fill(), for exactly one follow-up
        if a further request landed while this call's own _fill_pane() was
        running -- see _request_pane_fill()'s docstring."""
        self._pane_fill_after_id = None
        key = self._pane_fill_key
        self._pane_fill_key = None
        self._pane_filling = True
        try:
            fill = self._pane_fills.get(key)
            if fill is not None:
                _fill_pane(*fill)
        finally:
            self._pane_filling = False
            if self._pane_fill_wanted is not None:
                wanted = self._pane_fill_wanted
                self._pane_fill_wanted = None
                self._request_pane_fill(wanted)

    def _on_eat_card_settled(self):
        """card()'s on_settle callback for eat_card (story #24 feature 4 /
        G#28 GH#48): request a deferred _fill_pane() pass for the clicking
        pane every time the Eating card's own shell actually finishes
        resizing, closing the reentrancy gap _select()/_set_content_tab()'s
        own tails leave open -- they can run before eat_card's
        <Configure>-triggered _redraw() has settled to the card's real
        final height, so the `natural` they measure can be stale-too-small
        (see docs/implementation.md's round-2 section for the traced
        mechanism). Whatever an earlier request wrote gets overwritten by
        the eventual deferred pass with the correct split once the true
        height is known.

        Routed through _request_pane_fill() rather than calling
        _fill_pane() directly (round 5): this fires once per growth step --
        traced at up to 13 times for one Eating-card growth cascade -- and
        _request_pane_fill() collapses however many of those land in one
        burst into a single actual pass. See its own docstring.

        Guarded on `_content_tab == "clicking"`: this must never touch the
        pane while Clicking isn't the active tab -- reading a hidden pane's
        winfo_height() is the exact unmapped-widget hazard this story has
        hit before (_select()'s own tail carries the identical guard).
        `_pane_fills` doesn't have "clicking" yet the first time this
        fires (card()'s own unconditional initial _redraw() call happens
        before _build_content() populates `_pane_fills`) -- harmless here
        since _run_pane_fill()'s own `.get()` already no-ops on a missing
        key, so nothing further needs guarding against it above."""
        if self._content_tab == "clicking":
            self._request_pane_fill("clicking")

    def _set_content_tab(self, value):
        """Toggle which game-page pane is packed. Both panes are always
        built in full by _build_content() before this ever runs (see its
        own comment) -- this only ever changes which one is visible, never
        which widgets exist, so _select()/_persist()/_sync_settings() keep
        reading/writing Clicking/Eating widgets exactly as before regardless
        of which tab happens to be showing.

        Also keeps content_tab_var (the TabBar's own indicator) in step,
        since this method is reachable two ways: a real tab click (the
        var's own "write" trace calls this) and a direct call (e.g. this
        pane's own end-of-build line, or a future caller like a game switch
        that wants to force a tab). Without this, a direct call would move
        the pane but leave the underline pointing at the old tab. The
        `!=` guard is not an optimization: Tcl fires a variable's write
        traces even when the new value equals the old one, so writing the
        var unconditionally here would immediately re-enter this method via
        that trace -- and again, since the value is already `value`, forever.
        Guarding on an actual change makes that second call a no-op (its own
        `!=` check now says "already equal") and terminates one call deep."""
        if value not in ("hotkey", "clicking"):
            value = "hotkey"
        self._content_tab = value
        if self.content_tab_var.get() != value:
            self.content_tab_var.set(value)
        self.hotkey_pane.pack_forget()
        self.clicking_pane.pack_forget()
        (self.hotkey_pane if value == "hotkey" else self.clicking_pane).pack(
            fill="both", expand=True)
        # Story #24 feature 4: belt-and-suspenders recompute for the newly-
        # active pane -- the pack() call above already fires a correctly-
        # sized <Configure> on it (Empirical grounding #3), so this does
        # not depend on Tk's own event-dispatch timing. Routed through
        # _request_pane_fill() (G#28/GH#48 round 5), not called directly:
        # the <Configure> this pack() fires already requests the same key,
        # so this and that collapse into one deferred pass instead of two
        # separate immediate ones.
        self._request_pane_fill(value)

    def _set_settings_tab(self, value):
        """Same toggle as _set_content_tab(), for the Settings page's
        Appearance/Updates panes -- update_button/version_label stay built
        unconditionally whenever Settings is open, matching the existing
        `if not self._settings_open` guard in _offer_update()/
        _set_update_state(). Keeps settings_tab_var in step for the same
        reason and with the same re-entrancy guard as _set_content_tab()
        above -- see its docstring."""
        if value not in ("appearance", "updates"):
            value = "appearance"
        self._settings_tab = value
        if self.settings_tab_var.get() != value:
            self.settings_tab_var.set(value)
        self.appearance_pane.pack_forget()
        self.updates_pane.pack_forget()
        (self.appearance_pane if value == "appearance" else self.updates_pane).pack(
            fill="both", expand=True)
        # Story #24 feature 4: same belt-and-suspenders recompute as
        # _set_content_tab()'s own tail -- see its comment, including for
        # why this is routed through _request_pane_fill() (G#28/GH#48
        # round 5).
        self._request_pane_fill(value)
        # G#21/GH#32 item 4: a save failure that happened while Updates was
        # showing (self._save_failed already True, but _paint_save_notice()
        # returned early -- it only ever paints while Appearance itself is
        # the active tab) must become visible the moment the user switches
        # to Appearance, not only on the next full rebuild -- switching
        # tabs alone never rebuilds either pane, so nothing else would ever
        # call this again.
        self._paint_save_notice()

    # ---------- game list ----------

    def _rebuild_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.items = {}
        for profile in self.profiles:
            item = GameItem(self.list_frame, profile, self._select, self.s,
                            collapsed=self._rail_collapsed)
            item.pack(fill="x", pady=int(1 * self.s))
            self.items[profile["id"]] = item
        self.count_label.config(text=f"GAMES   {len(self.profiles)}")

    def _select(self, game_id, persist=True):
        if self._settings_open:
            self._settings_open = False
            self._rebuild_ui()
        self.current = game_id
        profile = self.by_id[game_id]
        for gid, item in self.items.items():
            item.set_state(selected=(gid == game_id))
        self.game_title.config(text=profile["name"])
        self.game_note.config(text=profile["note"])

        # Fill the form from this game's saved values, defaults where absent.
        self._loading = True
        values = dict(profile["defaults"])
        values.update({k: v for k, v in self.store.game(game_id).items()
                       if not k.startswith("_")})
        self.click_ms.var.set(fmt_num(values["click_ms"]))
        self.jitter_ms.var.set(fmt_num(values["jitter_ms"]))
        self.autostop_min.var.set(fmt_num(values["autostop_min"]))
        self.button_name.set(values["button"])
        self.eat_every.var.set(fmt_num(values["eat_every"]))
        self.eat_hold.var.set(fmt_num(values["eat_hold"]))
        self.eat_mode.set(values["eat_mode"] if profile["eating"] else "off")
        self._loading = False

        # The eating panel is Minecraft's, not everyone's -- hide it rather than
        # leave a dead control sitting there for games it means nothing to.
        #
        # `before=clicking_bottom` (story #24 feature 4) is load-bearing, not
        # cosmetic: pack_forget() unmanages a widget, and a later plain
        # pack() re-adds it at the END of its master's current packing list,
        # not back where it was -- confirmed empirically against this app's
        # own widgets (Xvfb probe, not committed). Without `before=`, the
        # first eating->non-eating->eating cycle would re-pack eat_section/
        # eat_card AFTER the already-packed bottom spacer, putting the
        # spacer above the Eating card instead of below it.
        clicking_bottom = self._pane_fills["clicking"][2]
        if profile["eating"]:
            self.eat_section.pack(fill="x", pady=(int(14 * self.s), int(6 * self.s)),
                                  before=clicking_bottom)
            self.eat_card.pack(fill="x", before=clicking_bottom)
        else:
            self.eat_section.pack_forget()
            self.eat_card.pack_forget()

        # Story #24 feature 4: the one trigger nothing Tk-driven ever fires
        # for -- toggling a child's pack state inside an already-expand=True
        # pane produces zero <Configure> events on the pane itself (Empirical
        # grounding #2). Guarded on the Clicking tab actually being visible:
        # reading a hidden pane's winfo_height() would be the exact
        # unmapped-widget hazard this story has hit before. Routed through
        # _request_pane_fill() (G#28/GH#48 round 5) -- see _set_content_tab()'s
        # own tail for why.
        if self._content_tab == "clicking":
            self._request_pane_fill("clicking")

        if persist:
            self.store.data["selected"] = game_id
            self._note_save(self.store.save())
        self._persist()

    def _note_sweep_hint(self, profile, values):
        """G#22/GH#33: compute the jitter row's dynamic hint from
        _persist()'s own already-_num()-coerced values (docs/spec.md
        "Proposed approach" item 4) -- the hint can never disagree with
        what the worker actually runs with, because it never re-reads the
        fields itself. Reused, unmodified, by every _persist() trigger: a
        keystroke, a profile switch (_select()'s own tail call), and a
        theme/scale rebuild (_rebuild_ui()'s own leading call).

        Round 2 (docs/design.md Revision 2 + its Orchestrator correction):
        the 550-649 ms band is INK bold, not MUTED bold -- MUTED is this
        codebase's plain secondary-text colour (every static row hint, the
        NumBox unit labels, ...), so a warning in it would still read as
        secondary text, one weight heavier. INK bold reads as "this
        matters"; BAD bold (<550 ms) stays the visibly stronger of the two
        bands by colour, so the ordering holds. Both are read as bare
        module globals here, at the moment this method runs (after
        set_active_theme() has already reassigned them on a theme rebuild),
        never a value captured earlier.

        Only *records* self._sweep_hint_pending unconditionally; the actual
        widget touch is deferred whenever self._rebuilding is True, mirroring
        _note_save()/_paint_save_notice() exactly (this feature's own
        Orchestrator correction, restating G#21/PR #78's Defect 1):
        _rebuild_ui()'s leading self._persist() call runs while the old
        jitter row is being (or is about to be) torn down, and the new one
        does not exist yet -- _build_ui()'s own tail (see _paint_sweep_hint's
        one other caller) is the safe point once a fresh one does."""
        min_sweep = profile["min_sweep_ms"]
        effective_min = max(50, values["click_ms"] - values["jitter_ms"])
        if min_sweep is not None and effective_min < min_sweep:
            if effective_min < MIN_SWEEP_BAD_MS:
                self._sweep_hint_pending = (SWEEP_HINT_BAD, BAD)
            else:
                self._sweep_hint_pending = (SWEEP_HINT_MUTED, INK)
        else:
            self._sweep_hint_pending = None
        if not self._rebuilding:
            self._paint_sweep_hint()

    def _paint_sweep_hint(self):
        """The one place that actually shows the jitter row's warning band
        or restores its static descriptive text, from whatever
        _note_sweep_hint() last computed. Safe to call once the current
        widget tree exists -- called from there directly (not mid-rebuild)
        and, unconditionally, from _build_ui()'s own tail once
        _build_content()/_select() have just (re)built self.jitter_row
        fresh.

        Round 2 (docs/design.md Revision 2, Decision A2): the hint slot
        itself is never hidden -- set_hint(..., bold=True) or
        restore_hint() only swap its text/colour/weight. But the row's own
        *height* still changes (the warning is one line, the restored
        static text can be two, per docs/design.md's own wrap precedent),
        so _request_pane_fill("clicking") still fires on an actual
        band-active/inactive *transition* (self._sweep_band_active), not on
        every keystroke -- most keystrokes just change text/colour within
        an already-active or already-inactive state -- and only while the
        Clicking tab is actually visible (_select()'s own identical guard,
        :3445): reading a hidden pane's geometry is the exact hazard
        _on_eat_card_settled()'s own docstring warns about.

        Guarded on self._settings_open exactly the way _paint_save_notice()
        guards on it (in the opposite direction): self.jitter_row only
        exists in the content tree, torn down (not rebuilt) while Settings
        is showing, so a call landing here with Settings open -- e.g.
        on_close()'s own unconditional _persist() call, with Settings left
        open -- would otherwise retext a destroyed widget. Round 1's
        clear_hint()/pack_forget() tolerated a stale widget silently; this
        round's set_hint()/restore_hint() go through .config(), which
        raises TclError on one, so the guard is now load-bearing rather
        than accidentally unnecessary."""
        if self._settings_open:
            return
        state = self._sweep_hint_pending
        now_active = state is not None
        if now_active:
            text, colour = state
            self.jitter_row.set_hint(text, colour, bold=True)
        else:
            self.jitter_row.restore_hint()
        if now_active != self._sweep_band_active:
            self._sweep_band_active = now_active
            if self._content_tab == "clicking":
                self._request_pane_fill("clicking")

    def _persist(self):
        if self._loading:
            return
        profile = self.by_id[self.current]
        values = {
            "click_ms": self._num(self.click_ms, profile["defaults"]["click_ms"], 50),
            "jitter_ms": self._num(self.jitter_ms, 0, 0),
            "autostop_min": self._num(self.autostop_min, 0, 0),
            "button": self.button_name.get(),
            "eat_mode": self.eat_mode.get(),
            "eat_every": self._num(self.eat_every, DEFAULT_EAT_EVERY_S, 5),
            "eat_hold": self._num(self.eat_hold, DEFAULT_EAT_HOLD_S, 0.5),
        }
        self._note_sweep_hint(profile, values)
        if profile.get("custom"):
            values["_profile"] = {"id": profile["id"], "name": profile["name"],
                                  "title": profile["titles"][0]}
        self._note_save(self.store.put_game(self.current, values))

    def add_current_game(self):
        def scan():
            title = foreground_title()
            self._ui(self._add_game, title)
        threading.Thread(target=scan, daemon=True).start()

    def _add_game(self, title):
        if not title:
            self.game_state.config(text="no window found", fg=BAD)
            return
        name = title.strip()[:28]
        game_id = "custom:" + name.lower()
        if game_id in self.by_id:
            self._select(game_id)
            return
        profile = make_profile(game_id, name, name)
        self.profiles.append(profile)
        self.by_id[game_id] = profile
        self._rebuild_list()
        self._select(game_id)

    # ---------- updates ----------

    def check_update(self):
        # A new check supersedes any previous offer (PR #31 review, Round 2
        # BLOCKER): _check_worker's own branches (unchanged below) never
        # touch self._pending/settings_item -- they only ever add an offer,
        # never retract one. Without this, a stale offer's sidebar mark and
        # the button's install_update wiring could survive past the very
        # check that resolves it (e.g. "Up to date" landing right after an
        # earlier offer). The install-failure retry path is untouched: a
        # checksum/verification error still leaves self._pending set, so
        # retrying the same install stays possible.
        self._pending = None
        self._check_seq += 1
        seq = self._check_seq
        self.settings_item.set_state(has_update=False)
        if self._settings_open:
            self.update_button.command = self.check_update
        self._set_update_state("Checking…", enabled=False)
        threading.Thread(target=self._check_worker, args=(seq,), daemon=True).start()

    def _check_worker(self, seq):
        try:
            release = latest_release()
        except NoReleases:
            self._ui(self._apply_check_state, seq, "No releases published yet", True)
            return
        if release is None:
            self._ui(self._apply_check_state, seq, "GitHub unreachable", True, BAD)
            return
        tag = release.get("tag_name", "")
        if not is_newer(tag):
            self._ui(self._apply_check_state, seq, f"Up to date · {__version__}", True)
            return
        asset = pick_asset(release)
        if asset is None:
            self._ui(self._apply_check_state, seq, f"{tag}: no build for this OS", True, BAD)
            return
        self._ui(self._apply_check, seq, tag, asset, release)

    def _apply_check_state(self, seq, text, enabled=True, colour=None):
        # test-review.md round 1, Finding 2: the same stale-result guard as
        # _apply_check() below, for _check_worker's four non-offer branches
        # (NoReleases/unreachable/not-newer/no-build-for-OS). Without this,
        # an orphaned older worker's "Up to date"/"GitHub unreachable"/etc.
        # could still land -- and overwrite the button/version-label text --
        # after a newer worker's offer has already been applied, the exact
        # supersession bug _apply_check()'s own gate exists to close, just
        # on the non-offer branches the spec's own proposed diff didn't
        # gate.
        if seq != self._check_seq:
            return
        self._set_update_state(text, enabled, colour)

    def _apply_check(self, seq, tag, asset, release):
        # Main-thread gate, mirroring _apply_scan()'s stale-scan guard
        # (G#39/GH#69, afk_clicker.py's own _poll_games()/_apply_scan()): an
        # orphaned older worker (started by a check_update() call a newer
        # one has already superseded) must not overwrite self._pending/the
        # offer state with a stale release once a newer check has moved
        # past it. Also the only place self._pending is ever written now --
        # always from here, always on the main thread via _ui()/_drain_ui(),
        # never directly from _check_worker's own background thread.
        if seq != self._check_seq:
            return
        self._pending = (tag, asset, release)
        self._offer_update(tag)

    def _offer_update(self, tag):
        self._update_text = (f"Install {tag}", True, None)
        # settings_item is unconditionally present in the sidebar (unlike
        # update_button/version_label below), so this needs no guard -- it's
        # what makes an offer found while sitting on a game page, with no
        # rebuild in sight, visible without waiting for one.
        self.settings_item.set_state(has_update=True)
        if not self._settings_open:
            return
        self.update_button.set_text(f"Install {tag}")
        self.update_button.set_primary(True)
        self.update_button.set_enabled(True)
        self.update_button.command = self.install_update
        self.version_label.config(text=f"v{__version__} → {tag}", fg=ACCENT)

    def install_update(self):
        if not is_frozen():
            # From source there is nothing to swap, and silently doing nothing
            # would look like a broken button.
            self._set_update_state("Run `git pull` — not a build", True, BAD)
            return
        self._set_update_state("Downloading… 0%", enabled=False)
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        tag, asset, release = self._pending
        try:
            sums_asset = pick_checksums(release)
            if sums_asset is None:
                # Fail closed. An update that cannot be checked is exactly the
                # one worth refusing: it downloads code and then runs it.
                self._ui(self._set_update_state,
                         f"{tag} publishes no {CHECKSUM_ASSET}", True, BAD)
                return
            checksums = fetch_checksums(sums_asset)
            staged = download_and_stage(
                asset, checksums=checksums,
                on_progress=lambda f: self._ui(self._set_update_state,
                                               f"Downloading… {f * 100:.0f}%", False))
            target = install_root()
            if not os.access(target, os.W_OK):
                self._ui(self._set_update_state, "Install folder is read-only", True, BAD)
                return
            log_path = os.path.join(os.path.dirname(config_path()), "update.log")
            # Fail safe, not closed: target_version is best-effort
            # diagnostics (the log's own "wrong_version" detection), not
            # load-bearing for the update itself -- an unexpectedly-shaped
            # tag_name (from GitHub's API, untrusted) is treated the same
            # as "version unknown" (write_swap_script's own existing
            # default), never passed through to a generated script. See
            # _is_safe_version_tag's own docstring for why: this is a
            # security fix (command injection via tag_name), not a
            # cosmetic validation nicety.
            safe_target_version = tag if _is_safe_version_tag(tag) else None
            script = write_swap_script(staged, target, sys.executable, log_path,
                                       target_version=safe_target_version)
        except ChecksumError as exc:
            # Say what happened. "Update failed" for a digest mismatch reads
            # like a network problem and invites a retry.
            self._ui(self._set_update_state, str(exc)[:40], True, BAD)
            return
        except Exception as exc:
            self._ui(self._set_update_state, f"Update failed: {exc}"[:40], True, BAD)
            return
        self._ui(self._quit_for_update, script)

    def _quit_for_update(self, script):
        self._set_update_state("Restarting…", enabled=False)
        launch_swap_script(script)
        self.on_close()

    def _set_update_state(self, text, enabled=True, colour=None):
        self._update_text = (text, enabled, colour)
        if not self._settings_open:
            return
        self.update_button.set_text(text)
        self.update_button.set_enabled(enabled)
        if colour:
            self.version_label.config(text=text, fg=colour)

    # ---------- update-log report dialog (G#36/GH#64) ----------

    def _maybe_offer_log_report(self):
        """The one startup check this feature adds: is there a previous
        in-app update attempt's log lying around, and did it actually
        finish? A no-op for "ok" (no log at all, or one that finished and
        landed the expected version) -- see update_log_status().

        The log's path is derived from self.store.path, not the bare
        config_path() module function _install_worker itself calls --
        identical in production (Store() with no override IS config_path()),
        but this is the only way tests can point a whole AfkAutoclicker at
        a temp settings directory (app.Store(self.config), the same
        isolation UITestCase already uses) without this prompt ever
        touching a real machine's actual settings directory.

        Belt and braces (round 3, test-review.md): on_close() now cancels
        the after_idle() job that calls this before it can fire against a
        torn-down root (the actual, tracked-down fix for the macOS CI
        failure -- see self._log_report_after_id's own comment), but this
        guards the case anyway, since a scheduled Tk callback's cancel
        guarantees around root.destroy() are apparently not airtight on
        every platform. Everything above this docstring's return is pure
        file I/O, no Tk; only _show_update_log_dialog() below touches
        widgets, so that's the only call wrapped."""
        log_path = os.path.join(os.path.dirname(self.store.path), "update.log")
        status = update_log_status(log_path)
        if status == "ok":
            return
        log_text = read_update_log(log_path) or ""
        target_version = _extract_target_version(log_text)
        try:
            self._show_update_log_dialog(status, log_path, log_text, target_version)
        except tk.TclError:
            pass    # the root this would have built a dialog against is gone

    def _capture_log_dialog_restore_state(self):
        """A plain-data snapshot of the update-log dialog's own state --
        not widgets, not Variables -- for _rebuild_ui() to recreate an
        equivalent dialog after tearing the old one down for a theme/UI-
        scale change (test-review.md round 2 Defect 1). None if no dialog
        is currently open."""
        ctx = self._log_dialog_ctx
        if ctx is None:
            return None
        return {
            "status": ctx["status"], "log_path": ctx["log_path"],
            "log_text": ctx["log_text"], "target_version": ctx["target_version"],
            "show_paths": bool(ctx["show_paths_var"].get()),
            "fallback_url": ctx.get("url"),
        }

    def _restore_log_dialog(self, state):
        """Rebuilds the update-log dialog from a snapshot
        _capture_log_dialog_restore_state() took before the previous
        generation was torn down. Never re-runs update_log_status() and
        never re-triggers "ask once" -- the log's own status/text/
        target_version are replayed exactly as captured, not looked up
        again; if the log had already been renamed to .reported by the
        time of this rebuild, there would be no captured state to restore
        in the first place (a fresh update_log_status() call would have
        nothing to find)."""
        self._show_update_log_dialog(state["status"], state["log_path"],
                                     state["log_text"], state["target_version"])
        if state["show_paths"]:
            self._log_dialog_ctx["show_paths_var"].set(True)
        if state["fallback_url"] is not None:
            self._show_log_fallback(state["fallback_url"])

    def _show_update_log_dialog(self, status, log_path, log_text, target_version):
        """Builds and shows the one-off Toplevel (docs/design.md "Dialog
        appears"). Transient, not modal -- no wait_window() -- there is
        nothing else demanding attention at launch (docs/spec.md "Where it
        appears")."""
        s = self.s
        top = tk.Toplevel(self.root, bg=BG)
        top.title("Update failed")
        top.transient(self.root)
        top.minsize(int(480 * s), int(300 * s))
        top.geometry(f"{int(600 * s)}x{int(480 * s)}")

        show_paths_var = tk.BooleanVar(value=False)   # unchecked by default
                                                        # -> redacted by default
        self._log_dialog = top
        self._log_dialog_show_paths_var = show_paths_var   # see __init__'s
                                                        # own comment on this
                                                        # attribute
        self._log_dialog_ctx = {
            "status": status, "log_path": log_path, "log_text": log_text,
            "target_version": target_version, "show_paths_var": show_paths_var,
        }

        top.protocol("WM_DELETE_WINDOW", self._on_log_dismiss)
        top.bind("<Escape>", lambda e: self._on_log_dismiss())

        body = tk.Frame(top, bg=BG)
        body.pack(fill="both", expand=True,
                  padx=int(CONTENT_PAD * s), pady=int(CONTENT_PAD * s))
        self._log_dialog_ctx["body"] = body

        tk.Label(body, text="Update failed", bg=BG, fg=INK, anchor="w",
                font=("Segoe UI", fs(14, s), "bold")).pack(fill="x", pady=(0, int(8 * s)))

        explanation = ("The last update didn't finish. Your clicker still "
                      "works — this just notifies us of the failure."
                      if status == "incomplete" else
                      "The last update relaunched the old version. Your "
                      "clicker still works — this just notifies us of the failure.")
        tk.Label(body, text=explanation, bg=BG, fg=MUTED, anchor="w", justify="left",
                wraplength=int(560 * s), font=("Segoe UI", fs(9, s))
                ).pack(fill="x", pady=(0, int(12 * s)))

        tk.Label(body, text="Preview of what will be sent to GitHub:", bg=BG, fg=MUTED,
                anchor="w", font=("Segoe UI", fs(9, s))).pack(fill="x", pady=(0, int(4 * s)))

        preview_frame = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        preview_frame.pack(fill="both", expand=True, pady=(0, int(16 * s)))
        # An explicit height, not tk.Text's own 24-row default: 24 rows of
        # Consolas plus this frame's own padding requests more vertical
        # space than the dialog has to give (confirmed the hard way -- an
        # unbounded default height silently squeezed the checkbox/button
        # rows below it down to 0px, still packed, never mapped, so no
        # click ever reached them). 12 rows leaves headroom for the rest of
        # the layout at the dialog's default 600x480 size; fill="both" +
        # expand=True still lets it grow into any extra space the person
        # resizes the window to.
        preview = tk.Text(preview_frame, bg=BG, fg=INK, wrap="word", relief="flat",
                          font=("Consolas", fs(10, s)), height=12,
                          padx=int(CARD_PAD * s), pady=int(CARD_PAD * s))
        scrollbar = tk.Scrollbar(preview_frame, command=preview.yview)
        preview.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        preview.pack(side="left", fill="both", expand=True)
        self._log_dialog_ctx["preview"] = preview

        checkbox_row = tk.Frame(body, bg=BG)
        checkbox_row.pack(fill="x", pady=(0, int(16 * s)))
        checkbox = ToggleCheckbox(checkbox_row, show_paths_var, s)
        checkbox.pack(side="left")
        tk.Label(checkbox_row, text="Show full local paths", bg=BG, fg=INK,
                font=("Segoe UI", fs(9.5, s))).pack(side="left", padx=(int(8 * s), 0))
        show_paths_var.trace_add("write", lambda *_a: self._refresh_log_preview())

        button_row = tk.Frame(body, bg=BG)
        button_row.pack(fill="x")
        fallback_row = tk.Frame(body, bg=BG)
        self._log_dialog_ctx["button_row"] = button_row
        self._log_dialog_ctx["fallback_row"] = fallback_row

        send_btn = Button(button_row, "Send via GitHub", self._on_log_send, s,
                          primary=True, width=120)
        send_btn.pack(side="left")
        dismiss_btn = Button(button_row, "Dismiss", self._on_log_dismiss, s, width=100)
        dismiss_btn.pack(side="left", padx=(int(8 * s), 0))
        open_btn = Button(button_row, "Open log folder", self._on_log_open_folder,
                          s, width=130)
        open_btn.pack(side="left", padx=(int(8 * s), 0))
        self._log_dialog_ctx["send_button"] = send_btn
        self._log_dialog_ctx["dismiss_button"] = dismiss_btn
        self._log_dialog_ctx["open_button"] = open_btn

        top.bind("<Return>", lambda e: self._on_log_send())
        self._refresh_log_preview()
        self._fit_log_dialog_to_content()

    def _fit_log_dialog_to_content(self):
        """Grows (never shrinks) the dialog to fit whatever it currently
        contains. `top.geometry(f"{w}x{h}")` in _show_update_log_dialog
        gives the dialog a sensible *initial* size (design's 600x480 mock)
        -- but per Tk's own `wm geometry` semantics, that explicit size
        call also switches this toplevel from automatic resize-to-content
        to a fixed size for every geometry request after it. The fallback
        row (an Entry plus 2 buttons, ~67px) is taller than the default
        3-button row it replaces (~35px); without this, the extra ~32px is
        silently clipped at the window's bottom edge (test-review.md round
        2 Defect 2 -- reproduced live: body.winfo_reqheight() 510 vs the
        pinned top.winfo_height() 500 at 100% scale). Called at the tail of
        both _show_update_log_dialog (covers the ordinary case, and a
        rebuild landing at a different UI scale) and _show_log_fallback
        (covers the layout swap itself)."""
        top, ctx = self._log_dialog, self._log_dialog_ctx
        top.update_idletasks()
        needed_h = ctx["body"].winfo_reqheight() + 2 * int(CONTENT_PAD * self.s)
        if needed_h > top.winfo_height():
            top.geometry(f"{top.winfo_width()}x{needed_h}")

    def _current_log_report(self):
        ctx = self._log_dialog_ctx
        return build_issue_report(__version__, ctx["target_version"], ctx["log_text"],
                                  redact=not ctx["show_paths_var"].get())

    def _refresh_log_preview(self):
        """Redaction must update the *visible* preview immediately, not
        just future sends (docs/spec.md "Redaction correctness") -- bound
        to show_paths_var's own write trace, so every checkbox click (and
        the initial build) runs through this one path."""
        ctx = self._log_dialog_ctx
        if ctx is None:
            return
        title, body = self._current_log_report()
        preview = ctx["preview"]
        preview.config(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", f"{title}\n\n{body}")
        preview.config(state="disabled")

    def _mark_log_reported(self):
        """The sole "seen" marker (docs/spec.md "Asking once, without new
        settings state") -- no new Store key, just renaming the log itself.
        Best-effort, same "not worth crashing over" posture as
        Store.save(): a failed rename (e.g. a read-only settings dir) just
        means the prompt reappears next launch, not a crash."""
        log_path = self._log_dialog_ctx["log_path"]
        try:
            os.replace(log_path, log_path + ".reported")
        except OSError:
            pass

    def _close_log_dialog(self):
        """Tears down the dialog and, just as importantly, the trace(s) on
        its "show full paths" Variable -- a Variable is not a widget, so
        destroying the Toplevel below never touches them (same "outgoing
        generation's traces" gap _forget_traces() exists for elsewhere in
        this file). Left alone, that Variable -- still holding a live
        reference to the ToggleCheckbox's own repaint callback and this
        dialog's _refresh_log_preview, both now pointed at destroyed
        widgets -- is exactly the ac-27 "trace outlives its widgets"
        pattern: a later .set() call raises TclError into a destroyed
        widget, and even with no such call, cyclic GC finalizing the
        Variable off the main thread is its own separate failure mode.
        Used by every path that ends this dialog's life: Dismiss, a
        successful Send, and _rebuild_ui()'s pre-teardown cleanup."""
        if self._log_dialog_show_paths_var is not None:
            var = self._log_dialog_show_paths_var
            for modes, cbname in var.trace_info():
                var.trace_remove(modes, cbname)
        if self._log_dialog is not None:
            try:
                self._log_dialog.destroy()
            except tk.TclError:
                pass
        self._log_dialog = None
        self._log_dialog_ctx = None
        self._log_dialog_show_paths_var = None

    def _on_log_dismiss(self):
        """Dismiss, Escape, and the OS close button all funnel here (design
        doc "Dialog dismissed") -- all three are a real, final "no" for
        this attempt."""
        self._mark_log_reported()
        self._close_log_dialog()

    def _on_log_open_folder(self):
        """Deliberately does not mark the log as seen (docs/spec.md
        acceptance criteria) -- the person can still Send/Dismiss the same
        dialog afterward. Best-effort: a missing xdg-open/failed launcher
        is not worth crashing the dialog over."""
        folder = os.path.dirname(self._log_dialog_ctx["log_path"])
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError:
            pass

    def _on_log_send(self):
        title, body = self._current_log_report()
        url = build_issue_url(title, body)
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            self._show_log_fallback(url)
            return
        self._mark_log_reported()
        self._close_log_dialog()

    def _show_log_fallback(self, url):
        """webbrowser.open() returned False or raised (docs/spec.md
        "Opening the browser") -- rather than silently failing, replace the
        button row with the raw URL (read-only, selectable) plus a Copy
        link button, so the person can still report by hand."""
        s = self.s
        ctx = self._log_dialog_ctx
        ctx["url"] = url
        ctx["button_row"].pack_forget()
        fallback_row = ctx["fallback_row"]
        for child in fallback_row.winfo_children():
            child.destroy()

        # Text inserted directly, then locked read-only -- not a
        # textvariable=. A textvariable-linked readonly Entry's initial
        # sync from the variable was observed to silently stay blank deep
        # into a long test run (reproducible only after ~300 other tests'
        # worth of accumulated Tk/Tcl state in the same process; never in
        # isolation) with no root cause pinned down worth the risk of
        # shipping -- inserting the text directly needs no variable, no
        # trace, and no sync step at all, so there is nothing left for that
        # failure mode to attach to.
        entry = tk.Entry(fallback_row, fg=INK, relief="flat",
                         highlightthickness=1, highlightbackground=LINE,
                         font=("Consolas", fs(9, s)))
        entry.insert(0, url)
        entry.config(state="readonly", readonlybackground=BG)
        entry.pack(fill="x", pady=(0, int(8 * s)))
        actions = tk.Frame(fallback_row, bg=BG)
        actions.pack(fill="x")
        copy_btn = Button(actions, "Copy link", self._on_log_copy_link, s, width=100)
        copy_btn.pack(side="left")
        dismiss_btn = Button(actions, "Dismiss", self._on_log_dismiss, s, width=100)
        dismiss_btn.pack(side="left", padx=(int(8 * s), 0))
        fallback_row.pack(fill="x")
        ctx["fallback_entry"] = entry
        ctx["copy_button"] = copy_btn
        ctx["fallback_dismiss_button"] = dismiss_btn
        self._fit_log_dialog_to_content()

    def _on_log_copy_link(self):
        url = self._log_dialog_ctx.get("url", "")
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

    def _poll_games(self):
        # Weak, not self, and dropped before the blocking call: _window_
        # titles() opens a fresh Xlib connection on every call, and that
        # connection setup can stall for an unbounded time (observed
        # directly, roughly 1 scan in a couple hundred, stuck inside
        # Xlib.display.Display() itself). profiles is a plain, self-
        # contained list of dicts, so holding only that (not self) across
        # the blocking detect_running() call means a scan stuck there does
        # not keep this whole UI -- and every tkinter.Variable it owns --
        # reachable for as long as that one thread has not returned, no
        # matter how long the app (or, in the test suite, a since-closed
        # window) is already gone. Left holding self there, whichever
        # thread eventually dropped that reference (or merely ran a GC pass
        # while still holding it) was not necessarily the main one -- which
        # is how a stale Variable gets finalized off the main thread and
        # aborts the interpreter ("Tcl_AsyncDelete: async handler deleted
        # by the wrong thread").
        #
        # self._poll_thread is overwritten here on every call, including the
        # periodic 5000ms reschedule below, with no join of whatever scan it
        # just superseded (G#39/GH#69 PR #70 review, Finding #1). Joining the
        # predecessor before starting a new one was considered and rejected:
        # the whole reason this method holds only a weak self is that a scan
        # can stall for an unbounded time, so blocking a new scan on an old
        # one finishing would let one stuck Display() connection freeze
        # detection entirely instead of merely delaying one indicator update.
        # Instead, each scan is stamped with a monotonically increasing
        # sequence number (self._poll_seq, touched only here, on the main
        # thread) and handed back to _apply_scan() below, which drops any
        # result older than the newest one already applied -- so an
        # orphaned, slower scan landing after a newer one can no longer
        # clobber it, no matter which thread finishes first or how long the
        # older one takes.
        weak = weakref.ref(self)
        self._poll_seq += 1
        seq = self._poll_seq

        def scan():
            me = weak()
            if me is None:
                return
            profiles = me.profiles
            del me
            running = detect_running(profiles)
            me = weak()
            if me is not None:
                me._ui(me._apply_scan, seq, running)
        # Tracked (not fire-and-forget) so on_close() can join it: every
        # rebuild calls _poll_games() again (_build_ui()'s own tail, so the
        # running-games indicator survives a theme/scale change), and nothing
        # else ever waits for that scan to land before a later on_close()
        # runs. Most of the time it finishes in well under a millisecond, but
        # for that brief window scan() above does hold a real reference back
        # to this UI on its own thread -- on_close() racing that window is
        # the common (not just the stuck-Display() rare) way a Variable ends
        # up finalized off the main thread.
        self._poll_thread = threading.Thread(target=scan, daemon=True)
        self._poll_thread.start()
        self._timers["poll_games"] = self.root.after(5000, self._poll_games)

    def _apply_scan(self, seq, running):
        """
        Main-thread gate in front of _mark_running(), for real scan results
        only: drops `running` if `seq` is older than the newest scan already
        applied, so a slow scan orphaned by a later, faster one (see
        _poll_games()'s own comment) can't land afterward and overwrite
        fresher data with stale window state (G#39/GH#69 PR #70 review).
        Both self._poll_seq (assigned) and self._poll_applied_seq (compared)
        are only ever touched from the main thread -- this method itself
        runs via _drain_ui(), and _poll_games() runs via a Tk callback/
        after(), so there is no cross-thread race on either counter.
        _mark_running() itself keeps its existing signature and behaviour
        unchanged for every other, non-scan caller (this test suite calls it
        directly via self.ui._ui(self.ui._mark_running, ...) in several
        places, deliberately bypassing sequencing -- a hand-queued value
        isn't a scan result and has no sequence number to compare).
        """
        if seq < self._poll_applied_seq:
            return
        self._poll_applied_seq = seq
        self._mark_running(running)

    def _mark_running(self, running_ids):
        for gid, item in self.items.items():
            item.set_state(running=(gid in running_ids))
        # Follow the game the first time it appears, then leave the choice
        # alone: silently overriding a hand-picked profile every five seconds
        # would be maddening.
        fresh = running_ids - getattr(self, "_seen_running", set())
        self._seen_running = running_ids
        if fresh and self.current not in running_ids:
            self._select(sorted(fresh)[0])
        # Only now, so the label describes the game that ended up selected.
        if self.current in running_ids:
            self.game_state.config(text="running", fg=OK)
        else:
            self.game_state.config(text="not detected", fg=MUTED)

    # ---------- helpers ----------

    def _num(self, field, fallback, minimum):
        """Entry boxes are user-editable, so never trust them at click time."""
        try:
            return max(minimum, float(field.var.get()))
        except (TypeError, ValueError):
            return fallback

    def _maybe_drop_focus(self, event):
        # Only an Entry's own class binding should keep it focused on click --
        # every other click (background, a label, a card, the sidebar, a
        # Button/Segmented/GameItem canvas) drops it, so a field stops looking
        # and acting focused the moment you click away instead of only when
        # Tk happens to hand focus to something else.
        if not isinstance(event.widget, tk.Entry):
            self.root.focus_set()

    def _ui(self, fn, *args):
        """
        Hand a widget update to the main thread.

        Not root.after() -- that is itself a Tk call, and calling it from a
        worker raises "main thread is not in main loop". A plain queue drained
        by _drain_ui() keeps every Tk touch on the thread that owns it.
        """
        self._ui_queue.put((fn, args))

    def _drain_ui(self):
        while True:
            try:
                fn, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except tk.TclError:
                if not self.root.winfo_exists():
                    return                  # window is really going away
                continue                    # a rebuilt/destroyed widget's stale
                                             # closure -- drop it, keep draining
        self._timers["drain"] = self.root.after(40, self._drain_ui)

    def _set_status(self, text, color, hint=""):
        """Looked up fresh here, on the main thread when _drain_ui() actually
        calls it -- never a bound self.status.set captured at enqueue time.
        start()/stop()/loop() run on the worker thread, and a rebuild can
        replace self.status with a new StatusPill between one of their
        self._ui(...) calls landing in the queue and _drain_ui() draining it;
        a captured self.status.set would target the old, now-destroyed
        canvas and raise TclError (docs/history/ac-17-f3a-spec.md "the actual correctness
        fix"). Every other queued callback (_offer_update, _set_update_state,
        _mark_running, ...) already resolves its target this way -- this
        makes the status pill's the same."""
        self.status.set(text, color, hint)

    def _sync_settings(self):
        """
        Snapshot every control into a plain dict for the worker thread.

        Reading a StringVar from another thread is the same unsupported Tk
        access as above; it happens to work while the main loop is spinning and
        raises when it is not. The worker reads this dict instead, so the
        clicking thread never touches Tk at all.
        """
        try:
            self.settings = {
                "click_ms": self._num(self.click_ms, DEFAULT_CLICK_MS, 50),
                "jitter_ms": self._num(self.jitter_ms, 0, 0),
                "autostop_min": self._num(self.autostop_min, 0, 0),
                "button": self.button_name.get(),
                "eat_mode": self.eat_mode.get(),
                "eat_every": self._num(self.eat_every, DEFAULT_EAT_EVERY_S, 5),
                "eat_hold": self._num(self.eat_hold, DEFAULT_EAT_HOLD_S, 0.5),
            }
        except tk.TclError:
            return
        self._timers["sync_settings"] = self.root.after(200, self._sync_settings)

    # ---------- hotkey ----------

    def register_hotkey(self):
        if self.capture_thread and self.capture_thread.is_alive():
            return
        self.hotkey_label.config(text="Press up to 3 keys, then let go…", fg=ACCENT)
        self.hotkey = None
        self.capture_thread = threading.Thread(target=self.capture_hotkey, daemon=True)
        self.capture_thread.start()

    def capture_hotkey(self):
        if not macos_input_permitted():
            self._ui(self._hotkey_error, "Accessibility permission not granted")
            return
        rec = HotkeyRecorder()
        try:
            with kb.Listener(on_press=rec.press, on_release=rec.release) as listener:
                listener.join()
        except Exception as exc:                   # no X11, or macOS denied access
            self._ui(self._hotkey_error, str(exc))
            return

        hotkey = rec.result()
        if hotkey is not None:
            self.hotkey = hotkey
            self._ui(self._hotkey_captured)
        else:
            self._ui(self._show_hotkey, self.registered_hotkey)

    def _show_hotkey(self, active):
        self.hotkey_label.config(text=active.label() if active else "Not set",
                                 fg=INK if active else MUTED)

    def _hotkey_captured(self):
        self.hotkey_label.config(text=f"{self.hotkey.label()}   · not applied",
                                 fg=ACCENT)
        self.apply_button.set_enabled(True)

    def _hotkey_error(self, detail):
        # On Wayland pynput has no way to see global keys, and on macOS the app
        # needs Accessibility permission. Both surface here as a failed listener,
        # and both are fixable by the user -- so say which, do not just die.
        self.hotkey_label.config(text=HOTKEY_HELP, fg=BAD)
        print(f"hotkey listener failed: {detail}", file=sys.stderr)

    def apply_hotkey(self):
        if not self.hotkey:
            return
        # Without this the old watcher stays live and both keys toggle the clicker.
        if self.hk_listener is not None:
            self.hk_listener.stop()
            self.hk_listener = None
        if not macos_input_permitted():
            # Starting the listener here would trap, not raise. Keep the
            # recorded combination (self.hotkey) so applying it again after
            # the permission is granted works without re-recording -- but
            # registered_hotkey means a listener is running for this, and
            # none is (the stop() above already cleared hk_listener even if
            # an earlier Apply had one running), so it must be reset to None
            # explicitly here, not just left alone.
            self.registered_hotkey = None
            self._hotkey_error("Accessibility permission not granted")
            return
        try:
            self.hk_listener = HotkeyWatcher(self.hotkey, self.toggle)
            self.hk_listener.start()
        except Exception as exc:
            self.hk_listener = None
            self._hotkey_error(exc)
            return
        self.registered_hotkey = self.hotkey
        self.store.data["hotkey"] = self.hotkey.to_json()
        self._note_save(self.store.save())
        self.hotkey_label.config(text=self.hotkey.label(), fg=INK)
        self.apply_button.set_enabled(False)
        self.status.set("OFF", BAD, f"{self.hotkey.label()} toggles")

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
        self._ui(self.root.focus_set)
        self._ui(self._set_status, "RUNNING", OK,
                 self.registered_hotkey.label() if self.registered_hotkey else "")
        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self._ui(self._set_status, "OFF", BAD,
                 self.registered_hotkey.label() if self.registered_hotkey else "")

    def _sleep(self, seconds):
        """Interruptible sleep, so toggling off reacts immediately."""
        deadline = time.monotonic() + seconds
        while self.running and time.monotonic() < deadline:
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
        return self.running

    def _release_right(self):
        if self.right_held:
            self.mouse.release(MouseButton.right)
            self.right_held = False

    CLICK_BUTTON = {"left": MouseButton.left, "right": MouseButton.right,
                    "middle": MouseButton.middle}

    def loop(self):
        try:
            started = last_meal = time.monotonic()
            while self.running:
                # Auto-stop is a safety net, not a feature: an autoclicker left
                # running against an empty farm is the thing that gets an
                # account flagged, and the thing that is still clicking when you
                # come back to the desk. 0 keeps the old always-on behaviour.
                cfg = self.settings
                limit = cfg.get("autostop_min", 0)
                if limit and time.monotonic() - started >= limit * 60:
                    self._ui(self._set_status, "STOPPED", MUTED, f"auto-stop after {limit:g} min")
                    self.running = False
                    break
                # Re-read every pass, like the numeric fields already are:
                # picking the mode up once meant switching the control did
                # nothing until you toggled the clicker off and on again.
                mode = cfg.get("eat_mode", "off")
                interval = cfg.get("click_ms", DEFAULT_CLICK_MS) / 1000.0
                jitter = cfg.get("jitter_ms", 0) / 1000.0
                if jitter:
                    # Spread around the set interval, never below the 50 ms
                    # floor the field itself enforces.
                    interval = max(0.05, interval + random.uniform(-jitter, jitter))
                button = self.CLICK_BUTTON.get(cfg.get("button", "left"), MouseButton.left)

                if mode == "hold":
                    if not self.right_held:
                        self.mouse.press(MouseButton.right)
                        self.right_held = True
                elif self.right_held:
                    # Left "hold" (or switched to off) -- do not leave the
                    # button down, that keeps blocking/eating forever.
                    self._release_right()

                if mode == "pause" and button is MouseButton.left:
                    every = cfg.get("eat_every", DEFAULT_EAT_EVERY_S)
                    if time.monotonic() - last_meal >= every:
                        self._ui(self._set_status, "EATING", ACCENT, "clicks paused")
                        hold = cfg.get("eat_hold", DEFAULT_EAT_HOLD_S)
                        self.mouse.press(MouseButton.right)
                        self.right_held = True
                        self._sleep(hold)          # no left-clicks here, or the eat cancels
                        self._release_right()
                        last_meal = time.monotonic()
                        if not self.running:
                            break
                        self._ui(self._set_status, "RUNNING", OK,
                 self.registered_hotkey.label() if self.registered_hotkey else "")

                self.mouse.click(button)
                if not self._sleep(interval):
                    break
        except Exception as exc:
            # Without this the flag stays set: the window keeps saying RUNNING,
            # the hotkey thinks it is already on and toggling does nothing,
            # and no click has happened since the throw.
            self._ui(self._set_status, "ERROR", BAD, str(exc)[:32])
            self.running = False
        finally:
            self.running = False
            self._release_right()

    def _forget_traces(self):
        """Release every write-trace registered on a Variable this UI owns.

        Segmented/TabBar register their repaint trace on the *variable*
        they are given, not on themselves (afk_clicker.py's Segmented/
        TabBar __init__), so destroying the widget never removes it --
        it is a leftover backlog item (see backlog.md, "Segmented never
        calls trace_remove") that turned out to matter for more than a
        dangling callback: the registered command is a live reference the
        Tcl interpreter's own command table holds back to whatever bound
        method it wraps, however many rebuilds ago that widget was
        replaced. destroy() only walks a widget's *own* bindings
        (Misc.destroy()'s self._tclCommands), never a trace registered on
        someone else's Variable, so nothing else ever clears this. Left in
        place, that reference chain (interpreter -> trace command ->
        bound method -> this whole UI -> every tkinter.Variable it owns)
        keeps the interpreter itself alive past on_close()/root.destroy()
        -- Python's own refcounting can never free a live C-level
        reference, no matter how much of the rest of the graph is
        otherwise unreachable. Walking every Variable this UI can reach
        (directly, or one NumBox-style ".var" attribute down) and clearing
        trace_info() here, rather than tracking each trace_add() call site
        by hand, is what keeps this correct as new controls get added --
        a call site missed by hand is exactly how the backlog item above
        happened once already.
        """
        for value in vars(self).values():
            var = value if isinstance(value, tk.Variable) else getattr(value, "var", None)
            if isinstance(var, tk.Variable):
                for modes, cbname in var.trace_info():
                    var.trace_remove(modes, cbname)

    def on_close(self):
        # G#38/GH#67 round 2 (PR #89 review): unbound first, before anything
        # below cancels a single already-pending _auto_settle_after_id job.
        # That cancellation only ever guards a job armed BEFORE on_close()
        # started -- with _on_root_resize still bound, a <Configure> firing
        # any time later in this same teardown (root.destroy() itself can
        # generate one) would re-arm a fresh job that nothing after that
        # point ever cancels again, later firing into a destroyed
        # interpreter. Unbinding here closes that off outright, the same
        # "make it impossible outright" preference the _rebuild_after_id
        # cancellation below already documents for its own job.
        self.root.unbind("<Configure>")
        self._persist()
        # The update-log dialog (G#36/GH#64), in whatever state it's
        # currently in -- the ordinary preview or the browser-failed
        # fallback, it's the same Toplevel either way. root.destroy() below
        # would tear it down anyway, but going through _close_log_dialog()
        # also clears its Variable's trace(s) (see that method's own
        # docstring) rather than leaving them to outlive their widgets.
        if self._log_dialog is not None:
            self._close_log_dialog()
        # Pending after() callbacks fire into a destroyed interpreter and Tcl
        # reports them as "invalid command name". Cancel them first.
        for job in getattr(self, "_timers", {}).values():
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._timers = {}
        # Same reasoning as _timers above, for the one job not kept there:
        # an Appearance change's deferred after_idle(self._rebuild_ui) can
        # still be pending here (_apply_appearance() ran, _rebuild_ui()
        # never got a chance to). Left uncancelled it fires after destroy()
        # into a Tcl interpreter that no longer has the command registered
        # -- "invalid command name" (docs/test-review.md's "Investigated,
        # not a defect": unreachable via a real mainloop(), but one line to
        # make it impossible outright).
        if self._rebuild_after_id is not None:
            try:
                self.root.after_cancel(self._rebuild_after_id)
            except tk.TclError:
                pass
            self._rebuild_after_id = None
        # Same reasoning, for _request_auto_settle()'s own deferred job
        # (G#38/GH#67): a live Auto-mode drag can still have a pending
        # settle timer here (a <Configure> fired, _on_auto_settle() never
        # got a chance to run).
        if self._auto_settle_after_id is not None:
            try:
                self.root.after_cancel(self._auto_settle_after_id)
            except tk.TclError:
                pass
            self._auto_settle_after_id = None
        # Same reasoning, for _request_pane_fill()'s own deferred job
        # (G#28/GH#48 round 5): a pane-fill can still be pending here (an
        # on_settle/<Configure> fired, _run_pane_fill() never got a chance
        # to).
        if self._pane_fill_after_id is not None:
            try:
                self.root.after_cancel(self._pane_fill_after_id)
            except tk.TclError:
                pass
            self._pane_fill_after_id = None
        # Same reasoning again, for the startup after_idle(self._
        # maybe_offer_log_report) job (G#36/GH#64 round 3, test-review.md):
        # a test (or a real close happening in the sliver of time before
        # the main window's first idle pass) can reach on_close() before
        # this job ever got a turn. Previously untracked entirely -- the
        # exact G#39-class bug (an unclosed scheduled callback surviving
        # teardown) -- reliably invisible on Linux/Windows's idle-flush
        # timing, reliably fatal on macOS CI once the queued call finally
        # ran against an already-destroyed root.
        if self._log_report_after_id is not None:
            try:
                self.root.after_cancel(self._log_report_after_id)
            except tk.TclError:
                pass
            self._log_report_after_id = None
        self.stop()
        if self.hk_listener is not None:
            self.hk_listener.stop()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)   # let it run its own release first
        if self._poll_thread and self._poll_thread.is_alive():
            # See _poll_games()'s own comment: bounded, not indefinite, since
            # a stuck Xlib.display.Display() connection must not hang close.
            self._poll_thread.join(timeout=2.0)
        self._release_right()          # never leave a mouse button stuck down
        # G#27/ac-27 round 2 (PR #47): this used to also release bind_all()'s
        # funcid (unbind_all()+deletecommand()) and sweep every Variable's
        # traces (self._forget_traces()) here, right after cancelling the
        # jobs above and right before root.destroy() below. That combination
        # reproduced a macOS-only interpreter abort twice in CI
        # (`Tcl_FindHashEntry on deleted table`, exit 134) that could not be
        # reproduced on Linux (55+ runs) or explained mechanically without
        # macOS access, so both calls were reverted rather than guessed at
        # further -- see docs/implementation.md's "Round 2" section and
        # backlog.md. The reference leaks they were closing are real and are
        # back on backlog.md, open.
        # self.stop() above (and any update still in flight from a worker)
        # queues through self._ui() rather than touching a widget directly,
        # and _drain_ui()'s own recurring after() job -- the only thing that
        # would otherwise empty this -- was already cancelled above. An
        # item left sitting in self._ui_queue is a normal (self ->
        # _ui_queue -> queued args tuple -> a bound method -> self) cycle,
        # but it is still a live reference back to this whole UI until
        # something breaks it -- discarded here, not run, since every
        # widget it would touch is seconds (or, by the time this actually
        # drains, already) gone.
        while True:
            try:
                self._ui_queue.get_nowait()
            except queue.Empty:
                break
        self.root.destroy()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    enable_dpi_awareness()
    # Store constructed here (earlier than before) so the saved appearance
    # is known before the first widget is built. detect_os_theme() runs at
    # most once, only when the saved choice actually needs it -- a saved
    # "light"/"dark" never shells out at all.
    store = Store()
    appearance = store.data["appearance"]
    os_theme = detect_os_theme() if appearance == "system" else None
    set_active_theme(resolve_appearance(appearance, os_theme))
    root = tk.Tk()
    # Segoe UI is the Windows system face; falling back keeps Linux usable.
    if "Segoe UI" not in tkfont.families():
        root.option_add("*Font", "TkDefaultFont")
    AfkAutoclicker(root, store=store, os_theme=os_theme)
    root.mainloop()

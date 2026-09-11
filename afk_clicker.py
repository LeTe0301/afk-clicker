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
import queue
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from pynput import keyboard as kb
# Imported under a different name: the Tk widget class below is also called
# Button, and the shadowing turned every mouse action into an AttributeError.
from pynput.mouse import Button as MouseButton, Controller

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
if sys.platform == "darwin":
    HOTKEY_HELP = "Grant Accessibility permission, then reopen"
elif sys.platform.startswith("linux"):
    HOTKEY_HELP = "Needs an X11 session (Wayland blocks global keys)"
else:
    HOTKEY_HELP = "Could not register the hotkey"

SIDEBAR_W = 208
CONTENT_W = 452
CARD_INNER_W = CONTENT_W - 2 - 24        # 1px border each side, 12px padding


def selftest():
    """
    CI entry point. A --windowed build has no console, so a missing hidden
    import does not show up as a traceback -- it shows up as "I double-clicked
    it and nothing happened", on the user's machine, after release. Touch every
    lazily-resolved platform backend here so the build fails in CI instead.
    """
    Controller()                                  # pynput mouse backend
    macos_input_permitted()                       # the guard itself must load
    if macos_input_permitted():
        kb.Listener(on_press=lambda k: False)     # pynput keyboard backend
    Hotkey({"ctrl"}, [_record(kb.KeyCode.from_char("h"))]).label()
    Hotkey(set(), [_record(kb.Key.f6), _record(kb.Key.f7)]).label()
    tk.Tk().destroy()                             # Tcl/Tk actually bundled
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
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
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
            if not (char is None or isinstance(char, str)):
                return None
            if name is None and vk is None and char is None:
                return None
            # Shape is not vocabulary: "bogus" and "" are strings of the right
            # type and would arm a hotkey no key can ever satisfy.
            if name is not None and not hasattr(kb.Key, name):
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
__version__ = "0.3.1"
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
                 "User-Agent": f"AFKFarmClicker/{__version__}"})
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
        headers={"User-Agent": f"AFKFarmClicker/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            sums[parts[1].lstrip("*").strip()] = parts[0].lower()
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

    zipfile and tarfile both happily write "../../.bashrc": the name is used as
    given. Publishing digests and then unpacking unsafely would leave open the
    hole the digests were meant to close.
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
    workdir = tempfile.mkdtemp(prefix="afkclicker-update-")
    archive = os.path.join(workdir, asset["name"])
    request = urllib.request.Request(
        asset["browser_download_url"],
        headers={"User-Agent": f"AFKFarmClicker/{__version__}"})
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
        # asset name ("AFK-Farm-Clicker-linux-x86_64.tar.gz") is long
        # enough on its own to push "not listed in SHA256SUMS" past that
        # budget if it leads the message instead of trailing it.
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


def write_swap_script(staged, target, relaunch):
    """
    A tiny script that waits for this process to exit, replaces the install
    directory and starts the new build. It has to be an external process: a
    program cannot overwrite its own running executable on Windows, and on any
    platform deleting the code you are executing is asking for trouble.
    """
    pid = os.getpid()
    # Two levels up from the staged tree is the temp working directory that
    # download_and_stage created. Guard it: with a shallow `staged` this walks
    # up to "/" and the script would be written to the filesystem root.
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(staged)))
    if not workdir or os.path.dirname(workdir) == workdir or not os.access(workdir, os.W_OK):
        workdir = tempfile.mkdtemp(prefix="afkclicker-update-")
    if sys.platform == "win32":
        path = os.path.join(workdir, "apply-update.cmd")
        script = f'''@echo off
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
robocopy "{staged}" "{target}" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul
start "" "{relaunch}"
'''
    else:
        path = os.path.join(workdir, "apply-update.sh")
        script = f'''#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 1; done
rm -rf "{target}."*  2>/dev/null
find "{target}" -mindepth 1 -delete 2>/dev/null
cp -a "{staged}/." "{target}/"
"{relaunch}" &
'''
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    if sys.platform != "win32":
        os.chmod(path, 0o755)
    return path


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
        self.data = {"games": {}, "hotkey": None, "selected": None}
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.data})
        except (OSError, ValueError):
            pass                      # missing or damaged -> start from defaults

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)     # atomic: never leave a half-written file
        except OSError:
            pass                           # read-only home is not worth crashing over

    def game(self, game_id):
        return self.data["games"].setdefault(game_id, {})

    def put_game(self, game_id, values):
        self.data["games"][game_id] = values
        self.save()


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
        "note": "510 ms is Rays Works' figure — faster breaks the sword sweep.",
        "defaults": {"click_ms": 510, "jitter_ms": 0, "autostop_min": 0,
                     "button": "left", "eat_mode": "pause",
                     "eat_every": 75, "eat_hold": 2.0},
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
    },
]
GENERIC_DEFAULTS = dict(PROFILES[-1]["defaults"])


def make_profile(game_id, name, title_fragment):
    """A game the user added from whatever window was in front."""
    return {"id": game_id, "name": name, "titles": (title_fragment.lower(),),
            "eating": False, "note": "Added from the active window.",
            "defaults": dict(GENERIC_DEFAULTS), "custom": True}




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

    def set_text(self, text):
        self.itemconfig(self.label, text=text)


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
        self.dot = self.create_oval(20 * s, h / 2 - 4.5 * s, 29 * s, h / 2 + 4.5 * s,
                                    fill=BAD, outline="")
        self.text = self.create_text(42 * s, h / 2, anchor="w", text="OFF", fill=INK,
                                     font=("Segoe UI", int(11.5 * s), "bold"))
        self.hint = self.create_text(w - 20 * s, h / 2, anchor="e", text="", fill=MUTED,
                                     font=("Segoe UI", int(8.5 * s)))

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


def section(parent, text, s, top=14):
    label = tk.Label(parent, text=text.upper(), bg=BG, fg=MUTED, anchor="w",
                     font=("Segoe UI", int(8 * s), "bold"))
    label.pack(fill="x", pady=(int(top * s), int(6 * s)))
    return label


def card(parent, s):
    f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    f.pack(fill="x")
    inner = tk.Frame(f, bg=CARD)
    inner.pack(fill="x", padx=int(12 * s), pady=int(10 * s))
    return inner


class GameItem(tk.Canvas):
    """One row in the sidebar: a state dot, the name, and a hover/selected fill."""

    def __init__(self, parent, profile, on_click, s, width=SIDEBAR_W - 16, height=38):
        super().__init__(parent, bg=BG, highlightthickness=0, cursor="hand2",
                         width=int(width * s), height=int(height * s))
        self.profile = profile
        self.on_click = on_click
        self.selected = False
        self.running = False
        w, h = int(width * s), int(height * s)
        self.shape = round_rect(self, 1, 1, w - 1, h - 1, 8 * s, fill=BG, outline="")
        self.dot = self.create_oval(12 * s, h / 2 - 3.5 * s, 19 * s, h / 2 + 3.5 * s,
                                    fill=LINE, outline="")
        self.text = self.create_text(30 * s, h / 2, anchor="w", text=profile["name"],
                                     fill=MUTED, font=("Segoe UI", int(9.5 * s)))
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


class Row(tk.Frame):
    """Label on the left, control on the right -- the NVIDIA settings-table look."""

    def __init__(self, parent, label, s, hint=None):
        super().__init__(parent, bg=CARD)
        text = tk.Frame(self, bg=CARD)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=label, bg=CARD, fg=INK, anchor="w",
                 font=("Segoe UI", int(9.5 * s))).pack(fill="x")
        if hint:
            tk.Label(text, text=hint, bg=CARD, fg=MUTED, anchor="w",
                     font=("Segoe UI", int(8 * s))).pack(fill="x")
        self.control = tk.Frame(self, bg=CARD)
        self.control.pack(side="right")


class NumBox(tk.Frame):
    """A right-aligned number with its unit, sized to sit in a Row."""

    def __init__(self, parent, default, unit, s, width=6):
        super().__init__(parent, bg=CARD)
        tk.Label(self, text=unit, bg=CARD, fg=MUTED, width=4, anchor="w",
                 font=("Segoe UI", int(9 * s))).pack(side="right")
        self.var = tk.StringVar(value=str(default))
        wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        wrap.pack(side="right", padx=(0, int(8 * s)))
        entry = tk.Entry(wrap, textvariable=self.var, width=width, bg=BG, fg=INK,
                         relief="flat", insertbackground=ACCENT, justify="right",
                         font=("Consolas", int(10 * s)), highlightthickness=0)
        entry.pack(ipady=int(4 * s), ipadx=int(5 * s))
        entry.bind("<FocusIn>", lambda e: wrap.config(bg=ACCENT))
        entry.bind("<FocusOut>", lambda e: wrap.config(bg=LINE))


class AfkAutoclicker:
    def __init__(self, root, store=None):
        self.root = root
        self.s = s = root.tk.call("tk", "scaling") / 1.333  # 1.0 at 96 dpi
        self.store = store if store is not None else Store()

        root.title("AFK Farm Clicker")
        root.config(bg=BG)
        root.resizable(False, False)
        # Both panes turn off geometry propagation to hold their widths, which
        # means nothing is left to tell the window how tall to be -- without an
        # explicit size the body collapses to zero height and only the header
        # shows.
        root.geometry(f"{int((SIDEBAR_W + 1 + CONTENT_W) * s)}x{int(690 * s)}")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.mouse = Controller()
        self.hotkey = None
        self.registered_hotkey = None
        self.hk_listener = None
        self.running = False
        self.worker = None
        self.capture_thread = None
        self.right_held = False
        self.settings = {}
        self._pending = None
        self._ui_queue = queue.SimpleQueue()
        self._loading = False          # suppress saves while filling the form

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

        # ── header ──
        header = tk.Frame(root, bg=CARD, height=int(52 * s))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="AFK Farm Clicker", bg=CARD, fg=INK,
                 font=("Segoe UI", int(12 * s), "bold")).pack(side="left",
                                                              padx=int(16 * s))
        self.status = StatusPill(header, s, width=250, height=36)
        self.status.config(bg=CARD)
        self.status.pack(side="right", padx=int(14 * s))

        shell = tk.Frame(root, bg=BG)
        shell.pack(fill="both", expand=True)

        # ── sidebar ──
        side = tk.Frame(shell, bg=BG, width=int(SIDEBAR_W * s))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self.count_label = tk.Label(side, text="GAMES", bg=BG, fg=MUTED, anchor="w",
                                    font=("Segoe UI", int(8 * s), "bold"))
        self.count_label.pack(fill="x", padx=int(14 * s), pady=(int(14 * s), int(6 * s)))
        self.list_frame = tk.Frame(side, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=int(8 * s))
        self.items = {}
        self._rebuild_list()
        Button(side, "Add current game", self.add_current_game, s,
               width=SIDEBAR_W - 28).pack(pady=(int(12 * s), int(4 * s)))
        self.update_button = Button(side, "Check for updates", self.check_update, s,
                                    width=SIDEBAR_W - 28)
        self.update_button.pack(pady=(0, int(6 * s)))
        self.version_label = tk.Label(side, text=f"v{__version__}", bg=BG, fg=MUTED,
                                      font=("Segoe UI", int(8 * s)))
        self.version_label.pack(pady=(0, int(10 * s)))

        tk.Frame(shell, bg=LINE, width=1).pack(side="left", fill="y")

        # ── content ──
        self.content = tk.Frame(shell, bg=BG, width=int(CONTENT_W * s))
        self.content.pack(side="left", fill="both", expand=True)
        self.content.pack_propagate(False)
        self._build_content(s)

        saved = Hotkey.from_json(self.store.data.get("hotkey") or {})
        if saved is not None:
            self.hotkey = saved
            self.apply_hotkey()

        self._select(self.current, persist=False)
        self._timers = []
        self._sync_settings()
        self._drain_ui()
        self._poll_games()

    # ---------- content pane ----------

    def _build_content(self, s):
        pad = int(16 * s)
        body = tk.Frame(self.content, bg=BG)
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        title = tk.Frame(body, bg=BG)
        title.pack(fill="x")
        self.game_title = tk.Label(title, text="", bg=BG, fg=INK, anchor="w",
                                   font=("Segoe UI", int(14 * s), "bold"))
        self.game_title.pack(side="left")
        self.game_state = tk.Label(title, text="", bg=BG, fg=MUTED, anchor="e",
                                   font=("Segoe UI", int(9 * s)))
        self.game_state.pack(side="right")
        self.game_note = tk.Label(body, text="", bg=BG, fg=MUTED, anchor="w",
                                  justify="left", wraplength=int((CONTENT_W - 32) * s),
                                  font=("Segoe UI", int(8.5 * s)))
        self.game_note.pack(fill="x", pady=(int(2 * s), int(12 * s)))

        section(body, "Hotkey  ·  shared by every game", s, top=0)
        hk = card(body, s)
        row = Row(hk, "Toggle", s)
        row.pack(fill="x")
        self.hotkey_label = tk.Label(row.control, text="Not set", bg=CARD, fg=MUTED,
                                     font=("Consolas", int(10 * s)))
        self.hotkey_label.pack(side="right", padx=(0, int(8 * s)))
        btns = tk.Frame(hk, bg=CARD)
        btns.pack(fill="x", pady=(int(8 * s), 0))
        Button(btns, "Record", self.register_hotkey, s, width=124).pack(side="left")
        self.apply_button = Button(btns, "Apply", self.apply_hotkey, s, width=124,
                                   primary=True)
        self.apply_button.pack(side="right")
        self.apply_button.set_enabled(False)

        section(body, "Clicking", s)
        cl = card(body, s)
        r = Row(cl, "Interval", s); r.pack(fill="x")
        self.click_ms = NumBox(r.control, DEFAULT_CLICK_MS, "ms", s)
        self.click_ms.pack()
        r = Row(cl, "Random jitter", s, hint="spreads the rhythm so it is not exact")
        r.pack(fill="x", pady=(int(6 * s), 0))
        self.jitter_ms = NumBox(r.control, 0, "±ms", s); self.jitter_ms.pack()
        r = Row(cl, "Auto-stop", s, hint="0 means never"); r.pack(fill="x", pady=(int(6 * s), 0))
        self.autostop_min = NumBox(r.control, 0, "min", s); self.autostop_min.pack()
        r = Row(cl, "Mouse button", s); r.pack(fill="x", pady=(int(8 * s), 0))
        self.button_name = tk.StringVar(value="left")
        Segmented(r.control, [("left", "Left"), ("right", "Right"), ("middle", "Mid")],
                  self.button_name, s, width=180).pack()

        self.eat_section = section(body, "Eating", s)
        self.eat_card_inner = card(body, s)
        self.eat_card = self.eat_card_inner.master
        self.eat_mode = tk.StringVar(value="off")
        Segmented(self.eat_card_inner,
                  [("pause", "Pause & eat"), ("hold", "Hold RMB"), ("off", "Off")],
                  self.eat_mode, s).pack(pady=(0, int(8 * s)))
        r = Row(self.eat_card_inner, "Eat every", s); r.pack(fill="x")
        self.eat_every = NumBox(r.control, DEFAULT_EAT_EVERY_S, "s", s); self.eat_every.pack()
        r = Row(self.eat_card_inner, "Hold for", s); r.pack(fill="x", pady=(int(6 * s), 0))
        self.eat_hold = NumBox(r.control, DEFAULT_EAT_HOLD_S, "s", s); self.eat_hold.pack()

        # Any edit belongs to the selected game, so persist as it happens.
        for var in (self.click_ms.var, self.jitter_ms.var, self.autostop_min.var,
                    self.button_name, self.eat_mode, self.eat_every.var,
                    self.eat_hold.var):
            var.trace_add("write", lambda *_a: self._persist())

    # ---------- game list ----------

    def _rebuild_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.items = {}
        for profile in self.profiles:
            item = GameItem(self.list_frame, profile, self._select, self.s)
            item.pack(fill="x", pady=int(1 * self.s))
            self.items[profile["id"]] = item
        self.count_label.config(text=f"GAMES   {len(self.profiles)}")

    def _select(self, game_id, persist=True):
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
        if profile["eating"]:
            self.eat_section.pack(fill="x", pady=(int(14 * self.s), int(6 * self.s)))
            self.eat_card.pack(fill="x")
        else:
            self.eat_section.pack_forget()
            self.eat_card.pack_forget()

        if persist:
            self.store.data["selected"] = game_id
            self.store.save()
        self._persist()

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
        if profile.get("custom"):
            values["_profile"] = {"id": profile["id"], "name": profile["name"],
                                  "title": profile["titles"][0]}
        self.store.put_game(self.current, values)

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
        self._set_update_state("Checking…", enabled=False)
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            release = latest_release()
        except NoReleases:
            self._ui(self._set_update_state, "No releases published yet", True)
            return
        if release is None:
            self._ui(self._set_update_state, "GitHub unreachable", True, BAD)
            return
        tag = release.get("tag_name", "")
        if not is_newer(tag):
            self._ui(self._set_update_state, f"Up to date · {__version__}", True)
            return
        asset = pick_asset(release)
        if asset is None:
            self._ui(self._set_update_state, f"{tag}: no build for this OS", True, BAD)
            return
        self._pending = (tag, asset, release)
        self._ui(self._offer_update, tag)

    def _offer_update(self, tag):
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
            script = write_swap_script(staged, target, sys.executable)
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
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", script],
                             creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
        else:
            subprocess.Popen(["/bin/sh", script], start_new_session=True)
        self.on_close()

    def _set_update_state(self, text, enabled=True, colour=None):
        self.update_button.set_text(text)
        self.update_button.set_enabled(enabled)
        if colour:
            self.version_label.config(text=text, fg=colour)

    def _poll_games(self):
        def scan():
            self._ui(self._mark_running, detect_running(self.profiles))
        threading.Thread(target=scan, daemon=True).start()
        self._timers.append(self.root.after(5000, self._poll_games))

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
                return                      # window is going away
        self._timers.append(self.root.after(40, self._drain_ui))

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
        self._timers.append(self.root.after(200, self._sync_settings))

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
            # Starting the listener here would trap, not raise. Show the label
            # and keep the recorded combination so applying it again after the
            # permission is granted just works.
            self.registered_hotkey = self.hotkey
            self.hotkey_label.config(text=self.hotkey.label(), fg=INK)
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
        self.store.save()
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
        self._ui(self.status.set, "RUNNING", OK,
                 self.registered_hotkey.label() if self.registered_hotkey else "")
        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self._ui(self.status.set, "OFF", BAD,
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
                    self._ui(self.status.set, "STOPPED", MUTED, f"auto-stop after {limit:g} min")
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
                        self._ui(self.status.set, "EATING", ACCENT, "clicks paused")
                        hold = cfg.get("eat_hold", DEFAULT_EAT_HOLD_S)
                        self.mouse.press(MouseButton.right)
                        self.right_held = True
                        self._sleep(hold)          # no left-clicks here, or the eat cancels
                        self._release_right()
                        last_meal = time.monotonic()
                        if not self.running:
                            break
                        self._ui(self.status.set, "RUNNING", OK,
                 self.registered_hotkey.label() if self.registered_hotkey else "")

                self.mouse.click(button)
                if not self._sleep(interval):
                    break
        except Exception as exc:
            # Without this the flag stays set: the window keeps saying RUNNING,
            # the hotkey thinks it is already on and toggling does nothing,
            # and no click has happened since the throw.
            self._ui(self.status.set, "ERROR", BAD, str(exc)[:32])
            self.running = False
        finally:
            self.running = False
            self._release_right()

    def on_close(self):
        self._persist()
        # Pending after() callbacks fire into a destroyed interpreter and Tcl
        # reports them as "invalid command name". Cancel them first.
        for job in getattr(self, "_timers", []):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._timers = []
        self.stop()
        if self.hk_listener is not None:
            self.hk_listener.stop()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)   # let it run its own release first
        self._release_right()          # never leave a mouse button stuck down
        self.root.destroy()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    enable_dpi_awareness()
    root = tk.Tk()
    # Segoe UI is the Windows system face; falling back keeps Linux usable.
    if "Segoe UI" not in tkfont.families():
        root.option_add("*Font", "TkDefaultFont")
    AfkAutoclicker(root)
    root.mainloop()

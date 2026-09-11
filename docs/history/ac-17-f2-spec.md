# Spec: OS light/dark detection (story #17, Feature 2)

## Summary
At startup, detect the OS's light/dark preference on Windows/macOS/Linux and
activate `THEMES["light"]` or `THEMES["dark"]` (Feature 1, `afk_clicker.py:65-78`)
before any widget is built, fail-safe to Dark on any platform where detection
is unavailable or ambiguous — no polling, no manual override, no persistence.

## Goals
- A pure function `detect_os_theme()` that returns `"dark"` or `"light"`,
  covering Windows (`winreg`), macOS (`defaults`), and Linux (`gsettings`),
  and never raises.
- A small activation function that points the module's palette globals
  (`BG`, `CARD`, `ACCENT`, …) at the chosen `THEMES` entry, called exactly
  once, before `AfkAutoclicker.__init__` builds its first widget.
- Every platform branch, and every documented failure mode, independently
  testable on Linux CI by swapping out three seams — no `unittest.mock`.

## Non-goals
- Manual System/Light/Dark override UI or `settings.json["theme"]` (Feature 3).
- Runtime re-detection / polling the OS for a live flip (story.md Decision:
  the existing 5 s X11 walk is already flagged as a battery cost in
  `ROADMAP.md`; this feature does not add a second one).
- A native OS change-notification listener (noted in story.md as a possible
  future `ROADMAP.md` item, not built here).
- Any change to `THEMES`'s values or Feature 1's shapes (`PILL_R`, `CARD_R`,
  widget geometry).
- Linux desktop-portal (`org.freedesktop.appearance`) or KDE
  (`kreadconfig5`/`6`, `kdeglobals`) detection. story.md's cross-cutting
  Decision already scoped Linux detection to GNOME's `gsettings` keys "no new
  dependency, consistent with `TECHSTACK.md`'s X11/GNOME framing" — and
  `TECHSTACK.md` already states the hotkey feature itself needs X11 and does
  not work on Wayland at all. A KDE/Wayland-portal user is already outside
  this project's supported Linux surface for the feature that matters most
  (the hotkey); building extra detection reach for a desktop this app barely
  functions on is scope this story explicitly rejected, not an oversight.
- No new third-party dependency (`docs/TECHSTACK.md`) — `winreg` and
  `subprocess` are stdlib; `defaults`/`gsettings` are external binaries
  invoked the same way `osascript` already is in `_window_titles()`.

## Background / current state
`afk_clicker.py:65-78` (Feature 1, committed `41f2a67`):
```python
THEMES = {"dark": _theme(...), "light": _theme(...)}
_ACTIVE = THEMES["dark"]      # feature 1 ships dark-only; #17 features 2-3 pick this
BG, CARD, CARD_HI, LINE, INK, MUTED = (_ACTIVE["BG"], ...)
ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD = (_ACTIVE["ACCENT"], ...)
```
Every widget constructor reads these eleven names as bare module globals at
*call* time (`bg=BG`, `fill=CARD`, `fill=INK if ... else MUTED`, confirmed by
grep — none of them are baked in as function-default-parameter values, which
would freeze them at class-definition/import time instead). The one
close call, `Segmented.__init__(self, parent, options, variable, s,
width=CARD_INNER_W, height=34)` at `afk_clicker.py:1012`, defaults a *size*
constant, not a color, so it's unaffected either way.

This matters because Python resolves a bare name inside a function body
against the module's global namespace at the moment the function *runs*, not
at the moment it was *defined*. So reassigning the eleven globals any time
before `AfkAutoclicker(root)` is constructed is sufficient — no widget code
needs to change, and no per-widget theme reference needs to be threaded onto
`self`.

`_window_titles()` (`afk_clicker.py:844-899`) is the existing precedent for
per-platform branching in this file: a `win32` branch using lazily-imported
`ctypes`, a `darwin` branch shelling out via `subprocess.run(..., timeout=5)`,
and an X11 branch. `macos_input_permitted()` (`afk_clicker.py:167-198`) is the
existing precedent for "this predicate must never crash the app; an
unanswerable question resolves to the safer of the two wrong answers" — same
shape of decision this feature makes, just Dark instead of False.

Tests (`tests/context.py`, `tests/test_hotkey.py:290-316`,
`tests/test_ui.py:747-773`) fake platform-dependent behaviour by directly
overwriting a module attribute on the imported `afk_clicker` module
(`app.sys.platform = "darwin"`, `app.macos_input_permitted = lambda: False`),
always restored in a `finally`. No `unittest.mock` anywhere in the suite.
CI (`.github/workflows/ci.yml`) runs the full `unittest` suite as a required
matrix leg on `ubuntu-latest` (under `xvfb-run`), `windows-latest`, and
`macos-latest` — not just a Linux leg with a separate build-only smoke test
on the other two.

## Proposed approach

### 1. `detect_os_theme()` — pure detection, beside `_window_titles()`/`detect_running()`

Add near `_window_titles()`/`detect_running()` (`afk_clicker.py:844-910`), per
story.md's own scope note:

```python
_THEME_DETECT_TIMEOUT = 2   # generous for a local registry/gsettings/defaults
                             # call, short enough to never visibly stall the
                             # first frame -- shorter than _window_titles's 5s
                             # because that's a background poll, this blocks
                             # startup once.

def _run_theme_command(args):
    """The command-runner seam: real subprocess in production, swapped out
    wholesale in tests so no real `defaults`/`gsettings` call happens on a
    machine that may not have one. Never shell=True -- args is always a list."""
    return subprocess.run(args, capture_output=True, text=True,
                           timeout=_THEME_DETECT_TIMEOUT, check=True)


def _read_windows_theme_registry():
    """The registry-reader seam. winreg only exists on Windows, so the import
    stays lazy and inside this one function -- same reason ctypes.windll is
    imported inside _window_titles's win32 branch, not at module level."""
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
    fallback for older GNOME, per story.md's Decision. A 'default'/
    unrecognized/failed color-scheme falls through to gtk-theme rather than
    going straight to Dark -- 'default' means "no explicit preference
    stated", not "detection failed", and giving up there would make Light
    mode unreachable for most non-bleeding-edge GNOME desktops, defeating the
    whole point of the fallback story.md already named."""
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
                             # output" case story.md's Decision names -- fail
                             # safe, don't guess.
        return "dark" if "dark" in name else "light"
    except Exception:
        return "dark"   # chain ends here; story.md names exactly these two
                         # gsettings keys and no further fallback.


def detect_os_theme():
    """
    Which THEMES key best matches the OS's own light/dark setting, checked
    once at startup (story.md Decision: no runtime polling -- ROADMAP.md
    already flags the existing 5s X11 walk as a battery cost, and this is a
    purely cosmetic follow that doesn't need to be live). Never raises: any
    exception, a missing binary/registry value, a timeout, or output that
    doesn't parse all resolve to "dark", because that's what the app already
    ships today -- an undetectable OS is the least-surprising possible
    regression, never a broken or half-themed window.
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
```

**macOS + the unsigned `.app`:** `_window_titles()`'s `darwin` branch already
shells out to `osascript` — a far more sensitive call, since driving "System
Events" requires the user to grant Automation permission the first time.
`defaults read -g` reads an unprotected preference domain via `CFPreferences`
and needs no permission prompt at all. Since the existing, more-sensitive
subprocess call already works from this unsigned, PyInstaller-frozen `.app`
in production, `defaults` — strictly less privileged — works too. This is
precedent, not a new assumption.

### 2. Wiring the result in before any widget exists

Add, directly below the existing palette-derivation block
(`afk_clicker.py:65-78`):

```python
def set_active_theme(name):
    """Point the module's palette globals at THEMES[name]. Every widget in
    this file reads BG/CARD/... as bare module globals at construction time
    (not as function-default values, see docs/spec.md background), so
    reassigning them here before any widget is built is sufficient -- no
    widget code changes, no theme reference threaded onto self anywhere.
    Feature 3 reuses this unchanged for its System/Light/Dark override,
    followed by its own widget-tree rebuild."""
    global _ACTIVE, BG, CARD, CARD_HI, LINE, INK, MUTED
    global ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD
    _ACTIVE = THEMES[name]
    BG, CARD, CARD_HI, LINE, INK, MUTED = (
        _ACTIVE["BG"], _ACTIVE["CARD"], _ACTIVE["CARD_HI"], _ACTIVE["LINE"],
        _ACTIVE["INK"], _ACTIVE["MUTED"])
    ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD = (
        _ACTIVE["ACCENT"], _ACTIVE["ACCENT_INK"], _ACTIVE["ACCENT_HI"],
        _ACTIVE["OK"], _ACTIVE["BAD"])
```

And call it in `__main__` (`afk_clicker.py:1826-1833`), before
`AfkAutoclicker(root)` is constructed:

```python
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    enable_dpi_awareness()
    set_active_theme(detect_os_theme())     # new
    root = tk.Tk()
    ...
    AfkAutoclicker(root)
```

**Why `__main__`, not `AfkAutoclicker.__init__`:** every test in
`tests/test_ui.py` constructs `AfkAutoclicker(root, store=...)` directly,
bypassing `__main__` entirely. If detection ran inside `__init__`, every one
of those ~dozen call sites would trigger a real subprocess/registry read on
every test run, on whatever machine CI happens to be — slow, and a source of
flakiness unrelated to what each test is actually checking. Running it only
in `__main__` means:
- Importing the module (what every test file does) never shells out or
  touches the registry — satisfies "no import-time subprocess" directly.
- `AfkAutoclicker.__init__` itself needs zero changes for this feature.
- Feature 2's own acceptance criterion ("given `THEMES["light"]` is active,
  when any widget is constructed, its colors come from `THEMES["light"]`")
  is directly testable as `app.set_active_theme("light")` followed by
  constructing an `AfkAutoclicker`, with no OS dependency at all.

**`selftest()` (`afk_clicker.py:108-...`):** add a call to `detect_os_theme()`
there too, alongside the existing `macos_input_permitted()` call. It's the
one place the *frozen* PyInstaller binary/`.app` gets exercised in CI
(`.github/workflows/release.yml:150,157,161`) — this is the only way this
story ever proves the unsigned-`.app`-can-call-`defaults` argument above
against a real frozen bundle rather than an unfrozen interpreter. Safe to add
unconditionally: `detect_os_theme()` never raises by construction, so it
cannot turn a passing selftest into a failing one.

## Affected areas
- `afk_clicker.py` only: `set_active_theme()` (new, ~10 lines, beside
  `THEMES`/`_ACTIVE`), `detect_os_theme()` + `_run_theme_command()` +
  `_read_windows_theme_registry()` + `_detect_linux_theme()` +
  `_THEME_DETECT_TIMEOUT` (new, beside `_window_titles()`/`detect_running()`),
  one new call in `selftest()`, one new call in `__main__`. No other file
  changes — one architectural layer, no split needed (skill 11 doesn't apply).
- No data model / schema change — nothing persisted this feature.
- No public interface change beyond the two new module-level functions.

## Edge cases
- **Windows, key present but value neither 0 nor 1** (garbage/future value):
  falls to the `else` branch → dark, not a crash.
- **Windows, key or value missing** (older Windows, or a machine that's never
  had Settings > Personalization opened): `winreg.OpenKey`/`QueryValueEx`
  raises `FileNotFoundError` → outer catch → dark.
- **Windows, unexpected `winreg`/`OSError`/`PermissionError`**: outer catch →
  dark, startup does not raise.
- **macOS, `defaults` missing** (shouldn't happen — it's a system tool — but
  the code must not assume): `FileNotFoundError` from `subprocess.run` →
  not a `CalledProcessError` → outer catch → dark.
- **macOS, call times out**: `subprocess.TimeoutExpired` → outer catch → dark.
- **macOS, key absent (light mode)**: `CalledProcessError` → light, by design
  — the one case where a "failure" is actually a successful detection.
- **Linux, `gsettings` entirely missing** (minimal/non-GNOME install): both
  calls raise → dark.
- **Linux, schema/key present but unrecognized value, or empty output**:
  falls through the chain as designed → dark or light per the table above,
  never a crash.
- **Linux, `gsettings` present but no `DISPLAY`/dbus session** (some CI/
  headless boxes): typically a nonzero exit or stderr-only output → caught,
  falls through the same chain.
- **Concurrent operations**: none — detection is one synchronous call before
  any thread exists (`self.worker`/`self.hk_listener` are created later, only
  once the user interacts), so there's no race to consider.
- **Permission boundaries**: none of the three calls need elevated rights;
  `defaults` in particular needs no TCC/Accessibility grant, unlike
  `macos_input_permitted()`'s concern.
- **Platform not one of the three recognized branches** (e.g. `sys.platform`
  faked to something else in a test, or a future BSD/etc. port): none of the
  three `if` branches match, the function falls out of the `try` and returns
  the default `"dark"` — no `else`/`NotImplementedError`, matching the
  fail-safe philosophy rather than crashing on an unrecognized platform.

## Testability (the three injectable seams)

No `unittest.mock`, following `tests/test_hotkey.py:290-316` and
`tests/test_ui.py:747-773`'s existing style: overwrite a module attribute on
`afk_clicker` directly, restore it in a `finally`.

1. **`app.sys.platform`** — already the established seam (`test_hotkey.py:311`).
2. **`app._run_theme_command`** — replace with a function/lambda returning a
   fake object with a `.stdout` attribute (for success), or a function that
   `raise`s the specific exception a test wants to simulate
   (`subprocess.CalledProcessError`, `FileNotFoundError`,
   `subprocess.TimeoutExpired`, or a generic `Exception` for "garbage"/
   unexpected failures). Covers both the macOS and the Linux branches — same
   seam, different platform under test.
3. **`app._read_windows_theme_registry`** — replace with a function returning
   `0`, `1`, some other int (garbage-value case), or one that raises
   (`FileNotFoundError` for "key/value missing", any other `Exception` for
   "unexpected `winreg` failure"). Windows-only branch, never exercised for
   real on Linux CI — this seam is exactly why it doesn't need to be.

## Acceptance criteria
- [ ] Given `sys.platform = "win32"` and `_read_windows_theme_registry`
      returns `0`, when `detect_os_theme()` runs, then it returns `"dark"`.
- [ ] Given `sys.platform = "win32"` and `_read_windows_theme_registry`
      returns `1`, then it returns `"light"`.
- [ ] Given `sys.platform = "win32"` and `_read_windows_theme_registry`
      returns `2` (or any value other than `0`/`1`), then it returns `"dark"`.
- [ ] Given `sys.platform = "win32"` and `_read_windows_theme_registry` raises
      `FileNotFoundError` (key/value missing — older Windows), then it
      returns `"dark"` and `detect_os_theme()` does not raise.
- [ ] Given `sys.platform = "win32"` and `_read_windows_theme_registry` raises
      any other exception, then it returns `"dark"` without raising.
- [ ] Given `sys.platform = "darwin"` and `_run_theme_command` returns a
      result whose `.stdout` is `"Dark\n"` (exit 0), then it returns `"dark"`.
- [ ] Given `sys.platform = "darwin"` and `_run_theme_command` raises
      `subprocess.CalledProcessError` (documented "key absent" exit), then it
      returns `"light"`.
- [ ] Given `sys.platform = "darwin"` and `_run_theme_command` raises
      `FileNotFoundError` (`defaults` missing), then it returns `"dark"`.
- [ ] Given `sys.platform = "darwin"` and `_run_theme_command` raises
      `subprocess.TimeoutExpired`, then it returns `"dark"`.
- [ ] Given `sys.platform.startswith("linux")` and the first
      `_run_theme_command` call returns `.stdout = "'prefer-dark'\n"`, then it
      returns `"dark"` (and the gtk-theme fallback is not needed to decide).
- [ ] Given the first call returns `"'prefer-light'\n"`, then it returns
      `"light"`.
- [ ] Given the first call returns `"'default'\n"` and the second
      (`gtk-theme`) call returns `"'Yaru-dark'\n"`, then it returns `"dark"`.
- [ ] Given the first call returns `"'default'\n"` and the second returns
      `"'Adwaita'\n"`, then it returns `"light"`.
- [ ] Given the first call raises (missing `gsettings`/schema/timeout) and the
      second call returns a name containing `"dark"` (case-insensitive), then
      it returns `"dark"`.
- [ ] Given both calls raise, then it returns `"dark"` without raising.
- [ ] Given the first call returns unrecognized/empty output and the second
      call also returns empty output, then it returns `"dark"` (the
      "unparseable output" fail-safe, not a guess).
- [ ] Given `sys.platform` is none of the three recognized values, then
      `detect_os_theme()` returns `"dark"` without raising.
- [ ] Given `set_active_theme("light")` has been called, when an
      `AfkAutoclicker` is constructed, then its widgets' colors come from
      `THEMES["light"]` (e.g. assert `ui.status.itemcget(ui.status.shape,
      "fill")` or equivalent against `app.THEMES["light"]["CARD"]`/`["BG"]`) —
      not `THEMES["dark"]`. Restore `set_active_theme("dark")` in a `finally`
      so later tests in the suite see the pre-existing default.
- [ ] Given no theme call has been made at all (module just imported), when
      an `AfkAutoclicker` is constructed, then its colors are `THEMES["dark"]`
      — today's unchanged default behavior, proving this feature adds a new
      path without disturbing the old one.
- [ ] Given `--selftest` is run (real platform, real `_run_theme_command`/
      `_read_windows_theme_registry`, not swapped), then it completes and
      exits 0 on all three CI platforms — proves `detect_os_theme()` cannot
      itself break a selftest run, on the real frozen build on Windows/macOS
      (`release.yml`) and the real interpreter on Linux (`ci.yml`).

## What CI can and cannot prove (REVIEW-PROTOCOL.md Round 7)

`ci.yml` runs the *unit test* matrix (not just a build smoke test) on real
`windows-latest` and `macos-latest` runners, in addition to `ubuntu-latest`
under `xvfb-run`. That changes what's provable here versus most of this file:

**Provable on CI, for real, no fakes:**
- Windows leg: a real `winreg.OpenKey`/`QueryValueEx` read against that
  runner's actual registry. A test with no monkeypatching at all — gated
  `if sys.platform == "win32"` so it only runs there — can assert
  `detect_os_theme()` returns `"dark"` or `"light"` (whichever the runner's
  image actually has) without raising. This is a real exercise of
  `_read_windows_theme_registry`'s happy path, not just the injected seam.
- macOS leg: same shape, a real `defaults read -g AppleInterfaceStyle` call
  against that runner's actual preference domain — proves the subprocess
  call itself (args, `text=True`, `capture_output=True`, `timeout=2`) is
  well-formed and actually runs under the real interpreter.
- Linux leg: `ubuntu-latest` under `xvfb-run` has no GNOME session and
  typically no `org.gnome.desktop.interface` schema registered at all, so a
  real (non-monkeypatched) `detect_os_theme()` call there is a genuine,
  unforced exercise of the fail-safe path — expect (and can assert) `"dark"`.
  Flag this assumption in a comment on that test: if a future Ubuntu runner
  image ships GNOME defaults, this specific assertion could start failing for
  a reason unrelated to a real bug, and should be loosened to "doesn't raise,
  returns a valid THEMES key" rather than removed outright.
- `release.yml`'s `--selftest` step against the *frozen* `.app`/`.exe` on
  Windows and macOS is the only place this story's "can an unsigned,
  PyInstaller-frozen app shell out to `defaults`" claim gets checked against
  a real frozen bundle, not an unfrozen interpreter.

**Not provable on CI, stated plainly per Round 7's own instruction:**
- Whether detection matches a *specific* OS light/dark setting a human
  actually chose — CI runners' registry/defaults/gsettings state is whatever
  each image ships, not something this PR controls or should assert an exact
  value against beyond "valid, doesn't raise."
- Flipping the OS setting mid-session and re-launching — inherently a manual
  check, and out of scope anyway (no polling, story.md Decision).
- Gatekeeper/notarization-specific subprocess restrictions on a real user's
  Mac that a CI-provisioned `macos-latest` runner doesn't reproduce (the
  existing `ROADMAP.md` line "macOS verification... never run by a human"
  already names this gap; this feature doesn't close it, only doesn't make
  it worse — `defaults` is exercised the same way `osascript` already is).
- KDE/Wayland-portal desktops — out of scope per Non-goals above, so there's
  nothing to prove either way.

## Open questions
None that need a human decision before implementation — story.md already
settled the cross-cutting decisions (once-at-startup, fail-safe-to-dark, the
exact commands per platform), and every remaining choice above (the Linux
`"default"`/unrecognized-value fallthrough table, the `_THEME_DETECT_TIMEOUT`
value, calling `detect_os_theme()` from `selftest()`, and where
`set_active_theme()` gets called from) is a refinement of story.md's own
"draft, refined in Feature 2's own spec" acceptance criteria, made here with
its reasoning shown rather than left for the developer to re-decide.

One assumption worth surfacing rather than silently picking: story.md's own
draft acceptance criteria literally read "any other clean value... selects
the documented fail-safe [Dark]" for the Linux `color-scheme` case, which
taken at face value would mean an explicit `prefer-light` read (or `default`
on a machine that's visibly light) never actually shows the user Quartz. I'm
treating that as a drafting shorthand, not a deliberate decision — the
alternative reading makes the entire Linux leg of this feature a no-op for
any user not on the newest GNOME, which can't be the intent of a feature
whose whole point is showing Quartz on a light desktop. Proceeding under the
refined 3-way table above; flagging here in case the literal draft wording
was actually intentional and I'm misreading it.

## Risk / rollback notes
- Additive only: `set_active_theme("dark")` is never called anywhere in this
  feature (dark stays the import-time default exactly as Feature 1 left it),
  so the only new runtime behavior is the single `set_active_theme(detect_os_
  theme())` call in `__main__`. Reverting is deleting that one line plus the
  new functions — no data migration, nothing persisted, nothing else in the
  file references them yet.
- Worst realistic failure mode: `detect_os_theme()` has a bug and always
  returns `"dark"` regardless of the real OS setting — behaviorally
  indistinguishable from today, i.e. the failure mode of a bug here is "looks
  exactly like before this shipped," not a crash or a half-themed window.
- The one behavior change with any risk is the `selftest()` addition — if
  `detect_os_theme()` ever *did* raise (it shouldn't, by construction, but if
  a future edit broke that), it would turn a currently-green `--selftest`
  red on all three release runners. Cheap to catch: any test in the "no
  human decision" acceptance list above that calls `detect_os_theme()`
  without try/except and asserts no exception propagates.

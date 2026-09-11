# Implementation: OS light/dark detection (Story #17, Feature 2)

## Summary
Added a pure `detect_os_theme()` (plus its three injectable seams and
`_THEME_DETECT_TIMEOUT`) beside `_window_titles()`/`detect_running()`, and a
`set_active_theme(name)` activation function beside `THEMES`/`_ACTIVE`. Wired
one `set_active_theme(detect_os_theme())` call into `__main__` before
`tk.Tk()`/`AfkAutoclicker(root)` are built, and one `detect_os_theme()` call
into `selftest()`. `AfkAutoclicker.__init__` and every existing widget
constructor are unchanged — no widget reads a theme value any differently
than it already did; only the module globals it reads now get pointed at a
different `THEMES` entry before construction, exactly per `docs/spec.md`'s
"Proposed approach". No UI/behavioral change beyond that one new startup
call — this feature is otherwise inert until Feature 3 or `set_active_theme`
is called directly.

## Root cause
N/A — this is a feature build, not a bugfix.

## Changes by file
- `afk_clicker.py`
  - `_lighten(hex6, factor)` (`~49-66`): hardened per the hard requirement
    from PR #28's review (Feature 3 gives this a second caller). `factor` is
    now clamped to `[0, 1]` rather than trusted — an out-of-range factor
    (`2.0`) used to walk `r`/`g`/`b` past 255 and produce a malformed
    9-character string (`"#17e17e17e"`) instead of a real color. `hex6` is
    now validated as `#rrggbb` and raises `ValueError` otherwise, rather than
    being coerced. The one existing caller (`_theme()`'s
    `_lighten(accent, 0.18)`) is unaffected — always a valid hex, in range.
  - `set_active_theme(name)` (new, directly below the `THEMES`/`_ACTIVE`
    block, before `PILL_R`): reassigns the same eleven module globals
    `_ACTIVE`/`BG`/`CARD`/`CARD_HI`/`LINE`/`INK`/`MUTED`/`ACCENT`/
    `ACCENT_INK`/`ACCENT_HI`/`OK`/`BAD` from `THEMES[name]`, matching how
    lines 72-78 derive them from `_ACTIVE` at import time. Raises
    `ValueError` for an unrecognized `name` (see "Key decisions" below for
    why, over silently falling back to dark).
  - `_THEME_DETECT_TIMEOUT = 2`, `_run_theme_command(args)`,
    `_read_windows_theme_registry()`, `_detect_linux_theme()`,
    `detect_os_theme()` (new, directly above `_window_titles()`): implemented
    verbatim per `docs/spec.md`'s "Proposed approach" code, with one addition
    — `_run_theme_command` passes `errors="replace"` to `subprocess.run`,
    which the spec's own snippet didn't specify (see "Deviations from
    spec").
  - `selftest()`: added `detect_os_theme()` alongside the existing
    `macos_input_permitted()` call, so a broken future edit that made
    detection raise would turn a currently-green `--selftest` red on all
    three `release.yml` runners, per the spec's "Risk / rollback notes".
  - `__main__`: added `set_active_theme(detect_os_theme())` between
    `enable_dpi_awareness()` and `tk.Tk()` — before any widget exists, per
    the spec's "Why `__main__`, not `AfkAutoclicker.__init__`" reasoning
    (every `tests/test_ui.py` call site constructs `AfkAutoclicker` directly
    and would otherwise trigger a real subprocess/registry read on every
    test run).
- `tests/test_ui.py` — additive only, no existing test changed:
  - `Lighten` (existing class) — three new tests: factor `2.0` clamps to
    `"#ffffff"`, factor `-1.0` clamps to the unchanged input, and six
    non-`#rrggbb` inputs (`"purple"`, `"#12345"`, `"#1234567"`, `"123456"`,
    `"#gggggg"`, `""`) each raise `ValueError`.
  - `SetActiveThemeUnknownName` (new) — `set_active_theme("solarized")`
    raises `ValueError`.
  - `SetActiveThemeWidgets` (new) — builds a real `AfkAutoclicker` after
    `set_active_theme("light")` and asserts four sampled widgets
    (`ui.root`'s bg, `ui.eat_card_inner`'s bg, `ui.apply_button`'s shape
    fill once enabled, `ui.click_ms.wrap`'s bg) all read from
    `THEMES["light"]`; a second test rebuilds after `set_active_theme("dark")`
    and asserts the same four read `THEMES["dark"]` again; a third builds
    with no `set_active_theme` call at all and asserts the untouched-default
    is still `THEMES["dark"]`. `tearDown` unconditionally calls
    `set_active_theme("dark")` so no later test in the suite inherits
    Quartz.
  - `DetectOsTheme` (new) — one test per acceptance-criteria bullet in
    `docs/spec.md`: Windows registry values `0`/`1`/`2`/`FileNotFoundError`/
    `PermissionError`/a generic `RuntimeError`; macOS `_run_theme_command`
    returning stdout (dark), raising `CalledProcessError` (light),
    `FileNotFoundError` (dark), `subprocess.TimeoutExpired` (dark), and
    `UnicodeDecodeError` (dark); Linux `prefer-dark`/`prefer-light`
    short-circuiting before the `gtk-theme` fallback runs, `'default'`
    falling through to a `-dark`/non-`-dark` `gtk-theme` name, the first
    call raising and the second naming `dark` case-insensitively, both
    calls raising, both calls returning empty output; and an unrecognized
    `sys.platform` value. Uses the three seams
    (`app.sys.platform`/`app._run_theme_command`/
    `app._read_windows_theme_registry`), monkeypatched and restored in
    `setUp`/`tearDown`, matching `tests/test_hotkey.py:290-316`'s style — no
    `unittest.mock` anywhere in this file.
  - `RunThemeCommandSeam` (new) — two tests against the real,
    non-monkeypatched `_run_theme_command`, invoking `sys.executable`
    itself so they run on every platform without depending on
    `defaults`/`gsettings` being installed: one confirms real stdout
    capture, the other writes an invalid UTF-8 byte to the child's stdout
    and asserts `_run_theme_command` does not raise (per the hard
    requirement to handle a non-UTF-8 byte in subprocess output) and that
    the replacement character appears in the decoded result.

## Key decisions / tradeoffs
- **`set_active_theme` on an unknown name raises `ValueError`, not a
  fallback to dark.** The task's hard requirement offered either option;
  picked `ValueError` because `detect_os_theme()` only ever returns
  `"dark"`/`"light"` by construction, so this branch is unreachable from
  real detection — it can only fire from a caller passing a typo or garbage
  string directly (Feature 3's override UI, or a test), which is a
  programming error that should fail loudly during development rather than
  silently paint a plausible-but-wrong theme. Documented in the function's
  own docstring, not just here.
- **Console-flash / `CREATE_NO_WINDOW` audit (hard requirement 1).** Grepped
  `subprocess`/`creationflags` across the file: the only existing
  `creationflags` use is `afk_clicker.py:1528-1529`'s
  `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on the self-update swap
  script's `Popen` — not `CREATE_NO_WINDOW`, and not directly reusable
  here. It doesn't apply to this feature's subprocess calls anyway:
  `_run_theme_command` is only ever invoked from the `darwin`/`linux`
  branches of `detect_os_theme()` — Windows detection reads the registry
  directly via `_read_windows_theme_registry()`/`winreg`, no subprocess at
  all — so there is no frozen-Windows-GUI console-flash risk for this
  feature's own subprocess call to guard against. Documented inline in
  `_run_theme_command`'s docstring so this reasoning doesn't need
  rediscovering later.
- **Captured-colour audit (hard requirement 2), so `set_active_theme`
  provably reaches everywhere a color was captured:**
  - The eleven module globals (`BG`/`CARD`/`CARD_HI`/`LINE`/`INK`/`MUTED`/
    `ACCENT`/`ACCENT_INK`/`ACCENT_HI`/`OK`/`BAD`) — the only place, per
    `docs/spec.md`'s own background section (confirmed independently by
    grepping every `bg=`/`fill=`/`fg=` call site in the file). `set_active_theme`
    reassigns exactly these.
  - Function-default arguments: grepped every `def __init__`/`def ` in the
    file for a colour-named global used as a default value. Found exactly
    one default that reads a module global at all —
    `Segmented.__init__(..., width=CARD_INNER_W, height=34)` — and
    `CARD_INNER_W` is a *size* constant derived from `CONTENT_W`/`CONTENT_PAD`/
    `CARD_R`, never a colour, so it's unaffected either way (matches the
    spec's own note). No colour default argument exists anywhere.
  - Class attributes: none of `Button`/`Segmented`/`StatusPill`/`GameItem`/
    `Row`/`NumBox`/`AfkAutoclicker` binds a colour as a class-level
    attribute — every colour reference found is inside a method body,
    reading the bare module global at call time (confirmed by grep, same
    conclusion the spec's own background section states).
  - Module-level dicts/tuples: `THEMES` itself is the only module-level
    structure built from colour hexes; it's immutable and indexed by name
    at both `_ACTIVE = THEMES["dark"]` (import time) and inside
    `set_active_theme` (call time) — no other module-level dict/tuple
    captures a `BG`/`CARD`/… value anywhere (`PROFILES`, `ASSET_SUFFIX`,
    `GENERIC_DEFAULTS` etc. hold no colour data).
  - `ACCENT_HI` via `_lighten`: already handled *inside* `THEMES`'s own
    construction — `_theme()` computes `"ACCENT_HI": _lighten(accent, 0.18)`
    once per theme when `THEMES = {"dark": _theme(...), "light": _theme(...)}`
    runs at import time, so `THEMES["light"]["ACCENT_HI"]` is already the
    correct lightened Quartz accent, not the dark one recomputed. This
    predates Feature 2 (Feature 1's own code, `41f2a67`) — `set_active_theme`
    doesn't need to call `_lighten` itself, only to read the value `THEMES`
    already baked in per-theme, which it does via `_ACTIVE["ACCENT_HI"]`
    like every other key.
  - Verified with a real test, not just the audit: `SetActiveThemeWidgets`
    samples the root window's bg, a card shell's bg (`eat_card_inner`), a
    primary button's fill (`apply_button`, enabled first — see next bullet),
    and a `NumBox`'s focus-ring wrap bg (`click_ms.wrap`), across
    light/dark/untouched-default, all four passing.
  - One test-writing wrinkle worth recording: `apply_button` is the only
    `primary=True` button in the app, and `AfkAutoclicker.__init__` calls
    `self.apply_button.set_enabled(False)` immediately after constructing
    it (`afk_clicker.py:1331`) — `Button._colors()` returns `CARD`/`LINE`/
    `MUTED` whenever `_enabled` is `False`, regardless of `primary`. The
    test enables it first (`ui.apply_button.set_enabled(True)`) before
    reading its shape fill, so it's actually sampling the primary-styled
    path the spec asked for, not the disabled-grey path.
- **`_run_theme_command` passes `errors="replace"`** (hard requirement:
  handle a non-UTF-8 byte in subprocess output) instead of relying solely on
  the outer `except Exception: pass` in `detect_os_theme()` to swallow a
  `UnicodeDecodeError`. Both would produce the same final answer ("dark"),
  but `errors="replace"` lets a garbled-but-mostly-valid response (e.g. one
  stray byte in an otherwise-readable `gtk-theme` name) fall through the
  already-tested "unrecognized value" branch instead of being thrown away
  entirely as an opaque exception — a strictly better fail-safe within the
  spec's own stated philosophy, verified with a real (non-monkeypatched)
  subprocess call in `RunThemeCommandSeam`.

## Deviations from spec
- `_run_theme_command` adds `errors="replace"` to the `subprocess.run` call,
  which `docs/spec.md`'s own code sample didn't include — see "Key
  decisions" above. This is a strict robustness addition inside the spec's
  own stated fail-safe philosophy, not a behavior change to any of the
  documented outcomes (every acceptance-criteria case in the spec still
  produces the exact same result).
- `set_active_theme`'s unknown-name behavior (`ValueError`) is not in
  `docs/spec.md`'s own code sample, which used a bare `THEMES[name]` lookup
  (a `KeyError`, not a `ValueError`, on a bad name) — the task's hard
  requirements explicitly asked for one of `ValueError`/fallback-to-dark,
  so this refines the spec's illustrative snippet rather than contradicting
  its actual intent (an unrecognized name was never meant to reach real
  detection either way).
- `_lighten`'s clamp/validate behavior is not in `docs/spec.md` at all — it
  comes from this task's own hard requirement citing the PR #28 review
  concern. Spec's Non-goals list "Any change to `THEMES`'s values or
  Feature 1's shapes" as out of scope; this change touches neither — same
  hex values in, same hex values out for every existing in-range call, only
  the previously-undefined out-of-range/invalid-input behavior changed.

## Known limitations
- `detect_os_theme()`'s Windows and macOS branches are only exercised
  through the injectable seams in this repo's Linux CI leg — genuinely
  untestable here beyond "the seam is called with the right arguments and
  the return value maps correctly," which is what the seam-based tests
  assert. Per `docs/spec.md`'s own "What CI can and cannot prove" section,
  the real `winreg`/`defaults` code paths only get exercised for real on
  `windows-latest`/`macos-latest` CI runners (unfaked, gated on
  `sys.platform`) — no such gated real-platform test was added here since
  this developer session only had a Linux sandbox to verify against; the
  seam coverage is what's locally provable, and the spec already documents
  this gap rather than treating it as an oversight.
- `_run_theme_command`'s `errors="replace"` behavior is verified with a
  synthetic child process (`sys.executable -c "..."` writing raw bytes),
  not a real `defaults`/`gsettings` invocation — chosen specifically so the
  test runs on every platform without depending on either binary being
  installed (this sandbox's Linux box has neither `gsettings` nor macOS's
  `defaults`, confirmed below).

## How to verify locally
From `/home/dev/projects/.worktrees/afk-clicker/ac-17`:

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```

Result: **183 tests, OK, skipped=5** (baseline before this feature was 155
tests, OK, skipped=5 — 28 new tests added, all passing, no existing test
touched or its assertions changed).

Real detection on this sandbox's Linux box (no monkeypatching, no
`--selftest`, just an import-time-safe direct call):

```python
import afk_clicker as app
app.detect_os_theme()   # -> "dark"
```

`shutil.which("gsettings")` returns `None` on this box — no GNOME session,
no `gsettings` binary at all — so both `_run_theme_command` calls inside
`_detect_linux_theme()` raise `FileNotFoundError`, both are caught, and the
chain ends at its documented fail-safe: `"dark"`. This matches
`docs/spec.md`'s own prediction for `ubuntu-latest` under `xvfb-run` ("no
GNOME session and typically no `org.gnome.desktop.interface` schema
registered at all").

To see Quartz rendered (never previously screenshotted — Feature 1 only
verified the hex values, not the pixels):

```python
import os, sys, tempfile, tkinter as tk
sys.path.insert(0, "/home/dev/projects/.worktrees/afk-clicker/ac-17")
import afk_clicker as app

app.set_active_theme("light")

cfg = os.path.join(tempfile.mkdtemp(), "settings.json")
root = tk.Tk()
ui = app.AfkAutoclicker(root, store=app.Store(cfg))
root.update()
ui._select("minecraft", persist=False)
root.update()
```

Screenshot taken this way (Minecraft selected):
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f2-quartz.png`
  — white card shells, light blue-grey window/sidebar background, dark ink
  text — the first real render of `THEMES["light"]`, confirming
  `set_active_theme("light")` reaches the whole widget tree, not just the
  hex values `Themes.test_light_matches_the_quartz_hex_exactly` already
  checked structurally.

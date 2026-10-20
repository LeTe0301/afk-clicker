# Tech stack

The constraints here are not preferences. Each one was paid for once already,
and a change that ignores it will fail in a way that is hard to see from a diff.

## Runtime

| | |
|---|---|
| Language | Python 3.12 (CI builds on 3.12; 3.11 works) |
| Framework / UI | **tkinter only** — stdlib; one source file, `afk_clicker.py` |
| Input | **pynput only** — mouse *and* keyboard |
| Build | PyInstaller, `--onedir`, `--windowed`, `--noupx`, one GitHub Actions runner per platform (`.github/workflows/release.yml`) |
| Data / backend | None of its own. Settings are JSON in the platform config directory (`config_path()`: `%APPDATA%\AFKFarmClicker`, `~/Library/Application Support/AFKFarmClicker`, `$XDG_CONFIG_HOME` or `~/.config` + `/afk-farm-clicker`) |
| HTTP | `urllib.request` from the stdlib — only the in-app updater talks to the network (GitHub releases API) |
| Hosting / deploy target | GitHub Releases on `LeTe0301/afk-clicker`; installed copies update themselves from there |
| Tests | `unittest` in `tests/`; on Linux under an X display (Xvfb) |

## Why no third-party GUI or HTTP library

Every dependency has to be frozen into the binary, and every frozen dependency
is another chance for PyInstaller's static analysis to miss a lazily imported
backend and ship something that dies at launch. The program is a dark window
with about fifteen controls; Qt or a requests dependency buys nothing that
pays for that risk.

## Why pynput and not `keyboard`

`keyboard` supports Windows and Linux only, and needs root on Linux. A macOS
build using it would install cleanly and then never respond to a hotkey.
pynput speaks all three, and the mouse half was already required.

## Why not pynput's GlobalHotKeys

It matches on `Listener.canonical()`, which routes character keys back through
the keyboard layout. Measured with synthesised presses: every named key
matched, and no character key ever did. The project matches the **raw** event
on name, character *or* virtual key code. See `Hotkey` in `afk_clicker.py`.

## Build

PyInstaller freezes the interpreter it runs on, so it **cannot cross-compile**.
Each platform is built on its own runner. Non-negotiables in the build flags:

- **No `--onefile`.** It unpacks to a temp directory on every start: slower,
  and the single biggest antivirus trigger for a program that already hooks the
  keyboard globally.
- **No UPX.** Same reason.
- **`--hidden-import` for every pynput backend.** They are resolved at import
  time and are invisible to static analysis.
- **`--selftest` must run in CI.** A `--windowed` build has no console, so a
  missing import surfaces as "I double-clicked it and nothing happened", on a
  user's machine, after release.
- **`--name "AFK Farm Clicker"` stays**, although the app is called Clickwork:
  every installed copy's swap script relaunches that exact path, so renaming
  the executable breaks auto-update for existing installs
  (`docs/history/ac-33-implementation.md`).

Linux builds on the **oldest** available runner: PyInstaller links the build
host's glibc, so a newer host produces a binary that refuses to start on older
distributions.

macOS archives are packed with `ditto`, not `zip`, or the bundle's symlinks and
permission bits are mangled and Finder refuses to open the app. The smoke test
runs the binary inside the bundle directly rather than `open`ing the app:
`open` returns as soon as it has handed off and tells you nothing about the
exit status.

`fail-fast: false` on the build matrix: a broken macOS runner should still
leave a usable Windows archive behind, and one platform's failure must not
hide the other two.

## Dependencies

A new runtime dependency needs an argument in the PR and a ticket that agreed
to it beforehand — the bar is high for the reason in "Why no third-party GUI or
HTTP library" above.

Every build input is pinned to an exact version — `pynput` (1.7.7),
`pyinstaller` (6.11.1), and the release action, which holds the only write
token in the pipeline. A floating dependency can change what ships without a
single commit here, and for a program whose whole job is synthesising input, a
changed input backend is not a detail. `build.bat` pins the same versions CI
does, so a local build cannot quietly differ from the published one.

## Environment

- **Environment variables** (names only): `AFK_SLOW_TESTS=1` adds the slow
  synthetic-key-press sweep (`tests/test_chords_slow.py`); `CI` makes a
  headless Linux run fail instead of skipping everything (`tests/context.py`);
  `PYTHONFAULTHANDLER=1` is set on the Windows/macOS CI legs so a native Tk
  crash prints the Python line (`ci.yml`). The app itself reads only
  `APPDATA` / `XDG_CONFIG_HOME` to find its config directory.
- **Xvfb client cap:** the suite opens far more X clients than Xvfb's default
  256 (a fresh `tk.Tk()` per test plus pynput controllers, with `gc.disable()`
  for the whole run), so CI starts it with `-maxclients 2048`; without it the
  run dies with "Maximum number of clients reached" (`ci.yml`).

## Platform limits worth stating plainly

- **Linux needs X11.** Wayland does not let an application observe keys sent to
  other windows. The hotkey cannot work there; the program says so rather than
  failing silently.
- **macOS needs Accessibility permission**, and the build is unsigned, so the
  first launch requires right-click → Open.
- **Windows Defender flags it.** A global keyboard hook plus synthetic mouse
  input is exactly the heuristic pattern. Documented, not fixable.

## Testing

`tests/` runs under `unittest`. On Linux the suite needs a display because
pynput raises at import without one — CI runs it under `xvfb-run`.

**One measured caveat:** XTEST under Xvfb delivers every synthetic press *and*
release **exactly twice**. Asserting an exact fire count across several presses
measures the harness, not the code. Assert properties instead.

# Tech stack

The constraints here are not preferences. Each one was paid for once already,
and a change that ignores it will fail in a way that is hard to see from a diff.

## Runtime

| | |
|---|---|
| Language | Python 3.12 (CI builds on 3.12; 3.11 works) |
| GUI | **tkinter only** — stdlib |
| Input | **pynput only** — mouse *and* keyboard |
| Packaging | PyInstaller, `--onedir`, `--windowed`, `--noupx` |
| Config | JSON in the platform config directory |
| HTTP | `urllib.request` from the stdlib |

### Why no third-party GUI or HTTP library

Every dependency has to be frozen into the binary, and every frozen dependency
is another chance for PyInstaller's static analysis to miss a lazily imported
backend and ship something that dies at launch. The program is a dark window
with about fifteen controls; Qt or a requests dependency buys nothing that
pays for that risk.

### Why pynput and not `keyboard`

`keyboard` supports Windows and Linux only, and needs root on Linux. A macOS
build using it would install cleanly and then never respond to a hotkey.
pynput speaks all three, and the mouse half was already required.

### Why not pynput's GlobalHotKeys

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

Linux builds on the **oldest** available runner: PyInstaller links the build
host's glibc, so a newer host produces a binary that refuses to start on older
distributions.

macOS archives are packed with `ditto`, not `zip`, or the bundle's symlinks and
permission bits are mangled and Finder refuses to open the app.

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

# Coding guidelines

## Comments

Comment the **why**, never the what. A comment that restates the code is noise
that rots; a comment explaining why a value is 650 and not 400, or why a
listener is hand-rolled instead of taken from the library, is the thing nobody
can reconstruct later.

Every non-obvious constant carries its reason. `650` is Java's 12-tick (600 ms)
sword-sweep charge plus a tick of margin; at the old 510 most hits landed
at 10 ticks, a 76%-damage non-sweep. `2.0` seconds is rotten flesh's 1.6 plus room
for a lagged tick. `0.25` is a debounce that also absorbs X11 auto-repeat.

A comment that cites a pipeline cycle's own doc (`docs/spec.md`,
`docs/test-review.md`, …) points at its archived copy in `docs/history/` —
the per-cycle docs themselves are never committed (`docs/history/README.md`).

## Structure and naming

The whole program is one file, `afk_clicker.py`; the tests are in `tests/`
(`test_hotkey.py`, `test_ui.py`, `test_updater.py`, and the release-only
`test_chords_slow.py`), sharing `tests/context.py`.

Watch for shadowing. The Tk widget class `Button` once shadowed pynput's mouse
`Button`, turning every `Button.right` in the click loop into a latent
`AttributeError` that only the eating path would have hit. It is imported as
`MouseButton` now.

## Input validation

Anything read from disk or typed by a user is untrusted.

- `_num()` never trusts an entry box at click time.
- Parsing stored structures **validates** instead of wrapping the parse in
  `try/except`. `{"keys": "nope"}` raises nothing at all: iterating a string
  yields characters, and a naive parser builds a plausible object out of
  garbage. Check the shape and the types, then decide.
- A corrupt config starts from defaults; it never blocks startup.

## Failure behaviour

Say what went wrong and what would fix it. "GitHub unreachable" and "no release
published" are different problems and only one is worth retrying. A read-only
install directory gets named as such rather than producing a silent no-op.

Never leave a mouse button held down. `_release_right()` runs in a `finally`.

## Security

The program downloads its own updates and executes them, so the updater is the
boundary. The archive is checked against the release's `SHA256SUMS` before
anything is extracted, and entries that escape the staging directory are
refused (`ROADMAP.md`, "Update integrity"). Any string from the network that
reaches `write_swap_script` is validated at its source, not escaped
downstream: a release tag once flowed unvalidated into the generated swap
script (G#36, `docs/history/README.md`).

## Concurrency

**Only the main thread may touch Tk.** Not a widget, not a `StringVar`, not
`root.after()`. Reading a variable from a worker happens to work while the main
loop spins and raises `main thread is not in main loop` when it does not.

- The clicking thread reads a plain settings dict, snapshotted on the main
  thread by `_sync_settings`.
- Background work hands UI updates to `_ui()`, a queue drained by `_drain_ui`.
- Cancel every pending `after()` job on close, or Tcl reports "invalid command
  name" as the interpreter goes away.

## Tests

Every fix lands with a test that fails without it. Test the property, not the
plumbing — and when a test fails, find out whether the code or the harness is
wrong before changing either. Two "bugs" in this project's history were the
test comparing an enum member to its `.value`, and the Xvfb double-delivery.

Network tests skip cleanly when offline; they never fail the suite for it.

The PR suite (`ci.yml`) runs on Linux, Windows and macOS; the slow
synthetic-key-press sweep runs only with `AFK_SLOW_TESTS=1`, which the release
pipeline sets. Commands: `AGENTS.md`.

## Versioning

Below `1.0.0` until the UI and the settings format stop moving, and until Leo
says otherwise. Only minor and patch advance. A bug fix in a released version
is a patch, on its own tag. Version source: `__version__` in `afk_clicker.py`,
checked against `release/{version}` by the release pipeline.

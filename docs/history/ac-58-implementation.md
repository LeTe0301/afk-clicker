# Implementation: Macros-specific regression test for the `put_game()` merge fix (G#58)

## Summary
Added one new regression test, `MacrosTab.test_a_macro_survives_an_unrelated_persist_call`,
that saves a macro via `_save_macro()` and then calls `_persist()` (the
Clicking-pane persistence path, which never knows about `"macros"`) and
asserts the macro survives both in memory and on disk. This exercises the
exact gap G#57's cycle review flagged as Finding #1: the hotkey-path test
already covers the `put_game()` merge fix, but nothing exercised it via the
macros path, since `_save_macro()` never calls `put_game()` itself.

Per the task brief, this branch was cut from `main`, not from the already-fixed
`feature/ac-57/per-game-hotkeys`, so `Store.put_game()` on this branch still had
the old wholesale-replace bug. Brought G#57's one-line fix forward onto this
branch (`afk_clicker.py:1759-1761`) so the new test has a real fix to guard —
this is **not** a new fix, it's forward-porting the identical change G#57
already made, and will net out as a no-op once G#57 and G#58 both merge to
`main` (G#57 already carries this exact line).

## Changes by file

### `afk_clicker.py`
- **`Store.put_game()`** (`:1759-1761`): `self.data["games"][game_id] = values`
  → `self.data["games"].setdefault(game_id, {}).update(values)`. Identical to
  G#57's fix, forward-ported onto this branch per the task brief — see
  "Deviations from spec" below.

### `tests/test_ui.py`
- **New `MacrosTab.test_a_macro_survives_an_unrelated_persist_call`**, added
  immediately after `test_save_macro_persists_and_arms_its_hotkey` (`:7559`),
  the test it's modeled on for call shape. Decorated with
  `@needs_input_permission` (same as its model — the macro carries a real
  hotkey, which arms a real `pynput` listener and hits the same macOS abort
  hazard documented on the class). Steps, per `docs/spec.md`'s "Test to add":
  1. `self.ui._select("minecraft")`.
  2. `self.ui._save_macro("minecraft", None, "Test macro", hotkey, steps)`,
     asserted `True`.
  3. `self.ui._persist()` — the unrelated persistence call under test.
  4. Asserts the macro is still present in
     `self.ui.store.game("minecraft")["macros"]` (length 1, same name) and in
     a fresh `app.Store(self.config)` reload from disk.

Added to `MacrosTab`, not `StoreMacroFiltering`, per the spec's own
instruction to pick "whichever already has a `self.ui`/`self.store` fixture
selecting `minecraft`" — `StoreMacroFiltering`'s tests construct `app.Store`
directly against a hand-written config file and never touch `self.ui` at all,
so `MacrosTab` (which already has `self.ui._select("minecraft")` in several
sibling tests) is the closer fit.

## Key decisions / tradeoffs
- Used `self.ui._persist()` directly rather than driving a real field
  edit/trace, per the spec's own explicit instruction ("simplest, most direct
  route to the exact code path that wiped macros").
- Reused the exact `_save_macro()` call shape, hotkey object, and on-disk
  reload assertion from `test_save_macro_persists_and_arms_its_hotkey` rather
  than inventing a new fixture pattern — zero new surface.

## Deviations from spec
None from `docs/spec.md` itself. The one-line `put_game()` fix is not part of
this ticket's stated scope ("No change to `put_game()`... — the fix already
shipped in G#57. This ticket is test-coverage only") in the literal sense that
G#57 is where the fix was designed and reviewed — but the task brief
explicitly directed bringing that already-approved one-line change forward
onto this branch, since without it the new test would be testing nothing (this
branch's `main`-cut state still had the bug). Recorded here for clarity: this
diff's `afk_clicker.py` change is a forward-port of G#57's fix, not a new
design decision, and should collapse to a no-op diff once both G#57 and G#58
land on `main`.

## Known limitations
None beyond what `test_save_macro_persists_and_arms_its_hotkey` (its model)
already carries: `needs_input_permission` skips this test on macOS CI (starting
a real `pynput` listener there aborts the process — see issue #7), same as
every other real-hotkey test in this file.

## Sabotage verification (run this session)
1. Reverted `put_game()` to the old wholesale-replace body
   (`self.data["games"][game_id] = values`).
2. Ran the new test alone:
   ```
   DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest \
       tests.test_ui.MacrosTab.test_a_macro_survives_an_unrelated_persist_call -v
   ```
   Result: **FAILED** —
   `KeyError: 'macros'` at `self.ui.store.game("minecraft")["macros"]`
   (the dict `_persist()` wrote back had no `"macros"` key at all; clear,
   unambiguous failure, not a silent pass).
3. Restored the fix (`setdefault(game_id, {}).update(values)`).
4. Re-ran the same test alone: **OK** (1 test, green).

## How to verify locally
Environment (this repo's convention: a venv with `pynput` + Xvfb, started
directly rather than via `xvfb-run`, which fails here with "xauth command not
found"):
```
Xvfb :99 -screen 0 1280x1024x24 &   # already running in this session
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .
```

### This ticket's own test
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest \
    tests.test_ui.MacrosTab.test_a_macro_survives_an_unrelated_persist_call -v
# Ran 1 test, OK
```

### Full suite result (this session)
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .
Ran 514 tests in 96.614s
OK (skipped=10)
```
514 = the pre-existing 513-test baseline + 1 new test this cycle. The 10 skips
are the pre-existing macOS-only `needs_input_permission` guards, which do not
trigger on this Linux run's skip count change (same 10 as before this cycle).

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
?? docs/implementation.md
?? docs/spec.md
```
No file outside `afk_clicker.py`/`tests/test_ui.py` was touched by the code
change itself; no scratch file was left in the repo tree.

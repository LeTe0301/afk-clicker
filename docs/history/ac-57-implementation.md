# Implementation: Per-game hotkeys (G#57)

## Summary
The single top-level toggle hotkey (`store.data["hotkey"]`, one `HotkeyWatcher`
armed once at startup regardless of the selected game) became an optional,
per-game value (`store.game(id)["hotkey"]`), re-armed on every real game
switch by a new `_arm_toggle_hotkey()`/`_disarm_toggle_hotkey()` pair that
mirrors the macros feature's existing `_arm_macro_hotkeys()` rebuild-on-switch
lifecycle — with the one deliberate exception the spec called out up front: a
same-game rebuild (theme/scale change) must not tear down and recreate the
live listener, guarded by a new `self._toggle_armed_for` slot, so
`HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild`
stays green unmodified. `SETTINGS_VERSION` bumped 2→3 with a migration that
copies the old global chord into every already-configured game. Built to
`docs/design.md`'s mechanism everywhere it names a deviation from
`docs/spec.md` (the capture-generation guard, and the honest arm-failure
state) — both implemented as `docs/design.md` describes, not as
`docs/spec.md`'s own original, less-thorough code sketch.

A pre-existing, unrelated bug was found and fixed because it directly blocks
this ticket's own acceptance criteria — see "Deviations from spec" below.

## Changes by file

### `afk_clicker.py`
- **`SETTINGS_VERSION`** (`:1571`): `2` → `3`.
- **New `_migrate_settings_v2_to_v3(data)`** (next to `_migrate_settings_v1_to_v2`):
  copies `data["hotkey"]` (if present) into every entry of `data["games"]`,
  verbatim per `docs/spec.md` §1. Registered as `_SETTINGS_MIGRATIONS[2]`.
- **`Store.__init__`**: dropped `"hotkey": None` from the default top-level
  dict. Added a per-game `"hotkey"` filter in the existing per-game loop,
  right after the `"macros"` filter — same `Hotkey.from_json()`
  reject-not-coerce contract, drops a corrupt blob for that game only.
- **`Store.put_game()`** — see "Deviations from spec" below; changed from a
  wholesale replace to a merge.
- **`AfkAutoclicker.__init__`**: added `self._toggle_armed_for = None` (which
  game id `self.hk_listener` is currently armed for), `self._capture_gen = 0`
  and `self._capture_thread_gen = None` (the generation-counter guard from
  `docs/design.md`, replacing the spec's own `_hotkey_capture_game` idea —
  see deviations). Deleted the startup-arm block that read
  `self.store.data.get("hotkey")` and called `apply_hotkey()` once at
  startup — dead code now, since `_build_content()`'s own bootstrap
  `_select(self.current, persist=False)` call (already running by the time
  `__init__` reaches that point, inside the preceding `_build_ui(s)` call)
  arms the initially-selected game's hotkey via `_arm_toggle_hotkey()`.
- **`_build_content()`** (`:3614` area): subtitle text
  `"Hotkey  ·  shared by every game"` → `"Hotkey  ·  this game only"`, per
  `docs/design.md`.
- **`_select()`**: added `self._arm_toggle_hotkey()`, called right before the
  existing macros block (`_refresh_macros_pane()`/`_arm_macro_hotkeys()`/
  `_arm_macro_intervals()`).
- **New `_arm_toggle_hotkey()`/`_disarm_toggle_hotkey()`** (placed right after
  `apply_hotkey()`, before the `# ---------- macros ----------` section,
  i.e. immediately next to `_arm_macro_hotkeys()`/`_disarm_macro_hotkeys()`
  as the spec asked): `_arm_toggle_hotkey()` early-returns if
  `self.current == self._toggle_armed_for` (the rebuild-identity guard),
  otherwise bumps `_capture_gen`, disarms, discards any pending unapplied
  candidate, reads the selected game's stored hotkey, and either arms it,
  shows `"Not set"`, or — `docs/design.md` deviation #3 — on an arm failure
  with a stored chord, shows `_hotkey_error()` and restores the candidate
  with Apply re-enabled instead of a silent `"Not set"`.
- **`register_hotkey()`/`capture_hotkey()`**: rewritten per
  `docs/design.md`'s generation-counter design (deviations #1/#2 — see
  below). `register_hotkey()` now blocks only a same-generation in-flight
  capture; `capture_hotkey(gen)` takes the generation it was started for and
  routes every UI hand-off through a new `_capture_ui(gen, fn)` helper that
  runs `fn()` only if `gen` is still current. `self.hotkey = hotkey` moved
  out of the worker thread and into `_hotkey_captured(hotkey)` (now takes
  the hotkey as a parameter instead of reading `self.hotkey`).
- **`apply_hotkey()`**: `self.store.data["hotkey"] = ...` →
  `self.store.game(self.current)["hotkey"] = ...`; sets
  `self._toggle_armed_for = self.current` on a successful arm; the manual
  "stop the old listener" block at the top replaced with a call to the new
  `_disarm_toggle_hotkey()` (reuse, no behavior change).

### `tests/test_ui.py`
- **`HotkeyPersistence`**: `test_a_corrupt_hotkey_starts_clean` and
  `test_nothing_is_saved_when_no_hotkey_was_applied` rewritten against
  `data["games"][game_id]["hotkey"]` instead of the old top-level key, per
  the spec's own named test impact.
  `test_capture_refuses_without_permission` updated to pass the new
  required `gen` argument (`self.ui._capture_gen`) to `capture_hotkey()` —
  a necessary signature-change fix, not a behavior change; the test still
  exercises the same permission-refusal path via a directly-started thread.
  `test_restored_and_armed_after_restart`,
  `test_no_listener_is_started_without_permission`, and
  `test_registered_hotkey_cleared_on_second_apply_without_permission`
  needed no change and stay green.
- **`HotkeyListenerSurvivesRebuild`**: unmodified, confirmed green — the
  regression tripwire for the `_toggle_armed_for` guard.
- **`SettingsSchemaVersion`**: five new tests for the v2→v3 migration
  (carries into one game / into every configured game / no games configured
  / no old hotkey ever set) and the per-game corrupt-blob filter (dropped for
  that game only, a sibling game's own hotkey unaffected) — same style as
  the existing `test_v1_*` migration tests in this class.
- **New `PerGameHotkeys(UITestCase)`** class (after
  `HotkeyListenerSurvivesRebuild`): per-game isolation across a real switch
  (each game's own chord armed only while selected, re-armed correctly on
  switching back), a game with no hotkey showing `"Not set"` after switching
  away from one that has one, two games sharing a chord causing no error,
  the stale-capture-after-switch guard exercised directly via `_capture_ui()`
  (both a single A→B switch and the A→B→A case `docs/design.md` specifically
  called out), `register_hotkey()` on a newly-selected game not being
  blocked by the previous game's still-alive capture thread (a blocking stub
  instead of a real `pynput.Listener`, matching this file's own
  "never a real listener/never inline a blocking join in a test" convention),
  an unapplied recorded candidate being discarded on switch, and the
  arm-failure-on-switch honest-state path (`docs/design.md` deviation #3).

### `docs/ROADMAP.md`
Checked off "Per-game hotkeys" under "Later", with a short description —
matching this file's own established convention of every other completed
roadmap item (e.g. "Settings schema version", "A Macros tab").

## Key decisions / tradeoffs
- **Built to `docs/design.md`'s three named deviations, not `docs/spec.md`'s
  own code sketch**, as instructed: the generation-counter capture guard
  (`_capture_gen`/`_capture_thread_gen`/`_capture_ui`) replaces the spec's
  `_hotkey_capture_game` idea; `register_hotkey()` returns early only for a
  same-generation capture, not any alive one; `_arm_toggle_hotkey()` on an
  arm failure with a stored chord shows the error and restores the
  candidate rather than a silent `"Not set"`.
- **`_arm_toggle_hotkey()`/`_disarm_toggle_hotkey()` placed immediately next
  to `apply_hotkey()`**, inside the existing `# ---------- hotkey ----------`
  section, rather than physically inside the `# ---------- macros ----------`
  section the spec's prose points at — they belong with the rest of the
  hotkey machinery; "next to `_arm_macro_hotkeys()`" is satisfied by sitting
  immediately before that section starts.
- **`apply_hotkey()` reuses the new `_disarm_toggle_hotkey()` instead of
  repeating its own "stop the old listener" block** — zero new surface,
  matches this codebase's own stated reuse convention; no behavior change.

## Deviations from spec

1. **A pre-existing bug in `Store.put_game()` was found and fixed, because
   it silently breaks this ticket's own acceptance criteria otherwise.**
   `put_game()` wholesale-replaced `self.data["games"][game_id]` with
   whatever `_persist()` built from the Clicking tab's own fields —
   `_persist()` has never known about `"macros"` or (now) `"hotkey"`, so
   the very next `_persist()` call for the same game (which runs
   unconditionally at the tail of *every* `_select()` call, and explicitly
   in `on_close()`) silently wiped both. Confirmed directly, independent of
   any change in this diff: select a game, save a macro, call `on_close()`
   with no other edit — the macro is gone from disk. This is not
   hypothetical; it is the single most basic "record a hotkey, then close
   the app" flow this ticket's own acceptance criteria require. Root cause
   fixed at the one shared method every per-game persistence call routes
   through: `put_game()` now merges (`setdefault(...).update(values)`)
   instead of replacing. The only two tests calling `put_game()` directly
   assert its save-success return value, not the per-game dict's shape, so
   neither needed a change; the fix also (correctly) makes the pre-existing
   macros-wiped-on-persist bug a non-issue, though no new test was added
   specifically for the macros case — out of this ticket's direct scope,
   flagged here for visibility rather than silently bundled in as if it
   were part of the hotkey feature itself. **This is a drive-by fix in the
   literal sense of "not asked for by the spec," but was necessary: without
   it, `apply_hotkey()` followed by anything that touches `_persist()` for
   the same game (switching tabs does not; closing the app, or editing any
   Clicking field, does) silently loses the just-applied hotkey, failing
   several of `docs/spec.md`'s own acceptance criteria outright.**
2. Everything else matches `docs/spec.md`/`docs/design.md` as written,
   including the three design deviations from the spec's own §3/§4
   (pre-approved by the orchestrator per the task brief) and every other
   proposed-approach item (storage key name, migration carry-forward-to-
   every-game choice, no collision validation, Hotkey tab staying in place,
   subtitle wording from `docs/design.md`).

## Known limitations
- Per-game isolation and the capture-generation guard are verified by
  reading/driving internal state directly (`registered_hotkey`,
  `hk_listener`, `_capture_gen`, `_toggle_armed_for`, a blocking stub instead
  of a real `pynput.Listener`), the same technique this suite's existing
  `MacrosTab`/`HotkeyPersistence` tests already use — not by synthesizing
  real OS-level key presses through two independently-armed listeners at
  once. This matches the existing precedent in this file and avoids the
  documented macOS listener-abort hazard (`needs_input_permission`, issue
  #7); it does not prove two real listeners can never both fire for an
  instant during a switch on a real OS, only that at most one is ever
  `self.hk_listener` at a time, which is what `_arm_toggle_hotkey()`'s
  disarm-before-arm ordering guarantees.
- `docs/design.md`'s own layout verification for the new subtitle string
  was done by metric estimate on a Linux sandbox without Segoe UI installed,
  not a real render on Windows — carried forward unchanged, not re-verified
  here.
- The `HOTKEY_HELP` copy clipping issue `docs/design.md` names under "Known
  pre-existing copy limits" is unchanged, as instructed (spec scope).

## How to verify locally
Environment (this repo's convention: a venv with `pynput` + Xvfb, started
directly rather than via `xvfb-run`):
```
Xvfb :99 -screen 0 1280x1024x24 &
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### This ticket's own tests
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.PerGameHotkeys \
    tests.test_ui.HotkeyPersistence tests.test_ui.HotkeyListenerSurvivesRebuild \
    tests.test_ui.SettingsSchemaVersion tests.test_ui.StoreMacroFiltering \
    tests.test_ui.MacrosTab -v
# Ran 43 tests, OK
```
`PerGameHotkeys` re-run three times in isolation to check for flakiness in
the thread/event-based tests (the stale-capture and blocking-capture-stub
tests) — stable all three times.

### Full suite result (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui
Ran 404 tests in 97.070s

OK
```
404 = the pre-existing 391-test baseline + 13 new tests this cycle (8 in
`PerGameHotkeys`, 5 in `SettingsSchemaVersion`). No skips reported on this
Linux run (the macOS-only `needs_input_permission` skip guards do not
trigger here).

### Verification of scope
```
git status --short
 M afk_clicker.py
 M backlog.md        (pre-existing, from the product-manager stage before this session)
 M docs/ROADMAP.md
 M tests/test_ui.py
?? docs/design.md     (pre-existing, written by ux-designer)
?? docs/implementation.md
?? docs/spec.md       (pre-existing, written by product-manager)
```
No file outside `afk_clicker.py`/`tests/test_ui.py`/`docs/ROADMAP.md` was
touched by the code change itself; no scratch file was left in the repo
tree.
